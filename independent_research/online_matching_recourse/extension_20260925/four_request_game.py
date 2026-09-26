"""Exact four-request online game on an explicitly finite coordinate alphabet."""
from datetime import datetime, timezone
from functools import lru_cache
from itertools import permutations
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parent
SERVERS = (-4, -1, 2, 8)
ALPHABET = (-4, -1, 0, 2, 8)
started = time.process_time()


def single_chain(old, new):
    changed = {i for i in range(len(old)) if old[i] != new[i]}
    owners = {s: i for i, s in enumerate(old)}
    reached, dest = set(), new[-1]
    while dest in owners:
        i = owners[dest]
        if i in reached or i not in changed:
            return False
        reached.add(i)
        dest = new[i]
    return reached == changed


def solve(budget, model, known_sequence=None, alphabet=ALPHABET):
    assignments = {k: list(permutations(range(4), k)) for k in range(1, 5)}

    @lru_cache(None)
    def cost(requests, matching):
        return sum(abs(r-SERVERS[s]) for r, s in zip(requests, matching))

    @lru_cache(None)
    def optimum(requests):
        return min(cost(requests, m) for m in assignments[len(requests)])

    @lru_cache(None)
    def actions(old, counts):
        options = []
        for m in assignments[len(old)+1]:
            changed = tuple(int(a != b) for a, b in zip(old, m))
            updated = tuple(c+d for c, d in zip(counts, changed))+(0,)
            if max(updated) > budget:
                continue
            if model == 'chain' and not single_chain(old, m):
                continue
            options.append((m, updated))
        return options

    @lru_cache(None)
    def game(requests, old, counts):
        if time.process_time()-started > 180:
            raise RuntimeError('Bounded game CPU cap reached')
        possible = alphabet if known_sequence is None else (known_sequence[len(requests)],)
        branch_results = []
        for r in possible:
            now = requests+(r,)
            opt = optimum(now)
            candidates = []
            for m, updated in actions(old, counts):
                if not requests and m[0] != min(range(4), key=lambda i: (abs(r-SERVERS[i]), SERVERS[i])):
                    continue
                future = 0 if len(now) == 4 else game(now, m, updated)[0]
                value = cost(now, m)-opt+future
                candidates.append((value, sum(updated)-sum(counts), m, updated))
            chosen = min(candidates)
            branch_results.append((chosen[0], r, chosen[2], chosen[3]))
        # Nature sees past assignments but future coordinates are not revealed early.
        return max(branch_results, key=lambda item: (item[0], -item[1]))

    value = game((), (), ())[0]
    req, old, counts, witness = (), (), (), []
    for _ in range(4):
        remaining, r, m, updated = game(req, old, counts)
        req += (r,)
        witness.append(dict(request=r, assignment=[SERVERS[s] for s in m],
                            counts=list(updated), cost=cost(req, m), optimum=optimum(req),
                            worst_remaining_excess=remaining))
        old, counts = m, updated
    assert sum(s['cost']-s['optimum'] for s in witness) == value
    assert all(max(s['counts']) <= budget for s in witness)
    return dict(budget=budget, model=model, value=value, states=game.cache_info().currsize,
                witness=witness, known_future=known_sequence is not None)


def main():
    out = ROOT/'output'/('four_game_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for model in ('atomic', 'chain'):
        for budget in (1, 2, 4):
            result = solve(budget, model)
            results.append(result)
            print(model, budget, result['value'], result['states'])
    hindsight = [solve(b, 'atomic', (0, -1, 2, -4)) for b in (1, 2, 4)]
    for model in ('atomic', 'chain'):
        values = [r['value'] for r in results if r['model'] == model]
        assert values == sorted(values, reverse=True) and values[-1] == 0
    summary = dict(status='computed_pending_independent_verification', servers=SERVERS, future_alphabet=ALPHABET,
                   horizon=4, first_step='nearest, ties left', objective='sum of prefix excess distances',
                   domain='Exact finite alphabet game; no continuous-domain minimax claim.',
                   results=results, hindsight_fixed_sequence=hindsight,
                   cpu_seconds=time.process_time()-started)
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    shutil.copyfile(__file__, out/'four_request_game.py')
    print(out)


if __name__ == '__main__':
    main()
