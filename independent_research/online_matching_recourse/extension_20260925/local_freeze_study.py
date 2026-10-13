"""Two predeclared local-freeze rounds; no old formal experiment is rerun."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction as Q
import gzip
from itertools import product
import json
from pathlib import Path
import time

import local_freeze
from long_sequence import run as run_restart
from verify_local_freeze import verify
from verify_long_sequence import verify as verify_restart


def require(condition, message='verification check failed'):
    """Keep scientific checks active under -O and PYTHONOPTIMIZE."""
    if not condition:
        raise AssertionError(message)

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parents[2] / 'results/online_matching_local_20260927'
CPU_LIMIT = 600


def fixed_cases():
    original = json.loads((HERE.parent / 'inputs.json').read_text(encoding='utf-8'))
    cases = [{key: case[key] for key in ('id', 'servers', 'requests')}
             for case in original['cases'] if case['split'] == 'dev']
    servers = [-4, -1, 2, 8]
    requests = [5, 2, -1, -4]
    cases.extend([
        dict(id='four_budget1', servers=servers, requests=requests),
        dict(id='four_budget2', servers=servers, requests=['1/2', -1, 2, -4]),
        dict(id='two_blocks', servers=servers + [s + 100 for s in servers],
             requests=requests + [r + 100 for r in requests]),
    ])
    return cases


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def compare(root):
    initial = json.loads((root / 'initial/summary.json').read_text())
    revised = json.loads((root / 'revised/summary.json').read_text())
    require(initial['status'] == revised['status'] == 'complete')
    old = {(r['case'], r['budget'], r['policy']): r for r in initial['comparisons']}
    result = dict(groups=[], cases=[], cpu_seconds=initial['cpu_seconds'] + revised['cpu_seconds'])
    for budget in (1, 2, 4):
        rows = [r for r in revised['comparisons'] if r['budget'] == budget]
        require(len(rows) == revised['input_cases'] and len({r['case'] for r in rows}) == len(rows))
        totals = {policy: Q(0) for policy in ('rm', 'global_reset', 'fixed4', 'budget_blocks')}
        wins = ties = losses = 0
        freeze = {'fixed4': Q(0), 'budget_blocks': Q(0)}
        restriction = dict(freeze)
        for row in rows:
            case = row['case']
            values = {p: Q(old[case, 0 if p == 'rm' else budget, p]['metrics']['prefix_sum'])
                      for p in ('rm', 'global_reset', 'fixed4')}
            values['budget_blocks'] = Q(row['metrics']['prefix_sum'])
            for p, value in values.items():
                totals[p] += value
            difference = values['budget_blocks'] - values['global_reset']
            wins += difference < 0
            ties += difference == 0
            losses += difference > 0
            for policy, phase, item in [('fixed4', 'initial', old[case, budget, 'fixed4']),
                                        ('budget_blocks', 'revised', row)]:
                data = json.loads((root / phase / item['file']).read_text())
                freeze[policy] += sum((Q(s['cost']) - Q(s['block_optimum_sum']) for s in data['trace']), Q())
                restriction[policy] += sum((Q(s['block_optimum_sum']) - Q(s['optimum']) for s in data['trace']), Q())
            result['cases'].append(dict(case=case, budget=budget, prefix_sum={p: str(v) for p, v in values.items()},
                                        repaired_metrics=row['metrics']))
        result['groups'].append(dict(budget=budget, cases=len(rows), prefix_sum={p: str(v) for p, v in totals.items()},
                                     vs_global=dict(better=wins, same=ties, worse=losses),
                                     relative_change=str(totals['budget_blocks'] / totals['global_reset'] - 1),
                                     frozen_excess={p: str(v) for p, v in freeze.items()},
                                     block_restriction_excess={p: str(v) for p, v in restriction.items()}))
    return result


def run_phase(phase, root):
    start = time.process_time()
    out = root / phase
    out.mkdir(parents=True, exist_ok=False)
    if phase == 'initial':
        cases = fixed_cases()
        previous_cpu = 0
    else:
        old = json.loads((root / 'initial/summary.json').read_text())
        require(old['status'] == 'complete')
        require(any(Q(row['verification'].get('maximum_frozen_loss', '0')) > 0
                   for row in old['comparisons']), 'predeclared second-round trigger absent')
        cases = json.loads((root / 'initial/inputs.json').read_text())
        previous_cpu = old['cpu_seconds']
    write(out / 'inputs.json', cases)
    summary = dict(status='incomplete', phase=phase, started_utc=datetime.now(timezone.utc).isoformat(),
                   cpu_limit=CPU_LIMIT, previous_cpu_seconds=previous_cpu, comparisons=[], audit={},
                   baseline_source='initial/summary.json', input_cases=len(cases))

    def check_time():
        if previous_cpu + time.process_time() - start > CPU_LIMIT:
            raise TimeoutError('local study CPU limit reached')

    def save(case, budget, policy, record, checked):
        name = f"{case['id']}_b{budget}_{policy}.json"
        write(out / name, record)
        summary['comparisons'].append(dict(case=case['id'], budget=budget, policy=policy, file=name,
                                          metrics=local_freeze.metrics(record), verification=checked))

    try:
        for case in cases:
            for budget in (1, 2, 4):
                check_time()
                data = local_freeze.run(case['servers'], case['requests'], budget, 4 if phase == 'initial' else None)
                checked = verify(data)
                save(case, budget, 'fixed4' if phase == 'initial' else 'budget_blocks', data, checked)
                if phase == 'initial':
                    baseline = run_restart(case['servers'], case['requests'], budget, trigger_ratio=2)
                    save(case, budget, 'global_reset', baseline, verify_restart(baseline))
                    if budget == 1:
                        save(case, 0, 'rm', data['shadow'], verify_restart(data['shadow']))
            print(f"{phase}: {case['id']}", flush=True)
        if phase == 'revised':
            alphabet = ('-4', '-1', '1/2', '2', '5', '8')
            audit = dict(alphabet=alphabet, servers=[-4, -1, 2, 8], sequences=0, traces=0,
                         prefixes=0, by_budget={str(b): dict(max_excess='0', max_ratio='1') for b in (1, 2, 4)})
            summary['audit'] = audit
            with gzip.open(out / 'finite_audit.jsonl.gz', 'wt', encoding='utf-8') as stream:
                for requests in product(alphabet, repeat=4):
                    for budget in (1, 2, 4):
                        check_time()
                        data = local_freeze.run(audit['servers'], requests, budget)
                        checked = verify(data)
                        stream.write(json.dumps(dict(data=data, verification=checked), separators=(',', ':')) + '\n')
                        measures = local_freeze.metrics(data)
                        group = audit['by_budget'][str(budget)]
                        if Q(measures['excess_sum']) > Q(group['max_excess']):
                            group['max_excess'] = measures['excess_sum']
                            group['worst_requests'] = requests
                        group['max_ratio'] = str(max(Q(group['max_ratio']), Q(measures['max_ratio'])))
                        audit['traces'] += 1
                        audit['prefixes'] += len(requests)
                    audit['sequences'] += 1
                    if audit['sequences'] % 216 == 0:
                        print(f"audit {audit['sequences']}/1296", flush=True)
            require(audit['sequences'] == 1296 and audit['traces'] == 3888)
        summary['status'] = 'complete'
    finally:
        summary['cpu_seconds'] = time.process_time() - start
        write(out / 'summary.json', summary)
        print(json.dumps(dict(status=summary['status'], cpu_seconds=summary['cpu_seconds'], output=str(out))), flush=True)
    if phase == 'revised':
        write(out / 'comparison.json', compare(root))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('initial', 'revised'))
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    run_phase(args.phase, args.output_root)


if __name__ == '__main__':
    main()
