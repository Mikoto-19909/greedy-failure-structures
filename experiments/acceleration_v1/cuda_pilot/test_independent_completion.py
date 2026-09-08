"""Exercise existing R2 checks and hand-checked R1 fixtures with compiled completion."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch
import independent_completion as optimized
import validate_greedy_failure_paths as reference

ROOT = Path(__file__).resolve().parents[2]


class IndependentPathTests(unittest.TestCase):
    def test_all_existing_r1_fixtures_have_identical_full_paths(self):
        design = json.loads((ROOT/'analysis/r1_prefix_exchange_design.json').read_text())
        limits = {'max_completions':200000,'max_two_swap_evaluations':100000}
        for fixture in design['fixtures']:
            base = {'sets':fixture['sets'],'k':fixture['k'],'population':'r2'}
            expected = reference.expected_path(base,limits)
            with patch.object(reference,'best_completion',optimized.best_completion):
                actual = reference.expected_path(base,limits)
            self.assertEqual(actual,expected,fixture['name'])

    def test_partial_exchange_budget_retains_exact_status_and_counts(self):
        design = json.loads((ROOT/'analysis/r1_prefix_exchange_design.json').read_text())
        fixture = next(f for f in design['fixtures'] if f['name']=='two_swap_escape')
        base = {'sets':fixture['sets'],'k':fixture['k'],'population':'r2'}
        for budget in (0,4,5,10):
            limits = {'max_completions':200000,'max_two_swap_evaluations':budget}
            expected = reference.expected_path(base,limits)
            with patch.object(reference,'best_completion',optimized.best_completion):
                actual = reference.expected_path(base,limits)
            self.assertEqual(actual,expected)


if __name__=='__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    first = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(IndependentPathTests))
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_r2_budget_grid.py')
    with patch.object(reference,'best_completion',optimized.best_completion):
        second = runner.run(suite)
    sys.exit(0 if first.wasSuccessful() and second.wasSuccessful() else 1)
