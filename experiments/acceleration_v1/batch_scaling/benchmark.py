"""Fixed-corpus command-level scaling experiment; no algorithm changes."""
from pathlib import Path
import argparse
import ctypes
import importlib.metadata
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT/'analysis'), str(ROOT/'src')]
from r2_design import make_design, validate_design, load_records, read_json, write_json

SOURCE = Path(r'D:\test area\greedy-failure\greedy-failure-structures\results\r4_source\results\r2_grid_v1')
MODES = [('numba',1),('numba',2),('numba',4),('python',4)]


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def prepare():
    if (HERE/'plan.json').exists():
        raise ValueError('existing fixed plan must be reused')
    started = time.perf_counter()
    source_design = validate_design(read_json(SOURCE/'config.json'))
    source_rows = load_records(SOURCE,source_design)
    assert len(source_rows)==1800 and source_design['repetitions']==200
    assert not git('diff','--name-only','HEAD')
    datasets=[]
    for repetitions in (10,40,200):
        design=make_design('exploration',repetitions=repetitions,diagnostic_count=min(32,repetitions))
        size=len(design['tasks'])
        directory=HERE/'data'/str(size)
        write_json(directory/'config.json',design)
        by_id={r['task']['base_graph_id']:r for r in source_rows}
        for task in design['tasks']:
            assert by_id[task['base_graph_id']]['task']==task
            original=SOURCE/'graphs'/(task['base_graph_id']+'.json')
            target=directory/'graphs'/original.name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(original,target)
            assert target.read_bytes()==original.read_bytes()
        load_records(directory,design)
        datasets.append({'size':size,'repetitions_per_cell':repetitions,
            'diagnostic_graphs':sum(t['diagnostic_k'] is not None for t in design['tasks']),
            'budget_rows':sum(len(t['budgets']) for t in design['tasks'])})
    cases=[]
    for d in datasets:
        for repeat in range(3):
            order=MODES[repeat:]+MODES[:repeat]
            for position,(backend,workers) in enumerate(order):
                cases.append({'id':f"b{d['size']}-r{repeat}-{backend}-w{workers}",
                    'size':d['size'],'repeat':repeat,'position':position,
                    'backend':backend,'workers':workers})
    write_json(HERE/'plan.json',{'source':str(SOURCE),'source_archive_commit':'4a419f338d70068fa988fa97027734cdcda0a036',
        'code_commit':git('rev-parse','HEAD'),'datasets':datasets,'cases':cases,
        'primary_metric':'wall seconds from subprocess launch to successful exit, including Python/Numba imports, JIT cache loading, fresh pool startup/shutdown, file read/check, full independent graph/diagnostic validation and report write',
        'secondary_metric':'validate_batch wall_seconds and per-graph base/diagnostic wall totals (totals are not parallel wall time)',
        'cache_policy':'precompile one tiny kernel before timing; use fresh interpreter and fresh worker pool for every case; OS file and JIT disk caches may be warm; no thread/power settings changed',
        'selection':'first 10/40/200 original repetitions in each of nine n,d cells, without filtering outcomes; diagnostic proportions differ',
        'repeats':3,'wall_budget_seconds':7200,'per_case_timeout_seconds':1200,
        'memory_budget_bytes':6*1024**3,'output_budget_bytes':2*1024**3,
        'scope':'verification only, no instance regeneration/production, analysis/bootstrap/plotting or pipeline speed claim',
        'preparation_seconds':time.perf_counter()-started})
    write_json(HERE/'environment.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
        'processor':platform.processor(),'logical_cpus':os.cpu_count(),
        'packages':{n:importlib.metadata.version(n) for n in ('numpy','numba','llvmlite','scipy')},
        'power_scheme':subprocess.check_output(['powercfg','/getactivescheme'],text=True,errors='replace').strip()})
    print('Fixed plan:',datasets,'cases',len(cases),flush=True)


