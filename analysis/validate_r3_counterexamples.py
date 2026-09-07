"""Independently verify R3 example searches using sets and 2x2 membership patterns."""
from __future__ import annotations

import argparse
from collections import Counter, deque
from itertools import combinations
import json
from pathlib import Path

from validate_counterexamples import compare, coverage, integer, recompute, require, unpack


def metrics(n, sets, k, limit):
    require(n <= 64 and len(sets) <= 32, "input exceeds the R3 example size limit")
    sizes = [len(s) for s in sets]
    require(len(set(sizes)) == 1, "equal-sized sets are required for the first-step event")
    result = recompute(n, sets, k, limit)
    require(result["status"] == "exact", "incomplete optimum reference")
    forced, witness = -1, None
    # Enumerate the full candidate space and restrict it independently to selections containing 0.
    for choice in combinations(range(len(sets)), k):
        if 0 in choice:
            value = coverage(sets, choice)
            if value > forced:
                forced, witness = value, list(choice)
    frequencies = [sum(a in s for s in sets) for a in range(n)]
    e0 = sum(frequencies[a] - 1 for a in sets[0])
    require(e0 == sum(len(sets[0] & s) for s in sets[1:]), "E0 double count differs")
    histogram = Counter(len(sets[i] & sets[j]) for i, j in combinations(range(len(sets)), 2))
    global_total = sum(f * (f - 1) // 2 for f in frequencies)
    first_loss = forced < result["optimum"]
    final_loss = result["greedy"] < result["optimum"]
    require(not first_loss or final_loss, "first-step loss must imply final failure")
    return {**result, "forced_optimum": forced, "forced_selected": witness,
            "first_step_irrecoverable": first_loss, "final_failure": final_loss,
            "late_failure": final_loss and not first_loss, "e0": e0,
            "row_degrees": sizes, "element_frequencies": frequencies,
            "global_intersection_total": global_total,
            "intersection_profile": [list(pair) for pair in sorted(histogram.items())],
            "unique_set_count": len({frozenset(s) for s in sets})}


def neighbors(n, sets):
    for i, j in combinations(range(len(sets)), 2):
        moves = []
        for a, b in combinations(range(n), 2):
            pattern = (a in sets[i], b in sets[i], a in sets[j], b in sets[j])
            if pattern == (True, False, False, True):
                moves.append([i, j, a, b])
            elif pattern == (False, True, True, False):
                moves.append([i, j, b, a])
        for move in sorted(moves):
            _, _, a, b = move
            result = [s.copy() for s in sets]
            result[i].remove(a)
            result[i].add(b)
            result[j].remove(b)
            result[j].add(a)
            yield move, result


def qualifies(original, candidate, settings):
    if original["first_step_irrecoverable"] == candidate["first_step_irrecoverable"]:
        return False
    if settings["same_optimum"] and original["optimum"] != candidate["optimum"]:
        return False
    if settings["target"] == "first-step-flip":
        return True
    if settings["target"] == "same-e0-flip":
        return original["e0"] == candidate["e0"]
    lower, higher = sorted((original, candidate), key=lambda value: value["e0"])
    return (lower["e0"] < higher["e0"] and lower["first_step_irrecoverable"]
            and not higher["first_step_irrecoverable"])


def validate_document(document):
    compare(document["schema_version"], 1)
    compare(document["purpose"], "r3_counterexample_exploration")
    settings = document["settings"]
    require(set(settings) == {"target", "same_optimum", "max_states", "max_switches", "max_combinations"},
            "incorrect search settings")
    require(settings["target"] in ("same-e0-flip", "lower-e0-worse", "first-step-flip"), "unknown target")
    require(type(settings["same_optimum"]) is bool, "same_optimum must be a boolean")
    max_states = integer(settings["max_states"], 1)
    max_switches = integer(settings["max_switches"])
    limit = integer(settings["max_combinations"], 1)
    n, sets, k = unpack(document["original"]["instance"])
    original = metrics(n, sets, k, limit)
    compare(document["original"]["evaluation"], original)
    key = lambda groups: tuple(tuple(sorted(s)) for s in groups)
    seen = {key(sets)}
    nodes = [(sets, [])]
    queue = deque([0])
    attempted, found = 0, None
    status = "component_exhausted"
    stop = False
    while queue and not stop:
        groups, path = nodes[queue.popleft()]
        for operation, candidate in neighbors(n, groups):
            if attempted >= max_switches:
                status, stop = "switch_budget_exhausted", True
                break
            attempted += 1
            identity = key(candidate)
            if identity in seen:
                continue
            if len(nodes) >= max_states:
                status, stop = "state_budget_exhausted", True
                break
            result = metrics(n, candidate, k, limit)
            compare(result["row_degrees"], original["row_degrees"])
            compare(result["element_frequencies"], original["element_frequencies"])
            compare(result["global_intersection_total"], original["global_intersection_total"])
            seen.add(identity)
            candidate_path = [*path, operation]
            nodes.append((candidate, candidate_path))
            if qualifies(original, result, settings):
                found = (candidate, candidate_path, result)
                status, stop = "pair_found", True
                break
            queue.append(len(nodes) - 1)
    compare(document["status"], status)
    compare(document["counts"], {"states": len(nodes), "switches": attempted})
    if found is None:
        compare(document["pair"], None)
    else:
        require(isinstance(document["pair"], dict), "missing paired witness")
        other_n, other_sets, other_k = unpack(document["pair"]["instance"])
        require((other_n, other_sets, other_k) == (n, found[0], k), "endpoint differs from the first matched state")
        compare(document["pair"]["switches"], found[1])
        compare(document["pair"]["evaluation"], found[2])
    return document["status"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="pair.json")
    args = parser.parse_args(argv)
    try:
        status = validate_document(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        parser.exit(2, f"invalid R3 counterexample search: {error}\n")
    print(f"Verified: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
