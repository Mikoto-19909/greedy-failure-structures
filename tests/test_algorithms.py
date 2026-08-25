from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import branch_and_bound, brute_force, greedy, local_search
from maxcover.generators import adversarial_greedy_trap, uniform_random
from maxcover.model import MaximumCoverageInstance, SolutionStatus


def mask(*elements: int) -> int:
    value = 0
    for element in elements:
        value |= 1 << element
    return value


class AlgorithmTests(unittest.TestCase):
    def test_known_instance_optimum(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=8,
            sets=(
                mask(0, 1, 2, 3),
                mask(2, 3, 4, 5),
                mask(5, 6, 7),
                mask(0, 4, 7),
            ),
            k=2,
        )
        brute = brute_force(instance)
        bounded = branch_and_bound(instance, time_limit_seconds=1.0)
        self.assertEqual(brute.coverage, 7)
        self.assertEqual(bounded.coverage, brute.coverage)
        self.assertEqual(brute.status, SolutionStatus.OPTIMAL)
        self.assertEqual(bounded.status, SolutionStatus.OPTIMAL)
        self.assertTrue(bounded.is_exact)

    def test_adversarial_family_exposes_greedy_gap(self) -> None:
        instance = adversarial_greedy_trap(block_size=20, seed=1)
        greedy_solution = greedy(instance)
        exact_solution = brute_force(instance)
        self.assertLess(greedy_solution.coverage, exact_solution.coverage)
        self.assertEqual(exact_solution.coverage, instance.universe_size)

    def test_local_search_never_reduces_greedy_value(self) -> None:
        for seed in range(5):
            instance = uniform_random(
                universe_size=50,
                set_count=12,
                k=4,
                density=0.2,
                seed=seed,
            )
            self.assertGreaterEqual(local_search(instance).coverage, greedy(instance).coverage)

    def test_selected_sets_respect_budget(self) -> None:
        instance = uniform_random(
            universe_size=40,
            set_count=10,
            k=3,
            density=0.25,
            seed=9,
        )
        for solution in (
            greedy(instance),
            local_search(instance),
            brute_force(instance),
            branch_and_bound(instance),
        ):
            self.assertLessEqual(len(solution.selected), instance.k)
            self.assertEqual(solution.coverage, instance.coverage(solution.selected))

    def test_exact_methods_agree_on_many_seeded_instances(self) -> None:
        for seed in range(50):
            instance = uniform_random(
                universe_size=32,
                set_count=10,
                k=3,
                density=0.1 + (seed % 5) * 0.1,
                seed=seed,
            )
            brute = brute_force(instance)
            bounded = branch_and_bound(instance, time_limit_seconds=2.0)
            self.assertFalse(bounded.timed_out, seed)
            self.assertEqual(bounded.coverage, brute.coverage, seed)

    def test_exact_timeout_preserves_a_feasible_incumbent(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=3,
            sets=(mask(0), mask(1), mask(2)),
            k=1,
        )
        solution = brute_force(instance, time_limit_seconds=1e-12)
        self.assertEqual(solution.status, SolutionStatus.TIMEOUT)
        self.assertEqual(solution.coverage, instance.coverage(solution.selected))
        self.assertIsNone(solution.optimal_value)
        self.assertGreater(solution.best_bound, solution.coverage)
        self.assertFalse(solution.is_exact)
        self.assertTrue(solution.timed_out)


if __name__ == "__main__":
    unittest.main()
