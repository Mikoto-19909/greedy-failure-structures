from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import plan_benchmark, run_benchmark
from maxcover.cli import main
from maxcover.config import ConfigurationError, load_config, parse_config


def _config(cases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "name": "sweep test",
        "base_seed": 10,
        "repetitions": 2,
        "algorithms": [{"name": "greedy"}],
        "cases": cases,
    }


def _uniform_case(name: str = "uniform") -> dict[str, object]:
    return {
        "name": name,
        "family": "uniform",
        "universe_size": 20,
        "set_count": 8,
        "k": 3,
        "density": 0.2,
    }


class SweepTests(unittest.TestCase):
    def test_single_parameter_sweep_expands_readable_case_ids(self) -> None:
        case = _uniform_case("density")
        case.pop("density")
        case["sweep"] = {"density": [0.1, 0.25]}

        config = parse_config(_config([case]))

        self.assertEqual(
            [item.case_id for item in config.cases],
            ["density__density=0.1", "density__density=0.25"],
        )
        self.assertEqual(
            [item.parameters["density"] for item in config.cases], [0.1, 0.25]
        )
        self.assertTrue(all(item.name == "density" for item in config.cases))

    def test_multi_parameter_sweep_is_a_stable_cartesian_product(self) -> None:
        case = _uniform_case("matrix")
        case.pop("density")
        case.pop("k")
        case["sweep"] = {"k": [2, 4], "density": [0.1, 0.2]}
        reversed_case = copy.deepcopy(case)
        reversed_case["sweep"] = {"density": [0.1, 0.2], "k": [2, 4]}

        first = parse_config(_config([case]))
        second = parse_config(_config([reversed_case]))

        expected = [
            "matrix__density=0.1__k=2",
            "matrix__density=0.1__k=4",
            "matrix__density=0.2__k=2",
            "matrix__density=0.2__k=4",
        ]
        self.assertEqual([item.case_id for item in first.cases], expected)
        self.assertEqual(first, second)

    def test_sweep_rejects_invalid_shapes_and_duplicate_fixed_fields(self) -> None:
        invalid_sweeps = (
            ({}, "$.cases[0].sweep"),
            ({"density": []}, "$.cases[0].sweep.density"),
            ({"unknown": [1]}, "$.cases[0].sweep.unknown"),
            ({"density": ["dense"]}, "$.cases[0].sweep.density[0]"),
        )
        for sweep, expected_path in invalid_sweeps:
            with self.subTest(sweep=sweep):
                case = _uniform_case()
                if "density" in sweep:
                    case.pop("density")
                case["sweep"] = sweep
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(_config([case]))
                self.assertIn(
                    expected_path, [path for path, _ in caught.exception.issues]
                )

        case = _uniform_case()
        case["sweep"] = {"density": [0.1]}
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(_config([case]))
        self.assertEqual(caught.exception.issues[0][0], "$.cases[0].sweep.density")

    def test_sweep_semantics_report_the_exact_value_path(self) -> None:
        case = _uniform_case()
        case.pop("k")
        case["sweep"] = {"k": [2, 9]}
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(_config([case]))
        self.assertTrue(
            any(path == "$.cases[0].sweep.k[1]" for path, _ in caught.exception.issues)
        )

    def test_expanded_case_id_collisions_are_rejected(self) -> None:
        fixed = _uniform_case("x__density=0.1")
        swept = _uniform_case("x")
        swept.pop("density")
        swept["sweep"] = {"density": [0.1]}
        with self.assertRaisesRegex(ConfigurationError, "duplicate case_id"):
            parse_config(_config([fixed, swept]))

        duplicate_values = _uniform_case("duplicate")
        duplicate_values.pop("density")
        duplicate_values["sweep"] = {"density": [0.1, 0.1]}
        with self.assertRaisesRegex(ConfigurationError, "duplicate case_id"):
            parse_config(_config([duplicate_values]))

    def test_benchmark_uses_case_id_and_preserves_deterministic_seeds(self) -> None:
        case = _uniform_case("density")
        case.pop("density")
        case["sweep"] = {"density": [0.1, 0.2]}
        value = _config([case])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "config.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = run_benchmark(path, root / "output")
        self.assertEqual(
            [row.case for row in result.rows],
            [
                "density__density=0.1",
                "density__density=0.1",
                "density__density=0.2",
                "density__density=0.2",
            ],
        )
        self.assertEqual([row.seed for row in result.rows], [10, 11, 10010, 10011])

    def test_plan_counts_expanded_instances_and_eligible_runs(self) -> None:
        case = _uniform_case("scale")
        case.pop("set_count")
        case["sweep"] = {"set_count": [6, 10]}
        value = _config([case])
        value["algorithms"] = [
            {
                "name": "brute_force",
                "options": {"time_limit_seconds": 1.0, "max_set_count": 8},
            },
            {"name": "greedy"},
        ]
        plan = plan_benchmark(parse_config(value))
        self.assertEqual(len(plan.case_ids), 2)
        self.assertEqual(plan.instance_count, 4)
        self.assertEqual(plan.algorithm_run_count, 6)
        self.assertEqual(
            dict(plan.runs_by_algorithm), {"brute_force": 2, "greedy": 4}
        )

    def test_cli_dry_run_does_not_run_algorithms_or_create_output(self) -> None:
        case = _uniform_case("density")
        case.pop("density")
        case["sweep"] = {"density": [0.1, 0.2]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "config.json"
            path.write_text(json.dumps(_config([case])), encoding="utf-8")
            output = io.StringIO()
            argv = ["run_project.py", "benchmark", "--config", str(path), "--dry-run"]
            with patch.object(sys, "argv", argv), patch(
                "maxcover.cli.run_benchmark"
            ) as run, redirect_stdout(output):
                main()
            run.assert_not_called()
            self.assertFalse((root / "output").exists())
        rendered = output.getvalue()
        self.assertIn("Expanded cases: 2", rendered)
        self.assertIn("Instances: 4", rendered)
        self.assertIn("Algorithm runs: 4", rendered)
        self.assertIn("density__density=0.1", rendered)

    def test_bundled_sweep_examples_cover_required_dimensions(self) -> None:
        config = load_config(ROOT / "configs" / "sweeps.json")
        self.assertEqual(len(config.cases), 14)
        case_ids = [case.case_id for case in config.cases]
        for prefix in (
            "density_sweep__",
            "overlap_sweep__",
            "budget_sweep__",
            "scale_sweep__",
        ):
            self.assertTrue(any(case_id.startswith(prefix) for case_id in case_ids))


if __name__ == "__main__":
    unittest.main()
