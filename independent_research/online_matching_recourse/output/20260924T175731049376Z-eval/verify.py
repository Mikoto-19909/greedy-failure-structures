"""Independent exhaustive audit; never import the policy or fixture generator."""
import argparse
from collections import Counter
from copy import deepcopy
import csv
from fractions import Fraction
import hashlib
from itertools import permutations
import json
import math
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parent
CONFIGURATIONS = [('nearest', 0)] + [
    (policy, budget) for policy in ('single', 'priced_chain') for budget in (1, 2, 4)
] + [('prefix_optimum', None)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def distance(servers, requests, assignment):
    return sum(abs(requests[i] - servers[j]) for i, j in enumerate(assignment))


def input_audit():
    raw = (ROOT / 'inputs.json').read_bytes()
    data = json.loads(raw)
    manifest = json.loads((ROOT / 'input_manifest.json').read_text(encoding='utf-8'))
    require(hashlib.sha256(raw).hexdigest() == manifest['input_sha256'], 'input hash')
    cases = data['cases']
    require(len(cases) == manifest['cases'] <= 30, 'case count')
    require(data['seed'] == manifest['seed'], 'seed')
    require(sum(c['split'] == 'dev' for c in cases) == manifest['development'], 'dev count')
    require(sum(c['split'] == 'eval' for c in cases) == manifest['evaluation'], 'eval count')
    require(len({c['id'] for c in cases}) == len(cases), 'duplicate case')
    for case in cases:
        n = len(case['requests'])
        require(1 <= n <= len(case['servers']) <= 6, f"size: {case['id']}")
        require(sorted(case['order']) == list(range(n)), f"order: {case['id']}")
    return data, manifest


def optimal_prefixes(servers, requests):
    values, enumerated = [], 0
    for t in range(1, len(requests) + 1):
        best = None
        for assignment in permutations(range(len(servers)), t):
            enumerated += 1
            value = distance(servers, requests[:t], assignment)
            best = value if best is None else min(best, value)
        values.append(best)
    return values, enumerated


def chain_execution(old, candidate):
    """Recognize a single augmenting path by following occupied destinations."""
    changed = {i for i, server in enumerate(old) if candidate[i] != server}
    if not changed:
        return []
    owners = {server: i for i, server in enumerate(old)}
    destination, forward = candidate[-1], []
    while destination in owners:
        request = owners[destination]
        if request in forward or request not in changed:
            return None
        forward.append(request)
        destination = candidate[request]
    if set(forward) != changed:
        return None
    return list(reversed(forward))


def independent_choice(servers, prefix, old, counts, policy, budget):
    free = set(range(len(servers))) - set(old)
    nearest = min(free, key=lambda j: (abs(prefix[-1] - servers[j]), servers[j], j))
    baseline = tuple(old + [nearest])
    if policy == 'nearest':
        return baseline, []
    value = distance(servers, prefix, baseline)
    best_key = (Fraction(value), value, 0, baseline)
    best, best_moves = baseline, []
    # Enumerate all injections, unlike the production path-permutation generator.
    for candidate in permutations(range(len(servers)), len(prefix)):
        changed = [i for i, server in enumerate(old) if candidate[i] != server]
        if not changed or (policy == 'single' and len(changed) > 1):
            continue
        if any(counts[i] >= budget for i in changed):
            continue
        moves = chain_execution(old, candidate)
        if moves is None:
            continue
        actual = distance(servers, prefix, candidate)
        penalty = Fraction(0)
        if policy == 'priced_chain':
            penalty = sum((Fraction(abs(servers[candidate[i]] - servers[old[i]]),
                                    2 * (budget - counts[i])) for i in changed), Fraction(0))
        key = (actual + penalty, actual, len(changed), candidate)
        if key < best_key:
            best, best_moves, best_key = candidate, moves, key
    return best, best_moves


def audit_trace(trace, case, optimal):
    tag = f"{case['id']}/{trace['policy']}/{trace['budget']}"
    require(trace['split'] == case['split'], f'{tag}: split')
    require(trace['family'] == case['family'], f'{tag}: family')
    require(trace['oracle_costs'] == optimal, f'{tag}: exact prefix values')
    for name in ('cpu_seconds', 'wall_seconds'):
        require(isinstance(trace[name], (int, float)) and math.isfinite(trace[name]) and trace[name] >= 0,
                f'{tag}: invalid {name}')
    if trace['policy'] == 'prefix_optimum':
        require(trace['history'] is None, f'{tag}: reference history')
        return 0, 0
    servers = case['servers']
    requests = [case['requests'][i] for i in case['order']]
    old, counts = [], []
    require(len(trace['history']) == len(requests), f'{tag}: history length')
    total_moves = 0
    for t, step in enumerate(trace['history'], 1):
        where = f'{tag}/t={t}'
        require(step['t'] == t, f'{where}: t')
        assignment, moves = step['assignment'], step['moves']
        require(len(assignment) == t and len(set(assignment)) == t, f'{where}: injection')
        require(all(type(j) is int and 0 <= j < len(servers) for j in assignment),
                f'{where}: server indices')
        require(len(moves) == len(set(moves)), f'{where}: repeated move')
        require(all(type(i) is int and 0 <= i < t - 1 for i in moves),
                f'{where}: move indices')
        changed = {i for i in range(t - 1) if old[i] != assignment[i]}
        require(changed == set(moves), f'{where}: moves differ from assignment changes')
        live = list(old)
        for request in moves:
            target = assignment[request]
            require(target not in live, f'{where}: move destination occupied')
            live[request] = target
            counts[request] += 1
        require(assignment[-1] not in live, f'{where}: arrival destination occupied')
        live.append(assignment[-1])
        counts.append(0)
        require(live == assignment, f'{where}: execution mismatch')
        require(counts == step['counts'], f'{where}: cumulative recourse counts')
        require(max(counts) <= trace['budget'], f'{where}: per-request lifetime budget')
        require(step['cost'] == distance(servers, requests[:t], assignment), f'{where}: cost')
        previous_counts = [counts[i] - (i in changed) for i in range(t - 1)]
        chosen, chosen_moves = independent_choice(
            servers, requests[:t], old, previous_counts, trace['policy'], trace['budget'])
        require(tuple(assignment) == chosen, f'{where}: strategy choice')
        require(moves == chosen_moves, f'{where}: strategy execution order')
        require(step['cost'] >= optimal[t - 1], f'{where}: cost below exact optimum')
        total_moves += len(moves)
        old = assignment
    return len(requests), total_moves


def audit_traces(traces, data, split):
    cases = {case['id']: case for case in data['cases'] if case['split'] == split}
    seen = Counter((trace['case_id'], trace['policy'], trace['budget']) for trace in traces)
    expected = {(case_id, policy, budget) for case_id in cases for policy, budget in CONFIGURATIONS}
    require(set(seen) == expected and all(n == 1 for n in seen.values()), 'trace coverage')
    oracles, enumerated = {}, 0
    for case_id, case in cases.items():
        requests = [case['requests'][i] for i in case['order']]
        oracles[case_id], count = optimal_prefixes(case['servers'], requests)
        enumerated += count
    stages = moves = 0
    for trace in traces:
        count, moved = audit_trace(trace, cases[trace['case_id']], oracles[trace['case_id']])
        stages += count
        moves += moved
    corrupt = deepcopy(next(t for t in traces if t['policy'] == 'nearest'))
    corrupt['history'][0]['cost'] += 1
    caught = False
    try:
        audit_trace(corrupt, cases[corrupt['case_id']], oracles[corrupt['case_id']])
    except ValueError as error:
        caught = str(error).endswith(': cost')
    require(caught, 'in-memory tampered-cost rejection')
    return dict(cases=len(cases), traces=len(traces), online_stages=stages,
                executed_reassignments=moves, exhaustive_assignments=enumerated,
                tampered_cost_rejected=True)


def same_number(actual, expected):
    if expected is None:
        return actual is None or actual == ''
    try:
        return math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-12)
    except (TypeError, ValueError):
        return False


