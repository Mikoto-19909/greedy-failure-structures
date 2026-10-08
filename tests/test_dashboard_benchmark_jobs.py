"""Bounded real local benchmark jobs, controls, restart and checkpoint recovery."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover.benchmark import run_benchmark
from maxcover.config import parse_config
from maxcover.dashboard_jobs import JobConflictError, JobService, _execute_benchmark, _FileLock, _read, _write
from maxcover.reproducibility import config_hash


def configuration(repetitions: int = 4) -> dict:
    return {"schema_version": 3, "name": "queued benchmark fixture", "base_seed": 31,
        "repetitions": repetitions, "algorithms": [{"name": "greedy"}],
        "cases": [{"name": "tiny", "family": "uniform", "universe_size": 8,
                   "set_count": 5, "k": 2, "density": 0.5}]}


class BenchmarkJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        shutil.copytree(ROOT / "src/maxcover", self.root / "src/maxcover",
                        ignore=shutil.ignore_patterns("__pycache__", "dashboard_ui"))
        shutil.copytree(ROOT / "analysis", self.root / "analysis",
                        ignore=shutil.ignore_patterns("__pycache__", "*.csv", "*.json", "*.md"))
        shutil.copy2(ROOT / "counterexamples.py", self.root / "counterexamples.py")
        (self.root / "configs/local").mkdir(parents=True)
        self.config = self.root / "configs/local/example.json"
        self.config.write_text(json.dumps(configuration()), encoding="utf-8")
        self.services: list[JobService] = []

    def tearDown(self) -> None:
        for service in self.services:
            service.close()
            service._thread.join(15)
        self.temporary.cleanup()

    def service(self) -> JobService:
        service = JobService(self.root)
        # Explicit test installation; production derives this solely from its
        # loaded code, never from a data root that could contain older sources.
        service._source_root = self.root / "src"
        self.services.append(service)
        return service

    def payload(self, **changes) -> dict:
        return {"kind": "benchmark", "config": "local/example.json", "output": "example",
            "config_hash": config_hash(parse_config(json.loads(self.config.read_text(encoding="utf-8")))), **changes}

    def until(self, service: JobService, job: dict, predicate, seconds: int = 20) -> dict:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = service.get_job(job["id"])
            if predicate(result):
                return result
            time.sleep(0.03)
        self.fail(f"job did not reach expected state: {service.get_job(job['id'])}")

    def wait(self, service: JobService, job: dict) -> dict:
        return self.until(service, job, lambda item: item["status"] in {"completed", "failed", "paused", "cancelled", "interrupted"})

    def block(self) -> _FileLock:
        queue = self.root / "results/workbench_jobs"
        queue.mkdir(parents=True, exist_ok=True)
        return _FileLock(queue / "execution.lock")

    def slow(self, repetitions: int = 50) -> None:
        self.config.write_text(json.dumps(configuration(repetitions)), encoding="utf-8")
        source = self.root / "src/maxcover/benchmark.py"
        text = source.read_text(encoding="utf-8")
        text = text.replace("def _execute_task(task: _RunTask) -> _CompletedRun:\n",
            "def _execute_task(task: _RunTask) -> _CompletedRun:\n"
            "    import os\n"
            "    marker = Path('worker-' + str(os.getpid()) + '-' + task.run_id)\n"
            "    marker.write_text('running')\n"
            "    time.sleep(0.08)\n"
            "    marker.write_text('done')\n")
        source.write_text(text, encoding="utf-8")

    def test_mixed_queue_freezes_config_and_survives_restart(self) -> None:
        lock = self.block()
        service = self.service()
        try:
            first = service.submit(self.payload(workers=2))
            second = service.submit({"kind": "refute", "budget": 0})
            self.config.write_text("original changed while queued", encoding="utf-8")
            with self.assertRaises(ValueError):
                service.submit({**first["params"], "config_hash": first["params"]["config_hash"]})
        finally:
            lock.close()
        completed, refute = self.wait(service, first), self.wait(service, second)
        self.assertEqual(completed["status"], "completed", completed)
        self.assertEqual(refute["status"], "completed", refute)
        self.assertLessEqual(completed["finished_at"], refute["started_at"])
        self.assertEqual(completed["progress"]["saved_runs"], 4)
        self.assertFalse(completed["summary"]["validated"])
        self.assertEqual(completed["result_name"], "example")
        exported, media = service.result_asset(first["id"], "raw_results.csv")
        self.assertIn("text/csv", media)
        self.assertIn(b"run_id", exported)
        service.close()
        service._thread.join(5)
        restarted = self.service()
        self.assertEqual(restarted.get_job(first["id"])["summary"], completed["summary"])

    def test_active_output_reservation_and_invalid_payloads_write_no_attempt(self) -> None:
        lock = self.block()
        service = self.service()
        try:
            first = service.submit(self.payload())
            for changed in ({}, {"force": True}):
                with self.assertRaises(JobConflictError):
                    service.submit(self.payload(**changed))
            for changed in ({"output": "workbench_jobs"}, {"output": "online_matching"},
                            {"output": "ONLINE_MATCHING"}, {"output": "../outside"}, {"workers": True},
                            {"force": "yes"}, {"config": "../../outside.json"}, {"config_hash": "f" * 64}):
                with self.assertRaises(ValueError):
                    service.submit(self.payload(**changed))
            self.assertEqual(len(service.list_jobs()["jobs"]), 1)
            service.cancel(first["id"])
        finally:
            lock.close()

    def test_partial_checkpoint_resume_keeps_directory_and_original_rows(self) -> None:
        output = self.root / "results/example"
        original = run_benchmark(self.config, output)
        with (output / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows, fields = list(reader), reader.fieldnames
        with (output / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(rows[0])
        service = self.service()
        first = self.wait(service, service.submit(self.payload()))
        self.assertEqual(first["status"], "completed", first)
        with (output / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
            completed = list(csv.DictReader(handle))
        self.assertEqual(completed[0], rows[0])
        self.assertEqual([row["run_id"] for row in completed], [row.run_id for row in original.rows])
        with self.assertRaises(JobConflictError):
            service.retry(first["id"])
        source = self.root / "src/maxcover/benchmark.py"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "def _execute_task(task: _RunTask) -> _CompletedRun:\n",
            "def _execute_task(task: _RunTask) -> _CompletedRun:\n    raise RuntimeError('completed task rerun')\n"), encoding="utf-8")
        second = self.wait(service, service.resume(first["id"]))
        self.assertEqual(second["status"], "completed", second)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["output_dir"], second["output_dir"])
        self.assertEqual(second["resume_of"], first["id"])

    def test_live_spawn_pause_drains_workers_then_resumes(self) -> None:
        self.slow()
        service = self.service()
        first = service.submit(self.payload(workers=2, checkpoint_interval=1))
        self.until(service, first, lambda item: item["progress"]["saved_runs"] >= 1)
        requested = service.pause(first["id"])
        self.assertEqual(requested["control_requested"], "pause")
        stopped = self.wait(service, first)
        self.assertEqual(stopped["status"], "paused", stopped)
        self.assertTrue(0 < stopped["progress"]["saved_runs"] < 50)
        markers = list(self.root.glob("worker-*"))
        self.assertTrue(markers)
        self.assertTrue(all(marker.read_text() == "done" for marker in markers))
        next_job = self.wait(service, service.submit({"kind": "refute", "budget": 0}))
        self.assertLessEqual(stopped["finished_at"], next_job["started_at"])
        resumed = self.wait(service, service.resume(first["id"]))
        self.assertEqual(resumed["status"], "completed", resumed)
        self.assertEqual(resumed["progress"]["saved_runs"], 50)
        self.assertEqual(service.get_job(first["id"])["progress"], stopped["progress"])

    def test_queued_pause_cancel_and_running_cancel_preserve_inputs(self) -> None:
        lock = self.block()
        service = self.service()
        try:
            queued = service.submit(self.payload())
            paused = service.pause(queued["id"])
            self.assertEqual(paused["status"], "paused")
            self.assertIsNone(paused["started_at"])
            other = service.submit(self.payload(output="cancelled"))
            self.assertEqual(service.cancel(other["id"])["status"], "cancelled")
        finally:
            lock.close()
        self.slow()
        running = service.submit(self.payload(output="live-cancel"))
        self.until(service, running, lambda item: item["progress"]["saved_runs"] >= 1)
        service.cancel(running["id"])
        stopped = self.wait(service, running)
        self.assertEqual(stopped["status"], "cancelled", stopped)
        self.assertTrue((service._job_path(running["id"]).parent / "config.json").is_file())
        resumed = self.wait(service, service.resume(running["id"]))
        self.assertEqual(resumed["status"], "completed", resumed)

    def test_bad_checkpoint_fails_preserving_file_and_diagnostic_then_queue_continues(self) -> None:
        output = self.root / "results/example"
        output.mkdir(parents=True)
        raw = output / "raw_results.csv"
        raw.write_text("not,a,valid,checkpoint\n1,2,3,4\n", encoding="utf-8")
        before = raw.read_bytes()
        service = self.service()
        failed = self.wait(service, service.submit(self.payload()))
        self.assertEqual(failed["status"], "failed", failed)
        self.assertIn("Traceback", failed["log_tail"])
        self.assertTrue(failed["error_type"])
        self.assertEqual(raw.read_bytes(), before)
        self.assertEqual(self.wait(service, service.submit(self.payload(output="good")))["status"], "completed")

    def test_algorithm_errors_are_completed_records_not_validated_success(self) -> None:
        source = self.root / "src/maxcover/benchmark.py"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "solution = specification.run(task.instance, task.options)", "raise ValueError('deliberate algorithm failure')"), encoding="utf-8")
        service = self.service()
        job = self.wait(service, service.submit(self.payload()))
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(job["summary"]["counts"], {"error": 4})
        self.assertFalse(job["summary"]["validated"])

    def test_terminal_write_failure_preserves_primary_exception(self) -> None:
        lock = self.block()
        service = self.service()
        try:
            job = service.submit(self.payload())
            path = service._job_path(job["id"])
            saved = _read(path)
            saved.update(status="running", started_at=saved["created_at"], owner="test")
            primary = OSError("checkpoint primary")
            with patch("maxcover.dashboard_jobs._run_benchmark_controlled", side_effect=primary), \
                    patch("maxcover.dashboard_jobs._write", side_effect=OSError("terminal secondary")), \
                    patch("maxcover.dashboard_jobs.traceback.print_exception"):
                with self.assertRaisesRegex(OSError, "checkpoint primary") as caught:
                    _execute_benchmark(self.root, path, saved)
            self.assertIs(caught.exception, primary)
            self.assertIn("terminal secondary", " ".join(primary.__notes__))
            service.cancel(job["id"])
        finally:
            lock.close()

    def test_recovery_marks_dead_attempt_interrupted_and_resumes_missing_ids(self) -> None:
        self.slow(4)
        output = self.root / "results/example"
        run_benchmark(self.config, output)
        with (output / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows, fields = list(reader), reader.fieldnames
        with (output / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(rows[0])
        lock = self.block()
        service = self.service()
        try:
            attempt = service.submit(self.payload())
            path = service._job_path(attempt["id"])
            saved = _read(path)
            saved.update(status="running", owner="dead-owner", started_at=saved["created_at"])
            _write(path, saved)
            self.assertEqual(service.get_job(attempt["id"])["status"], "running")
        finally:
            lock.close()
        interrupted = self.wait(service, attempt)
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertEqual(interrupted["progress"]["saved_runs"], 1)
        resumed = self.wait(service, service.resume(attempt["id"]))
        self.assertEqual(resumed["status"], "completed", resumed)
        markers = list(self.root.glob("worker-*"))
        self.assertEqual(len(markers), 3)
        self.assertFalse(any(rows[0]["run_id"] in marker.name for marker in markers))

    def test_real_spawn_worker_crash_preserves_checkpoint_and_manual_recovery(self) -> None:
        source = self.root / "src/maxcover/benchmark.py"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "def _execute_task(task: _RunTask) -> _CompletedRun:\n",
            "def _execute_task(task: _RunTask) -> _CompletedRun:\n"
            "    if task.repetition == 1:\n"
            "        import os\n"
            "        time.sleep(0.2)\n"
            "        os._exit(77)\n"), encoding="utf-8")
        service = self.service()
        failed = self.wait(service, service.submit(self.payload(workers=2)))
        self.assertEqual(failed["status"], "failed", failed)
        self.assertEqual(failed["error_type"], "BrokenProcessPool")
        self.assertEqual(failed["progress"]["saved_runs"], 1)
        shutil.copy2(ROOT / "src/maxcover/benchmark.py", source)
        resumed = self.wait(service, service.resume(failed["id"]))
        self.assertEqual(resumed["status"], "completed", resumed)

    def test_worker_uses_loaded_installation_not_old_code_in_data_root(self) -> None:
        (self.root / "src/maxcover/dashboard_jobs.py").write_text("raise RuntimeError('old source used')", encoding="utf-8")
        service = JobService(self.root)
        self.services.append(service)
        job = self.wait(service, service.submit(self.payload()))
        self.assertEqual(job["status"], "completed", job)

    def test_result_read_guard_blocks_dispatch_and_overlapping_active_output(self) -> None:
        service = self.service()
        with service.reading_outputs(["results/example/raw_results.csv"]):
            queued = service.submit(self.payload())
            time.sleep(0.1)
            self.assertEqual(service.get_job(queued["id"])["status"], "queued")
        self.assertEqual(self.wait(service, queued)["status"], "completed")
        self.slow(30)
        active = service.submit(self.payload(output="live"))
        self.until(service, active, lambda item: item["progress"]["saved_runs"] > 0)
        for candidate in ("results", "results/live", "results/live/raw_results.csv"):
            with self.assertRaises(JobConflictError):
                with service.reading_outputs([candidate]):
                    self.fail("running output was readable")
        with service.reading_outputs(["results/example"]):
            self.assertTrue((self.root / "results/example/raw_results.csv").is_file())
        service.cancel(active["id"])
        self.assertEqual(self.wait(service, active)["status"], "cancelled")

    def test_invalid_benchmark_record_is_preserved_and_does_not_crash_history(self) -> None:
        service = self.service()
        complete = self.wait(service, service.submit(self.payload()))
        path = service._job_path(complete["id"])
        record = _read(path)
        for field, value in (("progress", []), ("progress", {**record["progress"], "phase": []}),
                             ("plan", {"algorithm_run_count": True}),
                             ("resume_of", "../../outside")):
            damaged = {**record, field: value}
            _write(path, damaged)
            item = service.get_job(complete["id"])
            self.assertTrue(item["corrupt_record"])
            self.assertEqual(_read(path), damaged)
            with self.assertRaises(JobConflictError):
                service.resume(complete["id"])
        _write(path, record)

    def test_reused_output_rejects_other_config_and_labels_current_same_config_artifacts(self) -> None:
        service = self.service()
        first = self.wait(service, service.submit(self.payload()))
        same = self.wait(service, service.submit(self.payload(force=True)))
        self.assertEqual(same["status"], "completed", same)
        self.assertIn("当前产物", service.result(first["id"])["artifact_notice"])
        self.assertIn(first["params"]["config_hash"].encode(), service.result_asset(first["id"], "raw_results.csv")[0])
        changed = configuration()
        changed["base_seed"] = 99
        self.config.write_text(json.dumps(changed), encoding="utf-8")
        second = self.wait(service, service.submit(self.payload(force=True)))
        self.assertEqual(second["status"], "completed", second)
        current = service.result_asset(second["id"], "raw_results.csv")[0]
        self.assertIn(second["params"]["config_hash"].encode(), current)
        for operation in (lambda: service.result(first["id"]),
                          lambda: service.result_asset(first["id"], "raw_results.csv")):
            with self.assertRaisesRegex(JobConflictError, "no longer matches"):
                operation()
        self.assertEqual(service.get_job(first["id"])["summary"], first["summary"])
        refused = self.wait(service, service.resume(first["id"]))
        self.assertEqual(refused["status"], "failed")
        self.assertEqual((self.root / "results/example/raw_results.csv").read_bytes(), current)

    def test_nonfinite_and_malformed_progress_falls_back_without_rewriting_source(self) -> None:
        lock = self.block()
        service = self.service()
        try:
            job = service.submit(self.payload())
            path = service._job_path(job["id"])
            saved = _read(path)
            saved.update(status="running", owner="previous-owner", started_at=saved["created_at"])
            _write(path, saved)
            valid = {**saved["progress"], "saved_runs": 1, "counts": {"feasible": 1}, "phase": "running"}
            progress_file = path.with_name("progress.jsonl")
            for invalid in ({**valid, "saved_runs": float("nan")}, {**valid, "extra": float("inf")},
                            {**valid, "counts": {"feasible": "1"}}, {**valid, "phase": []}):
                content = json.dumps(valid) + "\n" + json.dumps(invalid) + "\n"
                progress_file.write_text(content, encoding="utf-8")
                result = service.get_job(job["id"])
                self.assertEqual(result["progress"]["saved_runs"], 1)
                self.assertIn("invalid saved progress", result["progress"]["error"])
                json.dumps(service.list_jobs(), allow_nan=False)
                self.assertEqual(progress_file.read_text(encoding="utf-8"), content)
        finally:
            lock.close()

    def test_junction_output_is_rejected_at_submission_and_before_queued_execution(self) -> None:
        lock = self.block()
        service = self.service()
        target = self.root / "results/actual"
        target.mkdir()
        marker = target / "research-note.txt"
        marker.write_text("preserve existing data", encoding="utf-8")
        links = [self.root / "results/alias", self.root / "results/later"]

        def link(path):
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(target)],
                               check=True, capture_output=True)
            else:
                path.symlink_to(target, target_is_directory=True)

        try:
            link(links[0])
            with self.assertRaisesRegex(ValueError, "linked or reparse"):
                service.submit(self.payload(output="alias"))
            self.assertEqual(service.list_jobs()["jobs"], [])
            queued = service.submit(self.payload(output="later"))
            link(links[1])
            lock.close()
            failed = self.wait(service, queued)
            self.assertEqual(failed["status"], "failed", failed)
            self.assertIn("linked or reparse", failed["error"])
            self.assertFalse((target / "raw_results.csv").exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve existing data")
            ordinary = self.wait(service, service.submit(self.payload(output="ordinary")))
            self.assertEqual(ordinary["status"], "completed", ordinary)
        finally:
            lock.close()
            for path in links:
                if path.is_symlink():
                    path.unlink()
                elif path.exists():
                    path.rmdir()

    def test_child_continues_after_server_process_exits_and_new_server_waits(self) -> None:
        self.slow(30)
        script = "\n".join([
            "import json, os, time", "from pathlib import Path", "from maxcover.dashboard_jobs import JobService",
            f"service = JobService(Path({str(self.root)!r}))", f"job = service.submit({self.payload(workers=2)!r})",
            "while service.get_job(job['id'])['progress']['saved_runs'] < 1: time.sleep(0.02)",
            "print(job['id'], flush=True)", "os._exit(0)"])
        env = {**os.environ, "PYTHONPATH": str(self.root / "src")}
        process = subprocess.Popen([sys.executable, "-u", "-c", script], cwd=self.root, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, stderr)
        identifier = stdout.strip().splitlines()[-1]
        service = self.service()
        previous = service.get_job(identifier)
        second = service.submit(self.payload(output="after-restart", workers=2))
        if previous["status"] == "running":
            self.assertEqual(service.list_jobs()["queue_state"], "recovering")
            self.assertEqual(second["status"], "queued")
        completed = self.wait(service, previous)
        self.assertEqual(completed["status"], "completed", completed)
        next_result = self.wait(service, second)
        self.assertEqual(next_result["status"], "completed", next_result)
        self.assertLessEqual(completed["finished_at"], next_result["started_at"])


if __name__ == "__main__":
    unittest.main()
