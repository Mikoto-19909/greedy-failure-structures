"""Exercise report output contracts without executing algorithms."""

from __future__ import annotations

import ast
import inspect
import pickle
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover import benchmark, reporting


# Captured from the pinned pre-extraction report, not inferred from new helpers.
HEADINGS = (
    "## Reproducibility", "## Headline checks", "## P5.1 descriptive aggregate",
    "## Exact-reference coverage and censoring diagnostics",
    "## P5.3 95% confidence intervals for instance means",
    "## P5.3 automatic-conclusion eligibility", "## P5.3 censored-runtime diagnostics",
    "## P5.2 classical Greedy failure rate", "## P5.2 mean/max relative optimality gap",
    "## P5.2 Local Search recovery rate", "## P5.2 remaining gap after Local Search recovery",
    "## P5.2 heuristic/exact runtime ratio", "## P5.2 Branch-and-Bound node reduction",
    "## P5.2 quality-runtime Pareto frontier", "## P5.4 gap vs actual-density association",
    "## P5.4 gap vs measured pairwise-overlap association",
    "## P5.4 gap vs mixed-cluster bridge intensity",
    "## P5.4 completed runtime vs candidate-set count",
    "## P5.4 completed runtime vs selection budget k",
    "## P5.4 completed BnB search nodes vs dominated-set ratio", "## Next analysis questions",
)


class ReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        output = Path(cls.temporary.name)
        fixture = ROOT / "tests/fixtures/benchmark_compatibility"
        cls.config_path = fixture / "config.json"
        for filename in ("raw_results.csv", "instances.csv"):
            shutil.copyfile(fixture / filename, output / filename)

        def prepare_report_files(output_dir, *args, **kwargs):
            # The runner publishes these files before returning its records.
            for filename in benchmark.REPORT_FILENAMES:
                (output_dir / filename).touch()

        # Build report inputs without first passing them through the candidate
        # writer: an idempotent mutation there would hide from render's check.
        with patch.object(benchmark, "_execute_task", side_effect=AssertionError("unexpected execution")), \
                patch.object(benchmark, "write_report_artifacts", side_effect=prepare_report_files):
            cls.result = benchmark.summarize_benchmark(cls.config_path, output)
        cls.names = tuple(name for name in inspect.signature(reporting.write_report_artifacts).parameters
                          if name not in {"output_dir", "config_path", "config"})
        cls.normal = {name: getattr(cls.result, "descriptive_statistics" if name == "statistics" else name)
                      for name in cls.names}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def render(self, arguments):
        before = pickle.dumps(arguments, protocol=4)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            markdown_writes = []
            write_text = Path.write_text

            def record_write(path, *args, **kwargs):
                if path.name == "results_summary.md":
                    markdown_writes.append(path)
                return write_text(path, *args, **kwargs)

            with patch.object(Path, "write_text", record_write):
                result = reporting.write_report_artifacts(directory, self.config_path, self.result.config, **arguments)
            self.assertIsNone(result)
            self.assertEqual(markdown_writes, [directory / "results_summary.md"])
            self.assertEqual(set(path.name for path in directory.iterdir()), set(benchmark.REPORT_FILENAMES))
            for path in directory.glob("*.svg"):
                self.assertEqual(ET.fromstring(path.read_bytes()).tag, "{http://www.w3.org/2000/svg}svg")
            text = (directory / "results_summary.md").read_text(encoding="utf-8")
        self.assertEqual(pickle.dumps(arguments, protocol=4), before)
        self.assertEqual(tuple(line for line in text.splitlines() if line.startswith("## ")), HEADINGS)
        return text

    def derived(self, rows, instances):
        values = {name: () for name in self.names}
        values.update(rows=tuple(rows), instances=tuple(instances))
        values["statistics"] = tuple(benchmark._descriptive_statistics(rows))
        values["confidence_interval_statistics"] = tuple(benchmark._confidence_interval_statistics(values["statistics"]))
        values["greedy_failure_statistics"] = tuple(benchmark._greedy_failure_statistics(rows))
        values["gap_density_association_statistics"] = tuple(benchmark._gap_density_association_statistics(rows, instances))
        return values

    def test_complete_report_preserves_sections_files_and_inputs(self) -> None:
        self.render(self.normal)

    def test_empty_inputs_keep_the_report_structure_and_valid_charts(self) -> None:
        self.render({name: () for name in self.names})

    def test_missing_reference_constant_and_deferred_inputs_render(self) -> None:
        # These are typed report fixtures, not complete benchmark checkpoints.
        instances = [item for item in self.result.instances if item.known_optimum is None]
        ids = {item.instance_id for item in instances}
        rows = [replace(item, optimum=None, optimality_gap=None) for item in self.result.rows
                if item.algorithm == "greedy" and item.instance_id in ids]
        missing = self.derived(rows, instances)
        self.assertTrue(all(item.sample_count == 0 for item in missing["statistics"] if item.metric == "optimality_gap"))
        self.render(missing)

        template = next(item for item in self.result.rows if item.algorithm == "greedy" and item.optimum)
        original = next(item for item in self.result.instances if item.instance_id == template.instance_id)
        copies = [replace(original, repetition=i, seed=i, instance_id=f"report-constant-{i}",
                          coupling_seed=None, coupling_pair_id=None) for i in range(2)]
        runs = [replace(template, repetition=i, seed=i, instance_id=item.instance_id,
                        run_id=f"report-run-{i}", runtime_seconds=0.125) for i, item in enumerate(copies)]
        constant = self.derived(runs, copies)
        self.assertEqual(constant["gap_density_association_statistics"][0].association_status, "constant_density")
        self.render(constant)
        deferred = self.derived(runs[:1], copies[:1])
        self.assertEqual(deferred["gap_density_association_statistics"][0].association_status, "insufficient_samples")
        self.render(deferred)

    def test_internal_report_modules_do_not_import_the_facade(self) -> None:
        for name in ("_report_labels.py", "_report_charts.py", "_report_markdown.py"):
            with self.subTest(module=name):
                tree = ast.parse((ROOT / "src/maxcover" / name).read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotIn(node.module, {"reporting", "maxcover.reporting"})
                        if node.module in {None, "maxcover"}:
                            self.assertNotIn("reporting", [alias.name for alias in node.names])
                    elif isinstance(node, ast.Import):
                        self.assertNotIn("maxcover.reporting", [alias.name for alias in node.names])


if __name__ == "__main__":
    unittest.main()
