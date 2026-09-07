"""R1c input binding, independent recomputation and confirmatory statistics."""
from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]

import r1c_confirmation as producer
import validate_r1c_confirmation as validator
from greedy_failure_paths import analyze_instance
from maxcover.benchmark import run_benchmark
from maxcover.config import load_config
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import config_hash

CONFIG = ROOT / "analysis/r1c_preflight_config.json"
HAS_SCIPY = importlib.util.find_spec("scipy") is not None


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fixture_paths(h_names, u_names):
    design = json.loads((ROOT / "analysis/r1_prefix_exchange_design.json").read_text(encoding="utf-8"))
    fixtures = {item["name"]: item for item in design["fixtures"]}
    paths = []
    for case, names in (("overlap", h_names), ("overlap_control", u_names)):
        for repetition, name in enumerate(names):
            item = fixtures[name]
            instance = MaximumCoverageInstance(item["universe_size"],
                tuple(sum(1 << e for e in group) for group in item["sets"]), item["k"])
            base = {"population": "resource_preflight", "config_hash": "functional-example",
                    "pair_id": str(repetition), "case_id": case, "repetition": repetition,
                    "seed": repetition, "instance_id": f"{case}:{repetition}",
                    "greedy_run_id": f"g:{case}:{repetition}", "exact_run_id": f"o:{case}:{repetition}"}
            paths.append({**base, **analyze_instance(instance)})
    return paths


