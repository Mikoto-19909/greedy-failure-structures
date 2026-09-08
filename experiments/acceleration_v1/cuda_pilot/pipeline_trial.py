"""Run real R2 production, diagnostics, verification and CSV analysis locally."""
from pathlib import Path
import argparse
import copy
import json
import statistics
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / 'pipeline_v1'
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'analysis')]
import r2_budget_grid as r2
from r2_design import make_design, read_json, write_json, load_records
from validate_r2_budget_grid import verify_summaries, verify_graph


def prepare():
    if (OUT / 'plan.json').exists():
        raise ValueError('plan already exists; reuse frozen plan')
    design = make_design('exploration', repetitions=1, diagnostic_count=1)
    old = read_json(HERE / 'design.json')['graphs']
    assert design['tasks'] == [g['task'] for g in old]
    write_json(OUT / 'plan.json', {'design': design, 'repeats': 3,
        'modes': ['python1', 'python4', 'compiled', 'hybrid'],
        'policy': 'hybrid uses CUDA for m=20 and compiled CPU otherwise; CUDA failures fall back to CPU',
        'scope': 'same nine R2 graphs, all planned budgets and diagnostics; actual R2 run/analyze(plot=False)/verify_summaries',
        'timing': 'warm parent process; fresh worker pools included; generation, batch preparation, compute, checkpoints, independent analysis verification, CSVs and summary verification included; imports/JIT warmup excluded',
        'verification_workers': 4, 'wall_limit_seconds': 600,
        'stop': 'three repeats per mode, exact semantic/CSV parity, partial and completed resume, fallback and invalid input checks; no production merge'})


def produce(design, directory, mode, backend=None, resume=False, stop_after=None):
    metrics = {'batch_prepare_seconds': 0.0, 'backend_seconds': 0.0, 'evaluation_seconds': 0.0}
    if mode in {'python1', 'python4'}:
        return r2.run(design, directory, workers=1 if mode == 'python1' else 4,
                      resume=resume, stop_after=stop_after), metrics

    def dispatch(function, arguments, workers, budget):
        # Called by the existing runner after checkpoint validation and pending-task selection.
        groups = {}
        t = time.perf_counter()
        for task, limits in arguments:
            instance = r2.fixed_size(universe_size=task['n'], set_count=task['n'], k=1,
                                    set_size=task['d'], unique_sets=False, seed=task['seed'])
            groups.setdefault(task['n'], []).append((task, limits, tuple(instance.sets)))
        metrics['batch_prepare_seconds'] += time.perf_counter() - t
        for group in groups.values():
            budget.check()
            t = time.perf_counter()
            answers = backend([list(g[2]) for g in group])
            metrics['backend_seconds'] += time.perf_counter() - t
            cached = {g[2]: answer for g, answer in zip(group, answers)}
            for task, limits, masks in group:
                budget.check()
                t = time.perf_counter()
                with patch.object(r2, 'all_budget_optima', side_effect=lambda sets: cached[tuple(sets)]):
                    record = function(task, limits)
                metrics['evaluation_seconds'] += time.perf_counter() - t
                yield record

    with patch.object(r2, 'computed_results', dispatch):
        result = r2.run(design, directory, workers=1, resume=resume, stop_after=stop_after)
    return result, metrics


def semantic_rows(directory, design):
    return [{k: v for k, v in row.items() if k != 'timing'} for row in load_records(directory, design)]


def pipeline(design, directory, mode, backend):
    start = time.perf_counter()
    status, detail = produce(design, directory, mode, backend)
    produced = time.perf_counter()
    r2.analyze(directory, plot=False)  # includes independent verify_graph for all nine graphs
    analyzed = time.perf_counter()
    verify_summaries(directory)
    verified = time.perf_counter()
    metrics = {'production_seconds': produced-start, 'analysis_seconds': analyzed-produced,
               'summary_verification_seconds': verified-analyzed, 'total_seconds': verified-start,
               'detail': detail, 'status': status}
    write_json(directory / 'pipeline_timing.json', metrics)
    return metrics


