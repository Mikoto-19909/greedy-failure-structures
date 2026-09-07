"""Analyze complete R1c benchmark inputs; validate before publishing outputs."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]

from greedy_failure_paths import analyze_instance, instance_summary, write_csv
from maxcover.benchmark_planning import _instance_record, _instances_for_config, _validate_run_identity
from maxcover.config import load_config
from maxcover.contracts import InstanceRecord, RunRecord
from maxcover.model import SolutionStatus
from maxcover.reproducibility import config_hash
from r1c_design_check import exact_interval

# Normalized experiment identities from the frozen design, not file checksums.
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


def read_records(path, record_type):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != record_type.CSV_FIELDS:
            raise ValueError(f"{path.name}: unexpected CSV fields")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"{path.name}: malformed row")
    return [record_type.from_csv_row(row) for row in rows]


def load_inputs(config_path, source):
    config = load_config(config_path)
    identifier = config_hash(config)
    if identifier not in PROFILES:
        raise ValueError("configuration is not a frozen R1c formal or preflight design")
    planned = _instances_for_config(config)
    instances = read_records(source / "instances.csv", InstanceRecord)
    expected = {item.instance_id: _instance_record(item, identifier) for item in planned}
    if len(instances) != len(expected) or len({r.instance_id for r in instances}) != len(expected):
        raise ValueError("instances.csv: incomplete or duplicate planned instances")
    for row in instances:
        if row.instance_id not in expected or row.to_csv_row() != expected[row.instance_id].to_csv_row():
            raise ValueError("instances.csv: instance differs from the execution plan")
    runs = read_records(source / "raw_results.csv", RunRecord)
    tasks = _validate_run_identity(config, identifier, runs, planned_instances=planned)
    indexed = {}
    for row in runs:
        if (row.status not in {SolutionStatus.FEASIBLE, SolutionStatus.OPTIMAL}
                or json.loads(row.algorithm_metadata)["termination"] != "completed" or row.error_message):
            raise ValueError("raw_results.csv: run did not complete")
        instance = tasks[row.run_id].instance
        if len(row.selected) > instance.k or any(i < 0 or i >= instance.set_count for i in row.selected):
            raise ValueError("raw_results.csv: infeasible selected indices")
        if instance.coverage(row.selected) != row.coverage:
            raise ValueError("raw_results.csv: selected coverage mismatch")
        indexed[(row.instance_id, row.algorithm_id)] = row
    entries = []
    for item in planned:
        instance = item.instance
        g, o = (indexed[(item.instance_id, name)] for name in ("greedy", "exact_reference"))
        if (o.status is not SolutionStatus.OPTIMAL or o.coverage is None
                or g.optimum != o.coverage or o.optimum != o.coverage or g.coverage > o.coverage):
            raise ValueError("raw_results.csv: incomplete or inconsistent exact reference")
        for row in (g, o):
            if ((row.status is SolutionStatus.OPTIMAL and row.coverage != o.coverage)
                    or (row.best_bound is not None and row.best_bound < o.coverage)):
                raise ValueError("raw_results.csv: optimal status or bound contradicts the reference")
            gap = (o.coverage - row.coverage) / o.coverage if o.coverage else None
            if row.optimality_gap != gap:
                # Raw CSV uses a decimal representation; allow its rounding error.
                if gap is None or row.optimality_gap is None or not math.isclose(row.optimality_gap, gap, abs_tol=1e-10):
                    raise ValueError("raw_results.csv: inconsistent reference gap")
        base = {"population": PROFILES[identifier], "config_hash": identifier,
                "pair_id": f"{identifier}:{item.repetition}", "case_id": item.case_id,
                "repetition": item.repetition, "seed": instance.seed, "instance_id": item.instance_id,
                "greedy_run_id": g.run_id, "exact_run_id": o.run_id,
                "source_greedy_selected": list(g.selected), "source_optimum": o.coverage,
                "universe_size": instance.universe_size, "k": instance.k,
                "sets": [[e for e in range(instance.universe_size) if mask & (1 << e)] for mask in instance.sets]}
        entries.append((base, instance))
    return entries


def summarize(paths):
    if not paths:
        raise ValueError("no complete instances")
    rows = []
    for path in paths:
        if any(path[phase]["status"] != "local_optimum" for phase in ("one_swap", "two_swap")):
            raise ValueError("incomplete exchange neighborhood; no R1c summary is publishable")
        row = {**path, **instance_summary(path)}
        row.update(F=int(row["greedy"] < row["optimal"]), A=int(row["mechanism"] == "tie_avoidable"),
                   missing_reason="zero_optimum_relative_gap" if row["optimal"] == 0 else "")
        rows.append({field: row[field] for field in INSTANCE_FIELDS})
    groups = []
    for case in ("overlap", "overlap_control"):
        members = [row for row in rows if row["case_id"] == case]
        if not members:
            raise ValueError("both R1c groups are required")
        n, m, x = len(members), sum(row["F"] for row in members), sum(row["A"] for row in members)
        lower, upper = exact_interval(x, m)
        group = {"population": members[0]["population"], "config_hash": members[0]["config_hash"],
                 "case_id": case, "N": n, "M": m, "X": x, "theta": x / m if m else None,
                 "theta_lower": lower, "theta_upper": upper, "theta_status": "estimable" if m else "not_estimable",
                 "failure_rate": m / n, "tie_avoidable_rate": x / n,
                 **{f"first_loss_{t}": sum(row["first_failure_step"] == t for row in members) for t in range(1, 5)},
                 "gap_defined_n": sum(row["optimal"] > 0 for row in members),
                 "zero_optimum_n": sum(row["optimal"] == 0 for row in members)}
        for phase in ("one_swap", "two_swap"):
            recovered = sum(row["F"] and row[phase] == row["optimal"] for row in members)
            group.update({f"{phase}_recovered": recovered, f"{phase}_recovery_rate": recovered / m if m else None,
                          f"{phase}_stalls": sum(row[phase] < row["optimal"] for row in members)})
        for phase in ("greedy", "one_swap", "two_swap"):
            gaps = [row[f"{phase}_gap"] for row in members if row[f"{phase}_gap"] is not None]
            group[f"mean_{phase}_gap"] = fmean(gaps) if gaps else None
        groups.append(group)
    left, right = groups
    lower = left["theta_lower"] - right["theta_upper"]
    upper = left["theta_upper"] - right["theta_lower"]
    estimable = left["M"] > 0 and right["M"] > 0
    direction = ("higher" if lower > 0 else "lower" if upper < 0 else "inconclusive") if estimable else "not_estimable"
    primary = {"population": left["population"], "config_hash": left["config_hash"],
               "pairs": left["N"], "instances": len(rows),
               "delta": left["theta"] - right["theta"] if estimable else None,
               "lower": lower, "upper": upper, "width": upper - lower, "target_width": 0.20,
               "precision_met": estimable and upper - lower <= 0.20,
               "estimate_status": "estimable" if estimable else "not_estimable", "direction": direction}
    return rows, groups, primary


def run(config_path, source, output):
    # Fail for missing offline dependency before constructing any study instances.
    exact_interval(0, 1)
    output = output.resolve()
    if output.exists():
        raise ValueError("output must not exist; use a new analysis directory")
    entries = load_inputs(config_path, source)
    paths = []
    for base, instance in entries:
        result = analyze_instance(instance, **BUDGETS)
        if (sorted(result["greedy_selected"]) != base["source_greedy_selected"]
                or result["optimum"] != base["source_optimum"]):
            raise ValueError("exact reconstruction differs from source Greedy or reference")
        paths.append({**base, **result})
    rows, groups, primary = summarize(paths)
    output.parent.mkdir(parents=True, exist_ok=True)
    # The temporary directory and destination share a filesystem. Nothing is
    # published at the requested destination until independent validation passes.
    with tempfile.TemporaryDirectory(prefix=".r1c-", dir=output.parent) as temporary:
        staged = Path(temporary)
        (staged / "paths.jsonl").write_text("".join(json.dumps(path, ensure_ascii=False) + "\n" for path in paths), encoding="utf-8", newline="\n")
        write_csv(staged / "instance_summary.csv", rows, INSTANCE_FIELDS)
        write_csv(staged / "group_summary.csv", groups, GROUP_FIELDS)
        write_csv(staged / "primary_summary.csv", [primary], PRIMARY_FIELDS)
        from validate_r1c_confirmation import validate
        validate(config_path, source, staged)
        staged.rename(output)
    return len(paths)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        count = run(args.config, args.results, args.output)
    except (ValueError, TypeError, KeyError, OSError, IndexError, ImportError) as error:
        print(f"R1c analysis failed: {error}", file=sys.stderr)
        return 1
    print(f"R1c analysis and independent validation passed: {count} instances; output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
