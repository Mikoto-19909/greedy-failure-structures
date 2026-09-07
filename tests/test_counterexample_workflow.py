"""Exercise user-facing experiment commands and their data/verification boundaries."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]
import counterexample_workflow as workflow
from mine_counterexamples import mine
from validate_counterexamples import validate_document


def invoke(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = workflow.main(list(arguments))
        except SystemExit as error:
            code = error.code
    return code, stdout.getvalue(), stderr.getvalue()


def input_file(root):
    path = root / "instances with spaces.jsonl"
    base = {"universe_size": 4, "sets": [[0, 1], [0, 2], [1, 3]], "k": 2}
    path.write_text("\n".join(json.dumps({**base, "population": population})
                              for population in ("pilot", "fixture")) + "\n", encoding="utf-8")
    return path


class CounterexampleWorkflowTests(unittest.TestCase):
    def test_default_mining_excludes_fixtures_and_verifies_selected_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pilot"
            code, _, error = invoke("mine", "--output", str(output), "--max-evaluations", "0")
            self.assertEqual(code, 0, error)
            document = json.loads((output / "counterexamples.json").read_text(encoding="utf-8"))
            self.assertEqual(document["counts"], {"input": 60, "exact": 60, "failures": 22, "selected": 5})
            self.assertEqual(document["settings"]["population"], "pilot")
            self.assertEqual({entry["source"]["population"] for entry in document["inputs"]}, {"pilot"})
            validate_document(document)

    def test_population_filter_preserves_old_defaults_and_rejects_false_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = input_file(root)
            old = mine(source, max_evaluations=0)
            self.assertEqual(old["counts"]["input"], 2)
            self.assertNotIn("population", old["settings"])
            selected = mine(source, max_evaluations=0, population="fixture")
            self.assertEqual(selected["counts"]["input"], 1)
            validate_document(selected)
            corrupt = deepcopy(selected)
            corrupt["settings"]["population"] = "pilot"
            with self.assertRaises(ValueError):
                validate_document(corrupt)
            code, _, _ = invoke("mine", "--input", str(source), "--population", "typo",
                                "--output", str(root / "invalid"))
            self.assertEqual(code, 2)
            self.assertFalse((root / "invalid").exists())

    def test_automatic_output_creates_new_runs_and_explicit_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = input_file(root)
            with patch.object(workflow, "ROOT", root):
                for _ in range(2):
                    code, _, error = invoke("mine", "--input", str(source), "--top", "1",
                                            "--max-evaluations", "0")
                    self.assertEqual(code, 0, error)
            directories = list((root / "results/counterexamples").iterdir())
            self.assertEqual(len(directories), 2)
            self.assertEqual((directories[0] / "counterexamples.json").read_bytes(),
                             (directories[1] / "counterexamples.json").read_bytes())
            before = (directories[0] / "counterexamples.json").read_bytes()
            code, _, _ = invoke("mine", "--input", str(source), "--output", str(directories[0]))
            self.assertEqual(code, 2)
            self.assertEqual((directories[0] / "counterexamples.json").read_bytes(), before)

    def test_design_refute_overrides_and_show_work_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design = root / "my guess.json"
            code, _, error = invoke("design", str(design), "--ratio", "0.8")
            self.assertEqual(code, 0, error)
            original = design.read_bytes()
            self.assertEqual(json.loads(original)["claim"]["min_ratio"], [4, 5])
            code, _, _ = invoke("design", str(design), "--ratio", "1")
            self.assertEqual(code, 2)
            self.assertEqual(design.read_bytes(), original)
            for label, options, status in (
                ("found", [], "counterexample_found"),
                ("complete", ["--ratio", "3/4"], "domain_exhausted"),
                ("unfinished", ["--budget", "2"], "budget_exhausted"),
            ):
                output = root / label
                code, _, error = invoke("refute", "--design", str(design), "--output", str(output), *options)
                self.assertEqual(code, 0, error)
                document = json.loads((output / "search.json").read_text(encoding="utf-8"))
                self.assertEqual(document["status"], status)
                self.assertEqual(json.loads((output / "design.json").read_text(encoding="utf-8")), document["design"])
                self.assertEqual(design.read_bytes(), original)
                self.assertEqual(invoke("show", str(output))[0], 0)
            corrupted = root / "found/search.json"
            document = json.loads(corrupted.read_text(encoding="utf-8"))
            document["counterexample"]["evaluation"]["optimum"] += 1
            corrupted.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(invoke("show", str(corrupted))[0], 2)

    def test_invalid_parameters_and_ambiguous_results_fail_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for options in (["--n", "0"], ["--ratio", "4/0"], ["--ratio", "1.1"],
                            ["--size", "wrong"], ["--size", "8"]):
                target = root / "new/design.json"
                self.assertEqual(invoke("design", str(target), *options)[0], 2)
                self.assertFalse(target.exists())
            self.assertFalse((root / "new").exists())
            for name in ("counterexamples.json", "search.json"):
                (root / name).write_text("{}", encoding="utf-8")
            self.assertEqual(invoke("show", str(root))[0], 2)
            self.assertEqual(invoke("show", str(root), "--rank", "0")[0], 2)

    def test_python_launcher_works_from_another_directory_with_spaced_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "nested folder/guess.json"
            command = [sys.executable, str(ROOT / "counterexamples.py"), "design", str(target),
                       "--size", "any", "--allow-duplicates", "--ratio", "3/4"]
            result = subprocess.run(command, cwd=root, capture_output=True, encoding="utf-8",
                                    env={**os.environ, "PYTHONUTF8": "1"})
            self.assertEqual(result.returncode, 0, result.stderr)
            design = json.loads(target.read_text(encoding="utf-8"))
            self.assertIsNone(design["domain"]["set_size"])
            self.assertFalse(design["domain"]["unique_sets"])


if __name__ == "__main__":
    unittest.main()
