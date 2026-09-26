"""Independent all-injection validation; no import from ablation or matching."""
import argparse
import csv
from fractions import Fraction
from itertools import permutations
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def path_moves(old, new):
    changed = {i for i in range(len(old)) if old[i] != new[i]}
    owners = {server: i for i, server in enumerate(old)}
    forward, destination = [], new[-1]
    while destination in owners:
        i = owners[destination]
        if i in forward or i not in changed:
            return None
        forward.append(i)
        destination = new[i]
    return list(reversed(forward)) if set(forward) == changed else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    out = parser.parse_args().directory
    started = time.process_time()
    cases = {c['id']: c for c in read(out/'inputs.json')['cases']}
    traces, summary, oracle = read(out/'traces.json'), read(out/'summary.json'), read(out/'oracle.json')
    with (out/'metrics.csv').open(encoding='utf-8-sig', newline='') as f:
        metrics = list(csv.DictReader(f))
    assert len(metrics) == len(traces)
    historic = {}
    for folder in ('20260924T175730918352Z-dev', '20260924T175731049376Z-eval'):
        for r in read(ROOT.parent/'output'/folder/'traces.json'):
            historic[r['case_id'], r['policy'], r['budget']] = r['history']
    stages, historic_matches, checked_oracles = 0, 0, 0
    for case in cases.values():
        ss = case['servers']
        rr = [case['requests'][i] for i in case['order']]
        for t in range(1, len(rr)+1):
            possibilities = [(sum(abs(rr[i]-ss[s]) for i, s in enumerate(m)), m)
                             for m in permutations(range(len(ss)), t)]
            optimum = min(cost for cost, _ in possibilities)
            locations = sorted({ss[m[0]] for cost, m in possibilities if cost == optimum})
            assert oracle[case['id']][t-1] == dict(t=t, optimum=optimum, possible_first_servers=locations)
            if case['split'] == 'stress':
                assert optimum == 2**(t-1)
                assert all(s*((-1)**t) > 0 for s in locations)
            checked_oracles += 1
    seen = set()
    for trace, metric in zip(traces, metrics):
        identifier = tuple(trace[k] for k in ('case_id', 'chain_limit', 'weight', 'budget'))
        assert identifier not in seen
        seen.add(identifier)
        case = cases[trace['case_id']]
        ss, rr = case['servers'], [case['requests'][i] for i in case['order']]
        old, counts = [], []
        for step in trace['history']:
            t = len(old)+1
            candidates = []
            for proposed in permutations(range(len(ss)), t):
                moves = path_moves(old, proposed)
                if moves is None or len(moves) > trace['chain_limit'] or any(counts[i] >= trace['budget'] for i in moves):
                    continue
                actual = sum(abs(rr[i]-ss[s]) for i, s in enumerate(proposed))
                price = sum(Fraction(trace['weight'])*Fraction(abs(ss[proposed[i]]-ss[old[i]]), trace['budget']-counts[i]) for i in moves)
                candidates.append(((actual+price, actual, len(moves), proposed), moves))
            best_key, moves = min(candidates)
            assert step['assignment'] == list(best_key[-1]) and step['cost'] == best_key[1]
            assert step['moves'] == moves
            occupied = set(old)
            for i in moves:
                target = step['assignment'][i]
                assert target not in occupied
                occupied.remove(old[i])
                occupied.add(target)
                counts[i] += 1
            assert step['assignment'][-1] not in occupied
            counts.append(0)
            assert counts == step['counts'] and max(counts) <= trace['budget']
            old = step['assignment']
            stages += 1
        h = trace['history']
        expected = dict(prefix_sum=sum(s['cost'] for s in h), final_cost=h[-1]['cost'],
                        total_recourse=sum(counts), max_request_recourse=max(counts),
                        optimum_prefix_sum=sum(s['optimum'] for s in oracle[case['id']]))
        for key, value in expected.items():
            assert trace[key] == value == int(metric[key])
        for key in trace:
            if key != 'history' and key in metric:
                assert str(trace[key]) == metric[key]
        policy = 'single' if (trace['chain_limit'], trace['weight']) == (1, '0') else 'priced_chain' if (trace['chain_limit'], trace['weight']) == (5, '1/2') else None
        if policy and case['split'] != 'stress':
            assert h == historic[case['id'], policy, trace['budget']]
            historic_matches += 1
    for group in summary['groups']:
        rows = [t for t in traces if all(t[k] == group[k] for k in ('split', 'chain_limit', 'weight', 'budget'))]
        assert group['count'] == len(rows)
        for field in ('prefix_sum', 'total_recourse', 'cpu_seconds'):
            assert group[field] == sum(r[field] for r in rows)
    result = dict(status='automatic_verification_passed_user_review_pending', trajectories=len(traces),
                  stages=stages, prefix_oracles=checked_oracles, unchanged_historical_trajectories=historic_matches,
                  checked='all injections, simple-path feasibility, execution, lifetime caps, costs, rational choice, aggregation, alternating signs',
                  cpu_seconds=time.process_time()-started)
    (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    summary['status'] = result['status']
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
