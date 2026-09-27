"""Independently check a rational adaptive lower witness, without an SMT solver.

This checks SAT witnesses only.  It does not turn an UNSAT or unknown solver
record into an independently proved upper bound.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as Q
from functools import lru_cache
from itertools import permutations
import json
from pathlib import Path

SERVERS = (-4, -1, 2, 8)


def _connected_update(old, new):
    # A single augmenting path has one connected component of moving requests.
    newcomer = len(old)
    moving = {i for i, server in enumerate(old) if server != new[i]} | {newcomer}
    owner = {server: i for i, server in enumerate(old)}
    neighbours = {i: set() for i in moving}
    for i in moving:
        displaced = owner.get(new[i])
        if displaced is not None:
            if displaced not in moving:
                return False
            neighbours[i].add(displaced)
            neighbours[displaced].add(i)
    reached, pending = set(), [newcomer]
    while pending:
        current = pending.pop()
        if current not in reached:
            reached.add(current)
            pending.extend(neighbours[current] - reached)
    return reached == moving


@lru_cache(None)
def _legal(old, used, budget, model):
    result = []
    for new in permutations(range(4), len(old) + 1):
        changed = tuple(used[i] + (old[i] != new[i]) for i in range(len(old))) + (0,)
        if max(changed) <= budget and (model == 'atomic' or _connected_update(old, new)):
            result.append((new, changed))
    return tuple(result)


@lru_cache(None)
def _cost(requests, assignment):
    return sum((abs(r - SERVERS[s]) for r, s in zip(requests, assignment)), Q())


@lru_cache(None)
def _optimum(requests):
    return min(_cost(requests, p) for p in permutations(range(4), len(requests)))


def verify(data):
    assert data['status'] == 'sat', 'only SAT lower witnesses can be checked here'
    budget, model = data['budget'], data['model']
    assert type(budget) is int and budget in (1, 2)
    assert model in ('atomic', 'chain')
    relation = data.get('relation', 'gt')
    assert relation in ('gt', 'ge')
    bound = Q(data['bound'])
    witness = data['witness']
    x, y = Q(witness['x']), Q(witness['y'])
    assert all(SERVERS[0] <= q <= SERVERS[-1] for q in (x, y))
    first = min(range(4), key=lambda s: (abs(x - SERVERS[s]), SERVERS[s]))
    assert data['first_server_index'] == first, 'first assignment violates nearest/ties-left'
    expected = dict(_legal((first,), (0,), budget, model))
    provided = {tuple(row['second_assignment']): row for row in witness['third']}
    assert len(provided) == len(witness['third']) and set(provided) == set(expected), 'incomplete second-action coverage'
    branches = []
    third_count = terminal_count = 0
    requests2 = (x, y)
    for a2, used2 in expected.items():
        row = provided[a2]
        assert tuple(row['used']) == used2, 'incorrect lifetime counts'
        z = Q(row['coordinate'])
        assert SERVERS[0] <= z <= SERVERS[-1]
        requests3 = requests2 + (z,)
        e2 = _cost(requests2, a2) - _optimum(requests2)
        third_values = []
        for a3, used3 in _legal(a2, used2, budget, model):
            third_count += 1
            e3 = _cost(requests3, a3) - _optimum(requests3)
            terminal = _legal(a3, used3, budget, model)
            terminal_count += len(terminal)
            # The adversary observes a3 before selecting its last request.
            worst_last = max(
                min(_cost(requests3 + (Q(w),), a4) for a4, _ in terminal)
                - _optimum(requests3 + (Q(w),))
                for w in SERVERS
            )
            third_values.append(e2 + e3 + worst_last)
        guaranteed = min(third_values)
        assert guaranteed >= bound if relation == 'ge' else guaranteed > bound, 'lower bound is not forced'
        branches.append({'second_assignment': list(a2), 'guaranteed_excess': str(guaranteed)})
    return {'verified': True, 'scope': 'rational adaptive lower witness only',
            'guaranteed_excess': str(min(Q(row['guaranteed_excess']) for row in branches)),
            'second_actions': len(branches), 'third_actions': third_count,
            'terminal_actions': terminal_count, 'branches': branches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(json.loads(args.input.read_text(encoding='utf-8')))
    content = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding='utf-8')
    print(content)


if __name__ == '__main__':
    main()
