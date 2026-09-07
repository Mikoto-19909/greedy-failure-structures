"""Exercise conjecture definitions, bounded completeness, and independent rejection."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]
from conjecture_spec import parse_design
from refute_conjecture import search, write_outputs
from validate_conjecture import validate_document


def design(**domain):
    return {"schema_version": 1, "name": "test_conjecture",
            "domain": {"universe_size": 4, "set_count": 3, "k": 2,
                       "set_size": 2, "unique_sets": True, **domain},
            "claim": {"min_ratio": [1, 1]}}


class ConjectureTests(unittest.TestCase):
    def test_equal_size_conjecture_has_a_known_counterexample(self):
        result = search(design())
        self.assertEqual(validate_document(result), "counterexample_found")
        self.assertEqual(result["counts"], {"candidate_space": 120, "scanned": 3,
                                          "eligible": 3, "rejected": 0})
        witness = result["counterexample"]
        self.assertEqual(witness["instance"]["sets"], [[0, 1], [0, 2], [1, 3]])
        self.assertEqual((witness["evaluation"]["greedy"], witness["evaluation"]["optimum"]), (3, 4))
        self.assertEqual(witness["evaluation"]["optimum_selected"], [1, 2])
        self.assertEqual(witness["evaluation"]["trace"][0]["ties"], [0, 1, 2])
        self.assertEqual(result, search(design()))

    def test_exhaustion_budget_and_empty_domains_are_distinct(self):
        complete = search(design(k=1))
        self.assertEqual(validate_document(complete), "domain_exhausted")
        self.assertEqual(complete["counts"], {"candidate_space": 120, "scanned": 120,
                                            "eligible": 120, "rejected": 0})
        for budget in (0, 1, 119, 120):
            cfg = design(k=1)
            cfg["search"] = {"max_instances": budget}
            result = search(cfg)
            expected = "domain_exhausted" if budget == 120 else "budget_exhausted"
            self.assertEqual(validate_document(result), expected)
            self.assertEqual(result["counts"]["scanned"], budget)
        empty = search(design(universe_size=2, set_size=2))
        self.assertEqual(validate_document(empty), "domain_exhausted")
        self.assertEqual(empty["counts"]["candidate_space"], 0)
        filtered = search(design(max_frequency=0))
        self.assertEqual(validate_document(filtered), "domain_exhausted")
        self.assertEqual(filtered["counts"]["eligible"], 0)
        self.assertEqual(filtered["counts"]["rejected"], 120)

    def test_frequency_filter_and_duplicate_policy_count_actual_candidates(self):
        cfg = design(universe_size=3, set_count=2, k=1, set_size=1,
                     unique_sets=False, max_frequency=1)
        result = search(cfg)
        self.assertEqual(validate_document(result), "domain_exhausted")
        self.assertEqual(result["counts"], {"candidate_space": 9, "scanned": 9,
                                          "eligible": 6, "rejected": 3})
        cfg["search"] = {"max_instances": 1}
        limited = search(cfg)
        self.assertEqual(validate_document(limited), "budget_exhausted")
        self.assertEqual(limited["counts"]["eligible"], 0)
        self.assertEqual(limited["counts"]["rejected"], 1)
        unrestricted = search(design(universe_size=2, set_count=2, k=1, set_size=None,
                                     unique_sets=False))
        self.assertEqual(validate_document(unrestricted), "domain_exhausted")
        self.assertEqual(unrestricted["counts"]["candidate_space"], 16)

    def test_ratio_equality_and_zero_objective_are_not_counterexamples(self):
        cfg = design()
        cfg["claim"]["min_ratio"] = [3, 4]
        result = search(cfg)
        self.assertEqual(validate_document(result), "domain_exhausted")
        cfg["claim"]["min_ratio"] = [4, 5]
        result = search(cfg)
        self.assertEqual(validate_document(result), "counterexample_found")
        zero = search(design(set_size=0, unique_sets=False))
        self.assertEqual(validate_document(zero), "domain_exhausted")
        self.assertEqual(zero["counts"]["eligible"], 1)

    def test_false_completeness_and_corrupt_witness_are_rejected(self):
        cfg = design()
        cfg["search"] = {"max_instances": 2}
        result = search(cfg)
        self.assertEqual(result["status"], "budget_exhausted")
        result["status"] = "domain_exhausted"
        with self.assertRaises(ValueError):
            validate_document(result)
        original = search(design())
        mutations = [
            lambda d: d["counterexample"]["evaluation"].update(optimum=5),
            lambda d: d["counterexample"]["evaluation"].update(optimum_selected=[0, 0]),
            lambda d: d["counterexample"].update(candidate_number=4),
            lambda d: d["counterexample"]["instance"].update(sets=[[0], [0, 2], [1, 3]]),
            lambda d: d["counts"].update(scanned=120),
            lambda d: d.update(counterexample=None),
            lambda d: d["design"]["domain"].update(max_frequency=1),
        ]
        for mutate in mutations:
            document = deepcopy(original)
            mutate(document)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_document(document)

    def test_invalid_designs_and_insufficient_reference_budget_are_rejected(self):
        mutations = [
            lambda d: d.update(schema_version=True),
            lambda d: d.update(name=""),
            lambda d: d["domain"].update(k=True),
            lambda d: d["domain"].update(k=4),
            lambda d: d["domain"].update(universe_size=13),
            lambda d: d["domain"].update(set_count=17),
            lambda d: d["domain"].update(set_size=5),
            lambda d: d["domain"].update(unique_sets=1),
            lambda d: d["domain"].update(max_frequency=-1),
            lambda d: d["domain"].update(unknown=True),
            lambda d: d["claim"].update(min_ratio=[1, 0]),
            lambda d: d["claim"].update(min_ratio=[True, 1]),
            lambda d: d["claim"].update(min_ratio=[2, 1]),
            lambda d: d["claim"].update(min_ratio=0.75),
            lambda d: d.update(search={"max_instances": -1}),
            lambda d: d.update(search={"max_combinations": 2}),
        ]
        for mutate in mutations:
            cfg = design()
            mutate(cfg)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                search(cfg)
        # A very large budget on a small finite domain must still stop at its end.
        cfg = design(k=1)
        cfg["search"] = {"max_instances": 10 ** 30}
        self.assertEqual(validate_document(search(cfg)), "domain_exhausted")
        self.assertEqual(parse_design(parse_design(design())), parse_design(design()))

    def test_cli_search_validate_replay_and_output_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, output = root / "design.json", root / "output"
            cfg.write_text(json.dumps(design()), encoding="utf-8")
            command = [sys.executable, str(ROOT / "analysis/refute_conjecture.py"),
                       "--design", str(cfg), "--output", str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = (output / "search.json").read_bytes()
            again = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)
            self.assertEqual((output / "search.json").read_bytes(), data)
            validator = [sys.executable, str(ROOT / "analysis/validate_conjecture.py"),
                         "--input", str(output / "search.json")]
            result = subprocess.run(validator, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for algorithm, coverage in (("greedy", 3), ("brute_force", 4)):
                replay = subprocess.run([sys.executable, str(ROOT / "run_project.py"), "replay",
                                         "--instance", str(output / "counterexample.json"),
                                         "--algorithm", algorithm], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(replay.returncode, 0, replay.stderr)
                self.assertIn(f"coverage={coverage}", replay.stdout)
            (output / "search.json").write_text("{}", encoding="utf-8")
            result = subprocess.run(validator, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            cfg.write_text('{"schema_version": true}', encoding="utf-8")
            command[-1] = str(root / "invalid_output")
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / "invalid_output").exists())

    def test_large_domain_and_big_integer_budget_can_stop_at_an_early_witness(self):
        cfg = design(universe_size=6, set_count=16, k=2, set_size=3, unique_sets=False)
        cfg["search"] = {"max_instances": 10 ** 30}
        result = search(cfg)
        self.assertGreater(result["counts"]["candidate_space"], sys.maxsize)
        self.assertEqual(result["counts"]["scanned"], 26)
        self.assertEqual(validate_document(result), "counterexample_found")

    def test_no_counterexample_output_is_explicit_and_rechecks_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = search(design(k=1))
            output = root / "complete"
            write_outputs(document, output)
            self.assertFalse((output / "counterexample.json").exists())
            with self.assertRaises(FileExistsError):
                write_outputs(document, output)
            document["counts"]["eligible"] = 1
            with self.assertRaises(ValueError):
                write_outputs(document, root / "invalid")
            self.assertFalse((root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
