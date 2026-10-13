"""Independent four-arrival game check: canonical request states and reverse chains.

Does not import four_request_game.py. The exact optimum uses sorted requests and
server subsets, independently of the production permutation oracle.
"""
from functools import lru_cache
from itertools import combinations, permutations
from pathlib import Path
import hashlib
import json
import sys
import time

SERVERS = (-4, -1, 2, 8)
ALPHABET = (-4, -1, 0, 2, 8)
HINDSIGHT_SEQUENCE = (0, -1, 2, -4)


def require(condition, message='verification check failed'):
    """Keep scientific checks active under -O and PYTHONOPTIMIZE."""
    if not condition:
        raise AssertionError(message)


def require_configurations(rows, expected):
    identities = [(row['model'], row['budget'], row['known_future']) for row in rows]
    require(all(type(row['budget']) is int and type(row['known_future']) is bool for row in rows), 'invalid configuration identity')
    require(len(set(identities)) == len(identities), 'duplicate game configuration')
    require(set(identities) == expected, 'incomplete or extra game configuration')


def verify_rounding(summary):
    """Check the saved rounding bound independently of its report producer."""
    require(tuple(summary['servers']) == (-4, -1, 2, 8))
    require(tuple(summary['future_alphabet']) == tuple(range(-4, 9)))
    require(summary['horizon'] == 4)
    rounding = summary['rounding']
    require(rounding['first_coordinate_error_at_most'] == 1)
    require(rounding['later_coordinate_error_at_most'] == 0.5)
    require(rounding['preserve_first_nearest_server'] is True)
    certificate = 2 * (3 * 1 + sum(range(1, 4)) * 0.5)
    require(rounding['additive_certificate'] == certificate)
    lower = {(row['model'], row['budget']): row['value'] for row in summary['results']}
    intervals = {(row['model'], row['budget']): row for row in summary['continuous_intervals']}
    expected = {(model, budget) for model in ('atomic', 'chain') for budget in (1, 2)}
    require(len(summary['results']) == len(summary['continuous_intervals']) == len(expected))
    require(set(lower) == set(intervals) == expected)
    for key, value in lower.items():
        require(intervals[key]['lower'] == value)
        require(intervals[key]['upper'] == value + certificate)
    require(summary['budget4_continuous_value'] == 0)
    require_configurations(summary['results'], {(model, budget, False) for model in ('atomic', 'chain') for budget in (1, 2)})
    require_configurations(summary['hindsight_fixed_sequence'], set())


