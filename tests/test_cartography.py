from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import _instances_for_config, plan_benchmark
from maxcover.cartography import (
    CARTOGRAPHY_FILENAMES,
    CARTOGRAPHY_OWNED_FILENAMES,
    HEURISTIC_ALGORITHMS,
    STRESSOR_FAMILIES,
    _InstanceGap,
    _instance_gaps,
    _paired_row,
    load_cartography_design,
    run_cartography,
    write_cartography_artifacts,
)
from maxcover.contracts import RunRecord
from maxcover.model import SolutionStatus
from maxcover.config import ConfigurationError, load_config, parse_config


def _algorithms() -> list[dict[str, object]]:
    return [
        {
            "id": "exact_reference",
            "name": "branch_and_bound_enhanced",
            "options": {"time_limit_seconds": 2.0},
        },
        {"name": "greedy"},
        {"name": "lazy_greedy"},
        {"name": "local_search"},
        {
            "name": "randomized_greedy",
            "algorithm_seeds": [0, 1],
            "options": {"rcl_size": 2},
        },
        {
            "name": "multi_start_local_search",
            "algorithm_seeds": [0, 1],
            "options": {
                "restart_count": 2,
                "max_iterations_per_restart": 20,
                "time_limit_seconds": 1.0,
            },
        },
    ]