def audit_summaries(traces, summary, directory, manifest):
    require(summary['source_sha256'] == manifest['input_sha256'], 'summary input hash')
    require(summary['processes'] == 1, 'single-process execution')
    require(summary['runtime']['process_cpu_seconds'] >= 0, 'process CPU time')
    for name in ('inputs.json', 'input_manifest.json'):
        require((directory / name).read_bytes() == (ROOT / name).read_bytes(), f'frozen {name}')
    with (directory / 'metrics.csv').open(encoding='utf-8-sig', newline='') as handle:
        metrics = list(csv.DictReader(handle))
    require(len(metrics) == len(traces), 'metrics row count')
    measured = {}
    for row in metrics:
        key = (row['case_id'], row['policy'], None if row['budget'] == '' else int(row['budget']))
        require(key not in measured, 'duplicate metrics row')
        measured[key] = row
    recomputed = []
    for trace in traces:
        key = (trace['case_id'], trace['policy'], trace['budget'])
        require(key in measured, 'missing metrics row')
        optimum = trace['oracle_costs']
        history = trace['history']
        costs = optimum if history is None else [step['cost'] for step in history]
        ratios = [cost / opt if opt else (1 if cost == 0 else math.inf)
                  for cost, opt in zip(costs, optimum)]
        row = dict(case_id=trace['case_id'], family=trace['family'], policy=trace['policy'],
                   budget=trace['budget'], prefix_sum=sum(costs), final_cost=costs[-1],
                   max_ratio=max(ratios),
                   total_recourse=None if history is None else sum(len(step['moves']) for step in history),
                   max_request_recourse=None if history is None else max(history[-1]['counts']),
                   cpu_seconds=trace['cpu_seconds'], wall_seconds=trace['wall_seconds'])
        for name in ('case_id', 'family', 'policy'):
            require(measured[key][name] == row[name], f'metrics {key}: {name}')
        for name in ('budget', 'prefix_sum', 'final_cost', 'max_ratio', 'total_recourse',
                     'max_request_recourse', 'cpu_seconds', 'wall_seconds'):
            require(same_number(measured[key][name], row[name]), f'metrics {key}: {name}')
        recomputed.append(row)
    groups = {}
    for entry in summary['aggregates']:
        key = (entry['family'], entry['policy'], entry['budget'])
        require(key not in groups, 'duplicate summary group')
        groups[key] = entry
    families = {'all'} | {trace['family'] for trace in traces}
    require(set(groups) == {(family, policy, budget) for family in families
                           for policy, budget in CONFIGURATIONS}, 'summary group coverage')
    for (family, policy, budget), reported in groups.items():
        family_rows = [row for row in recomputed if family == 'all' or row['family'] == family]
        items = [row for row in family_rows if row['policy'] == policy and row['budget'] == budget]
        denominator = sum(row['prefix_sum'] for row in family_rows if row['policy'] == 'nearest')
        expected = {name: sum(row[name] for row in items)
                    for name in ('prefix_sum', 'final_cost', 'cpu_seconds', 'wall_seconds')}
        expected.update(sequences=len(items), max_ratio=max(row['max_ratio'] for row in items),
                        reduction_pct=100 * (denominator - expected['prefix_sum']) / denominator,
                        total_recourse=None if budget is None else sum(row['total_recourse'] for row in items),
                        max_request_recourse=None if budget is None else max(row['max_request_recourse'] for row in items))
        for name, value in expected.items():
            require(same_number(reported[name], value), f'summary {family}/{policy}/{budget}: {name}')
    return dict(metrics_rows=len(metrics), summary_groups=len(groups))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_directory', type=Path)
    args = parser.parse_args()
    started = time.process_time()
    data, manifest = input_audit()
    summary = json.loads((args.run_directory / 'summary.json').read_text(encoding='utf-8'))
    require(summary['split'] in ('dev', 'eval'), 'run split')
    trace_path = args.run_directory / 'traces.json'
    traces = json.loads(trace_path.read_text(encoding='utf-8'))
    counts = audit_traces(traces, data, summary['split'])
    counts.update(audit_summaries(traces, summary, args.run_directory, manifest))
    result = dict(
        status='automatic_verification_passed_user_review_pending',
        split=summary['split'],
        input_sha256=manifest['input_sha256'],
        traces_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        checks=['input_manifest', 'complete_trace_coverage', 'prefix_optimum_by_all_injections',
                'matching_injection', 'vacant_destination_execution', 'lifetime_recourse_counts',
                'lifetime_budget', 'coordinate_cost', 'policy_choice_by_all_injections',
                'deterministic_ties', 'tampered_cost_rejected_in_memory',
                'frozen_input_snapshots', 'metrics_csv', 'summary_aggregates'],
        counts=counts, cpu_seconds=time.process_time() - started)
    (args.run_directory / 'verification.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
