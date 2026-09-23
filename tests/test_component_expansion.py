"""Shared rendering/replay and a new failure-bundle consumer."""
from __future__ import annotations

from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import replay_instance_file
from maxcover.case_workflows import assemble_failure_bundle
from maxcover.comparison import ComparisonSelection
from maxcover.comparison_rendering import render_snapshot
from maxcover.comparison_workflows import assemble_snapshot
from maxcover.dashboard_exports import ComparisonExports
from maxcover.dashboard_workbench import WorkbenchService
from maxcover.replay_documents import greedy_replay_document


class ComponentExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = "experiments/r1"
        target = self.root / self.source / "paths.jsonl"
        target.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "experiments/r1_prefix_exchange_v1/paths.jsonl", target)
        self.reader = WorkbenchService(self.root)
        self.analysis = self.reader.analyze([self.source], ComparisonSelection(outcome="loss"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_memory_and_saved_rendering_share_exact_bytes(self) -> None:
        snapshot = assemble_snapshot(self.analysis, identifier="d" * 32, saved_at="2026-09-21", title="<title>")
        snapshot["comparison"]["rows"][0]["case_id"] = "=untrusted"
        snapshot["comparison"]["rows"][0]["seed"] = "16941105954642047133"
        before = deepcopy(snapshot)
        rendered = {name: render_snapshot(snapshot, name) for name in ("json", "csv", "md", "svg")}
        self.assertFalse((self.root / "results/dashboard_views").exists())
        exports = ComparisonExports(self.root)
        exports.store.save(snapshot)
        for name, artifact in rendered.items():
            self.assertEqual(exports.artifact(snapshot["id"], name), artifact)
        csv_rows = list(csv.DictReader(io.StringIO(rendered["csv"][0].decode("utf-8-sig"))))
        self.assertEqual(csv_rows[0]["case_id"], "'=untrusted")
        self.assertEqual(csv_rows[0]["seed"], "16941105954642047133")
        self.assertIn("&lt;title&gt;", rendered["svg"][0].decode("utf-8"))
        self.assertEqual(snapshot, before)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            render_snapshot(snapshot, "exe")

    def test_new_bundle_reuses_population_and_all_failure_inventory(self) -> None:
        bundle = assemble_failure_bundle(self.analysis, self.reader.export, maximum_cases=3)
        self.assertEqual(bundle["selected_cases"], 22)
        self.assertEqual(bundle["exported_cases"], 3)
        self.assertTrue(bundle["truncated"])
        self.assertEqual(bundle["comparison"]["filtered_records"], 60)
        self.assertEqual(len(bundle["comparison"]["rows"]), 22)
        self.assertEqual(sum(g["records"] for g in bundle["comparison"]["summaries"]), 60)
        self.assertEqual([c["key"] for c in bundle["cases"]], [r["key"] for r in self.analysis.selected.rows[:3]])
        for index, case in enumerate(bundle["cases"]):
            path = self.root / f"replay-{index}.json"
            path.write_text(json.dumps(case["document"]), encoding="utf-8")
            self.assertTrue(replay_instance_file(path)[1])

    def test_bundle_rejects_wrong_selection_limits_and_resolver_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "loss-filtered"):
            assemble_failure_bundle(self.reader.analyze([self.source], ComparisonSelection()), self.reader.export)
        for value in (0, 201, True):
            with self.assertRaises(ValueError):
                assemble_failure_bundle(self.analysis, self.reader.export, maximum_cases=value)
        def wrong(source, key):
            document = self.reader.export(source, key)
            document["provenance"]["record_key"] = "another-record"
            return document
        with self.assertRaisesRegex(ValueError, "differs"):
            assemble_failure_bundle(self.analysis, wrong)
        def unavailable(source, key):
            raise ValueError("saved instance unavailable")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            assemble_failure_bundle(self.analysis, unavailable)

    def test_bundle_preserves_empty_selection_without_resolving(self) -> None:
        analysis = self.reader.analyze([self.source], ComparisonSelection(case="absent", outcome="loss"))
        def unexpected(source, key):
            self.fail("empty selection must not resolve any instance")
        bundle = assemble_failure_bundle(analysis, unexpected)
        self.assertEqual(bundle["cases"], [])
        self.assertEqual(bundle["selected_cases"], 0)
        self.assertFalse(bundle["truncated"])

    def test_shared_replay_builder_checks_witness_and_copies_metadata(self) -> None:
        row = self.analysis.selected.rows[0]
        saved = self.reader.export(row["source"], row["key"])
        expected = saved["replay"]["expected"]
        built = greedy_replay_document(saved["instance"], coverage=expected["coverage"],
                                       selected=expected["selected"], provenance=saved["provenance"])
        self.assertEqual(built, {key: saved[key] for key in ("instance", "replay", "provenance")})
        built["instance"]["sets"].clear()
        self.assertTrue(saved["instance"]["sets"])
        for selection in ([True], [-1], [0] * saved["instance"]["k"]):
            with self.assertRaises(ValueError):
                greedy_replay_document(saved["instance"], coverage=expected["coverage"],
                                       selected=selection, provenance=saved["provenance"])
        with self.assertRaisesRegex(ValueError, "coverage"):
            greedy_replay_document(saved["instance"], coverage=expected["coverage"] + 1,
                                   selected=expected["selected"], provenance=saved["provenance"])


if __name__ == "__main__":
    unittest.main()
