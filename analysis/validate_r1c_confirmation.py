"""Recompute R1c sources, trajectories and statistics independently of their producer."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]

from maxcover.benchmark_planning import _instance_record, _instances_for_config, _validate_run_identity
from maxcover.config import load_config
from maxcover.contracts import InstanceRecord, RunRecord
from maxcover.model import SolutionStatus
from maxcover.reproducibility import config_hash
from validate_greedy_failure_paths import compare, coverage, csv_rows, expected_path, instance_summary, require

PROFILES = {
    "9cb778eb27d01e6883ef2fc0c0f119288af0eedaefc514eb442d347858898545": "confirmation",
    "ef640ca30daff5de91060da965413dd1f5ff42022bf3e9b574dad1926d64cdb9": "resource_preflight",
}
BUDGETS = {"max_completions": 200000, "max_two_swap_evaluations": 100000}
INSTANCE_FIELDS = (
    "population", "config_hash", "pair_id", "case_id", "repetition", "seed", "instance_id",
    "greedy_run_id", "exact_run_id", "F", "A", "greedy", "optimal", "first_failure_step",
    "mechanism", "one_swap", "two_swap", "one_swap_moves", "two_swap_moves",
    "one_swap_evaluations", "two_swap_evaluations", "two_swap_status",
    "greedy_gap", "one_swap_gap", "two_swap_gap", "missing_reason",
)
GROUP_FIELDS = (
    "population", "config_hash", "case_id", "N", "M", "X", "theta", "theta_lower", "theta_upper",
    "theta_status", "failure_rate", "tie_avoidable_rate", "first_loss_1", "first_loss_2",
    "first_loss_3", "first_loss_4", "one_swap_recovered", "two_swap_recovered",
    "one_swap_recovery_rate", "two_swap_recovery_rate", "one_swap_stalls", "two_swap_stalls",
    "gap_defined_n", "zero_optimum_n", "mean_greedy_gap", "mean_one_swap_gap", "mean_two_swap_gap",
)
PRIMARY_FIELDS = (
    "population", "config_hash", "pairs", "instances", "delta", "lower", "upper", "width",
    "target_width", "precision_met", "estimate_status", "direction",
)


def inputs(config_path, source):
    config = load_config(config_path)
    identity = config_hash(config)
    require(identity in PROFILES, "not a frozen R1c configuration")
    planned = _instances_for_config(config)
    records = [InstanceRecord.from_csv_row(row) for row in csv_rows(source / "instances.csv", InstanceRecord.CSV_FIELDS)]
    expected = {item.instance_id: item for item in planned}
    require(len(records) == len(expected) == len({row.instance_id for row in records}), "incorrect instance population")
    for record in records:
        require(record.instance_id in expected, "unplanned instance")
        compare(record.to_csv_row(), _instance_record(expected[record.instance_id], identity).to_csv_row(), "source instance")
    runs = [RunRecord.from_csv_row(row) for row in csv_rows(source / "raw_results.csv", RunRecord.CSV_FIELDS)]
    tasks = _validate_run_identity(config, identity, runs, planned_instances=planned)
    by_instance = {}
    for row in runs:
        instance = tasks[row.run_id].instance
        sets = [{e for e in range(instance.universe_size) if mask & (1 << e)} for mask in instance.sets]
        require(len(row.selected) <= instance.k and len(set(row.selected)) == len(row.selected)
                and all(0 <= index < len(sets) for index in row.selected), "infeasible source selection")
        require(coverage(sets, row.selected) == row.coverage, "source selected coverage differs")
        require(row.status in {SolutionStatus.FEASIBLE, SolutionStatus.OPTIMAL}
                and json.loads(row.algorithm_metadata)["termination"] == "completed"
                and not row.error_message, "source algorithm did not complete")
        by_instance[(row.instance_id, row.algorithm_id)] = row
    bases = []
    for item in planned:
        instance = item.instance
        g = by_instance[(item.instance_id, "greedy")]
        exact = by_instance[(item.instance_id, "exact_reference")]
        require(exact.status is SolutionStatus.OPTIMAL and exact.coverage is not None, "reference is not proven optimal")
        require(g.optimum == exact.optimum == exact.coverage and g.coverage <= exact.coverage, "source optima differ")
        for row in (g, exact):
            require(row.status is not SolutionStatus.OPTIMAL or row.coverage == exact.coverage,
                    "source optimal status contradicts reference")
            require(row.best_bound is None or row.best_bound >= exact.coverage,
                    "source upper bound is below reference")
            gap = (exact.coverage - row.coverage) / exact.coverage if exact.coverage else None
            require(row.optimality_gap == gap or (gap is not None and row.optimality_gap is not None
                    and math.isclose(gap, row.optimality_gap, abs_tol=1e-10)), "source gap differs")
        bases.append({"population": PROFILES[identity], "config_hash": identity,
                      "pair_id": f"{identity}:{item.repetition}", "case_id": item.case_id,
                      "repetition": item.repetition, "seed": instance.seed, "instance_id": item.instance_id,
                      "greedy_run_id": g.run_id, "exact_run_id": exact.run_id,
                      "source_greedy_selected": list(g.selected), "source_optimum": exact.coverage,
                      "universe_size": instance.universe_size, "k": instance.k,
                      "sets": [[e for e in range(instance.universe_size) if mask & (1 << e)] for mask in instance.sets]})
    pairs = {}
    for base in bases:
        pairs.setdefault(base["repetition"], []).append(base)
    require(set(pairs) == set(range(config.repetitions)), "missing or extra repetitions")
    for pair in pairs.values():
        require(len(pair) == 2 and {p["case_id"] for p in pair} == {"overlap", "overlap_control"}
                and pair[0]["seed"] == pair[1]["seed"], "incomplete or mismatched pair")
    return bases


def summaries(paths):
    from scipy.stats import beta

    rows = []
    for path in paths:
        require(all(path[phase]["status"] == "local_optimum" for phase in ("one_swap", "two_swap")), "incomplete exchanges")
        row = {**path, **instance_summary(path)}
        row["F"] = int(row["greedy"] < row["optimal"])
        row["A"] = int(row["F"] == 1 and row["mechanism"] == "tie_avoidable")
        row["missing_reason"] = "zero_optimum_relative_gap" if row["optimal"] == 0 else ""
        rows.append({field: row[field] for field in INSTANCE_FIELDS})
    groups = []
    for case in ("overlap", "overlap_control"):
        members = [row for row in rows if row["case_id"] == case]
        n = len(members)
        require(n > 0, "missing summary group")
        failed = [row for row in members if row["F"]]
        m, x = len(failed), sum(row["A"] for row in failed)
        lower = float(beta.ppf(0.0125, x, m - x + 1)) if x else 0.0
        upper = float(beta.ppf(0.9875, x + 1, m - x)) if x < m else 1.0
        group = {"population": members[0]["population"], "config_hash": members[0]["config_hash"],
                 "case_id": case, "N": n, "M": m, "X": x,
                 "theta": x / m if m else None, "theta_lower": lower, "theta_upper": upper,
                 "theta_status": "estimable" if m else "not_estimable", "failure_rate": m / n,
                 "tie_avoidable_rate": x / n, "gap_defined_n": sum(row["optimal"] != 0 for row in members),
                 "zero_optimum_n": sum(row["optimal"] == 0 for row in members)}
        for t in range(1, 5):
            group[f"first_loss_{t}"] = sum(row["first_failure_step"] == t for row in failed)
        for phase in ("one_swap", "two_swap"):
            recovered = sum(row[phase] == row["optimal"] for row in failed)
            group[f"{phase}_recovered"] = recovered
            group[f"{phase}_recovery_rate"] = recovered / m if m else None
            group[f"{phase}_stalls"] = sum(row[phase] != row["optimal"] for row in members)
        for phase in ("greedy", "one_swap", "two_swap"):
            gaps = [(row["optimal"] - row[phase]) / row["optimal"] for row in members if row["optimal"]]
            group[f"mean_{phase}_gap"] = math.fsum(gaps) / len(gaps) if gaps else None
        groups.append(group)
    h, u = groups
    lower, upper = h["theta_lower"] - u["theta_upper"], h["theta_upper"] - u["theta_lower"]
    estimable = all(group["M"] > 0 for group in groups)
    direction = "not_estimable"
    if estimable:
        direction = "higher" if lower > 0 else "lower" if upper < 0 else "inconclusive"
    return rows, groups, {"population": h["population"], "config_hash": h["config_hash"],
                          "pairs": h["N"], "instances": len(paths),
                          "delta": h["theta"] - u["theta"] if estimable else None,
                          "lower": lower, "upper": upper, "width": upper - lower, "target_width": 0.20,
                          "precision_met": estimable and upper - lower <= 0.20,
                          "estimate_status": "estimable" if estimable else "not_estimable", "direction": direction}


def check_csv(path, fields, expected, key):
    actual = csv_rows(path, fields)
    indexed = {row[key]: row for row in actual}
    require(len(actual) == len(indexed) == len(expected), f"{path.name}: missing or duplicate rows")
    for row in expected:
        require(str(row[key]) in indexed, f"{path.name}: missing identity")
        record = indexed[str(row[key])]
        for field in fields:
            value, observed = row[field], record[field]
            if isinstance(value, float):
                number = float(observed)
                require(math.isfinite(number) and math.isclose(number, value, rel_tol=1e-10, abs_tol=1e-12),
                        f"{path.name}: {field} differs")
            else:
                require(observed == ("" if value is None else str(value)), f"{path.name}: {field} differs")


def validate(config_path, source, output):
    bases = inputs(config_path, source)
    actual = [json.loads(line) for line in (output / "paths.jsonl").read_text(encoding="utf-8").splitlines()]
    require(all(isinstance(path, dict) for path in actual), "trajectories must be objects")
    indexed = {path["instance_id"]: path for path in actual}
    require(len(actual) == len(indexed) == len(bases), "missing or duplicate trajectories")
    paths = []
    for base in bases:
        path = expected_path(base, BUDGETS)
        require(sorted(path["greedy_selected"]) == base["source_greedy_selected"]
                and path["optimum"] == base["source_optimum"], "source Greedy or optimum contradicts enumeration")
        require(base["instance_id"] in indexed, "missing planned trajectory")
        compare(indexed[base["instance_id"]], path, f"trajectory:{base['case_id']}:{base['repetition']}")
        paths.append(path)
    rows, groups, primary = summaries(paths)
    check_csv(output / "instance_summary.csv", INSTANCE_FIELDS, rows, "instance_id")
    check_csv(output / "group_summary.csv", GROUP_FIELDS, groups, "case_id")
    check_csv(output / "primary_summary.csv", PRIMARY_FIELDS, [primary], "config_hash")
    return len(paths)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        count = validate(args.config, args.results, args.output)
    except (ValueError, TypeError, KeyError, OSError, IndexError, ImportError) as error:
        print(f"R1c validation failed: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {count} R1c instances, complete trajectories and three summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
