"""Independent all-injection validation; no import from ablation or matching."""
import argparse
import csv
from fractions import Fraction
from itertools import permutations
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
METRIC_FIELDS = ('case_id', 'split', 'family', 'chain_limit', 'weight', 'budget',
                 'prefix_sum', 'final_cost', 'optimum_prefix_sum', 'total_recourse',
                 'max_request_recourse', 'cpu_seconds', 'wall_seconds')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def expected_cases():
    # Shared fixed inputs, independently constructed stress cases; no solver import.
    cases = read(ROOT.parent/'inputs.json')['cases']
    assert all(case['split'] in ('dev', 'eval') for case in cases)
    for n in (3, 4, 5, 6):
        radial = [(-1)**i * 2**(i-1) for i in range(1, n+1)]
        cases.append(dict(id=f'alternating_radius_n{n}', split='stress', family='alternating_radius',
                          servers=sorted(radial), requests=[0]+radial[:-1], order=list(range(n))))
    assert len({case['id'] for case in cases}) == len(cases), 'duplicate fixed case'
    return {case['id']: case for case in cases}


def configurations(case):
    configs = {(limit, str(weight), budget) for limit in (1, 5)
               for weight in (Fraction(0), Fraction(1, 2)) for budget in (1, 2, 4)}
    if case['split'] == 'dev':
        configs |= {(5, str(weight), budget) for weight in (Fraction(1, 4), Fraction(1))
                    for budget in (1, 2, 4)}
    if case['split'] == 'stress':
        configs |= {(5, '0', budget) for budget in range(1, len(case['servers']))}
    return configs


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
    supplied_cases = read(out/'inputs.json')['cases']
    cases = {c['id']: c for c in supplied_cases}
    assert len(cases) == len(supplied_cases), 'duplicate case'
    assert cases == expected_cases(), 'incomplete or altered case set'
    traces, summary, oracle = read(out/'traces.json'), read(out/'summary.json'), read(out/'oracle.json')
    assert cases and traces and summary['groups'], 'empty comparison'
    assert set(oracle) == set(cases), 'incomplete or extra oracle case'
    expected = {(case['id'], limit, weight, budget) for case in cases.values()
                for limit, weight, budget in configurations(case)}
    identities = [tuple(trace[k] for k in ('case_id', 'chain_limit', 'weight', 'budget'))
                  for trace in traces]
    assert len(set(identities)) == len(identities), 'duplicate trajectory'
    assert set(identities) == expected, 'incomplete or extra trajectory configuration'
    expected_groups = {(cases[case_id]['split'], limit, weight, budget)
                       for case_id, limit, weight, budget in expected}
    group_ids = [tuple(group[k] for k in ('split', 'chain_limit', 'weight', 'budget'))
                 for group in summary['groups']]
    assert len(set(group_ids)) == len(group_ids), 'duplicate summary group'
    assert set(group_ids) == expected_groups, 'incomplete or extra summary group'
    for field, split in (('development_count', 'dev'), ('fixed_comparison_count', 'eval'), ('stress_count', 'stress')):
        assert summary[field] == sum(case['split'] == split for case in cases.values()), 'incorrect case count'
    with (out/'metrics.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        assert len(reader.fieldnames or []) == len(METRIC_FIELDS) and set(reader.fieldnames or []) == set(METRIC_FIELDS), 'incomplete or duplicate metric header'
        metrics = list(reader)
    assert len(metrics) == len(traces)
    assert all(set(row) == set(METRIC_FIELDS) and all(row[key] not in (None, '') for key in METRIC_FIELDS)
               for row in metrics), 'incomplete or extra metric fields'
    historic = {}
    for folder in ('20260924T175730918352Z-dev', '20260924T175731049376Z-eval'):
        for r in read(ROOT.parent/'output'/folder/'traces.json'):
            historic[r['case_id'], r['policy'], r['budget']] = r['history']
    stages, historic_matches, checked_oracles = 0, 0, 0
    for case in cases.values():
        ss = case['servers']
        rr = [case['requests'][i] for i in case['order']]
        assert len(oracle[case['id']]) == len(rr), 'incomplete or extra oracle stage'
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
        assert tuple(metric[k] for k in ('case_id', 'chain_limit', 'weight', 'budget')) == tuple(map(str, identifier)), 'incorrect metric identity'
        assert identifier not in seen
        seen.add(identifier)
        case = cases[trace['case_id']]
        assert (trace['split'], trace['family']) == (case['split'], case['family']), 'incorrect case metadata'
        ss, rr = case['servers'], [case['requests'][i] for i in case['order']]
        old, counts = [], []
        assert len(trace['history']) == len(rr), 'incomplete trajectory'
        for step in trace['history']:
            t = len(old)+1
            assert step['t'] == t, 'nonconsecutive stage'
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
        for key in METRIC_FIELDS:
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
