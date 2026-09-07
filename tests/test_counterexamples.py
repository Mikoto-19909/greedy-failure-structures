"""Known answers, independent reduction checks, and invalid-state rejection."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]
from mine_counterexamples import deletions, evaluate, mine, read_inputs, shrink, write_outputs
from validate_counterexamples import validate_document
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_payload, load_instance


def bait():
    return MaximumCoverageInstance(8, (0b01110111, 0b00001111, 0b11110000), 2)


def make_document(directory, instances=None, **options):
    path = Path(directory) / "input.jsonl"
    instances = [bait()] if instances is None else instances
    path.write_text("".join(json.dumps({**instance_payload(x), "case_id": str(i)}) + "\n"
                            for i, x in enumerate(instances)), encoding="utf-8")
    return mine(path, **options)


class CounterexampleTests(unittest.TestCase):
    def test_known_answer_and_independent_reduction(self):
        result = evaluate(bait(), 100)
        self.assertEqual((result["greedy"], result["optimum"]), (7, 8))
        self.assertEqual(result["optimum_selected"], [1, 2])
        self.assertEqual(result["trace"][0]["ties"], [0])
        with tempfile.TemporaryDirectory() as directory:
            document = make_document(directory)
            validate_document(document)
            item = document["selected"][0]
            self.assertEqual(item["status"], "deletion_minimal")
            self.assertLess(item["instance"]["universe_size"], 8)
            self.assertEqual(item["instance"]["k"], 2)
            self.assertTrue(item["steps"])
            self.assertEqual(document, make_document(directory))

    def test_budget_exhaustion_never_claims_minimality(self):
        for budget in (0, 1, 3):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as directory:
                document = make_document(directory, max_evaluations=budget)
                validate_document(document)
                item = document["selected"][0]
                self.assertEqual(item["status"], "budget_exhausted")
                self.assertEqual(item["evaluations"], budget)
        with tempfile.TemporaryDirectory() as directory:
            document = make_document(directory, max_evaluations=0)
            document["selected"][0]["status"] = "deletion_minimal"
            with self.assertRaisesRegex(ValueError, "false deletion-minimal"):
                validate_document(document)

    def test_false_optimum_and_incomplete_results_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            original = make_document(directory)
            for target in ("inputs", "selected"):
                document = deepcopy(original)
                document[target][0]["evaluation"]["optimum"] += 1
                with self.subTest(target=target), self.assertRaises(ValueError):
                    validate_document(document)
            document = deepcopy(original)
            document["selected"] = []
            with self.assertRaises(ValueError):
                validate_document(document)
            document = deepcopy(original)
            document["selected"][0]["steps"] = []
            with self.assertRaisesRegex(ValueError, "deletion replay"):
                validate_document(document)
            document = deepcopy(original)
            document["inputs"][0]["evaluation"]["optimum_selected"] = [0, 0]
            with self.assertRaises(ValueError):
                validate_document(document)

    def test_limits_nonfailures_and_zero_objective(self):
        zero = MaximumCoverageInstance(2, (0, 0), 1)
        optimal = MaximumCoverageInstance(2, (1, 2), 1)
        with tempfile.TemporaryDirectory() as directory:
            document = make_document(directory, [bait(), zero, optimal], max_combinations=2)
            validate_document(document)
            self.assertEqual(document["counts"], {"input": 3, "exact": 2, "failures": 0, "selected": 0})
            self.assertEqual(document["inputs"][0]["evaluation"]["status"], "combination_limit")
            self.assertIsNone(document["inputs"][1]["evaluation"]["gap"])
        with self.assertRaises(ValueError):
            shrink(zero, evaluate(zero, 10), max_combinations=10, max_evaluations=10)

    def test_ranking_uses_original_gap_then_size_and_input_order(self):
        # Tied first choices: 6/8, worse than the unique bait's 7/8.
        worse = MaximumCoverageInstance(8, (0b00110011, 0b00001111, 0b11110000), 2)
        with tempfile.TemporaryDirectory() as directory:
            document = make_document(directory, [bait(), worse, worse], top=2, max_evaluations=0)
            validate_document(document)
            self.assertEqual([s["input_index"] for s in document["selected"]], [1, 2])

    def test_input_variants_and_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            payload = instance_payload(bait())
            for value in (payload, {"instance": payload},
                          {k: payload[k] for k in ("universe_size", "sets", "k")},
                          instance_payload(bait(), encoding="bitsets")):
                path.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(read_inputs(path)[0]["instance"]["sets"], payload["sets"])
            for value in ([payload], {**payload, "k": True}, {**payload, "k": 0},
                          {**payload, "k": 4}, {**payload, "sets": [[8]]},
                          {**payload, "sets": [[-1]]}):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(ValueError):
                    read_inputs(path)
            empty = Path(directory) / "empty.jsonl"
            empty.write_text("\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                mine(empty)
            for options in ({"top": 0}, {"max_combinations": 0}, {"max_evaluations": -1}):
                with self.assertRaises(ValueError):
                    mine(path, **options)

    def test_deletions_preserve_index_order_and_fix_k(self):
        instance = MaximumCoverageInstance(4, (9, 6, 3), 2)
        candidates = list(deletions(instance))
        self.assertEqual(candidates[1][1].sets, (9, 3))
        # Delete element 1: original 3 becomes 2, original 2 becomes 1.
        element = next(x for op, x in candidates if op == {"kind": "element", "index": 1})
        self.assertEqual(element.sets, (5, 2, 1))
        self.assertTrue(all(x.k == 2 for _, x in candidates))

    def test_saved_scores_are_recomputed_and_outputs_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {**instance_payload(bait()), "optimum": 999, "greedy_selected": [2, 1]}
            path = root / "source.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            document = mine(path)
            self.assertEqual(document["inputs"][0]["evaluation"]["optimum"], 8)
            output = root / "output"
            write_outputs(document, output)
            restored, _ = load_instance(output / "counterexample_001.json")
            result = evaluate(restored, 100)
            self.assertLess(result["greedy"], result["optimum"])
            with self.assertRaises(FileExistsError):
                write_outputs(document, output)
            validated = subprocess.run([sys.executable, str(ROOT / "analysis/validate_counterexamples.py"),
                                        "--input", str(output / "counterexamples.json")],
                                       capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            replay = subprocess.run([sys.executable, str(ROOT / "run_project.py"), "replay",
                                     "--instance", str(output / "counterexample_001.json"), "--algorithm", "greedy"],
                                    capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            broken = root / "broken.json"
            broken.write_text('{"schema_version": 1}', encoding="utf-8")
            invalid = subprocess.run([sys.executable, str(ROOT / "analysis/validate_counterexamples.py"),
                                      "--input", str(broken)], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()
