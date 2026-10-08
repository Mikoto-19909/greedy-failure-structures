"""Two-factor ablation and separate analytically constructed stress sequences."""
from datetime import datetime, timezone
from fractions import Fraction
from itertools import permutations
import csv
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parent


def choose(servers, requests, old, used, budget, limit, weight):
    free = [s for s in range(len(servers)) if s not in old]
    endpoint = min(free, key=lambda s: (abs(requests[-1]-servers[s]), servers[s], s))
    best = old + [endpoint]
    value = sum(abs(r-servers[s]) for r, s in zip(requests, best))
    key = (value, value, 0, tuple(best))
    moves = []
    eligible = [i for i in range(len(old)) if used[i] < budget]
    for length in range(1, min(limit, len(eligible))+1):
        for path in permutations(eligible, length):
            for endpoint in free:
                candidate = old + [old[path[0]]]
                for j, i in enumerate(path):
                    candidate[i] = old[path[j+1]] if j+1 < length else endpoint
                value = sum(abs(r-servers[s]) for r, s in zip(requests, candidate))
                price = sum(weight*Fraction(abs(servers[candidate[i]]-servers[old[i]]), budget-used[i]) for i in path)
                candidate_key = (value+price, value, length, tuple(candidate))
                if candidate_key < key:
                    best, moves, key = candidate, list(reversed(path)), candidate_key
    return best, moves


def simulate(case, budget, limit, weight):
    servers = case['servers']
    requests = [case['requests'][i] for i in case['order']]
    old, used, history = [], [], []
    for t in range(1, len(requests)+1):
        new, moves = choose(servers, requests[:t], old, used, budget, limit, weight)
        for i in moves:
            used[i] += 1
        used.append(0)
        history.append(dict(t=t, assignment=new, counts=list(used), moves=moves,
                            cost=sum(abs(r-servers[s]) for r, s in zip(requests[:t], new))))
        old = new
    return history


def oracle_and_signs(case):
    ss = case['servers']
    rr = [case['requests'][i] for i in case['order']]
    rows = []
    for t in range(1, len(rr)+1):
        scored = [(sum(abs(r-ss[s]) for r, s in zip(rr[:t], m)), m)
                  for m in permutations(range(len(ss)), t)]
        opt = min(value for value, _ in scored)
        first_locations = sorted({ss[m[0]] for value, m in scored if value == opt})
        rows.append(dict(t=t, optimum=opt, possible_first_servers=first_locations))
    return rows


def main():
    started = time.process_time()
    original = (ROOT.parent/'inputs.json').read_bytes()
    manifest = json.loads((ROOT.parent/'input_manifest.json').read_text())
    assert hashlib.sha256(original).hexdigest() == manifest['input_sha256']
    cases = json.loads(original)['cases']
    for n in (3, 4, 5, 6):
        radial = [(-1)**i*2**(i-1) for i in range(1, n+1)]
        cases.append(dict(id=f'alternating_radius_n{n}', split='stress', family='alternating_radius',
                          servers=sorted(radial), requests=[0]+radial[:-1], order=list(range(n))))
    out = ROOT/'output'/('ablation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out/'ablation.py')
    (out/'inputs.json').write_text(json.dumps(dict(original_sha256=manifest['input_sha256'], cases=cases), indent=2)+'\n')
    shutil.copyfile(ROOT/'过程/分支3与4协议.md', out/'protocol_snapshot.md')
    traces, metrics, oracle = [], [], {}
    for case in cases:
        oracle[case['id']] = oracle_and_signs(case)
        configs = {(limit, weight, b) for limit in (1, 5) for weight in (Fraction(0), Fraction(1, 2)) for b in (1, 2, 4)}
        if case['split'] == 'dev':
            configs |= {(5, weight, b) for weight in (Fraction(1, 4), Fraction(1)) for b in (1, 2, 4)}
        # Budget5 is a constructive all-prefix-optimal check on the n=6 witness.
        if case['split'] == 'stress':
            configs |= {(5, Fraction(0), b) for b in range(1, len(case['servers']))}
        for limit, weight, budget in sorted(configs):
            before = time.process_time()
            wall = time.perf_counter()
            history = simulate(case, budget, limit, weight)
            cpu, elapsed = time.process_time()-before, time.perf_counter()-wall
            row = dict(case_id=case['id'], split=case['split'], family=case['family'],
                       chain_limit=limit, weight=str(weight), budget=budget,
                       prefix_sum=sum(h['cost'] for h in history), final_cost=history[-1]['cost'],
                       optimum_prefix_sum=sum(h['optimum'] for h in oracle[case['id']]),
                       total_recourse=sum(history[-1]['counts']), max_request_recourse=max(history[-1]['counts']),
                       cpu_seconds=cpu, wall_seconds=elapsed)
            metrics.append(row)
            traces.append(dict(**row, history=history))
    (out/'traces.json').write_text(json.dumps(traces, indent=2)+'\n')
    (out/'oracle.json').write_text(json.dumps(oracle, indent=2)+'\n')
    with (out/'metrics.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    groups = []
    for split in ('dev', 'eval', 'stress'):
        for limit, weight, budget in sorted({(r['chain_limit'], r['weight'], r['budget']) for r in metrics if r['split']==split}):
            rows = [r for r in metrics if (r['split'], r['chain_limit'], r['weight'], r['budget'])==(split, limit, weight, budget)]
            groups.append(dict(split=split, chain_limit=limit, weight=weight, budget=budget,
                               count=len(rows), prefix_sum=sum(r['prefix_sum'] for r in rows),
                               total_recourse=sum(r['total_recourse'] for r in rows),
                               cpu_seconds=sum(r['cpu_seconds'] for r in rows)))
    summary = dict(status='computed_pending_independent_verification', original_sha256=manifest['input_sha256'],
                   groups=groups, fixed_comparison_count=24, development_count=6, stress_count=4,
                   runtime=dict(cpu_seconds=time.process_time()-started))
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(out)
    for r in groups:
        if r['split'] in ('eval', 'dev') and r['budget'] in (1, 2):
            print(r)
    print('Stress complete-chain weight=0:',
          [(r['case_id'], r['budget'], r['prefix_sum'], r['max_request_recourse']) for r in metrics
           if r['split']=='stress' and r['chain_limit']==5 and r['weight']=='0'])


if __name__ == '__main__':
    main()
