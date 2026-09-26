"""Run a fixed split. Usage: python -B run.py --split dev|eval."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time

from matching import exact_prefix, simulate

ROOT = Path(__file__).resolve().parent


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    start = time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['dev', 'eval'], required=True)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    data = (ROOT / 'inputs.json').read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == json.loads((ROOT / 'input_manifest.json').read_text())['input_sha256']
    out = args.output_root.resolve() / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + args.split)
    out.mkdir(parents=True, exist_ok=False)
    for name in ['inputs.json', 'input_manifest.json', 'protocol.md', 'matching.py', 'run.py']:
        shutil.copyfile(ROOT / name, out / name)
    traces, rows = [], []
    for case in json.loads(data)['cases']:
        if case['split'] != args.split:
            continue
        ss = case['servers']
        rr = [case['requests'][i] for i in case['order']]
        cpu0, wall0 = time.process_time(), time.perf_counter()
        optimum = [exact_prefix(ss, rr[:t]) for t in range(1, len(rr)+1)]
        ocpu, owall = time.process_time()-cpu0, time.perf_counter()-wall0
        configs = [('nearest', 0)] + [(p, b) for p in ['single', 'priced_chain'] for b in [1, 2, 4]] + [('prefix_optimum', None)]
        for policy, budget in configs:
            if policy == 'prefix_optimum':
                history, cpu, wall = None, ocpu, owall
                costs, total, max_one = optimum, None, None
            else:
                cpu0, wall0 = time.process_time(), time.perf_counter()
                history = simulate(ss, rr, policy, budget)
                cpu, wall = time.process_time()-cpu0, time.perf_counter()-wall0
                costs = [h['cost'] for h in history]
                total, max_one = sum(history[-1]['counts']), max(history[-1]['counts'])
            ratios = [c/o if o else (1 if c == 0 else float('inf')) for c, o in zip(costs, optimum)]
            traces.append(dict(case_id=case['id'], split=args.split, family=case['family'],
                               policy=policy, budget=budget, history=history, oracle_costs=optimum,
                               cpu_seconds=cpu, wall_seconds=wall))
            rows.append(dict(case_id=case['id'], family=case['family'], policy=policy, budget=budget,
                             prefix_sum=sum(costs), final_cost=costs[-1], max_ratio=max(ratios),
                             total_recourse=total, max_request_recourse=max_one,
                             cpu_seconds=cpu, wall_seconds=wall))
    dump(out / 'traces.json', traces)
    with (out / 'metrics.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    aggregates = []
    for family in ['all'] + sorted({r['family'] for r in rows}):
        baseline = sum(r['prefix_sum'] for r in rows if r['policy'] == 'nearest' and (family == 'all' or r['family'] == family))
        for policy, budget in configs:
            items = [r for r in rows if r['policy'] == policy and r['budget'] == budget and (family == 'all' or r['family'] == family)]
            prefix_sum = sum(r['prefix_sum'] for r in items)
            aggregates.append(dict(family=family, policy=policy, budget=budget, sequences=len(items),
                                   prefix_sum=prefix_sum, final_cost=sum(r['final_cost'] for r in items),
                                   reduction_pct=100*(1-prefix_sum/baseline), max_ratio=max(r['max_ratio'] for r in items),
                                   total_recourse=None if budget is None else sum(r['total_recourse'] for r in items),
                                   max_request_recourse=None if budget is None else max(r['max_request_recourse'] for r in items),
                                   cpu_seconds=sum(r['cpu_seconds'] for r in items), wall_seconds=sum(r['wall_seconds'] for r in items)))
    summary = dict(status='computed_pending_independent_verification', split=args.split,
                   source_sha256=digest, python=platform.python_version(), processes=1,
                   runtime=dict(process_cpu_seconds=time.process_time()-start),
                   exploratory_expectations=['longer chains can repair local displacement bottlenecks',
                                             'reserving a last move can avoid future budget locks'],
                   aggregates=aggregates)
    dump(out / 'summary.json', summary)
    print(out)
    for item in aggregates:
        if item['family'] == 'all':
            print(item)


if __name__ == '__main__':
    main()
