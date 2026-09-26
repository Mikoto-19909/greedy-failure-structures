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


def verify(source, cpu_limit=120):
    started = time.process_time()
    summary = json.loads(source.read_text(encoding="utf-8"))
    servers = tuple(summary["servers"])
    alphabet = tuple(summary["future_alphabet"])
    horizon = summary["horizon"]
    assert horizon == len(servers) == 4
    assert servers == tuple(sorted(set(servers)))

    @lru_cache(None)
    def optimum(requests_sorted):
        return min(sum(abs(x-s) for x, s in zip(requests_sorted, selected))
                   for selected in combinations(servers, len(requests_sorted)))

    def cost(state):
        return sum(abs(x-servers[s]) for x, s, _ in state)

    verified = []
    for reference in summary["results"] + summary["hindsight_fixed_sequence"]:
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
                        result.add(tuple(sorted(old+((request, assigned[-1], 0),))))
            else:
                assert model == "chain"
                used_servers = {s for _, s, _ in state}

                def grow(free, current, moved):
                    # Stop the chain by inserting the newly arrived request.
                    result.add(tuple(sorted(current+((request, free, 0),))))
                    for i, (x, old_server, used) in enumerate(current):
                        if i in moved or used == budget:
                            continue
                        changed = current[:i]+((x, free, used+1),)+current[i+1:]
                        grow(old_server, changed, moved | {i})

                for free in set(range(4))-used_servers:
                    grow(free, state, frozenset())
            assert result
            return tuple(sorted(result))

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
                best = min(cost(child)-reference_cost+(0 if len(child) == horizon else value(child))
                           for child in successors(state, request))
                worst = max(worst, best)
            return worst

        computed = value(())
        assert computed == reference["value"], (model, budget, computed, reference["value"])
        current, requests, assigned, counts = (), [], [], []
        witness_excess = 0
        for row in reference["witness"]:
            assert row["worst_remaining_excess"] == value(current)
            request = row["request"]
            requests.append(request)
            next_assigned = [servers.index(s) for s in row["assignment"]]
            assert len(set(next_assigned)) == len(next_assigned) == len(requests)
            next_counts = [used+int(old != new) for used, old, new
                           in zip(counts, assigned, next_assigned)]+[0]
            assert next_counts == row["counts"] and max(next_counts) <= budget
            child = tuple(sorted(zip(requests, next_assigned, next_counts)))
            assert child in successors(current, request)
            observed_cost = cost(child)
            reference_cost = optimum(tuple(sorted(requests)))
            assert observed_cost == row["cost"]
            assert reference_cost == row["optimum"]
            assert observed_cost-reference_cost+value(child) == value(current)
            # Check that the saved decision minimizes this revealed-request branch.
            best = min(cost(candidate)-reference_cost+value(candidate)
                       for candidate in successors(current, request))
            assert best == observed_cost-reference_cost+value(child)
            witness_excess += observed_cost-reference_cost
            current, assigned, counts = child, next_assigned, next_counts
        assert witness_excess == computed
        verified.append({"model": model, "budget": budget, "known_future": fixed is not None,
                         "value": computed, "canonical_states": value.cache_info().currsize,
                         "witness_stages_verified": len(requests)})
        print(json.dumps({"verified": verified[-1],
                          "cpu_seconds_so_far": time.process_time()-started}), flush=True)

    result = {"status": "independently_verified", "source": source.name,
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "6 finite alphabet online games, 3 known future comparisons, all saved witness stages",
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
