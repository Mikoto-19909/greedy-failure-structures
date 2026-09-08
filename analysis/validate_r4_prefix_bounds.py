"""Independent R4 set-based certificate, optimum and derived-table validation.

Shares only source parsing, identities, resource accounting and I/O. Does not
import the producer's path, upper-bound, optimum or summary functions.
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
from r4_inputs import (validate_configuration, source_record, check_source, read_json,
                       write_json, load_records, RuntimeBudget, check_resources)
from validate_r2_budget_grid import memory_usage


def same(actual, expected, label):
    if actual != expected:
        raise ValueError(f"R4 mismatch: {label}")


def verify_certificate(record, original, config):
    same(record["version"], config["version"], "version")
    same(record["source_commit"], config["source_commit"], "source commit")
    same(record["task"], original["task"], "source task")
    same(record["source"], original, "source association")
    same(record["status"], "complete", "completion")
    task = original["task"]
    same([v["k"] for v in record["values"]], task["budgets"], "complete budget records")
    sets = [set(s) for s in original["sets"]]
    b = len(set().union(*sets))
    for actual, reference in zip(record["values"], original["values"]):
        k = actual["k"]
        covered, path, prefixes = set(), [], []
        for t in range(k + 1):
            scores = [(len(s.difference(covered)), index) for index, s in enumerate(sets) if index not in path]
            maximum = max((score for score, _ in scores), default=0)
            witness = min((index for score, index in scores if score == maximum), default=None)
            prefixes.append({"t": t, "coverage": len(covered), "max_gain": maximum,
                             "gain_witness": witness, "upper": len(covered) + k * maximum})
            if t < k:
                path.append(witness)
                covered.update(sets[witness])
        u = min([b] + [p["upper"] for p in prefixes])
        initial = min(b, k * prefixes[0]["max_gain"])
        expected = {"k": k, "path": path, "prefixes": prefixes, "greedy": len(covered),
                    "union_size": b, "initial_upper": initial, "upper": u}
        same(actual, expected, "path, marginal witnesses and prefix bounds")
        same((len(covered), sorted(path)), (reference["greedy"], reference["greedy_selected"]), "source Greedy")
        if not len(covered) <= u <= initial <= b or (u == len(covered)) != (initial == len(covered)):
            raise ValueError("bound inequalities or certification equivalence failed")


def verify_references(record):
    sets = [set(s) for s in record["source"]["sets"]]
    for value, ref in zip(record["values"], record["source"]["values"]):
        optimum, witness = -1, None
        for selected in combinations(range(len(sets)), value["k"]):
            covered = set()
            for i in selected:
                covered.update(sets[i])
            if len(covered) > optimum:
                optimum, witness = len(covered), list(selected)
        same((ref["reference_status"], ref["optimum"], ref["optimum_selected"]),
             ("optimal", optimum, witness), "exhaustive optimum and canonical witness")
        if not value["greedy"] <= optimum <= value["upper"]:
            raise ValueError("G <= O <= U failed")


def verify_record(record, original, config):
    started = time.perf_counter()
    verify_certificate(record, original, config)
    certificate_seconds = time.perf_counter() - started
    started = time.perf_counter()
    verify_references(record)
    return {"certificate_seconds": certificate_seconds, "reference_seconds": time.perf_counter() - started,
            "peak_memory_bytes": memory_usage()}


def validate_batch(output, source):
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    check_source(source, config)
    report = {"status": "incomplete", "graphs": {}}
    write_json(output / "verification.json", report)
    with RuntimeBudget(output, config, "independent_verification") as budget:
        records = load_records(output, config)
        for row in records:
            budget.check()
            started = time.perf_counter()
            original = source_record(source, row["task"])
            source_seconds = time.perf_counter() - started
            timing = verify_record(row, original, config)
            timing["source_read_seconds"] = source_seconds
            report["graphs"][row["task"]["base_graph_id"]] = timing
            check_resources(output, config, timing["peak_memory_bytes"])
        budget.check()
        check_resources(output, config, memory_usage())
        report.update(status="passed", graph_count=len(records))
        write_json(output / "verification.json", report)
    return report


def numeric_equal(actual, wanted):
    if wanted is None:
        return actual == ""
    if isinstance(wanted, float):
        return math.isclose(float(actual), wanted, rel_tol=1e-12, abs_tol=1e-12)
    return actual == str(wanted)


def verify_summaries(output):
    """Derived consistency only; full certificate/reference checking is separate."""
    output = Path(output)
    config = validate_configuration(read_json(output / "config.json"))
    write_json(output / "summary_verification.json", {"status": "incomplete"})
    with RuntimeBudget(output, config, "derived_verification") as budget:
        records = load_records(output, config)
        expected = []
        for row in records:
            budget.check()
            t = row["task"]
            for v, ref in zip(row["values"], row["source"]["values"]):
                g, o, u, initial = v["greedy"], ref["optimum"], v["upper"], v["initial_upper"]
                expected.append({"base_graph_id": t["base_graph_id"], "n": t["n"], "d": t["d"], "k": v["k"],
                                 "greedy": g, "optimum": o, "upper": u, "initial_upper": initial,
                                 "certified_optimal": int(g == u), "initial_certified_optimal": int(g == initial),
                                 "trivial_endpoint": int(v["k"] == 1 or v["k"] == t["n"]),
                                 "tightening": initial - u, "upper_over_optimum": u / o if o else None,
                                 "relative_upper_slack": (u / o - 1) if o else None,
                                 "greedy_ratio": g / o if o else None, "certified_ratio": g / u if u else None,
                                 "relative_gap_bound": (u - g) / u if u else None})
        cells = []
        for key in sorted({(r["n"], r["d"], r["k"]) for r in expected}):
            group = [r for r in expected if (r["n"], r["d"], r["k"]) == key]
            n, d, k = key
            cell = {"n": n, "d": d, "k": k, "count": len(group),
                    "certified_optimal": sum(r["upper"] == r["greedy"] for r in group),
                    "initial_certified_optimal": sum(r["initial_upper"] == r["greedy"] for r in group),
                    "trivial_endpoint": int(k == 1 or k == n)}
            for metric in ("tightening", "upper_over_optimum", "relative_upper_slack", "greedy_ratio", "certified_ratio", "relative_gap_bound"):
                samples = sorted(r[metric] for r in group if r[metric] is not None)
                size = len(samples)
                cell[metric + "_missing"] = len(group) - size
                cell[metric + "_mean"] = math.fsum(samples) / size if size else None
                cell[metric + "_median"] = (samples[(size - 1) // 2] + samples[size // 2]) / 2 if size else None
                cell[metric + "_p90"] = samples[(9 * size + 9) // 10 - 1] if size else None
            cells.append(cell)
        for name, rows in (("budget_results.csv", expected), ("cell_summary.csv", cells)):
            with (output / name).open(encoding="utf-8", newline="") as handle:
                actual = list(csv.DictReader(handle))
            same(len(actual), len(rows), "derived row count")
            for got, wanted in zip(actual, rows):
                same(set(got), set(wanted), "derived columns")
                if not all(numeric_equal(got[key], value) for key, value in wanted.items()):
                    raise ValueError("derived numeric value or identity differs")
        result = {"status": "passed", "scope": "derived_consistency_only", "budget_rows": len(expected), "cells": len(cells)}
        check_resources(output, config, memory_usage())
        budget.check()
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
            if not args.source:
                raise ValueError("full verification requires --source")
            result = validate_batch(args.output, args.source)
        print({k: v for k, v in result.items() if k != "graphs"})
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
