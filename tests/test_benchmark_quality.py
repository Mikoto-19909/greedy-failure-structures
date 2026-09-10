"""Known answers and eligibility boundaries for deterministic quality statistics."""
from __future__ import annotations

import pickle
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover import benchmark_statistics as statistics
from maxcover.contracts import RunRecord
from maxcover.model import SolutionStatus

NAMES = ("_greedy_failure_statistics", "_local_search_pair_analyses",
         "_local_search_recovery_statistics", "_local_search_remaining_gap_statistics")


def row(unit, algorithm, coverage, optimum=10, status=SolutionStatus.FEASIBLE):
    return RunRecord(
        case="quality", repetition=unit, seed=unit, family="uniform",
        universe_size=20, set_count=4, k=2, parameters="{}", algorithm=algorithm,
        algorithm_options="{}", status=status, coverage=coverage, best_bound=None,
        optimum=optimum, optimality_gap=None, runtime_seconds=0.125,
        nodes_or_iterations=0, selected=() if coverage is None else (0,),
        config_hash="config", case_id="case", instance_id=f"instance-{unit}",
    )


def known_rows():
    # Three eligible failures: half, full, and no recovery. The other five
    # pairs isolate a tie, absent reference, both timeout directions, and error.
    return [
        row(0, "greedy", 6), row(0, "local_search", 8),
        row(1, "greedy", 5), row(1, "local_search", 10),
        row(2, "greedy", 4), row(2, "local_search", 4),
        row(3, "greedy", 10), row(3, "local_search", 10),
        row(4, "greedy", 6, None), row(4, "local_search", 8, None),
        row(5, "greedy", 6, status=SolutionStatus.TIMEOUT), row(5, "local_search", 8),
        row(6, "greedy", 6), row(6, "local_search", 8, status=SolutionStatus.TIMEOUT),
        row(7, "greedy", None, status=SolutionStatus.ERROR),
        row(7, "local_search", None, status=SolutionStatus.ERROR),
    ]


def invalid_pairs():
    greedy, local = row(0, "greedy", 6), row(0, "local_search", 8)
    # All mutations are valid RunRecords, so rejection must come from analysis.
    return (
        ([greedy, greedy, local], "classical Greedy recovery statistics require exactly one run per instance unit"),
        ([greedy, local, local], "Local Search recovery statistics require exactly one run per instance unit"),
        ([replace(greedy, algorithm_seed=1), local], "classical Greedy recovery statistics forbid algorithm seeds"),
        ([greedy, replace(local, algorithm_seed=1)], "Local Search recovery statistics forbid algorithm seeds"),
        ([greedy, replace(local, instance_id="other")], "Local Search recovery requires identical instance units for paired Greedy and Local Search variants"),
        ([greedy, replace(local, optimum=11)], "paired Greedy and Local Search rows have inconsistent normalized exact references"),
        ([replace(greedy, coverage=11), local], "classical Greedy coverage exceeds its normalized exact optimum"),
        ([greedy, replace(local, coverage=11)], "Local Search coverage exceeds its normalized exact optimum"),
        ([greedy, replace(local, coverage=5)], "Local Search coverage cannot be below its paired Greedy coverage"),
        ([replace(greedy, status=SolutionStatus.OPTIMAL, best_bound=6), local], "classical Greedy records must be feasible, timeout, or error"),
        ([greedy, replace(local, status=SolutionStatus.OPTIMAL, best_bound=8)], "Local Search records must be feasible, timeout, or error"),
    )


