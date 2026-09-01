"""Verify the paired-seed analysis module on synthetic inputs only."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from statistics import fmean, stdev, variance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover._run_contracts import RunRecord
from maxcover.model import SolutionStatus
from maxcover.paired_seed_analysis import (
    AnalysisError,
    ComparisonRow,
    DifferenceSummary,
    analyze_pairing,
    load_run_records,
    main,
)


def _record(
    *,
    case: str,
    repetition: int,
    seed: int,
    family: str = "high_overlap",
    algorithm: str = "greedy",
    coverage: int = 0,
    optimum: int | None = 12,
    universe_size: int = 12,
    set_count: int = 3,
    k: int = 2,
    status: SolutionStatus = SolutionStatus.FEASIBLE,
) -> RunRecord:
    parameters = json.dumps({"probe": True}, sort_keys=True, separators=(",", ":"))
    gap = None if optimum is None else (optimum - coverage) / optimum
    return RunRecord(
        config_hash="synthetic",
        case_id=case,
        instance_id=f"{case}-{repetition}",
        run_id=f"{case}-{repetition}-{algorithm}",
        case=case,
        repetition=repetition,
        seed=seed,
        family=family,
        universe_size=universe_size,
        set_count=set_count,
        k=k,
        parameters=parameters,
        algorithm_id=algorithm,
        algorithm=algorithm,
        algorithm_options="{}",
        algorithm_metadata="{}",
        status=status,
        coverage=coverage,
        best_bound=(coverage if status is SolutionStatus.OPTIMAL else None),
        optimum=optimum,
        optimality_gap=gap,
        runtime_seconds=0.1,
        nodes_or_iterations=0,
        selected=(),
    )


def _write_records(directory: Path, records: list[RunRecord]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "raw_results.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=RunRecord.CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_row())


class CsvRoundTripTest(unittest.TestCase):
    """The module reads the canonical CSV records it is given."""

    def test_csv_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "run"
            rows = [
                _record(case="treatment", repetition=0, seed=7, coverage=6),
                _record(case="control", repetition=0, seed=7, coverage=5),
            ]
            _write_records(directory, rows)
            loaded = load_run_records(directory)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].case_id, "treatment")


class PairingInvarianceTest(unittest.TestCase):
    """Seed sharing is required and dimension matching is enforced."""

    def test_missing_shared_seed_is_rejected(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=1, coverage=6),
            _record(case="control", repetition=0, seed=2, coverage=5),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_records(directory / "paired", paired)
            _write_records(directory / "unpaired", paired)
            with self.assertRaises(AnalysisError):
                analyze_pairing(
                    load_run_records(directory / "paired"),
                    load_run_records(directory / "unpaired"),
                )

    def test_dimension_mismatch_is_rejected(self) -> None:
        paired = [
            _record(
                case="treatment",
                repetition=0,
                seed=1,
                coverage=6,
                universe_size=10,
                optimum=8,
            ),
            _record(
                case="control",
                repetition=0,
                seed=1,
                coverage=5,
                family="uniform",
                universe_size=11,
                optimum=8,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_records(directory / "paired", paired)
            _write_records(directory / "unpaired", paired)
            with self.assertRaises(AnalysisError):
                analyze_pairing(
                    load_run_records(directory / "paired"),
                    load_run_records(directory / "unpaired"),
                )

    def test_unmatched_control_is_rejected(self) -> None:
        record = _record(case="orphan_control", repetition=0, seed=1, coverage=6)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_records(directory / "paired", [record])
            _write_records(directory / "unpaired", [record])
            with self.assertRaises(AnalysisError):
                analyze_pairing(
                    load_run_records(directory / "paired"),
                    load_run_records(directory / "unpaired"),
                )

    def test_multiple_runs_per_unit_are_rejected(self) -> None:
        first = _record(case="treatment", repetition=0, seed=1, coverage=6)
        second = _record(case="treatment", repetition=0, seed=1, coverage=6)
        control = _record(
            case="treatment_control", repetition=0, seed=1, coverage=5
        )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_records(directory / "paired", [first, second, control])
            _write_records(directory / "unpaired", [first, second, control])
            with self.assertRaises(AnalysisError):
                analyze_pairing(
                    load_run_records(directory / "paired"),
                    load_run_records(directory / "unpaired"),
                )


class VarianceComparisonTest(unittest.TestCase):
    """Statistics match hand-computed values on synthetic data."""

    def _dataset(self, directory: Path) -> None:
        paired: list[RunRecord] = []
        for repetition, seed in enumerate(range(1001, 1006)):
            coverage = 6 + repetition
            paired.append(
                _record(
                    case="treatment",
                    repetition=repetition,
                    seed=seed,
                    coverage=coverage,
                )
            )
            paired.append(
                _record(
                    case="treatment_control",
                    repetition=repetition,
                    seed=seed,
                    coverage=coverage - 1,
                    family="uniform",
                )
            )
        _write_records(directory / "paired", paired)
        unpaired: list[RunRecord] = []
        treatment_values = [6, 5, 8, 4, 7]
        control_values = [5, 6, 4, 7, 3]
        for repetition in range(5):
            unpaired.append(
                _record(
                    case="treatment",
                    repetition=repetition,
                    seed=2000 + repetition,
                    coverage=treatment_values[repetition],
                )
            )
            unpaired.append(
                _record(
                    case="treatment_control",
                    repetition=repetition,
                    seed=3000 + repetition,
                    coverage=control_values[repetition],
                    family="uniform",
                )
            )
        _write_records(directory / "unpaired", unpaired)

    def test_shared_seed_pairing_cuts_variance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._dataset(directory)
            rows, samples = analyze_pairing(
                load_run_records(directory / "paired"),
                load_run_records(directory / "unpaired"),
            )
        row = rows[0]
        self.assertEqual(row.family, "high_overlap")
        self.assertEqual(row.paired.n, 5)
        self.assertEqual(row.unpaired.n, 5)
        self.assertEqual(row.paired_seed_shared_count, 5)
        self.assertEqual(row.unpaired_seed_shared_count, 0)
        self.assertAlmostEqual(row.paired.mean or 0.0, 1.0)
        self.assertAlmostEqual(row.paired.sample_variance or 0.0, 0.0)
        self.assertGreater(row.unpaired.sample_variance or 0.0, 0.0)
        ratio = row.variance_ratio()
        self.assertIsNotNone(ratio)
        self.assertLess(ratio or 0.0, 1.0)
        self.assertAlmostEqual(
            row.paired.treatment_control_correlation or 0.0,
            1.0,
            places=10,
        )
        differences = [a - b for a, b in zip([6, 5, 8, 4, 7], [5, 6, 4, 7, 3])]
        self.assertAlmostEqual(row.unpaired.mean or 0.0, fmean(differences))
        self.assertAlmostEqual(
            row.unpaired.sample_variance or 0.0, variance(differences)
        )
        self.assertAlmostEqual(
            row.unpaired.sample_standard_deviation or 0.0, stdev(differences)
        )
        self.assertEqual(len(samples), 20)
        paired_samples = [s for s in samples if s["scheme"] == "paired"]
        self.assertEqual(len(paired_samples), 10)
        self.assertTrue(all(s["seeds_equal"] for s in paired_samples))

    def test_optimality_gap_metric_uses_gap_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._dataset(directory)
            rows, _ = analyze_pairing(
                load_run_records(directory / "paired"),
                load_run_records(directory / "unpaired"),
            )
        gap_row = next(row for row in rows if row.metric == "optimality_gap")
        self.assertAlmostEqual(gap_row.paired.mean or 0.0, -1.0 / 12.0, places=10)

    def test_missing_metric_rows_are_counted(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=1, coverage=6),
            _record(case="treatment", repetition=1, seed=2, coverage=7),
            _record(
                case="treatment_control",
                repetition=0,
                seed=1,
                coverage=5,
                family="uniform",
            ),
            _record(
                case="treatment_control",
                repetition=1,
                seed=2,
                coverage=6,
                family="uniform",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_records(directory / "paired", paired)
            _write_records(
                directory / "unpaired",
                [
                    _record(case="treatment", repetition=0, seed=1, coverage=6),
                    _record(case="treatment", repetition=1, seed=2, coverage=7),
                    _record(
                        case="treatment_control",
                        repetition=0,
                        seed=1,
                        coverage=5,
                        family="uniform",
                    ),
                ],
            )
            rows, _ = analyze_pairing(
                load_run_records(directory / "paired"),
                load_run_records(directory / "unpaired"),
            )
        row = next(row for row in rows if row.metric == "coverage")
        self.assertEqual(row.expected_repetitions, 2)
        self.assertEqual(row.paired.n, 2)
        self.assertEqual(row.unpaired.n, 1)
        self.assertEqual(row.unpaired_missing_count, 1)
        self.assertEqual(row.paired_missing_count, 0)

    def test_cli_writes_comparison_and_differences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._dataset(directory)
            output = directory / "analysis"
            status = main(
                [
                    "--paired-results",
                    str(directory / "paired"),
                    "--unpaired-results",
                    str(directory / "unpaired"),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            self.assertTrue((output / "comparison.csv").is_file())
            self.assertTrue((output / "differences.csv").is_file())
            with (output / "comparison.csv").open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(set(rows[0]), set(ComparisonRow.CSV_FIELDS))

    def test_summary_of_empty_series_is_empty(self) -> None:
        summary = DifferenceSummary.of((), (), ())
        self.assertEqual(summary.n, 0)
        self.assertIsNone(summary.mean)
        self.assertIsNone(summary.sample_variance)


if __name__ == "__main__":
    unittest.main()