def _pair(
    family: str,
    suffix: str,
    treatment: dict[str, object],
    control: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    group = f"{family}_{suffix}"
    treatment_id = group
    control_id = f"{group}_control"
    cases = [
        {"name": treatment_id, "seed_group": group, "family": family, **treatment},
        {
            "name": control_id,
            "seed_group": group,
            "family": "uniform",
            **control,
        },
    ]
    level = {
        "family": family,
        "strength": 0.0 if suffix == "low" else 1.0,
        "strength_label": suffix,
        "stressor_case_id": treatment_id,
        "control_case_id": control_id,
    }
    return cases, level


def _smoke_documents() -> tuple[dict[str, object], dict[str, object]]:
    definitions = [
        (
            "high_overlap",
            {"universe_size": 12, "set_count": 6, "k": 2,
             "core_probability": 0.8, "peripheral_probability": 0.05},
            "core_fraction",
            (0.25, 0.5),
            {"universe_size": 12, "set_count": 6, "k": 2},
            (0.2375, 0.425),
        ),
        (
            "clustered",
            {"universe_size": 12, "set_count": 6, "k": 2,
             "clusters": 2, "outside_probability": 0.05},
            "within_probability",
            (0.3, 0.6),
            {"universe_size": 12, "set_count": 6, "k": 2},
            (0.175, 0.325),
        ),
        (
            "long_tail",
            {"universe_size": 12, "set_count": 6, "k": 2, "set_size": 3},
            "gamma",
            (0.0, 1.0),
            {"universe_size": 12, "set_count": 6, "k": 2},
            (0.25, 0.25),
        ),
        (
            "duplicate_heavy",
            {"universe_size": 12, "base_set_count": 4, "k": 2, "set_size": 3},
            "copy_factor",
            (1, 2),
            {"universe_size": 12, "k": 2, "density": 0.25},
            (4, 8),
        ),
        (
            "dominated_heavy",
            {"anchor_count": 4, "anchor_size": 3, "k": 2},
            "child_count",
            (0, 1),
            {"universe_size": 12, "k": 2, "density": 0.25},
            (4, 8),
        ),
        (
            "adversarial",
            {"block_size": 4, "distractor_count": 0, "construction_version": 2},
            "trap_count",
            (4, 3),
            {"universe_size": 8, "set_count": 3, "k": 2},
            (0.5, 0.5),
        ),
    ]
    cases: list[dict[str, object]] = []
    levels: list[dict[str, object]] = []
    for family, fixed, parameter, values, control_fixed, controls in definitions:
        for index, suffix in enumerate(("low", "high")):
            treatment = {**fixed, parameter: values[index]}
            control = dict(control_fixed)
            if family in {"duplicate_heavy", "dominated_heavy"}:
                control["set_count"] = controls[index]
            else:
                control["density"] = controls[index]
            pair_cases, level = _pair(family, suffix, treatment, control)
            cases.extend(pair_cases)
            levels.append(level)
    config = {
        "schema_version": 3,
        "name": "cartography smoke",
        "base_seed": 19,
        "repetitions": 2,
        "algorithms": _algorithms(),
        "cases": cases,
    }
    design = {
        "schema_version": 1,
        "minimum_instance_seeds": 2,
        "precision_target_half_width": 0.2,
        "levels": levels,
    }
    return config, design


class CartographyTests(unittest.TestCase):
    def test_seed_group_is_a_nonempty_schema_three_case_field(self) -> None:
        base = {
            "name": "seed group validation",
            "repetitions": 1,
            "algorithms": [{"name": "greedy"}],
            "cases": [
                {
                    "name": "uniform",
                    "family": "uniform",
                    "universe_size": 12,
                    "set_count": 6,
                    "k": 2,
                    "density": 0.2,
                    "seed_group": "pair-a",
                }
            ],
        }
        schema_three = {"schema_version": 3, **base}
        self.assertEqual(parse_config(schema_three).cases[0].seed_group, "pair-a")

        invalid = json.loads(json.dumps(schema_three))
        invalid["cases"][0]["seed_group"] = " "
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(invalid)
        self.assertIn("$.cases[0].seed_group", str(caught.exception))

        schema_two = {"schema_version": 2, **base}
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(schema_two)
        self.assertIn("$.cases[0].seed_group", str(caught.exception))

    def test_bundled_design_has_formal_seed_and_algorithm_matrix(self) -> None:
        config = load_config(ROOT / "configs" / "structural_gap_cartography.json")
        design = load_cartography_design(
            ROOT / "designs" / "structural_gap_cartography.json", config
        )
        plan = plan_benchmark(config)

        self.assertEqual(config.repetitions, 30)
        self.assertEqual(len(config.cases), 36)
        self.assertEqual(len(design.levels), 18)
        self.assertEqual({level.family for level in design.levels}, set(STRESSOR_FAMILIES))
        self.assertEqual(plan.instance_count, 1080)
        self.assertEqual(plan.algorithm_run_count, 15120)
        cases = {case.case_id: case for case in config.cases}
        for case_id, expected_set_size in (
            ("dominated_low_control", 6.0),
            ("dominated_medium_control", 4.5),
            ("dominated_high_control", 3.75),
        ):
            density = float(cases[case_id].parameters["density"])
            self.assertAlmostEqual(
                36 * density + (1 - density) ** 36,
                expected_set_size,
                places=10,
            )

    def test_seed_groups_produce_actual_paired_seeds(self) -> None:
        config = load_config(ROOT / "configs" / "structural_gap_cartography.json")
        design = load_cartography_design(
            ROOT / "designs" / "structural_gap_cartography.json", config
        )
        planned = {
            (item.case_id, item.repetition): item
            for item in _instances_for_config(config)
        }
        for level in design.levels:
            for repetition in range(config.repetitions):
                stressor = planned[(level.stressor_case_id, repetition)]
                control = planned[(level.control_case_id, repetition)]
                self.assertEqual(stressor.instance.seed, control.instance.seed)
                if level.family in {
                    "long_tail",
                    "duplicate_heavy",
                    "dominated_heavy",
                    "adversarial",
                }:
                    self.assertEqual(stressor.coupling_seed, stressor.instance.seed)

    def test_design_rejects_declared_pairs_that_are_not_seed_paired(self) -> None:
        config_value, design_value = _smoke_documents()
        config_value["cases"][1]["seed_group"] = "different"
        config = parse_config(config_value)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "design.json"
            path.write_text(json.dumps(design_value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "need one seed_group"):
                load_cartography_design(path, config)

    def test_pair_estimator_rejects_mismatched_observed_seeds(self) -> None:
        from maxcover.cartography import CartographyLevel

        with self.assertRaisesRegex(ValueError, "do not share a seed"):
            _paired_row(
                level=CartographyLevel("high_overlap", 1.0, "high", "s", "c"),
                algorithm_id="greedy",
                algorithm="greedy",
                expected_seed_count=1,
                treatment={0: _InstanceGap(10, 0.2, 1, 1)},
                control={0: _InstanceGap(11, 0.1, 1, 1)},
            )

    def test_force_clears_only_cartography_owned_artifacts_before_benchmark(self) -> None:
        config_value, design_value = _smoke_documents()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            design_path = root / "design.json"
            output = root / "output"
            output.mkdir()
            config_path.write_text(json.dumps(config_value), encoding="utf-8")
            design_path.write_text(json.dumps(design_value), encoding="utf-8")
            for filename in CARTOGRAPHY_OWNED_FILENAMES:
                (output / filename).write_text("stale", encoding="utf-8")
            keep = output / "keep.txt"
            keep.write_text("unrelated", encoding="utf-8")

            with patch(
                "maxcover.cartography.run_benchmark",
                side_effect=RuntimeError("interrupted before benchmark output"),
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    run_cartography(
                        config_path,
                        design_path,
                        output,
                        force=True,
                    )

            self.assertTrue(keep.is_file())
            self.assertTrue(
                all(
                    not (output / filename).exists()
                    for filename in CARTOGRAPHY_OWNED_FILENAMES
                )
            )

    def test_smoke_workflow_writes_distributions_charts_and_paired_table(self) -> None:
        config_value, design_value = _smoke_documents()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            design_path = root / "design.json"
            output = root / "output"
            config_path.write_text(json.dumps(config_value), encoding="utf-8")
            design_path.write_text(json.dumps(design_value), encoding="utf-8")

            result = run_cartography(config_path, design_path, output)
            validator = ROOT / ".github" / "scripts" / "validate_cartography_output.py"
            validation_command = [
                sys.executable,
                str(validator),
                "--config",
                str(config_path),
                "--design",
                str(design_path),
                "--output",
                str(output),
            ]
            validated = subprocess.run(
                validation_command,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            changed_config = dict(config_value, base_seed=config_value["base_seed"] + 999)
            config_path.write_text(json.dumps(changed_config), encoding="utf-8")
            mismatched = subprocess.run(validation_command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn("config_hash", mismatched.stderr)
            config_path.write_text(json.dumps(config_value), encoding="utf-8")
            randomized = [
                row
                for row in result.rows
                if row.case_id == "high_overlap_low"
                and row.algorithm_id == "randomized_greedy"
                and row.repetition == 0
            ]
            self.assertEqual(len(randomized), 2)
            duplicated_seed_rows = [
                randomized[0],
                replace(randomized[1], algorithm_seed=randomized[0].algorithm_seed),
            ]
            with self.assertRaisesRegex(ValueError, "configured seed set"):
                _instance_gaps(
                    duplicated_seed_rows,
                    case_id="high_overlap_low",
                    algorithm_id="randomized_greedy",
                    expected_algorithm_seeds=(0, 1),
                )
            with (output / "structural_gap_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                statistics = list(csv.DictReader(handle))
            with (output / "paired_control_differences.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                paired = list(csv.DictReader(handle))
            strength_svg = (output / "stressor_strength_gap.svg").read_text(
                encoding="utf-8"
            )
            matrix_svg = (output / "family_algorithm_gap.svg").read_text(
                encoding="utf-8"
            )
            paired_path = output / "paired_control_differences.csv"
            with paired_path.open(encoding="utf-8", newline="") as handle:
                tampered_rows = list(csv.DictReader(handle))
                tampered_fields = tuple(tampered_rows[0])
            tampered_rows[0]["mean_paired_gap_difference"] = "0.987654321"
            with paired_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=tampered_fields, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(tampered_rows)
            rejected = subprocess.run(
                validation_command,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("mean_paired_gap_difference", rejected.stderr)

        self.assertEqual(len(result.rows), 384)
        self.assertEqual(len(statistics), 12 * len(HEURISTIC_ALGORITHMS) * 2)
        self.assertEqual(len(paired), 12 * len(HEURISTIC_ALGORITHMS))
        self.assertTrue(all(row["paired_seed_count"] == "2" for row in paired))
        self.assertTrue(all(row["difference_formula"] == "stressor_gap-control_gap" for row in paired))
        self.assertIn("<svg", strength_svg)
        self.assertIn("<svg", matrix_svg)


class CartographyPlanValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        config, design = _smoke_documents()
        cls.config_path = cls.root / "config.json"
        cls.design_path = cls.root / "design.json"
        cls.config_path.write_text(json.dumps(config), encoding="utf-8")
        cls.design_path.write_text(json.dumps(design), encoding="utf-8")
        cls.baseline = cls.root / "baseline"
        cls.result = run_cartography(cls.config_path, cls.design_path, cls.baseline)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "output"
        shutil.copytree(self.baseline, self.output)

    def write_runs(self, rows) -> None:
        with (self.output / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RunRecord.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(row.to_csv_row() for row in rows)

    def validate(self):
        return subprocess.run([
            sys.executable, str(ROOT / ".github/scripts/validate_cartography_output.py"),
            "--config", str(self.config_path), "--design", str(self.design_path),
            "--output", str(self.output),
        ], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_real_outputs_validate_without_a_manifest(self) -> None:
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_resume_removes_legacy_cartography_manifest_without_rerunning(self) -> None:
        manifest = self.output / "cartography_manifest.json"
        manifest.write_text("legacy", encoding="utf-8")
        note = self.output / "research-notes.md"
        note.write_text("keep", encoding="utf-8")
        raw_before = (self.output / "raw_results.csv").read_bytes()
        with patch("maxcover.benchmark._execute_task", side_effect=AssertionError("unexpected rerun")):
            run_cartography(self.config_path, self.design_path, self.output)
        self.assertFalse(manifest.exists())
        self.assertEqual(note.read_text(encoding="utf-8"), "keep")
        self.assertEqual((self.output / "raw_results.csv").read_bytes(), raw_before)

    def test_invalid_design_leaves_legacy_cartography_manifest_untouched(self) -> None:
        manifest = self.output / "cartography_manifest.json"
        manifest.write_text("legacy", encoding="utf-8")
        raw_before = (self.output / "raw_results.csv").read_bytes()
        invalid = self.output.parent / "invalid-design.json"
        design = json.loads(self.design_path.read_text(encoding="utf-8"))
        design["minimum_instance_seeds"] = 0
        invalid.write_text(json.dumps(design), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_cartography(self.config_path, invalid, self.output)
        self.assertEqual(manifest.read_text(encoding="utf-8"), "legacy")
        self.assertEqual((self.output / "raw_results.csv").read_bytes(), raw_before)

    def test_wrong_run_algorithm_options_and_coordinated_seeds_are_rejected(self) -> None:
        original = list(self.result.rows)
        mutations = [
            (field, [replace(original[0], **{field: value}), *original[1:]])
            for field, value in (("run_id", "f" * 64), ("algorithm", "unknown"),
                                 ("algorithm_id", "unknown"), ("algorithm_options", '{"unknown":true}'),
                                 ("instance_id", "e" * 64))
        ]
        mutations.append(("coordinated seeds", [replace(row, seed=row.seed + 999) for row in original]))
        mutations.append(("duplicate IDs", [replace(row, run_id=original[0].run_id) for row in original]))
        for name, rows in mutations:
            with self.subTest(mutation=name):
                self.write_runs(rows)
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, "execution plan|duplicate run_id")

    def test_absent_repetition_is_rejected_even_after_recomputing_tables(self) -> None:
        rows = tuple(row for row in self.result.rows if row.repetition == 0)
        self.write_runs(rows)
        write_cartography_artifacts(self.output, self.config_path, self.design_path,
                                    replace(self.result, rows=rows, output_dir=self.output))
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("execution plan", result.stderr)

    def test_coordinated_objective_edits_fail_even_after_rebuilding_tables(self) -> None:
        for field in ("coverage", "optimum"):
            with self.subTest(field=field):
                rows = list(self.result.rows)
                index = next(i for i, row in enumerate(rows) if row.algorithm == "greedy" and row.coverage > 0)
                row = rows[index]
                coverage = row.coverage - 1 if field == "coverage" else row.coverage
                optimum = row.optimum + 1 if field == "optimum" else row.optimum
                rows[index] = replace(row, coverage=coverage, optimum=optimum,
                                      optimality_gap=(optimum-coverage)/optimum)
                self.write_runs(rows)
                write_cartography_artifacts(self.output, self.config_path, self.design_path,
                                            replace(self.result, rows=tuple(rows), output_dir=self.output))
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, "coverage does not match|validated reference")

    def test_instance_table_is_checked_against_generated_instances(self) -> None:
        path = self.output / "instances.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        rows[0]["pairwise_overlap_mean_jaccard"] = "0.999"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("instance plan", result.stderr)

    def test_present_error_run_remains_a_missing_metric(self) -> None:
        rows = list(self.result.rows)
        index = next(i for i, row in enumerate(rows) if row.algorithm == "greedy")
        metadata = json.loads(rows[index].algorithm_metadata)
        metadata["termination"] = "error"
        rows[index] = replace(rows[index], status=SolutionStatus.ERROR, coverage=None,
                              best_bound=None, optimality_gap=None, selected=(),
                              algorithm_metadata=json.dumps(metadata), error_message="test failure")
        self.write_runs(rows)
        write_cartography_artifacts(self.output, self.config_path, self.design_path,
                                    replace(self.result, rows=tuple(rows), output_dir=self.output))
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
