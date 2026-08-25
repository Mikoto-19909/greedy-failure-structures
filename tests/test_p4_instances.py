from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import ALGORITHMS
from maxcover.benchmark import _instances_for_config, _tasks_for_config, run_benchmark
from maxcover.config import ConfigurationError, parse_config
from maxcover.contracts import GreedyFailureRecord, InstanceRecord
from maxcover.model import Solution, SolutionStatus
from maxcover.reproducibility import config_hash


def _write_config(root: Path, value: dict[str, object]) -> Path:
    path = root / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _base_config(*, algorithm: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "P4 instance records",
        "base_seed": 401,
        "repetitions": 2,
        "algorithms": [algorithm or {"name": "greedy", "id": "greedy"}],
        "cases": [
            {
                "name": "random",
                "family": "uniform",
                "universe_size": 20,
                "set_count": 8,
                "k": 3,
                "density": 0.2,
            },
            {
                "name": "trap",
                "family": "adversarial",
                "block_size": 10,
                "distractor_count": 3,
            },
        ],
    }


class InstanceOutputTests(unittest.TestCase):
    def test_instances_csv_round_trips_and_links_every_raw_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _base_config()
            config["algorithms"] = [
                {"name": "greedy", "id": "greedy"},
                {"name": "brute_force", "id": "brute"},
            ]
            result = run_benchmark(
                _write_config(root, config), root / "output"
            )
            self.assertEqual(len(result.instances), 4)
            with (result.output_dir / "instances.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(tuple(rows[0]), InstanceRecord.CSV_FIELDS)
            restored = [InstanceRecord.from_csv_row(row) for row in rows]
            self.assertEqual(
                [record.to_csv_row() for record in restored],
                [record.to_csv_row() for record in result.instances],
            )
            malformed_rows = []
            missing = dict(rows[0])
            del missing["actual_density"]
            malformed_rows.append(missing)
            unknown = dict(rows[0])
            unknown["unexpected"] = "value"
            malformed_rows.append(unknown)
            wrong_schema = dict(rows[0])
            wrong_schema["schema_version"] = "3"
            malformed_rows.append(wrong_schema)
            for malformed in malformed_rows:
                with self.assertRaises(ValueError):
                    InstanceRecord.from_csv_row(malformed)
            keys = {
                (record.case_id, record.repetition, record.instance_id)
                for record in restored
            }
            self.assertEqual(len(keys), 4)
            self.assertTrue(
                all(
                    (row.case_id, row.repetition, row.instance_id) in keys
                    for row in result.rows
                )
            )
            trap = [record for record in restored if record.family == "adversarial"]
            self.assertTrue(all(record.instance_origin == "constructed" for record in trap))
            self.assertTrue(all(record.is_adversarial for record in trap))
            self.assertTrue(all(record.adversarial_severity is None for record in trap))
            legacy = trap[0]
            invalid_legacy_values = (
                {"adversarial_severity": 0.1},
                {"realized_trap_fraction": 0.1},
                {
                    "known_optimum": 0,
                    "optimum_source": "claimed",
                    "optimum_selected": (),
                    "proof_kind": "claimed",
                },
            )
            for changes in invalid_legacy_values:
                with self.assertRaises(ValueError):
                    replace(legacy, **changes)

            report = (result.output_dir / "results_summary.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "Greedy-gap headline withheld: 0/2 Case/variant groups",
                report,
            )
            self.assertNotIn(
                "Largest eligible mean gap outside constructed instance "
                "families:",
                report,
            )

    def test_instances_are_identical_across_parallelism_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _write_config(root, _base_config())
            sequential = run_benchmark(config, root / "one", workers=1)
            parallel = run_benchmark(config, root / "many", workers=2)
            self.assertEqual(
                (sequential.output_dir / "instances.csv").read_bytes(),
                (parallel.output_dir / "instances.csv").read_bytes(),
            )
            resumed = run_benchmark(config, root / "one")
            self.assertEqual(len(resumed.instances), 4)
            with (root / "one" / "instances.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 4)

    def test_force_cleans_only_runner_owned_artifacts(self) -> None:
        seeded = _base_config(
            algorithm={
                "name": "randomized_greedy",
                "id": "randomized",
                "algorithm_seeds": [1, 2],
                "options": {"rcl_size": 2},
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = _write_config(root, seeded)
            output = root / "output"
            seeded_result = run_benchmark(config_path, output)
            self.assertTrue((output / "stochastic_summary.csv").exists())
            self.assertEqual(seeded_result.greedy_failure_statistics, ())
            greedy_failure_path = output / "greedy_failure_statistics.csv"
            with greedy_failure_path.open(
                encoding="utf-8", newline=""
            ) as handle:
                reader = csv.reader(handle)
                self.assertEqual(
                    tuple(next(reader)), GreedyFailureRecord.CSV_FIELDS
                )
                self.assertEqual(list(reader), [])
            (output / "search_comparison.csv").write_text("stale", encoding="utf-8")
            greedy_failure_path.write_text("stale", encoding="utf-8")
            (output / "failures").mkdir(exist_ok=True)
            (output / "failures" / "stale.json").write_text("{}", encoding="utf-8")
            (output / "notes.txt").write_text("preserve me", encoding="utf-8")

            replacement = _base_config()
            replacement["repetitions"] = 1
            config_path.write_text(json.dumps(replacement), encoding="utf-8")
            with patch(
                "maxcover.benchmark._execute_task",
                side_effect=KeyboardInterrupt("stop after force cleanup"),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    run_benchmark(config_path, output, force=True)
            self.assertFalse(greedy_failure_path.exists())
            self.assertEqual(
                (output / "notes.txt").read_text(encoding="utf-8"),
                "preserve me",
            )

            replacement_result = run_benchmark(config_path, output, force=True)

            self.assertFalse((output / "stochastic_summary.csv").exists())
            self.assertFalse((output / "search_comparison.csv").exists())
            self.assertFalse((output / "failures" / "stale.json").exists())
            with greedy_failure_path.open(
                encoding="utf-8", newline=""
            ) as handle:
                greedy_failure_rows = list(csv.DictReader(handle))
            self.assertEqual(
                len(greedy_failure_rows),
                len(replacement_result.greedy_failure_statistics),
            )
            self.assertGreater(len(greedy_failure_rows), 0)
            self.assertTrue(
                all(
                    GreedyFailureRecord.from_csv_row(row)
                    for row in greedy_failure_rows
                )
            )
            self.assertEqual((output / "notes.txt").read_text(encoding="utf-8"), "preserve me")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("notes.txt", manifest["outputs"])
            self.assertIn("instances.csv", manifest["outputs"])

    def test_each_failed_seed_gets_a_run_id_named_replay(self) -> None:
        config = _base_config(
            algorithm={
                "name": "randomized_greedy",
                "id": "randomized",
                "algorithm_seeds": [11, 22],
                "options": {"rcl_size": 2},
            }
        )
        config["repetitions"] = 1
        config["cases"] = [config["cases"][0]]
        original = ALGORITHMS["randomized_greedy"]

        def timeout(instance, options):
            return Solution(
                algorithm="randomized_greedy",
                selected=(0,),
                feasible_value=instance.coverage((0,)),
                runtime_seconds=0.001,
                status=SolutionStatus.TIMEOUT,
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(
                ALGORITHMS,
                {"randomized_greedy": replace(original, runner=timeout)},
            ):
                result = run_benchmark(
                    _write_config(root, config), root / "output"
                )
            artifacts = sorted((result.output_dir / "failures").glob("*.json"))
            self.assertEqual(len(artifacts), 2)
            self.assertEqual(
                {artifact.stem for artifact in artifacts},
                {row.run_id for row in result.rows},
            )
            documents = [
                json.loads(path.read_text(encoding="utf-8")) for path in artifacts
            ]
            self.assertEqual(
                {document["run_id"] for document in documents},
                {row.run_id for row in result.rows},
            )

    def test_instances_exist_even_when_no_algorithm_is_eligible(self) -> None:
        config = _base_config(
            algorithm={
                "name": "brute_force",
                "id": "limited",
                "options": {"max_set_count": 1},
            }
        )
        config["repetitions"] = 1
        config["cases"] = [config["cases"][0]]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_benchmark(_write_config(root, config), root / "output")
            self.assertEqual(result.rows, ())
            self.assertEqual(len(result.instances), 1)
            self.assertEqual(result.greedy_failure_statistics, ())
            with (result.output_dir / "greedy_failure_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                reader = csv.reader(handle)
                self.assertEqual(
                    tuple(next(reader)), GreedyFailureRecord.CSV_FIELDS
                )
                self.assertEqual(list(reader), [])


class InstancePreflightTests(unittest.TestCase):
    def test_repetitions_above_seed_stride_are_rejected_at_exact_path(self) -> None:
        config = _base_config()
        config["repetitions"] = 10_001
        with self.assertRaises(ConfigurationError) as caught:
            parse_config(config)
        self.assertIn("$.repetitions: must not exceed 10000", str(caught.exception))

    def test_seed_stride_boundary_keeps_adjacent_equal_cases_distinct(self) -> None:
        config = {
            "schema_version": 3,
            "name": "seed stride boundary",
            "base_seed": 23,
            "repetitions": 10_000,
            "algorithms": [{"name": "greedy", "id": "greedy"}],
            "cases": [
                {
                    "name": name,
                    "family": "uniform",
                    "universe_size": 1,
                    "set_count": 1,
                    "k": 1,
                    "density": 1.0,
                }
                for name in ("left", "right")
            ],
        }
        parsed = parse_config(config)
        identifier = config_hash(parsed)
        instances = _instances_for_config(parsed)
        tasks = _tasks_for_config(parsed, identifier, instances)

        left_last = instances[9_999]
        right_first = instances[10_000]
        self.assertEqual(left_last.instance.seed, 10_022)
        self.assertEqual(right_first.instance.seed, 10_023)
        self.assertNotEqual(left_last.instance_id, right_first.instance_id)
        self.assertNotEqual(tasks[9_999].run_id, tasks[10_000].run_id)
        self.assertEqual(len({item.instance_id for item in instances}), 20_000)
        self.assertEqual(len({task.run_id for task in tasks}), 20_000)


if __name__ == "__main__":
    unittest.main()
