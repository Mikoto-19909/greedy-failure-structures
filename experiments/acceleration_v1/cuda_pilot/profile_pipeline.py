"""Profile unchanged producer diagnostics and independent R2 validation."""
from pathlib import Path
import cProfile
import io
import json
import pstats
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT/'analysis'), str(ROOT/'src')]
from r2_design import read_json, load_records, write_json
from r2_budget_grid import evaluate_task
from validate_r2_budget_grid import verify_graph

def main():
    directory = HERE/'verification_v1'
    design = read_json(HERE/'pipeline_v1/plan.json')['design']
    records = load_records(HERE/'pipeline_v1/runs/0-hybrid', design)
    for name, call in [('production', lambda: [evaluate_task(t,design['diagnostics']) for t in design['tasks']]),
                       ('verification', lambda: [verify_graph(r,t,design['diagnostics']) for r,t in zip(records,design['tasks'])])]:
        profiler = cProfile.Profile()
        start = time.perf_counter()
        profiler.runcall(call)
        elapsed = time.perf_counter()-start
        directory.mkdir(exist_ok=True)
        profiler.dump_stats(str(directory/(name+'.prof')))
        stream = io.StringIO()
        pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
        (directory/(name+'.txt')).write_text(stream.getvalue(),encoding='utf-8')
        write_json(directory/(name+'_profile.json'),{'wall_seconds_with_profiler':elapsed})
        print(name,elapsed,stream.getvalue(),flush=True)

if __name__=='__main__':
    main()
