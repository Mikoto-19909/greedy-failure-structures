from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import (
    branch_and_bound,
    branch_and_bound_enhanced,
    brute_force,
    greedy,
    local_search,
    multi_start_local_search,
    randomized_greedy,
)
from maxcover.generators import uniform_random
from maxcover.model import MaximumCoverageInstance, SolutionStatus


def _mask(*elements: int) -> int:
    value = 0
    for element in elements:
        value |= 1 << element
    return value


class BranchAndBoundMetricTests(unittest.TestCase):
    def test_baseline_metric_counts_on_hand_checked_instance(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=3,
            sets=(_mask(0), _mask(1), _mask(2)),
            k=1,
        )
        solution = branch_and_bound(instance, time_limit_seconds=None)
        search = solution.metadata["search"]

        self.assertEqual(solution.status, SolutionStatus.OPTIMAL)
        self.assertEqual(solution.coverage, 1)
        self.assertEqual(search["nodes_visited"], 5)
        self.assertEqual(search["bound_prunes"], 1)
        self.assertEqual(search["cardinality_prunes"], 0)
        self.assertEqual(search["incumbent_updates"], 0)
        self.assertEqual(search["max_depth"], 2)
        self.assertEqual(search["initial_incumbent"], 1)
        self.assertEqual(solution.nodes_or_iterations, search["nodes_visited"])
        self.assertEqual(solution.metadata["termination"], "completed")

    def test_cardinality_prunes_are_counted_separately(self) -> None:
        instance = uniform_random(
            universe_size=20,
            set_count=8,
            k=4,
            density=0.25,
            seed=616,
        )
        solution = branch_and_bound(instance, time_limit_seconds=None)
        search = solution.metadata["search"]
        self.assertGreater(search["cardinality_prunes"], 0)
        self.assertLessEqual(search["max_depth"], instance.set_count)

    def test_baseline_matches_brute_force_on_200_random_instances(self) -> None:
        rng = random.Random(20260718)
        for sample in range(200):
            set_count = rng.randint(4, 10)
            k = rng.randint(1, min(4, set_count))
            instance = uniform_random(
                universe_size=rng.randint(8, 24),
                set_count=set_count,
                k=k,
                density=rng.uniform(0.08, 0.65),
                seed=rng.randrange(1_000_000),
            )
            expected = brute_force(instance, time_limit_seconds=None)
            actual = branch_and_bound(instance, time_limit_seconds=None)
            self.assertEqual(actual.status, SolutionStatus.OPTIMAL, sample)
            self.assertEqual(actual.coverage, expected.coverage, sample)
            search = actual.metadata["search"]
            self.assertGreaterEqual(search["nodes_visited"], 1)
            self.assertGreaterEqual(search["bound_prunes"], 0)
            self.assertGreaterEqual(search["cardinality_prunes"], 0)
            self.assertGreaterEqual(search["incumbent_updates"], 0)
            self.assertLessEqual(search["max_depth"], instance.set_count)


class RandomizedGreedyTests(unittest.TestCase):
    def test_rcl_one_matches_greedy_item_for_item(self) -> None:
        for seed in range(50):
            instance = uniform_random(
                universe_size=45,
                set_count=12,
                k=5,
                density=0.25,
                seed=seed,
            )
            expected = greedy(instance)
            actual = randomized_greedy(
                instance, algorithm_seed=999, rcl_size=1
            )
            self.assertEqual(actual.coverage, expected.coverage)
            self.assertEqual(actual.selected, expected.selected)

    def test_seeded_replay_and_trajectory_are_stable(self) -> None:
        instance = uniform_random(
            universe_size=40,
            set_count=10,
            k=4,
            density=0.2,
            seed=2026,
        )
        left = randomized_greedy(instance, algorithm_seed=17, rcl_size=3)
        right = randomized_greedy(instance, algorithm_seed=17, rcl_size=3)
        self.assertEqual(left.selected, right.selected)
        self.assertEqual(left.coverage, right.coverage)
        self.assertEqual(left.metadata, right.metadata)
        trajectory = left.metadata["trajectory"]
        self.assertEqual(len(trajectory), instance.k)
        self.assertTrue(
            all(
                step["selected_index"] in step["rcl"]
                and step["marginal_gain"] >= 0
                for step in trajectory
            )
        )

    def test_zero_marginal_gain_still_fills_the_budget(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=3,
            sets=(_mask(0), _mask(0), _mask(0), _mask(0)),
            k=4,
        )
        solution = randomized_greedy(instance, algorithm_seed=3, rcl_size=3)
        self.assertEqual(len(solution.selected), instance.k)
        self.assertEqual(solution.coverage, 1)
        self.assertEqual(
            [step["marginal_gain"] for step in solution.metadata["trajectory"]],
            [1, 0, 0, 0],
        )


