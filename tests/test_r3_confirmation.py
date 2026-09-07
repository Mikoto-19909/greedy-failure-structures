from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from r2_design import read_json, write_json
from r3_confirmation_inputs import validate_configuration, tasks_for, VERSION
from r3_confirmation import compute_graph, run, analyze, summary_rows
from validate_r3_confirmation import verify_record, validate_batch, verify_summaries


def fixture_config(count=3):
    config = copy.deepcopy(read_json(ROOT / "analysis/r3_confirmation_config.json"))
    config.update(version=VERSION + "-fixture", phase="fixture", sample_count=count,
                  interval_half_width=math.sqrt(2 * math.log(40) / count))
    config["tasks"] = tasks_for(config["version"], count, fixture=True)
    return validate_configuration(config)


class R3ConfirmationTests(unittest.TestCase):
    def test_frozen_configuration_and_seed_domains(self):
        config = read_json(ROOT / "analysis/r3_confirmation_config.json")
        validate_configuration(config)
        for key, value in (("sample_count", 2999), ("proposals", 512), ("k", 3), ("accept_equal", False)):
            bad = copy.deepcopy(config)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_configuration(bad)
        bad = copy.deepcopy(config)
        bad["tasks"][0]["chains"][0]["seed"] += 1
        with self.assertRaises(ValueError):
            validate_configuration(bad)
        fixture = fixture_config()
        self.assertTrue({t["seed"] for t in fixture["tasks"]}.isdisjoint(t["seed"] for t in config["tasks"]))

    def test_valid_record_and_corrupt_references_and_chains(self):
        config = fixture_config(1)
        task = config["tasks"][0]
        record = compute_graph(task, config)
        verify_record(record, task, config)
        for mode in ("optimum", "forced_optimum", "witness", "column_degree", "seed", "membership"):
            bad = copy.deepcopy(record)
            end = bad["chains"][0]["endpoints"][0]
            if mode in ("optimum", "forced_optimum"):
                end["values"][mode] += 1
            elif mode == "witness":
                end["values"]["forced_selected"].reverse()
            elif mode == "column_degree":
                end["sets"][0] = []
            elif mode == "seed":
                bad["chains"][0]["seed"] += 1
            else:
                bad["chains"].pop()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                verify_record(bad, task, config)

    def test_recovery_summary_and_stale_pass_rejected(self):
        config = fixture_config(3)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            run(config, output, workers=1, stop_after=1)
            path = next((output / "graphs").glob("*.json"))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                validate_batch(output, workers=1)
            with patch("r3_confirmation.compute_graph", wraps=compute_graph) as solver:
                state = run(config, output, workers=1, resume=True)
                self.assertEqual(solver.call_count, 2)
            self.assertTrue(state["complete"])
            self.assertEqual(path.read_bytes(), before)
            validate_batch(output, workers=1)
            analyze(output, workers=1)
            verify_summaries(output)
            primary_before = (output / "primary_summary.json").read_bytes()
            bad = read_json(path)
            bad["chains"][0]["endpoints"][0]["values"]["forced_optimum"] += 1
            write_json(path, bad)
            with self.assertRaises(ValueError):
                analyze(output, workers=1)
            self.assertEqual((output / "primary_summary.json").read_bytes(), primary_before)
            path.write_bytes(before)
            with patch("r3_confirmation.compute_graph", side_effect=AssertionError("no production rerun")):
                analyze(output, workers=1)
                self.assertEqual(run(config, output, workers=1, resume=True)["computed"], 0)
            bad_summary = read_json(output / "primary_summary.json")
            bad_summary["delta"] += .1
            write_json(output / "primary_summary.json", bad_summary)
            with self.assertRaises(ValueError):
                verify_summaries(output)

    def test_original_graph_unit_and_hoeffding_interval(self):
        config = fixture_config(2)
        records = [compute_graph(t, config) for t in config["tasks"]]
        # Statistical fixture: high minus low per graph is +1 and -1, independent n is 2.
        for i, record in enumerate(records):
            for chain in record["chains"]:
                chain["endpoints"][0]["values"]["first_loss"] = chain["direction"] == (1 if i == 0 else -1)
        bases, ends, summary = summary_rows(records, config)
        self.assertEqual([r["difference"] for r in bases], [1, -1])
        self.assertEqual(summary["n"], 2)
        self.assertEqual(len(ends), 8)
        self.assertEqual(summary["delta"], 0)
        self.assertAlmostEqual(summary["half_width"], math.sqrt(math.log(40)))
        self.assertEqual((summary["lower"], summary["upper"], summary["direction"]), (-1, 1, "inconclusive"))

    def test_resource_exhaustion_does_not_generate_replacements(self):
        config = fixture_config(1)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_json(output / "config.json", config)
            (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": 3600}) + "\n")
            with patch("r3_confirmation.compute_graph", side_effect=AssertionError("must not generate")):
                with self.assertRaisesRegex(RuntimeError, "cumulative"):
                    run(config, output, workers=1, resume=True)
            self.assertFalse((output / "graphs").exists())


if __name__ == "__main__":
    unittest.main()
