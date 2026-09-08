"""Fixed six-run R2 end-to-end A/B acceptance, using the public CLI."""
from pathlib import Path
import argparse
import csv
import importlib.metadata
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'analysis'),str(ROOT/'src')]
from r2_design import read_json,write_json,validate_design,load_records

SOURCE=Path(r'D:\test area\greedy-failure\greedy-failure-structures\results\r4_source\results\r2_grid_v1')
CONFIG=ROOT/'results/batch-scaling-v1/data/1800/config.json'
TABLES=('budget_results.csv','cell_summary.csv','mechanism_summary.csv')


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def prepare():
    if (HERE/'plan.json').exists():
        raise ValueError('reuse the existing fixed plan')
    started=time.perf_counter()
    design=validate_design(read_json(CONFIG))
    original=validate_design(read_json(SOURCE/'config.json'))
    assert design['tasks']==original['tasks'] and len(design['tasks'])==1800
    assert not git('diff','--name-only','HEAD')
    cases=[]
    for repeat,order in enumerate((('python','numba'),('numba','python'),('python','numba'))):
        for position,backend in enumerate(order):
            cases.append({'id':f'r{repeat}-{backend}','repeat':repeat,'position':position,'backend':backend})
    write_json(HERE/'config.json',design)
    write_json(HERE/'plan.json',{'code_commit':git('rev-parse','HEAD'),'source_archive':str(SOURCE),
        'source_config':str(CONFIG),'cases':cases,'graphs':1800,
        'budget_rows':sum(len(t['budgets']) for t in design['tasks']),
        'diagnostic_graphs':sum(t['diagnostic_k'] is not None for t in design['tasks']),
        'production_workers':4,'verification_workers':4,
        'stages':['production','analysis_with_independent_graph_verification','summary_verification'],
        'primary_metric':'wall time from first production process launch sequence to exit of summary verification; includes all three command startups, imports, JIT cache load, fresh pools, computation, diagnosis, data I/O and orchestration between stages',
        'cache_policy':'one tiny known-answer Numba precompile before measurement; each stage starts a new Python process; disk/JIT caches may be warm, all dependency imports inside stage commands count',
        'fresh_runs':'no checkpoint resume for timed production; each case has its own new output directory',
        'acceptance':'all 1800 non-timing graph records equal archived originals and all six runs; all three CSVs byte-identical across runs; 13000 budget rows; independent summary verification passed',
        'scope':'full declared no-plot R2 workflow; original CPU production only; no CUDA production or plotting; no duplicate separate graph-verification command',
        'wall_budget_seconds':7200,'stage_timeout_seconds':1200,'output_budget_bytes':2*1024**3,
        'memory_budget_bytes':6*1024**3,'preparation_seconds':time.perf_counter()-started})
    write_json(HERE/'environment.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
        'processor':platform.processor(),'logical_cpus':os.cpu_count(),
        'packages':{n:importlib.metadata.version(n) for n in ('numpy','numba','llvmlite','scipy')},
        'power_scheme':subprocess.check_output(['powercfg','/getactivescheme'],text=True,errors='replace').strip()})
    print('Plan fixed: six fresh runs, 1800 graphs and 13000 budget rows per run',flush=True)


def stable(record):
    return {key:value for key,value in record.items() if key!='timing'}


def check_artifacts(directory,design,baseline):
    status=read_json(directory/'run_status.json')
    assert status['complete'] and status['computed']==1800 and status['reused']==0
    assert read_json(directory/'config.json')==design
    records=load_records(directory,design)
    for record in records:
        name=record['task']['base_graph_id']+'.json'
        assert stable(record)==stable(read_json(SOURCE/'graphs'/name)),name
        if baseline is not None:
            assert stable(record)==stable(read_json(baseline/'graphs'/name)),name
    with (directory/'budget_results.csv').open(encoding='utf-8',newline='') as handle:
        assert sum(1 for _ in csv.DictReader(handle))==13000
    summary=read_json(directory/'summary_verification.json')
    assert summary['status']=='passed' and summary['budget_rows']==13000
    if baseline is not None:
        for name in TABLES:
            assert (directory/name).read_bytes()==(baseline/name).read_bytes(),name
    peak=max(r['timing']['peak_memory_bytes'] for r in records)
    return {'graph_records':len(records),'budget_rows':13000,'source_semantics_equal':True,
        'baseline_semantics_equal':True,'three_csvs_equal':True,
        'production_peak_process_bytes':peak,'production_conservative_memory_bytes':peak*5}


