"""Tests for the local dashboard service boundary."""

from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard import (  # noqa: E402
    DashboardConflictError,
    DashboardRequestError,
    DashboardService,
    _DashboardHTTPServer,
    serve_dashboard,
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
        self.assertRegex(inspected["config_hash"], r"^[0-9a-f]{64}$")
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
        config_hash = self.service.inspect_config("test.json")["config_hash"]
        with patch("maxcover.dashboard.run_benchmark") as run:
            job = self.service.start_run(
                {
                    "config": "test.json",
                    "config_hash": config_hash,
                    "output": "dashboard-test",
                }
            )
            deadline = time.monotonic() + 2
            while self.service.get_job(job["id"])["status"] in {"queued", "running"}:
                if time.monotonic() >= deadline:
                    self.fail("dashboard job did not finish")
                time.sleep(0.01)
            resolved_root = self.root.resolve()
            run.assert_called_once_with(
                resolved_root / "configs" / "test.json",
                resolved_root / "results" / "dashboard-test",
                workers=1,
                force=False,
                expected_config_hash=config_hash,
            )
        current = self.service.get_job(job["id"])
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["result_name"], "dashboard-test")

    def test_run_rejects_a_config_changed_after_preflight(self) -> None:
        config_hash = self.service.inspect_config("test.json")["config_hash"]
        changed = _config()
        changed["name"] = "changed after preflight"
        (self.root / "configs" / "test.json").write_text(
            json.dumps(changed), encoding="utf-8"
        )
        with self.assertRaises(DashboardConflictError):
            self.service.start_run(
                {"config": "test.json", "config_hash": config_hash}
            )


class DashboardHttpSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "configs").mkdir()
        (self.root / "configs" / "test.json").write_text(
            json.dumps(_config()), encoding="utf-8"
        )
        self.server = _DashboardHTTPServer(("127.0.0.1", 0), DashboardService(self.root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def _post(
        self, path: str, payload: object, *, origin: str | None, content_type: str
    ) -> tuple[int, dict[str, object]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        headers = {"Content-Type": content_type}
        if origin is not None:
            headers["Origin"] = origin
        connection.request("POST", path, json.dumps(payload), headers)
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, body

    def test_cross_origin_simple_post_is_rejected_before_run_dispatch(self) -> None:
        status, body = self._post(
            "/api/run",
            {"config": "test.json", "output": "attacker-triggered", "force": True},
            origin="https://attacker.example",
            content_type="text/plain",
        )
        self.assertEqual(status, 403)
        self.assertIn("same-origin", body["error"])
        self.assertEqual(self.server.service.list_jobs(), {"jobs": []})

    def test_same_origin_json_post_is_allowed(self) -> None:
        status, body = self._post(
            "/api/validate",
            {"config": "test.json"},
            origin=f"http://127.0.0.1:{self.port}",
            content_type="application/json; charset=utf-8",
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["valid"])

    def test_same_origin_non_json_post_is_rejected(self) -> None:
        status, body = self._post(
            "/api/run",
            {"config": "test.json"},
            origin=f"http://127.0.0.1:{self.port}",
            content_type="text/plain",
        )
        self.assertEqual(status, 415)
        self.assertIn("application/json", body["error"])

    def test_non_loopback_host_is_rejected_even_when_origin_matches_it(self) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request(
            "POST",
            "/api/run",
            json.dumps({"config": "test.json"}),
            {
                "Host": f"attacker.example:{self.port}",
                "Origin": f"http://attacker.example:{self.port}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        connection.close()
        self.assertEqual(response.status, 403)
        self.assertIn("same-origin", body["error"])

    def test_alternate_ipv4_loopback_host_is_allowed(self) -> None:
        server = _DashboardHTTPServer(("127.0.0.2", 0), DashboardService(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            connection = http.client.HTTPConnection("127.0.0.2", port)
            connection.request(
                "POST",
                "/api/validate",
                json.dumps({"config": "test.json"}),
                {
                    "Origin": f"http://127.0.0.2:{port}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)
            self.assertTrue(body["valid"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_non_loopback_bindings_are_rejected_before_serving(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            serve_dashboard("0.0.0.0", 0, project_root=self.root)


if __name__ == "__main__":
    unittest.main()
