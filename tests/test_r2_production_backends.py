"""Exact CPU production, timing boundaries, fallback and checkpoint integration."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'analysis'), str(ROOT / 'src')]
import r2_budget_grid as production
import r2_production_backends as backends
from r2_design import make_design, read_json, write_json, load_records
from validate_r2_budget_grid import reference, verify_summaries
from validate_r2_budget_grid_fast import verify_graph


def _slow_owner_task(marker):
    Path(marker).write_text('started')
    time.sleep(3)
    return None


class ProductionBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'results').mkdir(exist_ok=True)

    def tearDown(self):
        backends._numba_backend.cache_clear()

    def test_numba_exactness_and_bounds(self):
        families = list(itertools.product(range(4), repeat=3))
        families += [(), (0,)*20, ((1 << 64)-1, 1 << 63, 0, 1)]
        for masks in families:
            result, event = backends.solve_optima(masks, 'numba', production.all_budget_optima)
            self.assertEqual(result, production.all_budget_optima(masks))
            elements = [{i for i in range(64) if mask & (1 << i)} for mask in masks]
            # The M=20 all-zero case has an immediate known answer for every k.
            for k in range(len(masks)+1):
                expected = (0, list(range(k))) if len(masks)==20 else reference(elements, k)
                self.assertEqual((result[0][k], list(result[1][k])), expected)
        for masks in ((-1,), (True,), (1 << 64,), (0,)*21):
            with self.assertRaises(ValueError):
                backends.solve_optima(masks, 'numba', production.all_budget_optima)
        for masks in ((1 << 64, 1),):
            result, event = backends.solve_optima(masks, 'auto', production.all_budget_optima)
            self.assertEqual(result, production.all_budget_optima(masks))
            self.assertEqual(event['actual_backend'], 'python')
        with self.assertRaises(ValueError):
            backends.check_result((3, 3), ([0, 2, 2], [(), (0,), (0, 0)], 4))

    def test_timing_includes_solver_and_failures_are_not_success(self):
        design = make_design('fixture', (4,), (2,), 1, 0)
        task = design['tasks'][0]
        clock = [10.0]
        def solve(masks, mode, original):
            clock[0] += 7.0  # initialization + transfer + computation + synchronization
            return original(masks), {'requested_backend':mode, 'actual_backend':'numba'}
        with patch.object(production.time, 'perf_counter', side_effect=lambda:clock[0]), patch.object(backends, 'solve_optima', side_effect=solve):
            record = production.evaluate_task(task, design['diagnostics'], production_backend='numba')
        self.assertEqual(record['timing']['enumeration_seconds'], 7.0)
        self.assertGreaterEqual(record['timing']['base_seconds'], 7.0)
        with tempfile.TemporaryDirectory() as tmp, patch.object(backends, 'solve_optima', side_effect=ValueError('invalid launch argument')):
            output = Path(tmp)/'failed'
            with self.assertRaisesRegex(RuntimeError, 'invalid launch argument'):
                production.run(design, output, workers=1, production_backend='numba')
            self.assertFalse(read_json(output/'run_status.json')['complete'])
            self.assertEqual(list((output/'graphs').glob('*.json')), [])
            events = [json.loads(s) for s in (output/'production_backend.jsonl').read_text().splitlines()]
            self.assertFalse(any(e['status']=='complete' for e in events))
            self.assertEqual(json.loads((output/'execution.jsonl').read_text().splitlines()[-1])['status'], 'interrupted')

    def test_failure_logging_preserves_primary_error_and_resume(self):
        design = make_design('fixture', (4,), (2,), 2, 0)
        for failure in ('checkpoint', 'worker', 'completion_log'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)/'run'
                original_open, original_write = Path.open, production.write_json
                primary = OSError('checkpoint replace failed')
                logging_broken, calls, saved = False, 0, {}

                def solve(masks, mode, original):
                    nonlocal calls, logging_broken
                    calls += 1
                    if failure == 'worker' and calls == 2:
                        logging_broken = True
                        raise ValueError('worker solve failed')
                    return original(masks), {'requested_backend':mode, 'actual_backend':'python'}

                def write(path, value):
                    nonlocal logging_broken
                    graph = path.parent.name == 'graphs'
                    second = graph and path.stem == design['tasks'][1]['base_graph_id']
                    if second and failure == 'checkpoint':
                        logging_broken = True
                        raise primary
                    original_write(path, value)
                    if graph:
                        saved[path.name] = path.read_bytes()
                    if second and failure == 'completion_log':
                        logging_broken = True

                def opened(path, mode='r', *args, **kwargs):
                    if logging_broken and path.name == 'production_backend.jsonl' and mode == 'a':
                        raise PermissionError('backend log append denied')
                    return original_open(path, mode, *args, **kwargs)

                caught = None
                with patch.object(backends, 'solve_optima', side_effect=solve), \
                        patch.object(production, 'write_json', side_effect=write), \
                        patch.object(Path, 'open', new=opened):
                    try:
                        production.run(design, output, workers=1, production_backend='numba')
                    except Exception as error:
                        caught = error
                if failure == 'checkpoint':
                    self.assertIs(caught, primary)
                elif failure == 'worker':
                    self.assertIsInstance(caught, RuntimeError)
                    self.assertIn('ValueError: worker solve failed', str(caught))
                else:
                    self.assertIsInstance(caught, PermissionError)
                self.assertTrue(any('PermissionError: backend log append denied' in note
                                    for note in getattr(caught, '__notes__', ())))
                self.assertIn('PermissionError: backend log append denied',
                              ''.join(traceback.format_exception(caught)))
                self.assertFalse(read_json(output/'run_status.json')['complete'])
                events = [json.loads(line) for line in (output/'production_backend.jsonl').read_text().splitlines()]
                self.assertEqual([event['status'] for event in events], ['started', 'complete'])
                self.assertEqual(json.loads((output/'execution.jsonl').read_text().splitlines()[-1])['status'], 'interrupted')
                expected_saved = 2 if failure == 'completion_log' else 1
                self.assertEqual(len(saved), expected_saved)
                with patch.object(production, 'evaluate_task', wraps=production.evaluate_task) as solver:
                    resumed = production.run(design, output, workers=1, resume=True)
                    self.assertEqual(solver.call_count, 2-expected_saved)
                self.assertEqual((resumed['computed'], resumed['reused'], resumed['complete']),
                                 (2-expected_saved, expected_saved, True))
                for name, content in saved.items():
                    self.assertEqual((output/'graphs'/name).read_bytes(), content)
                for record in load_records(output, design):
                    verify_graph(record, record['task'], design['diagnostics'])

    def test_cpu_fallback_only_covers_dependency_loading(self):
        with patch.object(backends, '_numba_backend', return_value=(None, 'missing dependency')):
            with self.assertWarnsRegex(RuntimeWarning, 'using Python'):
                result, event = backends.solve_optima((3, 5), 'auto', production.all_budget_optima)
            self.assertEqual(result, production.all_budget_optima((3, 5)))
            self.assertEqual(event['actual_backend'], 'python')
            with self.assertRaises(backends.ProductionBackendUnavailable):
                backends.solve_optima((3, 5), 'numba', production.all_budget_optima)
        broken = types.SimpleNamespace(solve=lambda masks: (_ for _ in ()).throw(ValueError('logic error')))
        with patch.object(backends, '_numba_backend', return_value=(broken, None)):
            with self.assertRaisesRegex(ValueError, 'logic error'):
                backends.solve_optima((3, 5), 'auto', production.all_budget_optima)

    def test_cpu_spawn_resume_csv_and_completed_cuda_without_device(self):
        design = make_design('fixture', (5,), (2,), 3, 2)
        with tempfile.TemporaryDirectory() as tmp:
            base, fast = Path(tmp)/'base', Path(tmp)/'fast'
            production.run(design, base, workers=1)
            production.run(design, fast, workers=1, stop_after=1, production_backend='numba')
            graph = fast/'graphs'/(design['tasks'][0]['base_graph_id']+'.json')
            saved = graph.read_bytes()
            resumed = production.run(design, fast, workers=2, resume=True, production_backend='numba')
            self.assertEqual((resumed['computed'],resumed['reused']), (2,1))
            self.assertEqual(graph.read_bytes(), saved)
            with patch.object(backends, 'solve_optima', side_effect=AssertionError('no solver on completed resume')):
                done = production.run(design, fast, workers=4, resume=True, production_backend='cuda')
            self.assertEqual(done['computed'], 0)
            for original, actual in zip(load_records(base,design),load_records(fast,design)):
                self.assertEqual({k:v for k,v in original.items() if k!='timing'}, {k:v for k,v in actual.items() if k!='timing'})
                verify_graph(actual, actual['task'], design['diagnostics'])
            for directory in (base, fast):
                production.analyze(directory, plot=False, verification_workers=1)
                verify_summaries(directory)
            for name in ('budget_results.csv','cell_summary.csv','mechanism_summary.csv'):
                self.assertEqual((base/name).read_bytes(),(fast/name).read_bytes())
            bad = Path(tmp)/'bad'
            with self.assertRaisesRegex(ValueError,'workers=1'):
                production.run(design,bad,workers=4,production_backend='cuda')
            self.assertFalse(bad.exists())
            with self.assertRaisesRegex(ValueError,'preflight'):
                production.run(make_design('preflight',(4,),(2,),1,1),bad,production_backend='numba')
            self.assertFalse(bad.exists())
            from validate_r2_budget_grid_fast import validate_batch
            preflight=make_design('preflight',(4,),(2,),1,1)
            production.run(preflight,bad,workers=1)
            with self.assertRaisesRegex(ValueError,'Python cost baseline'):
                validate_batch(bad,workers=1,completion_backend='numba')

    def test_default_cli_and_import_remain_dependency_free(self):
        code = "import sys; sys.path[:0]=['analysis','src']; import r2_budget_grid,r2_cuda_backend; assert 'numpy' not in sys.modules and 'numba' not in sys.modules and 'cupy' not in sys.modules"
        result = subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.json'
            write_json(config,make_design('fixture',(4,),(2,),1,1))
            result=subprocess.run([sys.executable,'analysis/r2_budget_grid.py','run','--config',str(config),
                '--output',str(Path(tmp)/'run'),'--workers','1','--production-backend','numba'],cwd=ROOT,text=True,capture_output=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_cuda_owner_is_terminated_when_budget_expires(self):
        from r2_cuda_backend import computed_cuda_results
        with tempfile.TemporaryDirectory(dir=ROOT/'results') as tmp:
            marker=Path(tmp)/'started'
            class Budget:
                raised_at=None
                def check(self):
                    if marker.exists():
                        self.raised_at=time.perf_counter()
                        raise RuntimeError('test budget exhausted')
            budget=Budget()
            with self.assertRaisesRegex(RuntimeError,'budget exhausted'):
                list(computed_cuda_results(_slow_owner_task,[(str(marker),)],budget,tmp))
            self.assertIsNotNone(budget.raised_at)
            self.assertLess(time.perf_counter()-budget.raised_at,1.5)


if __name__=='__main__':
    unittest.main()