class MultiStartLocalSearchTests(unittest.TestCase):
    def test_zero_restarts_matches_existing_local_search(self) -> None:
        for seed in range(30):
            instance = uniform_random(
                universe_size=50,
                set_count=12,
                k=4,
                density=0.22,
                seed=seed,
            )
            expected = local_search(instance)
            actual = multi_start_local_search(
                instance,
                algorithm_seed=123,
                restart_count=0,
                time_limit_seconds=None,
            )
            self.assertEqual(actual.coverage, expected.coverage)
            self.assertEqual(actual.selected, expected.selected)

    def test_more_restarts_never_reduce_coverage_without_timeout(self) -> None:
        for seed in range(20):
            instance = uniform_random(
                universe_size=55,
                set_count=14,
                k=5,
                density=0.2,
                seed=seed,
            )
            coverages = [
                multi_start_local_search(
                    instance,
                    algorithm_seed=77,
                    restart_count=restarts,
                    max_iterations_per_restart=50,
                    time_limit_seconds=None,
                ).coverage
                for restarts in (1, 4, 8, 16)
            ]
            self.assertEqual(coverages, sorted(coverages))

    def test_iteration_budget_replays_and_trajectory_has_no_time(self) -> None:
        instance = uniform_random(
            universe_size=60,
            set_count=15,
            k=5,
            density=0.18,
            seed=2026,
        )
        kwargs = {
            "algorithm_seed": 19,
            "restart_count": 8,
            "max_iterations_per_restart": 2,
            "time_limit_seconds": None,
        }
        left = multi_start_local_search(instance, **kwargs)
        right = multi_start_local_search(instance, **kwargs)
        self.assertEqual(left.selected, right.selected)
        self.assertEqual(left.coverage, right.coverage)
        self.assertEqual(left.metadata, right.metadata)
        self.assertTrue(
            all(set(point) == {"iteration", "coverage"} for point in left.metadata["trajectory"])
        )

    def test_time_limit_returns_a_valid_incumbent(self) -> None:
        instance = uniform_random(
            universe_size=100,
            set_count=30,
            k=8,
            density=0.2,
            seed=5,
        )
        solution = multi_start_local_search(
            instance,
            algorithm_seed=0,
            restart_count=16,
            time_limit_seconds=1e-12,
        )
        self.assertEqual(solution.status, SolutionStatus.TIMEOUT)
        self.assertEqual(solution.coverage, instance.coverage(solution.selected))
        self.assertEqual(solution.metadata["termination"], "time_limit")

    def test_both_randomized_algorithms_replay_ten_distinct_runs(self) -> None:
        for run in range(10):
            instance = uniform_random(
                universe_size=50,
                set_count=12,
                k=4,
                density=0.2,
                seed=8000 + run,
            )
            randomized_left = randomized_greedy(
                instance, algorithm_seed=run, rcl_size=3
            )
            randomized_right = randomized_greedy(
                instance, algorithm_seed=run, rcl_size=3
            )
            multi_left = multi_start_local_search(
                instance,
                algorithm_seed=run,
                restart_count=8,
                max_iterations_per_restart=100,
                time_limit_seconds=None,
            )
            multi_right = multi_start_local_search(
                instance,
                algorithm_seed=run,
                restart_count=8,
                max_iterations_per_restart=100,
                time_limit_seconds=None,
            )
            self.assertEqual(
                (randomized_left.coverage, randomized_left.selected),
                (randomized_right.coverage, randomized_right.selected),
            )
            self.assertEqual(
                (multi_left.coverage, multi_left.selected),
                (multi_right.coverage, multi_right.selected),
            )


