"""Explicit hardware tests: python scripts/check.py --profile cuda --tests-only."""
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'analysis'),str(ROOT/'src')]
from r2_cuda_backend import initialize_worker


def device_checks():
    from unittest.mock import patch
    import cupy as cp
    import r2_cuda_backend as cuda
    from r2_production_backends import solve_optima
    from r2_budget_grid import all_budget_optima
    cases=[(0,)*4, ((1<<64)-1,)*4, (1<<63,1,1<<63,0), (3,6,9,12), (0,)*20]
    for masks in cases:
        result,meta=cuda.solve(masks,instrument=True)
        if result != all_budget_optima(masks):
            raise AssertionError('GPU differs from CPU')
    try:
        cuda.solve((0,)*20,instrument=True,_test_blocks=1)
    except ValueError:
        pass
    else:
        raise AssertionError('truncated grid accepted')
    for status in (1,700):
        with patch.object(cuda,'solve',side_effect=cp.cuda.runtime.CUDARuntimeError(status)):
            try:
                solve_optima((3,5),'cuda',all_budget_optima)
            except cp.cuda.runtime.CUDARuntimeError:
                pass
            else:
                raise AssertionError('CUDA error converted to CPU success')
    return meta


@unittest.skipUnless(os.environ.get('MAXCOVER_TEST_CUDA')=='1','requires explicit --profile cuda hardware check')
class CudaProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'results').mkdir(exist_ok=True)

    def test_real_kernel_counts_boundaries_and_runtime_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'results') as tmp:
            with ProcessPoolExecutor(max_workers=1,mp_context=multiprocessing.get_context('spawn'),
                    initializer=initialize_worker,initargs=(tmp,)) as pool:
                meta=pool.submit(device_checks).result(timeout=120)
            self.assertNotEqual(meta['owner_pid'],os.getpid())
            self.assertLessEqual(meta['pool_retained_bytes'],meta['pool_limit_bytes'])

    def test_real_cuda_owner_checkpoint_and_csv(self):
        import json
        from r2_design import make_design,read_json,load_records
        from r2_budget_grid import run,analyze
        from validate_r2_budget_grid_fast import verify_graph
        from validate_r2_budget_grid import verify_summaries
        design=make_design('fixture',(5,),(2,),2,2)
        with tempfile.TemporaryDirectory(dir=ROOT/'results') as tmp:
            baseline,output=Path(tmp)/'cpu',Path(tmp)/'含中文输出'
            cache=Path(tmp)/'cuda-cache'
            run(design,baseline,workers=1)
            run(design,output,workers=1,production_backend='cuda',stop_after=1,cuda_cache_dir=cache)
            p=output/'graphs'/(design['tasks'][0]['base_graph_id']+'.json')
            saved=p.read_bytes()
            result=run(design,output,workers=1,production_backend='cuda',resume=True,cuda_cache_dir=cache)
            self.assertEqual((result['computed'],result['reused']),(1,1))
            self.assertEqual(p.read_bytes(),saved)
            for a,b in zip(load_records(baseline,design),load_records(output,design)):
                self.assertEqual({k:v for k,v in a.items() if k!='timing'},{k:v for k,v in b.items() if k!='timing'})
                verify_graph(b,b['task'],design['diagnostics'])
            events=[json.loads(line) for line in (output/'production_backend.jsonl').read_text().splitlines()]
            completed=[e for e in events if e['status']=='complete']
            self.assertEqual(len(completed),2)
            self.assertTrue(all(e['actual_backend']=='cuda' and e['owner_pid']!=os.getpid() for e in completed))
            for directory in (baseline,output):
                analyze(directory,plot=False,verification_workers=1)
                verify_summaries(directory)
            for name in ('budget_results.csv','cell_summary.csv','mechanism_summary.csv'):
                self.assertEqual((baseline/name).read_bytes(),(output/name).read_bytes())


if __name__=='__main__':
    unittest.main()
