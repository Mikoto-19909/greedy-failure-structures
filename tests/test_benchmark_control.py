"""Cooperative stops preserve the public runner, checkpoints and spawn cleanup."""
from __future__ import annotations

import csv
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover import benchmark


def configuration(repetitions: int = 4) -> dict:
    return {"schema_version": 3, "name": "controlled fixture", "base_seed": 31,
        "repetitions": repetitions, "algorithms": [{"name": "greedy"}],
        "cases": [{"name": "tiny", "family": "uniform", "universe_size": 8,
                   "set_count": 5, "k": 2, "density": 0.5}]}


class BenchmarkControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps(configuration()), encoding="utf-8")
        self.output = self.root / "output"

    def rows(self) -> list[dict[str, str]]:
        with (self.output / "raw_results.csv").open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source))

    def test_pause_flushes_uncheckpointed_record_and_resume_only_executes_missing(self) -> None:
        checks = 0
        def control():
            nonlocal checks
            checks += 1
            return "pause" if checks == 2 else None
        with self.assertRaises(benchmark._BenchmarkStopped) as stopped:
            benchmark._run_benchmark_controlled(self.config, self.output, checkpoint_interval=100, control=control)
        self.assertEqual(stopped.exception.action, "pause")
        saved = self.rows()
        self.assertEqual(len(saved), 1)
        with patch.object(benchmark, "_execute_task", wraps=benchmark._execute_task) as execute:
            result = benchmark.run_benchmark(self.config, self.output)
        self.assertEqual(execute.call_count, 3)
        self.assertEqual(self.rows()[0], saved[0])
        self.assertEqual(len(result.rows), 4)
        with patch.object(benchmark, "_execute_task", side_effect=AssertionError("completed run executed")):
            benchmark.run_benchmark(self.config, self.output)

    def test_cancel_before_work_retains_resumable_empty_checkpoint(self) -> None:
        with patch.object(benchmark, "_execute_task") as execute:
            with self.assertRaises(benchmark._BenchmarkStopped):
                benchmark._run_benchmark_controlled(self.config, self.output, control=lambda: "cancel")
        execute.assert_not_called()
        self.assertEqual(self.rows(), [])
        self.assertEqual(len(benchmark.run_benchmark(self.config, self.output).rows), 4)

    def test_worker_error_stays_primary_when_shutdown_also_fails(self) -> None:
        primary = RuntimeError("worker primary")
        with patch.object(benchmark, "ProcessPoolExecutor") as factory:
            pool = factory.return_value
            pool.map.return_value = iter([None])
            pool.shutdown.side_effect = OSError("secondary shutdown")
            with patch.object(benchmark, "_record_for_completed", side_effect=primary):
                with self.assertRaisesRegex(RuntimeError, "worker primary") as raised:
                    benchmark._run_benchmark_controlled(self.config, self.output, workers=2)
        self.assertIs(raised.exception, primary)
        self.assertIn("secondary shutdown", " ".join(primary.__notes__))

    def test_failed_stop_checkpoint_is_failure_not_successful_pause(self) -> None:
        original = benchmark._write_csv
        def write(path, rows, fields):
            if path.name == "raw_results.csv":
                raise OSError("checkpoint primary")
            return original(path, rows, fields)
        with patch.object(benchmark, "_write_csv", side_effect=write):
            with self.assertRaisesRegex(OSError, "checkpoint primary"):
                benchmark._run_benchmark_controlled(self.config, self.output, control=lambda: "pause")

    def test_checkpoint_notification_failure_keeps_the_persisted_checkpoint(self) -> None:
        def notify(rows):
            if rows:
                raise OSError("progress disk unavailable")
        with self.assertRaisesRegex(OSError, "progress disk unavailable"):
            benchmark._run_benchmark_controlled(self.config, self.output, checkpoint_saved=notify)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(benchmark.run_benchmark(self.config, self.output).rows), 4)

    def test_shutdown_failure_cannot_be_reported_as_successful_pause(self) -> None:
        checks = 0
        def control():
            nonlocal checks
            checks += 1
            return "pause" if checks == 2 else None
        with patch.object(benchmark, "ProcessPoolExecutor") as factory:
            pool = factory.return_value
            pool.map.side_effect = lambda function, tasks: map(function, tasks)
            pool.shutdown.side_effect = OSError("could not drain workers")
            with self.assertRaisesRegex(OSError, "could not drain workers"):
                benchmark._run_benchmark_controlled(self.config, self.output, workers=2, control=control)

    def test_real_spawn_preserves_ids_seeds_order_and_values(self) -> None:
        serial = benchmark.run_benchmark(self.config, self.output)
        parallel = benchmark._run_benchmark_controlled(self.config, self.root / "parallel", workers=2, control=lambda: None)
        def stable(rows):
            return [{key: value for key, value in row.to_csv_row().items() if key != "runtime_seconds"} for row in rows]
        self.assertEqual(stable(serial.rows), stable(parallel.rows))
        self.assertEqual(list(inspect.signature(benchmark.run_benchmark).parameters),
            ["config_path", "output_dir", "workers", "force", "expected_config_hash", "checkpoint_interval"])


if __name__ == "__main__":
    unittest.main()
