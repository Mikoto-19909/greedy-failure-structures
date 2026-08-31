from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import ALGORITHMS, brute_force, greedy
from maxcover.benchmark import (
    _instance_record,
    _instances_for_config,
    _reference_status_records,
    run_benchmark,
)
from maxcover.config import parse_config
from maxcover.contracts import REFERENCE_STATUSES, RunRecord
from maxcover.contracts import (
    ReferenceCensoringBiasRecord,
    ReferenceCoverageRecord,
    ReferenceCutoffSensitivityRecord,
    ReferenceStatusRecord,
)
from maxcover.model import Solution, SolutionStatus
from maxcover.reproducibility import canonical_json, config_hash


def _write_config(root: Path, value: dict[str, object]) -> Path:
    path = root / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _uniform_case() -> dict[str, object]:
    return {
        "name": "same_slice",
        "family": "uniform",
        "universe_size": 12,
        "set_count": 5,
        "k": 2,
        "density": 0.25,
    }


class ReferenceCoverageTests(unittest.TestCase):
    def test_reference_records_round_trip_through_the_public_contract(self) -> None:
        record_types = (
            ReferenceStatusRecord,
            ReferenceCoverageRecord,
            ReferenceCensoringBiasRecord,
            ReferenceCutoffSensitivityRecord,
        )
        for record_type in record_types:
            with self.subTest(record_type=record_type.__name__):
                self.assertEqual(record_type.__module__, "maxcover.contracts")

    def test_feasible_precedes_timeout_in_the_effective_missing_status(self) -> None:
        config = parse_config(
            {
                "schema_version": 3,
                "name": "mixed unresolved statuses",
                "base_seed": 1,
                "repetitions": 1,
                "algorithms": [
                    {"id": "feasible_source", "name": "branch_and_bound"},
                    {
                        "id": "timeout_source",
                        "name": "branch_and_bound_enhanced",
                    },
                ],
                "cases": [_uniform_case()],
            }
        )
        planned = _instances_for_config(config)[0]
        identifier = config_hash(config)
        instance_record = _instance_record(planned, identifier)
        selected = (0,)
        coverage = planned.instance.coverage(selected)

        def row(
            algorithm_id: str,
            algorithm: str,
            status: SolutionStatus,
        ) -> RunRecord:
            return RunRecord(
                config_hash=identifier,
                case_id=planned.case_id,
                instance_id=planned.instance_id,
                case=planned.case_id,
                repetition=planned.repetition,
                seed=planned.instance.seed,
                family=planned.instance.family,
                universe_size=planned.instance.universe_size,
                set_count=planned.instance.set_count,
                k=planned.instance.k,
                parameters=canonical_json(dict(planned.instance.parameters)),
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                algorithm_options="{}",
                status=status,
                coverage=coverage,
                best_bound=None,
                optimum=None,
                optimality_gap=None,
                runtime_seconds=0.0,
                nodes_or_iterations=0,
                selected=selected,
            )

        status = _reference_status_records(
            config,
            [
                row(
                    "feasible_source",
                    "branch_and_bound",
                    SolutionStatus.FEASIBLE,
                ),
                row(
                    "timeout_source",
                    "branch_and_bound_enhanced",
                    SolutionStatus.TIMEOUT,
                ),
            ],
            [instance_record],
        )[0]
        self.assertEqual(status.reference_status, "feasible")

    def test_all_generated_instances_remain_in_status_coverage_and_bias(self) -> None:
        original = ALGORITHMS["branch_and_bound"]

        def controlled_runner(instance, options):
            del options
            assert instance.seed is not None
            mode = instance.seed % 3
            if mode == 2:
                raise RuntimeError("controlled exact failure")
            if mode == 1:
                incumbent = greedy(instance)
                return Solution(
                    algorithm="branch_and_bound",
                    selected=incumbent.selected,
                    feasible_value=incumbent.feasible_value,
                    runtime_seconds=0.0,
                    status=SolutionStatus.TIMEOUT,
                )
            optimum = brute_force(instance, time_limit_seconds=None)
            return Solution(
                algorithm="branch_and_bound",
                selected=optimum.selected,
                feasible_value=optimum.feasible_value,
                runtime_seconds=0.0,
                status=SolutionStatus.OPTIMAL,
                best_bound=optimum.feasible_value,
            )

        config = {
            "schema_version": 3,
            "name": "reference censoring",
            "base_seed": 3,
            "repetitions": 3,
            "algorithms": [
                {
                    "id": "reference_cutoff_1s",
                    "name": "branch_and_bound",
                    "options": {"time_limit_seconds": 1.0},
                }
            ],
            "cases": [_uniform_case()],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(
                ALGORITHMS,
                {"branch_and_bound": replace(original, runner=controlled_runner)},
            ):
                result = run_benchmark(
                    _write_config(root, config),
                    root / "output",
                )
            chart = (root / "output" / "reference_coverage_by_case.svg").read_text(
                encoding="utf-8"
            )

        self.assertEqual(
            [record.reference_status for record in result.reference_statuses],
            ["optimal", "timeout", "error"],
        )
        self.assertEqual(
            {
                json.loads(record.exact_solver_statuses)["reference_cutoff_1s"]
                for record in result.reference_statuses
            },
            {"optimal", "timeout", "error"},
        )
        coverage = {
            record.status: record
            for record in result.reference_coverage_statistics
        }
        self.assertEqual(set(coverage), set(REFERENCE_STATUSES))
        self.assertTrue(
            all(record.generated_instance_count == 3 for record in coverage.values())
        )
        self.assertEqual(coverage["optimal"].status_instance_count, 1)
        self.assertEqual(coverage["timeout"].status_instance_count, 1)
        self.assertEqual(coverage["error"].status_instance_count, 1)
        self.assertAlmostEqual(coverage["optimal"].reference_coverage, 1 / 3)

        set_count_bias = next(
            record
            for record in result.reference_censoring_bias_statistics
            if record.metric == "set_count"
        )
        self.assertEqual(set_count_bias.retained_instance_count, 1)
        self.assertEqual(set_count_bias.excluded_instance_count, 2)
        self.assertEqual(set_count_bias.comparison_status, "estimable")
        self.assertEqual(set_count_bias.excluded_minus_retained, 0.0)

        cutoff = result.reference_cutoff_sensitivity_statistics[0]
        self.assertEqual(cutoff.generated_instance_count, 3)
        self.assertEqual(cutoff.optimal_count, 1)
        self.assertEqual(cutoff.timeout_count, 1)
        self.assertEqual(cutoff.error_count, 1)
        self.assertAlmostEqual(cutoff.solver_reference_coverage, 1 / 3)
        self.assertIn("有证明参考 1/3 · 缺失 2", chart)
        for record_type, record in (
            (ReferenceStatusRecord, result.reference_statuses[0]),
            (ReferenceCoverageRecord, coverage["optimal"]),
            (ReferenceCensoringBiasRecord, set_count_bias),
            (ReferenceCutoffSensitivityRecord, cutoff),
        ):
            row = {name: str(value) for name, value in record.to_csv_row().items()}
            self.assertEqual(
                record_type.from_csv_row(row).to_csv_row(),
                record.to_csv_row(),
            )

    def test_certificate_is_an_explicit_reference_status_without_exact_solver(self) -> None:
        config = {
            "schema_version": 3,
            "name": "certificate reference",
            "base_seed": 9,
            "repetitions": 1,
            "algorithms": [{"name": "greedy"}],
            "cases": [
                {
                    "name": "certified",
                    "family": "adversarial",
                    "block_size": 4,
                    "trap_count": 3,
                    "distractor_count": 4,
                    "construction_version": 2,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_benchmark(
                _write_config(root, config),
                root / "output",
            )

        status = result.reference_statuses[0]
        self.assertEqual(status.reference_status, "known_optimum_certificate")
        self.assertEqual(json.loads(status.exact_solver_statuses), {})
        self.assertEqual(
            status.reference_source_ids,
            ("known_optimum_certificate",),
        )
        self.assertTrue(status.provably_optimal)
        self.assertEqual(status.cross_validation_status, "single_source")

    def test_small_brute_force_and_bnb_agreement_is_recorded(self) -> None:
        config = {
            "schema_version": 3,
            "name": "small cross validation",
            "base_seed": 11,
            "repetitions": 1,
            "algorithms": [
                {
                    "name": "brute_force",
                    "options": {
                        "time_limit_seconds": 2.0,
                        "max_set_count": 8,
                    },
                },
                {
                    "name": "branch_and_bound",
                    "options": {"time_limit_seconds": 2.0},
                },
            ],
            "cases": [_uniform_case()],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_benchmark(
                _write_config(root, config),
                root / "output",
            )

        status = result.reference_statuses[0]
        self.assertEqual(status.reference_status, "optimal")
        self.assertEqual(status.proof_source_count, 2)
        self.assertEqual(status.cross_validation_status, "agreement")
        self.assertTrue(status.small_instance_cross_validated)

    def test_set_count_cutoff_is_not_silently_dropped(self) -> None:
        config = {
            "schema_version": 3,
            "name": "ineligible brute force",
            "base_seed": 7,
            "repetitions": 1,
            "algorithms": [
                {"name": "greedy"},
                {
                    "name": "brute_force",
                    "options": {"max_set_count": 2},
                },
            ],
            "cases": [_uniform_case()],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_benchmark(
                _write_config(root, config),
                root / "output",
            )

        status = result.reference_statuses[0]
        self.assertEqual(status.reference_status, "not_run")
        self.assertEqual(
            json.loads(status.exact_solver_statuses),
            {"brute_force": "not_run"},
        )
        cutoff = result.reference_cutoff_sensitivity_statistics[0]
        self.assertEqual(cutoff.generated_instance_count, 1)
        self.assertEqual(cutoff.eligible_instance_count, 0)
        self.assertEqual(cutoff.not_run_count, 1)
        self.assertEqual(cutoff.solver_reference_coverage, 0.0)
        self.assertEqual(cutoff.effective_reference_coverage, 0.0)


if __name__ == "__main__":
    unittest.main()
