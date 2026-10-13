"""Explicit atomic policy attaining excess 3 on (-4, -1, 2, 8)."""
import argparse
from fractions import Fraction as Q
from itertools import combinations
import json
from pathlib import Path


def require(condition, message='verification check failed'):
    """Keep scientific checks active under -O and PYTHONOPTIMIZE."""
    if not condition:
        raise AssertionError(message)

SERVERS = (-4, -1, 2, 8)


def cost(requests, assignment):
    return sum((abs(r - SERVERS[s]) for r, s in zip(requests, assignment)), Q())


def prefix_matching(requests, anchor=False):
    """Sorted matching over at most four server subsets; no future optimization."""
    active = list(range(1 if anchor else 0, len(requests)))
    active.sort(key=lambda i: (requests[i], i))
    available = [s for s in range(4) if not (anchor and s == 2)]
    choices = []
    for subset in combinations(available, len(active)):
        assignment = [2 if anchor else -1] * len(requests)
        for request, server in zip(active, subset):
            assignment[request] = server
        choices.append((cost(requests, assignment), tuple(assignment)))
    return min(choices)[1]


class FourBudgetTwo:
    """Consume one coordinate at a time; the horizon and servers are fixed."""
    def __init__(self):
        self.requests = []
        self.assignment = ()
        self.counts = []
        self.anchored = False
        self.trace = []
        self.excess = Q(0)

    def arrive(self, coordinate):
        if len(self.requests) >= 4:
            raise ValueError('exactly four arrivals are allowed')
        coordinate = Q(str(coordinate))
        if not -4 <= coordinate <= 8:
            raise ValueError('request must lie in [-4,8]')
        requests = self.requests + [coordinate]
        t = len(requests)
        if t == 1:
            assignment = (min(range(4), key=lambda s: (abs(coordinate - SERVERS[s]), s)),)
            action = 'nearest'
        elif t == 2:
            if self.assignment[0] == 3 and coordinate > requests[0]:
                assignment = (2, 3)
                self.anchored = True
                action = 'anchor_first_at_2'
            else:
                free = [s for s in range(4) if s != self.assignment[0]]
                assignment = self.assignment + (min(free, key=lambda s: (abs(coordinate - SERVERS[s]), s)),)
                action = 'preserve_first'
        else:
            assignment = prefix_matching(requests, self.anchored)
            action = 'anchored_optimum' if self.anchored else 'prefix_optimum'
        changed = [i for i, (old, new) in enumerate(zip(self.assignment, assignment)) if old != new]
        counts = [used + (i in changed) for i, used in enumerate(self.counts)] + [0]
        value = cost(requests, assignment)
        optimum = cost(requests, prefix_matching(requests))
        self.excess += value - optimum
        require(max(counts) <= 2 and self.excess <= 3)
        row = dict(arrival=t, action=action, assignment=list(assignment), counts=counts,
                   changed=changed, anchored=self.anchored, cost=str(value), optimum=str(optimum),
                   excess=str(value - optimum), cumulative_excess=str(self.excess))
        self.requests, self.assignment, self.counts = requests, assignment, counts
        self.trace.append(row)
        return row


def run(requests):
    requests = list(requests)
    if len(requests) != 4:
        raise ValueError('a complete run requires four requests')
    policy = FourBudgetTwo()
    for request in requests:
        policy.arrive(request)
    return dict(servers=list(SERVERS), requests=list(map(str, policy.requests)), horizon=4, budget=2,
                model='atomic', first_step='nearest_ties_left', trace=policy.trace,
                excess_sum=str(policy.excess), maximum_recourse=max(policy.counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='JSON containing four requests')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = run(json.loads(args.input.read_text(encoding='utf-8'))['requests'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: data[key] for key in ('excess_sum', 'maximum_recourse')}))


if __name__ == '__main__':
    main()
