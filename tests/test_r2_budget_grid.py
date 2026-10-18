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
from r2_design import RuntimeBudget, make_design, read_json, write_json, validate_design
from r2_budget_grid import all_budget_optima, evaluate_task, run, summarize, analyze, f2_from_preflight
from validate_r2_budget_grid import reference, verify_graph, validate_batch, verify_summaries


class R2BudgetTests(unittest.TestCase):
    def test_exactly_k_canonical_witnesses_and_duplicate_sets(self):
        for sets in ((3, 5, 10), (3, 3, 3, 3), (1, 2, 4, 8), (3, 6, 5)):
            best, witnesses, visited = all_budget_optima(sets)
            self.assertEqual(visited, 2**len(sets))
            elements = [{a for a in range(4) if s & (1 << a)} for s in sets]
            for k in range(1, len(sets) + 1):
                optimum, witness = reference(elements, k)
                self.assertEqual((best[k], list(witnesses[k])), (optimum, witness))
                self.assertEqual(len(witnesses[k]), k)
        self.assertEqual(all_budget_optima((3, 3, 3, 3))[1][2], (0, 1))

    def test_complete_graph_and_corrupt_inputs(self):
        design = make_design("fixture", (4,), (2,), 2, 1)
        task = design["tasks"][0]
        row = evaluate_task(task, design["diagnostics"])
        verify_graph(row, task, design["diagnostics"])
        for change in ("optimum", "selected", "status", "sets", "diagnostic"):
            damaged = copy.deepcopy(row)
            if change == "optimum":
                damaged["values"][1]["optimum"] += 1
            elif change == "selected":
                damaged["values"][-1]["optimum_selected"].reverse()
            elif change == "status":
                damaged["values"][0]["reference_status"] = "timeout"
            elif change == "sets":
                damaged["sets"][0] = []
            else:
                damaged["diagnostic"]["prefixes"][0]["optimal_completion"] += 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_graph(damaged, task, design["diagnostics"])

    def test_resume_and_independent_reconstruction(self):
        design = make_design("fixture", (4,), (2,), 3, 1)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            first = run(design, output, workers=1, stop_after=1)
            self.assertFalse(first["complete"])
            checkpoint = output / "graphs" / (design["tasks"][0]["base_graph_id"] + ".json")
            before = checkpoint.read_bytes()
            with patch("r2_budget_grid.evaluate_task", wraps=evaluate_task) as solver:
                final = run(design, output, workers=1, resume=True)
                self.assertEqual(solver.call_count, 2)
            self.assertTrue(final["complete"])
            self.assertEqual(checkpoint.read_bytes(), before)
            validate_batch(output, workers=1)
            real_import = __import__

            def without_plot_dependency(name, *args, **kwargs):
                if name == "matplotlib" or name.startswith("matplotlib."):
                    raise ModuleNotFoundError(name)
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=without_plot_dependency):
                analyze(output, plot=False)
            verify_summaries(output)
            data_before = (output / "cell_summary.csv").read_bytes()
            with patch("r2_budget_grid.evaluate_task", side_effect=AssertionError("no algorithms on summarize")):
                analyze(output, plot=False)
            self.assertEqual((output / "cell_summary.csv").read_bytes(), data_before)
            damaged = (output / "cell_summary.csv").read_text().replace("ratio_of_means", "wrong_metric", 1)
            (output / "cell_summary.csv").write_text(damaged)
            with self.assertRaises(ValueError):
                verify_summaries(output)

    def test_incomplete_and_mismatched_designs_rejected(self):
        design = make_design("fixture", (4,), (2,), 2, 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            run(design, output, workers=1, stop_after=1)
            with self.assertRaises(ValueError):
                validate_batch(output, workers=1)
            with self.assertRaises(ValueError):
                analyze(output, plot=False)
            changed = make_design("fixture", (4,), (2,), 3, 0)
            with self.assertRaises(ValueError):
                run(changed, output, workers=1, resume=True)
        for name in ("seed", "budgets", "diagnostic_k"):
            damaged = copy.deepcopy(design)
            damaged["tasks"][0][name] = 1 if name == "diagnostic_k" else None
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_design(damaged)

    def test_metric_denominators_and_bootstrap_unit(self):
        design = make_design("fixture", (4,), (2,), 2, 0)
        records = [{"task": {"n": 4, "d": 2, "budgets": [2]},
                    "values": [{"greedy": g, "optimum": o}]}
                   for g, o in ((3, 3), (3, 4))]
        row = summarize(records, design)[0]
        self.assertAlmostEqual(row["ratio_of_means"], 6/7)
        self.assertAlmostEqual(row["mean_ratio"], 7/8)
        self.assertAlmostEqual(row["mean_relative_gap"], 1/8)
        self.assertEqual(row["failure_rate"], .5)
        self.assertEqual(row["count"], 2)
        for record in records:
            record["task"]["budgets"].append(3)
            record["values"].append(dict(record["values"][0]))
        rows = summarize(records, design)
        for metric in ("ratio_of_means", "mean_ratio", "mean_relative_gap", "mean_absolute_loss"):
            for suffix in ("", "_lower", "_upper"):
                self.assertEqual(rows[0][metric+suffix], rows[1][metric+suffix])

    def test_preflight_must_measure_all_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_json(output / "config.json", make_design("preflight", repetitions=8, diagnostic_count=0))
            with self.assertRaisesRegex(ValueError, "complete approved"):
                f2_from_preflight(output)

    def test_analyze_rejects_changed_inputs_despite_old_passed_status(self):
        design = make_design("fixture", (6,), (2,), 8, 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            run(design, output, workers=1)
            validate_batch(output, workers=1)
            analyze(output, plot=False)
            summary_before = (output / "cell_summary.csv").read_bytes()
            paths = sorted((output / "graphs").glob("*.json"))
            originals = {p: p.read_bytes() for p in paths}
            first = json.loads(originals[paths[0]])
            first["values"][0]["optimum"] += 1
            write_json(paths[0], first)
            with self.assertRaises(ValueError):
                analyze(output, plot=False)
            self.assertEqual((output / "cell_summary.csv").read_bytes(), summary_before)
            paths[0].write_bytes(originals[paths[0]])
            # A feasible but suboptimal witness also must not inherit an old proof.
            changed = False
            for path in paths:
                record = json.loads(originals[path])
                failures = [v for v in record["values"] if v["greedy"] < v["optimum"]]
                if failures:
                    failures[0]["optimum"] = failures[0]["greedy"]
                    failures[0]["optimum_selected"] = failures[0]["greedy_selected"][:]
                    write_json(path, record)
                    with self.assertRaises(ValueError):
                        analyze(output, plot=False)
                    path.write_bytes(originals[path])
                    changed = True
                    break
            self.assertTrue(changed, "fixture must contain a suboptimal feasible Greedy result")
            self.assertEqual((output / "cell_summary.csv").read_bytes(), summary_before)
            with patch("r2_budget_grid.evaluate_task", side_effect=AssertionError("no production rerun")):
                analyze(output, plot=False)
                result = run(design, output, workers=1, resume=True)
            self.assertEqual(result["computed"], 0)
            self.assertEqual(result["reused"], 8)

    def test_resource_limits_and_recovery_budget(self):
        design = make_design("fixture", (4,), (2,), 1, 0)
        for key, value in (("workers", 99), ("wall_seconds", float("inf")),
                           ("memory_bytes", -1), ("output_bytes", 0)):
            damaged = copy.deepcopy(design)
            damaged["limits"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_design(damaged)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_json(output / "config.json", design)
            (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": 43200}) + "\n")
            with patch("r2_budget_grid.evaluate_task", side_effect=AssertionError("must not run")):
                with self.assertRaisesRegex(RuntimeError, "cumulative"):
                    run(design, output, workers=1, resume=True)

    def test_last_single_worker_result_enforces_cumulative_budget(self):
        design = make_design("fixture", (2,), (1,), 1, 0)
        for elapsed in (0.5, 1.0, 2.0):
            with self.subTest(elapsed=elapsed), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                write_json(output / "config.json", design)
                (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": 43199}) + "\n")
                clock = [0.0]

                def finish_graph(task, limits):
                    record = evaluate_task(task, limits)
                    clock[0] = elapsed
                    return record

                with patch("time.perf_counter", side_effect=lambda: clock[0]), \
                        patch("r2_budget_grid.evaluate_task", side_effect=finish_graph) as solver:
                    if elapsed >= 1:
                        with self.assertRaisesRegex(RuntimeError, "cumulative"):
                            run(design, output, workers=1, resume=True)
                    else:
                        self.assertTrue(run(design, output, workers=1, resume=True)["complete"])
                self.assertEqual(solver.call_count, 1)
                task = design["tasks"][0]
                saved = read_json(output / "graphs" / (task["base_graph_id"] + ".json"))
                verify_graph(saved, task, design["diagnostics"])
                self.assertEqual(read_json(output / "run_status.json")["complete"], elapsed < 1)
                last = json.loads((output / "execution.jsonl").read_text().splitlines()[-1])
                self.assertEqual(last["status"], "complete" if elapsed < 1 else "interrupted")
                self.assertEqual(last["wall_seconds"], elapsed)

    def test_budget_exit_accounts_trailing_work_and_preserves_original_error(self):
        design = make_design("fixture", (2,), (1,), 1, 0)
        for elapsed, original in ((0.5, None), (1.0, None), (2.0, None),
                                  (2.0, ValueError("original calculation failure"))):
            with self.subTest(elapsed=elapsed, original=original), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": 43199}) + "\n")
                clock = [0.0]

                def operation():
                    with RuntimeBudget(output, design, "trailing_summary"):
                        clock[0] = elapsed
                        if original is not None:
                            raise original

                with patch("time.perf_counter", side_effect=lambda: clock[0]):
                    if original is not None:
                        with self.assertRaises(ValueError) as caught:
                            operation()
                        self.assertIs(caught.exception, original)
                    elif elapsed >= 1:
                        with self.assertRaisesRegex(RuntimeError, "cumulative"):
                            operation()
                    else:
                        operation()
                last = json.loads((output / "execution.jsonl").read_text().splitlines()[-1])
                self.assertEqual(last["status"], "complete" if elapsed < 1 else "interrupted")
                self.assertEqual(last["wall_seconds"], elapsed)

    def test_last_single_worker_verification_does_not_publish_over_budget_pass(self):
        from validate_r2_budget_grid import verify_saved

        design = make_design("fixture", (2,), (1,), 1, 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            run(design, output, workers=1)
            (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": 43199}) + "\n")
            clock = [0.0]

            def finish_verification(*args):
                result = verify_saved(*args)
                clock[0] = 2.0
                return result

            with patch("time.perf_counter", side_effect=lambda: clock[0]), \
                    patch("validate_r2_budget_grid.verify_saved", side_effect=finish_verification):
                with self.assertRaisesRegex(RuntimeError, "cumulative"):
                    validate_batch(output, workers=1)
            self.assertEqual(read_json(output / "verification.json")["status"], "incomplete")

    def test_summary_pass_is_published_only_after_budget_exit(self):
        import csv
        import validate_r2_budget_grid as r2_verifier
        import validate_r3_confirmation as r3_verifier
        from r3_confirmation import run as run_r3, analyze as analyze_r3
        from r3_confirmation_inputs import VERSION, tasks_for

        r2_design = make_design("fixture", (2,), (1,), 1, 1)
        r3_design = copy.deepcopy(read_json(ROOT / "analysis/r3_confirmation_config.json"))
        r3_design.update(version=VERSION + "-fixture", phase="fixture", sample_count=1,
                         interval_half_width=math.sqrt(2 * math.log(40)))
        r3_design["tasks"] = tasks_for(r3_design["version"], 1, fixture=True)
        with tempfile.TemporaryDirectory() as directory:
            for name, design in (("r2", r2_design), ("r3", r3_design)):
                output = Path(directory) / name
                if name == "r2":
                    run(design, output, workers=1)
                    analyze(output, plot=False, verification_workers=1)
                else:
                    run_r3(design, output, workers=1)
                    analyze_r3(output, workers=1)
                for elapsed, corrupt in ((0.5, False), (2.0, False), (2.0, True)):
                    with self.subTest(study=name, elapsed=elapsed, corrupt=corrupt):
                        prior = design["limits"]["wall_seconds"] - 1
                        (output / "execution.jsonl").write_text(json.dumps({"wall_seconds": prior}) + "\n")
                        clock = [0.0]
                        if name == "r2":
                            original_reader = csv.DictReader
                            reads = [0]

                            def read_last_csv(*args, **kwargs):
                                reader = original_reader(*args, **kwargs)
                                reads[0] += 1
                                if reads[0] == 3:
                                    clock[0] = elapsed
                                    if corrupt:
                                        reader.fieldnames = ["bad_column" if field == "failures" else field
                                                            for field in reader.fieldnames]
                                return reader

                            replacement = patch.object(r2_verifier.csv, "DictReader", side_effect=read_last_csv)
                            verifier = r2_verifier.verify_summaries
                        else:
                            def read_last_summary(path):
                                data = read_json(path)
                                if Path(path).name == "primary_summary.json":
                                    clock[0] = elapsed
                                    if corrupt:
                                        data["n"] += 1
                                return data

                            replacement = patch.object(r3_verifier, "read_json", side_effect=read_last_summary)
                            verifier = r3_verifier.verify_summaries
                        with patch("time.perf_counter", side_effect=lambda: clock[0]), replacement:
                            if corrupt:
                                with self.assertRaises(ValueError):
                                    verifier(output)
                            elif elapsed >= 1:
                                with self.assertRaisesRegex(RuntimeError, "cumulative"):
                                    verifier(output)
                            else:
                                verifier(output)
                        self.assertEqual(read_json(output / "summary_verification.json")["status"],
                                         "passed" if elapsed < 1 else "incomplete")


if __name__ == "__main__":
    unittest.main()
