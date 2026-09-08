"""Bounded independent-verifier optimization with actual pipeline comparisons."""
from pathlib import Path
import argparse
import copy
import itertools
import json
import statistics
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE/'verification_v1'
sys.path[:0] = [str(ROOT/'analysis'),str(ROOT/'src')]
import r2_budget_grid as r2
import validate_r2_budget_grid as verifier
import validate_greedy_failure_paths as original_paths
from r2_design import read_json,write_json,load_records


def prepare():
    if (OUT/'plan.json').exists():
        raise ValueError('plan already exists')
    write_json(OUT/'plan.json',{
        'design':read_json(HERE/'pipeline_v1/plan.json')['design'],
        'repeats':3,'modes':['original4','compiled1','compiled4'],
        'production':'unchanged local hybrid CPU/CUDA adapter from pipeline_v1',
        'change':'only independent best_completion; Boolean incidence and lex combinations, no producer kernel reuse',
        'timing':'warm imports and JIT; fresh processes and cache load included; complete run/analyze/verify_summaries including disk IO',
        'stop':'three repeats, original/new full graph and CSV parity, exhaustive small prefix checks and corruption rejection; local only',
        'wall_limit_seconds':600})


def correctness():
    import independent_completion as optimized
    design = read_json(OUT/'plan.json')['design']
    records = load_records(HERE/'pipeline_v1/runs/0-hybrid',design)
    checked = 0
    # All 3-set families over a 2-element universe; all budgets and valid prefixes.
    for masks in itertools.product(range(4), repeat=3):
        sets = [{e for e in range(2) if mask & (1<<e)} for mask in masks]
        for k in range(4):
            for length in range(k+1):
                for prefix in itertools.combinations(range(3),length):
                    for p in [list(prefix),list(reversed(prefix))]:
                        expected = original_paths.best_completion(sets,k,p,100)
                        actual = optimized.best_completion(sets,k,p,100)
                        assert actual == expected,(masks,k,p,actual,expected)
                        checked += 1
    for sets in [[{65},{1,65},set()],[set(),set()]]:
        for k in range(len(sets)+1):
            assert optimized.best_completion(sets,k,[],100) == original_paths.best_completion(sets,k,[],100)
    invalid = [(2,[0,0],100),(1,[0,1],100),(2,[],2),(1,[3],100),(-1,[],100),(1,[True],100)]
    for k,p,limit in invalid:
        try:
            optimized.best_completion([{0},{1},{2}],k,p,limit)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid completion input accepted')
    for record,task in zip(records,design['tasks']):
        optimized.verify_graph(record,task,design['diagnostics'])
        base = {'sets':record['sets'],'k':task['diagnostic_k'],'population':'r2'}
        truth = original_paths.expected_path(base,design['diagnostics'])
        with patch.object(original_paths,'best_completion',optimized.best_completion):
            actual = original_paths.expected_path(base,design['diagnostics'])
        assert actual == truth
    rejected = []
    for field in ('optimum','witness','count','path','tie','exchanges','seed','type'):
        row = copy.deepcopy(records[0])
        if field=='optimum': row['values'][0]['optimum'] += 1
        elif field=='witness': row['diagnostic']['optimum_selected'].reverse()
        elif field=='count': row['diagnostic']['optimal_solution_count'] += 1
        elif field=='path': row['diagnostic']['prefixes'][0]['optimal_completion'] += 1
        elif field=='tie': row['diagnostic']['ties'][0]['preserves_optimum'] = not row['diagnostic']['ties'][0]['preserves_optimum']
        elif field=='exchanges': row['diagnostic']['one_swap']['evaluations'] += 1
        elif field=='seed': row['task']['seed'] += 1
        else: row['diagnostic']['completion_count'] = True
        try:
            optimized.verify_graph(row,design['tasks'][0],design['diagnostics'])
        except ValueError:
            rejected.append(field)
        else:
            raise AssertionError(('corruption accepted',field))
    write_json(OUT/'checks.json',{'passed':True,'small_prefix_cases':checked,
        'full_graphs':len(records),'complete_path_parity':True,
        'corruptions_rejected':rejected,'invalid_inputs':len(invalid),
        'independence':'Boolean matrix and combinations; original reference, coverage, exchange, structural, identity and typed comparisons retained; no producer calculation imports'})
    print('Correctness passed',checked,'small prefix cases',flush=True)


def run():
    plan = read_json(OUT/'plan.json')
    if (OUT/'runs').exists():
        raise ValueError('existing measurements preserved')
    from pipeline_trial import produce,semantic_rows
    from pipeline_backends import Backend
    import independent_completion as optimized
    import scipy.stats
    t = time.perf_counter()
    backend = Backend('hybrid')
    for n in (12,16,20):
        backend([[1<<i for i in range(n)]])
    optimized.best_completion([{0},{1},{0,1}],2,[],100)
    warmup = time.perf_counter()-t
    measurements = []
    baseline = HERE/'pipeline_v1/runs/0-hybrid'
    started = time.perf_counter()
    for repeat in range(plan['repeats']):
        modes = plan['modes'][repeat:]+plan['modes'][:repeat]
        for mode in modes:
            design = copy.deepcopy(plan['design'])
            design['limits']['workers'] = 1 if mode=='compiled1' else 4
            output = OUT/'runs'/f'{repeat}-{mode}'
            t = time.perf_counter()
            produce(design,output,'hybrid',backend)
            produced = time.perf_counter()
            if mode=='original4':
                r2.analyze(output,plot=False)
            else:
                with patch.object(verifier,'verify_graph',optimized.verify_graph):
                    r2.analyze(output,plot=False)
            analyzed = time.perf_counter()
            verifier.verify_summaries(output)
            finished = time.perf_counter()
            assert semantic_rows(output,design)==semantic_rows(baseline,plan['design'])
            for file in ('cell_summary.csv','budget_results.csv','mechanism_summary.csv'):
                assert (output/file).read_bytes()==(baseline/file).read_bytes()
            row={'mode':mode,'repeat':repeat,'total_seconds':finished-t,
                'production_seconds':produced-t,'analysis_seconds':analyzed-produced,
                'summary_verification_seconds':finished-analyzed}
            measurements.append(row)
            write_json(OUT/'measurements.json',measurements)
            print(row,flush=True)
            if time.perf_counter()-started>plan['wall_limit_seconds']:
                raise RuntimeError('trial wall limit reached')
    summary={}
    for mode in plan['modes']:
        summary[mode]={}
        for field in ('total_seconds','production_seconds','analysis_seconds','summary_verification_seconds'):
            values=[row[field] for row in measurements if row['mode']==mode]
            summary[mode][field]={'median':statistics.median(values),'min':min(values),'max':max(values)}
    write_json(OUT/'summary.json',{'status':'complete','modes':summary,'warmup_seconds':warmup,
        'wall_seconds':time.perf_counter()-started,'graph_and_csv_parity':True})
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','check','run'])
    command=parser.parse_args().command
    {'prepare':prepare,'check':correctness,'run':run}[command]()
