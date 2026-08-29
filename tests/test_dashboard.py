"""Tests for the local dashboard service boundary."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard import (  # noqa: E402
    DashboardRequestError,
    DashboardService,
)


def _config() -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "dashboard test",
        "base_seed": 11,
        "repetitions": 1,
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


class DashboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "configs").mkdir()
        (self.root / "configs" / "test.json").write_text(
            json.dumps(_config()), encoding="utf-8"
        )
        self.service = DashboardService(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_config_listing_and_preflight_use_existing_engine(self) -> None:
        listed = self.service.list_configs()
        configs = listed["configs"]
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["name"], "test.json")
        self.assertEqual(configs[0]["path"], "test.json")

        inspected = self.service.inspect_config("test.json")
        self.assertTrue(inspected["valid"])
        plan = inspected["plan"]
        self.assertEqual(plan["instance_count"], 1)
        self.assertEqual(plan["algorithm_run_count"], 1)
        self.assertEqual(plan["runs_by_algorithm"], [{"algorithm": "greedy", "runs": 1}])

    def test_algorithm_listing_comes_from_the_engine_registry(self) -> None:
        algorithms = self.service.list_algorithms()["algorithms"]
        names = [item["name"] for item in algorithms]
        self.assertEqual(names, sorted(names))
        self.assertIn("greedy", names)
        self.assertIn("branch_and_bound", names)

    def test_user_paths_cannot_escape_config_or_results_roots(self) -> None:
        for path in ("../test.json", "../../etc/passwd", "", "C:/outside.json"):
            with self.subTest(path=path), self.assertRaises(DashboardRequestError):
                self.service.inspect_config(path)

    def test_result_and_replay_indexes_read_local_artifacts(self) -> None:
        result = self.root / "results" / "test-run"
        failures = result / "failures"
        failures.mkdir(parents=True)
        (result / "summary.csv").write_text(
            "case,family,algorithm_id,algorithm,runs,mean_coverage,mean_optimality_gap,max_optimality_gap,mean_runtime_seconds,timeouts,schema_version\n"
            "small_uniform,uniform,greedy,greedy,1,5,, ,0.01,0,4\n",
            encoding="utf-8",
        )
        (result / "raw_results.csv").write_text(
            "case,algorithm,coverage,selected\nsmall_uniform,greedy,5,0 2\n",
            encoding="utf-8",
        )
        (result / "gap_by_case.svg").write_text("<svg></svg>", encoding="utf-8")
        (failures / "run.json").write_text(
            json.dumps(
                {
                    "run_id": "run",
                    "replay": {"algorithm": "greedy", "algorithm_id": "greedy"},
                }
            ),
            encoding="utf-8",
        )

        result_payload = self.service.get_result("test-run")
        self.assertEqual(result_payload["summary"][0]["runs"], 1)
        self.assertEqual(result_payload["runs"][0]["selected"], [0, 2])
        self.assertEqual(result_payload["artifacts"][0]["name"], "gap_by_case.svg")
        self.assertEqual(
            self.service.list_replays()["replays"],
            [
                {
                    "path": "test-run/failures/run.json",
                    "result": "test-run",
                    "run_id": "run",
                    "algorithm": "greedy",
                    "algorithm_id": "greedy",
                }
            ],
        )

    def test_run_creates_one_local_job_and_reuses_benchmark_runner(self) -> None:
        with patch("maxcover.dashboard.run_benchmark") as run:
            job = self.service.start_run({"config": "test.json", "output": "dashboard-test"})
            deadline = time.monotonic() + 2
            while self.service.get_job(job["id"])["status"] in {"queued", "running"}:
                if time.monotonic() >= deadline:
                    self.fail("dashboard job did not finish")
                time.sleep(0.01)
            run.assert_called_once_with(
                self.root / "configs" / "test.json",
                self.root / "results" / "dashboard-test",
                workers=1,
                force=False,
            )
        current = self.service.get_job(job["id"])
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["result_name"], "dashboard-test")


if __name__ == "__main__":
    unittest.main()