class R1cInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.original = Path(cls.temporary.name) / "benchmark"
        run_benchmark(CONFIG, cls.original, workers=1)

    def setUp(self):
        self.working = tempfile.TemporaryDirectory()
        self.addCleanup(self.working.cleanup)
        self.directory = Path(self.working.name)
        self.source = self.directory / "source"
        self.source.mkdir()
        for name in ("instances.csv", "raw_results.csv"):
            (self.source / name).write_bytes((self.original / name).read_bytes())

    def assert_bad_source(self):
        for function in (producer.load_inputs, validator.inputs):
            with self.subTest(function=function.__module__), self.assertRaises((ValueError, KeyError)):
                function(CONFIG, self.source)

    def test_complete_preflight_binds_pairs_and_run_ids(self):
        entries = producer.load_inputs(CONFIG, self.source)
        bases = validator.inputs(CONFIG, self.source)
        self.assertEqual([base for base, _ in entries], bases)
        self.assertEqual(len(entries), 64)
        self.assertEqual(len({base["pair_id"] for base in bases}), 32)
        self.assertEqual({base["population"] for base in bases}, {"resource_preflight"})
        self.assertEqual(len({base[field] for base in bases for field in ("greedy_run_id", "exact_run_id")}), 128)

    def test_formal_identity_is_recognized_without_materializing_samples(self):
        identifier = config_hash(load_config(ROOT / "analysis/r1c_confirmation_config.json"))
        self.assertEqual(producer.PROFILES[identifier], "confirmation")
        self.assertEqual(validator.PROFILES[identifier], "confirmation")

    def test_changed_configuration_is_rejected_before_generation(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["repetitions"] = 1
        path = self.directory / "changed.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        for module, function in ((producer, producer.load_inputs), (validator, validator.inputs)):
            with patch.object(module, "_instances_for_config", side_effect=AssertionError("must reject first")):
                with self.assertRaises(ValueError):
                    function(path, self.source)

    def test_missing_or_duplicate_instance_cannot_shrink_the_sample(self):
        path = self.source / "instances.csv"
        original = read_csv(path)
        for changed in (original[:-1], [original[0], *original[:-1]]):
            write_csv(path, changed)
            self.assert_bad_source()

    def test_invalid_cli_inputs_report_failure_without_a_traceback(self):
        for module in (producer, validator):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = module.main(["--config", str(self.directory / "missing.json"),
                                    "--results", str(self.source), "--output", str(self.directory / "absent")])
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse((self.directory / "absent").exists())

    def test_run_id_seed_options_and_reference_state_are_bound(self):
        path = self.source / "raw_results.csv"
        original = read_csv(path)
        mutations = (
            (0, "run_id", "unplanned"), (0, "seed", "42"),
            (0, "algorithm_options", '{"time_limit_seconds":0.001}'), (0, "selected", ""),
            (0, "config_hash", "wrong"), (0, "error_message", "failed"),
        )
        for index, field, value in mutations:
            with self.subTest(field=field):
                rows = copy.deepcopy(original)
                rows[index][field] = value
                write_csv(path, rows)
                self.assert_bad_source()
        for rows in (original[:-1], [original[0], *original[:-1]]):
            write_csv(path, rows)
            self.assert_bad_source()
        rows = copy.deepcopy(original)
        exact = next(row for row in rows if row["algorithm_id"] == "exact_reference")
        exact.update(status="feasible", is_exact="False", optimum="", optimality_gap="")
        write_csv(path, rows)
        self.assert_bad_source()

    @unittest.skipUnless(HAS_SCIPY, "R1c statistics require the offline SciPy dependency")
    def test_valid_chain_and_invalid_outputs(self):
        output = self.directory / "analysis"
        self.assertEqual(producer.run(CONFIG, self.source, output), 64)
        self.assertEqual(validator.validate(CONFIG, self.source, output), 64)
        for filename, field, value in (("instance_summary.csv", "F", "9"),
                                      ("group_summary.csv", "M", "999"),
                                      ("primary_summary.csv", "lower", "nan"),
                                      ("primary_summary.csv", "direction", "fabricated")):
            path = output / filename
            saved = path.read_bytes()
            rows = read_csv(path)
            rows[0][field] = value
            write_csv(path, rows)
            with self.subTest(filename=filename, field=field), self.assertRaises(ValueError):
                validator.validate(CONFIG, self.source, output)
            path.write_bytes(saved)
        path = output / "paths.jsonl"
        saved = path.read_bytes()
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["ties"].pop()
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with self.assertRaises(ValueError):
            validator.validate(CONFIG, self.source, output)
        path.write_bytes(saved)
        # The verifier never calls the producer's trajectory or statistical functions.
        with patch.object(producer, "analyze_instance", side_effect=AssertionError), patch.object(producer, "summarize", side_effect=AssertionError):
            self.assertEqual(validator.validate(CONFIG, self.source, output), 64)
        with self.assertRaises(ValueError):
            producer.run(CONFIG, self.source, output)
        self.assertEqual(path.read_bytes(), saved)

    def test_false_greedy_optimal_status_and_bound_are_rejected(self):
        path = self.source / "raw_results.csv"
        original = read_csv(path)
        for false_status in (False, True):
            rows = copy.deepcopy(original)
            row = next(row for row in rows if row["algorithm_id"] == "greedy" and int(row["coverage"]) < int(row["optimum"]))
            row["best_bound"] = row["coverage"]
            if false_status:
                row.update(status="optimal", is_exact="True")
            write_csv(path, rows)
            self.assert_bad_source()

    @unittest.skipUnless(HAS_SCIPY, "R1c statistics require the offline SciPy dependency")
    def test_partial_budget_or_failed_verification_never_publishes_output(self):
        output = self.directory / "unpublished"
        with patch.object(producer, "BUDGETS", {"max_completions": 200000, "max_two_swap_evaluations": 0}):
            with self.assertRaises(ValueError):
                producer.run(CONFIG, self.source, output)
        self.assertFalse(output.exists())
        with patch.object(validator, "validate", side_effect=ValueError("independent rejection")):
            with self.assertRaises(ValueError):
                producer.run(CONFIG, self.source, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.directory.glob(".r1c-*")), [])

    @unittest.skipUnless(HAS_SCIPY, "R1c statistics require the offline SciPy dependency")
    def test_self_consistent_but_false_optimum_is_rejected_by_enumeration(self):
        path = self.source / "raw_results.csv"
        rows = read_csv(path)
        g = next(row for row in rows if row["algorithm_id"] == "greedy" and int(row["coverage"]) < int(row["optimum"]))
        exact = next(row for row in rows if row["instance_id"] == g["instance_id"] and row["algorithm_id"] == "exact_reference")
        exact.update(selected=g["selected"], coverage=g["coverage"], best_bound=g["coverage"], optimum=g["coverage"], optimality_gap="0")
        g.update(optimum=g["coverage"], optimality_gap="0")
        write_csv(path, rows)
        # Input feasibility alone is not a proof of optimality.
        producer.load_inputs(CONFIG, self.source)
        output = self.directory / "false-reference"
        with self.assertRaises(ValueError):
            producer.run(CONFIG, self.source, output)
        self.assertFalse(output.exists())


