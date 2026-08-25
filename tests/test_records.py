from __future__ import annotations

import csv
import io
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.contracts import (
    BNB_NODE_REDUCTION_SCHEMA_VERSION,
    BranchAndBoundNodeReductionRecord,
    CENSORED_RUNTIME_SCHEMA_VERSION,
    CensoredRuntimeRecord,
    CONFIDENCE_INTERVAL_SCHEMA_VERSION,
    ConfidenceIntervalRecord,
    GREEDY_FAILURE_SCHEMA_VERSION,
    HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION,
    INSTANCE_RECORD_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    BenchmarkResult,
    DescriptiveStatisticsRecord,
    GreedyFailureRecord,
    HeuristicExactRuntimeRatioRecord,
    InstanceRecord,
    LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION,
    LocalSearchRemainingGapRecord,
    QUALITY_RUNTIME_PARETO_SCHEMA_VERSION,
    QualityRuntimeParetoRecord,
    RunRecord,
    SummaryRecord,
)
from maxcover.config import parse_config
from maxcover.model import SolutionStatus


def _run_record(status: SolutionStatus) -> RunRecord:
    values = {
        SolutionStatus.OPTIMAL: (7, 7, 7, 0.0, (0,)),
        SolutionStatus.FEASIBLE: (6, None, 7, 1 / 7, (1,)),
        SolutionStatus.TIMEOUT: (5, 8, 7, 2 / 7, (2,)),
        SolutionStatus.ERROR: (None, None, 7, None, ()),
    }
    coverage, best_bound, optimum, gap, selected = values[status]
    return RunRecord(
        case="case",
        repetition=2,
        seed=42,
        family="uniform",
        universe_size=10,
        set_count=4,
        k=2,
        parameters='{"z":2,"a":1}',
        algorithm="algorithm",
        algorithm_options='{"time_limit_seconds":2.0,"max_set_count":9}',
        status=status,
        coverage=coverage,
        best_bound=best_bound,
        optimum=optimum,
        optimality_gap=gap,
        runtime_seconds=0.01234567894,
        nodes_or_iterations=12,
        selected=selected,
    )


def _string_row(record: RunRecord) -> dict[str, str]:
    return {name: str(value) for name, value in record.to_csv_row().items()}


