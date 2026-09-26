"""Small policies; integer distances, deterministic ties, no future requests."""
from itertools import permutations
from fractions import Fraction


def cost(servers, requests, assignment):
    return sum(abs(r - servers[s]) for r, s in zip(requests, assignment))


def exact_prefix(servers, requests):
    """Value-only order-preserving dynamic program."""
    dp = [0] * (len(servers) + 1)
    for r in sorted(requests):
        nxt = [float('inf')] * (len(servers) + 1)
        for j, s in enumerate(sorted(servers), 1):
            nxt[j] = min(nxt[j-1], dp[j-1] + abs(r-s))
        dp = nxt
    return dp[-1]


def choose(servers, requests, old, counts, policy, budget):
    free = [s for s in range(len(servers)) if s not in old]
    nearest = min(free, key=lambda s: (abs(requests[-1]-servers[s]), servers[s], s))
    base = old + [nearest]
    if policy == 'nearest':
        return base, []
    limit = 1 if policy == 'single' else len(old)
    eligible = [i for i in range(len(old)) if counts[i] < budget]
    best, moves = base, []
    base_cost = cost(servers, requests, base)
    best_key = (base_cost, base_cost, 0, tuple(base))
    for size in range(1, min(limit, len(eligible)) + 1):
        for path in permutations(eligible, size):
            for endpoint in free:
                candidate = old + [old[path[0]]]
                for k, i in enumerate(path):
                    candidate[i] = old[path[k+1]] if k+1 < size else endpoint
                candidate_cost = cost(servers, requests, candidate)
                price = 0
                if policy == 'priced_chain':
                    price = sum(Fraction(abs(servers[candidate[i]]-servers[old[i]]),
                                         2 * (budget-counts[i])) for i in path)
                key = (candidate_cost + price, candidate_cost, size, tuple(candidate))
                if key < best_key:
                    best, moves, best_key = candidate, list(reversed(path)), key
    return best, moves


def simulate(servers, requests, policy, budget):
    old, counts, history = [], [], []
    for t in range(1, len(requests)+1):
        assignment, moves = choose(servers, requests[:t], old, counts, policy, budget)
        for i in moves:
            counts[i] += 1
        counts.append(0)
        history.append(dict(t=t, assignment=assignment, moves=moves,
                            counts=list(counts), cost=cost(servers, requests[:t], assignment)))
        old = assignment
    return history
