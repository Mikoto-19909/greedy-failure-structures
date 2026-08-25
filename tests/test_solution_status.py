from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.model import Solution, SolutionStatus


class SolutionStatusTests(unittest.TestCase):
    def test_compatibility_properties_are_derived_from_status(self) -> None:
        optimal = Solution(
            algorithm="exact",
            selected=(0,),
            feasible_value=4,
            runtime_seconds=0.1,
            status="optimal",
            best_bound=4,
        )
        self.assertEqual(optimal.status, SolutionStatus.OPTIMAL)
        self.assertEqual(optimal.coverage, 4)
        self.assertEqual(optimal.optimal_value, 4)
        self.assertTrue(optimal.is_exact)
        self.assertFalse(optimal.timed_out)

        timeout = Solution(
            algorithm="exact",
            selected=(0,),
            feasible_value=4,
            runtime_seconds=0.1,
            status=SolutionStatus.TIMEOUT,
            best_bound=5,
        )
        self.assertEqual(timeout.coverage, 4)
        self.assertIsNone(timeout.optimal_value)
        self.assertFalse(timeout.is_exact)
        self.assertTrue(timeout.timed_out)

    def test_non_error_status_requires_an_incumbent(self) -> None:
        for status in (
            SolutionStatus.OPTIMAL,
            SolutionStatus.FEASIBLE,
            SolutionStatus.TIMEOUT,
        ):
            with self.subTest(status=status), self.assertRaises(ValueError):
                Solution(
                    algorithm="algorithm",
                    selected=(),
                    feasible_value=None,
                    runtime_seconds=0.0,
                    status=status,
                )

    def test_optimal_status_requires_a_closed_bound(self) -> None:
        for bound in (None, 6):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                Solution(
                    algorithm="exact",
                    selected=(0,),
                    feasible_value=5,
                    runtime_seconds=0.0,
                    status=SolutionStatus.OPTIMAL,
                    best_bound=bound,
                )

    def test_non_optimal_bound_must_leave_a_positive_gap(self) -> None:
        for status in (SolutionStatus.FEASIBLE, SolutionStatus.TIMEOUT):
            for bound in (3, 4):
                with (
                    self.subTest(status=status, bound=bound),
                    self.assertRaises(ValueError),
                ):
                    Solution(
                        algorithm="algorithm",
                        selected=(0,),
                        feasible_value=4,
                        runtime_seconds=0.0,
                        status=status,
                        best_bound=bound,
                    )

    def test_error_status_cannot_claim_an_incumbent_or_bound(self) -> None:
        Solution(
            algorithm="algorithm",
            selected=(),
            feasible_value=None,
            runtime_seconds=0.0,
            status=SolutionStatus.ERROR,
        )
        with self.assertRaises(ValueError):
            Solution(
                algorithm="algorithm",
                selected=(0,),
                feasible_value=1,
                runtime_seconds=0.0,
                status=SolutionStatus.ERROR,
                best_bound=2,
            )


if __name__ == "__main__":
    unittest.main()
