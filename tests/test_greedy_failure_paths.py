"""R1 definitions exercised on hand-checked examples and budget boundaries."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]

from greedy_failure_paths import analyze_instance, gap
from maxcover.algorithms import greedy
from maxcover.model import MaximumCoverageInstance


def fixture(name):
    design = json.loads((ROOT / "analysis/r1_prefix_exchange_design.json").read_text(encoding="utf-8"))
    item = next(item for item in design["fixtures"] if item["name"] == name)
    return MaximumCoverageInstance(item["universe_size"],
                                   tuple(sum(1 << e for e in group) for group in item["sets"]),
                                   item["k"])


class GreedyFailurePathTests(unittest.TestCase):
    def test_fixed_mechanisms_and_exchange_outcomes(self):
        examples = (
            ("multiple_optima", 4, 4, 4, 4, "optimal"),
            ("avoidable_tie", 6, 8, 8, 8, "tie_avoidable"),
            ("unique_bait", 7, 8, 8, 8, "one_step_limit"),
            ("two_swap_escape", 6, 8, 6, 8, "tie_avoidable"),
            ("two_swap_stall", 10, 12, 10, 10, "tie_avoidable"),
            ("zero_objective", 0, 0, 0, 0, "optimal"),
        )
        for name, g, optimum, one, two, mechanism in examples:
            with self.subTest(name=name):
                result = analyze_instance(fixture(name))
                self.assertEqual(result["prefixes"][-1]["coverage"], g)
                self.assertEqual(result["optimum"], optimum)
                self.assertEqual(result["one_swap"]["coverage"], one)
                self.assertEqual(result["two_swap"]["coverage"], two)
                self.assertEqual(result["mechanism"], mechanism)
                self.assertEqual(result["two_swap"]["status"], "local_optimum")
                reachable = [row["optimal_completion"] for row in result["prefixes"]]
                self.assertEqual(reachable[0], optimum)
                self.assertEqual(reachable[-1], g)
                self.assertEqual(reachable, sorted(reachable, reverse=True))

    def test_multiple_optima_do_not_create_a_false_failure(self):
        result = analyze_instance(fixture("multiple_optima"))
        self.assertEqual(result["optimal_solution_count"], 2)
        self.assertIsNone(result["first_failure_step"])

    def test_decision_order_is_not_the_sorted_terminal_selection(self):
        instance = MaximumCoverageInstance(3, (1, 2, 7), 2)
        result = analyze_instance(instance)
        self.assertEqual(greedy(instance).selected, (0, 2))
        self.assertEqual(result["greedy_selected"], [2, 0])
        self.assertEqual(result["prefixes"][1]["prefix"], [2])

    def test_all_maximum_gain_candidates_are_retained(self):
        result = analyze_instance(fixture("avoidable_tie"))
        first = [row for row in result["ties"] if row["step"] == 1]
        self.assertEqual([row["candidate"] for row in first], [0, 1, 2])
        self.assertEqual([row["preserves_optimum"] for row in first], [False, True, True])

    def test_partial_neighborhood_never_claims_local_optimality(self):
        for budget, expected_value, expected_status in (
            (0, 6, "budget_exhausted"), (4, 6, "budget_exhausted"),
            (5, 8, "budget_exhausted"), (10, 8, "local_optimum"),
        ):
            with self.subTest(budget=budget):
                result = analyze_instance(fixture("two_swap_escape"), max_two_swap_evaluations=budget)
                two = result["two_swap"]
                self.assertEqual(two["coverage"], expected_value)
                self.assertEqual(two["status"], expected_status)
                self.assertEqual(two["evaluations"], budget)

    def test_exact_enumeration_refuses_an_insufficient_budget(self):
        with self.assertRaises(ValueError):
            analyze_instance(fixture("two_swap_stall"), max_completions=1)

    def test_zero_optimum_has_no_relative_gap(self):
        self.assertIsNone(gap(0, 0))


if __name__ == "__main__":
    unittest.main()
