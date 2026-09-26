"""Exercise archived matching results and a fresh fixed development run."""
from __future__ import annotations

import http.client
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard import DashboardService, _DashboardHTTPServer
from maxcover.dashboard_matching import MatchingError, OnlineMatchingService, STUDY

EVAL = "20260924T175731049376Z-eval"
DEV = "20260924T175730918352Z-dev"


class OnlineMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.study = self.root / STUDY
        self.study.mkdir(parents=True)
        source = ROOT / STUDY
        for name in ("matching.py", "run.py", "verify.py", "fixtures.py",
                     "inputs.json", "input_manifest.json", "protocol.md"):
            shutil.copyfile(source / name, self.study / name)
        for run in (EVAL, DEV):
            destination = self.study / "output" / run
            destination.mkdir(parents=True)
            for name in ("summary.json", "metrics.csv", "traces.json", "verification.json", "inputs.json"):
                shutil.copyfile(source / "output" / run / name, destination / name)
        for relative in ("extension_20260925/报告/六分支研究结果.md",):
            target = self.study / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
        self.service = OnlineMatchingService(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_saved_comparison_keeps_distance_units_and_verification(self) -> None:
        original = (self.study / "output" / EVAL / "summary.json").read_bytes()
        listing = self.service.library()
        self.assertTrue(listing["available"])
        self.assertEqual({r["sequences"] for r in listing["runs"]}, {6, 24})
        detail = self.service.detail("saved/" + EVAL)
        rows = {r["policy"]: r for r in detail["summary"]["aggregates"]
                if r["family"] == "all" and r["budget"] in (0, 1, None)}
        self.assertEqual(rows["nearest"]["prefix_sum"], 1221)
        self.assertEqual(rows["single"]["prefix_sum"], 1043)
        self.assertEqual(rows["priced_chain"]["prefix_sum"], 1033)
        self.assertEqual(rows["prefix_optimum"]["prefix_sum"], 1033)
        self.assertEqual(len(detail["cases"]), 24)
        self.assertEqual(len(detail["rows"]), 192)
        self.assertEqual(detail["verification"]["recorded_status"],
                         "automatic_verification_passed_user_review_pending")
        self.assertEqual(detail["verification"]["status"], "current_artifacts_not_revalidated")
        self.assertEqual((self.study / "output" / EVAL / "summary.json").read_bytes(), original)

    def test_replay_keeps_long_chain_and_lifetime_budget(self) -> None:
        data = self.service.trace("saved/" + DEV, "dev_uniform", "priced_chain", 1)
        last = data["trace"]["history"][-1]
        self.assertEqual(last["cost"], 31)
        self.assertEqual(len(last["moves"]), 5)
        self.assertEqual(max(last["counts"]), 1)
        self.assertEqual(data["trace"]["oracle_costs"][-1], 31)
        one = self.service.trace("saved/" + DEV, "dev_uniform", "single", 4)
        self.assertEqual(one["trace"]["history"][-1]["cost"], 61)

    def test_changed_artifacts_never_inherit_a_current_verification_pass(self) -> None:
        directory = self.study / "output" / EVAL
        record = (directory / "verification.json").read_bytes()
        for name in ("summary.json", "metrics.csv", "traces.json"):
            with self.subTest(name=name):
                path = directory / name
                original = path.read_bytes()
                if name == "metrics.csv":
                    with path.open(encoding="utf-8-sig", newline="") as handle:
                        rows = list(csv.DictReader(handle))
                    rows[0]["prefix_sum"] = str(int(rows[0]["prefix_sum"]) + 1)
                    with path.open("w", encoding="utf-8-sig", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                        writer.writeheader(); writer.writerows(rows)
                else:
                    data = json.loads(original)
                    if name == "summary.json":
                        data["aggregates"][0]["prefix_sum"] += 1
                    else:
                        data[0]["history"][0]["cost"] += 1
                    path.write_text(json.dumps(data), encoding="utf-8")
                detail = self.service.detail("saved/" + EVAL)
                self.assertEqual(detail["verification"]["status"], "current_artifacts_not_revalidated")
                self.assertEqual(detail["verification"]["recorded_status"],
                                 "automatic_verification_passed_user_review_pending")
                self.assertEqual((directory / "verification.json").read_bytes(), record)
                path.write_bytes(original)

    def test_new_output_is_ignored_while_saved_snapshots_stay_tracked(self) -> None:
        for prefix in (STUDY, STUDY + "/extension_20260925"):
            result = subprocess.run(["git", "check-ignore", "--quiet", prefix + "/output/new-run/traces.json"],
                                    cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["git", "ls-files", "--error-unmatch", STUDY + "/output/" + EVAL + "/traces.json"],
                                cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_download_is_the_original_file_and_report_is_readable(self) -> None:
        payload, media = self.service.artifact("saved/" + EVAL, "metrics.csv")
        self.assertEqual(payload, (self.study / "output" / EVAL / "metrics.csv").read_bytes())
        self.assertEqual(media, "text/csv; charset=utf-8")
        report = self.service.report("results")
        self.assertIn("六分支继续研究结果", report["text"])

    def test_invalid_paths_and_controls_are_rejected(self) -> None:
        for identifier in ("../outside", "saved/../../README.md", "local/C:/secret", EVAL):
            with self.subTest(identifier=identifier), self.assertRaises(MatchingError):
                self.service.detail(identifier)
        for payload in ({"split": "other"}, {"split": "dev", "command": "anything"}, {}):
            with self.subTest(payload=payload), self.assertRaises(MatchingError):
                self.service.run(payload)
        with self.assertRaises(MatchingError):
            self.service.artifact("saved/" + EVAL, "../../protocol.md")
        with self.assertRaises(MatchingError):
            self.service.trace("saved/" + DEV, "dev_uniform", "priced_chain", 3)

    def test_new_run_uses_separate_output_and_independent_verifier(self) -> None:
        before = sorted(p.name for p in (self.study / "output").iterdir())
        completed = self.service.run({"split": "dev"})
        self.assertTrue(completed["id"].startswith("local/"))
        self.assertEqual(len(completed["cases"]), 6)
        self.assertEqual(completed["verification"]["recorded_status"],
                         "automatic_verification_passed_user_review_pending")
        self.assertEqual(completed["verification"]["status"], "current_artifacts_not_revalidated")
        self.assertEqual(sorted(p.name for p in (self.study / "output").iterdir()), before)
        self.assertEqual(sum(r["origin"] == "本地复现" for r in self.service.library()["runs"]), 1)
        self.assertTrue((self.root / "results/online_matching" / completed["id"].split("/")[1]).is_dir())

    def test_http_page_reads_data_and_post_obeys_existing_origin_rules(self) -> None:
        service = DashboardService(self.root)
        server = _DashboardHTTPServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("GET", "/online-matching")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn("有限改派在线匹配", response.read().decode())
            connection.request("GET", "/api/online-matching/detail?run=saved/" + EVAL)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["summary"]["split"], "eval")
            connection.request("GET", "/api/online-matching/detail?run=../outside")
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.request("POST", "/api/online-matching/run", '{"split":"dev"}',
                               {"Content-Type": "application/json", "Origin": "https://example.com"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            service.close()


if __name__ == "__main__":
    unittest.main()
