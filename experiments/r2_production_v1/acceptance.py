"""Pilot then full acceptance for the first public production backend release."""
from pathlib import Path
import argparse
import json
import importlib.metadata
import statistics
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'analysis'),str(ROOT/'src')]
from r2_design import make_design,read_json,write_json,load_records

SOURCE=Path(r'D:\test area\greedy-failure\greedy-failure-structures\results\r4_source\results\r2_grid_v1')
MODES=[('python',4),('numba',4),('cuda',1)]

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()

def prepare():
    if (HERE/'plan.json').exists(): raise ValueError('plan already exists')
    assert not git('diff','--name-only','HEAD')
    cases=[]
    for size,repetitions,count in [(9,1,1),(1800,200,3)]:
        design=make_design('exploration',repetitions=repetitions,diagnostic_count=min(32,repetitions))
        write_json(HERE/f'config-{size}.json',design)
        assert design['tasks']==[t for t in read_json(SOURCE/'config.json')['tasks'] if t['repetition']<repetitions]
        for repeat in range(count):
            for backend,workers in MODES[repeat:]+MODES[:repeat]:
                cases.append({'id':f'n{size}-r{repeat}-{backend}','size':size,'repeat':repeat,'backend':backend,'workers':workers})
    write_json(HERE/'plan.json',{'code_commit':git('rev-parse','HEAD'),'cases':cases,'source':str(SOURCE),
        'verification_backend':'numba','verification_workers':4,'wall_budget_seconds':7200,'stage_timeout_seconds':1200,
        'memory_budget_bytes':6*1024**3,'output_budget_bytes':2*1024**3,
        'scope':'per-graph production only; python4,numba4,cuda1 are different supported execution configurations, not a pure hardware comparison',
        'timing':'fresh CLI per stage; run -> analyze no-plot -> summary verification; all process startup/import/cache-load/I/O included; pilot warms JIT disk caches; shared ASCII CUDA cache reused; post-run parity checks excluded',
        'acceptance':'pilot must pass before full; all source semantics and three CSVs identical per size; real CUDA events required; fresh production only'})
    write_json(HERE/'environment.json',{'python':sys.version,'executable':sys.executable,
        'packages':{n:importlib.metadata.version(n) for n in ('numpy','numba','cupy-cuda12x','scipy','nvidia-cuda-runtime-cu12','nvidia-cuda-nvrtc-cu12')}})

def comparable(row): return {k:v for k,v in row.items() if k!='timing'}

def verify(directory,design,baseline,case):
    records=load_records(directory,design)
    status=read_json(directory/'run_status.json')
    assert status['complete'] and status['computed']==case['size'] and status['reused']==0
    assert read_json(directory/'config.json')==design
    for row in records:
        name=row['task']['base_graph_id']+'.json'
        assert comparable(row)==comparable(read_json(SOURCE/'graphs'/name)),name
        if baseline:
            assert comparable(row)==comparable(read_json(baseline/'graphs'/name)),name
    if baseline:
        for name in ('budget_results.csv','cell_summary.csv','mechanism_summary.csv'):
            assert (directory/name).read_bytes()==(baseline/name).read_bytes(),name
    check=read_json(directory/'summary_verification.json')
    assert check['status']=='passed' and check['budget_rows']==sum(len(t['budgets']) for t in design['tasks'])
    if case['backend']!='python':
        events=[json.loads(s) for s in (directory/'production_backend.jsonl').read_text().splitlines()]
        completed=[e for e in events if e['status']=='complete']
        assert len(completed)==case['size'] and all(e['actual_backend']==case['backend'] for e in completed)
        assert {e['graph_id'] for e in completed}=={t['base_graph_id'] for t in design['tasks']}
        if case['backend']=='cuda':
            assert len({e['owner_pid'] for e in completed})==1
            assert all(e['pool_retained_bytes']<=e['pool_limit_bytes'] for e in completed)
    return {'graphs':len(records),'all_semantics_and_csvs_equal':True,'fresh':True}

