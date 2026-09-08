from __future__ import annotations

import copy
from itertools import product
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from r2_design import make_design, write_json, read_json
from r2_budget_grid import evaluate_task
from r4_inputs import configuration, validate_configuration, source_record
from r4_prefix_bounds import certificates, evaluate, run, analyze, summarize, main, freeze
from validate_r4_prefix_bounds import verify_record, verify_certificate, validate_batch, verify_summaries, main as validator_main


def fixture(directory, count=2):
    source = Path(directory) / "source"
    design = make_design("fixture", (6,), (2,), count, 0)
    write_json(source / "config.json", design)
    for task in design["tasks"]:
        write_json(source / "graphs" / (task["base_graph_id"] + ".json"), evaluate_task(task, design["diagnostics"]))
    return source, configuration("fixture", design)


class R4PrefixTests(unittest.TestCase):
    def test_known_bounds_failed_prefix_endpoints_and_zero_union(self):
        masks = (7, 25, 38)  # S0={0,1,2}, S1={0,3,4}, S2={1,2,5}
        values = certificates(masks, [1, 2, 3])
        middle = values[1]
        self.assertEqual((middle["path"], middle["greedy"], middle["upper"]), ([0, 1], 5, 6))
        p = middle["prefixes"][1]
        self.assertEqual(p["coverage"] + (2 - 1) * p["max_gain"], 5)
        self.assertEqual(middle["prefixes"][-1]["max_gain"], 1)
        for v in (values[0], values[-1]):
            self.assertEqual(v["upper"], v["greedy"])
        self.assertIsNone(values[-1]["prefixes"][-1]["gain_witness"])
        zero = certificates((0, 0, 0), [1, 2, 3])
        self.assertEqual(zero[-1]["path"], [0, 1, 2])
        self.assertTrue(all(v["upper"] == v["greedy"] == 0 for v in zero))
        for budgets in ([0], [4], [2, 1], [1, 1], [True]):
            with self.subTest(budgets=budgets), self.assertRaises(ValueError):
                certificates(masks, budgets)

    def test_all_small_set_systems_match_reference_and_certification_limit(self):
        from itertools import combinations
        for masks in product(range(8), repeat=3):
            sets = [{a for a in range(3) if mask & (1 << a)} for mask in masks]
            for v in certificates(masks, [1, 2, 3]):
                optimum = max(len(set().union(*(sets[i] for i in chosen))) for chosen in combinations(range(3), v["k"]))
                self.assertLessEqual(v["greedy"], optimum)
                self.assertLessEqual(optimum, v["upper"])
                self.assertLessEqual(v["upper"], v["initial_upper"])
                self.assertEqual(v["upper"] == v["greedy"], v["initial_upper"] == v["greedy"])

    def test_independent_validation_rejects_bounds_references_sources_and_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory)
            task = config["tasks"][0]
            original = source_record(source, task)
            row = evaluate(source, task, config)
            timing = verify_record(row, original, config)
            self.assertIn("certificate_seconds", timing)
            self.assertIn("reference_seconds", timing)
            for change in ("gain", "bound", "path", "prefix", "budgets", "status", "source", "optimum", "witness"):
                bad = copy.deepcopy(row)
                if change == "gain": bad["values"][0]["prefixes"][-1]["max_gain"] += 1
                elif change == "bound": bad["values"][0]["upper"] += 1
                elif change == "path": bad["values"][-1]["path"].reverse()
                elif change == "prefix": bad["values"][-1]["prefixes"].pop()
                elif change == "budgets": bad["values"].pop()
                elif change == "status": bad["status"] = "incomplete"
                elif change == "source": bad["source_commit"] = "wrong"
                elif change == "optimum": bad["source"]["values"][0]["optimum"] += 1
                else: bad["source"]["values"][-1]["optimum_selected"].reverse()
                with self.subTest(change=change), self.assertRaises(ValueError):
                    verify_record(bad, original, config)
            # Even a coherently altered reference in both copies must be recomputed.
            bad = copy.deepcopy(row)
            bad["source"]["values"][0]["optimum"] += 1
            with self.assertRaisesRegex(ValueError, "exhaustive optimum"):
                verify_record(bad, bad["source"], config)
            duplicate = copy.deepcopy(row)
            duplicate["source"]["values"][-1]["optimum_selected"].reverse()
            with self.assertRaisesRegex(ValueError, "canonical witness"):
                verify_record(duplicate, duplicate["source"], config)

    def test_resume_rebuild_and_stale_pass_cannot_authorize_changed_data(self):
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory, 3)
            output = Path(directory) / "output"
            self.assertFalse(run(config, source, output, stop_after=1)["complete"])
            with self.assertRaises(ValueError): validate_batch(output, source)
            checkpoint = output / "graphs" / (config["tasks"][0]["base_graph_id"] + ".json")
            before = checkpoint.read_bytes()
            self.assertEqual(run(config, source, output, resume=True)["computed"], 2)
            self.assertEqual(checkpoint.read_bytes(), before)
            validate_batch(output, source)
            analyze(output, source)
            verify_summaries(output)
            summary = (output / "cell_summary.csv").read_bytes()
            with patch("r4_prefix_bounds.evaluate", side_effect=AssertionError("no production")):
                analyze(output, source)
            self.assertEqual((output / "cell_summary.csv").read_bytes(), summary)
            bad = read_json(checkpoint)
            bad["values"][0]["upper"] += 1
            write_json(checkpoint, bad)
            with self.assertRaises(ValueError): analyze(output, source)
            self.assertEqual((output / "cell_summary.csv").read_bytes(), summary)
            with self.assertRaises(ValueError): run(config, source, output, resume=True)

    def test_metrics_zero_denominators_and_paired_budget_grouping(self):
        records = [{"task": {"base_graph_id": "zero", "n": 3, "d": 0},
                    "values": certificates((0, 0, 0), [1, 2, 3]),
                    "source": {"values": [{"optimum": 0}] * 3}}]
        rows, cells = summarize(records)
        self.assertTrue(all(r["certified_optimal"] == 1 and r["certified_ratio"] is None for r in rows))
        self.assertTrue(all(c["upper_over_optimum_missing"] == 1 for c in cells))
        self.assertEqual([c["count"] for c in cells], [1, 1, 1])

    def test_cli_valid_invalid_and_resource_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory)
            output = Path(directory) / "output"
            run(config, source, output)
            self.assertIsNone(validator_main(["--source", str(source), "--output", str(output)]))
            self.assertIsNone(main(["analyze", "--source", str(source), "--output", str(output)]))
            with self.assertRaises(SystemExit):
                main(["run", "--source", str(source), "--output", str(output)])
            path = output / "graphs" / (config["tasks"][0]["base_graph_id"] + ".json")
            damaged = read_json(path)
            damaged["values"].pop()
            write_json(path, damaged)
            with self.assertRaises(SystemExit):
                validator_main(["--source", str(source), "--output", str(output)])
            second = Path(directory) / "interrupted"
            with patch("r4_prefix_bounds.check_resources", side_effect=RuntimeError("resource exhausted")):
                with self.assertRaises(RuntimeError): run(config, source, second)
            self.assertEqual(list((second / "graphs").glob("*.json")), [])

    def test_f4_requires_independent_preflight_and_fixed_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory)
            output = Path(directory) / "output"
            run(config, source, output)
            with self.assertRaisesRegex(ValueError, "18 independent"):
                freeze(output, source, Path(directory) / "f4.json")
            bad = copy.deepcopy(config)
            bad["tasks"] = bad["tasks"][:-1]
            with self.assertRaises(ValueError): validate_configuration(bad)
            bad = copy.deepcopy(config)
            bad["limits"]["workers"] = 4
            with self.assertRaises(ValueError): validate_configuration(bad)

    def test_coherently_replaced_source_graph_is_rejected(self):
        from maxcover.reproducibility import instance_id
        from r4_inputs import instance
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory)
            task = config["tasks"][0]
            path = source / "graphs" / (task["base_graph_id"] + ".json")
            row = read_json(path)
            # Keep the original task and seed, change candidates and re-sign all
            # computed identities. Association must still reject the replacement.
            row["sets"] = [[0, 1]] * task["n"]
            for value in row["values"]:
                value.update(instance_id=instance_id(instance(row["sets"], task, value["k"])),
                             greedy=2, optimum=2, greedy_selected=list(range(value["k"])),
                             optimum_selected=list(range(value["k"])))
            write_json(path, row)
            with self.assertRaisesRegex(ValueError, "frozen R2 seed"):
                run(config, source, Path(directory) / "output")

    def test_consumed_preflight_and_final_resource_checks_prevent_passed(self):
        from r4_inputs import RuntimeBudget
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory, 1)
            output = Path(directory) / "output"
            run(config, source, output)
            consumed = copy.deepcopy(config)
            consumed["resource_decision"] = {"preflight_wall_seconds": 3600}
            with self.assertRaises(RuntimeError):
                with RuntimeBudget(output, consumed, "fixture"):
                    self.fail("spent budget entered")
            with patch("r4_inputs.RuntimeBudget.check", side_effect=[None, None, RuntimeError("final reused limit")]):
                with self.assertRaises(RuntimeError): run(config, source, output, resume=True)
            with patch("validate_r4_prefix_bounds.check_resources", side_effect=[None, RuntimeError("final limit")]):
                with self.assertRaises(RuntimeError): validate_batch(output, source)
            self.assertEqual(read_json(output / "verification.json")["status"], "incomplete")
            analyze(output, source)
            with patch("validate_r4_prefix_bounds.check_resources", side_effect=RuntimeError("final limit")):
                with self.assertRaises(RuntimeError): verify_summaries(output)
            self.assertEqual(read_json(output / "summary_verification.json")["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
