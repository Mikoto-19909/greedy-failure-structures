"""Known R3 witnesses, strict degree preservation, first-step semantics and search limits."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]
from maxcover.model import MaximumCoverageInstance
from r3_counterexamples import evaluate_r3, load_source, search_pair, switches, write_outputs
from validate_r3_counterexamples import validate_document


def example():
    return load_source(ROOT / "designs/r3_pair_example.json")[0]


def from_sets(n, sets, k):
    return MaximumCoverageInstance(n, tuple(sum(1 << a for a in s) for s in sets), k)


class R3CounterexampleTests(unittest.TestCase):
    def test_same_e0_pair_has_equal_degrees_and_opposite_first_step_outcomes(self):
        document = search_pair(example(), {}, same_optimum=True)
        self.assertEqual(validate_document(document), "pair_found")
        before, after = document["original"]["evaluation"], document["pair"]["evaluation"]
        for field in ("row_degrees", "element_frequencies", "global_intersection_total", "e0", "optimum"):
            self.assertEqual(before[field], after[field])
        self.assertEqual((before["e0"], before["optimum"], before["forced_optimum"]), (2, 4, 3))
        self.assertEqual((after["e0"], after["optimum"], after["forced_optimum"]), (2, 4, 4))
        self.assertEqual(document["counts"], {"states": 5, "switches": 4})
        self.assertEqual(document["pair"]["switches"], [[1, 2, 0, 3]])
        self.assertEqual((before["unique_set_count"], after["unique_set_count"]), (3, 2))
        self.assertEqual(document, search_pair(example(), {}, same_optimum=True))

    def test_lower_e0_can_have_worse_first_step_with_the_same_optimum(self):
        instance, source = load_source(ROOT / "designs/r3_lower_e0_example.json")
        document = search_pair(instance, source, target="lower-e0-worse", same_optimum=True)
        self.assertEqual(validate_document(document), "pair_found")
        before, after = document["original"]["evaluation"], document["pair"]["evaluation"]
        self.assertEqual((before["e0"], before["optimum"], before["forced_optimum"]), (5, 8, 8))
        self.assertEqual((after["e0"], after["optimum"], after["forced_optimum"]), (4, 8, 7))
        self.assertEqual(document["counts"], {"states": 93, "switches": 98})
        self.assertEqual(len(document["pair"]["switches"]), 2)

    def test_recoverable_first_step_is_not_final_greedy_success(self):
        instance = from_sets(8, [[4, 5, 7], [1, 2, 5], [1, 6, 7], [2, 5, 7], [0, 2, 4]], 3)
        result = evaluate_r3(instance, 100)
        self.assertEqual((result["greedy"], result["optimum"], result["forced_optimum"]), (6, 7, 7))
        self.assertFalse(result["first_step_irrecoverable"])
        self.assertTrue(result["final_failure"])
        self.assertTrue(result["late_failure"])
        document = search_pair(instance, {}, max_switches=0)
        self.assertEqual(validate_document(document), "switch_budget_exhausted")

    def test_budget_boundaries_and_no_legal_switch_never_make_false_claims(self):
        for options, status, counts in (
            ({"max_states": 1}, "state_budget_exhausted", {"states": 1, "switches": 1}),
            ({"max_switches": 0}, "switch_budget_exhausted", {"states": 1, "switches": 0}),
            ({"max_switches": 3}, "switch_budget_exhausted", {"states": 4, "switches": 3}),
            ({"max_states": 5, "max_switches": 4}, "pair_found", {"states": 5, "switches": 4}),
        ):
            with self.subTest(options=options):
                document = search_pair(example(), {}, **options)
                self.assertEqual(validate_document(document), status)
                self.assertEqual(document["counts"], counts)
        no_moves = from_sets(3, [[0, 1, 2], [0, 1, 2]], 1)
        document = search_pair(no_moves, {}, max_states=1, max_switches=0)
        self.assertEqual(validate_document(document), "component_exhausted")
        self.assertEqual(document["counts"], {"states": 1, "switches": 0})
        for k in (1, 3):
            instance = MaximumCoverageInstance(4, example().sets, k)
            document = search_pair(instance, {})
            self.assertEqual(validate_document(document), "component_exhausted")
            self.assertIsNone(document["pair"])
        zero = search_pair(MaximumCoverageInstance(2, (0, 0), 1), {})
        self.assertEqual(validate_document(zero), "component_exhausted")
        self.assertEqual(zero["original"]["evaluation"]["forced_optimum"], 0)

    def test_regular_element_frequencies_keep_e0_fixed_under_switches(self):
        instance = from_sets(4, [[0, 1], [1, 2], [2, 3], [0, 3]], 2)
        original = evaluate_r3(instance, 100)
        self.assertEqual(original["element_frequencies"], [2, 2, 2, 2])
        for _, masks in switches(instance.sets, 4):
            current = evaluate_r3(MaximumCoverageInstance(4, masks, 2), 100)
            self.assertEqual(current["e0"], original["e0"])
        document = search_pair(instance, {}, target="lower-e0-worse")
        self.assertEqual(validate_document(document), "component_exhausted")

    def test_bad_degrees_forced_optimum_paths_and_false_completion_are_rejected(self):
        original = search_pair(example(), {})
        edits = [
            lambda d: d["pair"]["instance"]["sets"][0].append(2),
            lambda d: d["pair"]["evaluation"].update(forced_optimum=3),
            lambda d: d["pair"]["evaluation"].update(forced_selected=[0, 0]),
            lambda d: d["original"]["evaluation"].update(e0=99),
            lambda d: d["pair"].update(switches=[[0, 0, 1, 2]]),
            lambda d: d["counts"].update(states=6),
            lambda d: d.update(pair=None),
            lambda d: d["pair"]["evaluation"].update(first_step_irrecoverable=True),
        ]
        for edit in edits:
            document = deepcopy(original)
            edit(document)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                validate_document(document)
        incomplete = search_pair(example(), {}, max_switches=0)
        incomplete["status"] = "component_exhausted"
        with self.assertRaises(ValueError):
            validate_document(incomplete)

    def test_verifier_does_not_use_producer_computations(self):
        document = search_pair(example(), {})
        with patch("r3_counterexamples.search_pair", side_effect=AssertionError), \
             patch("r3_counterexamples.evaluate_r3", side_effect=AssertionError), \
             patch("r3_counterexamples.switches", side_effect=AssertionError), \
             patch("r3_counterexamples.matches", side_effect=AssertionError):
            self.assertEqual(validate_document(document), "pair_found")

    def test_input_adapters_require_explicit_k_for_r2_graphs_and_preserve_line_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "graph.json"
            graph = {"task": {"n": 4, "budgets": [1, 2, 3], "seed": 37},
                     "sets": [[0, 1], [0, 2], [1, 3]], "values": [{"optimum": 999}]}
            path.write_text(json.dumps(graph), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_source(path)
            instance, source = load_source(path, k=2)
            self.assertEqual(instance.sets, example().sets)
            self.assertEqual(source["task"]["seed"], 37)
            self.assertEqual(evaluate_r3(instance, 100)["optimum"], 4)
            lines = root / "records.jsonl"
            lines.write_text("\n" + json.dumps({"instance": {"universe_size": 4, "sets": graph["sets"], "k": 2}})
                             + "\n", encoding="utf-8")
            _, source = load_source(lines, record=2)
            self.assertEqual(source["record"], 2)
            for number in (0, 1, 3):
                with self.assertRaises(ValueError):
                    load_source(lines, record=number)
            with self.assertRaises(ValueError):
                load_source(path, record=2, k=2)

    def test_invalid_dimensions_settings_and_reference_limits_fail(self):
        for options in ({"max_states": 0}, {"max_switches": -1}, {"max_states": True},
                        {"max_combinations": 2}, {"target": "unknown"}, {"same_optimum": 1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                search_pair(example(), {}, **options)
        for instance in (MaximumCoverageInstance(4, (1, 3), 1),
                         MaximumCoverageInstance(65, (1,), 1),
                         MaximumCoverageInstance(2, (1,) * 33, 1)):
            with self.assertRaises(ValueError):
                search_pair(instance, {})

    def test_cli_output_show_and_independent_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "R3 pair"
            launcher = [sys.executable, str(ROOT / "counterexamples.py")]
            command = [*launcher, "r3-pair", "--same-optimum", "--output", str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads((output / "pair.json").read_text(encoding="utf-8"))
            self.assertEqual(validate_document(document), "pair_found")
            before = (output / "pair.json").read_bytes()
            result = subprocess.run(command, cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual((output / "pair.json").read_bytes(), before)
            result = subprocess.run([*launcher, "show", str(output)], cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("original.json", "counterexample.json"):
                result = subprocess.run([sys.executable, str(ROOT / "run_project.py"), "replay",
                                         "--instance", str(output / name), "--algorithm", "brute_force"],
                                        cwd=ROOT, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            document["pair"]["switches"] = []
            (output / "pair.json").write_text(json.dumps(document), encoding="utf-8")
            result = subprocess.run([*launcher, "show", str(output)], cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 2)
            with self.assertRaises(ValueError):
                write_outputs(document, root / "invalid")
            self.assertFalse((root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
