"""Saved comparisons preserve selected data and reject unusable local snapshots."""
from __future__ import annotations

import csv
import http.client
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover.dashboard import DashboardConflictError, DashboardService, _DashboardHTTPServer
from maxcover.dashboard_jobs import JobService
from maxcover.dashboard_exports import ComparisonExports
from maxcover.dashboard_workbench import WorkbenchError


class ComparisonExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "experiments/r1"
        self.source.mkdir(parents=True)
        shutil.copyfile(ROOT / "experiments/r1_prefix_exchange_v1/paths.jsonl", self.source / "paths.jsonl")
        self.exports = ComparisonExports(self.root)
        self.payload = {"title": "R1 失效实例 <script>bad</script>", "note": "观察：仅针对已保存样本。",
                        "sources": ["experiments/r1"], "filters": {"outcome": "loss"}}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_full_export_and_frozen_values_survive_source_replacement_and_restart(self) -> None:
        saved = self.exports.save(self.payload)
        data = saved["comparison"]
        self.assertEqual((data["input_records"], data["filtered_records"], data["total"]), (66, 60, 22))
        self.assertEqual(sum(item["records"] for item in data["summaries"]), 60)
        exports = {kind: self.exports.artifact(saved["id"], kind)[0] for kind in ("csv", "md", "svg", "json")}
        (self.source / "paths.jsonl").write_text("invalid", encoding="utf-8")
        reopened = ComparisonExports(self.root)
        self.assertEqual(reopened.list_views()["views"][0]["id"], saved["id"])
        for kind, content in exports.items():
            self.assertEqual(reopened.artifact(saved["id"], kind)[0], content)
        rows = list(csv.DictReader(io.StringIO(exports["csv"].decode("utf-8-sig"))))
        self.assertEqual(len(rows), 22)
        self.assertEqual(rows[0]["seed"], data["rows"][0]["seed"])
        self.assertNotIn("<script>", exports["md"].decode("utf-8"))
        svg = ET.fromstring(exports["svg"])
        self.assertNotIn("script", [node.tag.rsplit("}", 1)[-1] for node in svg.iter()])

    def test_selected_rows_above_page_size_are_all_exported(self) -> None:
        saved = self.exports.save({**self.payload, "filters": {"population": "all"}})
        self.assertEqual(saved["comparison"]["total"], 66)
        self.assertEqual(len(saved["comparison"]["rows"]), 50)
        full = json.loads(self.exports.artifact(saved["id"], "json")[0])
        self.assertEqual(len(full["comparison"]["rows"]), 66)
        csv_rows = list(csv.DictReader(io.StringIO(self.exports.artifact(saved["id"], "csv")[0].decode("utf-8-sig"))))
        self.assertEqual(len(csv_rows), 66)

    def test_empty_comparison_saves_without_fabricating_a_plot(self) -> None:
        saved = self.exports.save({**self.payload, "filters": {"case": "missing"}})
        self.assertEqual(saved["comparison"]["total"], 0)
        self.assertTrue(self.exports.artifact(saved["id"], "csv")[0])
        with self.assertRaisesRegex(WorkbenchError, "no mean gaps"):
            self.exports.artifact(saved["id"], "svg")

    def test_invalid_payload_and_paths_do_not_create_snapshots(self) -> None:
        for change in ({"title": ""}, {"title": "x" * 121}, {"note": []}, {"sources": "experiments/r1"},
                       {"sources": ["results/../../outside"]}, {"filters": {"include_all": True}},
                       {"filters": {"outcome": "unknown"}}, {"command": "execute"}):
            with self.subTest(change=change), self.assertRaises(WorkbenchError):
                self.exports.save({**self.payload, **change})
        self.assertFalse((self.root / "results/dashboard_views").exists())
        for identifier in ("../x", "a" * 31, "A" * 32, ""):
            with self.assertRaises(WorkbenchError):
                self.exports.get(identifier)

    def test_corrupt_nested_records_and_nonfinite_numbers_are_local_errors(self) -> None:
        saved = self.exports.save(self.payload)
        path = self.root / "results/dashboard_views" / (saved["id"] + ".json")
        original = path.read_text(encoding="utf-8")
        for mutate in (
            lambda data: data["comparison"]["rows"].__setitem__(0, None),
            lambda data: data["comparison"]["summaries"].__setitem__(0, {}),
            lambda data: data["comparison"]["summaries"][0].__setitem__("mean_gap", float("nan")),
            lambda data: data["comparison"]["summaries"][0].__setitem__("mean_gap", float("inf")),
            lambda data: data["comparison"].__setitem__("total", -1),
        ):
            data = json.loads(original); mutate(data); path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(WorkbenchError):
                self.exports.get(saved["id"])
            for kind in ("csv", "md", "svg", "json"):
                with self.assertRaises(WorkbenchError):
                    self.exports.artifact(saved["id"], kind)
            self.assertTrue(self.exports.list_views()["views"][0]["error"])

    def test_save_route_requires_same_origin_and_download_is_attachment(self) -> None:
        server = _DashboardHTTPServer(("127.0.0.1", 0), DashboardService(self.root))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            # Origin must be rejected before consuming a body. Sending a body
            # after that rejection races socket closure on Windows.
            connection.request("POST", "/api/workbench/views", headers={"Content-Type": "application/json", "Content-Length": "1"})
            response = connection.getresponse(); response.read(); self.assertEqual(response.status, 403)
            connection.request("POST", "/api/workbench/views", json.dumps(self.payload),
                               {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"})
            response = connection.getresponse(); saved = json.loads(response.read()); self.assertEqual(response.status, 201)
            connection.request("GET", f'/api/workbench/views/{saved["id"]}/artifact?format=csv')
            response = connection.getresponse(); response.read()
            self.assertEqual(response.status, 200)
            self.assertIn("attachment", response.getheader("Content-Disposition"))
        finally:
            connection.close(); server.shutdown(); server.server_close(); worker.join()

    def test_close_waits_for_in_progress_job_initialization_and_prevents_reopen(self) -> None:
        service = DashboardService(self.root)
        started, release, closed = threading.Event(), threading.Event(), threading.Event()
        created = []

        def factory(root: Path) -> JobService:
            started.set()
            if not release.wait(5):
                raise RuntimeError("test did not release initialization")
            queue = JobService(root); created.append(queue)
            return queue

        with patch("maxcover.dashboard.JobService", side_effect=factory):
            initialize = threading.Thread(target=lambda: service.research_jobs)
            closer = threading.Thread(target=lambda: (service.close(), closed.set()))
            initialize.start(); self.assertTrue(started.wait(5)); closer.start()
            self.assertFalse(closed.wait(.05))
            release.set(); initialize.join(5); closer.join(5)
        self.assertTrue(closed.is_set())
        self.assertFalse(created[0]._thread.is_alive())
        with self.assertRaises(DashboardConflictError):
            _ = service.research_jobs

    def test_research_http_preserves_large_seeds_and_exact_search_counts(self) -> None:
        service = DashboardService(self.root)
        server = _DashboardHTTPServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        record = {"n": 3000, "seed": 16941105954642047133, "candidate_space": 10 ** 80, "delta": .6815}
        try:
            with patch.object(service.studies, "detail", return_value={"primary": record}):
                connection.request("GET", "/api/studies/detail?source=results/example")
                response = connection.getresponse(); data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(data["primary"], {**record, "seed": str(record["seed"]), "candidate_space": str(record["candidate_space"])})
        finally:
            connection.close(); server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
