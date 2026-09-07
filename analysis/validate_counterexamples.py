"""Independently recompute mined counterexamples using Python sets.

Shares only the project's instance parser. Does not import the miner, algorithms,
their coverage helpers, or the shrinker's neighbor construction.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from itertools import combinations
import json
from math import comb
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover.reproducibility import instance_from_payload


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "invalid integer or budget")
    return value


def compare(actual, expected):
    require(type(actual) is type(expected), "incorrect result type")
    if isinstance(expected, dict):
        require(actual.keys() == expected.keys(), "incorrect result fields")
        for key in expected:
            compare(actual[key], expected[key])
    elif isinstance(expected, list):
        require(len(actual) == len(expected), "incorrect result length")
        for a, e in zip(actual, expected):
            compare(a, e)
    else:
        require(actual == expected, f"incorrect value: {actual!r} != {expected!r}")


def unpack(payload):
    integer(payload["k"], 1)
    instance_from_payload(payload)  # Shared input validation, no numerical evaluation.
    require(payload["encoding"] == "elements", "expected normalized element lists")
    sets = [set(group) for group in payload["sets"]]
    require(all(group == sorted(s) for group, s in zip(payload["sets"], sets)),
            "expected sorted distinct elements")
    return payload["universe_size"], sets, payload["k"]


def coverage(sets, indices):
    return len(set().union(*(sets[i] for i in indices)))


def recompute(n, sets, k, limit):
    count = comb(len(sets), k)
    if count > limit:
        return {"status": "combination_limit", "combinations": count}
    chosen, trace, covered = [], [], set()
    for step in range(k):
        candidates = [(len(s - covered), i) for i, s in enumerate(sets) if i not in chosen]
        gain = max(value for value, _ in candidates)
        ties = [i for value, i in candidates if value == gain]
        i = ties[0]
        chosen.append(i)
        covered.update(sets[i])
        trace.append({"step": step + 1, "selected": i, "gain": gain,
                      "ties": ties, "coverage": len(covered)})
    optimum, witness = -1, None
    for indices in combinations(range(len(sets)), k):
        value = coverage(sets, indices)
        if value > optimum:
            optimum, witness = value, list(indices)
    return {"status": "exact", "combinations": count, "greedy": len(covered),
            "optimum": optimum, "greedy_selected": chosen, "optimum_selected": witness,
            "trace": trace, "gap": (optimum - len(covered)) / optimum if optimum else None}


def operations(n, sets, k):
    if len(sets) > k:
        for i in range(len(sets)):
            yield {"kind": "set", "index": i}
    if n > 1:
        for e in range(n):
            yield {"kind": "element", "index": e}
    for i, s in enumerate(sets):
        for e in sorted(s):
            yield {"kind": "membership", "set": i, "element": e}


def apply_operation(n, sets, k, operation):
    kind = operation.get("kind")
    result = [s.copy() for s in sets]
    if kind == "set":
        i = integer(operation["index"])
        require(set(operation) == {"kind", "index"} and len(sets) > k and i < len(sets),
                "invalid set deletion")
        result.pop(i)
    elif kind == "element":
        e = integer(operation["index"])
        require(set(operation) == {"kind", "index"} and n > 1 and e < n, "invalid element deletion")
        result = [{x if x < e else x - 1 for x in s if x != e} for s in sets]
        n -= 1
    elif kind == "membership":
        i, e = integer(operation["set"]), integer(operation["element"])
        require(set(operation) == {"kind", "set", "element"} and i < len(sets)
                and e in sets[i], "invalid membership deletion")
        result[i].remove(e)
    else:
        raise ValueError("unknown deletion")
    return n, result, k


def validate_document(document):
    compare(document["schema_version"], 1)
    settings = document["settings"]
    top = integer(settings["top"], 1)
    limit = integer(settings["max_combinations"], 1)
    budget = integer(settings["max_evaluations"])
    entries = document["inputs"]
    require(isinstance(entries, list) and bool(entries), "missing inputs")
    failures, exact = [], 0
    for index, entry in enumerate(entries):
        result = recompute(*unpack(entry["instance"]), limit)
        compare(entry["evaluation"], result)
        if result["status"] == "exact":
            exact += 1
            if result["greedy"] < result["optimum"]:
                failures.append(index)
    failures.sort(key=lambda i: (
        -Fraction(entries[i]["evaluation"]["optimum"] - entries[i]["evaluation"]["greedy"],
                  entries[i]["evaluation"]["optimum"]),
        (len(entries[i]["instance"]["sets"]), entries[i]["instance"]["universe_size"],
         sum(len(s) for s in entries[i]["instance"]["sets"])), i))
    compare([item["input_index"] for item in document["selected"]], failures[:top])
    compare(document["counts"], {"input": len(entries), "exact": exact,
                                 "failures": len(failures), "selected": min(top, len(failures))})
    for item in document["selected"]:
        n, sets, k = unpack(entries[item["input_index"]]["instance"])
        attempts = integer(item["evaluations"])
        require(attempts <= budget, "reduction exceeds budget")
        previous = 0
        for step in item["steps"]:
            number = integer(step["evaluation_number"], 1)
            require(previous < number <= attempts, "invalid deletion evaluation sequence")
            previous = number
            n, sets, k = apply_operation(n, sets, k, step["operation"])
            result = recompute(n, sets, k, limit)
            require(result["status"] == "exact" and result["greedy"] < result["optimum"],
                    "deletion does not preserve a verified failure")
        final_n, final_sets, final_k = unpack(item["instance"])
        require((final_n, final_sets, final_k) == (n, sets, k), "saved instance differs from deletion replay")
        result = recompute(n, sets, k, limit)
        compare(item["evaluation"], result)
        require(result["status"] == "exact" and result["greedy"] < result["optimum"],
                "output is not a counterexample")
        if item["status"] == "budget_exhausted":
            require(attempts == budget, "inconsistent exhausted budget")
        elif item["status"] == "deletion_minimal":
            for operation in operations(n, sets, k):
                neighbor = apply_operation(n, sets, k, operation)
                evaluation = recompute(*neighbor, limit)
                require(evaluation["status"] == "exact"
                        and evaluation["greedy"] == evaluation["optimum"],
                        "false deletion-minimal claim")
        else:
            raise ValueError("unknown reduction status")
    return document["counts"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="counterexamples.json")
    args = parser.parse_args(argv)
    try:
        counts = validate_document(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        parser.exit(2, f"invalid counterexamples: {error}\n")
    print(f"Verified: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
