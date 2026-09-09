"""Real optional CPU verification, fallback and R2 command integration."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'analysis'), str(ROOT / 'src')]
import verification_completion as backend
from validate_greedy_failure_paths import best_completion, expected_path
from r2_design import make_design, read_json, write_json
from r2_budget_grid import run, analyze
from validate_r2_budget_grid_fast import verify_graph


class FastVerificationTests(unittest.TestCase):
    def tearDown(self):
        backend.get_completion_solver.cache_clear()
        backend._optional_solver.cache_clear()

    def test_adapter_preserves_inputs_and_rejects_unplanned_diagnostics(self):
        from r2_budget_grid import evaluate_task
        for diagnostic_count in (0, 1):
            design = make_design('fixture', (4,), (2,), 1, diagnostic_count)
            task = design['tasks'][0]
            record = evaluate_task(task, design['diagnostics'])
            original = copy.deepcopy(record)
            verify_graph(record, task, design['diagnostics'], completion_backend='numba')
            self.assertEqual(record, original)
            for damage in ('task', 'sets', 'reference', 'structure', 'diagnostic'):
                bad = copy.deepcopy(record)
                if damage == 'task': bad['task']['diagnostic_k'] = 3
                elif damage == 'sets': bad['sets'][0] = []
                elif damage == 'reference': bad['values'][0]['optimum'] += 1
                elif damage == 'structure': bad['structure']['incidence_count'] += 1
                else: bad['diagnostic'] = {} if diagnostic_count == 0 else None
                with self.subTest(diagnostic_count=diagnostic_count, damage=damage), self.assertRaises(ValueError):
                    verify_graph(bad, task, design['diagnostics'], completion_backend='numba')

    def test_accelerated_preflight_does_not_replace_the_frozen_cost_baseline(self):
        from validate_r2_budget_grid_fast import validate_batch
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_json(output / 'config.json', make_design('preflight', (4,), (2,), 1, 1))
            for name in ('auto', 'numba'):
                with self.subTest(backend=name), self.assertRaisesRegex(ValueError, 'Python cost baseline'):
                    validate_batch(output, completion_backend=name)
                with self.assertRaisesRegex(ValueError, 'Python cost baseline'):
                    analyze(output, plot=False, completion_backend=name)

    def test_compiled_completion_matches_independent_small_cases(self):
        solve = backend.get_completion_solver('numba')
        self.assertIs(backend.get_completion_solver('auto'), solve)
        for masks in itertools.product(range(4), repeat=3):
            sets = [{e for e in range(2) if mask & (1 << e)} for mask in masks]
            for k in range(4):
                for length in range(k + 1):
                    for prefix in itertools.combinations(range(3), length):
                        for ordered in (list(prefix), list(reversed(prefix))):
                            self.assertEqual(solve(sets, k, ordered, 100),
                                             best_completion(sets, k, ordered, 100))
        for sets in ([set(), set()], [{65}, {1, 65}, set()], []):
            for k in range(len(sets) + 1):
                self.assertEqual(solve(sets, k, [], 100), best_completion(sets, k, [], 100))
        for k, prefix, limit in ((2, [0, 0], 100), (1, [0, 1], 100), (2, [], 2),
                                 (1, [3], 100), (-1, [], 100), (1, [True], 100)):
            with self.assertRaises(ValueError):
                solve([{0}, {1}, {2}], k, prefix, limit)

    def test_fallback_is_explicit_and_does_not_hide_calculation_errors(self):
        backend.get_completion_solver.cache_clear()
        backend._optional_solver.cache_clear()
        unavailable = backend.FastVerificationUnavailable('injected missing dependency')
        with patch.object(backend, '_build_solver', side_effect=unavailable) as build:
            with self.assertWarnsRegex(RuntimeWarning, 'original Python'):
                solve = backend.get_completion_solver('auto')
            self.assertEqual(solve([{0}, {1}], 1, [], 10), (1, [0], 2, 2))
            self.assertIs(backend.get_completion_solver('auto'), solve)
            with self.assertRaisesRegex(backend.FastVerificationUnavailable, 'fast-verification'):
                backend.get_completion_solver('numba')
            self.assertEqual(build.call_count, 1)
            with self.assertRaises(ValueError):
                solve([{0}], 1, [0, 0], 10)
        backend.get_completion_solver.cache_clear()
        backend._optional_solver.cache_clear()
        with patch.object(backend, '_build_solver', side_effect=AssertionError('incorrect kernel')):
            with self.assertRaisesRegex(AssertionError, 'incorrect kernel'):
                backend.get_completion_solver('auto')
        backend.get_completion_solver.cache_clear()
        backend._optional_solver.cache_clear()
        with patch.object(backend, '_build_solver', return_value=lambda *args: 1 / 0):
            with self.assertRaises(ZeroDivisionError):
                backend.get_completion_solver('auto')([{0}], 1, [], 10)
        with self.assertRaises(ValueError):
            backend.get_completion_solver('unknown')

    def test_python_default_does_not_load_optional_packages(self):
        code = ("import sys; sys.path[:0]=['analysis','src']; "
                "from verification_completion import get_completion_solver; "
                "assert get_completion_solver()([{0},{1}],1,[],10)==(1,[0],2,2); "
                "assert 'numba' not in sys.modules and 'numpy' not in sys.modules")
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_full_paths_and_corrupt_records_match_original_verification(self):
        design = read_json(ROOT / 'analysis/r1_prefix_exchange_design.json')
        limits = {'max_completions': 200000, 'max_two_swap_evaluations': 100000}
        for fixture in design['fixtures']:
            base = {'sets': fixture['sets'], 'k': fixture['k'], 'population': 'r2'}
            self.assertEqual(expected_path(base, limits, completion_backend='numba'),
                             expected_path(base, limits), fixture['name'])
        fixture = next(f for f in design['fixtures'] if f['name'] == 'two_swap_escape')
        for budget in (0, 4, 5, 10):
            limits['max_two_swap_evaluations'] = budget
            base = {'sets': fixture['sets'], 'k': fixture['k'], 'population': 'r2'}
            self.assertEqual(expected_path(base, limits, completion_backend='numba'), expected_path(base, limits))
        from r2_budget_grid import evaluate_task
        d = make_design('fixture', (4,), (2,), 1, 1)
        row = evaluate_task(d['tasks'][0], d['diagnostics'])
        verify_graph(row, d['tasks'][0], d['diagnostics'], completion_backend='numba')
        for field in ('count', 'tie', 'path', 'type', 'seed'):
            damaged = copy.deepcopy(row)
            if field == 'count':
                damaged['diagnostic']['optimal_solution_count'] += 1
            elif field == 'tie':
                damaged['diagnostic']['ties'][0]['preserves_optimum'] = not damaged['diagnostic']['ties'][0]['preserves_optimum']
            elif field == 'path':
                damaged['diagnostic']['prefixes'][0]['optimal_completion'] += 1
            elif field == 'seed':
                damaged['task']['seed'] += 1
            else:
                damaged['diagnostic']['completion_count'] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_graph(damaged, d['tasks'][0], d['diagnostics'], completion_backend='numba')

    def test_cli_spawn_resume_and_corruption_rejection(self):
        design = make_design('fixture', (4,), (2,), 2, 2)
        def command(script, *args):
            return subprocess.run([sys.executable, str(ROOT / 'analysis' / script), *map(str, args)],
                                  cwd=ROOT, text=True, capture_output=True, timeout=120)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'batch'
            run(design, output, workers=1, stop_after=1)
            graph = output / 'graphs' / (design['tasks'][0]['base_graph_id'] + '.json')
            before_graph = graph.read_bytes()
            resumed = run(design, output, workers=1, resume=True)
            self.assertEqual((resumed['computed'], resumed['reused']), (1, 1))
            self.assertEqual(graph.read_bytes(), before_graph)
            analyze(output, plot=False)
            config = (output / 'config.json').read_bytes()
            files = ('cell_summary.csv', 'budget_results.csv', 'mechanism_summary.csv')
            tables = {name: (output / name).read_bytes() for name in files}
            verified = command('validate_r2_budget_grid_fast.py', '--output', output, '--workers', 2,
                               '--verification-backend', 'numba')
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            rebuilt = command('r2_budget_grid.py', 'analyze', '--output', output, '--no-plot',
                              '--verification-backend', 'numba', '--verification-workers', 2)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
            self.assertEqual((output / 'config.json').read_bytes(), config)
            self.assertEqual({name: (output / name).read_bytes() for name in files}, tables)
            for script, args in (
                ('r2_budget_grid.py', ['analyze', '--verification-workers', 0]),
                ('r2_budget_grid.py', ['run', '--verification-backend', 'numba']),
                ('validate_r2_budget_grid_fast.py', ['--summaries-only', '--verification-backend', 'auto']),
            ):
                invalid = command(script, *args, '--output', output)
                self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            damaged = read_json(graph)
            damaged['diagnostic']['optimal_solution_count'] += 1
            write_json(graph, damaged)
            rejected = command('validate_r2_budget_grid_fast.py', '--output', output, '--workers', 1,
                               '--verification-backend', 'numba')
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(read_json(output / 'verification.json')['status'], 'incomplete')
            with self.assertRaises(ValueError):
                analyze(output, plot=False, completion_backend='numba', verification_workers=1)
            self.assertEqual({name: (output / name).read_bytes() for name in files}, tables)


if __name__ == '__main__':
    unittest.main()
