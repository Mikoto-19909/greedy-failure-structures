"""Independent R2 recomputation using Python sets, combinations and weighted statistics.

Shared infrastructure: design parsing, deterministic seeds, instance generation/identity,
and file I/O. No R2 producer, objective sweep or producer statistics are imported.
The existing independent R1 verifier supplies prefix/exchange verification.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import json
from itertools import combinations
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover._generators_random import fixed_size
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_id
from r2_design import validate_design, read_json, write_json, load_records, seed_for
from r2_design import RuntimeBudget, computed_results
from validate_greedy_failure_paths import expected_path, compare
from verification_completion import BACKENDS, validate_backend


def memory_usage():
    if os.name != "nt":
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform == "darwin" else value * 1024
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong), ("values", ctypes.c_size_t * 8)]
    counts = Counters()
    counts.cb = ctypes.sizeof(counts)
    handle = ctypes.windll.kernel32.GetCurrentProcess
    handle.restype = ctypes.c_void_p
    function = ctypes.windll.psapi.GetProcessMemoryInfo
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not function(handle(), ctypes.byref(counts), counts.cb):
        raise OSError("cannot measure verification memory")
    return counts.values[0]


def union(sets, indices):
    result = set()
    for index in indices:
        result.update(sets[index])
    return result


def reference(sets, k):
    best_value, witness = -1, None
    for indices in combinations(range(len(sets)), k):
        value = len(union(sets, indices))
        if value > best_value:
            best_value, witness = value, list(indices)
    return best_value, witness


def greedy_reference(sets, k):
    covered, selected = set(), []
    for _ in range(k):
        gains = [(len(s - covered), -i, i) for i, s in enumerate(sets) if i not in selected]
        chosen = max(gains)[2]
        selected.append(chosen)
        covered.update(sets[chosen])
    return len(covered), sorted(selected)


def structure_reference(sets, n):
    frequencies = [sum(a in s for s in sets) for a in range(n)]
    sizes = [len(s) for s in sets]
    unique = list({frozenset(s) for s in sets})
    intersections = [len(a & b) for a, b in combinations(sets, 2)]
    jaccards = [len(a & b) / len(a | b) for a, b in combinations(sets, 2) if a | b]
    dominated = sum(any(a < b for b in unique) for a in unique)
    incidence = sum(sizes)
    duplicate = len(sets) - len(unique)
    return {"incidence_count": incidence, "covered_element_count": len(set().union(*sets)),
            "actual_density": incidence / (n * len(sets)), "mean_set_size": incidence / len(sets),
            "pairwise_overlap_mean_jaccard": math.fsum(jaccards) / len(jaccards) if jaccards else None,
            "pairwise_overlap_total_pairs": len(intersections), "pairwise_overlap_valid_pairs": len(jaccards),
            "coverage_skew_gini": sum(abs(a - b) for a, b in combinations(frequencies, 2)) / ((n - 1) * incidence) if n > 1 and incidence else 0.0,
            "unique_set_count": len(unique), "duplicate_set_count": duplicate,
            "duplicate_set_ratio": duplicate / len(sets), "dominated_set_count": dominated,
            "dominated_set_ratio": dominated / len(sets), "dominated_unique_ratio": dominated / len(unique),
            "preprocessed_set_count": len(unique) - dominated,
            "element_frequencies": frequencies, "pair_intersections": intersections}


def verify_graph(record, task, diagnostic_limits, *, completion_backend="python"):
    validate_backend(completion_backend)
    started = time.perf_counter()
    if completion_backend != "python":
        from verification_completion import get_completion_solver
        get_completion_solver(completion_backend)
    compare(record["task"], task, "task")
    compare(record["status"], "complete", "status")
    n, d = task["n"], task["d"]
    original = fixed_size(universe_size=n, set_count=n, k=1, set_size=d,
                          unique_sets=False, seed=task["seed"])
    elements = [[a for a in range(n) if mask & (1 << a)] for mask in original.sets]
    compare(record["sets"], elements, "ordered original sets")
    sets = [set(s) for s in record["sets"]]
    compare(record["subset_count"], 2**n, "complete subset sweep")
    compare(record["structure"], structure_reference(sets, n), "structure")
    expected_values = []
    for k in task["budgets"]:
        optimum, witness = reference(sets, k)
        value, chosen = greedy_reference(sets, k)
        if optimum <= 0:
            raise ValueError("R2 optimum must be positive")
        item = MaximumCoverageInstance(n, original.sets, k, original.family, original.seed, original.parameters)
        expected_values.append({"k": k, "instance_id": instance_id(item), "greedy": value,
                                "greedy_selected": chosen, "optimum": optimum,
                                "optimum_selected": witness, "reference_status": "optimal"})
    compare(record["values"], expected_values, "budget results and canonical witnesses")
    base_done = time.perf_counter()
    if task["diagnostic_k"] is None:
        compare(record["diagnostic"], None, "no unplanned diagnostic")
    else:
        base = {"sets": record["sets"], "k": task["diagnostic_k"], "population": "r2"}
        expected = expected_path(base, diagnostic_limits, completion_backend=completion_backend)
        expected = {k: v for k, v in expected.items() if k not in base}
        compare(record["diagnostic"], expected, "independent prefix/exchange path")
    return {"base_seconds": base_done - started, "diagnostic_seconds": time.perf_counter() - base_done,
            "peak_memory_bytes": memory_usage()}


def verify_saved(path, task, diagnostic_limits, completion_backend="python"):
    return task["base_graph_id"], verify_graph(read_json(path), task, diagnostic_limits,
                                             completion_backend=completion_backend)


def validate_batch(output, *, workers=4, completion_backend="python"):
    validate_backend(completion_backend)
    output = Path(output)
    design = validate_design(read_json(output / "config.json"))
    if design["phase"] == "preflight" and completion_backend != "python":
        raise ValueError("F2 preflight verification requires the Python cost baseline")
    if not 1 <= workers <= design["limits"]["workers"]:
        raise ValueError("invalid verification worker count")
    started = time.perf_counter()
    report = {"status": "incomplete", "graphs": {}, "wall_seconds": 0.0}
    write_json(output / "verification.json", report)
    load_records(output, design)
    tasks = [(output / "graphs" / (t["base_graph_id"] + ".json"), t, design["diagnostics"],
              completion_backend) for t in design["tasks"]]
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


def _verify_summaries(output, budget):
    """Recompute saved summaries independently; weighted bootstrap preserves whole graphs."""
    import numpy as np
    from scipy.stats import binomtest
    output = Path(output)
    design = validate_design(read_json(output / "config.json"))
    write_json(output / "summary_verification.json", {"status": "incomplete"})
    records = load_records(output, design)
    with (output / "cell_summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    wanted = {(n, d, k) for r in records for n, d in [(r["task"]["n"], r["task"]["d"])] for k in r["task"]["budgets"]}
    if len(rows) != len(wanted) or {(int(r["n"]), int(r["d"]), int(r["k"])) for r in rows} != wanted:
        raise ValueError("missing or duplicate summary cells")
    for n in design["n_values"]:
        for d in design["d_values"]:
            budget.check()
            group = [r for r in records if (r["task"]["n"], r["task"]["d"]) == (n, d)]
            count = len(group)
            generator = np.random.default_rng(seed_for(design["phase"], n, d, 0, "bootstrap"))
            draws = generator.integers(0, count, size=(10000, count))
            weights = np.array([np.bincount(draw, minlength=count) for draw in draws])
            for j, k in enumerate(group[0]["task"]["budgets"]):
                g = np.array([r["values"][j]["greedy"] for r in group])
                o = np.array([r["values"][j]["optimum"] for r in group])
                failures = sum(int(a < b) for a, b in zip(g, o))
                interval = binomtest(failures, count).proportion_ci(.95, method="exact")
                expected = {"n": n, "d": d, "k": k, "lambda": k * d / n, "count": count,
                            "failures": failures, "failure_rate": failures / count,
                            "failure_lower": interval.low, "failure_upper": interval.high,
                            "mean_greedy": sum(g) / count, "mean_optimum": sum(o) / count}
                metrics = {"ratio_of_means": (sum(g) / sum(o), (weights @ g) / (weights @ o)),
                           "mean_ratio": (math.fsum(g / o) / count, (weights @ (g / o)) / count),
                           "mean_relative_gap": (math.fsum(1 - g / o) / count, (weights @ (1 - g / o)) / count),
                           "mean_absolute_loss": (sum(o - g) / count, (weights @ (o - g)) / count)}
                for name, (value, distribution) in metrics.items():
                    expected[name] = value
                    expected[name + "_lower"], expected[name + "_upper"] = np.quantile(distribution, [.025, .975])
                actual = next(r for r in rows if (int(r["n"]), int(r["d"]), int(r["k"])) == (n, d, k))
                if set(actual) != set(expected) or any(not math.isclose(float(actual[key]), float(value), rel_tol=1e-11, abs_tol=1e-12) for key, value in expected.items()):
                    raise ValueError(f"summary calculation differs at {(n, d, k)}")
    with (output / "budget_results.csv").open(encoding="utf-8", newline="") as handle:
        budget_rows = list(csv.DictReader(handle))
    expected_rows = [{"base_graph_id": r["task"]["base_graph_id"], "n": r["task"]["n"], "d": r["task"]["d"],
                      "repetition": r["task"]["repetition"], "k": v["k"], "instance_id": v["instance_id"],
                      "greedy": v["greedy"], "optimum": v["optimum"], "relative_gap": (v["optimum"] - v["greedy"]) / v["optimum"]}
                     for r in records for v in r["values"]]
    if budget_rows != [{k: str(v) for k, v in row.items()} for row in expected_rows]:
        raise ValueError("budget_results.csv differs from saved graph records")
    with (output / "mechanism_summary.csv").open(encoding="utf-8", newline="") as handle:
        mechanisms = list(csv.DictReader(handle))
    expected_keys = {(r["task"]["n"], r["task"]["d"], r["task"]["diagnostic_k"])
                     for r in records if r["diagnostic"] is not None}
    if len(mechanisms) != len(expected_keys) or {(int(r["n"]), int(r["d"]), int(r["k"])) for r in mechanisms} != expected_keys:
        raise ValueError("mechanism summary has missing or duplicate cells")
    for actual in mechanisms:
        n, d, k = (int(actual[key]) for key in ("n", "d", "k"))
        paths = [r["diagnostic"] for r in records if (r["task"]["n"], r["task"]["d"], r["task"]["diagnostic_k"]) == (n, d, k)]
        count = len(paths)
        expected = {"n": n, "d": d, "k": k, "count": count, "failures": 0, "tie_avoidable": 0,
                    "one_step_limit": 0, "one_swap_repaired": 0, "two_swap_repaired": 0,
                    "two_swap_incomplete": 0, "mean_greedy_relative_gap": 0.0,
                    "mean_one_swap_relative_gap": 0.0, "mean_two_swap_relative_gap": 0.0}
        first = [0] * k
        for path in paths:
            optimum = path["optimum"]
            failure = path["prefixes"][-1]["coverage"] < optimum
            expected["failures"] += failure
            expected["tie_avoidable"] += path["mechanism"] == "tie_avoidable"
            expected["one_step_limit"] += path["mechanism"] == "one_step_limit"
            expected["one_swap_repaired"] += failure and path["one_swap"]["coverage"] == optimum
            expected["two_swap_repaired"] += failure and path["two_swap"]["coverage"] == optimum
            expected["two_swap_incomplete"] += path["two_swap"]["status"] != "local_optimum"
            for name, value in (("greedy", path["prefixes"][-1]["coverage"]), ("one_swap", path["one_swap"]["coverage"]), ("two_swap", path["two_swap"]["coverage"])):
                expected[f"mean_{name}_relative_gap"] += (optimum - value) / optimum / count
            if path["first_failure_step"] is not None:
                first[path["first_failure_step"] - 1] += 1
        if (set(actual) != set(expected) | {"first_failure_counts"}
                or json.loads(actual["first_failure_counts"]) != first
                or any(not math.isclose(float(actual[key]), value, rel_tol=1e-11, abs_tol=1e-12) for key, value in expected.items())):
            raise ValueError("mechanism summary differs from complete diagnostics")
    write_json(output / "summary_verification.json", {"status": "passed", "cells": len(rows), "budget_rows": len(budget_rows), "mechanism_cells": len(mechanisms)})


def verify_summaries(output):
    design = validate_design(read_json(Path(output) / "config.json"))
    with RuntimeBudget(output, design, "summary_verification") as budget:
        _verify_summaries(output, budget)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--summaries-only", action="store_true")
    parser.add_argument("--verification-backend", choices=BACKENDS, default="python",
                        help="Prefix completion verifier: python (default), auto with fallback, or required numba")
    args = parser.parse_args()
    if args.summaries_only:
        if args.verification_backend != "python":
            parser.error("--verification-backend applies to graph verification, not --summaries-only")
        verify_summaries(args.output)
        print("R2 summary verification passed", flush=True)
    else:
        validate_batch(args.output, workers=args.workers, completion_backend=args.verification_backend)
        print("R2 independent graph verification passed", flush=True)


if __name__ == "__main__":
    main()
