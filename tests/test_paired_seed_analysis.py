"""Check synthetic arithmetic separately from plan-validated analysis inputs."""

from __future__ import annotations

import csv
from dataclasses import replace
import json
import sys
import tempfile
import unittest
from pathlib import Path
from statistics import fmean, stdev, variance

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / ".github" / "scripts" / "validate_benchmark_output.py"
sys.path.insert(0, str(ROOT / "src"))

from maxcover._instance_contracts import InstanceRecord
from maxcover._run_contracts import RunRecord
from maxcover.model import SolutionStatus
from maxcover.benchmark import run_benchmark
from maxcover.config import load_config
from maxcover.paired_seed_analysis import (
    AnalysisError,
    ComparisonRow,
    DifferenceSummary,
    _compare_records,
    analyze_pairing,
    load_instance_records,
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


def _instance_record(
    *,
    case: str,
    repetition: int,
    seed: int | None,
    family: str = "high_overlap",
    universe_size: int = 12,
    set_count: int = 3,
    k: int = 2,
) -> InstanceRecord:
    parameters = json.dumps({"probe": True}, sort_keys=True, separators=(",", ":"))
    return InstanceRecord(
        config_hash="synthetic",
        case_id=case,
        repetition=repetition,
        instance_id=f"{case}-{repetition}",
        seed=seed,
        family=family,
        generator_version=1,
        instance_origin="stochastic",
        is_adversarial=False,
        universe_size=universe_size,
        set_count=set_count,
        k=k,
        parameters=parameters,
        incidence_count=0,
        covered_element_count=0,
        unique_set_count=set_count,
        actual_density=0.0,
        mean_set_size=0.0,
        pairwise_overlap_mean_jaccard=None,
        pairwise_overlap_total_pairs=set_count * (set_count - 1) // 2,
        pairwise_overlap_valid_pairs=0,
        coverage_skew_gini=0.0,
        duplicate_set_count=0,
        duplicate_set_ratio=0.0,
        dominated_set_count=0,
        dominated_set_ratio=0.0,
        dominated_unique_ratio=0.0,
        preprocessed_set_count=set_count,
    )


def _coupled_instance(
    *,
    case: str,
    repetition: int,
    seed: int,
    coupling_pair_id: str,
    coupling_seed: int,
) -> InstanceRecord:
    """A coupling-capable long_tail instance with an injected coupling seed."""

    set_size = 4
    parameters = json.dumps(
        {"set_size": set_size, "gamma": 0.0, "coupling_seed": coupling_seed},
        sort_keys=True,
        separators=(",", ":"),
    )
    return InstanceRecord(
        config_hash="synthetic",
        case_id=case,
        repetition=repetition,
        instance_id=f"{case}-{repetition}",
        seed=seed,
        family="long_tail",
        generator_version=1,
        instance_origin="stochastic",
        is_adversarial=False,
        universe_size=12,
        set_count=3,
        k=2,
        parameters=parameters,
        incidence_count=3 * set_size,
        covered_element_count=0,
        unique_set_count=3,
        actual_density=set_size / 12.0,
        mean_set_size=float(set_size),
        pairwise_overlap_mean_jaccard=None,
        pairwise_overlap_total_pairs=3,
        pairwise_overlap_valid_pairs=0,
        coverage_skew_gini=0.0,
        duplicate_set_count=0,
        duplicate_set_ratio=0.0,
        dominated_set_count=0,
        dominated_set_ratio=0.0,
        dominated_unique_ratio=0.0,
        preprocessed_set_count=3,
        coupling_pair_id=coupling_pair_id,
        coupling_seed=coupling_seed,
        research_question_id="long_tail_coverage_skew",
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


def _write_instances(directory: Path, records: list[InstanceRecord]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "instances.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=InstanceRecord.CSV_FIELDS)
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

    def test_instance_csv_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "run"
            rows = [
                _instance_record(case="treatment", repetition=0, seed=7),
                _coupled_instance(
                    case="control",
                    repetition=0,
                    seed=7,
                    coupling_pair_id='seed_group="pair"|repetition=0',
                    coupling_seed=7,
                ),
            ]
            _write_instances(directory, rows)
            loaded = load_instance_records(directory)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].case_id, "treatment")
        self.assertEqual(loaded[1].coupling_seed, 7)


class PairingInvarianceTest(unittest.TestCase):
    """Seed sharing is required and dimension matching is enforced."""

    def _pair_records(
        self, *, paired_seed: int, unpaired_seed: int
    ) -> tuple[list[RunRecord], list[RunRecord]]:
        paired = [
            _record(case="treatment", repetition=0, seed=paired_seed, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=paired_seed,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=unpaired_seed, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=unpaired_seed + 1,
                coverage=5,
                family="uniform",
            ),
        ]
        return paired, unpaired

    def _instances_for(
        self, paired: list[RunRecord], unpaired: list[RunRecord]
    ) -> tuple[list[InstanceRecord], list[InstanceRecord]]:
        paired_instances = [
            _instance_record(
                case=row.case_id,
                repetition=row.repetition,
                seed=row.seed,
                family=row.family,
            )
            for row in paired
        ]
        unpaired_instances = [
            _instance_record(
                case=row.case_id,
                repetition=row.repetition,
                seed=row.seed,
                family=row.family,
            )
            for row in unpaired
        ]
        return paired_instances, unpaired_instances

    def test_missing_shared_seed_is_rejected(self) -> None:
        paired, unpaired = self._pair_records(paired_seed=1, unpaired_seed=2000)
        paired[1] = _record(
            case="treatment_control", repetition=0, seed=2, coverage=5, family="uniform"
        )
        paired_instances, unpaired_instances = self._instances_for(paired, unpaired)
        with self.assertRaises(AnalysisError):
            _compare_records(
                paired,
                unpaired,
                paired_instances=paired_instances,
                unpaired_instances=unpaired_instances,
            )

    def test_dimension_mismatch_is_rejected(self) -> None:
        paired, unpaired = self._pair_records(paired_seed=1, unpaired_seed=2000)
        paired[0] = _record(
            case="treatment",
            repetition=0,
            seed=1,
            coverage=6,
            universe_size=10,
            optimum=8,
        )
        unpaired[0] = _record(
            case="treatment",
            repetition=0,
            seed=2000,
            coverage=6,
            universe_size=10,
            optimum=8,
        )
        paired_instances, unpaired_instances = self._instances_for(paired, unpaired)
        paired_instances[0] = _instance_record(
            case="treatment", repetition=0, seed=1, universe_size=10
        )
        unpaired_instances[0] = _instance_record(
            case="treatment", repetition=0, seed=2000, universe_size=10
        )
        with self.assertRaises(AnalysisError):
            _compare_records(
                paired,
                unpaired,
                paired_instances=paired_instances,
                unpaired_instances=unpaired_instances,
            )

    def test_unmatched_control_is_rejected(self) -> None:
        record = _record(case="orphan_control", repetition=0, seed=1, coverage=6)
        instance = _instance_record(case="orphan_control", repetition=0, seed=1)
        with self.assertRaises(AnalysisError):
            _compare_records(
                [record],
                [record],
                paired_instances=[instance],
                unpaired_instances=[instance],
            )

    def test_multiple_runs_per_unit_are_rejected(self) -> None:
        first = _record(case="treatment", repetition=0, seed=1, coverage=6)
        second = _record(case="treatment", repetition=0, seed=1, coverage=6)
        control = _record(
            case="treatment_control", repetition=0, seed=1, coverage=5
        )
        instance = _instance_record(case="treatment", repetition=0, seed=1)
        control_instance = _instance_record(
            case="treatment_control", repetition=0, seed=1
        )
        with self.assertRaises(AnalysisError):
            _compare_records(
                [first, second, control],
                [first, second, control],
                paired_instances=[instance, control_instance],
                unpaired_instances=[instance, control_instance],
            )


class EffectiveCouplingTest(unittest.TestCase):
    """The effective seed is the coupling seed when one was injected."""

    def test_shared_coupling_accepts_distinct_instance_seeds(self) -> None:
        for coupled_control in (False, True):
            with self.subTest(coupled_control=coupled_control):
                control_family = "long_tail" if coupled_control else "uniform"
                paired = [
                    _record(case="treatment", repetition=0, seed=11,
                            family="long_tail", coverage=6),
                    _record(case="treatment_control", repetition=0, seed=7,
                            family=control_family, coverage=5),
                ]
                unpaired = [
                    _record(case="treatment", repetition=0, seed=2000,
                            family="long_tail", coverage=6),
                    _record(case="treatment_control", repetition=0, seed=3000,
                            family=control_family, coverage=5),
                ]
                paired_instances = [
                    _coupled_instance(
                        case="treatment", repetition=0, seed=11,
                        coupling_pair_id='seed_group="pair"|repetition=0',
                        coupling_seed=7,
                    ),
                    _coupled_instance(
                        case="treatment_control", repetition=0, seed=7,
                        coupling_pair_id='seed_group="pair"|repetition=0',
                        coupling_seed=7,
                    ) if coupled_control else _instance_record(
                        case="treatment_control", repetition=0, seed=7,
                        family="uniform",
                    ),
                ]
                unpaired_instances = [
                    _coupled_instance(
                        case=row.case_id, repetition=0, seed=row.seed,
                        coupling_pair_id=f'case="{row.case_id}"|repetition=0',
                        coupling_seed=row.seed,
                    ) if row.family == "long_tail" else _instance_record(
                        case=row.case_id, repetition=0,
                        seed=row.seed, family=row.family,
                    )
                    for row in unpaired
                ]
                paired = [replace(row, family=item.family, parameters=item.parameters)
                          for row, item in zip(paired, paired_instances)]
                unpaired = [replace(row, family=item.family, parameters=item.parameters)
                            for row, item in zip(unpaired, unpaired_instances)]
                rows, samples = _compare_records(
                    paired, unpaired, paired_instances=paired_instances,
                    unpaired_instances=unpaired_instances,
                )
                coverage = next(row for row in rows if row.metric == "coverage")
                self.assertEqual(coverage.paired.n, 1)
                self.assertEqual(coverage.paired.mean, 1.0)
                self.assertEqual(coverage.paired_seed_shared_count, 0)
                sample = next(row for row in samples
                              if row["scheme"] == "paired" and row["metric"] == "coverage")
                self.assertEqual(sample["treatment_seed"], 11)
                self.assertEqual(sample["control_seed"], 7)
                self.assertFalse(sample["seeds_equal"])

    def test_paired_scheme_rejects_unequal_effective_coupling_seed(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=7, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=7,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=3000,
                coverage=5,
                family="uniform",
            ),
        ]
        paired_instances = [
            _coupled_instance(
                case="treatment",
                repetition=0,
                seed=7,
                coupling_pair_id='seed_group="pair"|repetition=0',
                coupling_seed=99,
            ),
            _instance_record(
                case="treatment_control", repetition=0, seed=7, family="uniform"
            ),
        ]
        unpaired_instances = [
            _instance_record(case="treatment", repetition=0, seed=2000),
            _instance_record(
                case="treatment_control", repetition=0, seed=3000, family="uniform"
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "effective coupling seed"):
            _compare_records(
                paired,
                unpaired,
                paired_instances=paired_instances,
                unpaired_instances=unpaired_instances,
            )

    def test_paired_scheme_accepts_sharing_effective_coupling_seed(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=7, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=7,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=3000,
                coverage=5,
                family="uniform",
            ),
        ]
        paired_instances = [
            _coupled_instance(
                case="treatment",
                repetition=0,
                seed=7,
                coupling_pair_id='seed_group="pair"|repetition=0',
                coupling_seed=7,
            ),
            _instance_record(
                case="treatment_control", repetition=0, seed=7, family="uniform"
            ),
        ]
        unpaired_instances = [
            _coupled_instance(case="treatment", repetition=0, seed=2000,
                              coupling_pair_id="independent", coupling_seed=2000),
            _instance_record(
                case="treatment_control", repetition=0, seed=3000, family="uniform"
            ),
        ]
        paired = [replace(row, family=item.family, parameters=item.parameters)
                  for row, item in zip(paired, paired_instances)]
        unpaired = [replace(row, family=item.family, parameters=item.parameters)
                    for row, item in zip(unpaired, unpaired_instances)]
        rows, _ = _compare_records(
            paired,
            unpaired,
            paired_instances=paired_instances,
            unpaired_instances=unpaired_instances,
        )
        self.assertEqual(rows[0].paired.n, 1)

    def test_unpaired_scheme_rejects_shared_effective_seed(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=7, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=7,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=2000,
                coverage=5,
                family="uniform",
            ),
        ]
        paired_instances = [
            _instance_record(case="treatment", repetition=0, seed=7),
            _instance_record(
                case="treatment_control", repetition=0, seed=7, family="uniform"
            ),
        ]
        unpaired_instances = [
            _instance_record(case="treatment", repetition=0, seed=2000),
            _instance_record(
                case="treatment_control", repetition=0, seed=2000, family="uniform"
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "independent effective seeds"):
            _compare_records(
                paired,
                unpaired,
                paired_instances=paired_instances,
                unpaired_instances=unpaired_instances,
            )

    def test_partial_instance_pairs_are_rejected(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=7, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=7,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=3000,
                coverage=5,
                family="uniform",
            ),
        ]
        paired_instances = [
            _instance_record(case="treatment", repetition=0, seed=7),
        ]
        unpaired_instances = [
            _instance_record(case="treatment", repetition=0, seed=2000),
            _instance_record(
                case="treatment_control", repetition=0, seed=3000, family="uniform"
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "records only one"):
            _compare_records(
                paired,
                unpaired,
                paired_instances=paired_instances,
                unpaired_instances=unpaired_instances,
            )

    def test_absent_instance_pairs_are_rejected(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=7, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=7,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=3000,
                coverage=5,
                family="uniform",
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "records neither"):
            _compare_records(
                paired,
                unpaired,
                paired_instances=[],
                unpaired_instances=[],
            )

    def test_missing_effective_seed_is_rejected(self) -> None:
        paired = [
            _record(case="treatment", repetition=0, seed=7, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=7,
                coverage=5,
                family="uniform",
            ),
        ]
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(
                case="treatment_control",
                repetition=0,
                seed=3000,
                coverage=5,
                family="uniform",
            ),
        ]
        paired_instances = [
            _instance_record(case="treatment", repetition=0, seed=None),
            _instance_record(
                case="treatment_control", repetition=0, seed=7, family="uniform"
            ),
        ]
        unpaired_instances = [
            _instance_record(case="treatment", repetition=0, seed=2000),
            _instance_record(
                case="treatment_control", repetition=0, seed=3000, family="uniform"
            ),
        ]
        with self.assertRaisesRegex(AnalysisError, "neither a seed nor"):
            _compare_records(
                paired,
                unpaired,
                paired_instances=paired_instances,
                unpaired_instances=unpaired_instances,
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
        _write_instances(
            directory / "paired",
            [
                _instance_record(
                    case=row.case_id,
                    repetition=row.repetition,
                    seed=row.seed,
                    family=row.family,
                )
                for row in paired
            ],
        )
        _write_instances(
            directory / "unpaired",
            [
                _instance_record(
                    case=row.case_id,
                    repetition=row.repetition,
                    seed=row.seed,
                    family=row.family,
                )
                for row in unpaired
            ],
        )

    def test_shared_seed_pairing_cuts_variance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._dataset(directory)
            rows, samples = _compare_records(
                load_run_records(directory / "paired"),
                load_run_records(directory / "unpaired"),
                paired_instances=load_instance_records(directory / "paired"),
                unpaired_instances=load_instance_records(
                    directory / "unpaired"
                ),
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
            rows, _ = _compare_records(
                load_run_records(directory / "paired"),
                load_run_records(directory / "unpaired"),
                paired_instances=load_instance_records(directory / "paired"),
                unpaired_instances=load_instance_records(
                    directory / "unpaired"
                ),
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
        unpaired = [
            _record(case="treatment", repetition=0, seed=2000, coverage=6),
            _record(case="treatment", repetition=1, seed=2001, coverage=7),
            _record(
                case="treatment_control",
                repetition=0,
                seed=3000,
                coverage=5,
                family="uniform",
            ),
        ]
        paired_instances = [
            _instance_record(case="treatment", repetition=0, seed=1),
            _instance_record(case="treatment", repetition=1, seed=2),
            _instance_record(
                case="treatment_control", repetition=0, seed=1, family="uniform"
            ),
            _instance_record(
                case="treatment_control", repetition=1, seed=2, family="uniform"
            ),
        ]
        unpaired_instances = [
            _instance_record(case="treatment", repetition=0, seed=2000),
            _instance_record(case="treatment", repetition=1, seed=2001),
            _instance_record(
                case="treatment_control", repetition=0, seed=3000, family="uniform"
            ),
            _instance_record(
                case="treatment_control", repetition=1, seed=3001, family="uniform"
            ),
        ]
        rows, _ = _compare_records(
            paired,
            unpaired,
            paired_instances=paired_instances,
            unpaired_instances=unpaired_instances,
        )
        row = next(row for row in rows if row.metric == "coverage")
        self.assertEqual(row.expected_repetitions, 2)
        self.assertEqual(row.paired.n, 2)
        self.assertEqual(row.unpaired.n, 1)
        self.assertEqual(row.unpaired_missing_count, 1)
        self.assertEqual(row.paired_missing_count, 0)

    def test_runs_must_match_their_instance_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._dataset(directory)
            paired = load_run_records(directory / "paired")
            unpaired = load_run_records(directory / "unpaired")
            for field, value in (("config_hash", "other"), ("instance_id", "other"), ("seed", 42)):
                with self.subTest(field=field):
                    changed = [replace(paired[0], **{field: value}), *paired[1:]]
                    with self.assertRaisesRegex(AnalysisError, "run does not match its instance row"):
                        _compare_records(
                            changed, unpaired,
                            paired_instances=load_instance_records(directory / "paired"),
                            unpaired_instances=load_instance_records(directory / "unpaired"),
                        )



    def test_summary_of_empty_series_is_empty(self) -> None:
        summary = DifferenceSummary.of((), (), ())
        self.assertEqual(summary.n, 0)
        self.assertIsNone(summary.mean)
        self.assertIsNone(summary.sample_variance)
        self.assertIsNone(summary.treatment_control_correlation)


class PlannedPairingTests(unittest.TestCase):
    """Real runner outputs exercise the public input boundary without manifests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.paths = {}
        cls.configs = {}
        cls.runs = {}
        cls.instances = {}
        for scheme in ("paired", "unpaired"):
            config = json.loads((ROOT / f"configs/pairing_{scheme}.json").read_text(encoding="utf-8"))
            config["repetitions"] = 2
            config["cases"] = config["cases"][:2]
            for case in config["cases"]:
                case.update(universe_size=12, set_count=6, k=2)
            config["algorithms"] = [{"name": "greedy"}, {"name": "brute_force"}]
            path = cls.root / f"{scheme}.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            run_benchmark(path, cls.root / scheme)
            cls.paths[scheme] = path
            cls.configs[scheme] = load_config(path)
            cls.runs[scheme] = load_run_records(cls.root / scheme)
            cls.instances[scheme] = load_instance_records(cls.root / scheme)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def analyze(self, records=None, *, scheme="paired", instances=None):
        runs = dict(self.runs)
        inputs = dict(self.instances)
        if records is not None:
            runs[scheme] = records
        if instances is not None:
            inputs[scheme] = instances
        return analyze_pairing(
            runs["paired"], runs["unpaired"],
            paired_config=self.configs["paired"], unpaired_config=self.configs["unpaired"],
            paired_instances=inputs["paired"], unpaired_instances=inputs["unpaired"],
        )

    def test_real_complete_inputs_and_reordered_rows_are_accepted(self) -> None:
        expected = self.analyze()
        self.assertEqual(expected, self.analyze(list(reversed(self.runs["paired"]))))
        self.assertTrue(expected[0])

    def test_run_identity_and_algorithm_metadata_match_the_plan(self) -> None:
        for scheme in ("paired", "unpaired"):
            original = self.runs[scheme]
            for field, value in (("run_id", "f" * 64), ("algorithm", "unknown"),
                                 ("algorithm_id", "unknown"), ("algorithm_options", '{"unknown":true}'),
                                 ("seed", original[0].seed + 1), ("instance_id", "e" * 64)):
                with self.subTest(scheme=scheme, field=field):
                    changed = [replace(original[0], **{field: value}), *original[1:]]
                    with self.assertRaisesRegex(AnalysisError, "execution plan"):
                        self.analyze(changed, scheme=scheme)

    def test_duplicate_and_missing_planned_runs_are_rejected(self) -> None:
        original = self.runs["paired"]
        with self.assertRaisesRegex(AnalysisError, "duplicate run_id"):
            self.analyze([replace(row, run_id=original[0].run_id) for row in original])
        with self.assertRaisesRegex(AnalysisError, "execution plan"):
            self.analyze(original[:-1])

    def test_coordinated_coverage_gap_edits_still_fail_selected_set_check(self) -> None:
        original = self.runs["paired"]
        index = next(i for i, row in enumerate(original) if row.algorithm == "greedy")
        row = original[index]
        changed = list(original)
        changed[index] = replace(row, coverage=1, optimality_gap=(row.optimum - 1) / row.optimum)
        with self.assertRaisesRegex(AnalysisError, "coverage does not match"):
            self.analyze(changed)

    def test_instance_table_must_match_the_configured_generation(self) -> None:
        changed = list(self.instances["paired"])
        changed[0] = replace(changed[0], pairwise_overlap_mean_jaccard=0.999)
        with self.assertRaisesRegex(AnalysisError, "instance plan"):
            self.analyze(instances=changed)

    def test_coordinated_optimum_gap_edit_is_rejected(self) -> None:
        changed = list(self.runs["paired"])
        index = next(i for i, row in enumerate(changed) if row.algorithm == "greedy")
        row = changed[index]
        changed[index] = replace(row, optimum=row.optimum + 1,
                                 optimality_gap=(row.optimum + 1 - row.coverage) / (row.optimum + 1))
        with self.assertRaisesRegex(AnalysisError, "validated reference"):
            self.analyze(changed)

    def test_unavailable_reference_stays_unknown(self) -> None:
        changed = []
        for row in self.runs["paired"]:
            if row.algorithm == "brute_force":
                metadata = json.loads(row.algorithm_metadata)
                metadata["termination"] = "error"
                row = replace(row, status=SolutionStatus.ERROR, coverage=None, best_bound=None,
                              selected=(), optimum=None, optimality_gap=None,
                              algorithm_metadata=json.dumps(metadata), error_message="test failure")
            else:
                row = replace(row, optimum=None, optimality_gap=None)
            changed.append(row)
        rows, _ = self.analyze(changed)
        greedy_gap = next(row for row in rows if row.algorithm_id == "greedy" and row.metric == "optimality_gap")
        self.assertEqual(greedy_gap.paired.n, 0)
        self.assertEqual(greedy_gap.paired_missing_count, 2)
        row = changed[0]
        if row.algorithm == "greedy":
            changed[0] = replace(row, optimum=12, optimality_gap=(12-row.coverage)/12)
        with self.assertRaisesRegex(AnalysisError, "validated reference"):
            self.analyze(changed)

    def test_present_error_record_is_distinct_from_a_missing_run(self) -> None:
        changed = list(self.runs["paired"])
        index = next(i for i, row in enumerate(changed) if row.algorithm == "greedy")
        metadata = json.loads(changed[index].algorithm_metadata)
        metadata["termination"] = "error"
        changed[index] = replace(changed[index], status=SolutionStatus.ERROR,
                                 coverage=None, best_bound=None, optimality_gap=None, selected=(),
                                 algorithm_metadata=json.dumps(metadata), error_message="test failure")
        rows, _ = self.analyze(changed)
        row = next(item for item in rows if item.algorithm_id == "greedy" and item.metric == "coverage")
        self.assertEqual(row.paired_missing_count, 1)

    def test_cli_checks_configurations_before_writing_comparisons(self) -> None:
        output = self.root / "analysis"
        argv = [
            "--paired-config", str(self.paths["paired"]),
            "--unpaired-config", str(self.paths["unpaired"]),
            "--paired-results", str(self.root / "paired"),
            "--unpaired-results", str(self.root / "unpaired"), "--output", str(output),
        ]
        status = main(argv)
        self.assertEqual(status, 0)
        self.assertTrue((output / "comparison.csv").is_file())
        self.assertTrue((output / "differences.csv").is_file())
        self.assertFalse((output / "analysis_manifest.json").exists())
        invalid_output = self.root / "invalid-analysis"
        argv[argv.index("--paired-config") + 1] = str(self.paths["unpaired"])
        argv[argv.index("--output") + 1] = str(invalid_output)
        with self.assertRaises(AnalysisError):
            main(argv)
        self.assertFalse(invalid_output.exists())


if __name__ == "__main__":
    unittest.main()
