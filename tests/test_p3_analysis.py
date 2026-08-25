from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import plan_benchmark, run_benchmark
from maxcover.config import load_config


class P3AnalysisTests(unittest.TestCase):
    def test_bundled_randomized_plan_registers_1200_seeded_runs(self) -> None:
        config = load_config(ROOT / "configs" / "p3_randomized_greedy.json")
        plan = plan_benchmark(config)
        self.assertEqual(plan.instance_count, 40)
        self.assertEqual(dict(plan.runs_by_algorithm)["randomized_greedy_rcl3"], 1200)
        self.assertEqual(plan.algorithm_run_count, 1280)

    def test_bundled_multi_start_plan_has_restart_matrix(self) -> None:
        config = load_config(ROOT / "configs" / "p3_multi_start.json")
        plan = plan_benchmark(config)
        self.assertEqual(plan.instance_count, 40)
        self.assertEqual(
            dict(plan.runs_by_algorithm),
            {
                "bnb_reference": 40,
                "greedy_baseline": 40,
                "multi_start_r1": 400,
                "multi_start_r4": 400,
                "multi_start_r8": 400,
                "multi_start_r16": 400,
            },
        )
        self.assertEqual(plan.algorithm_run_count, 1680)

    def test_bundled_bnb_ablation_plan_has_five_variants_and_80_instances(self) -> None:
        config = load_config(ROOT / "configs" / "p3_bnb_ablation.json")
        plan = plan_benchmark(config)
        self.assertEqual(plan.instance_count, 80)
        self.assertEqual(plan.algorithm_run_count, 400)
        self.assertEqual(
            [algorithm.algorithm_id for algorithm in config.algorithms],
            [
                "bnb_baseline",
                "bnb_dedup",
                "bnb_dominance",
                "bnb_cardinality_bound",
                "bnb_enhanced",
            ],
        )

    def test_paired_search_comparison_is_generated_and_checksummed(self) -> None:
        config = {
            "schema_version": 3,
            "name": "paired BnB",
            "base_seed": 4,
            "repetitions": 2,
            "algorithms": [
                {
                    "id": "bnb_baseline",
                    "name": "branch_and_bound",
                    "options": {"time_limit_seconds": 2.0},
                },
                {
                    "id": "bnb_enhanced",
                    "name": "branch_and_bound_enhanced",
                    "options": {"time_limit_seconds": 2.0},
                },
            ],
            "cases": [
                {
                    "name": "tiny",
                    "family": "uniform",
                    "universe_size": 30,
                    "set_count": 9,
                    "k": 3,
                    "density": 0.2,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            output = root / "output"
            result = run_benchmark(config_path, output)
            with (output / "search_comparison.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                comparisons = list(csv.DictReader(handle))
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(len(result.rows), 4)
        self.assertEqual(len(comparisons), 2)
        self.assertTrue(
            all(
                row["baseline_coverage"] == row["enhanced_coverage"]
                for row in comparisons
            )
        )
        self.assertIn("search_comparison.csv", manifest["outputs"])

    def test_stochastic_summary_and_parallel_replay_are_deterministic(self) -> None:
        config = {
            "schema_version": 3,
            "name": "seeded randomized greedy",
            "base_seed": 12,
            "repetitions": 2,
            "algorithms": [
                {"id": "greedy_baseline", "name": "greedy"},
                {
                    "id": "randomized_greedy_rcl3",
                    "name": "randomized_greedy",
                    "algorithm_seeds": [0, 1, 2, 3],
                    "options": {"rcl_size": 3},
                },
            ],
            "cases": [
                {
                    "name": "tiny",
                    "family": "uniform",
                    "universe_size": 40,
                    "set_count": 10,
                    "k": 4,
                    "density": 0.2,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            serial = run_benchmark(config_path, root / "serial", workers=1)
            parallel = run_benchmark(config_path, root / "parallel", workers=4)
            with (root / "serial" / "stochastic_summary.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                stochastic = list(csv.DictReader(handle))
            manifest = json.loads(
                (root / "serial" / "manifest.json").read_text(encoding="utf-8")
            )

        def stable(result):
            return [
                (
                    row.run_id,
                    row.instance_id,
                    row.algorithm_id,
                    row.algorithm_seed,
                    row.coverage,
                    row.selected,
                    row.algorithm_metadata,
                )
                for row in result.rows
            ]

        self.assertEqual(stable(serial), stable(parallel))
        self.assertEqual(len(stochastic), 2)
        self.assertTrue(all(row["seed_count"] == "4" for row in stochastic))
        self.assertTrue(
            all(
                abs(
                    float(row["better_than_greedy_rate"])
                    + float(row["equal_to_greedy_rate"])
                    + float(row["worse_than_greedy_rate"])
                    - 1.0
                )
                < 1e-9
                for row in stochastic
            )
        )
        self.assertIn("stochastic_summary.csv", manifest["outputs"])


if __name__ == "__main__":
    unittest.main()
