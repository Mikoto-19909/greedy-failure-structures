"""Produce, resume and summarize integer L5 DUAL certificates offline."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover.algorithms import greedy
from r4_dual_core import certificates
from r4_dual_io import (validate_configuration, SourceAccess, instance, read_json, write_json,
                        write_checkpoint, load_records, RuntimeBudget, check_resources, check_code_revision,
                        output_size, METRICS)
from validate_r2_budget_grid import memory_usage


def evaluate(original, config):
    task = original["task"]
    started = time.perf_counter()
    solutions = [greedy(instance(original["sets"], task, k)) for k in task["budgets"]]
    greedy_seconds = time.perf_counter() - started
    started = time.perf_counter()
    values = certificates(instance(original["sets"], task, 1).sets, task["budgets"])
    for value, solution, reference in zip(values, solutions, original["values"]):
        actual = (value["greedy"], sorted(value["path"]))
        if actual != (solution.coverage, list(solution.selected)) or actual != (reference["greedy"], reference["greedy_selected"]):
            raise ValueError("DUAL path differs from public or archived Greedy")
    return {"version": config["version"], "source_commit": config["source_commit"],
            "task": task, "source": original, "status": "complete", "values": values,
            "timing": {"greedy_seconds": greedy_seconds, "production_seconds": time.perf_counter() - started,
                       "peak_memory_bytes": memory_usage()}}


def run(config, source, output, resume=False, stop_after=None):
    validate_configuration(config)
    check_code_revision(config)
    if stop_after is not None and (type(stop_after) is not int or stop_after < 0):
        raise ValueError("stop_after must be a nonnegative graph count")
    output = Path(output)
    if (output / "config.json").exists():
        if not resume or read_json(output / "config.json") != config:
            raise ValueError("existing batch requires resume with unchanged configuration")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("new output directory must be empty")
    else:
        write_json(output / "config.json", config)
    timing = {"source_read_seconds": 0.0, "greedy_seconds": 0.0, "production_seconds": 0.0,
              "resume_verification_seconds": 0.0, "checkpoint_io_seconds": 0.0}
    with RuntimeBudget(output, config, "production") as budget:
        write_json(output / "run_status.json", {"complete": False})
        return _produce(config, source, output, stop_after, budget, timing)


def _produce(config, source, output, stop_after, budget, timing):
    from validate_r4_dual import verify_record
    done, computed, reused = set(), 0, 0
    check_resources(output, config, memory_usage())
    current_bytes = output_size(output)
    with SourceAccess(source, config) as access:
        for row in load_records(output, config, partial=True):
            budget.check()
            started = time.perf_counter()
            original = access.record(row["task"])
            timing["source_read_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            verify_record(row, original, config)
            timing["resume_verification_seconds"] += time.perf_counter() - started
            done.add(row["task"]["base_graph_id"])
            reused += 1
        for task in config["tasks"]:
            if task["base_graph_id"] in done:
                continue
            if stop_after is not None and computed >= stop_after:
                break
            budget.check()
            if memory_usage() > config["limits"]["memory_bytes"]:
                raise RuntimeError("DUAL memory budget exhausted; preserve checkpoints")
            started = time.perf_counter()
            original = access.record(task)
            source_seconds = time.perf_counter() - started
            row = evaluate(original, config)
            row["timing"]["source_read_seconds"] = source_seconds
            for key in ("source_read_seconds", "greedy_seconds", "production_seconds"):
                timing[key] += row["timing"][key]
            started = time.perf_counter()
            write_checkpoint(output / "graphs" / (task["base_graph_id"] + ".json"), row)
            timing["checkpoint_io_seconds"] += time.perf_counter() - started
            current_bytes += (output / "graphs" / (task["base_graph_id"] + ".json")).stat().st_size
            done.add(task["base_graph_id"])
            computed += 1
            if current_bytes > config["limits"]["output_bytes"]:
                raise RuntimeError("DUAL output budget exhausted; preserve checkpoints")
            if memory_usage() > config["limits"]["memory_bytes"]:
                raise RuntimeError("DUAL memory budget exhausted; preserve checkpoints")
            budget.check()
            if len(done) % 100 == 0 or len(done) == len(config["tasks"]):
                print(f"DUAL produced {len(done)}/{len(config['tasks'])}", flush=True)
        check_resources(output, config, memory_usage())
        budget.check()
        result = {"complete": len(done) == len(config["tasks"]), "computed": computed, "reused": reused,
                  "graph_count": len(done), "timing": timing, "peak_memory_bytes": memory_usage()}
        write_json(output / "run_status.json", result)
    return result


def summarize(records):
    rows = []
    for record in records:
        task = record["task"]
        for value, ref in zip(record["values"], record["source"]["values"]):
            k, g, o = value["k"], value["greedy"], ref["optimum"]
            initial, prefix, dual = value["initial_upper"], value["prefix_upper"], value["dual_upper"]
            ir, pr, dr = (g / initial if initial else None), (g / prefix if prefix else None), (g / dual if dual else None)
            rows.append({"base_graph_id": task["base_graph_id"], "instance_id": ref["instance_id"],
                         "n": task["n"], "d": task["d"], "k": k, "greedy": g, "optimum": o,
                         "initial_upper": initial, "prefix_upper": prefix, "dual_upper": dual,
                         "endpoint": "k=1" if k == 1 else "k=M" if k == task["n"] else "interior",
                         "tightening_initial": initial - dual, "tightening_prefix": prefix - dual,
                         "initial_ratio": ir, "prefix_ratio": pr, "dual_ratio": dr,
                         "ratio_gain_initial": dr - ir if dr is not None and ir is not None else None,
                         "ratio_gain_prefix": dr - pr if dr is not None and pr is not None else None,
                         "dual_over_optimum": dual / o if o else None,
                         "initial_certified": int(g == initial), "prefix_certified": int(g == prefix), "dual_certified": int(g == dual)})
    cells = []
    grouped = {}
    for row in rows:
        grouped.setdefault((row["n"], row["d"], row["k"]), []).append(row)
    for (n, d, k), group in sorted(grouped.items()):
        cell = {"n": n, "d": d, "k": k, "count": len(group), "endpoint": group[0]["endpoint"],
                "tightened_initial": sum(r["tightening_initial"] > 0 for r in group),
                "tightened_prefix": sum(r["tightening_prefix"] > 0 for r in group)}
        for method in ("initial", "prefix", "dual"):
            cell[method + "_certified"] = sum(r[method + "_certified"] for r in group)
        for metric in METRICS:
            samples = sorted(r[metric] for r in group if r[metric] is not None)
            cell[metric + "_missing"] = len(group) - len(samples)
            cell[metric + "_mean"] = statistics.fmean(samples) if samples else None
            cell[metric + "_median"] = statistics.median(samples) if samples else None
            cell[metric + "_p90"] = samples[math.ceil(.9 * len(samples)) - 1] if samples else None
        cells.append(cell)
    return rows, cells


def analyze(output, source):
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    check_code_revision(config)
    timing = {"source_read_seconds": 0.0, "certificate_seconds": 0.0, "reference_seconds": 0.0}
    with RuntimeBudget(output, config, "analyze") as budget:
        write_json(output / "analysis_status.json", {"status": "incomplete"})
        return _analyze(output, source, config, budget, timing)


def _analyze(output, source, config, budget, timing):
    from validate_r4_dual import verify_record
    with SourceAccess(source, config) as access:
        def checked_records():
            for row in load_records(output, config):
                budget.check()
                started = time.perf_counter()
                original = access.record(row["task"])
                timing["source_read_seconds"] += time.perf_counter() - started
                checked = verify_record(row, original, config)
                for name in ("certificate_seconds", "reference_seconds"):
                    timing[name] += checked[name]
                yield row
        started = time.perf_counter()
        rows, cells = summarize(checked_records())
        # This residual is summary/loop overhead, not a second total wall cost.
        timing["summary_seconds"] = max(0.0, time.perf_counter() - started - sum(timing.values()))
        started = time.perf_counter()
        for filename, values in (("budget_results.csv", rows), ("cell_summary.csv", cells)):
            destination = output / filename
            temporary = destination.with_suffix(".csv.tmp")
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(values[0]))
                writer.writeheader()
                writer.writerows(values)
            temporary.replace(destination)
        timing["table_io_seconds"] = time.perf_counter() - started
        result = {"status": "complete", "graphs": len({r["base_graph_id"] for r in rows}),
                  "budget_rows": len(rows), "cells": len(cells), "timing": timing,
                  "peak_memory_bytes": memory_usage()}
        check_resources(output, config, memory_usage())
        budget.check()
        write_json(output / "analysis_status.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["run", "analyze"])
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stop-after", type=int, help="save a controlled graph-boundary checkpoint")
    args = parser.parse_args(argv)
    try:
        if args.operation == "run":
            if not args.config:
                raise ValueError("run requires --config")
            result = run(validate_configuration(read_json(args.config)), args.source, args.output, args.resume, args.stop_after)
        else:
            if args.config or args.resume or args.stop_after is not None:
                raise ValueError("analyze reads saved configuration; run options are invalid")
            result = analyze(args.output, args.source)
        print(result)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
