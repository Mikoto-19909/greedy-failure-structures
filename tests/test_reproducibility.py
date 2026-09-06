from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maxcover.benchmark as benchmark_module
from maxcover.contracts import RunRecord
from maxcover.algorithms import ALGORITHMS
from maxcover.benchmark import replay_instance_file, run_benchmark
from maxcover.generators import uniform_random
from maxcover.reproducibility import (
    DEFAULT_INSTANCE_RESOURCE_LIMITS,
    instance_from_payload,
    instance_id,
    instance_payload,
)


def _config(*, algorithms: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": 2,
        "name": "P2 reproducibility",
        "base_seed": 31,
        "repetitions": 2,
        "algorithms": algorithms or [{"name": "greedy"}, {"name": "local_search"}],
        "cases": [
            {
                "name": "tiny",
                "family": "uniform",
                "universe_size": 30,
                "set_count": 8,
                "k": 3,
                "density": 0.2,
            }
        ],
    }


def _write_config(root: Path, value: dict[str, object]) -> Path:
    path = root / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _stable_rows(result) -> list[dict[str, object]]:
    rows = []
    for record in result.rows:
        row = record.to_csv_row()
        row.pop("runtime_seconds")
        rows.append(row)
    return rows


class ReproducibilityTests(unittest.TestCase):
    def test_partial_resume_removes_legacy_manifest_and_only_runs_missing_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _write_config(root, _config())
            output = root / "output"
            original = run_benchmark(config, output)
            manifest = output / "manifest.json"
            manifest.write_text('{"legacy":true}\n', encoding="utf-8")
            note = output / "research-notes.md"
            note.write_text("keep this note", encoding="utf-8")
            with (output / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=RunRecord.CSV_FIELDS)
                writer.writeheader()
                writer.writerows(row.to_csv_row() for row in original.rows[:-1])
            with patch.object(benchmark_module, "_execute_task", wraps=benchmark_module._execute_task) as execute:
                resumed = run_benchmark(config, output)
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(len(resumed.rows), len(original.rows))
            self.assertFalse(manifest.exists())
            self.assertEqual(note.read_text(encoding="utf-8"), "keep this note")

    def test_summarize_removes_legacy_manifest_without_rerunning_algorithms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _write_config(root, _config())
            output = root / "output"
            run_benchmark(config, output)
            raw_before = (output / "raw_results.csv").read_bytes()
            report_before = (output / "results_summary.md").read_bytes()
            (output / "manifest.json").write_text("legacy", encoding="utf-8")
            (output / "results_summary.md").write_text("stale", encoding="utf-8")
            with patch.object(benchmark_module, "_execute_task", side_effect=AssertionError("unexpected rerun")):
                benchmark_module.summarize_benchmark(config, output)
            self.assertFalse((output / "manifest.json").exists())
            self.assertEqual((output / "raw_results.csv").read_bytes(), raw_before)
            self.assertEqual((output / "results_summary.md").read_bytes(), report_before)

    def test_invalid_resume_keeps_legacy_manifest_and_existing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = _config()
            config = _write_config(root, value)
            output = root / "output"
            run_benchmark(config, output)
            manifest = output / "manifest.json"
            manifest.write_text("legacy", encoding="utf-8")
            raw_before = (output / "raw_results.csv").read_bytes()
            value["base_seed"] += 1
            config.write_text(json.dumps(value), encoding="utf-8")
            for command in (run_benchmark, benchmark_module.summarize_benchmark):
                with self.subTest(command=command.__name__):
                    with self.assertRaises(ValueError):
                        command(config, output)
                    self.assertEqual(manifest.read_text(encoding="utf-8"), "legacy")
                    self.assertEqual((output / "raw_results.csv").read_bytes(), raw_before)

    @staticmethod
    def _instance_payload() -> dict[str, object]:
        return {
            "schema_version": 1,
            "encoding": "elements",
            "universe_size": 3,
            "sets": [[0, 1]],
            "k": 1,
            "family": "resource-limit-fixture",
            "seed": 1,
            "parameters": {},
        }

    def test_instance_json_round_trips_elements_and_bitsets(self) -> None:
        instance = uniform_random(
            universe_size=25, set_count=7, k=2, density=0.3, seed=9
        )
        for encoding in ("elements", "bitsets"):
            with self.subTest(encoding=encoding):
                restored = instance_from_payload(
                    instance_payload(instance, encoding=encoding)
                )
                self.assertEqual(restored, instance)
                self.assertEqual(instance_id(restored), instance_id(instance))

    def test_instance_id_is_stable_across_processes(self) -> None:
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "from maxcover.generators import uniform_random; "
            "from maxcover.reproducibility import instance_id; "
            "instance=uniform_random(universe_size=25,set_count=7,k=2,"
            "density=.3,seed=9); print(instance_id(instance))"
        )
        values = [
            subprocess.check_output(
                [sys.executable, "-c", script], cwd=ROOT, text=True
            ).strip()
            for _ in range(2)
        ]
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(values[0]), 64)

    def test_instance_resource_limits_allow_compatibility_boundaries(self) -> None:
        limits = DEFAULT_INSTANCE_RESOURCE_LIMITS
        payload = self._instance_payload()
        payload["universe_size"] = limits.max_universe_size
        payload["sets"] = [list(range(limits.max_elements_per_set))]
        restored = instance_from_payload(payload)
        self.assertEqual(restored.universe_size, limits.max_universe_size)

        bitset_payload = self._instance_payload()
        bitset_payload.update(
            {
                "encoding": "bitsets",
                "universe_size": limits.max_universe_size,
                "sets": ["0x" + "f" * (limits.max_bitset_chars - 2)],
            }
        )
        bitset = instance_from_payload(bitset_payload)
        self.assertEqual(instance_id(bitset), instance_id(restored))

        set_count_payload = self._instance_payload()
        set_count_payload["encoding"] = "bitsets"
        set_count_payload["sets"] = ["0x0"] * limits.max_set_count
        instance_from_payload(set_count_payload)

        nested: object = "leaf"
        for _ in range(limits.max_parameter_depth):
            nested = {"child": nested}
        nested_payload = self._instance_payload()
        nested_payload["parameters"] = nested
        instance_from_payload(nested_payload)

    def test_instance_resource_limits_reject_before_expensive_operations(self) -> None:
        limits = DEFAULT_INSTANCE_RESOURCE_LIMITS
        cases: list[tuple[str, dict[str, object], str]] = []

        universe_payload = self._instance_payload()
        universe_payload["universe_size"] = limits.max_universe_size + 1
        cases.append(("universe", universe_payload, "universe_size"))

        set_count_payload = self._instance_payload()
        set_count_payload["encoding"] = "bitsets"
        set_count_payload["sets"] = ["0x0"] * (limits.max_set_count + 1)
        cases.append(("set count", set_count_payload, "set count"))

        elements_payload = self._instance_payload()
        elements_payload["sets"] = [
            list(range(limits.max_elements_per_set + 1))
        ]
        elements_payload["universe_size"] = limits.max_universe_size
        cases.append(("elements per set", elements_payload, "element count"))

        negative_payload = self._instance_payload()
        negative_payload["sets"] = [[-1]]
        cases.append(("negative element", negative_payload, "outside"))

        out_of_range_payload = self._instance_payload()
        out_of_range_payload["universe_size"] = limits.max_universe_size
        out_of_range_payload["sets"] = [[limits.max_universe_size]]
        cases.append(("out-of-range element", out_of_range_payload, "outside"))

        hex_payload = self._instance_payload()
        hex_payload.update(
            {
                "encoding": "bitsets",
                "universe_size": limits.max_universe_size,
                "sets": ["0x" + "1" * (limits.max_bitset_chars - 1)],
            }
        )
        cases.append(("hex length", hex_payload, "bitset entry"))

        nested = "leaf"
        for _ in range(limits.max_parameter_depth + 1):
            nested = {"child": nested}
        nested_payload = self._instance_payload()
        nested_payload["parameters"] = nested
        cases.append(("parameter depth", nested_payload, "nesting depth"))

        mixed_nested: object = "leaf"
        for depth in range(limits.max_parameter_depth):
            if depth % 2:
                mixed_nested = [mixed_nested]
            else:
                mixed_nested = (mixed_nested,)
        mixed_nested_payload = self._instance_payload()
        mixed_nested_payload["parameters"] = {"child": mixed_nested}
        cases.append(
            ("mixed parameter depth", mixed_nested_payload, "nesting depth")
        )

        for name, payload, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, message):
                    instance_from_payload(payload)


    def test_interruption_checkpoints_and_resume_skips_completed_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = _write_config(root, _config())
            output = root / "output"
            original = benchmark_module._execute_task
            calls = 0

            def interrupt_second(task):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt("simulated interruption")
                return original(task)

            with patch(
                "maxcover.benchmark._execute_task", side_effect=interrupt_second
            ):
                with self.assertRaises(KeyboardInterrupt):
                    run_benchmark(config_path, output)
            with (output / "raw_results.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                checkpoint = list(csv.DictReader(handle))
            self.assertEqual(len(checkpoint), 1)

            result = run_benchmark(config_path, output)
            self.assertEqual(len(result.rows), 4)
            self.assertEqual(len({row.run_id for row in result.rows}), 4)

    def test_force_reruns_completed_ids(self) -> None:
        value = _config(algorithms=[{"name": "greedy"}])
        value["repetitions"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = _write_config(root, value)
            output = root / "output"
            first = run_benchmark(config_path, output)
            original = ALGORITHMS["greedy"]
            calls = 0

            def counted(instance, options):
                nonlocal calls
                calls += 1
                return original.runner(instance, options)

            with patch.dict(
                ALGORITHMS, {"greedy": replace(original, runner=counted)}
            ):
                second = run_benchmark(config_path, output, force=True)
            self.assertEqual(calls, 1)
            self.assertEqual(first.rows[0].run_id, second.rows[0].run_id)

    def test_spawn_parallelism_preserves_order_ids_and_objective_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = _write_config(root, _config())
            sequential = run_benchmark(config_path, root / "one", workers=1)
            parallel = run_benchmark(config_path, root / "many", workers=2)
            self.assertEqual(_stable_rows(sequential), _stable_rows(parallel))
            self.assertEqual(
                [row.run_id for row in sequential.rows],
                [row.run_id for row in parallel.rows],
            )

    def test_timeout_is_exported_and_replays_without_generator(self) -> None:
        value = _config(
            algorithms=[
                {
                    "name": "brute_force",
                    "options": {
                        "time_limit_seconds": 1e-12,
                        "max_set_count": 20,
                    },
                }
            ]
        )
        value["repetitions"] = 1
        value["cases"][0].update(
            {"universe_size": 80, "set_count": 14, "k": 7, "density": 0.08}
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_benchmark(_write_config(root, value), root / "output")
            self.assertTrue(result.rows[0].timed_out)
            artifacts = list((result.output_dir / "failures").glob("*.json"))
            self.assertEqual(len(artifacts), 1)
            solution, matches = replay_instance_file(artifacts[0])
            self.assertEqual(solution.coverage, result.rows[0].coverage)
            self.assertEqual(solution.selected, result.rows[0].selected)
            self.assertTrue(matches)


if __name__ == "__main__":
    unittest.main()
