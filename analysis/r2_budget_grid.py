"""Offline R2 budget grid: preflight/run, F2 selection, and saved-data analysis."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from functools import partial
import csv
import ctypes
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover._generators_random import fixed_size
from maxcover.algorithms import greedy
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_id
from maxcover.structure import analyze_instance as structure_metrics
from greedy_failure_paths import analyze_instance as diagnose
from r2_design import (make_design, validate_design, seed_for, read_json, write_json, load_records)
from r2_design import RuntimeBudget, computed_results


def peak_memory():
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in
                ("peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess
        handle.restype = ctypes.c_void_p
        read = ctypes.windll.psapi.GetProcessMemoryInfo
        read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if not read(handle(), ctypes.byref(counters), counters.cb):
            raise OSError("cannot measure process memory")
        return counters.peak
    import resource
    size = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return size if sys.platform == "darwin" else size * 1024


def all_budget_optima(sets):
    """Visit every subset once; choose the smallest ascending witness at each size."""
    m = len(sets)
    best = [-1] * (m + 1)
    witnesses = [None] * (m + 1)
    selected = []
    visited = 0

    def visit(start, mask):
        nonlocal visited
        visited += 1
        k, value = len(selected), mask.bit_count()
        witness = tuple(selected)
        if value > best[k] or (value == best[k] and witness < witnesses[k]):
            best[k], witnesses[k] = value, witness
        for index in range(start, m):
            selected.append(index)
            visit(index + 1, mask | sets[index])
            selected.pop()

    visit(0, 0)
    return best, witnesses, visited


def evaluate_task(task, diagnostic_limits, *, production_backend="python"):
    record, _ = _evaluate_task(task, diagnostic_limits, production_backend)
    return record


def _evaluate_task(task, diagnostic_limits, production_backend):
    started = time.perf_counter()
    instance = fixed_size(universe_size=task["n"], set_count=task["n"], k=1,
                          set_size=task["d"], unique_sets=False, seed=task["seed"])
    generated = time.perf_counter()
    event = None
    if production_backend == "python":
        best, witnesses, visited = all_budget_optima(instance.sets)
    else:
        from r2_production_backends import solve_optima
        (best, witnesses, visited), event = solve_optima(instance.sets, production_backend, all_budget_optima)
    enumerated = time.perf_counter()
    values = []
    for k in task["budgets"]:
        item = MaximumCoverageInstance(instance.universe_size, instance.sets, k,
                                       instance.family, instance.seed, instance.parameters)
        solution = greedy(item)
        values.append({"k": k, "instance_id": instance_id(item), "greedy": solution.coverage,
                       "greedy_selected": list(solution.selected), "optimum": best[k],
                       "optimum_selected": list(witnesses[k]), "reference_status": "optimal"})
    base_done = time.perf_counter()
    diagnostic = None
    if task["diagnostic_k"] is not None:
        item = MaximumCoverageInstance(instance.universe_size, instance.sets, task["diagnostic_k"],
                                       instance.family, instance.seed, instance.parameters)
        diagnostic = diagnose(item, **diagnostic_limits)
    diagnosed = time.perf_counter()
    elements = [[a for a in range(instance.universe_size) if mask & (1 << a)] for mask in instance.sets]
    structure = asdict(structure_metrics(instance))
    structure["element_frequencies"] = [sum(a in s for s in elements) for a in range(task["n"])]
    structure["pair_intersections"] = [(left & right).bit_count() for i, left in enumerate(instance.sets)
                                        for right in instance.sets[i + 1:]]
    record = {"task": task, "status": "complete", "sets": elements, "values": values,
            "subset_count": visited, "structure": structure, "diagnostic": diagnostic,
            "timing": {"generation_seconds": generated - started,
                       "enumeration_seconds": enumerated - generated,
                       "base_seconds": base_done - started,
                       "diagnostic_seconds": diagnosed - base_done,
                       "total_seconds": time.perf_counter() - started,
                       "peak_memory_bytes": peak_memory()}}
    return record, event


def _evaluate_accelerated(task, diagnostic_limits, production_backend):
    started = time.perf_counter()
    try:
        record, event = _evaluate_task(task, diagnostic_limits, production_backend)
        return record, {**event, "status": "complete", "graph_id": task["base_graph_id"],
                        "enumeration_seconds": record["timing"]["enumeration_seconds"],
                        "wall_seconds": time.perf_counter() - started}
    except Exception as error:
        # Serialize errors instead of trying to pickle CUDA exception/context objects.
        # The parent records this failure and aborts, never converts it to CPU success.
        return None, {"requested_backend": production_backend, "actual_backend": None,
                      "status": "failed", "graph_id": task["base_graph_id"],
                      "error_type": type(error).__name__, "error": str(error),
                      "wall_seconds": time.perf_counter() - started}


def run(design, output, *, workers=4, resume=False, stop_after=None,
        production_backend="python", cuda_cache_dir=None):
    from r2_production_backends import validate_backend
    validate_backend(production_backend)
    validate_design(design)
    if design["phase"] == "preflight" and production_backend != "python":
        raise ValueError("accelerated production is not supported for F2 preflight")
    if cuda_cache_dir is not None and production_backend != "cuda":
        raise ValueError("cuda_cache_dir requires CUDA production")
    if type(workers) is not int or not 1 <= workers <= design["limits"]["workers"]:
        raise ValueError("workers must be between 1 and the configured maximum")
    output = Path(output)
    if output.exists() and not resume:
        raise ValueError("output already exists; use resume with the same design")
    if output.exists() and read_json(output / "config.json") != design:
        raise ValueError("resume design differs from saved configuration")
    completed = load_records(output, design, partial=True)
    done = {r["task"]["base_graph_id"] for r in completed}
    pending = [t for t in design["tasks"] if t["base_graph_id"] not in done]
    if stop_after is not None:
        pending = pending[:stop_after]
    if pending and production_backend == "cuda":
        if workers != 1:
            raise ValueError("CUDA production v1 requires workers=1 (one isolated GPU owner)")
        cuda_cache_dir = Path(cuda_cache_dir or output / ".cuda").resolve()
        if not str(cuda_cache_dir).isascii():
            raise ValueError("CUDA requires an ASCII --cuda-cache-dir")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "config.json", design)
    started = time.perf_counter()
    size = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())

    def save(record):
        nonlocal size
        if record["timing"]["peak_memory_bytes"] * (workers + 1) > design["limits"]["memory_bytes"]:
            raise RuntimeError("memory budget exceeded; keep completed inputs, do not replace samples")
        path = output / "graphs" / (record["task"]["base_graph_id"] + ".json")
        write_json(path, record)
        size += path.stat().st_size
        if size > design["limits"]["output_bytes"] or time.perf_counter() - started > design["limits"]["wall_seconds"]:
            raise RuntimeError("run resource budget exceeded; checkpoints preserved")
        done.add(record["task"]["base_graph_id"])
        if len(done) % 10 == 0 or len(done) == len(design["tasks"]):
            print(f"R2 computed {len(done)}/{len(design['tasks'])}", flush=True)

    def backend_event(event):
        with (output / "production_backend.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    if pending:
        write_json(output / "run_status.json", {"computed": 0, "reused": len(completed), "complete": False,
                                                "wall_seconds": 0.0, "workers": workers})
    with RuntimeBudget(output, design, "production") as budget:
        if production_backend == "python":
            for record in computed_results(evaluate_task, [(t, design["diagnostics"]) for t in pending], workers, budget):
                save(record)
        elif pending:
            backend_event({"status": "started", "requested_backend": production_backend,
                           "pending": len(pending), "reused": len(completed), "workers": workers})
            arguments = [(t, design["diagnostics"], production_backend) for t in pending]
            try:
                if production_backend == "cuda":
                    from r2_cuda_backend import computed_cuda_results
                    results = computed_cuda_results(_evaluate_accelerated, arguments, budget, cuda_cache_dir)
                else:
                    results = computed_results(_evaluate_accelerated, arguments, workers, budget)
                try:
                    for record, event in results:
                        if record is None:
                            backend_event(event)
                            raise RuntimeError(f"{production_backend} production failed for {event['graph_id']}: "
                                               f"{event['error_type']}: {event['error']}")
                        save(record)
                        backend_event(event)
                finally:
                    results.close()
            except Exception as error:
                backend_event({"status": "failed", "requested_backend": production_backend,
                               "error_type": type(error).__name__, "error": str(error),
                               "wall_seconds": time.perf_counter() - started})
                raise
    entry = {"computed": len(pending), "reused": len(completed), "complete": len(done) == len(design["tasks"]),
             "wall_seconds": time.perf_counter() - started, "workers": workers}
    write_json(output / "run_status.json", entry)
    return entry


def f2_from_preflight(output):
    output = Path(output)
    design = validate_design(read_json(output / "config.json"))
    if design["phase"] != "preflight" or design["n_values"] != [12, 16, 20] or design["d_values"] != [2, 3, 4] or design["repetitions"] != 8 or design["diagnostic_count"] != 8:
        raise ValueError("F2 selection requires the complete approved 72-graph preflight")
    records = load_records(output, design)
    verification = read_json(output / "verification.json")
    if verification["status"] != "passed" or set(verification["graphs"]) != {r["task"]["base_graph_id"] for r in records}:
        raise ValueError("independent preflight verification is incomplete")
    estimates = []
    for ns in ((12, 16, 20), (12, 16)):
        work = 0.0
        bytes_estimate = 0
        peak = 0
        for n in ns:
            for d in (2, 3, 4):
                rows = [r for r in records if (r["task"]["n"], r["task"]["d"]) == (n, d)]
                checks = [verification["graphs"][r["task"]["base_graph_id"]] for r in rows]
                work += 200 * max(r["timing"]["base_seconds"] + c["base_seconds"] for r, c in zip(rows, checks))
                work += 32 * max(r["timing"]["diagnostic_seconds"] + c["diagnostic_seconds"] for r, c in zip(rows, checks))
                peak = max(peak, *(r["timing"]["peak_memory_bytes"] for r in rows), *(c["peak_memory_bytes"] for c in checks))
                bytes_estimate += 200 * max((output / "graphs" / (r["task"]["base_graph_id"] + ".json")).stat().st_size for r in rows)
        workers = min(4, max(0, design["limits"]["memory_bytes"] // max(1, peak) - 1))
        preflight_wall = sum(json.loads(line)["wall_seconds"] for line in (output / "execution.jsonl").read_text(encoding="utf-8").splitlines())
        estimate = {"n_values": list(ns), "workers": workers,
                    "conservative_wall_seconds": 2 * work / max(1, workers) + preflight_wall + 600,
                    "conservative_output_bytes": 2 * bytes_estimate,
                    "peak_process_bytes": peak, "safety_factor": 2, "analysis_allowance_seconds": 600}
        estimates.append(estimate)
        if workers and estimate["conservative_wall_seconds"] <= 43200 and 2 * bytes_estimate <= 2 * 1024**3:
            chosen = make_design("exploration", ns)
            chosen["limits"]["workers"] = workers
            chosen["f2_resource_decision"] = {"preflight": str(output.resolve()), "preflight_wall_seconds": preflight_wall, "estimates": estimates}
            return chosen
    raise RuntimeError(f"Neither approved grid fits the budget: {estimates}")


def summarize(records, design):
    import numpy as np
    from scipy.stats import beta
    rows = []
    for n in design["n_values"]:
        for d in design["d_values"]:
            group = [r for r in records if (r["task"]["n"], r["task"]["d"]) == (n, d)]
            g = np.array([[v["greedy"] for v in r["values"]] for r in group], dtype=float)
            o = np.array([[v["optimum"] for v in r["values"]] for r in group], dtype=float)
            if np.any(o <= 0):
                raise ValueError("relative metrics require positive exact optima")
            samples = np.random.default_rng(seed_for(design["phase"], n, d, 0, "bootstrap")).integers(
                0, len(group), size=(design["statistics"]["bootstrap_repetitions"], len(group)))
            # The same row draws are used for every budget and every metric.
            for j, k in enumerate(group[0]["task"]["budgets"]):
                a, b = g[:, j], o[:, j]
                aa, bb = a[samples], b[samples]
                metrics = {"ratio_of_means": (a.sum() / b.sum(), aa.sum(axis=1) / bb.sum(axis=1)),
                           "mean_ratio": ((a / b).mean(), (aa / bb).mean(axis=1)),
                           "mean_relative_gap": (((b - a) / b).mean(), ((bb - aa) / bb).mean(axis=1)),
                           "mean_absolute_loss": ((b - a).mean(), (bb - aa).mean(axis=1))}
                failed = int((a < b).sum())
                count = len(group)
                row = {"n": n, "d": d, "k": k, "lambda": k * d / n, "count": count,
                       "failures": failed, "failure_rate": failed / count,
                       "failure_lower": 0.0 if failed == 0 else float(beta.ppf(.025, failed, count - failed + 1)),
                       "failure_upper": 1.0 if failed == count else float(beta.ppf(.975, failed + 1, count - failed)),
                       "mean_greedy": float(a.mean()), "mean_optimum": float(b.mean())}
                for key, (value, distribution) in metrics.items():
                    lo, hi = np.quantile(distribution, [.025, .975])
                    row.update({key: float(value), key + "_lower": float(lo), key + "_upper": float(hi)})
                rows.append(row)
    return rows


DIAGNOSTIC_FIELDS = ("n", "d", "k", "count", "failures", "tie_avoidable", "one_step_limit",
                     "one_swap_repaired", "two_swap_repaired", "two_swap_incomplete",
                     "mean_greedy_relative_gap", "mean_one_swap_relative_gap", "mean_two_swap_relative_gap",
                     "first_failure_counts")


def mechanism_summary(records):
    keys = sorted({(r["task"]["n"], r["task"]["d"], r["task"]["diagnostic_k"])
                   for r in records if r["diagnostic"] is not None})
    result = []
    for n, d, k in keys:
        paths = [r["diagnostic"] for r in records if (r["task"]["n"], r["task"]["d"], r["task"]["diagnostic_k"]) == (n, d, k)]
        failed = [v for v in paths if v["mechanism"] != "optimal"]
        result.append({"n": n, "d": d, "k": k, "count": len(paths), "failures": len(failed),
                       "tie_avoidable": sum(v["mechanism"] == "tie_avoidable" for v in paths),
                       "one_step_limit": sum(v["mechanism"] == "one_step_limit" for v in paths),
                       "one_swap_repaired": sum(v["one_swap"]["coverage"] == v["optimum"] for v in failed),
                       "two_swap_repaired": sum(v["two_swap"]["coverage"] == v["optimum"] for v in failed),
                       "two_swap_incomplete": sum(v["two_swap"]["status"] != "local_optimum" for v in paths),
                       "mean_greedy_relative_gap": math.fsum((v["optimum"] - v["prefixes"][-1]["coverage"]) / v["optimum"] for v in paths) / len(paths),
                       "mean_one_swap_relative_gap": math.fsum((v["optimum"] - v["one_swap"]["coverage"]) / v["optimum"] for v in paths) / len(paths),
                       "mean_two_swap_relative_gap": math.fsum((v["optimum"] - v["two_swap"]["coverage"]) / v["optimum"] for v in paths) / len(paths),
                       "first_failure_counts": json.dumps([sum(v["first_failure_step"] == t for v in paths) for t in range(1, k + 1)])})
    return result


def _analyze(output, budget, plot, completion_backend="python", verification_workers=None):
    output = Path(output)
    design = validate_design(read_json(output / "config.json"))
    records = load_records(output, design)
    # A saved pass is historical. Validate exactly the records summarized below.
    if completion_backend == "python":
        from validate_r2_budget_grid import verify_graph
    else:
        from validate_r2_budget_grid_fast import verify_graph
    workers = design["limits"]["workers"] if verification_workers is None else verification_workers
    if type(workers) is not int or not 1 <= workers <= design["limits"]["workers"]:
        raise ValueError("invalid verification worker count")
    arguments = [(record, task, design["diagnostics"]) for record, task in zip(records, design["tasks"])]
    verify = verify_graph if completion_backend == "python" else partial(verify_graph, completion_backend=completion_backend)
    for timing in computed_results(verify, arguments, workers, budget):
        if timing["peak_memory_bytes"] * (workers + 1) > design["limits"]["memory_bytes"]:
            raise RuntimeError("analysis verification memory budget exceeded")
    rows = summarize(records, design)
    budget.check()
    with (output / "cell_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    budget_rows = [{"base_graph_id": r["task"]["base_graph_id"], "n": r["task"]["n"], "d": r["task"]["d"],
                    "repetition": r["task"]["repetition"], "k": v["k"], "instance_id": v["instance_id"],
                    "greedy": v["greedy"], "optimum": v["optimum"], "relative_gap": (v["optimum"] - v["greedy"]) / v["optimum"]}
                   for r in records for v in r["values"]]
    with (output / "budget_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(budget_rows[0]))
        writer.writeheader()
        writer.writerows(budget_rows)
    with (output / "mechanism_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DIAGNOSTIC_FIELDS)
        writer.writeheader()
        writer.writerows(mechanism_summary(records))
    if not plot:
        return rows
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for n in design["n_values"]:
        for d in design["d_values"]:
            selected = [r for r in rows if (r["n"], r["d"]) == (n, d)]
            for ax, metric in zip(axes, ("failure_rate", "mean_relative_gap")):
                ax.plot([r["lambda"] for r in selected], [r[metric] for r in selected], marker=".", label=f"N={n}, d={d}")
    for ax, label in zip(axes, ("Greedy failure rate", "Mean relative optimality gap")):
        ax.set(xlabel="lambda = kd/N", ylabel=label)
        ax.grid(alpha=.2)
    axes[1].legend(fontsize=8)
    fig.savefig(output / "budget_curves.svg")
    plt.close(fig)
    return rows


def analyze(output, *, plot=True, completion_backend="python", verification_workers=None):
    from verification_completion import validate_backend
    validate_backend(completion_backend)
    design = validate_design(read_json(Path(output) / "config.json"))
    if design["phase"] == "preflight" and completion_backend != "python":
        raise ValueError("F2 preflight analysis keeps the original Python cost baseline")
    with RuntimeBudget(output, design, "analysis") as budget:
        return _analyze(output, budget, plot, completion_backend, verification_workers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "freeze", "run", "analyze"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--production-backend", choices=("python", "numba", "cuda", "auto"), default="python")
    parser.add_argument("--cuda-cache-dir", type=Path, help="CUDA only: ASCII compiler temporary/cache directory")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-plot", action="store_true", help="Rebuild validated tables without the optional plotting dependency")
    parser.add_argument("--verification-backend", choices=("python", "auto", "numba"), default="python",
                        help="analyze only: prefix completion verifier")
    parser.add_argument("--verification-workers", type=int,
                        help="analyze only: verification processes, up to the saved design limit")
    args = parser.parse_args()
    if args.command != "run" and (args.production_backend != "python" or args.cuda_cache_dir is not None):
        parser.error("production backend options apply only to run")
    if args.command != "analyze" and (args.verification_backend != "python" or args.verification_workers is not None):
        parser.error("verification options apply only to analyze")
    if args.command == "freeze":
        if args.output.exists():
            raise ValueError("F2 output already exists")
        write_json(args.output, f2_from_preflight(args.preflight))
    elif args.command == "analyze":
        analyze(args.output, plot=not args.no_plot, completion_backend=args.verification_backend,
                verification_workers=args.verification_workers)
    else:
        design = (make_design("preflight", repetitions=8, diagnostic_count=8)
                  if args.command == "preflight" else read_json(args.config))
        run(design, args.output, workers=args.workers, resume=args.resume,
            production_backend=args.production_backend, cuda_cache_dir=args.cuda_cache_dir)


if __name__ == "__main__":
    main()
