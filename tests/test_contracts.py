from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import ALGORITHMS
from maxcover.contracts import AlgorithmRunOptions, AlgorithmSpec
from maxcover.generators import uniform_random
from maxcover.model import Solution, SolutionStatus


class AlgorithmContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = uniform_random(
            universe_size=30,
            set_count=10,
            k=3,
            density=0.2,
            seed=42,
        )

    def test_every_registered_algorithm_uses_common_interface(self) -> None:
        config = {
            "exact_time_limit_seconds": 2.0,
            "brute_force_set_cutoff": 12,
        }
        for name, specification in ALGORITHMS.items():
            if (
                specification.preflight_error is not None
                and specification.preflight_error() is not None
            ):
                continue
            options = specification.options_from_config(config)
            if specification.uses_random_seed:
                options = replace(options, algorithm_seed=0)
            self.assertTrue(specification.is_eligible(self.instance, options), name)
            result = specification.run(self.instance, options)
            self.assertEqual(result.algorithm, name)

    def test_registry_metadata_translates_legacy_config(self) -> None:
        brute = ALGORITHMS["brute_force"]
        options = brute.options_from_config(
            {
                "exact_time_limit_seconds": 1.25,
                "brute_force_set_cutoff": 9,
            }
        )
        self.assertEqual(options.time_limit_seconds, 1.25)
        self.assertEqual(options.max_set_count, 9)
        self.assertFalse(brute.is_eligible(self.instance, options))

    def test_invalid_common_options_are_rejected(self) -> None:
        for kwargs in (
            {"time_limit_seconds": 0},
            {"time_limit_seconds": float("inf")},
            {"time_limit_seconds": True},
            {"max_set_count": -1},
            {"max_set_count": 1.5},
            {"max_set_count": False},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AlgorithmRunOptions(**kwargs)

    def test_registry_declares_and_enforces_supported_options(self) -> None:
        self.assertEqual(ALGORITHMS["greedy"].supported_options, frozenset())
        self.assertEqual(
            ALGORITHMS["branch_and_bound"].supported_options,
            frozenset({"time_limit_seconds"}),
        )
        self.assertEqual(
            ALGORITHMS["brute_force"].supported_options,
            frozenset({"time_limit_seconds", "max_set_count"}),
        )
        with self.assertRaisesRegex(ValueError, "does not support"):
            ALGORITHMS["greedy"].run(
                self.instance, AlgorithmRunOptions(time_limit_seconds=1.0)
            )

    def test_option_values_include_only_supported_adopted_fields(self) -> None:
        brute = ALGORITHMS["brute_force"]
        values = brute.option_values(
            AlgorithmRunOptions(time_limit_seconds=1.25, max_set_count=9)
        )
        self.assertEqual(
            values, {"time_limit_seconds": 1.25, "max_set_count": 9}
        )
        self.assertEqual(
            ALGORITHMS["greedy"].option_values(AlgorithmRunOptions()), {}
        )

    def test_result_contract_detects_algorithm_name_mismatch(self) -> None:
        def bad_runner(instance, options):
            del instance, options
            return Solution(
                algorithm="wrong_name",
                selected=(),
                feasible_value=0,
                runtime_seconds=0.0,
                status=SolutionStatus.FEASIBLE,
            )

        specification = AlgorithmSpec(
            name="expected_name",
            exact=False,
            runner=bad_runner,
        )
        with self.assertRaises(RuntimeError):
            specification.run(self.instance, AlgorithmRunOptions())

    def test_result_contract_rejects_status_incompatible_with_registry(self) -> None:
        def falsely_optimal_runner(instance, options):
            del options
            selected = tuple(range(instance.k))
            value = instance.coverage(selected)
            return Solution(
                algorithm="heuristic",
                selected=selected,
                feasible_value=value,
                runtime_seconds=0.0,
                status=SolutionStatus.OPTIMAL,
                best_bound=value,
            )

        specification = AlgorithmSpec(
            name="heuristic",
            exact=False,
            runner=falsely_optimal_runner,
        )
        with self.assertRaisesRegex(RuntimeError, "incompatible"):
            specification.run(self.instance, AlgorithmRunOptions())


if __name__ == "__main__":
    unittest.main()
