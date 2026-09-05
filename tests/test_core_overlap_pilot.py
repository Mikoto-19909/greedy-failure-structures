"""Check the preregistered overlap analysis with synthetic records only."""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import io
import json
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover import InstanceRecord, RunRecord
from maxcover.config import load_config
from maxcover.model import SolutionStatus
from maxcover.reproducibility import config_hash

SPEC = importlib.util.spec_from_file_location(
    "core_overlap_pilot", ROOT / "analysis" / "core_overlap_pilot.py"
)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)

CONFIG = ROOT / "configs" / "core_overlap_pilot.json"
CONFIG_HASH = "593d362a8a5bdcd8dc0366e9d1cb05238c6a07b8cc0c75419691511c53e8e17d"
METRICS = (
    "pairwise_overlap_mean_jaccard",
    "actual_density",
    "mean_set_size",
    "covered_element_count",
    "coverage_skew_gini",
)


def _synthetic_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build canonical records without generating or solving any instance."""
    seed_payload = b'{"base_seed":7401,"seed_group":"core_overlap_pilot"}'
    first_seed = int.from_bytes(hashlib.sha256(seed_payload).digest()[:8], "big")
    instances: list[dict[str, str]] = []
    runs: list[dict[str, str]] = []
    for case, family, parameters, jaccard, gini in (
        (
            "overlap", "high_overlap",
            {"core_fraction": 0.5, "core_probability": 0.8,
             "peripheral_probability": 0.05}, 0.6, 0.2,
        ),
        ("overlap_control", "uniform", {"density": 0.425}, 0.3, 0.1),
    ):
        for repetition in range(30):
            identifier = hashlib.sha256(f"synthetic:{case}:{repetition}".encode()).hexdigest()
            record = InstanceRecord(
                config_hash=CONFIG_HASH, case_id=case, repetition=repetition,
                instance_id=identifier, seed=first_seed + repetition,
                family=family, generator_version=1, instance_origin="stochastic",
                is_adversarial=False, universe_size=48, set_count=16, k=4,
                parameters=json.dumps(parameters), incidence_count=320,
                covered_element_count=48, unique_set_count=16,
                actual_density=320 / 768, mean_set_size=20.0,
                pairwise_overlap_mean_jaccard=jaccard,
                pairwise_overlap_total_pairs=120, pairwise_overlap_valid_pairs=120,
                coverage_skew_gini=gini, duplicate_set_count=0,
                duplicate_set_ratio=0.0, dominated_set_count=0,
                dominated_set_ratio=0.0, dominated_unique_ratio=0.0,
                preprocessed_set_count=16,
            )
            instances.append({key: str(value) for key, value in record.to_csv_row().items()})
            for algorithm_id, algorithm, status, options in (
                ("greedy", "greedy", SolutionStatus.FEASIBLE, {}),
                ("exact_reference", "brute_force", SolutionStatus.OPTIMAL,
                 {"max_set_count": 16, "time_limit_seconds": None}),
            ):
                run = RunRecord(
                    config_hash=CONFIG_HASH, case_id=case, instance_id=identifier,
                    run_id=hashlib.sha256(f"{identifier}:{algorithm_id}".encode()).hexdigest(),
                    case=case, repetition=repetition, seed=record.seed, family=family,
                    universe_size=48, set_count=16, k=4, parameters=record.parameters,
                    algorithm_id=algorithm_id, algorithm=algorithm,
                    algorithm_options=json.dumps(options), status=status,
                    coverage=40, best_bound=40 if status is SolutionStatus.OPTIMAL else None,
                    optimum=40, optimality_gap=0.0, runtime_seconds=0.01,
                    nodes_or_iterations=0, selected=(0, 1, 2, 3),
                )
                runs.append({key: str(value) for key, value in run.to_csv_row().items()})
    return instances, runs


def _write_inputs(
    directory: Path, instances: list[dict[str, str]], runs: list[dict[str, str]]
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, str | int]] = {}
    for name, fields, records in (
        ("instances.csv", InstanceRecord.CSV_FIELDS, instances),
        ("raw_results.csv", RunRecord.CSV_FIELDS, runs),
    ):
        path = directory / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        data = path.read_bytes()
        outputs[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (directory / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "configuration": {"config_hash": CONFIG_HASH},
            "git": {"commit": "a" * 40, "dirty": False},
            "outputs": outputs,
        }), encoding="utf-8",
    )


def _pairs(counts: tuple[int, int, int, int]) -> list[dict[str, int | float]]:
    rows: list[dict[str, int | float]] = []
    for (treatment, control), count in zip(((0, 0), (1, 0), (0, 1), (1, 1)), counts):
        for _ in range(count):
            row: dict[str, int | float] = {
                "repetition": len(rows), "treatment_failure": treatment,
                "control_failure": control, "treatment_gap": treatment / 4,
                "control_gap": control / 20,
            }
            for metric, left, right in zip(METRICS, (0.6, 0.4, 20, 48, 0.2),
                                           (0.3, 0.4, 20, 48, 0.1)):
                row[f"treatment_{metric}"] = left
                row[f"control_{metric}"] = right
            rows.append(row)
    return rows


class PilotInputTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "results"
        self.instances, self.runs = _synthetic_inputs()

    def write(self) -> None:
        _write_inputs(self.directory, self.instances, self.runs)

    def manifest(self) -> dict:
        return json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        (self.directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def assert_rejected(self) -> None:
        self.write()
        with self.assertRaises(ValueError):
            pilot.load_inputs(CONFIG, self.directory)

    def test_configuration_is_the_frozen_design(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config_hash(config), CONFIG_HASH)
        reference = next(item for item in config.algorithms if item.algorithm_id == "exact_reference")
        self.assertEqual(reference.options.max_set_count, 16)
        self.assertIsNone(reference.options.time_limit_seconds)

    def test_complete_synthetic_input_is_accepted(self) -> None:
        self.write()
        data = pilot.load_inputs(CONFIG, self.directory)
        self.assertEqual(data.config_hash, CONFIG_HASH)
        self.assertEqual(len(data.rows), 30)
        self.assertEqual([row["repetition"] for row in data.rows], list(range(30)))
        self.assertTrue(all(row["treatment_failure"] == 0 for row in data.rows))
        for role in ("treatment", "control"):
            self.assertTrue(all(f"{role}_{metric}" in data.rows[0] for metric in METRICS))

    def test_pairing_does_not_depend_on_either_csv_order(self) -> None:
        self.write()
        expected = pilot.load_inputs(CONFIG, self.directory).rows
        self.instances = self.instances[::2] + self.instances[1::2]
        self.runs.reverse()
        self.write()
        self.assertEqual(pilot.load_inputs(CONFIG, self.directory).rows, expected)

    def test_manifest_version_requires_integer_one(self) -> None:
        for version in (None, True, 1.0, "1", 0, 2):
            with self.subTest(version=version):
                self.write()
                manifest = self.manifest()
                manifest["schema_version"] = version
                self.write_manifest(manifest)
                with self.assertRaises(ValueError):
                    pilot.load_inputs(CONFIG, self.directory)

    def test_both_input_hash_declarations_are_required(self) -> None:
        for name in ("instances.csv", "raw_results.csv"):
            for missing in ("output", "sha256"):
                with self.subTest(name=name, missing=missing):
                    self.write()
                    manifest = self.manifest()
                    if missing == "output":
                        del manifest["outputs"][name]
                    else:
                        del manifest["outputs"][name]["sha256"]
                    self.write_manifest(manifest)
                    with self.assertRaises(ValueError):
                        pilot.load_inputs(CONFIG, self.directory)

    def test_actual_csv_bytes_must_match_declared_hash(self) -> None:
        for name in ("instances.csv", "raw_results.csv"):
            with self.subTest(name=name):
                self.write()
                path = self.directory / name
                path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(ValueError, "(?i)sha|hash|checksum"):
                    pilot.load_inputs(CONFIG, self.directory)

    def test_configuration_hash_must_match_every_source(self) -> None:
        for source in ("manifest", "instance", "run"):
            with self.subTest(source=source):
                self.instances, self.runs = _synthetic_inputs()
                if source == "instance":
                    self.instances[0]["config_hash"] = "b" * 64
                elif source == "run":
                    self.runs[0]["config_hash"] = "b" * 64
                self.write()
                if source == "manifest":
                    manifest = self.manifest()
                    manifest["configuration"]["config_hash"] = "b" * 64
                    self.write_manifest(manifest)
                with self.assertRaises(ValueError):
                    pilot.load_inputs(CONFIG, self.directory)

    def test_a_different_design_is_rejected_even_with_matching_hashes(self) -> None:
        for field, value in (("base_seed", 7402), ("repetitions", 29)):
            with self.subTest(field=field):
                config_data = json.loads(CONFIG.read_text(encoding="utf-8"))
                config_data[field] = value
                config_path = self.directory.parent / "changed.json"
                config_path.write_text(json.dumps(config_data), encoding="utf-8")
                changed_hash = config_hash(load_config(config_path))
                self.instances, self.runs = _synthetic_inputs()
                for row in self.instances + self.runs:
                    row["config_hash"] = changed_hash
                self.write()
                manifest = self.manifest()
                manifest["configuration"]["config_hash"] = changed_hash
                self.write_manifest(manifest)
                with self.assertRaises(ValueError):
                    pilot.load_inputs(config_path, self.directory)

    def test_missing_instance_and_unexpected_case_are_rejected(self) -> None:
        for mutation in ("missing", "unexpected_case"):
            with self.subTest(mutation=mutation):
                self.instances, self.runs = _synthetic_inputs()
                if mutation == "missing":
                    self.instances.pop()
                else:
                    self.instances[0]["case_id"] = "extra_case"
                self.assert_rejected()

    def test_duplicate_instance_keys_are_rejected_at_unchanged_row_count(self) -> None:
        for distinct_id in (False, True):
            with self.subTest(distinct_id=distinct_id):
                self.instances, self.runs = _synthetic_inputs()
                original_id = self.instances[1]["instance_id"]
                self.instances[1] = self.instances[0].copy()
                if distinct_id:
                    self.instances[1]["instance_id"] = original_id
                self.assert_rejected()

    def test_instance_id_cannot_identify_two_units(self) -> None:
        self.instances[1]["instance_id"] = self.instances[0]["instance_id"]
        self.assert_rejected()

    def test_repetition_range_is_complete(self) -> None:
        for repetition in ("30", "-1"):
            with self.subTest(repetition=repetition):
                self.instances, self.runs = _synthetic_inputs()
                self.instances[29]["repetition"] = repetition
                self.assert_rejected()

    def test_every_instance_requires_exactly_two_distinct_algorithm_runs(self) -> None:
        for mutation in ("missing_greedy", "missing_reference", "duplicate", "replacement"):
            with self.subTest(mutation=mutation):
                self.instances, self.runs = _synthetic_inputs()
                if mutation == "missing_greedy":
                    del self.runs[0]
                elif mutation == "missing_reference":
                    del self.runs[1]
                elif mutation == "duplicate":
                    self.runs.append(self.runs[0].copy())
                else:
                    self.runs[1] = self.runs[0].copy()
                self.assert_rejected()

    def test_algorithm_identity_options_and_absence_of_seed_are_enforced(self) -> None:
        for index, field, value in (
            (0, "algorithm_id", "extra"), (0, "algorithm", "lazy_greedy"),
            (1, "algorithm", "branch_and_bound"), (0, "algorithm_seed", "7"),
            (1, "algorithm_seed", "7"),
            (1, "algorithm_options", '{"max_set_count":17,"time_limit_seconds":null}'),
        ):
            with self.subTest(index=index, field=field):
                self.instances, self.runs = _synthetic_inputs()
                self.runs[index][field] = value
                self.assert_rejected()

    def test_orphan_run_is_rejected(self) -> None:
        self.runs[0]["instance_id"] = "f" * 64
        self.assert_rejected()

    def test_linked_run_metadata_must_agree_with_its_instance(self) -> None:
        for field, value in (
            ("case_id", "overlap_control"), ("repetition", "1"), ("family", "uniform"),
            ("seed", "7"), ("universe_size", "49"), ("set_count", "17"),
            ("k", "5"), ("parameters", '{"core_fraction":0.7}'),
        ):
            with self.subTest(field=field):
                self.instances, self.runs = _synthetic_inputs()
                self.runs[0][field] = value
                self.assert_rejected()

    def test_pairing_rejects_unequal_effective_seeds(self) -> None:
        self.instances[30]["seed"] = "7"
        self.runs[60]["seed"] = self.runs[61]["seed"] = "7"
        self.assert_rejected()

    def test_shared_but_unplanned_seed_is_rejected(self) -> None:
        for index in (0, 30):
            self.instances[index]["seed"] = "7401"
        for index in (0, 1, 60, 61):
            self.runs[index]["seed"] = "7401"
        self.assert_rejected()

    def test_missing_seed_and_unconfigured_coupling_are_rejected(self) -> None:
        for mutation in ("missing_seed", "coupling"):
            with self.subTest(mutation=mutation):
                self.instances, self.runs = _synthetic_inputs()
                if mutation == "missing_seed":
                    self.instances[0]["seed"] = ""
                    self.runs[0]["seed"] = self.runs[1]["seed"] = ""
                else:
                    self.instances[0]["coupling_pair_id"] = "unexpected"
                    self.instances[0]["coupling_seed"] = self.instances[0]["seed"]
                self.assert_rejected()

    def test_matching_dimensions_must_still_equal_the_fixed_design(self) -> None:
        for index in (0, 30):
            self.instances[index]["k"] = "5"
        for index in (0, 1, 60, 61):
            self.runs[index]["k"] = "5"
        self.assert_rejected()

    def test_nonoptimal_reference_is_rejected(self) -> None:
        for status in ("feasible", "timeout", "error"):
            with self.subTest(status=status):
                self.instances, self.runs = _synthetic_inputs()
                row = self.runs[1]
                row.update(status=status, is_exact="False", best_bound="",
                           timed_out=str(status == "timeout"))
                if status == "error":
                    row.update(coverage="", selected="", optimality_gap="",
                               error_message="synthetic error")
                self.assert_rejected()

    def test_positive_reference_and_matching_optimum_are_required(self) -> None:
        for mutation in ("zero", "missing_greedy_optimum", "missing_reference_optimum",
                         "different_greedy_optimum", "different_reference_optimum"):
            with self.subTest(mutation=mutation):
                self.instances, self.runs = _synthetic_inputs()
                if mutation == "zero":
                    for row in self.runs[:2]:
                        row.update(coverage="0", optimum="0", optimality_gap="")
                    self.runs[1]["best_bound"] = "0"
                else:
                    index = 0 if "greedy" in mutation else 1
                    self.runs[index]["optimum"] = "" if mutation.startswith("missing") else "41"
                    self.runs[index]["optimality_gap"] = ""
                self.assert_rejected()

    def test_greedy_cannot_exceed_the_reference(self) -> None:
        self.runs[0].update(coverage="41", optimality_gap="")
        self.assert_rejected()

    def test_greedy_must_be_completed_not_just_have_an_incumbent(self) -> None:
        for status, termination in (
            ("timeout", "time_limit"), ("error", "error"),
            ("feasible", "time_limit"), ("feasible", "iteration_limit"),
            ("feasible", "error"),
        ):
            with self.subTest(status=status, termination=termination):
                self.instances, self.runs = _synthetic_inputs()
                row = self.runs[0]
                metadata = json.loads(row["algorithm_metadata"])
                metadata["termination"] = termination
                row.update(status=status, timed_out=str(status == "timeout"),
                           algorithm_metadata=json.dumps(metadata))
                if status == "error":
                    row.update(coverage="", selected="", optimality_gap="",
                               error_message="synthetic error")
                self.assert_rejected()

    def test_typed_csv_record_validation_is_not_bypassed(self) -> None:
        for target, field, value in (
            ("instance", "schema_version", "99"), ("run", "schema_version", "99"),
            ("instance", "actual_density", "nan"), ("run", "coverage", "invalid"),
        ):
            with self.subTest(target=target, field=field):
                self.instances, self.runs = _synthetic_inputs()
                rows = self.instances if target == "instance" else self.runs
                rows[0][field] = value
                self.assert_rejected()

    def test_hashing_and_parsing_use_the_same_input_bytes(self) -> None:
        self.write()
        original_read = Path.read_bytes
        calls: dict[Path, int] = {}

        def change_after_first_read(path: Path) -> bytes:
            if path.parent == self.directory and path.suffix == ".csv":
                calls[path] = calls.get(path, 0) + 1
                if calls[path] > 1:
                    return b"changed after hashing\n"
            return original_read(path)

        with patch.object(Path, "read_bytes", change_after_first_read):
            data = pilot.load_inputs(CONFIG, self.directory)
        self.assertEqual(len(data.rows), 30)
        self.assertEqual(calls, {self.directory / "instances.csv": 1,
                                 self.directory / "raw_results.csv": 1})

    def test_cli_rejects_invalid_inputs_before_creating_outputs(self) -> None:
        self.instances.pop()
        self.write()
        output = self.directory.parent / "analysis"
        with patch.object(pilot, "validate_complete_output", return_value="synthetic PASS"):
            with redirect_stderr(io.StringIO()):
                try:
                    code = pilot.main(["--config", str(CONFIG), "--results",
                                       str(self.directory), "--output", str(output)])
                except ValueError:
                    code = 1
        self.assertNotEqual(code, 0)
        self.assertFalse(output.exists())

    def test_feasible_status_is_not_a_failure_and_gap_is_recomputed(self) -> None:
        self.runs[0].update(coverage="30", optimality_gap="")
        self.write()
        rows = pilot.load_inputs(CONFIG, self.directory).rows
        self.assertEqual(rows[0]["treatment_failure"], 1)
        self.assertEqual(rows[0]["treatment_gap"], 0.25)
        self.assertEqual(rows[1]["treatment_failure"], 0)
        self.assertEqual(rows[1]["treatment_gap"], 0.0)

    def test_validation_commands_preserve_external_paths_with_spaces(self) -> None:
        try:
            import matplotlib
        except ImportError:
            self.skipTest("Matplotlib is an optional offline analysis dependency")
        matplotlib.use("Agg")
        external = self.directory.parent / "external fixture"
        external.mkdir()
        config_path = external / "fixed config.json"
        config_path.write_bytes(CONFIG.read_bytes())
        results = external / "benchmark results"
        output = external / "analysis artifacts"
        _write_inputs(results, self.instances, self.runs)
        data = pilot.load_inputs(config_path, results)
        pilot.write_analysis(data, config_path, results, output, "synthetic validator fixture")

        validation = (output / "validation.md").read_text(encoding="utf-8")
        command_lines = validation.split("```console\n", 1)[1].split("\n```", 1)[0].splitlines()
        commands = [shlex.split(line) for line in command_lines]
        self.assertEqual(len(commands), 3)
        for command in commands:
            emitted_config = Path(command[command.index("--config") + 1])
            self.assertTrue(emitted_config.is_absolute())
            self.assertEqual(emitted_config, config_path)
            self.assertEqual(config_hash(load_config(emitted_config)), CONFIG_HASH)

        self.assertEqual(commands[0][:3], ["python", "run_project.py", "benchmark"])
        self.assertEqual(commands[1][1], ".github/scripts/validate_benchmark_output.py")
        for command in commands[:2]:
            self.assertEqual(Path(command[command.index("--output") + 1]), results)
        analysis_command = commands[2]
        self.assertEqual(analysis_command[1], "analysis/core_overlap_pilot.py")
        self.assertEqual(Path(analysis_command[analysis_command.index("--results") + 1]), results)
        self.assertEqual(Path(analysis_command[analysis_command.index("--output") + 1]), output)


class PilotStatisticsTest(unittest.TestCase):
    def test_four_cells_and_exact_two_sided_tail(self) -> None:
        result = pilot.summarize_pairs(_pairs((10, 8, 2, 10)))
        for key, expected in {"n00": 10, "n10": 8, "n01": 2, "n11": 10, "n": 30,
                              "treatment_failures": 18, "control_failures": 12}.items():
            self.assertEqual(result[key], expected)
        self.assertAlmostEqual(result["treatment_failure_rate"], 0.6)
        self.assertAlmostEqual(result["control_failure_rate"], 0.4)
        self.assertAlmostEqual(result["delta_failure"], 0.2)
        self.assertEqual(result["p_two_sided"], 0.109375)
        self.assertEqual(pilot.conclusion_key(result, pilot.structural_diagnostics(
            _pairs((10, 8, 2, 10)))), "inconclusive")

    def test_positive_and_reversed_direction_use_the_same_two_sided_test(self) -> None:
        for counts, delta, conclusion in (((20, 8, 0, 2), 8 / 30, "positive"),
                                          ((20, 0, 8, 2), -8 / 30, "negative")):
            with self.subTest(counts=counts):
                rows = _pairs(counts)
                result = pilot.summarize_pairs(rows)
                self.assertAlmostEqual(result["delta_failure"], delta)
                self.assertEqual(result["p_two_sided"], 0.0078125)
                self.assertEqual(pilot.conclusion_key(result, pilot.structural_diagnostics(rows)),
                                 conclusion)

    def test_no_discordance_including_all_zero_gaps_returns_p_one(self) -> None:
        for counts in ((15, 0, 0, 15), (30, 0, 0, 0)):
            with self.subTest(counts=counts):
                rows = _pairs(counts)
                result = pilot.summarize_pairs(rows)
                self.assertEqual(result["p_two_sided"], 1.0)
                self.assertEqual(result["delta_failure"], 0.0)
                self.assertEqual(pilot.conclusion_key(result, pilot.structural_diagnostics(rows)),
                                 "inconclusive")
                if counts[0] == 30:
                    self.assertEqual(result["treatment_mean_gap"], 0.0)
                    self.assertEqual(result["control_mean_gap"], 0.0)
                    self.assertEqual(result["delta_gap"], 0.0)

    def test_equal_failure_rates_can_have_different_all_instance_mean_gaps(self) -> None:
        result = pilot.summarize_pairs(_pairs((27, 0, 0, 3)))
        self.assertEqual(result["treatment_failure_rate"], 0.1)
        self.assertEqual(result["control_failure_rate"], 0.1)
        self.assertAlmostEqual(result["treatment_mean_gap"], 0.025)
        self.assertAlmostEqual(result["control_mean_gap"], 0.005)
        self.assertAlmostEqual(result["delta_gap"], 0.02)

    def test_swapping_roles_reverses_both_effects_and_preserves_p(self) -> None:
        rows = _pairs((10, 8, 2, 10))
        swapped = copy.deepcopy(rows)
        for row in swapped:
            for field in ("failure", "gap"):
                left, right = f"treatment_{field}", f"control_{field}"
                row[left], row[right] = row[right], row[left]
        original = pilot.summarize_pairs(rows)
        reverse = pilot.summarize_pairs(swapped)
        self.assertEqual(original["p_two_sided"], reverse["p_two_sided"])
        self.assertAlmostEqual(original["delta_failure"], -reverse["delta_failure"])
        self.assertAlmostEqual(original["delta_gap"], -reverse["delta_gap"])

    def test_structure_statistics_preserve_both_groups_and_paired_difference(self) -> None:
        rows = _pairs((30, 0, 0, 0))
        rows[0]["treatment_pairwise_overlap_mean_jaccard"] = 0.9
        diagnostics = pilot.structural_diagnostics(rows)
        self.assertEqual(set(diagnostics), set(METRICS))
        jaccard = diagnostics["pairwise_overlap_mean_jaccard"]
        self.assertAlmostEqual(jaccard["treatment_mean"], 0.61)
        self.assertEqual(jaccard["treatment_min"], 0.6)
        self.assertEqual(jaccard["treatment_max"], 0.9)
        self.assertAlmostEqual(jaccard["control_mean"], 0.3)
        self.assertEqual(jaccard["control_min"], 0.3)
        self.assertEqual(jaccard["control_max"], 0.3)
        self.assertAlmostEqual(jaccard["paired_mean_difference"], 0.31)

    def test_structure_not_separated_takes_precedence_without_discarding_pairs(self) -> None:
        for treatment_jaccard in (0.3, 0.2):
            with self.subTest(treatment_jaccard=treatment_jaccard):
                rows = _pairs((20, 8, 0, 2))
                for row in rows:
                    row["treatment_pairwise_overlap_mean_jaccard"] = treatment_jaccard
                    row["treatment_actual_density"] = 0.5
                    row["treatment_covered_element_count"] = 44
                summary = pilot.summarize_pairs(rows)
                diagnostics = pilot.structural_diagnostics(rows)
                self.assertEqual(summary["n"], 30)
                self.assertEqual(summary["treatment_failures"], 10)
                self.assertEqual(pilot.conclusion_key(summary, diagnostics), "structure_not_separated")
                self.assertAlmostEqual(diagnostics["actual_density"]["paired_mean_difference"], 0.1)
                self.assertEqual(diagnostics["covered_element_count"]["paired_mean_difference"], -4)

    def test_chart_displays_failure_fractions_on_fixed_zero_to_one_axis(self) -> None:
        try:
            import matplotlib
        except ImportError:
            self.skipTest("Matplotlib is an optional offline analysis dependency")
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        summary = pilot.summarize_pairs(_pairs((10, 8, 2, 10)))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "failure_rate.svg"
            with patch.object(plt, "close"):
                pilot.render_chart(summary, path)
                figure = plt.gcf()
                axes = figure.axes[0]
                self.assertEqual(axes.get_ylim(), (0.0, 1.0))
                self.assertEqual([bar.get_height() for bar in axes.patches], [0.6, 0.4])
                annotations = " ".join(text.get_text() for text in axes.texts)
                self.assertIn("18/30", annotations.replace(" ", ""))
                self.assertIn("12/30", annotations.replace(" ", ""))
                self.assertTrue(path.is_file())
            plt.close(figure)


if __name__ == "__main__":
    unittest.main()
