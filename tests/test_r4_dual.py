from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from itertools import combinations, product
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from r4_dual_core import certificates
from validate_r4_dual import verify_certificate


def original_sets(masks):
    return [[item for item in range(mask.bit_length()) if mask & (1 << item)]
            for mask in masks]


def exact_optimum(elements, k):
    return max(len(set().union(*(elements[index] for index in chosen)))
               for chosen in combinations(range(len(elements)), k))


def fixture(directory, count=2):
    from r2_budget_grid import evaluate_task
    from r2_design import make_design, write_json
    from r4_dual_io import configuration
    source = Path(directory) / "source"
    design = make_design("fixture", (6,), (2,), count, 0)
    write_json(source / "config.json", design)
    for task in design["tasks"]:
        write_json(source / "graphs" / (task["base_graph_id"] + ".json"),
                   evaluate_task(task, design["diagnostics"]))
    return source, configuration("fixture", design)


class R4DualTests(unittest.TestCase):
    def test_hand_examples_strict_tightening_and_unequal_size_certification(self):
        # The independently hand-worked equal-size example in the method note.
        masks = (15, 51, 71, 135)
        value = certificates(masks, [2])[0]
        self.assertEqual(value["path"], [0, 1])
        self.assertEqual((value["greedy"], value["initial_upper"],
                          value["prefix_upper"], value["dual_upper"]), (6, 8, 8, 7))
        self.assertEqual(value["minimizing_prefixes"], [1])
        self.assertEqual(value["prefixes"][1], {
            "t": 1, "selected": [0], "coverage": 4,
            "order": [1, 2, 3, 0], "s": [2, 1, 1, 0], "F": [2, 3, 4, 4],
            "q": [0, 2, 3], "upper": 7,
        })
        self.assertEqual([prefix["upper"] for prefix in value["prefixes"]], [8, 7, 8])
        self.assertEqual(exact_optimum(original_sets(masks), 2), 6)
        verify_certificate(original_sets(masks), value)

        unequal = certificates((3, 4, 8), [2])[0]
        self.assertEqual((unequal["greedy"], unequal["initial_upper"],
                          unequal["prefix_upper"], unequal["dual_upper"]), (3, 4, 4, 3))
        self.assertEqual(unequal["minimizing_prefixes"], [0])
        verify_certificate(original_sets((3, 4, 8)), unequal)

    def test_zero_no_crossing_saturation_and_original_indices(self):
        zero = certificates((0, 0, 0), [1, 2, 3])
        for value in zero:
            self.assertEqual(value["path"], list(range(value["k"])))
            self.assertEqual(value["greedy"], 0)
            self.assertEqual(value["dual_upper"], 0)
            self.assertEqual(value["minimizing_prefixes"], list(range(value["k"] + 1)))
            for prefix in value["prefixes"]:
                self.assertEqual(prefix["order"], [0, 1, 2])
                self.assertEqual(prefix["q"], [0] * (value["k"] + 1))
            verify_certificate([[], [], []], value)

        triangle = certificates((6, 10, 12), [2, 3])
        self.assertEqual(triangle[0]["prefixes"][0]["q"], [0, 2, 3])
        self.assertEqual(triangle[1]["prefixes"][0]["q"], [0, 2, 3, 3])
        self.assertEqual(triangle[1]["prefixes"][-1]["q"], [0, 0, 0, 0])
        for value in triangle:
            verify_certificate(original_sets((6, 10, 12)), value)

        # Certificate sorting must leave original indices and Greedy order intact.
        ordered = certificates((3, 12, 7), [2, 3])
        self.assertEqual(ordered[0]["prefixes"][0]["order"], [2, 0, 1])
        self.assertEqual(ordered[0]["path"], [2, 1])
        self.assertEqual(ordered[1]["path"], [2, 1, 0])
        self.assertEqual(ordered[0]["prefixes"][-1]["selected"], [2, 1])
        for value in ordered:
            verify_certificate(original_sets((3, 12, 7)), value)

    def test_all_tiny_set_systems_bound_exact_optimum_and_match_independent_checker(self):
        # All 512 ordered three-set systems, including duplicates and empty sets.
        for masks in product(range(8), repeat=3):
            elements = original_sets(masks)
            equal_size = len({len(candidate) for candidate in elements}) == 1
            for value in certificates(masks, [1, 2, 3]):
                optimum = exact_optimum(elements, value["k"])
                self.assertLessEqual(value["greedy"], optimum)
                self.assertLessEqual(optimum, value["dual_upper"])
                self.assertLessEqual(value["dual_upper"], value["prefix_upper"])
                self.assertLessEqual(value["prefix_upper"], value["initial_upper"])
                self.assertLessEqual(value["initial_upper"], value["union_size"])
                if equal_size:
                    self.assertEqual(value["dual_upper"] == value["greedy"],
                                     value["initial_upper"] == value["greedy"])
                if value["k"] in (1, 3):
                    self.assertEqual(value["dual_upper"], optimum)
                verify_certificate(elements, value)

    def test_nonmaximal_partition_and_reduced_residual_budget_are_rejected(self):
        disjoint = original_sets((3, 12))
        bad = certificates((3, 12), [2])[0]
        self.assertEqual(bad["prefixes"][0]["q"], [0, 2, 4])
        # (2, 0) is feasible, but is not the maximizing Method 3 partition.
        bad["prefixes"][0]["q"] = [0, 2, 2]
        bad["prefixes"][0]["upper"] = 2
        bad["dual_upper"] = 2
        bad["minimizing_prefixes"] = [0]
        with self.assertRaises(ValueError):
            verify_certificate(disjoint, bad)

        masks = (14, 22, 104)  # Full k is necessary even after conditioning on P_1.
        good = certificates(masks, [2])[0]
        self.assertEqual(good["path"], [0, 2])
        self.assertEqual(good["prefixes"][1]["q"], [0, 2, 3])
        self.assertEqual(exact_optimum(original_sets(masks), 2), 6)
        verify_certificate(original_sets(masks), good)
        for shortened in (False, True):
            bad = copy.deepcopy(good)
            bad["prefixes"][1]["q"] = [0, 2] if shortened else [0, 2, 2]
            bad["prefixes"][1]["upper"] = 5
            bad["dual_upper"] = 5
            bad["minimizing_prefixes"] = [1]
            with self.subTest(shortened=shortened), self.assertRaises(ValueError):
                verify_certificate(original_sets(masks), bad)

    def test_wrong_residual_sort_prefix_association_and_forged_values_are_rejected(self):
        masks = (15, 51, 71, 135)
        good = certificates(masks, [2])[0]
        cases = ("order", "s", "F", "q", "coverage", "selected", "t", "prefix_upper",
                 "initial_upper", "dual_upper", "union_size", "greedy", "minimizer",
                 "missing_empty", "missing_endpoint", "path", "extra_field", "bool", "float")
        for change in cases:
            bad = copy.deepcopy(good)
            prefix = bad["prefixes"][1]
            if change == "order": prefix["order"][0], prefix["order"][1] = prefix["order"][1], prefix["order"][0]
            elif change in ("s", "F", "q"): prefix[change][-1] += 1
            elif change in ("coverage", "t"): prefix[change] += 1
            elif change == "selected": prefix["selected"] = [1]
            elif change == "minimizer": bad["minimizing_prefixes"] = [0]
            elif change == "missing_empty": bad["prefixes"].pop(0)
            elif change == "missing_endpoint": bad["prefixes"].pop()
            elif change == "path": bad["path"].reverse()
            elif change == "extra_field": prefix["remaining_budget"] = 1
            elif change == "bool": prefix["t"] = True
            elif change == "float": prefix["s"][0] = float(prefix["s"][0])
            else: bad[change] += 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_certificate(original_sets(masks), bad)

    def test_invalid_inputs_and_budgets_are_rejected(self):
        for masks, budgets in (((), [1]), ((1, -1), [1]), ((True, 1), [1]),
                               ((1.0, 2), [1]), ((1, 2), []), ((1, 2), [0]),
                               ((1, 2), [3]), ((1, 2), [2, 1]), ((1, 2), [1, 1]),
                               ((1, 2), [True]), ((1, 2), [1.0])):
            with self.subTest(masks=masks, budgets=budgets), self.assertRaises(ValueError):
                certificates(masks, budgets)
        good = certificates((1, 2), [1])[0]
        for elements in ([], [[0], [-1]], [[0], [True]], [[0], [1, 1]], [[0], [1.0]]):
            with self.subTest(elements=elements), self.assertRaises(ValueError):
                verify_certificate(elements, good)
        for k in (0, 3, True, 1.0, "1"):
            bad = copy.deepcopy(good)
            bad["k"] = k
            with self.subTest(k=k), self.assertRaises(ValueError):
                verify_certificate([[0], [1]], bad)

    def test_independent_record_validation_rejects_sources_references_and_completion(self):
        from r4_dual import evaluate
        from r4_dual_io import SourceAccess
        from validate_r4_dual import verify_record
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory)
            with SourceAccess(source, config) as inputs:
                original = inputs.record(config["tasks"][0])
            row = evaluate(original, config)
            timing = verify_record(row, original, config)
            self.assertIn("certificate_seconds", timing)
            self.assertIn("reference_seconds", timing)
            for change in ("source_commit", "version", "task", "source", "status", "budgets",
                           "reference", "witness", "nonfinite_timing"):
                bad = copy.deepcopy(row)
                if change == "source_commit": bad["source_commit"] = "wrong"
                elif change == "version": bad["version"] = "wrong"
                elif change == "task": bad["task"]["seed"] += 1
                elif change == "source": bad["source"]["sets"][0] = []
                elif change == "status": bad["status"] = "incomplete"
                elif change == "budgets": bad["values"].pop()
                elif change == "reference": bad["source"]["values"][0]["optimum"] += 1
                elif change == "witness": bad["source"]["values"][-1]["optimum_selected"].reverse()
                else: bad["timing"][next(iter(bad["timing"]))] = float("nan")
                with self.subTest(change=change), self.assertRaises(ValueError):
                    verify_record(bad, original, config)
            bad = copy.deepcopy(row)
            bad["source"]["values"][0]["optimum"] += 1
            with self.assertRaises(ValueError):
                verify_record(bad, bad["source"], config)

    def test_resume_rebuild_and_stale_pass_cannot_authorize_changed_data(self):
        from r2_design import read_json, write_json
        from r4_dual import run, analyze
        from validate_r4_dual import validate_batch, verify_summaries
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory, 3)
            output = Path(directory) / "output"
            self.assertFalse(run(config, source, output, stop_after=1)["complete"])
            # Forged status does not replace the actual complete graph population.
            write_json(output / "run_status.json", {"complete": True, "computed": 3})
            with self.assertRaises(ValueError):
                validate_batch(output, source)
            checkpoint = output / "graphs" / (config["tasks"][0]["base_graph_id"] + ".json")
            before = checkpoint.read_bytes()
            self.assertEqual(run(config, source, output, resume=True)["computed"], 2)
            self.assertEqual(checkpoint.read_bytes(), before)
            validate_batch(output, source)
            analyze(output, source)
            verify_summaries(output)
            summary = (output / "cell_summary.csv").read_bytes()
            with patch("r4_dual.evaluate", side_effect=AssertionError("no certificate production during analyze")):
                analyze(output, source)
            self.assertEqual((output / "cell_summary.csv").read_bytes(), summary)
            damaged = read_json(checkpoint)
            damaged["values"][0]["dual_upper"] += 1
            write_json(checkpoint, damaged)
            with self.assertRaises(ValueError):
                analyze(output, source)
            self.assertEqual((output / "cell_summary.csv").read_bytes(), summary)
            with self.assertRaises(ValueError):
                run(config, source, output, resume=True)

    def test_corrupt_json_changed_source_and_incomplete_checkpoint_are_rejected(self):
        from r2_design import read_json, write_json
        from r4_dual import run
        from validate_r4_dual import validate_batch
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory, 1)
            output = Path(directory) / "output"
            run(config, source, output)
            checkpoint = output / "graphs" / (config["tasks"][0]["base_graph_id"] + ".json")
            saved = checkpoint.read_bytes()
            checkpoint.write_text('{"status":"complete",', encoding="utf-8")
            with self.assertRaises(ValueError):
                run(config, source, output, resume=True)
            checkpoint.write_bytes(saved)
            damaged = read_json(checkpoint)
            damaged["status"] = "incomplete"
            write_json(checkpoint, damaged)
            with self.assertRaises(ValueError):
                validate_batch(output, source)
            checkpoint.write_bytes(saved)
            source_path = source / "graphs" / checkpoint.name
            original = read_json(source_path)
            original["sets"] = [[0, 1]] * 6
            write_json(source_path, original)
            with self.assertRaises(ValueError):
                run(config, source, output, resume=True)

    def test_cli_valid_invalid_and_resource_interruption(self):
        from r2_design import read_json, write_json
        from r4_dual import run, main
        from validate_r4_dual import main as validator_main
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            source, config = fixture(directory, 1)
            output = Path(directory) / "output"
            config_path = Path(directory) / "dual-config.json"
            write_json(config_path, config)
            main(["run", "--source", str(source), "--output", str(output), "--config", str(config_path)])
            validator_main(["--source", str(source), "--output", str(output)])
            main(["analyze", "--source", str(source), "--output", str(output)])
            validator_main(["--summaries-only", "--output", str(output)])
            with self.assertRaises(SystemExit):
                main(["run", "--source", str(source), "--output", str(output)])
            with self.assertRaises(SystemExit):
                main(["analyze", "--source", str(source), "--output", str(output), "--resume"])
            with self.assertRaises(SystemExit):
                validator_main(["--output", str(output)])
            csv_path = output / "budget_results.csv"
            lines = csv_path.read_text(encoding="utf-8").splitlines()
            csv_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                validator_main(["--summaries-only", "--output", str(output)])
            self.assertEqual(read_json(output / "summary_verification.json")["status"], "incomplete")
            stopped = Path(directory) / "resource-stopped"
            with patch("r4_dual.check_resources", side_effect=RuntimeError("resource exhausted")):
                with self.assertRaises(RuntimeError):
                    run(config, source, stopped)
            self.assertEqual(list((stopped / "graphs").glob("*.json")), [])
            self.assertFalse(read_json(stopped / "run_status.json")["complete"])

    def test_metrics_zero_denominators_and_original_graph_budget_pairing(self):
        from r4_dual import summarize
        records = [{"task": {"base_graph_id": "zero", "n": 3, "d": 0},
                    "values": certificates((0, 0, 0), [1, 2, 3]),
                    "source": {"values": [{"optimum": 0, "instance_id": f"zero-{k}"}
                                           for k in (1, 2, 3)]}}]
        rows, cells = summarize(records)
        self.assertEqual([row["endpoint"] for row in rows], ["k=1", "interior", "k=M"])
        self.assertEqual({row["base_graph_id"] for row in rows}, {"zero"})
        self.assertEqual([cell["count"] for cell in cells], [1, 1, 1])
        for row, cell in zip(rows, cells):
            self.assertEqual(row["dual_certified"], 1)
            for metric in ("dual_ratio", "initial_ratio", "prefix_ratio", "dual_over_optimum",
                           "ratio_gain_initial", "ratio_gain_prefix"):
                self.assertIsNone(row[metric])
                self.assertEqual(cell[metric + "_missing"], 1)
                self.assertIsNone(cell[metric + "_mean"])

    def test_runtime_accounting_rejects_live_resume_and_recovers_real_hard_exit(self):
        from r4_dual_io import RuntimeBudget
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "accounting"
            config = {"limits": {"wall_seconds": 30}}
            with RuntimeBudget(output, config, "live"):
                with self.assertRaisesRegex(RuntimeError, "live operation"):
                    with RuntimeBudget(output, config, "concurrent"):
                        self.fail("concurrent operation entered")
            script = "\n".join((
                "import os, sys",
                "from pathlib import Path",
                "sys.path.insert(0, str(Path(sys.argv[1]) / 'analysis'))",
                "from r4_dual_io import RuntimeBudget",
                "with RuntimeBudget(sys.argv[2], {'limits': {'wall_seconds': 30}}, 'hard_exit') as budget:",
                "    budget.check()",
                "    os._exit(9)",
            ))
            child = subprocess.run([sys.executable, "-c", script, str(ROOT), str(output)],
                                   capture_output=True, text=True, timeout=20)
            self.assertEqual(child.returncode, 9, child.stderr)
            self.assertTrue((output / "active_operation.json").exists())
            with RuntimeBudget(output, config, "recovered"):
                pass
            history = [json.loads(line) for line in (output / "execution.jsonl").read_text(encoding="utf-8").splitlines()]
            recovered = [entry for entry in history if entry["status"] == "recovered_hard_interruption"]
            self.assertEqual(len(recovered), 1)
            self.assertGreaterEqual(recovered[0]["charged_wall_seconds"], recovered[0]["wall_seconds"])
            self.assertIn("unmeasured_tail_seconds_upper_bound", recovered[0])
            self.assertFalse((output / "active_operation.json").exists())
            self.assertEqual(len({entry["operation_id"] for entry in history}), len(history))
            for bad_seconds in (-1, float("nan")):
                (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": bad_seconds}) + "\n", encoding="utf-8")
                with self.subTest(seconds=bad_seconds), self.assertRaises(ValueError):
                    with RuntimeBudget(output, config, "invalid_history"):
                        self.fail("invalid resource history entered")

    def test_failed_source_context_entry_closes_its_git_process(self):
        from r4_dual_io import SourceAccess
        # A real cat-file subprocess fails on the unavailable object then exits;
        # repeated entry must neither leak it nor pretend a source is available.
        with tempfile.TemporaryDirectory() as directory:
            access = SourceAccess(directory, {"phase": "comparison", "source_design": {}})
            with self.assertRaises(ValueError):
                access.__enter__()
            self.assertIsNone(access.process)

    def test_concurrent_commands_preserve_live_status_and_checkpoints(self):
        from r2_design import read_json
        from r4_dual import run, analyze
        from r4_dual_io import RuntimeBudget
        from validate_r4_dual import validate_batch, verify_summaries
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory, 1)
            output = Path(directory) / "output"
            run(config, source, output)
            validate_batch(output, source)
            analyze(output, source)
            verify_summaries(output)
            names = ("run_status.json", "verification.json", "analysis_status.json", "summary_verification.json")
            before = {name: (output / name).read_bytes() for name in names}
            with RuntimeBudget(output, config, "held"):
                active_before = read_json(output / "active_operation.json")
                for operation in (lambda: run(config, source, output, resume=True),
                                  lambda: analyze(output, source),
                                  lambda: validate_batch(output, source),
                                  lambda: verify_summaries(output)):
                    with self.assertRaisesRegex(RuntimeError, "live operation"):
                        operation()
                    self.assertEqual(read_json(output / "active_operation.json"), active_before)
                    self.assertEqual({name: (output / name).read_bytes() for name in names}, before)

    def test_frozen_code_revision_accepts_prose_and_rejects_code_changes(self):
        from r4_dual_io import check_code_revision
        with tempfile.TemporaryDirectory() as directory, patch("r4_dual_io.CODE_PATHS", ("analysis/kernel.py", "src/maxcover")):
            root = Path(directory)
            def git(*args):
                result = subprocess.run(["git", "-C", str(root), "-c", "user.name=DUAL test", "-c",
                                         "user.email=dual-test@example.invalid", "-c", "commit.gpgSign=false", *args],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            git("init", "--quiet")
            (root / "README.md").write_text("initial\n", encoding="utf-8")
            git("add", "README.md")
            git("commit", "--quiet", "-m", "initial fixture")
            absent = git("rev-parse", "HEAD")
            (root / "analysis").mkdir()
            (root / "src/maxcover").mkdir(parents=True)
            implementation = root / "analysis/kernel.py"
            implementation.write_text("VALUE = 1\n", encoding="utf-8")
            (root / "src/maxcover/__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
            git("add", "analysis", "src")
            git("commit", "--quiet", "-m", "implementation fixture")
            revision = git("rev-parse", "HEAD")
            config = {"phase": "comparison", "code_revision": revision}
            check_code_revision(config, root)
            (root / "README.md").write_text("updated explanation\n", encoding="utf-8")
            git("add", "README.md")
            git("commit", "--quiet", "-m", "prose fixture")
            check_code_revision(config, root)
            implementation.write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                check_code_revision(config, root)
            implementation.write_text("VALUE = 1\n", encoding="utf-8")
            for bad_revision in (absent, "0" * 40):
                with self.subTest(revision=bad_revision), self.assertRaisesRegex(ValueError, "lacks"):
                    check_code_revision({"phase": "comparison", "code_revision": bad_revision}, root)
            (root / "src/maxcover/untracked.py").write_text("VALUE = 3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "uncommitted"):
                check_code_revision(config, root)

    def test_preflight_report_recovery_rechecks_records_without_production(self):
        from r2_design import make_design, read_json, write_json
        from r4_dual_io import configuration
        from r4_dual_preflight import preflight
        # Exercise the complete recovery path cheaply with 18 independently
        # seeded tiny graphs; the actual resource preflight uses all nine cells.
        design = make_design("fixture", (6,), (2,), 18, 0)
        config = configuration("fixture", design)
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()), \
                patch("r4_dual_preflight.make_design", return_value=design), \
                patch("r4_dual_preflight.configuration", return_value=config), \
                patch("r4_dual_preflight.directory_scale_probe", return_value={"conservative_allowance_seconds": 1.0}):
            output = Path(directory) / "preflight"
            first = preflight(output)
            self.assertEqual(first["status"], "passed")
            checkpoint = output / "dual/graphs" / (design["tasks"][0]["base_graph_id"] + ".json")
            saved = checkpoint.read_bytes()
            with patch("r4_dual_preflight.prepare_sources", side_effect=AssertionError("no source regeneration")), \
                    patch("r4_dual_preflight.run", side_effect=AssertionError("no certificate reproduction")):
                resumed = preflight(output, resume=True)
                self.assertEqual(resumed["status"], "passed")
                self.assertIn("recovery_check_seconds", resumed)
                self.assertEqual(checkpoint.read_bytes(), saved)
                for change in ("missing_budget", "reference", "completion"):
                    bad = json.loads(saved)
                    if change == "missing_budget": bad["values"].pop()
                    elif change == "reference": bad["source"]["values"][0]["optimum"] += 1
                    else: bad["status"] = "incomplete"
                    write_json(checkpoint, bad)
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        preflight(output, resume=True)
                    self.assertEqual(read_json(output / "resource_preflight.json")["status"], "incomplete")
                    checkpoint.write_bytes(saved)

    def test_simultaneous_hard_exit_recovery_has_exactly_one_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "race"
            gate = Path(directory) / "go"
            prefix = "\n".join(("import os, sys, time", "from pathlib import Path",
                                 "sys.path.insert(0, str(Path(sys.argv[1]) / 'analysis'))",
                                 "from r4_dual_io import RuntimeBudget"))
            killed = subprocess.run([sys.executable, "-c", prefix + "\nwith RuntimeBudget(sys.argv[2], {'limits': {'wall_seconds': 30}}, 'killed'):\n    os._exit(9)",
                                     str(ROOT), str(output)], capture_output=True, text=True, timeout=20)
            self.assertEqual(killed.returncode, 9, killed.stderr)
            script = prefix + "\n" + "\n".join((
                "print('ready', flush=True)", "while not Path(sys.argv[3]).exists(): time.sleep(.005)",
                "try:", "    with RuntimeBudget(sys.argv[2], {'limits': {'wall_seconds': 30}}, 'racer'):",
                "        print('owned', flush=True)", "        time.sleep(.4)",
                "except RuntimeError:", "    print('rejected', flush=True)",
            ))
            children = [subprocess.Popen([sys.executable, "-c", script, str(ROOT), str(output), str(gate)],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
            try:
                for child in children:
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                gate.write_text("go", encoding="utf-8")
                outcomes = [child.communicate(timeout=20) for child in children]
                self.assertEqual(sorted(stdout.strip() for stdout, _ in outcomes), ["owned", "rejected"], outcomes)
                self.assertTrue(all(child.returncode == 0 for child in children), outcomes)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=10)
            history = [json.loads(line) for line in (output / "execution.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sum(entry["status"] == "recovered_hard_interruption" for entry in history), 1)
            self.assertEqual(sum(entry["status"] == "complete" for entry in history), 1)

    def test_incremental_output_and_per_graph_memory_caps_preserve_checkpoints(self):
        from r2_design import read_json
        from r4_dual import run
        with tempfile.TemporaryDirectory() as directory, patch.dict("r4_dual_io.LIMITS", {"output_bytes": 5000}):
            source, config = fixture(directory, 3)
            output = Path(directory) / "output-cap"
            with self.assertRaisesRegex(RuntimeError, "output budget"):
                run(config, source, output)
            checkpoints = list((output / "graphs").glob("*.json"))
            self.assertGreater(len(checkpoints), 0)
            self.assertLess(len(checkpoints), 3)
            self.assertFalse(read_json(output / "run_status.json")["complete"])
            self.assertTrue(all(read_json(path)["status"] == "complete" for path in checkpoints))
        with tempfile.TemporaryDirectory() as directory:
            source, config = fixture(directory, 3)
            output = Path(directory) / "memory-cap"
            def measured_memory():
                return config["limits"]["memory_bytes"] + 1 if list((output / "graphs").glob("*.json")) else 0
            with patch("r4_dual.memory_usage", side_effect=measured_memory):
                with self.assertRaisesRegex(RuntimeError, "memory budget"):
                    run(config, source, output)
            self.assertEqual(len(list((output / "graphs").glob("*.json"))), 1)
            self.assertFalse(read_json(output / "run_status.json")["complete"])


if __name__ == "__main__":
    unittest.main()