class QualityStatisticsTests(unittest.TestCase):
    def test_known_answers_preserve_distinct_denominators_and_input(self):
        rows = known_rows()
        before = pickle.dumps(rows, protocol=4)
        failure, = statistics._greedy_failure_statistics(rows)
        self.assertEqual((failure.instance_count, failure.completed_count,
                          failure.timeout_count, failure.error_count), (8, 6, 1, 1))
        self.assertEqual((failure.valid_exact_reference_count, failure.eligible_pair_count,
                          failure.failure_count, failure.optimal_tie_count), (7, 5, 4, 1))
        self.assertEqual(failure.failure_rate, 4 / 5)
        analysis, = statistics._local_search_pair_analyses(rows)
        self.assertEqual(analysis.recoveries, (0.5, 1.0, 0.0))
        self.assertEqual(analysis.remaining_relative_gaps, (0.2, 0.0, 0.6))
        recovery, = statistics._local_search_recovery_statistics(rows)
        self.assertEqual((recovery.instance_count, recovery.valid_exact_reference_count,
                          recovery.greedy_failure_count, recovery.eligible_pair_count), (8, 7, 4, 3))
        self.assertEqual((recovery.greedy_completed_count, recovery.greedy_timeout_count,
                          recovery.greedy_error_count, recovery.local_search_completed_count,
                          recovery.local_search_timeout_count, recovery.local_search_error_count),
                         (6, 1, 1, 6, 1, 1))
        self.assertEqual(recovery.eligible_pair_rate, 3 / 4)
        self.assertEqual(recovery.mean_gap_recovery_rate, 0.5)
        self.assertEqual(recovery.full_recovery_rate, 1 / 3)
        remaining, = statistics._local_search_remaining_gap_statistics(rows)
        self.assertAlmostEqual(remaining.mean_remaining_relative_gap, 4 / 15)
        self.assertEqual(remaining.maximum_remaining_relative_gap, 0.6)
        self.assertEqual(remaining.zero_remaining_gap_rate, 1 / 3)
        for name in NAMES:
            self.assertEqual(getattr(statistics, name)(rows), getattr(statistics, name)(list(reversed(rows))))
        self.assertEqual(pickle.dumps(rows, protocol=4), before)

    def test_empty_unpaired_and_zero_eligible_inputs(self):
        for name in NAMES:
            self.assertEqual(getattr(statistics, name)([]), [])
        for algorithm in ("greedy", "local_search"):
            for name in NAMES[1:]:
                self.assertEqual(getattr(statistics, name)([row(0, algorithm, 6)]), [])
        for optimum, coverage in ((None, 0), (0, 0), (10, 10)):
            with self.subTest(optimum=optimum):
                rows = [row(0, algorithm, coverage, optimum) for algorithm in ("greedy", "local_search")]
                failure, = statistics._greedy_failure_statistics(rows)
                self.assertEqual(failure.failure_rate, None if optimum is None else 0.0)
                recovery, = statistics._local_search_recovery_statistics(rows)
                self.assertEqual(recovery.eligible_pair_count, 0)
                self.assertIsNone(recovery.eligible_pair_rate)
                self.assertIsNone(recovery.mean_gap_recovery_rate)
                self.assertIsNone(recovery.full_recovery_rate)
                remaining, = statistics._local_search_remaining_gap_statistics(rows)
                self.assertIsNone(remaining.mean_remaining_relative_gap)
                self.assertIsNone(remaining.maximum_remaining_relative_gap)
                self.assertIsNone(remaining.zero_remaining_gap_rate)

    def test_pairing_and_reference_errors_are_rejected(self):
        for rows, message in invalid_pairs():
            for name in NAMES[1:]:
                with self.subTest(function=name, message=message):
                    with self.assertRaises(ValueError) as caught:
                        getattr(statistics, name)(rows)
                    self.assertEqual(str(caught.exception), message)

    def test_greedy_seed_duplicate_status_and_coverage_are_rejected(self):
        greedy = row(0, "greedy", 6)
        for rows, message in (
            ([greedy, greedy], "classical greedy failure statistics require exactly one run per instance unit"),
            ([replace(greedy, algorithm_seed=1)], "classical greedy failure statistics forbid algorithm seeds"),
            ([replace(greedy, status=SolutionStatus.OPTIMAL, best_bound=6)], "classical greedy records must be feasible, timeout, or error"),
            ([replace(greedy, coverage=11)], "classical greedy coverage exceeds its normalized exact optimum"),
        ):
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as caught:
                    statistics._greedy_failure_statistics(rows)
                self.assertEqual(str(caught.exception), message)

    def test_seeded_registry_replacements_remain_ineligible(self):
        for algorithm in ("greedy", "local_search"):
            replacement = replace(statistics.ALGORITHMS[algorithm], uses_random_seed=True)
            with patch.dict(statistics.ALGORITHMS, {algorithm: replacement}):
                for name in NAMES[1:]:
                    self.assertEqual(getattr(statistics, name)(known_rows()), [])
                failures = statistics._greedy_failure_statistics(known_rows())
                self.assertEqual(bool(failures), algorithm == "local_search")


if __name__ == "__main__":
    unittest.main()
