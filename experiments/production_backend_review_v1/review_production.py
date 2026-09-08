from pathlib import Path
import os,sys,ast,itertools,json,tempfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=Path(r'D:/test area/greedy-failure/greedy-failure-structures/results/cuda_trial_v1')
os.environ['CUPY_CACHE_DIR']=str(HERE/'cupy_cache')
os.environ['CUDA_PATH']=str(OLD/'.venv/Lib/site-packages/nvidia/cuda_runtime')
(HERE/'tmp').mkdir(exist_ok=True)
tempfile.tempdir=str(HERE/'tmp')
sys.path[:0]=[str(ROOT/'analysis'),str(ROOT/'src')]
import numpy as np
from numba import njit
from r2_budget_grid import all_budget_optima
trial_ast=ast.parse((ROOT/'experiments/acceleration_v1/cuda_pilot/trial.py').read_text())
cuda=ast.literal_eval(next(n.value for n in trial_ast.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CUDA_SOURCE' for t in n.targets)))
cpu_node=next(n for n in ast.walk(trial_ast) if isinstance(n,ast.FunctionDef) and n.name=='cpu_scores')
cpu_node.decorator_list=[]
namespace={'np':np,'all_budget_optima':all_budget_optima,'CUDA_SOURCE':cuda}
exec(compile(ast.Module(body=[cpu_node],type_ignores=[]),str(HERE/'cpu_extracted.py'),'exec'),namespace)
namespace['CPU_SCORES']=njit(namespace['cpu_scores'])
backend_ast=ast.parse((ROOT/'experiments/acceleration_v1/cuda_pilot/pipeline_backends.py').read_text())
exec(compile(ast.Module(body=[n for n in backend_ast.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))],type_ignores=[]),str(HERE/'backend_extracted.py'),'exec'),namespace)
Backend=namespace['Backend']
b=Backend('hybrid')
fixtures=[[0]*4,[2**64-1]*4,[1<<63,1,1<<63,0],[3,6,9,12],[0,0,1,0]]
def reference(masks):
    sets=[{i for i in range(64) if mask>>i&1} for mask in masks]
    values=[]; witnesses=[]
    for k in range(len(sets)+1):
        candidates=[]
        for selected in itertools.combinations(range(len(sets)),k):
            covered=set()
            for i in selected: covered.update(sets[i])
            candidates.append((len(covered),selected))
        best=max(v for v,w in candidates)
        values.append(best); witnesses.append(min(w for v,w in candidates if v==best))
    return values,witnesses,2**len(masks)
expected=[reference(f) for f in fixtures]
assert b.cpu(fixtures)==expected
assert b.gpu(fixtures)==expected
assert b.cpu([[0]*20])[0]==([0]*21,[tuple(range(k)) for k in range(21)],2**20)
assert b.gpu([[0]*20])[0]==([0]*21,[tuple(range(k)) for k in range(21)],2**20)
wide=[[1<<64,0,1,(1<<64)|1]]
assert b(wide)==[all_budget_optima(wide[0])]
assert b.events[-1]['selected']=='python'
print('CPU/CUDA 5 x m4 plus m20 all-empty: 46 budget outcomes per backend passed; wide-mask Python fallback passed',flush=True)
# CUDA error code 1 (invalid value) is caught indiscriminately by this prototype.
cp=b.cp
b.gpu=lambda batch: (_ for _ in ()).throw(cp.cuda.runtime.CUDARuntimeError(1))
assert b([[0]*20])[0]==([0]*21,[tuple(range(k)) for k in range(21)],2**20)
assert b.events[-1]['selected']=='compiled'
print('Confirmed prototype swallows injected cudaErrorInvalidValue into compiled fallback:',b.events[-1]['fallback'],flush=True)
try: b([[]])
except ValueError: print('Confirmed prototype rejects m0 while original returns',all_budget_optima([]),flush=True)
else: raise AssertionError('m0 unexpectedly accepted')
report={'passed':True,'budgets_per_backend':46,'fixtures':fixtures,'max_packed_score_m20':(64<<20)|((1<<20)-1),'invalid_value_fallback':b.events[-1],'limits':'small functional checks; no performance measurement; source AST extracted to avoid archival import side effects'}
(HERE/'review_checks.json').write_text(json.dumps(report,indent=2))
