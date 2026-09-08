"""Independent set-based validation of L5 Method 4 / Method 3 certificates.

The checker rebuilds Greedy, every conditional residual, its stable ordering,
prefix unions and the maximum in every recurrence round from original sets.
It does not import any producer bound or summary calculation.
"""
from __future__ import annotations

import argparse
import csv
from itertools import combinations
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from validate_r2_budget_grid import memory_usage
from r4_dual_io import (METRICS, SourceAccess, RuntimeBudget, check_resources,
                        check_code_revision, load_records, read_json, validate_configuration, write_json)


def same(actual, expected, label):
    """Compare JSON-shaped data without accepting bools as integers."""
    if type(actual) is not type(expected):
        raise ValueError(f"R4 DUAL mismatch: {label} type")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"R4 DUAL mismatch: {label} fields")
        for key, value in expected.items():
            same(actual[key], value, f"{label}.{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"R4 DUAL mismatch: {label} length")
        for index, value in enumerate(expected):
            same(actual[index], value, f"{label}[{index}]")
    elif actual != expected:
        raise ValueError(f"R4 DUAL mismatch: {label}")


def verify_certificate(elements, value):
    """Check one complete budget certificate against its original set lists.

    Exhaustive maxima are intentionally evaluated over all sorted residual
    indices, independently of the producer's crossing-point implementation.
    Conditional problems use the original full budget, including at P_k.
    """
    if not isinstance(elements, list) or not elements:
        raise ValueError("R4 DUAL requires a nonempty list of original sets")
    sets = []
    for candidates in elements:
        if (not isinstance(candidates, list)
                or any(type(item) is not int or item < 0 for item in candidates)
                or len(set(candidates)) != len(candidates)):
            raise ValueError("R4 DUAL original set contains invalid elements")
        sets.append(set(candidates))
    if not isinstance(value, dict):
        raise ValueError("R4 DUAL certificate must be an object")
    k = value.get("k")
    if type(k) is not int or not 1 <= k <= len(sets):
        raise ValueError("R4 DUAL budget must be an integer in 1..M")

    covered = set()
    selected = []
    prefixes = []
    simple_prefix_candidates = []
    total = len(set().union(*sets))
    initial = min(total, k * max(map(len, sets)))
    for t in range(k + 1):
        residuals = [candidate - covered for candidate in sets]
        order = sorted(range(len(sets)), key=lambda i: (-len(residuals[i]), i))
        sizes, union_sizes = [], []
        residual_union = set()
        for index in order:
            sizes.append(len(residuals[index]))
            residual_union.update(residuals[index])
            union_sizes.append(len(residual_union))
        q = [0]
        for _ in range(k):
            candidates = [min(union_size, q[-1] + size)
                          for union_size, size in zip(union_sizes, sizes)]
            q.append(max(candidates))
        coverage = len(covered)
        prefixes.append({"t": t, "selected": list(selected), "coverage": coverage,
                         "order": order, "s": sizes, "F": union_sizes,
                         "q": q, "upper": coverage + q[k]})
        simple_prefix_candidates.append(coverage + k * max(sizes))
        if t < k:
            available = [index for index in range(len(sets)) if index not in selected]
            chosen = min(available, key=lambda index: (-len(residuals[index]), index))
            selected.append(chosen)
            covered.update(sets[chosen])

    prefix_upper = min([total] + simple_prefix_candidates)
    dual_upper = min([total] + [prefix["upper"] for prefix in prefixes])
    greedy = len(covered)
    expected = {"k": k, "path": selected, "greedy": greedy, "union_size": total,
                "initial_upper": initial, "prefix_upper": prefix_upper,
                "dual_upper": dual_upper,
                "minimizing_prefixes": [prefix["t"] for prefix in prefixes
                                        if prefix["upper"] == dual_upper],
                "prefixes": prefixes}
    same(value, expected, "certificate")
    if not greedy <= dual_upper <= prefix_upper <= initial <= total:
        raise ValueError("R4 DUAL bound ordering failed")
    if len({len(candidate) for candidate in sets}) == 1:
        if (dual_upper == greedy) != (initial == greedy):
            raise ValueError("R4 DUAL equal-size certification equivalence failed")


def _verify_reference(elements, value, reference, exhaustive):
    sets = [set(candidate) for candidate in elements]
    same(reference["k"], value["k"], "reference budget")
    same(reference["reference_status"], "optimal", "reference status")
    same(reference["greedy"], value["greedy"], "source Greedy coverage")
    same(reference["greedy_selected"], sorted(value["path"]), "source Greedy terminal set")
    witness = reference["optimum_selected"]
    if (not isinstance(witness, list) or len(witness) != value["k"]
            or any(type(index) is not int or not 0 <= index < len(sets) for index in witness)
            or witness != sorted(set(witness))):
        raise ValueError("R4 DUAL invalid exact reference selected set")
    coverage = len(set().union(*(sets[index] for index in witness)))
    same(reference["optimum"], coverage, "reference witness coverage")
    if exhaustive:
        optimum, canonical = -1, None
        for chosen in combinations(range(len(sets)), value["k"]):
            candidate_coverage = len(set().union(*(sets[index] for index in chosen)))
            if candidate_coverage > optimum:
                optimum, canonical = candidate_coverage, list(chosen)
        same(reference["optimum"], optimum, "exhaustive optimum")
        same(witness, canonical, "exhaustive canonical witness")
    if not value["greedy"] <= coverage <= value["dual_upper"]:
        raise ValueError("R4 DUAL reference ordering G <= O <= DUAL failed")


def _verify_baseline(value, baseline):
    """Check old prefix certificates using independently rebuilt new arrays."""
    prefixes = []
    for prefix in value["prefixes"]:
        available = [index for index in prefix["order"] if index not in prefix["selected"]]
        maximum = max(prefix["s"])
        prefixes.append({"t": prefix["t"], "coverage": prefix["coverage"],
                         "max_gain": maximum,
                         "gain_witness": available[0] if available else None,
                         "upper": prefix["coverage"] + value["k"] * maximum})
    expected = {"k": value["k"], "path": value["path"], "prefixes": prefixes,
                "greedy": value["greedy"], "union_size": value["union_size"],
                "initial_upper": value["initial_upper"], "upper": value["prefix_upper"]}
    same(baseline, expected, "archived prefix certificate")


def verify_record(record, original, config):
    """Validate a graph and reuse only references linked by trusted source I/O.

    Formal comparison independently checks the saved exact witness and its
    association with the pinned evidence. Earlier exhaustive proof is reused;
    fixtures and independent preflight inputs are enumerated in this checker.
    """
    started = time.perf_counter()
    if not isinstance(record, dict):
        raise ValueError("R4 DUAL checkpoint must be an object")
    same(set(record), {"version", "source_commit", "task", "source", "status", "values", "timing"},
         "checkpoint fields")
    same(record["version"], config["version"], "method version")
    same(record["source_commit"], config["source_commit"], "source commit")
    same(record["task"], original["task"], "source task")
    same(record["source"], original, "source association")
    same(record["status"], "complete", "completion")
    if not isinstance(record["values"], list):
        raise ValueError("R4 DUAL values must be a list")
    same([value["k"] for value in record["values"]], original["task"]["budgets"],
         "complete budget records")
    same([reference["k"] for reference in original["values"]], original["task"]["budgets"],
         "complete reference records")
    timing = record["timing"]
    if (not isinstance(timing, dict) or not timing
            or any(type(number) not in (int, float) or not math.isfinite(number) or number < 0
                   for number in timing.values())):
        raise ValueError("R4 DUAL invalid checkpoint resource timing")
    for value in record["values"]:
        verify_certificate(original["sets"], value)
    baseline = original.get("baseline_values")
    if config["phase"] == "comparison":
        if not isinstance(baseline, list):
            raise ValueError("R4 DUAL comparison requires archived prefix certificates")
        same([value["k"] for value in baseline], original["task"]["budgets"], "baseline budgets")
    if baseline:
        for value, old_value in zip(record["values"], baseline):
            _verify_baseline(value, old_value)
    certificate_seconds = time.perf_counter() - started
    started = time.perf_counter()
    for value, reference in zip(record["values"], original["values"]):
        _verify_reference(original["sets"], value, reference, config["phase"] != "comparison")
    return {"certificate_seconds": certificate_seconds,
            "reference_seconds": time.perf_counter() - started,
            "peak_memory_bytes": memory_usage()}


def validate_batch(output, source):
    """Revalidate all current certificates and their authoritative sources."""
    output = Path(output)
    started = time.perf_counter()
    report = {"status": "incomplete", "graphs": {}}
    config = validate_configuration(read_json(output / "config.json"))
    check_code_revision(config)
    with RuntimeBudget(output, config, "dual_independent_verification") as budget:
        write_json(output / "verification.json", report)
        try:
            check_resources(output, config, memory_usage())
            source_started = time.perf_counter()
            with SourceAccess(source, config) as access:
                report["source_setup_seconds"] = time.perf_counter() - source_started
                records = iter(load_records(output, config))
                count = 0
                while True:
                    read_started = time.perf_counter()
                    try:
                        record = next(records)
                    except StopIteration:
                        break
                    read_seconds = time.perf_counter() - read_started
                    budget.check()
                    source_started = time.perf_counter()
                    original = access.record(record["task"])
                    source_seconds = time.perf_counter() - source_started
                    timing = verify_record(record, original, config)
                    timing.update(source_read_seconds=source_seconds, checkpoint_read_seconds=read_seconds)
                    report["graphs"][record["task"]["base_graph_id"]] = timing
                    count += len(record["values"])
                    # Graph checkpoints are read-only in this owned operation;
                    # repeated full-tree size scans would add quadratic I/O.
                    if timing["peak_memory_bytes"] > config["limits"]["memory_bytes"]:
                        raise RuntimeError("R4 DUAL memory budget exhausted; preserve checkpoints")
            budget.check()
            check_resources(output, config, memory_usage())
            report.update(status="passed", graph_count=len(report["graphs"]), budget_records=count,
                          reference_check=("published_reference_association_and_witness_coverage"
                                           if config["phase"] == "comparison" else "independent_exhaustive"),
                          wall_seconds=time.perf_counter() - started, peak_memory_bytes=memory_usage())
        finally:
            write_json(output / "verification.json", report)
    return report


def _expected_tables(records):
    """Independently derive paired budget rows and descriptive cell summaries."""
    rows = []
    for record in records:
        task = record["task"]
        same([value["k"] for value in record["values"]], task["budgets"], "summary budget completeness")
        same([value["k"] for value in record["source"]["values"]], task["budgets"],
             "summary reference completeness")
        for value, reference in zip(record["values"], record["source"]["values"]):
            greedy, optimum = value["greedy"], reference["optimum"]
            initial, prefix, dual = value["initial_upper"], value["prefix_upper"], value["dual_upper"]
            k = value["k"]
            initial_ratio = greedy / initial if initial else None
            prefix_ratio = greedy / prefix if prefix else None
            dual_ratio = greedy / dual if dual else None
            rows.append({"base_graph_id": task["base_graph_id"], "instance_id": reference["instance_id"],
                         "n": task["n"], "d": task["d"], "k": k, "greedy": greedy, "optimum": optimum,
                         "initial_upper": initial, "prefix_upper": prefix, "dual_upper": dual,
                         "endpoint": "k=1" if k == 1 else "k=M" if k == task["n"] else "interior",
                         "tightening_initial": initial - dual, "tightening_prefix": prefix - dual,
                         "initial_ratio": initial_ratio, "prefix_ratio": prefix_ratio, "dual_ratio": dual_ratio,
                         "ratio_gain_initial": dual_ratio - initial_ratio if dual and initial else None,
                         "ratio_gain_prefix": dual_ratio - prefix_ratio if dual and prefix else None,
                         "dual_over_optimum": dual / optimum if optimum else None,
                         "initial_certified": int(greedy == initial), "prefix_certified": int(greedy == prefix),
                         "dual_certified": int(greedy == dual)})
    cells = []
    groups = {}
    for row in rows:
        groups.setdefault((row["n"], row["d"], row["k"]), []).append(row)
    for (n, d, k), samples in sorted(groups.items()):
        cell = {"n": n, "d": d, "k": k, "count": len(samples),
                "endpoint": "k=1" if k == 1 else "k=M" if k == n else "interior",
                "tightened_initial": sum(row["initial_upper"] > row["dual_upper"] for row in samples),
                "tightened_prefix": sum(row["prefix_upper"] > row["dual_upper"] for row in samples),
                "initial_certified": sum(row["initial_certified"] for row in samples),
                "prefix_certified": sum(row["prefix_certified"] for row in samples),
                "dual_certified": sum(row["dual_certified"] for row in samples)}
        for metric in METRICS:
            numbers = sorted(row[metric] for row in samples if row[metric] is not None)
            count = len(numbers)
            cell[metric + "_missing"] = len(samples) - count
            cell[metric + "_mean"] = math.fsum(numbers) / count if count else None
            cell[metric + "_median"] = (numbers[(count - 1) // 2] + numbers[count // 2]) / 2 if count else None
            cell[metric + "_p90"] = numbers[(9 * count + 9) // 10 - 1] if count else None
        cells.append(cell)
    return rows, cells


def _numeric_equal(actual, expected):
    if expected is None:
        return actual == ""
    if isinstance(expected, float):
        try:
            return math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return actual == str(expected)


def verify_summaries(output):
    """Check saved CSV arithmetic and identities; source proof is separate."""
    output = Path(output)
    started = time.perf_counter()
    config = validate_configuration(read_json(output / "config.json"))
    check_code_revision(config)
    with RuntimeBudget(output, config, "dual_derived_verification") as budget:
        write_json(output / "summary_verification.json", {"status": "incomplete"})
        def checked_records():
            for record in load_records(output, config):
                budget.check()
                yield record
        rows, cells = _expected_tables(checked_records())
        for name, expected in (("budget_results.csv", rows), ("cell_summary.csv", cells)):
            with (output / name).open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                actual = list(reader)
                if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise ValueError("R4 DUAL invalid or duplicate CSV columns")
            same(len(actual), len(expected), "derived row count")
            for got, wanted in zip(actual, expected):
                same(set(got), set(wanted), "derived columns")
                if not all(_numeric_equal(got[key], value) for key, value in wanted.items()):
                    raise ValueError("R4 DUAL derived numeric value or identity differs")
        budget.check()
        check_resources(output, config, memory_usage())
        result = {"status": "passed", "scope": "derived_consistency_only", "budget_rows": len(rows),
                  "cells": len(cells), "wall_seconds": time.perf_counter() - started,
                  "peak_memory_bytes": memory_usage()}
        write_json(output / "summary_verification.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--summaries-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.summaries_only:
            result = verify_summaries(args.output)
        else:
            if args.source is None:
                raise ValueError("full verification requires --source")
            result = validate_batch(args.output, args.source)
        print({key: value for key, value in result.items() if key != "graphs"})
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