def run():
    plan=read_json(HERE/'plan.json')
    design=read_json(HERE/'config.json')
    assert git('rev-parse','HEAD')==plan['code_commit'] and not git('diff','--name-only','HEAD')
    from verification_completion import get_completion_solver
    before=time.perf_counter()
    assert get_completion_solver('numba')([{0},{1}],1,[],10)==(1,[0],2,2)
    warm=time.perf_counter()-before
    write_json(HERE/'warmup.json',{'seconds':warm,'known_answer_passed':True})
    started=time.perf_counter()
    prior=sum(read_json(p)['pipeline_wall_seconds'] for p in (HERE/'runs').glob('*/attempt*/result.json'))
    baseline=None
    for index,case in enumerate(plan['cases']):
        folder=HERE/'runs'/case['id']
        if (folder/'result.json').exists():
            result=read_json(folder/'result.json')
            assert result['case']==case and result['status']=='passed'
            if baseline is None:
                baseline=Path(result['output'])
            continue
        attempt=folder/f"attempt{len(list(folder.glob('attempt*')))+1}"
        output=attempt/'output'
        attempt.mkdir(parents=True)
        stages=[('production',['r2_budget_grid.py','run','--config',str(HERE/'config.json'),'--output',str(output),'--workers','4']),
            ('analysis',['r2_budget_grid.py','analyze','--output',str(output),'--no-plot','--verification-backend',case['backend'],'--verification-workers','4']),
            ('summary_verification',['validate_r2_budget_grid.py','--output',str(output),'--summaries-only'])]
        print(f"START {index+1}/6 {case['id']}",flush=True)
        result={'case':case,'output':str(output),'status':'incomplete','stages':{}}
        pipeline_start=time.perf_counter()
        try:
            for name,args in stages:
                remaining=plan['wall_budget_seconds']-prior-(time.perf_counter()-started)-warm-plan['preparation_seconds']
                if remaining<=0:
                    raise RuntimeError('fixed overall wall budget exhausted')
                log_path=attempt/(name+'.log')
                command=[sys.executable,str(ROOT/'analysis'/args[0]),*args[1:]]
                write_json(HERE/'progress.json',{'status':'running','case':case,'index':index+1,'total':6,
                    'stage':name,'log':str(log_path),'output':str(output),
                    'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
                tick=time.perf_counter()
                with log_path.open('w',encoding='utf-8') as handle:
                    process=subprocess.Popen(command,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
                    try:
                        code=process.wait(timeout=min(remaining,plan['stage_timeout_seconds']))
                    except subprocess.TimeoutExpired:
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                        process.wait()
                        code=-1
                elapsed=time.perf_counter()-tick
                result['stages'][name]={'wall_seconds':elapsed,'returncode':code,'command':command}
                write_json(attempt/(name+'_timing.json'),result['stages'][name])
                print(f"STAGE {case['id']} {name}: {elapsed:.3f}s code={code}",flush=True)
                if code!=0:
                    raise RuntimeError(f'{name} failed; preserve logs and checkpoints')
            result['pipeline_wall_seconds']=time.perf_counter()-pipeline_start
            assert all(s['returncode']==0 for s in result['stages'].values())
            # Acceptance comparisons are extra checks, outside measured pipeline time.
            result['acceptance']=check_artifacts(output,design,baseline)
            assert result['acceptance']['production_conservative_memory_bytes']<=plan['memory_budget_bytes']
            if baseline is None:
                baseline=output
            result['status']='passed'
            write_json(attempt/'result.json',result)
            write_json(folder/'result.json',result)
            write_json(HERE/'progress.json',{'status':'case_complete','case':case,'index':index+1,'total':6,
                'pipeline_wall_seconds':result['pipeline_wall_seconds']})
            print(f"DONE {index+1}/6 {case['id']}: {result['pipeline_wall_seconds']:.3f}s; artifact parity passed",flush=True)
            if sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())>plan['output_budget_bytes']:
                raise RuntimeError('fixed output budget exhausted')
        except Exception as error:
            result.setdefault('pipeline_wall_seconds',time.perf_counter()-pipeline_start)
            result.update(status='failed',error=f'{type(error).__name__}: {error}')
            write_json(attempt/'result.json',result)
            write_json(HERE/'progress.json',{'status':'failed','case':case,'error':str(error),'attempt':str(attempt)})
            raise
    summarize()


def summarize():
    plan=read_json(HERE/'plan.json')
    assert git('rev-parse','HEAD')==plan['code_commit'] and not git('diff','--name-only','HEAD')
    rows=[read_json(HERE/'runs'/c['id']/'result.json') for c in plan['cases']]
    assert all(r['status']=='passed' and all(s['returncode']==0 for s in r['stages'].values()) for r in rows)
    modes={}
    for backend in ('python','numba'):
        chosen=[r for r in rows if r['case']['backend']==backend]
        assert len(chosen)==3
        modes[backend]={}
        for field in ('total','production','analysis','summary_verification'):
            values=[r['pipeline_wall_seconds'] if field=='total' else r['stages'][field]['wall_seconds'] for r in chosen]
            modes[backend][field]={'median':statistics.median(values),'min':min(values),'max':max(values)}
    pairs=[]
    for repeat in range(3):
        times={r['case']['backend']:r['pipeline_wall_seconds'] for r in rows if r['case']['repeat']==repeat}
        pairs.append({'repeat':repeat,**times,'speedup':times['python']/times['numba'],
            'saved_seconds':times['python']-times['numba'],'reduction_percent':100*(1-times['numba']/times['python'])})
    write_json(HERE/'summary.json',{'status':'complete','modes':modes,'pairs':pairs,
        'runs':6,'fresh_graph_computations':10800,'budget_records':78000,
        'all_graph_and_csv_parity_passed':True,'total_pipeline_seconds':sum(r['pipeline_wall_seconds'] for r in rows),
        'max_production_conservative_memory_bytes':max(r['acceptance']['production_conservative_memory_bytes'] for r in rows)})
    write_json(HERE/'progress.json',{'status':'complete','runs':6})
    print(json.dumps(modes,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','run','summarize'])
    args=parser.parse_args()
    {'prepare':prepare,'run':run,'summarize':summarize}[args.command]()
