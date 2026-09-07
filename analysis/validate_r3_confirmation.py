"""Independent current-input F3 verification and derived-result consistency checks."""
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
from validate_r3_feasibility import replay, exact_values
from validate_r2_budget_grid import memory_usage
from validate_greedy_failure_paths import compare


def verify_record(record, task, config):
    started = time.perf_counter()
    compare(record["task"], task, "F3 task")
    compare(record["status"], "complete", "F3 completion")
    instance = fixed_size(universe_size=12, set_count=12, k=4, set_size=3, unique_sets=False, seed=task["seed"])
    original = [[a for a in range(12) if mask & (1 << a)] for mask in instance.sets]
    compare(record["sets"], original, "F3 original graph")
    compare(record["instance_id"], identity(original, task, config), "original identity")
    compare(record["values"], exact_values(original, 4), "original references")
    expected = []
    for spec in task["chains"]:
        chain = replay(original, 12, spec["seed"], spec["direction"], [2048], 4)
        chain["replica"] = spec["replica"]
        endpoint = chain["endpoints"][0]
        endpoint["instance_id"] = identity(endpoint["sets"], task, config, spec)
        expected.append(chain)
    compare(record["chains"], expected, "F3 degree-preserving replay, references and witnesses")
    return {"seconds": time.perf_counter() - started, "peak_memory_bytes": memory_usage()}


def validate_batch(output, workers=4):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    report = {"status": "incomplete", "graphs": {}}
    write_json(output / "verification.json", report)
    records = load_records(output, config)
    settings = {key: config[key] for key in ("version", "n", "d", "k")}
    started = time.perf_counter()
    with RuntimeBudget(output, config, "r3_verification") as budget:
        arguments = [(r, t, settings) for r, t in zip(records, config["tasks"])]
        # Results carry their graph ID because completion order is not input order.
        for identifier, timing in computed_results(verify_identified, arguments, workers, budget):
            if timing["peak_memory_bytes"] * (workers + 1) > config["limits"]["memory_bytes"]:
                raise RuntimeError("F3 verification memory budget exceeded")
            report["graphs"][identifier] = timing
            if len(report["graphs"]) % 100 == 0:
                print(f"R3 verified {len(report['graphs'])}/{config['sample_count']}", flush=True)
    report.update(status="passed", graph_count=len(records), endpoints=4 * len(records),
                  wall_seconds=time.perf_counter() - started)
    write_json(output / "verification.json", report)
    return report


def verify_identified(record, task, config):
    return task["base_graph_id"], verify_record(record, task, config)


def verify_summaries(output):
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    write_json(output / "summary_verification.json", {"status": "incomplete"})
    records = load_records(output, config)
    with RuntimeBudget(output, config, "r3_summary_verification") as budget:
        with (output / "base_graph_summary.csv").open(encoding="utf-8", newline="") as handle:
            actual_bases = list(csv.DictReader(handle))
        with (output / "endpoint_results.csv").open(encoding="utf-8", newline="") as handle:
            actual_ends = list(csv.DictReader(handle))
        if len(actual_bases) != len(records) or len(actual_ends) != 4 * len(records):
            raise ValueError("missing or duplicate derived F3 rows")
        expected_bases, expected_ends = [], []
        for record in records:
            budget.check()
            row = {"base_graph_id": record["task"]["base_graph_id"], "repetition": record["task"]["repetition"]}
            for side, label in ((-1, "low"), (1, "high")):
                selected = [c for c in record["chains"] if c["direction"] == side]
                vals = [c["endpoints"][0] for c in selected]
                row[label + "_first_loss"] = sum(int(e["values"]["forced_optimum"] < e["values"]["optimum"]) for e in vals) / 2
                row[label + "_failure"] = sum(int(e["values"]["greedy"] != e["values"]["optimum"]) for e in vals) / 2
                row[label + "_relative_gap"] = sum((1 - e["values"]["greedy"] / e["values"]["optimum"]) / 2 for e in vals)
                row[label + "_exposure"] = sum(e["exposure"] for e in vals) / 2
            row["difference"] = row["high_first_loss"] - row["low_first_loss"]
            expected_bases.append(row)
            for chain in record["chains"]:
                e = chain["endpoints"][0]
                expected_ends.append({"base_graph_id": record["task"]["base_graph_id"], "direction": chain["direction"],
                                      "replica": chain["replica"], "chain_seed": chain["seed"], "instance_id": e["instance_id"],
                                      "exposure": e["exposure"], "greedy": e["values"]["greedy"], "optimum": e["values"]["optimum"],
                                      "forced_optimum": e["values"]["forced_optimum"],
                                      "first_loss": int(e["values"]["forced_optimum"] < e["values"]["optimum"]),
                                      "accepted": e["accepted"], "legal": e["legal"], "proposals": e["proposals"]})
        def compare_csv(actual, expected):
            for got, wanted in zip(actual, expected):
                if set(got) != set(wanted):
                    raise ValueError("F3 derived columns differ")
                for key, value in wanted.items():
                    if type(value) is int:
                        if got[key] != str(value):
                            raise ValueError(f"F3 derived integer differs: {key}")
                    elif isinstance(value, float):
                        if not math.isclose(float(got[key]), value, rel_tol=1e-12, abs_tol=1e-12):
                            raise ValueError(f"F3 derived value differs: {key}")
                    elif got[key] != value:
                        raise ValueError(f"F3 derived identity differs: {key}")
        compare_csv(actual_bases, expected_bases)
        compare_csv(actual_ends, expected_ends)
        n = len(records)
        theta = sum((r["high_first_loss"] - r["low_first_loss"]) for r in expected_bases) / n
        half = math.sqrt(-2 * math.log(config["alpha"] / 2) / n)
        lower, upper = max(-1.0, theta - half), min(1.0, theta + half)
        expected = {"n": n, "endpoints": 4 * n, "delta": theta, "lower": lower, "upper": upper,
                    "half_width": half, "confidence": .95,
                    "direction": "positive" if lower > 0 else "negative" if upper < 0 else "inconclusive",
                    "graphs_without_exposure_separation": sum(r["high_exposure"] <= r["low_exposure"] for r in expected_bases)}
        for key in ("low_first_loss", "high_first_loss", "low_failure", "high_failure",
                    "low_relative_gap", "high_relative_gap", "low_exposure", "high_exposure"):
            expected[key] = math.fsum(r[key] for r in expected_bases) / n
        actual = read_json(output / "primary_summary.json")
        if set(actual) != set(expected):
            raise ValueError("F3 primary summary fields differ")
        for key, value in expected.items():
            if type(value) is int:
                if type(actual[key]) is not int or actual[key] != value:
                    raise ValueError(f"F3 primary integer differs: {key}")
            elif isinstance(value, float):
                if not math.isclose(actual[key], value, rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError(f"F3 primary summary differs: {key}")
            elif actual[key] != value:
                raise ValueError(f"F3 primary summary differs: {key}")
        write_json(output / "summary_verification.json", {"status": "passed", "graphs": n, "endpoints": 4 * n,
                                                          "scope": "derived consistency; not an independent optimum proof"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--summaries-only", action="store_true")
    args = parser.parse_args()
    if args.summaries_only:
        verify_summaries(args.output)
        print("R3 derived summaries verified", flush=True)
    else:
        validate_batch(args.output, args.workers)
        print("R3 original graphs, switches and exact references verified", flush=True)


if __name__ == "__main__":
    main()
