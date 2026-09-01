"""Focused unit tests for command-line subcommands."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import REPORT_FILENAMES, RUNNER_OWNED_FILENAMES, run_benchmark
from maxcover.cli import build_parser, main
from maxcover.generators import uniform_random
from maxcover.reproducibility import instance_payload


def _valid_config() -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "CLI validation fixture",
        "base_seed": 17,
        "repetitions": 2,
        "algorithms": [{"name": "greedy"}],
        "cases": [
            {
                "name": "small_uniform",
                "family": "uniform",
                "universe_size": 8,
                "set_count": 4,
                "k": 2,
                "density": 0.25,
            }
        ],
    }


class HelpConsistencyTests(unittest.TestCase):
    def test_top_level_help_lists_every_command_and_default(self) -> None:
        help_text = build_parser().format_help()

        for command in (
            "quick",
            "demo",
            "audit-stressors",
            "validate-config",
            "summarize",
            "benchmark",
            "resume",
            "replay",
            "dashboard",
        ):
            self.assertIn(command, help_text)
        self.assertIn("When COMMAND is omitted", help_text)
        self.assertIn("quick starter benchmark", help_text)

    def test_subcommand_help_covers_every_accepted_parameter(self) -> None:
        parser = build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        expected_options = {
            "quick": set(),
            "demo": set(),
            "audit-stressors": {
                "--config",
                "--incidence-tolerance",
                "--strict",
            },
            "validate-config": {"--config"},
            "summarize": {"--config", "--output"},
            "benchmark": {
                "--config",
                "--output",
                "--workers",
                "--force",
                "--dry-run",
            },
            "cartography": {
                "--config",
                "--design",
                "--output",
                "--workers",
                "--force",
            },
            "resume": {"--config", "--output", "--workers", "--force"},
            "replay": {"--instance", "--algorithm"},
            "dashboard": {"--host", "--port"},
        }

        self.assertEqual(set(subparser_action.choices), set(expected_options))
        for command, option_strings in expected_options.items():
            command_parser = subparser_action.choices[command]
            self.assertTrue(command_parser.description, command)
            actual_options: set[str] = set()
            for action in command_parser._actions:
                public_options = {
                    option
                    for option in action.option_strings
                    if option not in {"-h", "--help"}
                }
                if not public_options:
                    continue
                actual_options.update(public_options)
                self.assertIsNotNone(action.help, f"{command}: {public_options}")
                self.assertNotEqual(action.help, argparse.SUPPRESS)
            self.assertEqual(actual_options, option_strings, command)

        benchmark_help = " ".join(
            subparser_action.choices["benchmark"].format_help().split()
        )
        replay_help = " ".join(
            subparser_action.choices["replay"].format_help().split()
        )
        self.assertIn("required unless --dry-run", benchmark_help)
        self.assertIn("without writing output", benchmark_help)
        self.assertIn("defaults to the algorithm recorded", replay_help)


class ValidateConfigCommandTests(unittest.TestCase):
    def test_valid_config_is_preflighted_without_running_algorithms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "valid.json"
            config_path.write_text(json.dumps(_valid_config()), encoding="utf-8")
            output = io.StringIO()
            argv = [
                "run_project.py",
                "validate-config",
                "--config",
                str(config_path),
            ]
            with patch.object(sys, "argv", argv), patch(
                "maxcover.cli.run_benchmark"
            ) as run, redirect_stdout(output):
                result = main()

        self.assertEqual(result, 0)
        run.assert_not_called()
        rendered = output.getvalue()
        self.assertIn(f"Configuration is valid: {config_path.resolve()}", rendered)
        self.assertIn("Schema version: 3", rendered)
        self.assertIn("Expanded cases: 1", rendered)
        self.assertIn("Instances: 2", rendered)
        self.assertIn("Algorithm runs: 2", rendered)

    def test_invalid_config_returns_nonzero_without_a_traceback(self) -> None:
        invalid = _valid_config()
        invalid["unknown"] = True
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "invalid.json"
            config_path.write_text(json.dumps(invalid), encoding="utf-8")
            argv = [
                "run_project.py",
                "validate-config",
                "--config",
                str(config_path),
            ]
            errors = io.StringIO()
            with patch.object(sys, "argv", argv), patch(
                "maxcover.cli.run_benchmark"
            ) as run, redirect_stderr(errors):
                result = main()

        self.assertEqual(result, 1)
        run.assert_not_called()
        self.assertIn("error: invalid experiment configuration", errors.getvalue())
        self.assertIn("$.unknown: unknown field", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())


class SummarizeCommandTests(unittest.TestCase):
    def test_rebuilds_derived_artifacts_without_running_algorithms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical_config_path = root / "config.json"
            alias_directory = root / "path-alias"
            alias_directory.mkdir()
            config_path = alias_directory / ".." / canonical_config_path.name
            output_dir = root / "output"
            config = _valid_config()
            config["repetitions"] = 1
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run_benchmark(config_path, output_dir)
            initial_report = (output_dir / "results_summary.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                f"Configuration: `{canonical_config_path.resolve().as_posix()}`",
                initial_report,
            )
            self.assertNotIn("path-alias/..", initial_report)
            reproducible_names = [
                name
                for name in RUNNER_OWNED_FILENAMES
                if name != "manifest.json" and (output_dir / name).is_file()
            ]
            expected = {
                name: (output_dir / name).read_bytes()
                for name in reproducible_names
            }
            for name in REPORT_FILENAMES:
                (output_dir / name).write_text("stale\n", encoding="utf-8")

            rendered = io.StringIO()
            argv = [
                "run_project.py",
                "summarize",
                "--config",
                str(config_path),
                "--output",
                str(output_dir),
            ]
            with patch.object(sys, "argv", argv), patch(
                "maxcover.benchmark._execute_task",
                side_effect=AssertionError("summarize executed an algorithm"),
            ), redirect_stdout(rendered):
                result = main()

            actual = {
                name: (output_dir / name).read_bytes()
                for name in reproducible_names
            }

        self.assertEqual(result, 0)
        self.assertEqual(actual, expected)
        self.assertIn(
            "Summary rebuilt from canonical benchmark artifacts",
            rendered.getvalue(),
        )
        self.assertIn("Algorithm runs: 1", rendered.getvalue())
        self.assertIn("Summary groups: 1", rendered.getvalue())

    def test_incomplete_checkpoint_is_rejected_before_algorithm_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            output_dir = root / "output"
            config = _valid_config()
            config["repetitions"] = 1
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run_benchmark(config_path, output_dir)
            raw_results = output_dir / "raw_results.csv"
            header = raw_results.read_text(encoding="utf-8").splitlines()[0]
            raw_results.write_text(header + "\n", encoding="utf-8")
            argv = [
                "run_project.py",
                "summarize",
                "--config",
                str(config_path),
                "--output",
                str(output_dir),
            ]
            errors = io.StringIO()
            with patch.object(sys, "argv", argv), patch(
                "maxcover.benchmark._execute_task",
                side_effect=AssertionError("summarize executed an algorithm"),
            ), redirect_stderr(errors):
                result = main()

        self.assertEqual(result, 1)
        self.assertIn(
            "incomplete for summarize: missing 1 planned run", errors.getvalue()
        )
        self.assertNotIn("Traceback", errors.getvalue())


class ProcessExitCodeTests(unittest.TestCase):
    def _run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, str(ROOT / "run_project.py"), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )

    def test_success_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "valid.json"
            config_path.write_text(json.dumps(_valid_config()), encoding="utf-8")
            completed = self._run_cli(
                "validate-config", "--config", str(config_path)
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Configuration is valid", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_configuration_error_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "invalid.json"
            config_path.write_text('{"schema_version": 3}', encoding="utf-8")

            completed = self._run_cli(
                "validate-config", "--config", str(config_path)
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("error: invalid experiment configuration", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_missing_required_argument_returns_two(self) -> None:
        completed = self._run_cli("benchmark", "--config", "missing.json")

        self.assertEqual(completed.returncode, 2)
        self.assertIn("benchmark requires --output", completed.stderr)

    def test_resume_missing_config_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = self._run_cli(
                "resume",
                "--config",
                str(root / "missing.json"),
                "--output",
                str(root / "output"),
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("error:", completed.stderr)
        self.assertIn("missing.json", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_replay_mismatch_returns_one(self) -> None:
        instance = uniform_random(
            universe_size=8, set_count=4, k=2, density=0.25, seed=17
        )
        document = {
            "instance": instance_payload(instance),
            "replay": {
                "algorithm": "greedy",
                "options": {},
                "expected": {"coverage": -1, "selected": []},
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            instance_path = Path(temporary) / "mismatch.json"
            instance_path.write_text(json.dumps(document), encoding="utf-8")

            completed = self._run_cli("replay", "--instance", str(instance_path))

        self.assertEqual(completed.returncode, 1)
        self.assertIn("Replay mismatch.", completed.stderr)
        self.assertNotIn("Replay mismatch.", completed.stdout)

    def test_malformed_checkpoint_csv_returns_one_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            output_dir = root / "output"
            config = _valid_config()
            config["repetitions"] = 1
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run_benchmark(config_path, output_dir)
            raw_results = output_dir / "raw_results.csv"
            header = raw_results.read_text(encoding="utf-8").splitlines()[0]
            oversized_field = "x" * (csv.field_size_limit() + 1)
            raw_results.write_text(
                f"{header}\n{oversized_field}\n",
                encoding="utf-8",
            )

            completed = self._run_cli(
                "summarize",
                "--config",
                str(config_path),
                "--output",
                str(output_dir),
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("error: field larger than field limit", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
