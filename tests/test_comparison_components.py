"""Composition boundaries independent of Dashboard, disk inputs and solvers."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.comparison import (ComparisonSelection, paginate, select_outcomes,
                                select_population, summarize_population)
from maxcover.comparison_workflows import analyze_comparison, assemble_snapshot, preview_comparison
from maxcover.dashboard_exports import ComparisonSnapshotStore
from maxcover.dashboard_workbench import WorkbenchError


def records() -> tuple[dict, ...]:
    # One loss, one success and one missing reference, repeated beyond one page.
    rows = []
    for index in range(123):
        gap = (0.5, 0.0, None)[index % 3]
        rows.append({"source": "results/example", "key": str(index), "case_id": "case",
                     "instance_id": str(index), "algorithm_id": "greedy", "population": "experiment",
                     "universe_size": 4, "set_count": 3, "k": 1,
                     "parameters": {}, "algorithm_options": {}, "coverage": 2 if gap == 0.5 else 4,
                     "optimum": None if gap is None else 4, "optimality_gap": gap,
                     "runtime_seconds": None, "status": "saved", "selected": [0],
                     "seed": "16941105954642047133"})
    return tuple(rows)


class ComparisonComponentTests(unittest.TestCase):
    def test_memory_composition_preserves_population_and_does_not_mutate_input(self) -> None:
        rows = records()
        before = deepcopy(rows)
        selection = ComparisonSelection(outcome="loss")
        population = select_population(rows, selection)
        summary = summarize_population(population)
        selected = select_outcomes(population, selection.outcome)
        self.assertEqual(summary[0]["records"], 123)
        self.assertEqual(summary[0]["gap_records"], 82)
        self.assertEqual(summary[0]["missing_gap"], 41)
        self.assertEqual(summary[0]["loss_rate"], 0.5)
        self.assertEqual(len(selected.rows), 41)
        self.assertEqual(paginate(selected, 999, 10).page, 4)
        self.assertEqual(len(paginate(selected, 999, 10).rows), 1)
        self.assertEqual(rows, before)
        with self.assertRaisesRegex(TypeError, "population rows"):
            summarize_population(selected)  # type: ignore[arg-type]

    def test_same_analysis_drives_page_and_full_persistent_snapshot(self) -> None:
        analysis = analyze_comparison(("results/example",), records(), ComparisonSelection())
        page = preview_comparison(analysis, page_size=10)
        snapshot = assemble_snapshot(analysis, identifier="a" * 32, saved_at="2026-09-21T00:00:00Z", title="test")
        self.assertEqual(len(page["rows"]), 10)
        self.assertEqual(len(snapshot["comparison"]["rows"]), 123)
        self.assertEqual(page["summaries"], snapshot["comparison"]["summaries"])
        page["rows"][0]["selected"].append(99)
        page["summaries"][0]["parameters"]["changed"] = True
        self.assertEqual(analysis.selected.rows[0]["selected"], [0])
        self.assertEqual(snapshot["comparison"]["summaries"][0]["parameters"], {})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ComparisonSnapshotStore(root).save(snapshot)
            self.assertEqual(ComparisonSnapshotStore(root).load("a" * 32), snapshot)
        with self.assertRaisesRegex(TypeError, "complete comparison"):
            assemble_snapshot(page, identifier="a" * 32, saved_at="now", title="bad")  # type: ignore[arg-type]

    def test_store_rejects_truncated_page_before_writing(self) -> None:
        analysis = analyze_comparison(("results/example",), records(), ComparisonSelection())
        snapshot = assemble_snapshot(analysis, identifier="b" * 32, saved_at="now", title="test")
        snapshot["comparison"] = preview_comparison(analysis)
        with tempfile.TemporaryDirectory() as directory:
            store = ComparisonSnapshotStore(Path(directory))
            with self.assertRaisesRegex(WorkbenchError, "all selected records"):
                store.save(snapshot)
            self.assertFalse(store.path("b" * 32).exists())

    def test_invalid_filters_and_pages_fail_at_component_boundary(self) -> None:
        for values in ({"outcome": "invalid"}, {"population": "invalid"}):
            with self.assertRaises(ValueError):
                ComparisonSelection(**values)
        for sources in ((), ("results/example", "results/example")):
            with self.assertRaises(ValueError):
                analyze_comparison(sources, records(), ComparisonSelection())
        analysis = analyze_comparison(("results/example",), records(), ComparisonSelection(case="absent"))
        self.assertEqual(preview_comparison(analysis)["total"], 0)
        self.assertEqual(preview_comparison(analysis)["pages"], 1)
        for page, size in ((-1, 50), (True, 50), (0, 0), (0, 101)):
            with self.assertRaises(ValueError):
                preview_comparison(analysis, page, size)


if __name__ == "__main__":
    unittest.main()
