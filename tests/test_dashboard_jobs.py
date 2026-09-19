"""Real bounded CLI jobs, persistence, locking and input-boundary regressions."""
from __future__ import annotations

import json
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard_jobs import JobConflictError, JobService, _execute, _FileLock, _read, _write


class DashboardJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        shutil.copytree(ROOT / "src/maxcover", self.root / "src/maxcover",
                        ignore=shutil.ignore_patterns("__pycache__", "dashboard_ui"))
        (self.root / "analysis").mkdir()
        for source in (ROOT / "analysis").glob("*.py"):
            shutil.copy2(source, self.root / "analysis" / source.name)
        shutil.copy2(ROOT / "counterexamples.py", self.root / "counterexamples.py")
        (self.root / "source.json").write_text(json.dumps({
            "universe_size": 6, "k": 2, "sets": [[0, 1, 2, 3], [0, 1, 4], [2, 3, 5]]}), encoding="utf-8")
        self.services: list[JobService] = []

    def tearDown(self) -> None:
        for service in self.services:
            service.close()
            service._thread.join(10)
        self.temporary.cleanup()

    def service(self) -> JobService:
        service = JobService(self.root)
        self.services.append(service)
        return service

    def wait(self, service: JobService, job: dict) -> dict:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = service.get_job(job["id"])
            if result["status"] in {"completed", "failed", "interrupted"}:
                return result
            time.sleep(0.03)
        self.fail(f"job did not terminate: {service.get_job(job['id'])}")

    def test_real_mining_freezes_input_and_exports_verified_case(self) -> None:
        queue = self.root / "results/workbench_jobs"
        queue.mkdir(parents=True)
        lock = _FileLock(queue / "execution.lock")
        service = self.service()
        try:
            job = service.submit({"kind": "mine", "input": "source.json", "top": 1, "max_evaluations": 50})
            (self.root / "source.json").write_text("source changed after submission", encoding="utf-8")
        finally:
            lock.close()
        result = self.wait(service, job)
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(result["summary"]["validated"])
        self.assertEqual(result["summary"]["status"], "counterexample_found")
        case = result["summary"]["cases"][0]
        self.assertEqual((case["original"]["evaluation"]["greedy"], case["original"]["evaluation"]["optimum"]), (5, 6))
        self.assertLess(case["reduced"]["evaluation"]["greedy"], case["reduced"]["evaluation"]["optimum"])
        exported, media = service.result_asset(job["id"], "counterexample_001.json")
        self.assertEqual(json.loads(exported), case["reduced"]["instance"])
        self.assertIn("application/json", media)
        self.assertTrue(service.result(job["id"])["artifacts"])
        with self.assertRaises(ValueError):
            service.result_asset(job["id"], "../../source.json")
        service.close()
        restarted = self.service()
        self.assertEqual(restarted.get_job(job["id"])["summary"], result["summary"])

    def test_serial_queue_and_refutation_outcomes(self) -> None:
        queue = self.root / "results/workbench_jobs"
        queue.mkdir(parents=True)
        lock = _FileLock(queue / "execution.lock")
        service = self.service()
        try:
            first = service.submit({"kind": "refute", "budget": 0})
            second = service.submit({"kind": "refute", "n": 2, "m": 2, "k": 1, "set_size": 1})
            self.assertEqual(service.get_job(first["id"])["status"], "queued")
            self.assertEqual(service.get_job(second["id"])["status"], "queued")
            self.assertEqual(service.list_jobs()["queue_state"], "recovering")
            with self.assertRaises(JobConflictError):
                JobService(self.root)
        finally:
            lock.close()
        first_result, second_result = self.wait(service, first), self.wait(service, second)
        self.assertEqual(first_result["summary"]["status"], "budget_exhausted")
        self.assertEqual(second_result["summary"]["status"], "domain_exhausted")
        self.assertLessEqual(first_result["finished_at"], second_result["started_at"])
        third = self.wait(service, service.submit({"kind": "refute", "n": 5, "m": 3, "k": 2, "set_size": 2, "budget": 1000}))
        self.assertEqual(third["summary"]["status"], "counterexample_found")

    def test_failed_cli_retry_uses_new_directory_and_does_not_claim_resume(self) -> None:
        service = self.service()
        job = self.wait(service, service.submit({"kind": "refute", "max_combinations": 1}))
        self.assertEqual(job["status"], "failed")
        self.assertIn("exact reference exceeds", job["log_tail"])
        with self.assertRaises(JobConflictError):
            service.result(job["id"])
        with self.assertRaises(JobConflictError):
            service.resume(job["id"])
        retried = self.wait(service, service.retry(job["id"]))
        self.assertEqual(retried["retry_of"], job["id"])
        self.assertNotEqual(retried["output_dir"], job["output_dir"])
        self.assertEqual(retried["status"], "failed")

    def test_recovery_blocks_while_previous_process_owns_execution_lock(self) -> None:
        queue = self.root / "results/workbench_jobs"
        queue.mkdir(parents=True)
        lock = _FileLock(queue / "execution.lock")
        service = self.service()
        first = service.submit({"kind": "refute", "budget": 0})
        path = service._job_path(first["id"])
        old = _read(path)
        old.update(status="running", owner="previous-owner", started_at=old["created_at"])
        _write(path, old)
        second = service.submit({"kind": "refute", "budget": 0})
        time.sleep(0.3)
        self.assertEqual(service.get_job(first["id"])["status"], "running")
        self.assertEqual(service.get_job(second["id"])["status"], "queued")
        lock.close()
        self.assertEqual(self.wait(service, first)["status"], "interrupted")
        self.assertEqual(self.wait(service, second)["status"], "completed")
        self.assertEqual(_execute(self.root, first["id"], "previous-owner"), 2)
        self.assertFalse((path.parent / "output").exists())

    def test_damaged_record_is_visible_and_does_not_kill_queue(self) -> None:
        bad = self.root / "results/workbench_jobs" / ("a" * 32) / "job.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{incomplete", encoding="utf-8")
        service = self.service()
        damaged = service.get_job("a" * 32)
        self.assertTrue(damaged["corrupt_record"])
        self.assertEqual(bad.read_text(encoding="utf-8"), "{incomplete")
        with self.assertRaises(JobConflictError):
            service.retry("a" * 32)
        job = self.wait(service, service.submit({"kind": "refute", "budget": 0}))
        self.assertEqual(job["status"], "completed", job)
        self.assertTrue(service._thread.is_alive())

    def test_incomplete_completed_records_and_nonfinite_numbers_are_quarantined(self) -> None:
        service = self.service()
        completed = self.wait(service, service.submit({"kind": "refute", "budget": 0}))
        path = service._job_path(completed["id"])
        original = _read(path)
        invalid = [{"id": original["id"], "status": "completed", "created_at": original["created_at"], "params": {}}]
        for field in ("kind", "output_dir", "input_snapshot", "summary", "finished_at"):
            item = copy.deepcopy(original)
            del item[field]
            invalid.append(item)
        for value in (None, {}, {"validated": True, "status": "budget_exhausted", "counts": {}, "cases": []}):
            invalid.append({**original, "summary": value})
        invalid.extend([{**original, "output_dir": "results/another-job/output"},
                        {**original, "input_snapshot": "../../secret.json"},
                        {**original, "started_at": None}, {**original, "error": "failed but marked completed"}])
        encoded = [json.dumps(item) for item in invalid]
        encoded.extend(json.dumps({**original, "unexpected": value}) for value in (float("nan"), float("inf"), -float("inf")))
        encoded.append(json.dumps(original)[:-1] + ', "unexpected": 1e999}')
        for text in encoded:
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                job = service.get_job(original["id"])
                self.assertTrue(job["corrupt_record"])
                self.assertEqual(job["status"], "failed")
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                json.dumps(service.list_jobs(), allow_nan=False)
                with self.assertRaises(JobConflictError):
                    service.result(original["id"])
                with self.assertRaises(JobConflictError):
                    service.retry(original["id"])
        _write(path, original)
        self.assertEqual(service.result(original["id"])["summary"]["status"], "budget_exhausted")
        self.assertTrue(service._thread.is_alive())

    def test_child_keeps_lock_and_finishes_after_parent_process_exits(self) -> None:
        cli = self.root / "counterexamples.py"
        cli.write_text("import time\nfrom pathlib import Path\n"
                       "Path(__file__).with_name('child-started').touch()\ntime.sleep(1.0)\n"
                       + cli.read_text(encoding="utf-8"), encoding="utf-8")
        parent = self.root / "parent.py"
        parent.write_text(
            "import json, os, time\nfrom pathlib import Path\n"
            "from maxcover.dashboard_jobs import JobService\n"
            "root = Path(__file__).parent\nservice = JobService(root)\n"
            "job = service.submit({'kind':'refute','budget':0})\n"
            "print(job['id'], flush=True)\n"
            "while not (root / 'child-started').exists(): time.sleep(0.01)\n"
            "os._exit(0)\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(parent)], cwd=self.root,
            env={**os.environ, "PYTHONPATH": str(self.root / "src"), "PYTHONIOENCODING": "utf-8"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stderr)
        job_id = stdout.strip()
        service = self.service()
        self.assertEqual(service.list_jobs()["queue_state"], "recovering")
        second = service.submit({"kind": "refute", "budget": 0})
        self.assertEqual(service.get_job(second["id"])["status"], "queued")
        first_result = self.wait(service, {"id": job_id})
        second_result = self.wait(service, second)
        self.assertEqual(first_result["status"], "completed", first_result)
        self.assertEqual(second_result["status"], "completed", second_result)
        self.assertLessEqual(first_result["finished_at"], second_result["started_at"])

    def test_child_enforces_wall_clock_budget_and_releases_queue(self) -> None:
        cli = self.root / "counterexamples.py"
        cli.write_text("import time\ntime.sleep(2)\n" + cli.read_text(encoding="utf-8"), encoding="utf-8")
        service = self.service()
        expired = self.wait(service, service.submit({"kind": "refute", "budget": 0, "timeout_seconds": 1}))
        self.assertEqual(expired["status"], "failed")
        self.assertIn("wall-clock budget", expired["error"])
        self.assertIsNone(expired["summary"])
        next_job = self.wait(service, service.submit({"kind": "refute", "budget": 0, "timeout_seconds": 5}))
        self.assertEqual(next_job["status"], "completed", next_job)

    def test_invalid_fields_types_paths_and_budgets_do_not_create_jobs(self) -> None:
        service = self.service()
        invalid = [{"kind": "shell", "command": "echo nope"}, {"kind": []},
            {"kind": "refute", "budget": True}, {"kind": "refute", "n": 13},
            {"kind": "refute", "min_ratio": [2, 1]}, {"kind": "refute", "timeout_seconds": 601},
            {"kind": "refute", "unique_sets": "true"}, {"kind": "refute", "output": "existing"},
            {"kind": "mine", "input": "../source.json"}, {"kind": "mine", "input": str(self.root / "source.json")},
            {"kind": "mine", "input": "source.json", "max_evaluations": -1}]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                service.submit(payload)
        self.assertEqual(service.list_jobs()["jobs"], [])


if __name__ == "__main__":
    unittest.main()
