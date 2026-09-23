"""Reader/index integration preserves public results and detects changed sources."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover.dashboard import DashboardService, _DashboardHTTPServer
from maxcover.dashboard_exports import ComparisonExports
from maxcover.dashboard_local import LocalCatalog
from maxcover.dashboard_studies import StudiesService
from maxcover.dashboard_workbench import WorkbenchError, WorkbenchService


class CachedReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / "experiments/r1"
        self.directory.mkdir(parents=True)
        self.file = self.directory / "paths.jsonl"
        shutil.copyfile(ROOT / "experiments/r1_prefix_exchange_v1/paths.jsonl", self.file)
        self.service = WorkbenchService(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_warm_restart_metadata_comparison_and_detail_avoid_reparsing_r1(self) -> None:
        expected = self.service.library()
        result = self.service.compare(["experiments/r1"], outcome="loss")
        row = result["rows"][0]
        detail = self.service.detail("experiments/r1", row["key"])
        restarted = WorkbenchService(self.root)
        with patch.object(restarted, "_load", side_effect=AssertionError("source was reparsed")):
            self.assertEqual(restarted.library(), expected)
            self.assertEqual(restarted.compare(["experiments/r1"], outcome="loss"), result)
            self.assertEqual(restarted.detail("experiments/r1", row["key"]), detail)
        # The memoized result cannot be changed through a returned dictionary.
        result["rows"].clear()
        self.assertEqual(self.service.compare(["experiments/r1"], outcome="loss")["total"], 22)
        self.assertEqual(len(self.service.compare(["experiments/r1"], outcome="loss")["rows"]), 22)

    def test_change_delete_and_bad_source_never_use_old_comparison(self) -> None:
        self.assertEqual(self.service.compare(["experiments/r1"])["total"], 60)
        first = self.file.read_text(encoding="utf-8").splitlines()[0]
        self.file.write_text(first + "\n", encoding="utf-8")
        self.assertEqual(self.service.compare(["experiments/r1"])["total"], 1)
        self.assertEqual(self.service.library()["sources"][0]["records"], 1)
        self.file.write_text("{bad", encoding="utf-8")
        with self.assertRaises(WorkbenchError):
            self.service.compare(["experiments/r1"])
        self.assertTrue(self.service.library()["sources"][0]["error"])
        self.file.unlink()
        with self.assertRaises(WorkbenchError):
            self.service.compare(["experiments/r1"])

    def test_source_change_during_full_export_is_not_frozen_as_a_mixed_read(self) -> None:
        source = ["experiments/r1"]
        signature = self.service._source_signatures(source)
        with patch.object(self.service, "_source_signatures", side_effect=[signature, [("changed", ())]]):
            with self.assertRaisesRegex(WorkbenchError, "source changed"):
                self.service.compare(source, include_all=True)

    def test_study_tables_and_documents_invalidate_and_reject_overflow(self) -> None:
        directory = self.root / "results/r3"; directory.mkdir(parents=True)
        table = directory / "endpoint_results.csv"
        table.write_text("base_graph_id,seed\na,16941105954642047133\n", encoding="utf-8")
        document = directory / "primary_summary.json"
        document.write_text('{"n":1,"endpoints":4,"delta":0.5}', encoding="utf-8")
        service = StudiesService(self.root)
        expected = service.detail("results/r3")
        with patch.object(service, "_load_table", side_effect=AssertionError("table reparsed")), patch.object(service, "_load_document", wraps=service._load_document) as loader:
            self.assertEqual(service.detail("results/r3"), expected)
            self.assertFalse(any(call.args[1] == "primary_summary.json" for call in loader.call_args_list))
        table.write_text("base_graph_id,seed\na,16941105954642047133\nb,1\n", encoding="utf-8")
        self.assertEqual(service._table("results/r3", "endpoint_results.csv")["total"], 2)
        document.write_text('{"n":1,"value":1e999}', encoding="utf-8")
        failed = service._document("results/r3", "primary_summary.json")
        self.assertTrue(failed["present"])
        self.assertTrue(failed["error"])
        self.assertIsNone(failed["data"])

    def test_rebuild_and_archive_http_preserve_source_and_snapshot_bytes(self) -> None:
        exports = ComparisonExports(self.root)
        saved = exports.save({"title": "原始分析", "sources": ["experiments/r1"]})
        snapshot = self.root / "results/dashboard_views" / (saved["id"] + ".json")
        before = self.file.read_bytes(), snapshot.read_bytes()
        service = DashboardService(self.root)
        server = _DashboardHTTPServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
        try:
            body = json.dumps({"kind": "view", "id": saved["id"], "archived": True})
            # Origin rejection happens before body consumption. Send headers
            # alone so Windows cannot reset a socket with an unread POST body.
            connection.request("POST", "/api/local/archive", headers={"Content-Type": "application/json", "Content-Length": str(len(body))})
            response = connection.getresponse(); response.read(); self.assertEqual(response.status, 403)
            connection.request("POST", "/api/local/archive", body, headers)
            response = connection.getresponse(); data = json.loads(response.read())
            self.assertEqual(response.status, 200); self.assertTrue(data["archived"])
            connection.request("POST", "/api/local/index/rebuild", "{}", headers)
            response = connection.getresponse(); data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(data["workbench_sources"], 1)
            self.assertTrue(LocalCatalog(self.root).list("view")[saved["id"]]["archived"])
            self.assertEqual((self.file.read_bytes(), snapshot.read_bytes()), before)
        finally:
            connection.close(); server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