def run():
    plan=read_json(HERE/'plan.json')
    assert git('rev-parse','HEAD')==plan['code_commit'] and not git('diff','--name-only','HEAD')
    started=time.perf_counter();baselines={}
    prior=sum(read_json(p)['total_seconds'] for p in (HERE/'runs').glob('*/attempt*/result.json'))
    for index,case in enumerate(plan['cases']):
        folder=HERE/'runs'/case['id']
        if (folder/'result.json').exists():
            old=read_json(folder/'result.json');assert old['status']=='passed' and old['case']==case
            baselines.setdefault(case['size'],Path(old['output']));continue
        attempt=folder/f"attempt{len(list(folder.glob('attempt*')))+1}";attempt.mkdir(parents=True)
        output=attempt/'output';design=read_json(HERE/f"config-{case['size']}.json")
        run_args=['run','--config',str(HERE/f"config-{case['size']}.json"),'--output',str(output),
            '--workers',str(case['workers']),'--production-backend',case['backend']]
        if case['backend']=='cuda': run_args+=['--cuda-cache-dir',str(HERE/'cuda-cache')]
        commands=[('production','r2_budget_grid.py',run_args),
            ('analysis','r2_budget_grid.py',['analyze','--output',str(output),'--no-plot','--verification-backend','numba','--verification-workers','4']),
            ('summary','validate_r2_budget_grid.py',['--output',str(output),'--summaries-only'])]
        result={'case':case,'output':str(output),'stages':{},'status':'running'}
        tick=time.perf_counter()
        print('START',index+1,len(plan['cases']),case['id'],flush=True)
        try:
            for name,script,args in commands:
                remaining=plan['wall_budget_seconds']-prior-(time.perf_counter()-started)
                if remaining<=0: raise RuntimeError('acceptance wall budget exhausted')
                log=attempt/(name+'.log')
                write_json(HERE/'progress.json',{'status':'running','index':index+1,'total':len(plan['cases']),
                    'case':case,'stage':name,'log':str(log)})
                before=time.perf_counter()
                with log.open('w',encoding='utf-8') as handle:
                    p=subprocess.Popen([sys.executable,str(ROOT/'analysis'/script),*args],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
                    try: code=p.wait(timeout=min(remaining,plan['stage_timeout_seconds']))
                    except subprocess.TimeoutExpired:
                        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True);p.wait();code=-1
                result['stages'][name]={'seconds':time.perf_counter()-before,'returncode':code}
                write_json(attempt/(name+'_timing.json'),result['stages'][name])
                print(case['id'],name,result['stages'][name],flush=True)
                if code: raise RuntimeError(f'{name} failed; see preserved log')
            result['total_seconds']=time.perf_counter()-tick
            result['checks']=verify(output,design,baselines.get(case['size']),case)
            baselines.setdefault(case['size'],output)
            result['status']='passed'
            write_json(attempt/'result.json',result);write_json(folder/'result.json',result)
            print('DONE',case['id'],round(result['total_seconds'],3),'parity passed',flush=True)
            if sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())>plan['output_budget_bytes']:
                raise RuntimeError('acceptance output budget exhausted')
        except Exception as error:
            result.setdefault('total_seconds',time.perf_counter()-tick)
            result.update(status='failed',error=f'{type(error).__name__}: {error}')
            write_json(attempt/'result.json',result)
            write_json(HERE/'progress.json',{'status':'failed','case':case,'error':str(error)});raise
    summarize()

def summarize():
    plan=read_json(HERE/'plan.json');rows=[read_json(HERE/'runs'/c['id']/'result.json') for c in plan['cases']]
    assert all(r['status']=='passed' for r in rows)
    groups={}
    for backend,_ in MODES:
        selected=[r for r in rows if r['case']['size']==1800 and r['case']['backend']==backend]
        assert len(selected)==3
        group={}
        for stage in ('production','analysis','summary','total'):
            values=[r['total_seconds'] if stage=='total' else r['stages'][stage]['seconds'] for r in selected]
            group[stage]={'median':statistics.median(values),'min':min(values),'max':max(values)}
        groups[backend]=group
    write_json(HERE/'acceptance_summary.json',{'status':'complete','groups':groups,'all_parity_passed':True,
        'pilot_runs':3,'full_runs':9,'total_seconds':sum(r['total_seconds'] for r in rows),'code_commit':plan['code_commit']})
    write_json(HERE/'progress.json',{'status':'complete','runs':12})
    print(json.dumps(groups,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','summarize'])
    {'prepare':prepare,'run':run,'summarize':summarize}[p.parse_args().command]()
