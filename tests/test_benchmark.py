from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import _rows_for_instance, run_benchmark
from maxcover.config import ExperimentConfig
from maxcover.contracts import (
    BenchmarkResult,
    CensoredRuntimeRecord,
    ConfidenceIntervalRecord,
    DescriptiveStatisticsRecord,
    GreedyFailureRecord,
    HeuristicExactRuntimeRatioRecord,
    InstanceRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    RunRecord,
    SummaryRecord,
)
from maxcover.model import MaximumCoverageInstance, Solution, SolutionStatus


class BenchmarkTests(unittest.TestCase):
    def test_only_optimal_status_supplies_reference_optimum(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=5,
            sets=(0b00011, 0b01100, 0b10000),
            k=1,
        )
        timed_out = Solution(
            algorithm="timed_out_exact",
            selected=(0,),
            feasible_value=2,
            runtime_seconds=0.01,
            status=SolutionStatus.TIMEOUT,
            best_bound=5,
        )
        feasible = Solution(
            algorithm="heuristic",
            selected=(1,),
            feasible_value=2,
            runtime_seconds=0.001,
            status=SolutionStatus.FEASIBLE,
        )
        rows = _rows_for_instance(
            case_name="status",
            repetition=0,
            instance=instance,
            solutions=[timed_out, feasible],
        )
        self.assertTrue(all(row.optimum is None for row in rows))
        self.assertTrue(all(row.optimality_gap is None for row in rows))

        optimal = Solution(
            algorithm="optimal_exact",
            selected=(0,),
            feasible_value=2,
            runtime_seconds=0.02,
            status=SolutionStatus.OPTIMAL,
            best_bound=2,
        )
        rows = _rows_for_instance(
            case_name="status",
            repetition=0,
            instance=instance,
            solutions=[timed_out, feasible, optimal],
        )
        self.assertTrue(all(row.optimum == 2 for row in rows))

    def test_smoke_run_writes_all_artifacts(self) -> None:
        config = {
            "schema_version": 2,
            "name": "test",
            "base_seed": 10,
            "repetitions": 1,
            "algorithms": [
                {
                    "name": "brute_force",
                    "options": {"time_limit_seconds": 1.0, "max_set_count": 12},
                },
                {
                    "name": "branch_and_bound",
                    "options": {"time_limit_seconds": 1.0},
                },
                {"name": "greedy"},
                {"name": "local_search"},
            ],
            "cases": [
                {
                    "name": "tiny",
                    "family": "uniform",
                    "universe_size": 20,
                    "set_count": 8,
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
            self.assertIsInstance(result, BenchmarkResult)
            self.assertIsInstance(result.config, ExperimentConfig)
            self.assertEqual(len(result.rows), 4)
            self.assertTrue(all(isinstance(row, RunRecord) for row in result.rows))
            self.assertTrue(
                all(isinstance(row, SummaryRecord) for row in result.summary)
            )
            self.assertTrue(
                all(
                    isinstance(row, DescriptiveStatisticsRecord)
                    for row in result.descriptive_statistics
                )
            )
            self.assertEqual(len(result.confidence_interval_statistics), 12)
            self.assertTrue(
                all(
                    isinstance(row, ConfidenceIntervalRecord)
                    for row in result.confidence_interval_statistics
                )
            )
            self.assertEqual(len(result.censored_runtime_statistics), 4)
            self.assertTrue(
                all(
                    isinstance(row, CensoredRuntimeRecord)
                    for row in result.censored_runtime_statistics
                )
            )
            self.assertEqual(len(result.greedy_failure_statistics), 1)
            self.assertTrue(
                all(
                    isinstance(row, GreedyFailureRecord)
                    for row in result.greedy_failure_statistics
                )
            )
            self.assertEqual(len(result.local_search_recovery_statistics), 1)
            self.assertTrue(
                all(
                    isinstance(row, LocalSearchRecoveryRecord)
                    for row in result.local_search_recovery_statistics
                )
            )
            self.assertEqual(len(result.instances), 1)
            self.assertIsInstance(result.instances[0], InstanceRecord)
            self.assertEqual(result.output_dir, output)
            options = {row.algorithm: json.loads(row.algorithm_options) for row in result.rows}
            self.assertEqual(
                options["brute_force"],
                {"time_limit_seconds": 1.0, "max_set_count": 12},
            )
            self.assertEqual(
                options["branch_and_bound"], {"time_limit_seconds": 1.0}
            )
            self.assertEqual(options["greedy"], {})
            self.assertEqual(options["local_search"], {})
            for filename in (
                "raw_results.csv",
                "instances.csv",
                "summary.csv",
                "descriptive_statistics.csv",
                "confidence_interval_statistics.csv",
                "censored_runtime_statistics.csv",
                "greedy_failure_statistics.csv",
                "heuristic_exact_runtime_ratio_statistics.csv",
                "local_search_recovery_statistics.csv",
                "local_search_remaining_gap_statistics.csv",
                "results_summary.md",
                "gap_by_family.svg",
                "runtime_by_algorithm.svg",
                "gap_by_case.svg",
                "gap_vs_structural_parameter.svg",
                "local_search_recovery.svg",
                "quality_runtime_pareto.svg",
                "runtime_scaling.svg",
                "node_scaling.svg",
                "timeout_by_case.svg",
                "manifest.json",
            ):
                self.assertTrue((output / filename).is_file(), filename)
            chart_expectations = {
                "gap_by_case.svg": (
                    "source=descriptive_statistics.csv",
                    "样本=1 实例种子",
                ),
                "gap_vs_structural_parameter.svg": (
                    "sources=gap_*_association_statistics.csv",
                    "状态=",
                ),
                "local_search_recovery.svg": (
                    "source=local_search_recovery_statistics.csv",
                    "样本=0 对应的实例种子",
                ),
                "quality_runtime_pareto.svg": (
                    "source=quality_runtime_pareto_statistics.csv",
                    "样本=1 实例种子",
                ),
                "runtime_scaling.svg": (
                    "sources=runtime_set_count_association_statistics.csv + runtime_k_association_statistics.csv",
                    "样本=1 实例种子",
                    "未完成实例=0",
                ),
                "node_scaling.svg": (
                    "source=search_nodes_dominated_ratio_association_statistics.csv",
                    "来源：搜索节点与结构参数关联统计",
                ),
                "timeout_by_case.svg": (
                    "source=censored_runtime_statistics.csv",
                    "样本=1 实例种子",
                    "右删失=0 次/0 个实例",
                    "平均删失时间=blank（仅作诊断）",
                ),
            }
            for filename, markers in chart_expectations.items():
                chart = (output / filename).read_text(encoding="utf-8")
                for marker in markers:
                    self.assertIn(marker, chart, f"{filename}: {marker}")
                visible_chart = re.sub(r"<desc>.*?</desc>", "", chart, flags=re.DOTALL)
                self.assertNotRegex(
                    visible_chart,
                    r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b",
                    f"{filename} exposes an underscored identifier in visible text",
                )
            report = (output / "results_summary.md").read_text(encoding="utf-8")
            self.assertIn(
                "## P5.2 mean/max relative optimality gap",
                report,
            )
            self.assertIn(
                "## P5.3 95% confidence intervals for instance means",
                report,
            )
            self.assertIn(
                "## P5.3 censored-runtime diagnostics",
                report,
            )

            with (output / "raw_results.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(tuple(next(csv.reader(handle))), RunRecord.CSV_FIELDS)
            with (output / "summary.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(csv.reader(handle).__next__()), SummaryRecord.CSV_FIELDS
                )
            with (output / "descriptive_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    DescriptiveStatisticsRecord.CSV_FIELDS,
                )
            with (output / "confidence_interval_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    ConfidenceIntervalRecord.CSV_FIELDS,
                )
            with (output / "censored_runtime_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    CensoredRuntimeRecord.CSV_FIELDS,
                )
            with (output / "greedy_failure_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    GreedyFailureRecord.CSV_FIELDS,
                )
            with (
                output / "heuristic_exact_runtime_ratio_statistics.csv"
            ).open(encoding="utf-8", newline="") as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    HeuristicExactRuntimeRatioRecord.CSV_FIELDS,
                )
            with (output / "local_search_recovery_statistics.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    LocalSearchRecoveryRecord.CSV_FIELDS,
                )
            with (
                output / "local_search_remaining_gap_statistics.csv"
            ).open(encoding="utf-8", newline="") as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))),
                    LocalSearchRemainingGapRecord.CSV_FIELDS,
                )
            with (output / "instances.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(
                    tuple(next(csv.reader(handle))), InstanceRecord.CSV_FIELDS
                )


if __name__ == "__main__":
    unittest.main()