class EnhancedBranchAndBoundTests(unittest.TestCase):
    def test_enhanced_matches_both_exact_methods_on_500_random_instances(self) -> None:
        rng = random.Random(20260719)
        for sample in range(500):
            set_count = rng.randint(4, 11)
            k = rng.randint(1, set_count)
            instance = uniform_random(
                universe_size=rng.randint(8, 26),
                set_count=set_count,
                k=k,
                density=rng.uniform(0.05, 0.7),
                seed=rng.randrange(10_000_000),
            )
            brute = brute_force(instance, time_limit_seconds=None)
            baseline = branch_and_bound(instance, time_limit_seconds=None)
            enhanced = branch_and_bound_enhanced(
                instance, time_limit_seconds=None
            )
            self.assertEqual(baseline.coverage, brute.coverage, sample)
            self.assertEqual(enhanced.coverage, brute.coverage, sample)
            self.assertEqual(enhanced.status, SolutionStatus.OPTIMAL, sample)
            self.assertEqual(
                enhanced.coverage,
                instance.coverage(enhanced.selected),
                sample,
            )

    def test_preprocessing_preserves_original_indices(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=5,
            sets=(
                _mask(0, 1),
                _mask(0, 1),
                _mask(0, 1, 2),
                _mask(3, 4),
            ),
            k=2,
        )
        solution = branch_and_bound_enhanced(instance, time_limit_seconds=None)
        search = solution.metadata["search"]
        self.assertEqual(solution.coverage, 5)
        self.assertEqual(instance.coverage(solution.selected), 5)
        self.assertEqual(search["duplicate_sets_removed"], 1)
        self.assertEqual(search["dominated_sets_removed"], 1)
        self.assertEqual(search["search_set_count"], 2)
        self.assertTrue(set(solution.selected) <= set(range(instance.set_count)))

    def test_edge_cases_and_all_ablation_options_remain_exact(self) -> None:
        instances = (
            MaximumCoverageInstance(
                universe_size=3,
                sets=(_mask(0), _mask(1), _mask(2)),
                k=1,
            ),
            MaximumCoverageInstance(
                universe_size=4,
                sets=(_mask(0), _mask(1), _mask(2), _mask(3)),
                k=4,
            ),
            MaximumCoverageInstance(
                universe_size=3,
                sets=(_mask(), _mask(), _mask()),
                k=2,
            ),
        )
        variants = (
            (False, False, "suffix_union", "static_size"),
            (True, False, "suffix_union", "static_size"),
            (True, True, "suffix_union", "static_size"),
            (True, True, "cardinality", "static_size"),
            (True, True, "cardinality", "dynamic_marginal"),
        )
        for instance in instances:
            expected = brute_force(instance, time_limit_seconds=None)
            for duplicate, dominated, bound, ordering in variants:
                with self.subTest(
                    instance=instance,
                    duplicate=duplicate,
                    dominated=dominated,
                    bound=bound,
                    ordering=ordering,
                ):
                    actual = branch_and_bound_enhanced(
                        instance,
                        time_limit_seconds=None,
                        remove_duplicates=duplicate,
                        remove_dominated=dominated,
                        bound_strategy=bound,
                        ordering_strategy=ordering,
                    )
                    self.assertEqual(actual.coverage, expected.coverage)
                    self.assertEqual(actual.status, SolutionStatus.OPTIMAL)

    def test_timeout_never_claims_an_optimum(self) -> None:
        instance = uniform_random(
            universe_size=100,
            set_count=24,
            k=12,
            density=0.08,
            seed=12,
        )
        solution = branch_and_bound_enhanced(
            instance,
            time_limit_seconds=1e-12,
            remove_duplicates=False,
            remove_dominated=False,
        )
        self.assertEqual(solution.status, SolutionStatus.TIMEOUT)
        self.assertIsNone(solution.optimal_value)
        self.assertEqual(
            solution.coverage, instance.coverage(solution.selected)
        )


if __name__ == "__main__":
    unittest.main()