def verify(source, cpu_limit=120):
    started = time.process_time()
    summary = json.loads(source.read_text(encoding="utf-8"))
    servers = tuple(summary["servers"])
    alphabet = tuple(summary["future_alphabet"])
    horizon = summary["horizon"]
    require(horizon == len(servers) == 4)
    require(servers == SERVERS)
    require(alphabet, 'empty request alphabet')
    require(summary['results'] or summary['hindsight_fixed_sequence'], 'empty game comparison')
    if 'rounding' in summary or 'continuous_intervals' in summary:
        verify_rounding(summary)
    else:
        require(alphabet == ALPHABET, 'incorrect finite request alphabet')
        require_configurations(summary['results'], {(model, budget, False) for model in ('atomic', 'chain') for budget in (1, 2, 4)})
        require_configurations(summary['hindsight_fixed_sequence'], {('atomic', budget, True) for budget in (1, 2, 4)})
        for reference in summary['hindsight_fixed_sequence']:
            require(tuple(row['request'] for row in reference['witness']) == HINDSIGHT_SEQUENCE, 'incorrect hindsight sequence')

    @lru_cache(None)
    def optimum(requests_sorted):
        return min(sum(abs(x-s) for x, s in zip(requests_sorted, selected))
                   for selected in combinations(servers, len(requests_sorted)))

    def cost(state):
        return sum(abs(x-servers[s]) for x, s, _ in state)

    verified = []
    for reference in summary["results"] + summary["hindsight_fixed_sequence"]:
        require(len(reference["witness"]) == horizon, "incomplete witness")
        budget, model = reference["budget"], reference["model"]
        fixed = tuple(row["request"] for row in reference["witness"]) if reference["known_future"] else None

        def successors(state, request):
            if not state:
                nearest = min(range(4), key=lambda j: (abs(request-servers[j]), j))
                return (((request, nearest, 0),),)
            result = set()
            if model == "atomic":
                for assigned in permutations(range(4), len(state)+1):
                    old = tuple((x, assigned[i], used+int(s != assigned[i]))
                                for i, (x, s, used) in enumerate(state))
                    if all(used <= budget for _, _, used in old):
                        result.add(old+((request, assigned[-1], 0),))
            else:
                require(model == "chain")
                used_servers = {s for _, s, _ in state}

                def grow(free, current, moved):
                    # Stop the chain by inserting the newly arrived request.
                    result.add(current+((request, free, 0),))
                    for i, (x, old_server, used) in enumerate(current):
                        if i in moved or used == budget:
                            continue
                        changed = current[:i]+((x, free, used+1),)+current[i+1:]
                        grow(old_server, changed, moved | {i})

                for free in set(range(4))-used_servers:
                    grow(free, state, frozenset())
            require(result)
            return tuple(sorted(result))

        def objective(child, reference_cost):
            future = 0 if len(child) == horizon else value(tuple(sorted(child)))
            return cost(child)-reference_cost+future

        @lru_cache(None)
        def value(state):
            if time.process_time()-started > cpu_limit:
                raise RuntimeError(f"Independent verification exceeded {cpu_limit} CPU seconds")
            if len(state) == horizon:
                return 0
            candidates = alphabet if fixed is None else (fixed[len(state)],)
            worst = 0
            for request in candidates:
                prefix = tuple(sorted([x for x, _, _ in state]+[request]))
                reference_cost = optimum(prefix)
                best = min(objective(child, reference_cost)
                           for child in successors(state, request))
                worst = max(worst, best)
            return worst

        computed = value(())
        require(computed == reference["value"], (model, budget, computed, reference["value"]))
        current, requests, assigned, counts = (), [], [], []
        witness_excess = 0
        for row in reference["witness"]:
            require(row["worst_remaining_excess"] == value(current))
            request = row["request"]
            # Nature selects the smallest coordinate among worst branches.
            possible = alphabet if fixed is None else (fixed[len(requests)],)
            branches = []
            for candidate_request in possible:
                reference_cost = optimum(tuple(sorted(requests+[candidate_request])))
                best = min(objective(child, reference_cost) for child in successors(current, candidate_request))
                branches.append((best, candidate_request))
            require(request == max(branches, key=lambda item: (item[0], -item[1]))[1], 'nondeterministic request tie')
            ordered_state = tuple(zip(requests, assigned, counts))
            requests.append(request)
            next_assigned = [servers.index(s) for s in row["assignment"]]
            require(len(set(next_assigned)) == len(next_assigned) == len(requests))
            next_counts = [used+int(old != new) for used, old, new
                           in zip(counts, assigned, next_assigned)]+[0]
            require(next_counts == row["counts"] and max(next_counts) <= budget)
            child = tuple(sorted(zip(requests, next_assigned, next_counts)))
            require(child in {tuple(sorted(candidate)) for candidate in successors(current, request)})
            observed_cost = cost(child)
            reference_cost = optimum(tuple(sorted(requests)))
            require(observed_cost == row["cost"])
            require(reference_cost == row["optimum"])
            require(observed_cost-reference_cost+value(child) == value(current))
            # Preserve arrival identities for the full production action tie key;
            # only value computations use canonical, coordinate-sorted states.
            keys = []
            for candidate in successors(ordered_state, request):
                matching = tuple(s for _, s, _ in candidate)
                updated = tuple(used for _, _, used in candidate)
                keys.append((objective(candidate, reference_cost), sum(updated)-sum(counts), matching, updated))
            observed = (objective(child, reference_cost), sum(next_counts)-sum(counts), tuple(next_assigned), tuple(next_counts))
            require(observed == min(keys), 'nondeterministic action tie')
            witness_excess += observed_cost-reference_cost
            current, assigned, counts = child, next_assigned, next_counts
        require(witness_excess == computed)
        verified.append({"model": model, "budget": budget, "known_future": fixed is not None,
                         "value": computed, "canonical_states": value.cache_info().currsize,
                         "witness_stages_verified": len(requests)})
        print(json.dumps({"verified": verified[-1],
                          "cpu_seconds_so_far": time.process_time()-started}), flush=True)

    result = {"status": "independently_verified", "source": source.name,
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": f"{len(summary['results'])} finite alphabet online games, {len(summary['hindsight_fixed_sequence'])} known future comparisons, all saved witness stages",
              "independence": {"imports_original_solver": False,
                               "state": "sorted multiset of coordinate, server index, lifetime count triples",
                               "optimum": "sorted requests against every service subset",
                               "chain_actions": "grow backwards from each free service; move each old request at most once"},
              "results": verified, "cpu_seconds": time.process_time()-started,
              "all_checks_passed": True}
    (source.parent/"verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).parent/"output"/"four_game_20260925T053018894723Z"/"summary.json")
    verify(path, float(sys.argv[2]) if len(sys.argv) > 2 else 120)
