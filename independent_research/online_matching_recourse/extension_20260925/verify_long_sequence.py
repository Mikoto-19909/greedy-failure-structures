"""Independent exhaustive check of RM paths, resets and the residual lemma."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from itertools import permutations
from pathlib import Path


def require(condition, message='verification check failed'):
    """Keep scientific checks active under -O and PYTHONOPTIMIZE."""
    if not condition:
        raise AssertionError(message)


def _minimum(servers, requests, available):
    return min(
        sum((abs(r - servers[s]) for r, s in zip(requests, assignment)), Fraction())
        for assignment in permutations(available, len(requests))
    )


def _path_score(servers, requests, previous_auxiliary, epoch_start, path):
    value = Fraction()
    for index, (request, server) in enumerate(path):
        value += 3 * abs(requests[request] - servers[server])
        if index + 1 < len(path):
            following_request = path[index + 1][0]
            require(previous_auxiliary[following_request - epoch_start] == server)
            value -= abs(requests[following_request] - servers[server])
    return value, 2 * len(path) - 1


def _best_path_score(servers, requests, available, auxiliary, epoch_start):
    owner = {s: epoch_start + r for r, s in enumerate(auxiliary)}
    server_node = {s: len(requests) - epoch_start + i for i, s in enumerate(available)}
    scores = []

    def visit(request, seen, value, pairs, path):
        for server in available:
            if server in seen or owner.get(server) == request:
                continue
            new_value = value + 3 * abs(requests[request] - servers[server])
            new_path = path + (server_node[server],)
            if server not in owner:
                scores.append((new_value, 2 * (pairs + 1) - 1, new_path, server))
            else:
                following = owner[server]
                visit(following, seen | {server}, new_value - abs(requests[following] - servers[server]),
                      pairs + 1, new_path + (following - epoch_start,))

    visit(len(requests) - 1, set(), Fraction(), 0, (len(requests) - 1 - epoch_start,))
    best = min(scores)
    return best[:2], best[3]


def verify(data):
    """Raise on invalid/incomplete output; no producer calculation is imported."""
    servers = tuple(Fraction(s) for s in data["servers"])
    requests = tuple(Fraction(r) for r in data["requests"])
    budget = data["budget"]
    require(type(budget) is int and budget >= 0)
    require(servers and len(servers) == len(set(servers)))
    require(len(requests) <= len(servers))
    schedule = data["reset_at"]
    threshold = data.get("trigger_ratio")
    if threshold is not None:
        threshold = Fraction(threshold)
        require(threshold >= 1)
    require(all(type(t) is int and 1 <= t <= len(requests) for t in schedule))
    require(len(schedule) == len(set(schedule)) and len(schedule) <= budget)
    require(len(data["trace"]) == len(requests))
    previous = []
    used = []
    auxiliary = []
    epoch_start = 0
    available = list(range(len(servers)))
    resets = 0
    frozen_cost = Fraction()
    for time, row in enumerate(data["trace"], 1):
        current_requests = requests[:time]
        assignment = row["assignment"]
        require(len(assignment) == time and len(set(assignment)) == time)
        require(all(type(s) is int and 0 <= s < len(servers) for s in assignment))
        require(row["arrival"] == time)
        require(type(row["reset"]) is bool and row["reset"] == (time in schedule))
        best = _minimum(servers, current_requests, range(len(servers)))
        cost = sum((abs(r - servers[s]) for r, s in zip(current_requests, assignment)), Fraction())
        path_score, endpoint = _best_path_score(servers, current_requests, available, auxiliary, epoch_start)
        if threshold is not None:
            previous_cost = sum((abs(r - servers[s]) for r, s in zip(requests, previous)), Fraction())
            tentative = previous_cost + abs(current_requests[-1] - servers[endpoint])
            require(row["reset"] == (resets < budget and tentative > threshold * best))
        used = [count + (old != new) for count, old, new in zip(used, previous, assignment)] + [0]
        require(row["recourse"] == used and max(used) <= budget)
        require(Fraction(row["cost"]) == cost and Fraction(row["optimum"]) == best)
        if row["reset"]:
            require(cost == best and row["path"] == [] and row["auxiliary"] == [])
            resets += 1
            epoch_start = time
            available = [s for s in range(len(servers)) if s not in assignment]
            auxiliary = []
            frozen_cost = best
        else:
            require(assignment[:-1] == previous)
            path = row["path"]
            require(path and path[0][0] == time - 1)
            require(len({r for r, _ in path}) == len(path))
            require(len({s for _, s in path}) == len(path))
            require(all(type(r) is int and epoch_start <= r < time for r, _ in path))
            require(all(type(s) is int and s in available for _, s in path))
            require(path[-1][1] not in auxiliary)
            require(assignment[-1] == path[-1][1])
            require(_path_score(servers, current_requests, auxiliary, epoch_start, path) == path_score)
            require(assignment[-1] == endpoint)
            following_auxiliary = auxiliary + [path[0][1]]
            for r, s in path:
                following_auxiliary[r - epoch_start] = s
            require(row["auxiliary"] == following_auxiliary)
            auxiliary = following_auxiliary
            require(len(set(auxiliary)) == len(auxiliary))
            require(set(auxiliary) == set(assignment[epoch_start:]))
        require(row["epoch_start"] == epoch_start and row["resets_used"] == resets)
        require(Fraction(row["frozen_cost"]) == frozen_cost)
        residual = _minimum(servers, current_requests[epoch_start:], available)
        require(Fraction(row["residual_optimum"]) == residual)
        require(residual <= best + frozen_cost)
        require(frozen_cost <= best)
        aux_cost = sum((abs(r - servers[s]) for r, s in zip(current_requests[epoch_start:], auxiliary)), Fraction())
        require(aux_cost <= 3 * residual)
        previous = assignment
    return {"verified": True, "prefixes": len(requests), "resets": resets,
            "maximum_recourse": max(used, default=0), "independent_method": "exhaustive assignments and alternating paths"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(json.loads(args.input.read_text(encoding="utf-8")))
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