def run():
    plan=read_json(HERE/'plan.json')
    assert git('rev-parse','HEAD')==plan['code_commit'] and not git('diff','--name-only','HEAD')
    from verification_completion import get_completion_solver
    warm=time.perf_counter()
    assert get_completion_solver('numba')([{0},{1}],1,[],10)==(1,[0],2,2)
    warm=time.perf_counter()-warm
    write_json(HERE/'warmup.json',{'seconds':warm,'expected_result_checked':True})
    started=time.perf_counter()
    previous=sum(read_json(p)['process_wall_seconds'] for p in (HERE/'runs').glob('*/attempt*/result.json'))
    for index,case in enumerate(plan['cases']):
        directory=HERE/'runs'/case['id']
        if (directory/'result.json').exists():
            existing=read_json(directory/'result.json')
            assert existing['case']==case and existing['status']=='passed'
            continue
        remaining=plan['wall_budget_seconds']-previous-(time.perf_counter()-started)-plan['preparation_seconds']-warm
        if remaining<=0:
            raise RuntimeError('fixed experiment wall budget exhausted; preserve completed cases')
        attempt=directory/f"attempt{len(list(directory.glob('attempt*')))+1}"
        attempt.mkdir(parents=True)
        data=HERE/'data'/str(case['size'])
        command=[sys.executable,str(ROOT/'analysis/validate_r2_budget_grid.py'),'--output',str(data),
                 '--workers',str(case['workers']),'--verification-backend',case['backend']]
        write_json(HERE/'progress.json',{'case':case,'index':index+1,'total':len(plan['cases']),
            'status':'running','log':str(attempt/'command.log'),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
        print(f"START {index+1}/{len(plan['cases'])} {case['id']}",flush=True)
        tick=time.perf_counter()
        with (attempt/'command.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            try:
                code=process.wait(timeout=min(remaining,plan['per_case_timeout_seconds']))
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait()
                code=-1
        elapsed=time.perf_counter()-tick
        report_path=data/'verification.json'
        report=read_json(report_path) if report_path.exists() else {}
        result={'case':case,'process_wall_seconds':elapsed,'returncode':code,'status':'failed'}
        if code==0 and report.get('status')=='passed':
            design=read_json(data/'config.json')
            expected={t['base_graph_id'] for t in design['tasks']}
            assert set(report['graphs'])==expected and len(expected)==case['size']
            peak=max(r['peak_memory_bytes'] for r in report['graphs'].values())
            assert peak*(case['workers']+1)<=plan['memory_budget_bytes']
            result.update(status='passed',validation_wall_seconds=report['wall_seconds'],
                verified_graphs=len(expected),sum_base_seconds=sum(r['base_seconds'] for r in report['graphs'].values()),
                sum_diagnostic_seconds=sum(r['diagnostic_seconds'] for r in report['graphs'].values()),
                peak_process_bytes=peak,conservative_process_memory_bytes=peak*(case['workers']+1))
        write_json(attempt/'result.json',result)
        if report_path.exists():
            shutil.copyfile(report_path,attempt/'verification.json')
        if result['status']!='passed':
            write_json(HERE/'progress.json',{'status':'failed','case':case,'log':str(attempt/'command.log')})
            raise RuntimeError(f"case failed: {case['id']}; see its preserved log")
        write_json(directory/'result.json',result)
        write_json(HERE/'progress.json',{'status':'case_complete','case':case,'index':index+1,'total':len(plan['cases']),
            'process_wall_seconds':elapsed})
        print(f"DONE {index+1}/{len(plan['cases'])} {case['id']}: {elapsed:.3f}s",flush=True)
        if sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())>plan['output_budget_bytes']:
            raise RuntimeError('fixed output budget exhausted')
    summarize()


def summarize():
    plan=read_json(HERE/'plan.json')
    results=[read_json(HERE/'runs'/case['id']/'result.json') for case in plan['cases']]
    assert all(r['status']=='passed' for r in results)
    assert git('rev-parse','HEAD')==plan['code_commit'] and not git('diff','--name-only','HEAD')
    unchanged=0
    for d in plan['datasets']:
        directory=HERE/'data'/str(d['size'])
        design=read_json(directory/'config.json')
        expected=make_design('exploration',repetitions=d['repetitions_per_cell'],diagnostic_count=min(32,d['repetitions_per_cell']))
        assert design==expected
        for task in design['tasks']:
            name=task['base_graph_id']+'.json'
            assert (directory/'graphs'/name).read_bytes()==(SOURCE/'graphs'/name).read_bytes()
            unchanged+=1
    summaries=[]
    for d in plan['datasets']:
        row={**d,'modes':{}}
        for backend,workers in MODES:
            runs=[r for r in results if (r['case']['size'],r['case']['backend'],r['case']['workers'])==(d['size'],backend,workers)]
            values=[r['process_wall_seconds'] for r in runs]
            assert len(values)==3
            row['modes'][f'{backend}-{workers}']={'median':statistics.median(values),'min':min(values),'max':max(values),
                'peak_process_bytes':max(r['peak_process_bytes'] for r in runs)}
        summaries.append(row)
    write_json(HERE/'summary.json',{'status':'complete','summaries':summaries,'cases':len(results),
        'total_command_seconds':sum(r['process_wall_seconds'] for r in results),'copied_graph_files_unchanged':unchanged,
        'all_graphs_independently_verified_every_case':True,'code_commit':plan['code_commit']})
    write_json(HERE/'progress.json',{'status':'complete','cases':len(results)})
    print(json.dumps(summaries,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','run','summarize'])
    args=parser.parse_args()
    {'prepare':prepare,'run':run,'summarize':summarize}[args.command]()
