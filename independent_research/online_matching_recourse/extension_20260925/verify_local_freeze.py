"""Independent global-injection audit of a small local-freeze trajectory."""
from fractions import Fraction as Q
from itertools import permutations
import argparse
import json
from pathlib import Path

from verify_long_sequence import verify as verify_router


def cost(servers, requests, assignment):
    return sum((abs(r - servers[s]) for r, s in zip(requests, assignment)), Q())


def verify(data):
    servers = tuple(map(Q, data['servers']))
    requests = tuple(map(Q, data['requests']))
    budget, size = data['budget'], data['block_size']
    assert type(budget) is int and budget >= 0
    assert type(size) is int and 1 <= size <= 4
    assert servers and len(servers) == len(set(servers)) and len(requests) <= len(servers)
    order = sorted(range(len(servers)), key=lambda i: (servers[i], i))
    blocks = [order[i:i + size] for i in range(0, len(order), size)]
    assert data['blocks'] == blocks
    assert data['shadow']['servers'] == data['servers'] and data['shadow']['requests'] == data['requests']
    assert data['shadow']['budget'] == 0
    verify_router(data['shadow'])
    assert len(data['trace']) == len(requests), 'incomplete trajectory'
    owner = {server: b for b, block in enumerate(blocks) for server in block}
    admitted, old, counts = [], (), []
    max_loss = Q(0)
    for t, (row, route) in enumerate(zip(data['trace'], data['shadow']['trace']), 1):
        block_id = owner[route['assignment'][-1]]
        admitted.append(block_id)
        assert row['arrival'] == t and row['block'] == block_id
        current = tuple(row['assignment'])
        assert len(current) == t and len(set(current)) == t
        assert all(type(s) is int and 0 <= s < len(servers) for s in current)
        candidates = []
        best = None
        for assignment in permutations(range(len(servers)), t):
            value = cost(servers, requests[:t], assignment)
            best = value if best is None else min(best, value)
            if any(owner[s] != admitted[i] for i, s in enumerate(assignment)):
                continue
            changed = [i for i, s in enumerate(assignment[:-1]) if old[i] != s]
            if any(admitted[i] != block_id or counts[i] == budget for i in changed):
                continue
            candidates.append((value, len(changed), assignment))
        assert (Q(row['cost']), len(row['moved']), current) == min(candidates), 'not the budget-feasible minimum'
        changed = [i for i, s in enumerate(current[:-1]) if old[i] != s]
        assert row['moved'] == changed
        counts = [c + (i in changed) for i, c in enumerate(counts)] + [0]
        assert row['counts'] == counts and max(counts) <= budget
        assert row['frozen'] == [i for i, c in enumerate(counts) if c == budget]
        assert Q(row['cost']) == cost(servers, requests[:t], current)
        assert Q(row['optimum']) == best
        assert Q(row['shadow_cost']) == Q(route['cost'])
        relaxed = Q(0)
        for b, block in enumerate(blocks):
            members = [i for i, assignment_block in enumerate(admitted) if assignment_block == b]
            local_requests = tuple(requests[i] for i in members)
            local_best = min(cost(servers, local_requests, p) for p in permutations(block, len(members)))
            relaxed += local_best
            if b == block_id:
                assert Q(row['block_optimum']) == local_best
                assert Q(row['block_cost']) == cost(servers, local_requests, tuple(current[i] for i in members))
        assert Q(row['block_optimum_sum']) == relaxed
        alpha = 2 ** max(1, size - budget) - 1
        assert Q(row['cost']) <= alpha * relaxed <= alpha * Q(route['cost'])
        if size <= budget + 1:
            assert Q(row['cost']) == relaxed <= Q(route['cost'])
        max_loss = max(max_loss, Q(row['cost']) - relaxed)
        old = current
    return dict(verified=True, prefixes=len(requests), maximum_recourse=max(counts, default=0),
                maximum_frozen_loss=str(max_loss), method='global injections; independent RM path enumeration')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.input.read_text(encoding='utf-8')))))


if __name__ == '__main__':
    main()
