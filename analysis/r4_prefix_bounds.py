"""R4 integer prefix certificates and fixed-corpus calibration (offline)."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover.algorithms import greedy
from r4_inputs import (configuration, validate_configuration, instance, source_record, check_source,
                       read_json, write_json, load_records, RuntimeBudget, check_resources)
from validate_r2_budget_grid import memory_usage


def certificates(masks, budgets):
    if not masks or budgets != sorted(set(budgets)) or not budgets:
        raise ValueError("nonempty ordered unique budgets required")
    if any(type(k) is not int or not 1 <= k <= len(masks) for k in budgets):
        raise ValueError("invalid budget")
    if any(type(mask) is not int or mask < 0 for mask in masks):
        raise ValueError("invalid candidate masks")
    covered, chosen, states = 0, [], []
    available = set(range(len(masks)))
    union_mask = 0
    for mask in masks:
        union_mask |= mask
    for t in range(max(budgets) + 1):
        best = max(available, key=lambda i: ((masks[i] & ~covered).bit_count(), -i)) if available else None
        gain = (masks[best] & ~covered).bit_count() if best is not None else 0
        states.append({"t": t, "coverage": covered.bit_count(), "max_gain": gain, "gain_witness": best})
        if t < max(budgets):
            chosen.append(best)
            available.remove(best)
            covered |= masks[best]
    values = []
    for k in budgets:
        prefixes = [{**s, "upper": s["coverage"] + k * s["max_gain"]} for s in states[:k + 1]]
        values.append({"k": k, "path": chosen[:k], "prefixes": prefixes,
                       "greedy": states[k]["coverage"], "union_size": union_mask.bit_count(),
                       "initial_upper": min(union_mask.bit_count(), k * states[0]["max_gain"]),
                       "upper": min(union_mask.bit_count(), *(s["upper"] for s in prefixes))})
    return values


def evaluate(source, task, config):
    started = time.perf_counter()
    original = source_record(source, task)
    source_seconds = time.perf_counter() - started
    started = time.perf_counter()
    solutions = [greedy(instance(original["sets"], task, k)) for k in task["budgets"]]
    greedy_seconds = time.perf_counter() - started
    started = time.perf_counter()
    masks = instance(original["sets"], task, task["budgets"][0]).sets
    values = certificates(masks, task["budgets"])
    for v, solution, ref in zip(values, solutions, original["values"]):
        if (v["greedy"], sorted(v["path"])) != (solution.coverage, list(solution.selected)):
            raise ValueError("offline path differs from public Greedy")
        if (v["greedy"], sorted(v["path"])) != (ref["greedy"], ref["greedy_selected"]):
            raise ValueError("Greedy differs from R2 source")
    return {"version": config["version"], "source_commit": config["source_commit"],
            "task": task, "source": original, "status": "complete", "values": values,
            "timing": {"source_read_seconds": source_seconds, "greedy_seconds": greedy_seconds,
                       "production_seconds": time.perf_counter() - started,
                       "peak_memory_bytes": memory_usage()}}


def run(config, source, output, resume=False, stop_after=None):
    validate_configuration(config)
    check_source(source, config)
    if config["phase"] == "calibration" and config.get("f4_status") != "frozen":
        raise ValueError("calibration requires the F4 frozen configuration")
    output = Path(output)
    if (output / "config.json").exists():
        if not resume or read_json(output / "config.json") != config:
            raise ValueError("existing batch needs resume with the same configuration")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("new output directory must be empty")
    else:
        write_json(output / "config.json", config)
    rows = load_records(output, config, partial=True)
    from validate_r4_prefix_bounds import verify_certificate
    with RuntimeBudget(output, config, "production") as budget:
        for row in rows:
            budget.check()
            verify_certificate(row, source_record(source, row["task"]), config)
        done = {r["task"]["base_graph_id"] for r in rows}
        pending = [t for t in config["tasks"] if t["base_graph_id"] not in done]
        selected = pending if stop_after is None else pending[:stop_after]
        for task in selected:
            budget.check()
            check_resources(output, config, memory_usage())
            row = evaluate(source, task, config)
            write_json(output / "graphs" / (task["base_graph_id"] + ".json"), row)
            done.add(task["base_graph_id"])
            check_resources(output, config, row["timing"]["peak_memory_bytes"])
            budget.check()
            print(f"R4 produced {len(done)}/{len(config['tasks'])}", flush=True)
        budget.check()
        check_resources(output, config, memory_usage())
    result = {"complete": len(done) == len(config["tasks"]), "computed": len(selected), "reused": len(rows)}
    write_json(output / "run_status.json", result)
    return result


def summarize(records):
    rows = []
    for record in records:
        task = record["task"]
        for v, ref in zip(record["values"], record["source"]["values"]):
            g, o, u, initial = v["greedy"], ref["optimum"], v["upper"], v["initial_upper"]
            row = {"base_graph_id": task["base_graph_id"], "n": task["n"], "d": task["d"], "k": v["k"],
                   "greedy": g, "optimum": o, "upper": u, "initial_upper": initial,
                   "certified_optimal": int(g == u), "initial_certified_optimal": int(g == initial),
                   "trivial_endpoint": int(v["k"] in {1, task["n"]}), "tightening": initial - u,
                   "upper_over_optimum": u / o if o else None,
                   "relative_upper_slack": (u - o) / o if o else None,
                   "greedy_ratio": g / o if o else None, "certified_ratio": g / u if u else None,
                   "relative_gap_bound": 1 - g / u if u else None}
            rows.append(row)
    cells = []
    for n, d, k in sorted({(r["n"], r["d"], r["k"]) for r in rows}):
        group = [r for r in rows if (r["n"], r["d"], r["k"]) == (n, d, k)]
        cell = {"n": n, "d": d, "k": k, "count": len(group),
                "certified_optimal": sum(r["certified_optimal"] for r in group),
                "initial_certified_optimal": sum(r["initial_certified_optimal"] for r in group),
                "trivial_endpoint": int(k in {1, n})}
        for metric in ("tightening", "upper_over_optimum", "relative_upper_slack", "greedy_ratio", "certified_ratio", "relative_gap_bound"):
            values = sorted(r[metric] for r in group if r[metric] is not None)
            cell[metric + "_missing"] = len(group) - len(values)
            for name, value in (("mean", statistics.fmean(values) if values else None),
                                ("median", statistics.median(values) if values else None),
                                ("p90", values[math.ceil(.9 * len(values)) - 1] if values else None)):
                cell[metric + "_" + name] = value
        cells.append(cell)
    return rows, cells


def analyze(output, source):
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    check_source(source, config)
    from validate_r4_prefix_bounds import verify_record
    with RuntimeBudget(output, config, "analyze") as budget:
        records = load_records(output, config)
        checks = {"source_read_seconds": 0.0, "certificate_seconds": 0.0, "reference_seconds": 0.0}
        for row in records:
            budget.check()
            started = time.perf_counter()
            original = source_record(source, row["task"])
            checks["source_read_seconds"] += time.perf_counter() - started
            checked = verify_record(row, original, config)
            for name in ("certificate_seconds", "reference_seconds"):
                checks[name] += checked[name]
        started = time.perf_counter()
        rows, cells = summarize(records)
        for name, values in (("budget_results.csv", rows), ("cell_summary.csv", cells)):
            with (output / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(values[0]))
                writer.writeheader()
                writer.writerows(values)
        write_json(output / "analysis_timing.json", {**checks, "summary_seconds": time.perf_counter() - started})
        check_resources(output, config, memory_usage())
        budget.check()
    return {"graphs": len(records), "budget_rows": len(rows), "cells": len(cells)}


def freeze(preflight, source, destination):
    """Fix the full R2 corpus only after current preflight data pass verification."""
    from validate_r4_prefix_bounds import validate_batch, verify_summaries
    preflight, destination = Path(preflight), Path(destination)
    if destination.exists():
        raise ValueError("F4 destination already exists; no implicit design replacement")
    config = validate_configuration(read_json(preflight / "config.json"))
    if config["phase"] != "preflight" or len(config["tasks"]) != 18:
        raise ValueError("F4 requires the planned 18 independent preflight graphs")
    verification = validate_batch(preflight, source)
    verify_summaries(preflight)
    records = load_records(preflight, config)
    component_work, expected_bytes, peak = 0.0, 0, memory_usage()
    cells = []
    for n in (12, 16, 20):
        for d in (2, 3, 4):
            selected = [r for r in records if (r["task"]["n"], r["task"]["d"]) == (n, d)]
            costs = []
            for r in selected:
                v = verification["graphs"][r["task"]["base_graph_id"]]
                p = r["timing"]
                # Both the full verifier and analyze independently recheck O.
                costs.append(p["source_read_seconds"] + p["greedy_seconds"] + p["production_seconds"]
                             + 2 * (v["source_read_seconds"] + v["certificate_seconds"] + v["reference_seconds"]))
                peak = max(peak, p["peak_memory_bytes"], v["peak_memory_bytes"])
            worst = max(costs)
            size = max((preflight / "graphs" / (r["task"]["base_graph_id"] + ".json")).stat().st_size for r in selected)
            component_work += 200 * worst
            expected_bytes += 200 * size
            cells.append({"n": n, "d": d, "worst_graph_seconds": worst, "worst_graph_bytes": size})
    execution = [json.loads(line) for line in (preflight / "execution.jsonl").read_text(encoding="utf-8").splitlines()]
    preflight_wall = sum(e["wall_seconds"] for e in execution)
    # In-entry wall time includes checkpoint I/O and analysis, plus the F4
    # recheck. The separate allowance covers startup and additional summary I/O.
    measured_wall_projection = 1800 * preflight_wall / len(records)
    estimate = {"cells": cells, "preflight_wall_seconds": preflight_wall,
                "component_projection_seconds": component_work,
                "observed_wall_projection_seconds": measured_wall_projection,
                "conservative_wall_seconds": preflight_wall + 2 * max(component_work, measured_wall_projection) + 600,
                "conservative_output_bytes": 2 * expected_bytes + 16 * 1024**2,
                "conservative_peak_memory_bytes": 2 * peak, "workers": 1,
                "safety_factor": 2, "summary_io_allowance_seconds": 600}
    if (estimate["conservative_wall_seconds"] > config["limits"]["wall_seconds"]
            or estimate["conservative_output_bytes"] > config["limits"]["output_bytes"]
            or estimate["conservative_peak_memory_bytes"] > config["limits"]["memory_bytes"]):
        write_json(preflight / "resource_gap.json", estimate)
        raise RuntimeError("complete calibration does not fit; no F4 file written")
    original = read_json(ROOT / "analysis" / "r2_f2_config.json")
    final = configuration("calibration", original)
    final.update(f4_status="frozen", resource_decision=estimate,
                 timing_contract=["source_read", "standard_greedy", "certificate_production",
                                  "certificate_verification", "exhaustive_reference", "summary_and_derived"])
    write_json(destination, final)
    return estimate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preflight", "run", "analyze", "freeze"])
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "freeze":
            if not args.config or args.resume:
                raise ValueError("freeze requires --config as a new F4 destination")
            result = freeze(args.output, args.source, args.config)
        elif args.operation == "analyze":
            if args.config or args.resume:
                raise ValueError("analyze reads its saved configuration")
            result = analyze(args.output, args.source)
        else:
            if args.operation == "preflight":
                if args.config:
                    raise ValueError("preflight derives the approved 18-source design")
                config = configuration("preflight", read_json(args.source / "config.json"))
            else:
                if not args.config:
                    raise ValueError("run requires --config")
                config = validate_configuration(read_json(args.config))
                if config["phase"] != "calibration":
                    raise ValueError("run accepts only F4 calibration, not test fixtures")
            result = run(config, args.source, args.output, args.resume)
        print(result)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
