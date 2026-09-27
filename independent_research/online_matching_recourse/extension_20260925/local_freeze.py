"""Route with zero-recourse RM, then repair a bounded block atomically."""
from __future__ import annotations

import argparse
from fractions import Fraction as Q
from itertools import permutations
import json
from pathlib import Path

from long_sequence import RestartMatcher


class LocalMatcher:
    def __init__(self, servers, budget, block_size=None):
        if type(budget) is not int or budget < 0:
            raise ValueError('budget must be a nonnegative integer')
        self.router = RestartMatcher(servers, 0)
        self.servers = self.router.servers
        self.budget = budget
        self.block_size = min(4, budget + 1) if block_size is None else block_size
        if type(self.block_size) is not int or not 1 <= self.block_size <= 4:
            raise ValueError('block size must be between one and four')
        order = sorted(range(len(self.servers)), key=lambda i: (self.servers[i], i))
        self.blocks = [order[i:i + self.block_size] for i in range(0, len(order), self.block_size)]
        self.block_for = {s: b for b, block in enumerate(self.blocks) for s in block}
        self.requests = []
        self.admissions = []
        self.assignment = []
        self.counts = []
        self.block_optima = [Q(0)] * len(self.blocks)
        self.history = []
        self.router_history = []

    def arrive(self, request):
        route = self.router.arrive(request)
        coordinate = Q(str(request))
        block_id = self.block_for[route['assignment'][-1]]
        self.requests.append(coordinate)
        self.admissions.append(block_id)
        members = [i for i, b in enumerate(self.admissions) if b == block_id]
        block = self.blocks[block_id]
        choices = []
        unconstrained = []
        for assignment in permutations(block, len(members)):
            value = sum((abs(self.requests[i] - self.servers[s]) for i, s in zip(members, assignment)), Q())
            unconstrained.append(value)
            moved = [i for i, s in zip(members[:-1], assignment[:-1]) if self.assignment[i] != s]
            if any(self.counts[i] >= self.budget for i in moved):
                continue
            choices.append((value, len(moved), assignment, moved))
        block_cost, _, chosen, moved = min(choices)
        self.assignment.append(-1)
        self.counts.append(0)
        for i, s in zip(members, chosen):
            self.assignment[i] = s
        for i in moved:
            self.counts[i] += 1
        self.block_optima[block_id] = min(unconstrained)
        value = sum((abs(r - self.servers[s]) for r, s in zip(self.requests, self.assignment)), Q())
        row = dict(arrival=len(self.requests), block=block_id, assignment=list(self.assignment),
                   counts=list(self.counts), moved=moved,
                   frozen=[i for i, count in enumerate(self.counts) if count == self.budget],
                   cost=str(value), optimum=route['optimum'], shadow_cost=route['cost'],
                   block_cost=str(block_cost), block_optimum=str(self.block_optima[block_id]),
                   block_optimum_sum=str(sum(self.block_optima)))
        self.history.append(row)
        self.router_history.append(route)
        return row

    def result(self):
        servers, requests = [str(s) for s in self.servers], [str(r) for r in self.requests]
        shadow = dict(servers=servers, requests=requests, budget=0, reset_at=[], trigger_ratio=None,
                      trace=self.router_history)
        return dict(servers=servers, requests=requests, budget=self.budget, block_size=self.block_size,
                    blocks=self.blocks, trace=self.history, shadow=shadow)


def run(servers, requests, budget, block_size=None):
    matcher = LocalMatcher(servers, budget, block_size)
    for request in requests:
        matcher.arrive(request)
    return matcher.result()


def metrics(data):
    rows = data['trace']
    counts_key = 'counts' if 'blocks' in data else 'recourse'
    ratios = [Q(row['cost']) / Q(row['optimum']) if Q(row['optimum']) else Q(1) for row in rows]
    final = rows[-1][counts_key] if rows else []
    previous = []
    events = 0
    for row in rows:
        current = row['assignment']
        events += current[:-1] != previous
        previous = current
    return dict(prefix_sum=str(sum((Q(row['cost']) for row in rows), Q())),
                excess_sum=str(sum((Q(row['cost']) - Q(row['optimum']) for row in rows), Q())),
                max_ratio=str(max(ratios, default=Q(1))), total_recourse=sum(final),
                maximum_recourse=max(final, default=0), repair_arrivals=events)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--block-size', type=int)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    result = run(data['servers'], data['requests'], data['budget'], args.block_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(metrics(result)))


if __name__ == '__main__':
    main()
