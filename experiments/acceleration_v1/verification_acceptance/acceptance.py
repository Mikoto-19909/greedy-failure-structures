"""Run the formal CLI on a copy of the previous nine-graph trial."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'analysis'),str(ROOT/'src')]
from r2_design import make_design
from r2_budget_grid import run

SOURCE = Path(r'D:\test area\greedy-failure\greedy-failure-structures\results\cuda_trial_v1\pipeline_v1\runs\0-hybrid')
OUT = ROOT/'results/fast-verification/acceptance'
if OUT.exists():
    raise ValueError('preserve existing acceptance output')
shutil.copytree(SOURCE,OUT/'nine-graphs')
directory = OUT/'nine-graphs'
originals = {p.relative_to(directory):p.read_bytes() for p in directory.glob('graphs/*.json')}
originals[Path('config.json')] = (directory/'config.json').read_bytes()
tables = {name:(directory/name).read_bytes() for name in ('cell_summary.csv','budget_results.csv','mechanism_summary.csv')}
results=[]

def cli(executable,script,args,success=True):
    p=subprocess.run([str(executable),str(ROOT/'analysis'/script),*map(str,args)],
                     cwd=ROOT,text=True,capture_output=True,timeout=180)
    results.append({'script':script,'args':list(map(str,args)),'returncode':p.returncode,
                    'stdout':p.stdout,'stderr':p.stderr})
    assert (p.returncode==0)==success,results[-1]
    print(script, 'passed expected outcome',flush=True)
    return p

cli(sys.executable,'validate_r2_budget_grid.py',['--output',directory,'--workers',1,'--verification-backend','numba'])
cli(sys.executable,'r2_budget_grid.py',['analyze','--output',directory,'--no-plot','--verification-backend','numba','--verification-workers',1])
cli(sys.executable,'validate_r2_budget_grid.py',['--output',directory,'--workers',1])
for name,content in originals.items():
    assert (directory/name).read_bytes()==content,name
for name,content in tables.items():
    assert (directory/name).read_bytes()==content,name

# The main repository's original environment has no Numba installed.
plain = Path(r'D:\test area\greedy-failure\greedy-failure-structures\.venv\Scripts\python.exe')
probe=subprocess.run([str(plain),'-c',"import importlib.util; assert importlib.util.find_spec('numba') is None"],capture_output=True,text=True)
assert probe.returncode==0,probe.stderr
fixture=OUT/'no-numba'
run(make_design('fixture',(4,),(2,),1,1),fixture,workers=1)
fallback=cli(plain,'validate_r2_budget_grid.py',['--output',fixture,'--workers',1,'--verification-backend','auto'])
assert 'original Python' in fallback.stderr
cli(plain,'validate_r2_budget_grid.py',['--output',fixture,'--workers',1,'--verification-backend','numba'],success=False)
(OUT/'acceptance.json').write_text(json.dumps({'passed':True,'graphs':9,'graph_bytes_unchanged':True,
    'config_bytes_unchanged':True,'three_csvs_unchanged':True,'actual_dependency_absence_tested':True,
    'commands':results},ensure_ascii=False,indent=2),encoding='utf-8')
print('Acceptance complete',flush=True)
