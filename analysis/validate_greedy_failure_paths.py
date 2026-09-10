"""Independently check the fixed R1 trajectories using sets and enumeration.

Only input generation and stable identities come from the project. Coverage,
restricted optima, tie candidates, exchanges, and summaries are recomputed here;
the trajectory producer and its calculation helpers are never imported.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from itertools import combinations
from pathlib import Path
from statistics import fmean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark_planning import _instances_for_config
from maxcover.config import load_config
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import config_hash, instance_id


INSTANCE_FIELDS = (
    "population", "case_id", "repetition", "instance_id", "greedy", "optimal",
    "first_failure_step", "mechanism", "one_swap", "two_swap", "one_swap_moves",
    "two_swap_moves", "one_swap_evaluations", "two_swap_evaluations", "two_swap_status",
    "greedy_gap", "one_swap_gap", "two_swap_gap",
)
CASE_FIELDS = (
    "case_id", "n", "greedy_failures", "tie_avoidable", "one_step_limit",
    "first_loss_1", "first_loss_2", "first_loss_3", "first_loss_4",
    "one_swap_recovered", "two_swap_recovered", "one_swap_stalls", "two_swap_stalls",
    "two_swap_incomplete", "mean_greedy_gap", "mean_one_swap_gap", "mean_two_swap_gap",
    "tie_avoidable_among_failures", "tie_avoidable_among_all",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def compare(actual: Any, expected: Any, location: str) -> None:
    """Compare declared fields with type sensitivity, including bool versus int."""
    require(type(actual) is type(expected), f"{location}: incorrect value type")
    if isinstance(expected, dict):
        require(set(actual) == set(expected), f"{location}: incorrect fields")
        for key in expected:
            compare(actual[key], expected[key], f"{location}.{key}")
    elif isinstance(expected, list):
        require(len(actual) == len(expected), f"{location}: incorrect length")
        for index, value in enumerate(expected):
            compare(actual[index], value, f"{location}[{index}]")
    else:
        require(actual == expected, f"{location}: expected {expected!r}, got {actual!r}")


def coverage(sets: list[set[int]], selected: tuple[int, ...] | list[int]) -> int:
    covered: set[int] = set()
    for index in selected:
        covered.update(sets[index])
    return len(covered)


def best_completion(
    sets: list[set[int]], k: int, prefix: list[int], limit: int,
) -> tuple[int, list[int], int, int]:
    fixed = set(prefix)
    require(len(fixed) == len(prefix) and len(fixed) <= k, "invalid completion prefix")
    outside = [index for index in range(len(sets)) if index not in fixed]
    count = math.comb(len(outside), k - len(fixed))
    require(count <= limit, "completion enumeration exceeds the design budget")
    optimum = -1
    witness: tuple[int, ...] | None = None
    optimal_count = 0
    inspected = 0
    for extra in combinations(outside, k - len(fixed)):
        selected = tuple(sorted(fixed | set(extra)))
        value = coverage(sets, selected)
        inspected += 1
        if value > optimum:
            optimum, witness, optimal_count = value, selected, 1
        elif value == optimum:
            optimal_count += 1
            if witness is None or selected < witness:
                witness = selected
    require(inspected == count and witness is not None, "incomplete completion enumeration")
    return optimum, list(witness), inspected, optimal_count


def exchange(
    sets: list[set[int]], initial: list[int], maximum_size: int, budget: int | None,
) -> dict[str, Any]:
    selected = tuple(sorted(initial))
    total = 0
    moves = 0
    rounds: list[dict[str, Any]] = []
    while True:
        value = coverage(sets, selected)
        chosen = set(selected)
        outside = tuple(index for index in range(len(sets)) if index not in chosen)
        best_value = value
        best: tuple[int, tuple[int, ...], tuple[int, ...]] | None = None
        count = 0
        exhausted = False
        for size in range(1, min(maximum_size, len(selected), len(outside)) + 1):
            for removed in combinations(selected, size):
                for added in combinations(outside, size):
                    if budget is not None and total + count >= budget:
                        exhausted = True
                        break
                    candidate = tuple(sorted((chosen - set(removed)) | set(added)))
                    candidate_value = coverage(sets, candidate)
                    count += 1
                    key = (size, removed, added)
                    if candidate_value > best_value or (
                        candidate_value == best_value and best is not None and key < best
                    ):
                        best_value, best = candidate_value, key
                if exhausted:
                    break
            if exhausted:
                break
        total += count
        if exhausted or best is None:
            status = "budget_exhausted" if exhausted else "local_optimum"
            after = selected
            removed_tuple: tuple[int, ...] = ()
            added_tuple: tuple[int, ...] = ()
        else:
            status = "improved"
            _, removed_tuple, added_tuple = best
            after = tuple(sorted((chosen - set(removed_tuple)) | set(added_tuple)))
            moves += 1
        rounds.append({
            "round": len(rounds) + 1,
            "before": list(selected), "before_coverage": value,
            "removed": list(removed_tuple), "added": list(added_tuple),
            "after": list(after), "after_coverage": coverage(sets, after),
            "evaluations": count, "status": status,
        })
        selected = after
        if status != "improved":
            return {"selected": list(selected), "coverage": coverage(sets, selected),
                    "evaluations": total, "exchanges": moves, "status": status,
                    "rounds": rounds}


def expected_path(base: dict[str, Any], design: dict[str, Any], *,
                  completion_backend: str = "python") -> dict[str, Any]:
    solve = best_completion
    if completion_backend != "python":
        from verification_completion import get_completion_solver
        solve = get_completion_solver(completion_backend)
    sets = [set(elements) for elements in base["sets"]]
    k = base["k"]
    limit = design["max_completions"]
    optimum, witness, count, optimal_count = solve(sets, k, [], limit)
    prefixes: list[dict[str, Any]] = []
    ties: list[dict[str, Any]] = []
    prefix: list[int] = []
    first_failure: int | None = None
    while True:
        completed, completed_selection, completed_count, _ = solve(sets, k, prefix, limit)
        prefixes.append({"step": len(prefix), "prefix": list(prefix),
                         "coverage": coverage(sets, prefix), "optimal_completion": completed,
                         "completion_selected": completed_selection,
                         "completion_count": completed_count})
        if completed < optimum and first_failure is None:
            first_failure = len(prefix)
        if len(prefix) == k:
            break
        gains = {index: coverage(sets, prefix + [index]) - coverage(sets, prefix)
                 for index in range(len(sets)) if index not in prefix}
        maximum = max(gains.values())
        candidates = sorted(index for index, gain in gains.items() if gain == maximum)
        chosen = candidates[0]
        for candidate in candidates:
            value, selection, candidate_count, _ = solve(sets, k, prefix + [candidate], limit)
            ties.append({"step": len(prefix) + 1, "candidate": candidate,
                         "marginal_gain": maximum, "chosen": candidate == chosen,
                         "optimal_completion": value, "completion_selected": selection,
                         "completion_count": candidate_count, "preserves_optimum": value == optimum})
        prefix.append(chosen)
    mechanism = "optimal" if first_failure is None else (
        "tie_avoidable" if any(row["step"] == first_failure and row["preserves_optimum"]
                               for row in ties) else "one_step_limit"
    )
    one = exchange(sets, prefix, 1, None)
    two = exchange(sets, one["selected"], 2, design["max_two_swap_evaluations"])
    if base["population"] == "pilot":
        require(sorted(base["source_greedy_selected"]) == sorted(prefix),
                f"{base['instance_id']}: source Greedy selection disagrees")
        require(base["source_optimum"] == optimum,
                f"{base['instance_id']}: source exact optimum disagrees")
    return {**base, "greedy_selected": prefix, "optimum": optimum,
            "optimum_selected": witness, "optimal_solution_count": optimal_count,
            "completion_count": count, "prefixes": prefixes, "ties": ties,
            "first_failure_step": first_failure, "mechanism": mechanism,
            "one_swap": one, "two_swap": two}


def csv_rows(path: Path, fields: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if fields is not None:
            require(tuple(reader.fieldnames or ()) == fields, f"{path.name}: incorrect fields")
        rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows),
            f"{path.name}: malformed CSV")
    return rows


def inputs(design: dict[str, Any]) -> list[dict[str, Any]]:
    config = load_config(ROOT / design["config"])
    identifier = config_hash(config)
    records = csv_rows(ROOT / design["source_results"] / "raw_results.csv")
    source: dict[tuple[str, str], dict[str, str]] = {}
    for record in records:
        require(record["config_hash"] == identifier, "source configuration mismatch")
        key = (record["instance_id"], record["algorithm_id"])
        require(key not in source, "source contains duplicate algorithm/instance rows")
        source[key] = record
    bases = []
    for planned in _instances_for_config(config):
        instance = planned.instance
        iid = instance_id(instance)
        greedy = source[(iid, "greedy")]
        exact = source[(iid, "exact_reference")]
        require(exact["status"] == "optimal" and exact["algorithm"] == "brute_force",
                "source reference must be the completed exhaustive result")
        require(greedy["status"] in {"feasible", "optimal"} and greedy["algorithm"] == "greedy",
                "source Greedy run did not complete")
        for row in (greedy, exact):
            require(row["case_id"] == planned.case_id and int(row["repetition"]) == planned.repetition
                    and int(row["seed"]) == instance.seed, "source instance identity mismatch")
        bases.append({"instance_id": iid, "population": "pilot", "case_id": planned.case_id,
                      "repetition": planned.repetition, "seed": instance.seed,
                      "config_hash": identifier, "universe_size": instance.universe_size,
                      "k": instance.k,
                      "sets": [[element for element in range(instance.universe_size) if mask & (1 << element)]
                               for mask in instance.sets],
                      "source_greedy_selected": [int(index) for index in greedy["selected"].split()],
                      "source_optimum": int(exact["coverage"])})
    require(len(source) == 2 * len(bases), "source contains unplanned records")
    for fixture in design["fixtures"]:
        instance = MaximumCoverageInstance(
            universe_size=fixture["universe_size"], k=fixture["k"],
            sets=tuple(sum(1 << element for element in elements) for elements in fixture["sets"]),
            family="custom", parameters={"r1_fixture": fixture["name"]},
        )
        bases.append({"instance_id": instance_id(instance), "population": "fixture",
                      "case_id": fixture["name"], "repetition": None, "seed": None,
                      "config_hash": None, "universe_size": fixture["universe_size"],
                      "k": fixture["k"], "sets": fixture["sets"],
                      "source_greedy_selected": None, "source_optimum": None})
    require(len({row["instance_id"] for row in bases}) == len(bases), "duplicate planned instance identities")
    return bases


def gap(value: int, optimum: int) -> float | None:
    return (optimum - value) / optimum if optimum else None


def instance_summary(path: dict[str, Any]) -> dict[str, Any]:
    one, two = path["one_swap"], path["two_swap"]
    greedy = path["prefixes"][-1]["coverage"]
    optimum = path["optimum"]
    return {"population": path["population"], "case_id": path["case_id"],
            "repetition": path["repetition"], "instance_id": path["instance_id"],
            "greedy": greedy, "optimal": optimum,
            "first_failure_step": path["first_failure_step"], "mechanism": path["mechanism"],
            "one_swap": one["coverage"], "two_swap": two["coverage"],
            "one_swap_moves": one["exchanges"], "two_swap_moves": two["exchanges"],
            "one_swap_evaluations": one["evaluations"], "two_swap_evaluations": two["evaluations"],
            "two_swap_status": two["status"], "greedy_gap": gap(greedy, optimum),
            "one_swap_gap": gap(one["coverage"], optimum), "two_swap_gap": gap(two["coverage"], optimum)}


def case_summaries(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    case_ids = sorted({path["case_id"] for path in paths if path["population"] == "pilot"})
    for case_id in case_ids:
        members = [path for path in paths if path["population"] == "pilot" and path["case_id"] == case_id]
        n = len(members)
        summaries = [instance_summary(path) for path in members]
        failures = sum(row["greedy"] < row["optimal"] for row in summaries)
        avoidable = sum(row["mechanism"] == "tie_avoidable" for row in summaries)
        result.append({
            "case_id": case_id, "n": n, "greedy_failures": failures,
            "tie_avoidable": avoidable,
            "one_step_limit": sum(row["mechanism"] == "one_step_limit" for row in summaries),
            **{f"first_loss_{step}": sum(row["first_failure_step"] == step for row in summaries)
               for step in range(1, 5)},
            **{f"{phase}_recovered": sum(row["greedy"] < row["optimal"] and row[phase] == row["optimal"]
                                        for row in summaries) for phase in ("one_swap", "two_swap")},
            **{f"{phase}_stalls": sum(path[phase]["coverage"] < path["optimum"]
                                      and path[phase]["status"] == "local_optimum" for path in members)
               for phase in ("one_swap", "two_swap")},
            "two_swap_incomplete": sum(path["two_swap"]["status"] != "local_optimum" for path in members),
            **{f"mean_{name}_gap": fmean(row[f"{name}_gap"] for row in summaries)
               for name in ("greedy", "one_swap", "two_swap")},
            "tie_avoidable_among_failures": avoidable / failures if failures else None,
            "tie_avoidable_among_all": avoidable / n,
        })
    return result


def validate_csv(path: Path, fields: tuple[str, ...], expected: list[dict[str, Any]], key: str) -> None:
    actual = csv_rows(path, fields)
    require(len(actual) == len(expected), f"{path.name}: incorrect row count")
    indexed = {row[key]: row for row in actual}
    require(len(indexed) == len(actual), f"{path.name}: duplicate {key}")
    for row in expected:
        formatted = {field: "" if row[field] is None else (
            format(row[field], ".12g") if isinstance(row[field], float) else str(row[field]))
                     for field in fields}
        require(row[key] in indexed, f"{path.name}: missing {key} {row[key]}")
        compare(indexed[row[key]], formatted, f"{path.name}:{row[key]}")


def validate(design_path: Path, output: Path) -> int:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    for field in ("max_completions", "max_two_swap_evaluations"):
        require(type(design[field]) is int and design[field] >= (1 if field == "max_completions" else 0),
                f"{field}: invalid budget")
    bases = inputs(design)
    lines = (output / "paths.jsonl").read_text(encoding="utf-8").splitlines()
    require(len(lines) == len(bases), "paths.jsonl: incorrect instance count")
    actual = [json.loads(line) for line in lines]
    require(all(isinstance(path, dict) for path in actual), "paths.jsonl: expected objects")
    indexed = {path["instance_id"]: path for path in actual}
    require(len(indexed) == len(actual), "paths.jsonl: duplicate instance identity")
    expected = []
    for base in bases:
        path = expected_path(base, design)
        iid = base["instance_id"]
        require(iid in indexed, f"paths.jsonl: missing instance {iid}")
        compare(indexed[iid], path, f"paths.jsonl:{base['population']}:{base['case_id']}:{base['repetition']}")
        expected.append(path)
    validate_csv(output / "instance_summary.csv", INSTANCE_FIELDS,
                 [instance_summary(path) for path in expected], "instance_id")
    validate_csv(output / "case_summary.csv", CASE_FIELDS, case_summaries(expected), "case_id")
    return len(expected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        count = validate(args.design, args.output)
    except (ValueError, TypeError, KeyError, OSError, IndexError) as error:
        print(f"R1 validation failed: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {count} instances, trajectories and both summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