def checks(design, backends, baseline):
    from pipeline_backends import Backend
    tests = []
    mini = make_design('fixture', (4,), (2,), repetitions=2, diagnostic_count=1)
    directory = OUT / 'resume_check'
    b = backends['hybrid']
    before_events = len(b.events)
    first, _ = produce(mini, directory, 'hybrid', b, stop_after=1)
    assert not first['complete'] and first['computed'] == 1
    p = directory / 'graphs' / (mini['tasks'][0]['base_graph_id']+'.json')
    original = p.read_bytes()
    final, _ = produce(mini, directory, 'hybrid', b, resume=True)
    assert final['complete'] and final['computed'] == 1 and final['reused'] == 1
    assert p.read_bytes() == original and len(b.events)-before_events == 2
    t = len(b.events)
    finished, _ = produce(mini, directory, 'hybrid', b, resume=True)
    assert finished['computed'] == 0 and len(b.events) == t
    for row, task in zip(load_records(directory, mini), mini['tasks']):
        verify_graph(row, task, mini['diagnostics'])
    tests += ['partial resume computes pending only and preserves old bytes', 'completed resume invokes no backend']
    changed = copy.deepcopy(mini)
    changed['limits']['workers'] = 3
    try:
        produce(changed, directory, 'hybrid', b, resume=True)
    except ValueError:
        tests.append('changed resume design rejected')
    else:
        raise AssertionError('changed design accepted')
    record = read_json(p)
    record['values'][0]['optimum'] += 1
    try:
        verify_graph(record, mini['tasks'][0], mini['diagnostics'])
    except ValueError:
        tests.append('independent verifier rejects corrupted optimum')
    else:
        raise AssertionError('corruption accepted')
    fallback = Backend('hybrid', disabled=True)
    sub = make_design('exploration', (20,), (2,), repetitions=1, diagnostic_count=1)
    fallback_dir = OUT / 'fallback_check'
    produce(sub, fallback_dir, 'hybrid', fallback)
    rows = semantic_rows(fallback_dir, sub)
    expected = [r for r in semantic_rows(baseline, design) if r['task'] == sub['tasks'][0]]
    assert rows == expected and fallback.events[0]['selected'] == 'compiled'
    verify_graph(load_records(fallback_dir, sub)[0], sub['tasks'][0], sub['diagnostics'])
    tests.append('unavailable CUDA falls back to CPU and complete graph output matches baseline')
    wide = [[1 << 64, 1, (1 << 64) | 1]]
    assert b(wide) == [r2.all_budget_optima(wide[0])]
    tests.append('wide masks use original arbitrary-precision CPU')
    for invalid in [[], [[]], [[-1]], [[True]], [[1]*21], [[1], [1, 2]]]:
        try:
            b(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid backend input accepted')
    tests.append('six invalid input classes rejected before fallback')
    write_json(OUT / 'checks.json', {'passed': True, 'checks': tests, 'fallback_events': fallback.events})


def run():
    plan = read_json(OUT / 'plan.json')
    if (OUT / 'runs').exists():
        raise ValueError('runs already exist; preserve previous measurements')
    from pipeline_backends import Backend
    import scipy.stats
    started = time.perf_counter()
    backends = {name: Backend(name) for name in ('compiled', 'hybrid')}
    warm = {}
    for name, b in backends.items():
        t = time.perf_counter()
        for n in (12, 16, 20):
            b([[1 << i for i in range(n)]])
        warm[name] = time.perf_counter()-t
        b.events.clear()
    design = plan['design']
    baseline = None
    rows = []
    for repeat in range(plan['repeats']):
        order = plan['modes'][repeat:] + plan['modes'][:repeat]
        for mode in order:
            directory = OUT / 'runs' / f'{repeat}-{mode}'
            metrics = pipeline(design, directory, mode, backends.get(mode))
            if baseline is None:
                baseline = directory
            assert semantic_rows(directory, design) == semantic_rows(baseline, design), mode
            for name in ('cell_summary.csv', 'budget_results.csv', 'mechanism_summary.csv'):
                assert (directory/name).read_bytes() == (baseline/name).read_bytes(), (mode, name)
            rows.append({'repeat': repeat, 'mode': mode, **metrics})
            write_json(OUT / 'measurements.json', rows)
            print(mode, repeat, f"total={metrics['total_seconds']:.3f}s production={metrics['production_seconds']:.3f}s", flush=True)
            if time.perf_counter()-started > plan['wall_limit_seconds']:
                raise RuntimeError('local 600 second experiment limit exhausted; preserve partial results')
    checks(design, backends, baseline)
    summary = {}
    for mode in plan['modes']:
        summary[mode] = {}
        for field in ('production_seconds', 'analysis_seconds', 'summary_verification_seconds', 'total_seconds'):
            samples = [r[field] for r in rows if r['mode'] == mode]
            summary[mode][field] = {'median': statistics.median(samples), 'min': min(samples), 'max': max(samples)}
    write_json(OUT / 'summary.json', {'status': 'complete', 'modes': summary, 'warmup_seconds': warm,
        'events': {name:b.events for name,b in backends.items()},
        'wall_seconds': time.perf_counter()-started, 'parity': 'all semantic graph fields and all three CSVs identical in all 12 runs'})
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'run'])
    args = parser.parse_args()
    prepare() if args.command == 'prepare' else run()
