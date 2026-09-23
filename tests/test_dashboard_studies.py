"""Saved study readers preserve units, original artifacts and path boundaries."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard_studies import PREVIEW_LIMIT, StudiesError, StudiesService


class StudiesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = StudiesService(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, source: str, filename: str, text: str) -> Path:
        path = self.root / source / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_json(self, source: str, filename: str, value: dict) -> None:
        self.write(source, filename, json.dumps(value))

    def write_csv(self, source: str, filename: str, columns: list[str], rows: list[list[str]]) -> None:
        path = self.write(source, filename, "")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)

    def r2(self, source: str = "results/r2") -> None:
        self.write_json(source, "config.json", {"version": "r2-budget-v1", "tasks": [{"seed": 42}]})
        self.write_csv(source, "budget_results.csv",
                       ["base_graph_id", "n", "d", "repetition", "k", "instance_id", "greedy", "optimum", "relative_gap"],
                       [["graph-1", "12", "3", "0", str(k), f"instance-{k}", "8", "9", "0.1111111111111111"]
                        for k in range(1, 5)])
        self.write_csv(source, "cell_summary.csv",
                       ["n", "d", "k", "count", "failures", "failure_lower", "failure_upper"],
                       [["12", "3", "4", "1", "1", "0.02500000000000000", "1.0"]])
        self.write_csv(source, "mechanism_summary.csv", ["n", "d", "k", "count", "failures"],
                       [["12", "3", "4", "1", "1"]])

    def test_r2_preserves_original_strings_intervals_and_separate_historical_states(self) -> None:
        self.r2()
        self.write_json("results/r2", "run_status.json", {"complete": False, "computed": 1})
        self.write_json("results/r2", "verification.json", {"status": "passed", "graphs": {"graph-1": {}}})
        self.write_json("results/r2", "summary_verification.json", {"status": "failed", "scope": "derived_consistency_only"})
        data = self.service.detail("results/r2")
        self.assertEqual(data["kind"], "r2")
        tables = {table["name"]: table for table in data["tables"]}
        self.assertEqual(tables["budget_results.csv"]["total"], 4)
        self.assertEqual(tables["cell_summary.csv"]["rows"][0]["count"], "1")
        self.assertEqual(tables["cell_summary.csv"]["rows"][0]["failure_lower"], "0.02500000000000000")
        self.assertNotIn("instances", data)
        self.assertFalse(data["statuses"]["run_status"]["data"]["complete"])
        self.assertEqual(data["statuses"]["verification"]["data"]["status"], "passed")
        self.assertEqual(data["statuses"]["summary_verification"]["data"]["status"], "failed")
        self.assertEqual(data["statuses"]["verification"]["omitted_fields"], ["graphs"])
        self.assertFalse(data["statuses"]["analysis_status"]["present"])
        self.assertIn("历史", data["notice"])
        self.assertEqual(data["errors"], [])

    def test_r3_keeps_graph_and_endpoint_counts_distinct_and_primary_summary_unchanged(self) -> None:
        source = "experiments/r3"
        self.write_json(source, "config.json", {"version": "r3-first-step-confirm-v1-fixture"})
        primary = {"n": 2, "endpoints": 8, "delta": 0.5, "lower": -0.25, "upper": 1.0,
                   "confidence": 0.95, "direction": "inconclusive"}
        self.write_json(source, "primary_summary.json", primary)
        self.write_csv(source, "base_graph_summary.csv", ["base_graph_id", "difference"],
                       [["g1", "1.0"], ["g2", "0.0"]])
        seed = "18446744073709551615"
        self.write_csv(source, "endpoint_results.csv", ["base_graph_id", "direction", "replica", "chain_seed"],
                       [[graph, side, replica, seed] for graph in ("g1", "g2") for side in ("-1", "1") for replica in ("0", "1")])
        data = self.service.detail(source)
        self.assertEqual(data["kind"], "r3")
        self.assertEqual(data["documents"][0]["data"], primary)
        self.assertEqual([table["total"] for table in data["tables"]], [2, 8])
        self.assertEqual(data["tables"][1]["rows"][0]["chain_seed"], seed)

    def test_r4_prefix_and_dual_are_identified_from_native_headers(self) -> None:
        for source, columns, expected in (
            ("results/prefix", ["base_graph_id", "upper", "initial_upper"], "r4"),
            ("results/dual", ["base_graph_id", "dual_upper", "prefix_upper"], "r4_dual"),
        ):
            self.write_csv(source, "budget_results.csv", columns, [["g1", "7", "8"]])
            self.write_csv(source, "cell_summary.csv", ["n", "d", "k", "count"], [["12", "3", "4", "1"]])
            self.assertEqual(self.service.detail(source)["kind"], expected)
        self.assertEqual([entry["kind"] for entry in self.service.library()["sources"]], ["r4_dual", "r4"])

    def test_preview_reports_full_count_and_download_is_original_bytes(self) -> None:
        self.r2()
        path = self.write("results/r2", "budget_results.csv", "base_graph_id,k,greedy,optimum,relative_gap\n" +
                          "".join(f"g{i},1,1,2,0.5\n" for i in range(PREVIEW_LIMIT + 9)))
        data = self.service.detail("results/r2")
        table = next(table for table in data["tables"] if table["name"] == "budget_results.csv")
        self.assertEqual((table["total"], table["shown"], table["truncated"]), (209, 200, True))
        original = path.read_bytes()
        payload, media = self.service.artifact("results/r2", "budget_results.csv")
        self.assertEqual(payload, original)
        self.assertEqual(media, "text/csv; charset=utf-8")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(payload.splitlines()), 210)

    def test_late_bad_csv_row_invalidates_table_without_breaking_other_files(self) -> None:
        self.r2()
        self.write("results/r2", "budget_results.csv", "base_graph_id,k,greedy,optimum,relative_gap\n" +
                   "g1,1,1,2,0.5\n" * (PREVIEW_LIMIT + 1) + "too,few\n")
        data = self.service.detail("results/r2")
        table = next(table for table in data["tables"] if table["name"] == "budget_results.csv")
        self.assertIsNone(table["total"])
        self.assertEqual(table["rows"], [])
        self.assertIn("different width", table["error"])
        self.assertIsNone(data["tables"][0]["error"])
        self.assertEqual(data["errors"][0]["file"], "budget_results.csv")

    def test_duplicate_columns_and_bad_json_are_independent_errors(self) -> None:
        self.r2()
        self.write("results/r2", "cell_summary.csv", "n,n,count\n12,12,1\n")
        self.write("results/r2", "verification.json", '{"status": "passed", "cost": NaN}')
        self.write("results/r2", "summary_verification.json", "[1, 2]")
        data = self.service.detail("results/r2")
        self.assertIn("unique column", data["tables"][0]["error"])
        self.assertIn("non-finite", data["statuses"]["verification"]["error"])
        self.assertIn("JSON object", data["statuses"]["summary_verification"]["error"])
        self.assertEqual(len(data["errors"]), 3)
        self.assertEqual(data["tables"][2]["total"], 4)

    def test_missing_table_is_reported_and_in_progress_config_is_discoverable(self) -> None:
        self.write_json("results/pending", "config.json", {"version": "r4-l5-dual-v1"})
        self.write_json("results/pending", "run_status.json", {"complete": False})
        self.write_json("results/unrelated", "config.json", {"version": "benchmark"})
        self.assertEqual([entry["source"] for entry in self.service.library()["sources"]], ["results/pending"])
        data = self.service.detail("results/pending")
        self.assertEqual(len(data["errors"]), 2)
        self.assertTrue(all(table["error"] for table in data["tables"]))
        self.assertFalse(data["statuses"]["verification"]["present"])

    def test_invalid_paths_and_non_artifact_downloads_are_rejected(self) -> None:
        self.r2()
        for source in ("", "../results/r2", "results/../r2", "results/./r2", "results\\r2",
                       "results/r2/", "results:escape", str(self.root / "results/r2"), "analysis/r2", "results/\x00"):
            with self.subTest(source=source), self.assertRaises(StudiesError):
                self.service.detail(source)
        for name in ("../config.json", "graphs/graph-1.json", "execution.jsonl", "C:/file", "x.csv"):
            with self.subTest(name=name), self.assertRaises(StudiesError):
                self.service.artifact("results/r2", name)

    def test_linked_directory_is_not_discovered_or_read(self) -> None:
        self.r2("outside/r2")
        link = self.root / "results/link"
        link.parent.mkdir()
        target = self.root / "outside/r2"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           check=True, capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.service.library()["sources"], [])
        with self.assertRaises(StudiesError):
            self.service.detail("results/link")
        with self.assertRaises(StudiesError):
            self.service.artifact("results/link", "config.json")

    def test_broken_source_does_not_hide_valid_sources(self) -> None:
        self.r2()
        self.write("experiments/broken", "budget_results.csv", "k,k\n1,1\n")
        sources = self.service.library()["sources"]
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["kind"], "unknown")
        self.assertIsNotNone(sources[0]["error"])
        self.assertEqual(sources[1]["kind"], "r2")
        self.assertEqual(self.service.detail("experiments/broken")["tables"], [])


if __name__ == "__main__":
    unittest.main()
