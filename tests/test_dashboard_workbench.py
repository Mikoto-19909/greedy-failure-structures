"""Research workbench arithmetic, provenance, replay and HTTP regressions."""

from __future__ import annotations

import copy
import csv
import http.client
import json
import sys
import tempfile
import threading
import unittest
from itertools import combinations
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import replay_instance_file
from maxcover.dashboard import DashboardService, _DashboardHTTPServer
from maxcover.dashboard_workbench import WorkbenchError, WorkbenchService


class WorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = WorkbenchService(self.root)
        self.r1 = [json.loads(line) for line in
                   (ROOT / "experiments/r1_prefix_exchange_v1/paths.jsonl").read_text(encoding="utf-8").splitlines()]
        with (ROOT / "experiments/core_rq/overlap_pilot_v1/raw_results.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            self.fields = reader.fieldnames
            self.raw = list(reader)
        self.write_r1(self.r1)
        self.write_benchmark(self.raw)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_r1(self, rows: list[dict], source: str = "experiments/r1") -> None:
        target = self.root / source / "paths.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def write_benchmark(self, rows: list[dict], source: str = "results/pilot") -> None:
        target = self.root / source / "raw_results.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_real_pilot_counts_and_fixture_separation(self) -> None:
        library = self.service.library()["sources"]
        self.assertEqual([(item["records"], item["instances"]) for item in library], [(66, 66), (120, 60)])
        data = self.service.compare(["experiments/r1", "results/pilot"], algorithm="greedy")
        self.assertEqual(data["input_records"], 186)
        self.assertEqual(data["filtered_records"], 120)
        self.assertEqual([(item["records"], item["losses"]) for item in data["summaries"]],
                         [(30, 12), (30, 10), (30, 12), (30, 10)])
        fixtures = self.service.compare(["experiments/r1"], population="fixture")
        self.assertEqual(fixtures["total"], 6)
        self.assertTrue(all(row["population"] == "fixture" for row in fixtures["rows"]))
        all_data = self.service.compare(["experiments/r1"], population="all")
        self.assertEqual(sum(item["records"] for item in all_data["summaries"]), 66)

    def test_loss_filter_does_not_change_denominator_and_pages_are_complete(self) -> None:
        rows = []
        for index in range(2005):
            row = dict(self.raw[0], run_id=f"run-{index}", instance_id=f"instance-{index}", repetition=str(index))
            if index != 2004:
                row.update(coverage="33", optimality_gap="0")
            rows.append(row)
        self.write_benchmark(rows)
        data = self.service.compare(["results/pilot"], outcome="loss")
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["rows"][0]["key"], "run-2004")
        self.assertEqual(data["summaries"][0]["records"], 2005)
        self.assertEqual(data["summaries"][0]["losses"], 1)
        self.assertAlmostEqual(data["summaries"][0]["loss_rate"], 1 / 2005)
        final = self.service.compare(["results/pilot"], page=999)
        self.assertEqual(final["page"], 40)
        self.assertEqual(len(final["rows"]), 5)

    def test_missing_reference_is_not_zero_loss_and_large_seed_is_exact(self) -> None:
        row = dict(self.raw[0], optimum="", optimality_gap="")
        self.write_benchmark([row])
        data = self.service.compare(["results/pilot"])
        self.assertIsNone(data["summaries"][0]["mean_gap"])
        self.assertIsNone(data["summaries"][0]["loss_rate"])
        self.assertEqual(data["summaries"][0]["missing_gap"], 1)
        self.assertEqual(data["rows"][0]["seed"], self.raw[0]["seed"])
        self.assertEqual(self.service.compare(["results/pilot"], outcome="zero")["total"], 0)
        self.assertEqual(self.service.compare(["results/pilot"], outcome="missing")["total"], 1)

    def test_all_saved_r1_trajectories_and_replay_exports(self) -> None:
        rows = self.service.compare(["experiments/r1"], population="all", page_size=100)["rows"]
        for row in rows:
            with self.subTest(case=row["case_id"], repetition=row["repetition"]):
                detail = self.service.detail("experiments/r1", row["key"])
                trace = detail["trace"]
                self.assertEqual(trace["steps"][-1]["coverage"], row["coverage"])
                exported = self.service.export("experiments/r1", row["key"])
                file = self.root / "export.json"
                file.write_text(json.dumps(exported), encoding="utf-8")
                solution, matched = replay_instance_file(file)
                self.assertTrue(matched)
                self.assertEqual(solution.coverage, row["coverage"])

    def test_selected_trace_matches_independent_set_enumeration(self) -> None:
        row = self.service.compare(["experiments/r1"], outcome="loss")["rows"][0]
        trace = self.service.detail("experiments/r1", row["key"])["trace"]
        sets = [set(values) for values in trace["sets"]]
        choices = [(set(indices), len(set().union(*(sets[i] for i in indices))))
                   for indices in combinations(range(len(sets)), trace["k"])]
        self.assertEqual(max(value for _, value in choices), trace["optimum"])
        for step in trace["steps"]:
            self.assertEqual(step["optimal_completion"], max(value for indices, value in choices if set(step["prefix"]) <= indices))

    def test_link_includes_repetition_zero_and_never_uses_seed_alone(self) -> None:
        first = self.raw[0]
        detail = self.service.detail("results/pilot", first["run_id"])
        self.assertEqual(detail["trace_source"], "experiments/r1")
        for key, replacement in (("instance_id", "different"), ("config_hash", "different"),
                                 ("case_id", "different"), ("repetition", "99")):
            with self.subTest(key=key):
                self.write_benchmark([dict(first, **{key: replacement})])
                self.assertIsNone(self.service.detail("results/pilot", first["run_id"])["trace"])
                with self.assertRaises(WorkbenchError):
                    self.service.export("results/pilot", first["run_id"])

    def test_corrupt_source_is_isolated_and_invalid_input_is_rejected(self) -> None:
        self.write_r1([{"sets": []}], "results/broken")
        library = self.service.library()["sources"]
        self.assertEqual(sum(item.get("error") is not None for item in library), 1)
        self.assertEqual(self.service.compare(["results/pilot"])["total"], 120)
        for source in ("../outside", "results/../../outside", "configs", str(self.root), "results\\pilot"):
            with self.subTest(source=source), self.assertRaises(WorkbenchError):
                self.service.compare([source])
        for sources in ([], ["results/pilot"] * 2, [str(i) for i in range(5)]):
            with self.assertRaises(WorkbenchError):
                self.service.compare(sources)
        for kwargs in ({"page": -1}, {"page_size": 0}, {"population": "unknown"}, {"outcome": "unknown"}):
            with self.assertRaises(WorkbenchError):
                self.service.compare(["results/pilot"], **kwargs)

    def test_corrupt_trace_cannot_be_displayed_or_exported(self) -> None:
        broken = copy.deepcopy(self.r1[0])
        broken["prefixes"][1]["coverage"] += 1
        self.write_r1([broken])
        key = self.service.compare(["experiments/r1"])["rows"][0]["key"]
        with self.assertRaisesRegex(WorkbenchError, "coverage disagrees"):
            self.service.detail("experiments/r1", key)
        with self.assertRaises(WorkbenchError):
            self.service.export("experiments/r1", key)

    def test_conflicting_link_is_not_arbitrarily_selected(self) -> None:
        changed = copy.deepcopy(self.r1[0]); changed["optimum"] += 1
        self.write_r1([changed], "experiments/conflict")
        detail = self.service.detail("results/pilot", self.raw[0]["run_id"])
        self.assertIsNone(detail["trace"])
        self.assertTrue(detail["warnings"])

    def test_empty_filter_and_changed_source_identity(self) -> None:
        data = self.service.compare(["results/pilot"], case="absent")
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["summaries"], [])
        with self.assertRaises(WorkbenchError):
            self.service.detail("results/pilot", "stale-id")
        self.write_benchmark([self.raw[0], self.raw[0]])
        with self.assertRaisesRegex(WorkbenchError, "duplicate"):
            self.service.compare(["results/pilot"])

    def test_http_views_read_export_and_reject_traversal(self) -> None:
        server = _DashboardHTTPServer(("127.0.0.1", 0), DashboardService(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            for endpoint in ("/workbench", "/workbench.js", "/workbench.css", "/api/workbench/library",
                             "/api/workbench/compare?source=results%2Fpilot"):
                connection.request("GET", endpoint)
                response = connection.getresponse(); body = response.read()
                self.assertEqual(response.status, 200, body)
            query = urlencode({"source": "results/pilot", "key": self.raw[0]["run_id"]})
            connection.request("GET", "/api/workbench/export?" + query)
            response = connection.getresponse()
            self.assertIn("instance", json.loads(response.read()))
            self.assertEqual(response.status, 200)
            for endpoint in ("/api/workbench/compare?source=results%2F..%2F..%2Fsecret",
                             "/api/workbench/compare?source=results%2Fpilot&page=bad",
                             "/api/workbench/detail?source=results%2Fpilot&key=missing"):
                connection.request("GET", endpoint)
                response = connection.getresponse(); response.read()
                self.assertEqual(response.status, 400)
        finally:
            connection.close(); server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
