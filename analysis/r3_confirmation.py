"""Run/recover frozen F3 samples and summarize independently verified records."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover._generators_random import fixed_size
from r2_design import read_json, write_json, RuntimeBudget, computed_results
from r3_confirmation_inputs import validate_configuration, load_records, identity
from r3_feasibility import construct, evaluate
from validate_r2_budget_grid import memory_usage


def compute_graph(task, config):
    started = time.perf_counter()
    instance = fixed_size(universe_size=12, set_count=12, k=4, set_size=3, unique_sets=False, seed=task["seed"])
    original = [[a for a in range(12) if mask & (1 << a)] for mask in instance.sets]
    chains = []
    for specification in task["chains"]:
        chain = construct(original, 12, specification["seed"], specification["direction"], [2048])
        chain["replica"] = specification["replica"]
        chains.append(chain)
    constructed = time.perf_counter()
    # The four constructions are complete before consulting any outcome.
    values = evaluate(original, 12, 4)
    for chain in chains:
        endpoint = chain["endpoints"][0]
        endpoint["values"] = evaluate(endpoint["sets"], 12, 4)
        endpoint["instance_id"] = identity(endpoint["sets"], task, config, chain)
    return {"task": task, "status": "complete", "sets": original,
            "instance_id": identity(original, task, config), "values": values, "chains": chains,
            "timing": {"construction_seconds": constructed - started,
                       "evaluation_seconds": time.perf_counter() - constructed,
                       "peak_memory_bytes": memory_usage()}}


def run(config, output, workers=4, resume=False, stop_after=None):
    validate_configuration(config)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    output = Path(output)
    if output.exists() and not resume:
        raise ValueError("F3 output exists; use recovery with the same frozen configuration")
    if output.exists() and read_json(output / "config.json") != config:
        raise ValueError("recovery configuration differs from saved F3 design")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "config.json", config)
    records = load_records(output, config, partial=True)
    done = {r["task"]["base_graph_id"] for r in records}
    pending = [t for t in config["tasks"] if t["base_graph_id"] not in done]
    if stop_after is not None:
        pending = pending[:stop_after]
    size = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
    started = time.perf_counter()
    state = {"complete": False, "computed": 0, "reused": len(done), "workers": workers}
    write_json(output / "run_status.json", state)
    settings = {key: config[key] for key in ("version", "n", "d", "k")}
    with RuntimeBudget(output, config, "r3_production") as budget:
        for record in computed_results(compute_graph, [(t, settings) for t in pending], workers, budget):
            if record["timing"]["peak_memory_bytes"] * (workers + 1) > config["limits"]["memory_bytes"]:
                raise RuntimeError("F3 memory budget exceeded; retain saved samples")
            path = output / "graphs" / (record["task"]["base_graph_id"] + ".json")
            write_json(path, record)
            size += path.stat().st_size
            done.add(record["task"]["base_graph_id"])
            state["computed"] += 1
            if size > config["limits"]["output_bytes"]:
                raise RuntimeError("F3 output budget exceeded; retain saved samples")
            if len(done) % 100 == 0 or len(done) == config["sample_count"]:
                print(f"R3 computed {len(done)}/{config['sample_count']}", flush=True)
    state.update(complete=len(done) == config["sample_count"], wall_seconds=time.perf_counter() - started)
    write_json(output / "run_status.json", state)
    return state


def summary_rows(records, config):
    base_rows, endpoint_rows = [], []
    for record in records:
        sides = {}
        for direction in (-1, 1):
            endpoints = [c["endpoints"][0] for c in record["chains"] if c["direction"] == direction]
            sides[direction] = {"first_loss": sum(e["values"]["first_loss"] for e in endpoints) / 2,
                                "failure": sum(e["values"]["greedy"] < e["values"]["optimum"] for e in endpoints) / 2,
                                "gap": math.fsum((e["values"]["optimum"] - e["values"]["greedy"]) / e["values"]["optimum"] for e in endpoints) / 2,
                                "exposure": sum(e["exposure"] for e in endpoints) / 2}
        base_rows.append({"base_graph_id": record["task"]["base_graph_id"], "repetition": record["task"]["repetition"],
                          "low_first_loss": sides[-1]["first_loss"], "high_first_loss": sides[1]["first_loss"],
                          "difference": sides[1]["first_loss"] - sides[-1]["first_loss"],
                          "low_failure": sides[-1]["failure"], "high_failure": sides[1]["failure"],
                          "low_relative_gap": sides[-1]["gap"], "high_relative_gap": sides[1]["gap"],
                          "low_exposure": sides[-1]["exposure"], "high_exposure": sides[1]["exposure"]})
        for chain in record["chains"]:
            endpoint = chain["endpoints"][0]
            endpoint_rows.append({"base_graph_id": record["task"]["base_graph_id"], "direction": chain["direction"],
                                  "replica": chain["replica"], "chain_seed": chain["seed"],
                                  "instance_id": endpoint["instance_id"], "exposure": endpoint["exposure"],
                                  "greedy": endpoint["values"]["greedy"], "optimum": endpoint["values"]["optimum"],
                                  "forced_optimum": endpoint["values"]["forced_optimum"],
                                  "first_loss": int(endpoint["values"]["first_loss"]),
                                  "accepted": endpoint["accepted"], "legal": endpoint["legal"], "proposals": endpoint["proposals"]})
    n = len(base_rows)
    theta = math.fsum(r["difference"] for r in base_rows) / n
    half = math.sqrt(2 * math.log(2 / config["alpha"]) / n)
    lower, upper = max(-1.0, theta - half), min(1.0, theta + half)
    summary = {"n": n, "endpoints": len(endpoint_rows), "delta": theta, "lower": lower, "upper": upper,
               "half_width": half, "confidence": 1 - config["alpha"],
               "direction": "positive" if lower > 0 else "negative" if upper < 0 else "inconclusive",
               "graphs_without_exposure_separation": sum(r["high_exposure"] <= r["low_exposure"] for r in base_rows)}
    for name in ("low_first_loss", "high_first_loss", "low_failure", "high_failure",
                 "low_relative_gap", "high_relative_gap", "low_exposure", "high_exposure"):
        summary[name] = math.fsum(r[name] for r in base_rows) / n
    return base_rows, endpoint_rows, summary


def analyze(output, workers=4):
    from validate_r3_confirmation import verify_record
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    records = load_records(output, config)
    settings = {key: config[key] for key in ("version", "n", "d", "k")}
    with RuntimeBudget(output, config, "r3_analysis") as budget:
        # Recheck the loaded snapshot, never authorize it with a historical passed flag.
        for timing in computed_results(verify_record, [(r, t, settings) for r, t in zip(records, config["tasks"])], workers, budget):
            if timing["peak_memory_bytes"] * (workers + 1) > config["limits"]["memory_bytes"]:
                raise RuntimeError("F3 analysis verification memory budget exceeded")
        base_rows, endpoint_rows, summary = summary_rows(records, config)
        budget.check()
        for name, rows in (("base_graph_summary.csv", base_rows), ("endpoint_results.csv", endpoint_rows)):
            with (output / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        write_json(output / "primary_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "analyze"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = validate_configuration(read_json(args.config if args.command == "run" else args.output / "config.json"))
    if config["phase"] != "confirmation":
        raise ValueError("CLI accepts only the frozen confirmation design")
    if args.command == "run":
        run(config, args.output, args.workers, args.resume)
    else:
        analyze(args.output, args.workers)


if __name__ == "__main__":
    main()
