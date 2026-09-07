"""Independently enumerate the searched prefix and check conjecture results.

Shares only schema parsing and the earlier independent set-based evaluator.
Does not import the search producer, bitset evaluator, or candidate generator.
"""
from __future__ import annotations

import argparse
from itertools import combinations, permutations, product
import json
from math import comb, factorial
from pathlib import Path

from conjecture_spec import parse_design
from validate_counterexamples import compare, recompute, require, unpack


def validate_document(document):
    compare(document["schema_version"], 1)
    design = parse_design(document["design"])
    compare(document["design"], design)
    domain, budget = design["domain"], design["search"]
    n, m, k = domain["universe_size"], domain["set_count"], domain["k"]
    limit = budget["max_combinations"]
    require(comb(m, k) <= limit, "exact reference exceeds the allowed combinations")
    sizes = range(n + 1) if domain["set_size"] is None else [domain["set_size"]]
    pool = [set(elements) for size in sizes for elements in combinations(range(n), size)]
    pool.sort(key=lambda elements: sum(2 ** e for e in elements))
    q = len(pool)
    total = ((factorial(q) // factorial(q - m) if m <= q else 0)
             if domain["unique_sets"] else q ** m)
    candidates = (permutations(range(q), m) if domain["unique_sets"]
                  else product(range(q), repeat=m))
    scanned, eligible, expected_witness = 0, 0, None
    numerator, denominator = design["claim"]["min_ratio"]
    for _ in range(min(total, budget["max_instances"])):
        indices = next(candidates)
        scanned += 1
        sets = [pool[i] for i in indices]
        frequency = [sum(e in s for s in sets) for e in range(n)]
        if domain["max_frequency"] is not None and max(frequency) > domain["max_frequency"]:
            continue
        eligible += 1
        result = recompute(n, sets, k, limit)
        if result["greedy"] * denominator < result["optimum"] * numerator:
            expected_witness = (sets, result)
            break
    status = ("counterexample_found" if expected_witness is not None else
              "domain_exhausted" if scanned == total else "budget_exhausted")
    compare(document["status"], status)
    compare(document["counts"], {"candidate_space": total, "scanned": scanned,
                                 "eligible": eligible, "rejected": scanned - eligible})
    witness = document["counterexample"]
    if expected_witness is None:
        compare(witness, None)
    else:
        require(isinstance(witness, dict), "missing counterexample")
        compare(witness["candidate_number"], scanned)
        actual_n, actual_sets, actual_k = unpack(witness["instance"])
        require((actual_n, actual_sets, actual_k) == (n, expected_witness[0], k),
                "counterexample is not the first violation in the specified domain")
        compare(witness["evaluation"], expected_witness[1])
    return document["status"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="search.json")
    args = parser.parse_args(argv)
    try:
        status = validate_document(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        parser.exit(2, f"invalid conjecture search: {error}\n")
    print(f"Verified: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