@unittest.skipUnless(HAS_SCIPY, "R1c statistics require the offline SciPy dependency")
class R1cStatisticsTests(unittest.TestCase):
    def test_zero_failure_denominators_are_not_zero_estimates(self):
        paths = fixture_paths(["multiple_optima"], ["multiple_optima"])
        _, groups, primary = producer.summarize(paths)
        self.assertTrue(all(group["theta"] is None for group in groups))
        self.assertEqual((primary["lower"], primary["upper"]), (-1.0, 1.0))
        self.assertIsNone(primary["delta"])
        self.assertEqual(primary["direction"], "not_estimable")
        self.assertFalse(primary["precision_met"])

    def test_zero_and_all_events_have_exact_boundary_intervals(self):
        paths = fixture_paths(["avoidable_tie"] * 8, ["unique_bait"] * 8)
        _, (h, u), primary = producer.summarize(paths)
        boundary = 0.0125 ** (1 / 8)
        self.assertAlmostEqual(h["theta_lower"], boundary, places=12)
        self.assertEqual(h["theta_upper"], 1)
        self.assertEqual(u["theta_lower"], 0)
        self.assertAlmostEqual(u["theta_upper"], 1 - boundary, places=12)
        self.assertEqual(primary["delta"], 1)

    def test_gap_denominator_and_recovery_keep_successes_and_zero_optima_distinct(self):
        paths = fixture_paths(["zero_objective", "multiple_optima", "avoidable_tie"],
                              ["zero_objective", "multiple_optima", "unique_bait"])
        rows, groups, primary = producer.summarize(paths)
        for group in groups:
            self.assertEqual((group["N"], group["M"], group["zero_optimum_n"], group["gap_defined_n"]), (3, 1, 1, 2))
            self.assertEqual(group["one_swap_recovery_rate"], 1)
        self.assertAlmostEqual(groups[0]["mean_greedy_gap"], 0.125)
        self.assertEqual(sum(row["missing_reason"] != "" for row in rows), 2)
        expected = validator.summaries(paths)
        for actual_group, expected_group in zip(groups, expected[1]):
            for key in actual_group:
                if isinstance(actual_group[key], float):
                    self.assertAlmostEqual(actual_group[key], expected_group[key], places=10)
                else:
                    self.assertEqual(actual_group[key], expected_group[key])
        self.assertEqual(primary["direction"], expected[2]["direction"])

    def test_direction_and_precision_are_distinct_outputs(self):
        paths = fixture_paths(["avoidable_tie"] * 8, ["unique_bait"] * 8)
        primary = producer.summarize(paths)[2]
        self.assertEqual(primary["direction"], "higher")
        self.assertFalse(primary["precision_met"])
        for path in paths:
            path["case_id"] = "overlap_control" if path["case_id"] == "overlap" else "overlap"
        self.assertEqual(producer.summarize(paths)[2]["direction"], "lower")


if __name__ == "__main__":
    unittest.main()