class RecordContractTests(unittest.TestCase):
    def test_run_record_round_trips_every_status_through_csv(self) -> None:
        records = tuple(_run_record(status) for status in SolutionStatus)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=RunRecord.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(record.to_csv_row() for record in records)

        stream.seek(0)
        restored = tuple(
            RunRecord.from_csv_row(row) for row in csv.DictReader(stream)
        )
        self.assertEqual(
            [record.to_csv_row() for record in restored],
            [record.to_csv_row() for record in records],
        )
        self.assertEqual(restored[0].parameters, '{"a":1,"z":2}')
        self.assertEqual(
            restored[0].algorithm_options,
            '{"max_set_count":9,"time_limit_seconds":2.0}',
        )

    def test_summary_records_round_trip_with_values_and_blanks(self) -> None:
        records = (
            SummaryRecord(
                case="case",
                family="uniform",
                algorithm="greedy",
                runs=3,
                mean_coverage=6.25,
                mean_optimality_gap=0.125,
                max_optimality_gap=0.25,
                mean_runtime_seconds=0.00123456789,
                timeouts=0,
            ),
            SummaryRecord(
                case="errors",
                family="uniform",
                algorithm="broken",
                runs=2,
                mean_coverage=None,
                mean_optimality_gap=None,
                max_optimality_gap=None,
                mean_runtime_seconds=0.01,
                timeouts=0,
            ),
        )
        for record in records:
            row = {name: str(value) for name, value in record.to_csv_row().items()}
            restored = SummaryRecord.from_csv_row(row)
            self.assertEqual(restored.to_csv_row(), record.to_csv_row())

    def test_summary_allows_insignificant_floating_point_drift(self) -> None:
        # The point is only that a mean one ULP above the max must not trip the
        # mean <= max validator.  The field values are arbitrary placeholders.
        SummaryRecord(
            case="case",
            family="uniform",
            algorithm="greedy",
            runs=10,
            mean_coverage=151.0,
            mean_optimality_gap=0.10000000000000002,
            max_optimality_gap=0.1,
            mean_runtime_seconds=0.001,
            timeouts=0,
        )

    def test_csv_schema_is_stable_and_version_is_last(self) -> None:
        self.assertEqual(RECORD_SCHEMA_VERSION, 4)
        self.assertEqual(BNB_NODE_REDUCTION_SCHEMA_VERSION, 1)
        self.assertEqual(CENSORED_RUNTIME_SCHEMA_VERSION, 1)
        self.assertEqual(CONFIDENCE_INTERVAL_SCHEMA_VERSION, 1)
        self.assertEqual(INSTANCE_RECORD_SCHEMA_VERSION, 2)
        self.assertEqual(GREEDY_FAILURE_SCHEMA_VERSION, 1)
        self.assertEqual(HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION, 1)
        self.assertEqual(QUALITY_RUNTIME_PARETO_SCHEMA_VERSION, 1)
        self.assertEqual(LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION, 1)
        self.assertEqual(InstanceRecord.CSV_FIELDS[-1], "schema_version")
        self.assertEqual(RunRecord.CSV_FIELDS[-1], "schema_version")
        self.assertEqual(SummaryRecord.CSV_FIELDS[-1], "schema_version")
        self.assertEqual(
            DescriptiveStatisticsRecord.CSV_FIELDS[-1], "schema_version"
        )
        self.assertEqual(
            ConfidenceIntervalRecord.CSV_FIELDS[-1], "schema_version"
        )
        self.assertEqual(
            CensoredRuntimeRecord.CSV_FIELDS[-1], "schema_version"
        )
        self.assertEqual(GreedyFailureRecord.CSV_FIELDS[-1], "schema_version")
        self.assertEqual(
            HeuristicExactRuntimeRatioRecord.CSV_FIELDS[-1], "schema_version"
        )
        self.assertEqual(
            BranchAndBoundNodeReductionRecord.CSV_FIELDS[-1],
            "schema_version",
        )
        self.assertEqual(
            QualityRuntimeParetoRecord.CSV_FIELDS[-1],
            "schema_version",
        )
        self.assertEqual(
            LocalSearchRemainingGapRecord.CSV_FIELDS[-1], "schema_version"
        )
        self.assertEqual(
            GreedyFailureRecord.CSV_FIELDS,
            (
                "config_hash",
                "case_id",
                "family",
                "algorithm_id",
                "algorithm",
                "repetition_unit",
                "instance_count",
                "run_count",
                "completed_count",
                "timeout_count",
                "timeout_rate",
                "error_count",
                "error_rate",
                "valid_exact_reference_count",
                "exact_reference_rate",
                "no_exact_reference_count",
                "eligible_pair_count",
                "eligible_pair_rate",
                "failure_count",
                "optimal_tie_count",
                "failure_rate",
                "optimal_tie_rate",
                "schema_version",
            ),
        )
        self.assertEqual(
            RunRecord.CSV_FIELDS[:-1],
            (
                "config_hash",
                "case_id",
                "instance_id",
                "run_id",
                "case",
                "repetition",
                "seed",
                "family",
                "universe_size",
                "set_count",
                "k",
                "parameters",
                "algorithm_id",
                "algorithm_seed",
                "algorithm",
                "algorithm_options",
                "algorithm_metadata",
                "status",
                "coverage",
                "best_bound",
                "optimum",
                "optimality_gap",
                "runtime_seconds",
                "is_exact",
                "timed_out",
                "nodes_or_iterations",
                "selected",
                "error_message",
            ),
        )

    def test_run_record_rejects_malformed_csv_contracts(self) -> None:
        valid = _string_row(_run_record(SolutionStatus.TIMEOUT))
        mutations = []

        wrong_version = dict(valid)
        wrong_version["schema_version"] = "5"
        mutations.append(wrong_version)

        missing = dict(valid)
        del missing["case"]
        mutations.append(missing)

        unknown = dict(valid)
        unknown["extra"] = "value"
        mutations.append(unknown)

        invalid_integer = dict(valid)
        invalid_integer["repetition"] = "not-an-integer"
        mutations.append(invalid_integer)

        invalid_boolean = dict(valid)
        invalid_boolean["timed_out"] = "true"
        mutations.append(invalid_boolean)

        conflicting_boolean = dict(valid)
        conflicting_boolean["is_exact"] = "True"
        mutations.append(conflicting_boolean)

        invalid_options = dict(valid)
        invalid_options["algorithm_options"] = "[]"
        mutations.append(invalid_options)

        for row in mutations:
            with self.subTest(row=row), self.assertRaises(ValueError):
                RunRecord.from_csv_row(row)

    def test_records_and_benchmark_result_are_immutable(self) -> None:
        record = _run_record(SolutionStatus.OPTIMAL)
        result = BenchmarkResult(
            config=parse_config(
                {
                    "schema_version": 2,
                    "name": "test",
                    "repetitions": 1,
                    "algorithms": [{"name": "greedy"}],
                    "cases": [
                        {
                            "name": "tiny",
                            "family": "uniform",
                            "universe_size": 5,
                            "set_count": 3,
                            "k": 1,
                            "density": 0.5,
                        }
                    ],
                }
            ),
            rows=[record],
            summary=[],
            output_dir=Path("output"),
        )
        self.assertIsInstance(result.rows, tuple)
        self.assertIsInstance(result.greedy_failure_statistics, tuple)
        self.assertIsInstance(result.local_search_recovery_statistics, tuple)
        self.assertIsInstance(
            result.local_search_remaining_gap_statistics, tuple
        )
        self.assertIsInstance(
            result.heuristic_exact_runtime_ratio_statistics, tuple
        )
        self.assertIsInstance(result.bnb_node_reduction_statistics, tuple)
        self.assertIsInstance(result.quality_runtime_pareto_statistics, tuple)
        self.assertIsInstance(result.confidence_interval_statistics, tuple)
        self.assertIsInstance(result.censored_runtime_statistics, tuple)
        with self.assertRaises(TypeError):
            replace(result, greedy_failure_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, local_search_recovery_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, local_search_remaining_gap_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, heuristic_exact_runtime_ratio_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, bnb_node_reduction_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, quality_runtime_pareto_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, confidence_interval_statistics=(record,))
        with self.assertRaises(TypeError):
            replace(result, censored_runtime_statistics=(record,))
        with self.assertRaises(FrozenInstanceError):
            record.case = "changed"
        with self.assertRaises(FrozenInstanceError):
            result.output_dir = Path("changed")


if __name__ == "__main__":
    unittest.main()
