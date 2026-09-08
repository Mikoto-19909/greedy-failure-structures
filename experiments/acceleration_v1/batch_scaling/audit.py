"""Read back raw attempts and independently check the reported timing arithmetic."""
from pathlib import Path
import json
import math

HERE=Path(__file__).resolve().parent
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
plan=read(HERE/'plan.json')
summary=read(HERE/'summary.json')
assert summary['status']=='complete'
assert len(plan['cases'])==len({c['id'] for c in plan['cases']})==36
rows=[]
for case in plan['cases']:
    directory=HERE/'runs'/case['id']
    result=read(directory/'result.json')
    assert result['case']==case and result['returncode']==0 and result['status']=='passed'
    assert result['process_wall_seconds']>=result['validation_wall_seconds']>0
    attempts=[p for p in directory.glob('attempt*/result.json') if read(p)==result]
    assert len(attempts)==1
    verification=read(attempts[0].with_name('verification.json'))
    design=read(HERE/'data'/str(case['size'])/'config.json')
    assert verification['status']=='passed'
    assert set(verification['graphs'])=={t['base_graph_id'] for t in design['tasks']}
    assert len(verification['graphs'])==case['size']==result['verified_graphs']
    assert verification['wall_seconds']==result['validation_wall_seconds']
    assert all(math.isfinite(r[field]) and r[field]>=0
               for r in verification['graphs'].values() for field in ('base_seconds','diagnostic_seconds'))
    rows.append(result)
for group in summary['summaries']:
    for name,stats in group['modes'].items():
        backend,workers=name.split('-')
        times=sorted(r['process_wall_seconds'] for r in rows
            if (r['case']['size'],r['case']['backend'],r['case']['workers'])==(group['size'],backend,int(workers)))
        assert len(times)==3
        assert (stats['min'],stats['median'],stats['max'])==tuple(times)
assert summary['total_command_seconds']==sum(r['process_wall_seconds'] for r in rows)
assert sum(r['verified_graphs'] for r in rows)==27000
result={'passed':True,'raw_attempts_checked':36,'independent_graph_checks':27000,
        'all_reported_medians_and_ranges_recomputed':True,
        'scope':'artifact readback and arithmetic; each CLI run already independently recomputed graph results'}
(HERE/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
