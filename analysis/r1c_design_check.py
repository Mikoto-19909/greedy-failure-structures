"""Reproduce R1c design arithmetic; only --preflight-output runs nonformal seeds."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]

from maxcover.benchmark_planning import _case_seed, _instances_for_config
from maxcover.config import load_config

FORMAL = ROOT / "analysis/r1c_confirmation_config.json"
PREFLIGHT = ROOT / "analysis/r1c_preflight_config.json"
PILOT = ROOT / "experiments/core_rq/overlap_pilot_v1/config.json"
BUDGETS = {"max_completions": 200000, "max_two_swap_evaluations": 100000}


def exact_interval(successes: int, trials: int, confidence: float = 0.975) -> tuple[float, float]:
    from scipy.stats import binomtest

    if type(trials) is not int or trials < 0 or type(successes) is not int or not 0 <= successes <= trials:
        raise ValueError("require integer counts with 0 <= successes <= trials")
    if not 0 < confidence < 1:
        raise ValueError("confidence must lie strictly between zero and one")
    if trials == 0:
        return 0.0, 1.0
    interval = binomtest(successes, trials).proportion_ci(confidence, method="exact")
    return float(interval.low), float(interval.high)


def design_arithmetic() -> dict:
    import numpy as np
    import scipy
    from scipy.stats import beta, binom

    configs = {name: load_config(path) for name, path in
               (("formal", FORMAL), ("preflight", PREFLIGHT), ("pilot", PILOT))}
    # Derive seeds without constructing any formal instances or running solvers.
    seeds = {}
    for name, config in configs.items():
        group = [[_case_seed(config, case, index, r) for r in range(config.repetitions)]
                 for index, case in enumerate(config.cases)]
        if len(group) != 2 or group[0] != group[1] or len(set(group[0])) != config.repetitions:
            raise ValueError(f"{name}: expected unique paired seeds")
        seeds[name] = set(group[0])
    if any(seeds[a] & seeds[b] for a, b in (("formal", "pilot"), ("formal", "preflight"), ("pilot", "preflight"))):
        raise ValueError("seed batches must be disjoint")
    n = configs["formal"].repetitions
    widths = []
    for failures in (100, 200, 400, 600, 800, 1000):
        x = np.arange(failures + 1)
        lower = np.zeros(failures + 1)
        upper = np.ones(failures + 1)
        lower[1:] = beta.ppf(0.0125, x[1:], failures - x[1:] + 1)
        upper[:-1] = beta.ppf(0.9875, x[:-1] + 1, failures - x[:-1])
        widths.append({"failures_per_group": failures,
                       "max_group_interval_width": float(np.max(upper - lower)),
                       "max_difference_interval_width_if_equal_denominators": float(2 * np.max(upper - lower))})
    return {"scipy_version": scipy.__version__, "pairs": n, "instances": 2 * n,
            "benchmark_runs": 4 * n,
            "seed_ranges": {name: [min(values), max(values)] for name, values in seeds.items()},
            "seed_batches_disjoint": True, "widths": widths,
            "planning_probability_either_group_below_600_failures_upper_bound":
                min(1.0, float(2 * binom.cdf(599, n, 0.25))),
            "completions_per_instance": math.comb(16, 4),
            "neighbors_per_two_swap_scan": 4 * 12 + math.comb(4, 2) * math.comb(12, 2),
            "worst_case_two_swap_evaluations": 49 * (4 * 12 + math.comb(4, 2) * math.comb(12, 2))}


def preflight(output: Path) -> dict:
    from greedy_failure_paths import analyze_instance
    from validate_greedy_failure_paths import compare, expected_path

    if output.exists():
        raise ValueError("preflight output must not exist; use a new directory")
    output.mkdir(parents=True)
    measurements = {}
    commands = {
        "benchmark": [sys.executable, "-B", str(ROOT / "run_project.py"), "benchmark",
                      "--config", str(PREFLIGHT), "--output", str(output / "benchmark"), "--workers", "1"],
        "benchmark_validation": [sys.executable, "-B", str(ROOT / ".github/scripts/validate_benchmark_output.py"),
                                 "--config", str(PREFLIGHT), "--output", str(output / "benchmark")],
    }
    for phase, command in commands.items():
        start = time.perf_counter()
        with (output / f"{phase}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        measurements[f"{phase}_seconds"] = time.perf_counter() - start
    entries = _instances_for_config(load_config(PREFLIGHT))
    paths = []
    start = time.perf_counter()
    for entry in entries:
        instance = entry.instance
        base = {"population": "resource_preflight", "instance_id": entry.instance_id,
                "case_id": entry.case_id, "repetition": entry.repetition, "seed": instance.seed,
                "k": instance.k, "sets": [[e for e in range(instance.universe_size) if mask & (1 << e)]
                                          for mask in instance.sets]}
        paths.append({**base, **analyze_instance(instance, **BUDGETS)})
    measurements["r1_analysis_seconds"] = time.perf_counter() - start
    start = time.perf_counter()
    base_fields = ("population", "instance_id", "case_id", "repetition", "seed", "k", "sets")
    for path in paths:
        base = {field: path[field] for field in base_fields}
        compare(path, expected_path(base, BUDGETS), "preflight path")
    measurements["r1_independent_validation_seconds"] = time.perf_counter() - start
    (output / "paths.jsonl").write_text("".join(json.dumps(path) + "\n" for path in paths), encoding="utf-8")
    measurements.update(instances=len(paths),
                        output_bytes=sum(path.stat().st_size for path in output.rglob("*") if path.is_file()),
                        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    (output / "timings.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    return measurements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-output", type=Path)
    args = parser.parse_args()
    result = design_arithmetic()
    if args.preflight_output is not None:
        result["preflight"] = preflight(args.preflight_output.resolve())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
