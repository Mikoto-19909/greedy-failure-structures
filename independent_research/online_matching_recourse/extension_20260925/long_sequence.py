"""RM matching with at most b atomic resets; exact rational reference code."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path
from typing import Any


def matching_cost(servers, requests, assignment):
    return sum((abs(r - servers[s]) for r, s in zip(requests, assignment)), Fraction())


def optimum(servers, requests):
    """Sorted line matching, allowing unused servers; return original indices."""
    order = sorted(range(len(requests)), key=lambda i: (requests[i], i))
    server_order = sorted(range(len(servers)), key=lambda i: (servers[i], i))
    states = {0: (Fraction(), ())}
    for server in server_order:
        following = dict(states)
        for count, (value, chosen) in states.items():
            if count == len(requests):
                continue
            candidate = (value + abs(requests[order[count]] - servers[server]), chosen + (server,))
            if count + 1 not in following or candidate < following[count + 1]:
                following[count + 1] = candidate
        states = following
    value, chosen = states[len(requests)]
    assignment = [0] * len(requests)
    for request, server in zip(order, chosen):
        assignment[request] = server
    return value, assignment


def rm_path(servers, requests, auxiliary):
    """Minimum 3-net-cost path; ties use edge count then vertex IDs."""
    count = len(requests)
    vertices = count + len(servers)
    edges = []
    for request, coordinate in enumerate(requests):
        for server, location in enumerate(servers):
            if request < len(auxiliary) and auxiliary[request] == server:
                edges.append((count + server, request, -abs(coordinate - location)))
            else:
                edges.append((request, count + server, 3 * abs(coordinate - location)))
    labels = {count - 1: (Fraction(), 0, (count - 1,))}
    for _ in range(vertices - 1):
        following = dict(labels)
        for source, target, weight in edges:
            if source not in labels:
                continue
            value, length, path = labels[source]
            candidate = (value + weight, length + 1, path + (target,))
            if target not in following or candidate < following[target]:
                following[target] = candidate
        if following == labels:
            break
        labels = following
    occupied = set(auxiliary)
    best = min(labels[count + s] for s in range(len(servers)) if s not in occupied)
    path = best[2]
    if len(path) != len(set(path)):
        raise AssertionError("minimum path contains a cycle")
    return [(path[i], path[i + 1] - count) for i in range(0, len(path), 2)]


class RestartMatcher:
    """Call arrive using only the new coordinate and an online reset decision."""

    def __init__(self, servers, budget):
        if type(budget) is not int or budget < 0:
            raise ValueError("budget must be a nonnegative integer")
        self.servers = tuple(Fraction(str(s)) for s in servers)
        if not self.servers or len(set(self.servers)) != len(self.servers):
            raise ValueError("servers must be nonempty and distinct")
        self.budget = budget
        self.resets = 0
        self.requests: list[Fraction] = []
        self.assignment: list[int] = []
        self.recourse: list[int] = []
        self.epoch_start = 0
        self.epoch_servers = list(range(len(self.servers)))
        self.auxiliary: list[int] = []

    def wants_reset(self, request, threshold=2):
        """Plan an assignment without executing it; never inspect later arrivals."""
        if self.resets == self.budget:
            return False
        if len(self.requests) == len(self.servers):
            raise ValueError("more requests than servers")
        coordinate = Fraction(str(request))
        local_servers = [self.servers[s] for s in self.epoch_servers]
        path = rm_path(local_servers, self.requests[self.epoch_start :] + [coordinate], self.auxiliary)
        tentative = matching_cost(self.servers, self.requests, self.assignment) + abs(coordinate - local_servers[path[-1][1]])
        best, _ = optimum(self.servers, self.requests + [coordinate])
        return tentative > Fraction(str(threshold)) * best

    def arrive(self, request, *, reset=False):
        if len(self.requests) == len(self.servers):
            raise ValueError("more requests than servers")
        if reset and self.resets == self.budget:
            raise ValueError("reset budget exhausted")
        coordinate = Fraction(str(request))
        previous = list(self.assignment)
        self.requests.append(coordinate)
        path = []
        if reset:
            _, self.assignment = optimum(self.servers, self.requests)
            self.resets += 1
            self.epoch_start = len(self.requests)
            occupied = set(self.assignment)
            self.epoch_servers = [s for s in range(len(self.servers)) if s not in occupied]
            self.auxiliary = []
        else:
            local_servers = [self.servers[s] for s in self.epoch_servers]
            local_requests = self.requests[self.epoch_start :]
            path = rm_path(local_servers, local_requests, self.auxiliary)
            self.auxiliary.append(path[0][1])
            for r, s in path:
                self.auxiliary[r] = s
            self.assignment.append(self.epoch_servers[path[-1][1]])
        self.recourse = [used + (old != new) for used, old, new in zip(self.recourse, previous, self.assignment)] + [0]
        best, _ = optimum(self.servers, self.requests)
        residual_best, _ = optimum(
            [self.servers[s] for s in self.epoch_servers], self.requests[self.epoch_start :]
        )
        return {
            "arrival": len(self.requests), "reset": reset, "resets_used": self.resets,
            "assignment": list(self.assignment), "recourse": list(self.recourse),
            "cost": str(matching_cost(self.servers, self.requests, self.assignment)),
            "optimum": str(best), "epoch_start": self.epoch_start,
            "frozen_cost": str(matching_cost(self.servers, self.requests[: self.epoch_start], self.assignment[: self.epoch_start])),
            "residual_optimum": str(residual_best),
            "auxiliary": [self.epoch_servers[s] for s in self.auxiliary],
            "path": [[r + self.epoch_start, self.epoch_servers[s]] for r, s in path],
        }


def run(servers, requests, budget, reset_at=(), trigger_ratio=None):
    reset_at = tuple(reset_at)
    if any(type(t) is not int or t < 1 or t > len(requests) for t in reset_at):
        raise ValueError("reset times must be valid arrival indices")
    if len(set(reset_at)) != len(reset_at) or len(reset_at) > budget:
        raise ValueError("reset schedule exceeds budget or contains duplicates")
    if trigger_ratio is not None:
        trigger_ratio = Fraction(str(trigger_ratio))
        if reset_at or trigger_ratio < 1:
            raise ValueError("online threshold must be at least one and cannot accompany a fixed schedule")
    algorithm = RestartMatcher(servers, budget)
    trace = []
    for i, request in enumerate(requests, 1):
        reset = i in reset_at if trigger_ratio is None else algorithm.wants_reset(request, trigger_ratio)
        trace.append(algorithm.arrive(request, reset=reset))
    actual_resets = [row["arrival"] for row in trace if row["reset"]]
    return {"servers": [str(s) for s in algorithm.servers], "requests": [str(r) for r in algorithm.requests],
            "budget": budget, "reset_at": actual_resets,
            "trigger_ratio": None if trigger_ratio is None else str(trigger_ratio), "trace": trace}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON with servers, requests, budget, reset_at")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data: dict[str, Any] = json.loads(args.input.read_text(encoding="utf-8"))
    result = run(data["servers"], data["requests"], data["budget"], data.get("reset_at", []), data.get("trigger_ratio"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"arrivals": len(result["trace"]), "resets": len(result["reset_at"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
