"""Study calculations, pair membership and saved-instance replay contracts."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import brute_force, greedy
from maxcover.benchmark import replay_instance_file
from maxcover.dashboard_analysis import StudyAnalysisService
from maxcover.dashboard_studies import StudiesError
from maxcover.reproducibility import instance_from_payload, instance_id


def write_json(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_csv(root, name, rows):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


SETS = [[0, 1], [0, 2], [1, 3], [0, 1]]


def instance(sets, k, seed=42, parameters=None, family="fixed_size"):
    return instance_from_payload({"schema_version": 1, "encoding": "elements", "sets": sets, "k": k,
        "universe_size": 4, "seed": seed, "family": family,
        "parameters": parameters if parameters is not None else {"set_size": 2, "unique_sets": False}})


def outcomes(item):
    g, o = greedy(item), brute_force(item)
    forced = max((item.coverage((0, i)), [0, i]) for i in range(1, 4))
    return {"greedy": g.coverage, "greedy_selected": list(g.selected), "optimum": o.coverage,
            "optimum_selected": list(o.selected), "forced_optimum": forced[0], "forced_selected": forced[1],
            "first_loss": forced[0] < o.coverage}


def make_r2(root, source="results/r2", count=2, kind="r2"):
    rows, tasks, graphs = [], [], []
    version = {"r2": "r2-budget-v1-fixture", "r4": "r4-prefix-bound-v1-fixture", "r4_dual": "r4-l5-dual-v1-fixture"}[kind]
    for repetition in range(count):
        task = {"base_graph_id": f"g{repetition:04d}", "n": 4, "d": 2, "seed": 42 + repetition,
                "repetition": repetition, "budgets": [1, 2, 4], "diagnostic_k": None}
        tasks.append(task)
        values, certificates = [], []
        for k in task["budgets"]:
            item = instance(SETS, k, task["seed"])
            g, o = greedy(item), brute_force(item)
            values.append({"k": k, "instance_id": instance_id(item), "greedy": g.coverage,
                "greedy_selected": list(g.selected), "optimum": o.coverage,
                "optimum_selected": list(o.selected), "reference_status": "optimal"})
            row = {"base_graph_id": task["base_graph_id"], "n": 4, "d": 2, "k": k,
                   "instance_id": instance_id(item), "greedy": g.coverage, "optimum": o.coverage}
            if kind == "r2":
                row.update(repetition=repetition, relative_gap=(o.coverage - g.coverage) / o.coverage)
            else:
                bound = o.coverage
                if kind == "r4":
                    row.update(initial_upper=bound, upper=bound, tightening=0, certified_ratio=g.coverage / bound,
                               certified_optimal=int(g.coverage == bound))
                else:
                    row.update(initial_upper=bound, prefix_upper=bound, dual_upper=bound, tightening_prefix=0,
                        initial_ratio=g.coverage / bound, prefix_ratio=g.coverage / bound, dual_ratio=g.coverage / bound,
                        initial_certified=int(g.coverage == bound), prefix_certified=int(g.coverage == bound), dual_certified=int(g.coverage == bound))
                chosen, covered, prefixes = [], set(), []
                for t in range(k + 1):
                    prefixes.append({"t": t, "coverage": len(covered)})
                    if t < k:
                        best = max((i for i in range(4) if i not in chosen), key=lambda i: (len(set(SETS[i]) - covered), -i))
                        chosen.append(best)
                        covered.update(SETS[best])
                certificates.append({"k": k, "greedy": g.coverage, "path": chosen, "prefixes": prefixes,
                    **({"initial_upper": bound, "upper": bound} if kind == "r4" else {"initial_upper": bound, "prefix_upper": bound, "dual_upper": bound})})
            rows.append(row)
        graph = {"task": task, "sets": SETS, "status": "complete", "values": values}
        if kind != "r2":
            graph = {"task": task, "source": graph, "status": "complete", "values": certificates}
        graphs.append(graph)
        write_json(root, source + "/graphs/" + task["base_graph_id"] + ".json", graph)
    cells = []
    for k in (1, 2, 4):
        group = [r for r in rows if r["k"] == k]
        cell = {"n": 4, "d": 2, "k": k, "count": count}
        if kind == "r2":
            failure = float(group[0]["greedy"] < group[0]["optimum"])
            gap = group[0]["relative_gap"]
            cell.update(failure_rate=failure, failure_lower=0, failure_upper=1,
                        mean_relative_gap=gap, mean_relative_gap_lower=0, mean_relative_gap_upper=1)
        else:
            ratio = group[0]["greedy"] / group[0]["optimum"]
            cell.update(certified_ratio_mean=ratio, tightening_mean=0,
                        initial_ratio_mean=ratio, prefix_ratio_mean=ratio, dual_ratio_mean=ratio)
        cells.append(cell)
    write_json(root, source + "/config.json", {"version": version, "tasks": tasks})
    write_csv(root, source + "/budget_results.csv", rows)
    write_csv(root, source + "/cell_summary.csv", cells)
    return rows, graphs


def make_r3(root, source="results/r3"):
    version = "r3-first-step-confirm-v1-fixture"
    task = {"base_graph_id": "r3-fixture-r0000", "repetition": 0, "seed": 42,
            "chains": [{"direction": side, "replica": rep, "seed": 18000000000000000000 + (side + 1) * 2 + rep}
                       for side in (-1, 1) for rep in (0, 1)]}
    original = instance(SETS, 2)
    graph = {"task": task, "status": "complete", "sets": SETS, "instance_id": instance_id(original), "values": outcomes(original), "chains": []}
    rows = []
    for spec in task["chains"]:
        low = spec["direction"] == -1
        sets = [[0, 2], [0, 1], [1, 3], [0, 1]] if low else SETS
        parameters = {"r3_version": version, "base_graph_id": task["base_graph_id"], "direction": spec["direction"], "replica": spec["replica"]}
        item = instance(sets, 2, spec["seed"], parameters, "custom")
        values = outcomes(item)
        endpoint = {"sets": sets, "values": values, "instance_id": instance_id(item), "proposals": 2048,
                    "accepted": int(low), "legal": 1, "exposure": 2 if low else 4}
        graph["chains"].append({**spec, "moves": [[1, 0, 1, 1, 2]] if low else [], "endpoints": [endpoint]})
        rows.append({"base_graph_id": task["base_graph_id"], "direction": spec["direction"], "replica": spec["replica"], "chain_seed": spec["seed"],
            "instance_id": instance_id(item), "greedy": values["greedy"], "optimum": values["optimum"], "forced_optimum": values["forced_optimum"],
            "first_loss": int(values["first_loss"]), "accepted": int(low), "legal": 1, "proposals": 2048, "exposure": endpoint["exposure"]})
    base = {"base_graph_id": task["base_graph_id"], "repetition": 0, "low_first_loss": 0, "high_first_loss": 1, "difference": 1,
            "low_failure": 0, "high_failure": 1, "low_relative_gap": 0, "high_relative_gap": .25, "low_exposure": 2, "high_exposure": 4}
    write_json(root, source + "/config.json", {"version": version, "n": 4, "d": 2, "k": 2, "proposals": 2048, "tasks": [task]})
    write_json(root, source + "/graphs/" + task["base_graph_id"] + ".json", graph)
    write_json(root, source + "/primary_summary.json", {"n": 1, "endpoints": 4, "delta": 1, "lower": -1, "upper": 1})
    write_csv(root, source + "/endpoint_results.csv", rows)
    write_csv(root, source + "/base_graph_summary.csv", [base])
    return rows, graph


class StudyAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = StudyAnalysisService(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_complete_pagination_and_fixed_cell_distribution(self):
        make_r2(self.root, count=71)
        overview = self.service.overview("results/r2", {"n": "4", "d": "2", "k": "2"})
        self.assertEqual(overview["total_records"], 213)
        self.assertEqual(overview["distributions"]["relative_gap"]["mean"], .25)
        self.assertEqual(overview["graph_count"], 71)
        last = self.service.records("results/r2", offset=200)
        self.assertEqual((last["total"], len(last["rows"])), (213, 13))
        self.assertEqual(self.service.overview("results/r2")["distributions"], {})

    def test_budget_pairing_and_saved_ci(self):
        make_r2(self.root)
        data = self.service.pairs("results/r2", 4, 2, 1, 2)
        self.assertEqual(data["distribution"]["mean"], .25)
        self.assertEqual(len(data["pairs"]), 2)
        self.assertEqual(self.service.overview("results/r2")["cells"][0]["failure_upper"], 1)
        with self.assertRaises(StudiesError):
            self.service.pairs("results/r2", 4, 2, 2, 2)
        with self.assertRaises(StudiesError):
            self.service.pairs("results/r2", 4, 2, 1, 3)

    def test_missing_and_duplicate_budget_rejected(self):
        rows, _ = make_r2(self.root)
        for changed in (rows[:-1], rows + [rows[0]]):
            write_csv(self.root, "results/r2/budget_results.csv", changed)
            with self.assertRaises(StudiesError):
                self.service.overview("results/r2")

    def test_r3_four_endpoints_and_graph_level_differences(self):
        make_r3(self.root)
        data = self.service.overview("results/r3")
        self.assertEqual((data["graph_count"], data["record_count"]), (1, 4))
        self.assertEqual(data["distributions"]["high_minus_low_first_loss"]["mean"], 1)
        filtered = self.service.overview("results/r3", {"loss_only": "true"})
        self.assertEqual(filtered["record_count"], 2)
        self.assertEqual(filtered["distributions"]["high_minus_low_first_loss"]["mean"], 1)
        self.assertEqual(self.service.records("results/r3")["rows"][0]["chain_seed"], "18000000000000000000")

    def test_r3_missing_chain_duplicate_identity_and_inconsistent_summary_rejected(self):
        for mutation in ("missing", "duplicate", "difference"):
            rows, _ = make_r3(self.root)
            if mutation == "missing":
                write_csv(self.root, "results/r3/endpoint_results.csv", rows[:-1])
            elif mutation == "duplicate":
                rows[-1]["instance_id"] = rows[0]["instance_id"]
                write_csv(self.root, "results/r3/endpoint_results.csv", rows)
            else:
                path = self.root / "results/r3/base_graph_summary.csv"
                with path.open() as handle:
                    contents = list(csv.DictReader(handle))
                contents[0]["difference"] = 0
                write_csv(self.root, "results/r3/base_graph_summary.csv", contents)
            with self.subTest(mutation=mutation), self.assertRaises(StudiesError):
                self.service.overview("results/r3")

    def test_all_study_kinds_export_and_replay(self):
        for kind in ("r2", "r4", "r4_dual"):
            make_r2(self.root, source="results/" + kind, kind=kind)
            data = self.service.instance("results/" + kind, "g0000", 2)
            self.assertEqual(data["steps"][1]["selected"], [0])
            self.assertEqual(data["steps"][1]["candidates"], [1, 2])
            document = self.service.export_instance("results/" + kind, "g0000", 2)
            write_json(self.root, "replay.json", document)
            self.assertTrue(replay_instance_file(self.root / "replay.json")[1])
            if kind != "r2":
                self.assertEqual(len(self.service.overview("results/" + kind, {"k": "2"})["pairs"]), 2)
        make_r3(self.root)
        for direction, replica in ((None, None), (-1, 0), (1, 1)):
            doc = self.service.export_instance("results/r3", "r3-fixture-r0000", direction=direction, replica=replica)
            write_json(self.root, "replay.json", doc)
            self.assertTrue(replay_instance_file(self.root / "replay.json")[1])

    def test_wrong_instance_identity_witness_and_moves_rejected(self):
        _, graphs = make_r2(self.root)
        graph = graphs[0]
        graph["values"][1]["instance_id"] = "wrong"
        write_json(self.root, "results/r2/graphs/g0000.json", graph)
        with self.assertRaisesRegex(StudiesError, "identity"):
            self.service.instance("results/r2", "g0000", 2)
        _, graphs = make_r2(self.root)
        graphs[0]["values"][1]["optimum_selected"] = [0, 1]
        write_json(self.root, "results/r2/graphs/g0000.json", graphs[0])
        with self.assertRaisesRegex(StudiesError, "witness"):
            self.service.instance("results/r2", "g0000", 2)
        _, graph = make_r3(self.root)
        graph["chains"][0]["moves"][0] = [1, 0, 0, 1, 2]
        write_json(self.root, "results/r3/graphs/r3-fixture-r0000.json", graph)
        with self.assertRaisesRegex(StudiesError, "exchange"):
            self.service.instance("results/r3", "r3-fixture-r0000", direction=-1, replica=0)

    def test_explicit_directory_origin_and_unsafe_git_registration(self):
        make_r2(self.root)
        (self.root / "results/r2/graphs").rename(self.root / "graphs")
        write_json(self.root, "results/r2/graph_origin.json", {"kind": "directory", "path": str(self.root)})
        self.assertEqual(self.service.instance("results/r2", "g0000", 2)["values"]["greedy"], 3)
        for origin in ({"kind": "git", "commit": "main", "path": "results/r2"},
                       {"kind": "git", "commit": "a" * 40, "path": "../private"}):
            write_json(self.root, "results/r2/graph_origin.json", origin)
            with self.assertRaises(StudiesError):
                self.service.instance("results/r2", "g0000", 2)

    def test_invalid_filter_pagination_nonfinite_and_bounds(self):
        make_r2(self.root)
        for filters in ({"n": "NaN"}, {"loss_only": "yes"}, {"seed": "1"}):
            with self.assertRaises(StudiesError):
                self.service.records("results/r2", filters)
        with self.assertRaises(StudiesError):
            self.service.records("results/r2", offset=-1)
        rows, _ = make_r2(self.root, source="results/r4", kind="r4")
        rows[0]["upper"] = 1
        write_csv(self.root, "results/r4/budget_results.csv", rows)
        with self.assertRaises(StudiesError):
            self.service.overview("results/r4")

    def test_fixed_local_git_graph_origin(self):
        make_r2(self.root)
        (self.root / "results/r2/graphs").rename(self.root / "graphs")
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        git("init")
        git("add", "graphs")
        git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "saved graph fixture")
        commit = git("rev-parse", "HEAD")
        # Register a safe nonempty path under the fixed commit.
        (self.root / "evidence").mkdir()
        (self.root / "graphs").rename(self.root / "evidence/graphs")
        git("add", "-A")
        git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "artifact directory")
        commit = git("rev-parse", "HEAD")
        write_json(self.root, "results/r2/graph_origin.json", {"kind": "git", "commit": commit, "path": "evidence"})
        detail = self.service.instance("results/r2", "g0000", 2)
        self.assertTrue(detail["provenance"]["graph_origin"].startswith("git:" + commit))

    def test_registered_linked_origin_is_rejected(self):
        make_r2(self.root)
        (self.root / "results/r2/graphs").rename(self.root / "graphs")
        target = self.root / "origin-link"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(self.root)], check=True, capture_output=True)
        else:
            target.symlink_to(self.root, target_is_directory=True)
        try:
            write_json(self.root, "results/r2/graph_origin.json", {"kind": "directory", "path": str(target)})
            with self.assertRaisesRegex(StudiesError, "linked"):
                self.service.instance("results/r2", "g0000", 2)
        finally:
            if os.name == "nt":
                target.rmdir()
            else:
                target.unlink()

    def test_git_graph_overflowed_extra_certificate_field_is_rejected(self):
        _, graphs = make_r2(self.root, source="results/r4", kind="r4")
        evidence = self.root / "evidence"
        evidence.mkdir()
        (self.root / "results/r4/graphs").rename(evidence / "graphs")
        graphs[0]["values"][1]["extra_bound"] = "overflow"
        path = evidence / "graphs/g0000.json"
        path.write_text(json.dumps(graphs[0]).replace('"extra_bound": "overflow"', '"extra_bound": 1e999'), encoding="utf-8")
        for arguments in (("init",), ("add", "evidence"),
                          ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "overflowed saved certificate fixture")):
            subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        write_json(self.root, "results/r4/graph_origin.json", {"kind": "git", "commit": commit, "path": "evidence"})
        with self.assertRaisesRegex(StudiesError, "finite display range"):
            self.service.instance("results/r4", "g0000", 2)


if __name__ == "__main__":
    unittest.main()
