from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import run_benchmark
from maxcover.config import (
    CONFIG_SCHEMA_VERSION,
    AlgorithmConfig,
    CaseConfig,
    ConfigurationError,
    ExperimentConfig,
    LegacyConfigWarning,
    load_config,
    parse_config,
)


def _valid_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "validation test",
        "base_seed": 10,
        "repetitions": 1,
        "exact_time_limit_seconds": 1.0,
        "brute_force_set_cutoff": 12,
        "algorithms": ["brute_force", "branch_and_bound", "greedy"],
        "cases": [
            {
                "name": "tiny",
                "family": "uniform",
                "universe_size": 20,
                "set_count": 8,
                "k": 3,
                "density": 0.2,
            }
        ],
    }


def _v2_config() -> dict[str, object]:
    value = _valid_config()
    value["schema_version"] = 2
    value.pop("exact_time_limit_seconds")
    value.pop("brute_force_set_cutoff")
    value["algorithms"] = [
        {
            "name": "brute_force",
            "options": {"time_limit_seconds": 1.0, "max_set_count": 12},
        },
        {
            "name": "branch_and_bound",
            "options": {"time_limit_seconds": 1.0},
        },
        {"name": "greedy", "options": {}},
    ]
    return value


class ConfigurationTests(unittest.TestCase):
    def test_bundled_schema_v1_configs_are_migrated_with_one_warning(self) -> None:
        self.assertEqual(CONFIG_SCHEMA_VERSION, 3)
        for filename, case_count in (("quick.json", 4), ("full.json", 8)):
            with self.subTest(filename=filename):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    config = load_config(ROOT / "configs" / filename)
                self.assertIsInstance(config, ExperimentConfig)
                self.assertEqual(config.schema_version, 3)
                self.assertEqual(len(config.cases), case_count)
                self.assertEqual(len(caught), 1)
                self.assertIs(caught[0].category, LegacyConfigWarning)
                self.assertTrue(
                    all(isinstance(item, AlgorithmConfig) for item in config.algorithms)
                )
                self.assertTrue(
                    all(isinstance(item, CaseConfig) for item in config.cases)
                )

    def test_missing_schema_version_uses_defaults_without_mutating_input(self) -> None:
        value = _valid_config()
        for field in (
            "schema_version",
            "base_seed",
            "exact_time_limit_seconds",
            "brute_force_set_cutoff",
        ):
            value.pop(field)
        original = copy.deepcopy(value)

        with self.assertWarns(LegacyConfigWarning):
            config = parse_config(value)

        self.assertEqual(value, original)
        self.assertEqual(config.schema_version, 3)
        self.assertEqual(config.base_seed, 2026)
        options = {algorithm.name: algorithm.options for algorithm in config.algorithms}
        self.assertEqual(options["brute_force"].time_limit_seconds, 5.0)
        self.assertEqual(options["brute_force"].max_set_count, 18)
        self.assertEqual(options["branch_and_bound"].time_limit_seconds, 5.0)
        self.assertIsNone(options["branch_and_bound"].max_set_count)
        self.assertEqual(options["greedy"].time_limit_seconds, None)
        with self.assertRaises(TypeError):
            config.cases[0].parameters["density"] = 0.5

    def test_v1_controls_are_converted_to_per_algorithm_options(self) -> None:
        with self.assertWarnsRegex(LegacyConfigWarning, "migrated to schema 3"):
            config = parse_config(_valid_config())
        options = {algorithm.name: algorithm.options for algorithm in config.algorithms}
        self.assertEqual(options["brute_force"].time_limit_seconds, 1.0)
        self.assertEqual(options["brute_force"].max_set_count, 12)
        self.assertEqual(options["branch_and_bound"].time_limit_seconds, 1.0)
        self.assertIsNone(options["branch_and_bound"].max_set_count)
        self.assertIsNone(options["greedy"].time_limit_seconds)
        self.assertIsNone(options["greedy"].max_set_count)

    def test_v2_loads_without_warning_and_rejects_legacy_top_level_controls(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = parse_config(_v2_config())
        self.assertEqual(caught, [])
        self.assertEqual(config.schema_version, 3)

        value = _v2_config()
        value["exact_time_limit_seconds"] = 1.0
        with self.assertRaises(ConfigurationError) as error:
            parse_config(value)
        self.assertEqual(error.exception.issues[0][0], "$.exact_time_limit_seconds")

    def test_v2_supports_independent_exact_options(self) -> None:
        value = _v2_config()
        value["algorithms"][0]["options"]["time_limit_seconds"] = 0.25
        value["algorithms"][1]["options"]["time_limit_seconds"] = 0.75
        config = parse_config(value)
        algorithms = {item.name: item for item in config.algorithms}
        self.assertEqual(
            algorithms["brute_force"].options.time_limit_seconds, 0.25
        )
        self.assertEqual(
            algorithms["branch_and_bound"].options.time_limit_seconds, 0.75
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "config.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = run_benchmark(path, root / "output")
        recorded = {
            row.algorithm: json.loads(row.algorithm_options) for row in result.rows
        }
        self.assertEqual(recorded["brute_force"]["time_limit_seconds"], 0.25)
        self.assertEqual(
            recorded["branch_and_bound"]["time_limit_seconds"], 0.75
        )

    def test_enabled_flag_and_eligibility_condition_control_execution(self) -> None:
        value = _v2_config()
        value["algorithms"][0]["options"]["max_set_count"] = 1
        value["algorithms"][1]["enabled"] = False
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "config.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = run_benchmark(path, root / "output")
        self.assertEqual([row.algorithm for row in result.rows], ["greedy"])

    def test_all_algorithms_cannot_be_disabled(self) -> None:
        value = _v2_config()
        for algorithm in value["algorithms"]:
            algorithm["enabled"] = False
        with self.assertRaisesRegex(ConfigurationError, "at least one algorithm"):
            parse_config(value)

    def test_algorithm_specific_unsupported_options_are_rejected(self) -> None:
        invalid = (
            ("greedy", "time_limit_seconds"),
            ("branch_and_bound", "max_set_count"),
        )
        for name, option in invalid:
            with self.subTest(algorithm=name, option=option):
                value = _v2_config()
                algorithm = next(
                    item for item in value["algorithms"] if item["name"] == name
                )
                algorithm["options"][option] = 1
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(value)
                self.assertTrue(
                    any(
                        path.endswith(f".options.{option}")
                        and "not supported" in message
                        for path, message in caught.exception.issues
                    )
                )

    def test_v1_and_v2_produce_equivalent_normalized_config_and_results(self) -> None:
        legacy = _valid_config()
        current = _v2_config()
        with self.assertWarns(LegacyConfigWarning):
            legacy_config = parse_config(legacy)
        current_config = parse_config(current)
        self.assertEqual(legacy_config, current_config)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = root / "legacy.json"
            current_path = root / "current.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")
            with self.assertWarns(LegacyConfigWarning):
                legacy_result = run_benchmark(legacy_path, root / "legacy")
            current_result = run_benchmark(current_path, root / "current")

        def stable_rows(result):
            rows = []
            for row in result.rows:
                values = row.to_csv_row()
                values.pop("runtime_seconds")
                rows.append(values)
            return rows

        self.assertEqual(stable_rows(legacy_result), stable_rows(current_result))

    def test_root_errors_are_aggregated_with_stable_paths(self) -> None:
        value = {
            "unexpected": True,
            "name": " ",
            "base_seed": False,
            "repetitions": 0,
            "exact_time_limit_seconds": math.inf,
            "brute_force_set_cutoff": True,
            "algorithms": [],
            "cases": [],
        }
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(value)

        paths = [path for path, _ in caught.exception.issues]
        self.assertEqual(paths[0], "$.unexpected")
        for path in (
            "$.name",
            "$.base_seed",
            "$.repetitions",
            "$.exact_time_limit_seconds",
            "$.brute_force_set_cutoff",
            "$.algorithms",
            "$.cases",
        ):
            self.assertIn(path, paths)

    def test_required_fields_and_json_shape_report_paths(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            parse_config({})
        self.assertEqual(
            [path for path, _ in caught.exception.issues],
            ["$.name", "$.repetitions", "$.algorithms", "$.cases"],
        )

        with self.assertRaises(ConfigurationError) as caught:
            parse_config([])
        self.assertEqual(caught.exception.issues[0][0], "$")

    def test_algorithm_names_must_be_registered_and_unique(self) -> None:
        value = _valid_config()
        value["algorithms"] = ["greedy", "missing", "greedy", False]
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(value)
        self.assertEqual(
            [path for path, _ in caught.exception.issues],
            ["$.algorithms[1]", "$.algorithms[2]", "$.algorithms[3]"],
        )

    def test_case_names_must_be_present_and_unique(self) -> None:
        value = _valid_config()
        second = copy.deepcopy(value["cases"][0])
        value["cases"] = [value["cases"][0], second, {"family": "uniform"}]
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(value)
        paths = [path for path, _ in caught.exception.issues]
        self.assertIn("$.cases[1].name", paths)
        self.assertIn("$.cases[2].name", paths)
        self.assertIn("$.cases[2].universe_size", paths)

    def test_generator_shape_errors_report_parameter_paths(self) -> None:
        cases = [
            ({"name": "bad", "family": "unknown"}, "$.cases[0].family"),
            (
                {
                    "name": "bad",
                    "family": "uniform",
                    "universe_size": 10,
                    "set_count": 5,
                    "k": 2,
                    "extra": 1,
                },
                "$.cases[0].extra",
            ),
            (
                {
                    "name": "bad",
                    "family": "uniform",
                    "universe_size": "10",
                    "set_count": 5,
                    "k": 2,
                    "density": 0.2,
                },
                "$.cases[0].universe_size",
            ),
        ]
        for raw_case, expected_path in cases:
            with self.subTest(path=expected_path):
                value = _valid_config()
                value["cases"] = [raw_case]
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(value)
                self.assertIn(
                    expected_path, [path for path, _ in caught.exception.issues]
                )

    def test_every_generator_family_is_semantically_preflighted(self) -> None:
        invalid_cases = [
            (
                {
                    "name": "uniform",
                    "family": "uniform",
                    "universe_size": 10,
                    "set_count": 5,
                    "k": 6,
                    "density": 0.2,
                },
                "$.cases[0].k",
            ),
            (
                {
                    "name": "overlap",
                    "family": "high_overlap",
                    "universe_size": 10,
                    "set_count": 5,
                    "k": 2,
                    "core_fraction": 0,
                    "core_probability": 0.5,
                    "peripheral_probability": 0.1,
                },
                "$.cases[0].core_fraction",
            ),
            (
                {
                    "name": "clustered",
                    "family": "clustered",
                    "universe_size": 10,
                    "set_count": 5,
                    "k": 2,
                    "clusters": 1,
                    "within_probability": 0.5,
                    "outside_probability": 0.1,
                },
                "$.cases[0].clusters",
            ),
            (
                {
                    "name": "adversarial",
                    "family": "adversarial",
                    "block_size": 3,
                },
                "$.cases[0].block_size",
            ),
        ]
        for raw_case, expected_path in invalid_cases:
            with self.subTest(path=expected_path):
                value = _valid_config()
                value["cases"] = [raw_case]
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(value)
                self.assertEqual(caught.exception.issues[0][0], expected_path)

    def test_unsupported_schema_and_non_finite_json_number_are_rejected(self) -> None:
        for field, value, expected_path in (
            ("schema_version", 4, "$.schema_version"),
            ("exact_time_limit_seconds", float("nan"), "$.exact_time_limit_seconds"),
        ):
            with self.subTest(field=field):
                config = _valid_config()
                config[field] = value
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(config)
                self.assertEqual(caught.exception.issues[0][0], expected_path)

    def test_invalid_json_reports_root_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text('{"name":', encoding="utf-8")
            with self.assertRaises(ConfigurationError) as caught:
                load_config(path)
        self.assertEqual(caught.exception.issues[0][0], "$")
        self.assertIn("line 1", str(caught.exception))

    def test_invalid_config_fails_before_output_or_algorithm_execution(self) -> None:
        value = _valid_config()
        value["cases"][0]["density"] = 0
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "invalid.json"
            config_path.write_text(json.dumps(value), encoding="utf-8")
            output = root / "output"
            with patch("maxcover.benchmark._execute_task") as algorithms:
                with self.assertRaises(ConfigurationError):
                    run_benchmark(config_path, output)
            algorithms.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
