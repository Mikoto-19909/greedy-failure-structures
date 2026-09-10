"""Optional completion acceleration around the unchanged R2 reference verifier.

The frozen verifier checks original tasks, ordered sets, exact budget references
and structure. Its no-diagnostic path is reused on temporary views, after the
original task is compared; the complete planned diagnostic is checked separately
with the independent completion backend. Neither input records nor config files
are modified, and no producer computations are imported.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
import validate_r2_budget_grid as baseline
from r2_design import RuntimeBudget, computed_results, load_records, read_json, validate_design, write_json
from validate_greedy_failure_paths import compare, expected_path
from verification_completion import BACKENDS, get_completion_solver, validate_backend


def verify_graph(record, task, diagnostic_limits, *, completion_backend="python"):
    validate_backend(completion_backend)
    if completion_backend == "python":
        return baseline.verify_graph(record, task, diagnostic_limits)
    started = time.perf_counter()
    get_completion_solver(completion_backend)
    compare(record["task"], task, "task")
    diagnostic_k = task["diagnostic_k"]
    base_task = {**task, "diagnostic_k": None}
    base_record = {**record, "task": base_task, "diagnostic": None}
    baseline.verify_graph(base_record, base_task, diagnostic_limits)
    base_done = time.perf_counter()
    if diagnostic_k is None:
        compare(record["diagnostic"], None, "no unplanned diagnostic")
    else:
        base = {"sets": record["sets"], "k": diagnostic_k, "population": "r2"}
        expected = expected_path(base, diagnostic_limits, completion_backend=completion_backend)
        compare(record["diagnostic"], {k: v for k, v in expected.items() if k not in base},
                "independent prefix/exchange path")
    return {"base_seconds": base_done - started,
            "diagnostic_seconds": time.perf_counter() - base_done,
            "peak_memory_bytes": baseline.memory_usage()}


def verify_saved(path, task, diagnostic_limits, completion_backend="python"):
    return task["base_graph_id"], verify_graph(read_json(path), task, diagnostic_limits,
                                              completion_backend=completion_backend)


def validate_batch(output, *, workers=4, completion_backend="python"):
    validate_backend(completion_backend)
    if completion_backend == "python":
        return baseline.validate_batch(output, workers=workers)
    output = Path(output)
    design = validate_design(read_json(output / "config.json"))
    if design["phase"] == "preflight":
        raise ValueError("F2 preflight verification keeps the original Python cost baseline")
    if type(workers) is not int or not 1 <= workers <= design["limits"]["workers"]:
        raise ValueError("invalid verification worker count")
    started = time.perf_counter()
    report = {"status": "incomplete", "graphs": {}, "wall_seconds": 0.0}
    write_json(output / "verification.json", report)
    load_records(output, design)
    tasks = [(output / "graphs" / (task["base_graph_id"] + ".json"), task,
              design["diagnostics"], completion_backend) for task in design["tasks"]]
    with RuntimeBudget(output, design, "verification") as budget:
        for identifier, timing in computed_results(verify_saved, tasks, workers, budget):
            if timing["peak_memory_bytes"] * (workers + 1) > design["limits"]["memory_bytes"]:
                raise RuntimeError("verification memory budget exceeded")
            report["graphs"][identifier] = timing
            if len(report["graphs"]) % 10 == 0:
                print(f"R2 verified {len(report['graphs'])}/{len(tasks)}", flush=True)
    report.update(status="passed", wall_seconds=time.perf_counter() - started)
    write_json(output / "verification.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--summaries-only", action="store_true")
    parser.add_argument("--verification-backend", choices=BACKENDS, default="python")
    args = parser.parse_args()
    if args.summaries_only:
        if args.verification_backend != "python":
            parser.error("--verification-backend applies to graph verification, not --summaries-only")
        baseline.verify_summaries(args.output)
    else:
        validate_batch(args.output, workers=args.workers, completion_backend=args.verification_backend)
    print("R2 independent verification passed", flush=True)


if __name__ == "__main__":
    main()
