"""Freeze the benchmark API and the execution seams used before extraction."""

from __future__ import annotations

import dataclasses
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maxcover.benchmark as benchmark


# Audited direct imports plus the two legacy patch attributes. Extra module
# attributes are not prohibited, and this is not a wildcard-import contract.
COMPATIBILITY_EXPORTS = (
    "BenchmarkPlan",
    "REPORT_FILENAMES",
    "RUNNER_OWNED_FILENAMES",
    "_bnb_node_reduction_statistics",
    "_canonical_instance_records",
    "_canonical_run_records",
    "_case_seed",
    "_censored_runtime_statistics",
    "_confidence_interval_statistics",
    "_descriptive_statistics",
    "_execute_task",
    "_gap_clustering_association_statistics",
    "_gap_density_association_statistics",
    "_gap_overlap_association_statistics",
    "_greedy_failure_statistics",
    "_heuristic_exact_runtime_ratio_statistics",
    "_instance_record",
    "_instances_for_config",
    "_linear_quantile",
    "_local_search_recovery_statistics",
    "_local_search_remaining_gap_statistics",
    "_normalize_optima",
    "_quality_runtime_pareto_statistics",
    "_reference_censoring_bias_statistics",
    "_reference_coverage_statistics",
    "_reference_cutoff_sensitivity_statistics",
    "_reference_status_records",
    "_rows_for_instance",
    "_run_algorithms",
    "_runtime_k_association_statistics",
    "_runtime_set_count_association_statistics",
    "_search_nodes_dominated_ratio_association_statistics",
    "_student_t_critical_95",
    "_tasks_for_config",
    "plan_benchmark",
    "replay_instance_file",
    "run_benchmark",
    "summarize_benchmark",
)

PUBLIC_SIGNATURES = {
    "BenchmarkPlan": (
        "(name: 'str', case_ids: 'tuple[str, ...]', repetitions: 'int', "
        "instance_count: 'int', algorithm_run_count: 'int', "
        "runs_by_algorithm: 'tuple[tuple[str, int], ...]') -> None"
    ),
    "plan_benchmark": "(config: 'ExperimentConfig') -> 'BenchmarkPlan'",
    "replay_instance_file": (
        "(path: 'Path', algorithm: 'str | None' = None) -> 'tuple[Solution, bool | None]'"
    ),
    "run_benchmark": (
        "(config_path: 'Path', output_dir: 'Path', *, workers: 'int' = 1, "
        "force: 'bool' = False, expected_config_hash: 'str | None' = None, "
        "checkpoint_interval: 'int' = 1) -> 'BenchmarkResult'"
    ),
    "summarize_benchmark": (
        "(config_path: 'Path', output_dir: 'Path') -> 'BenchmarkResult'"
    ),
}

REPORT_FILENAMES = (
    "results_summary.md", "gap_by_family.svg", "runtime_by_algorithm.svg",
    "gap_by_case.svg", "gap_vs_structural_parameter.svg", "local_search_recovery.svg",
    "quality_runtime_pareto.svg", "runtime_scaling.svg", "node_scaling.svg",
    "timeout_by_case.svg", "reference_coverage_by_case.svg",
)
RUNNER_OWNED_FILENAMES = (
    "raw_results.csv", "instances.csv", "summary.csv", "descriptive_statistics.csv",
    "confidence_interval_statistics.csv", "censored_runtime_statistics.csv",
    "reference_status.csv", "reference_coverage_statistics.csv",
    "reference_censoring_bias_statistics.csv", "reference_cutoff_sensitivity_statistics.csv",
    "greedy_failure_statistics.csv", "local_search_recovery_statistics.csv",
    "local_search_remaining_gap_statistics.csv", "heuristic_exact_runtime_ratio_statistics.csv",
    "bnb_node_reduction_statistics.csv", "quality_runtime_pareto_statistics.csv",
    "gap_density_association_statistics.csv", "gap_overlap_association_statistics.csv",
    "gap_clustering_association_statistics.csv", "runtime_set_count_association_statistics.csv",
    "runtime_k_association_statistics.csv", "search_nodes_dominated_ratio_association_statistics.csv",
    "search_comparison.csv", "stochastic_summary.csv", "manifest.json", *REPORT_FILENAMES,
)


class BenchmarkCompatibilityTests(unittest.TestCase):
    def test_recorded_facade_symbols_remain_directly_importable(self) -> None:
        namespace: dict[str, object] = {}
        exec("from maxcover.benchmark import " + ", ".join(COMPATIBILITY_EXPORTS), namespace)
        for name in COMPATIBILITY_EXPORTS:
            with self.subTest(name=name):
                self.assertIs(namespace[name], getattr(benchmark, name))
                if name not in {"REPORT_FILENAMES", "RUNNER_OWNED_FILENAMES"}:
                    self.assertTrue(callable(namespace[name]))

    def test_public_callable_names_and_signatures_are_frozen(self) -> None:
        for name, signature in PUBLIC_SIGNATURES.items():
            with self.subTest(name=name):
                value = getattr(benchmark, name)
                self.assertEqual(value.__name__, name)
                self.assertEqual(value.__qualname__, name)
                self.assertEqual(value.__module__, "maxcover.benchmark")
                self.assertEqual(str(inspect.signature(value)), signature)

    def test_runner_owned_and_report_filename_order_is_frozen(self) -> None:
        self.assertEqual(benchmark.REPORT_FILENAMES, REPORT_FILENAMES)
        self.assertEqual(benchmark.RUNNER_OWNED_FILENAMES, RUNNER_OWNED_FILENAMES)

    def test_benchmark_plan_field_order_defaults_and_immutability_are_frozen(self) -> None:
        fields = ("name", "case_ids", "repetitions", "instance_count",
                  "algorithm_run_count", "runs_by_algorithm")
        cls = benchmark.BenchmarkPlan
        self.assertEqual(cls.__slots__, fields)
        self.assertEqual(cls.__match_args__, fields)
        self.assertTrue(cls.__dataclass_params__.frozen)
        self.assertEqual(tuple(field.name for field in dataclasses.fields(cls)), fields)
        for field in dataclasses.fields(cls):
            with self.subTest(field=field.name):
                self.assertIs(field.default, dataclasses.MISSING)
                self.assertIs(field.default_factory, dataclasses.MISSING)
                self.assertTrue(field.init)
                self.assertFalse(field.kw_only)
        plan = cls("fixture", ("case_b", "case_a"), 3, 6, 12,
                   (("greedy", 6), ("exact", 6)))
        self.assertFalse(hasattr(plan, "__dict__"))
        self.assertEqual(plan.__getstate__(), ["fixture", ("case_b", "case_a"), 3, 6, 12,
                                              (("greedy", 6), ("exact", 6))])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            plan.name = "changed"

    def test_saved_plan_pickles_load_with_public_identity_in_a_new_interpreter(self) -> None:
        fixtures = ROOT / "tests" / "fixtures" / "benchmark_compatibility"
        script = """
import dataclasses
import json
import pickle
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import maxcover
import maxcover.benchmark as benchmark
results = []
for filename in sys.argv[2:]:
    value = pickle.loads(Path(filename).read_bytes())
    assert type(value) is maxcover.BenchmarkPlan is benchmark.BenchmarkPlan
    assert type(value).__module__ == 'maxcover.benchmark'
    assert type(value).__qualname__ == 'BenchmarkPlan'
    assert dataclasses.astuple(value) == (
        'fixture', ('case_b', 'case_a'), 3, 6, 12, (('greedy', 6), ('exact', 6))
    )
    results.append(Path(filename).name)
print(json.dumps(results))
"""
        filenames = [f"benchmark_plan_protocol{protocol}.pickle" for protocol in (4, 5)]
        completed = subprocess.run(
            [sys.executable, "-c", script, str(ROOT / "src"),
             *(str(fixtures / name) for name in filenames)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout), filenames)


class BenchmarkExecutionSeamTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_path = self.root / "config.json"
        self.output = self.root / "output"
        self.config_path.write_text(json.dumps({
            "schema_version": 3, "name": "benchmark seam fixture", "base_seed": 17,
            "repetitions": 1, "algorithms": [{"name": "greedy"}],
            "cases": [{"name": "tiny", "family": "uniform", "universe_size": 6,
                       "set_count": 4, "k": 2, "density": 0.5}],
        }), encoding="utf-8")

    def test_serial_runner_uses_the_facade_execute_task_attribute(self) -> None:
        # The legacy helper is deliberately retained, but is not the runner's
        # execution hook. A valid run must reach _execute_task instead.
        with patch.object(benchmark, "_run_algorithms") as legacy:
            with patch.object(benchmark, "_execute_task",
                              side_effect=KeyboardInterrupt("execution seam reached")) as execute:
                with self.assertRaisesRegex(KeyboardInterrupt, "execution seam reached"):
                    benchmark.run_benchmark(self.config_path, self.output, workers=1)
        execute.assert_called_once()
        legacy.assert_not_called()
        task = execute.call_args.args[0]
        self.assertEqual((task.case_id, task.repetition, task.algorithm), ("tiny", 0, "greedy"))

    def test_changed_configuration_hash_is_rejected_before_execution_or_output(self) -> None:
        with patch.object(benchmark, "_execute_task") as execute:
            with self.assertRaisesRegex(ValueError, "configuration changed after preflight"):
                benchmark.run_benchmark(self.config_path, self.output,
                                        expected_config_hash="f" * 64)
        execute.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_parallel_dispatch_uses_the_facade_execution_hook(self) -> None:
        # Observe the scheduling argument without pretending a Mock is
        # pickleable. The existing reproducibility tests exercise real spawn.
        with patch.object(benchmark, "ProcessPoolExecutor") as factory:
            pool = factory.return_value
            pool.map.side_effect = lambda function, tasks: map(function, tasks)
            with patch.object(benchmark, "_execute_task",
                              side_effect=KeyboardInterrupt("parallel seam reached")) as execute:
                with self.assertRaisesRegex(KeyboardInterrupt, "parallel seam reached"):
                    benchmark.run_benchmark(self.config_path, self.output, workers=2)
            factory.assert_called_once()
            self.assertEqual(factory.call_args.kwargs["mp_context"].get_start_method(), "spawn")
            pool.map.assert_called_once()
            self.assertIs(pool.map.call_args.args[0], execute)
            execute.assert_called_once()
            pool.shutdown.assert_called_once_with(wait=True, cancel_futures=True)

    def test_invalid_execution_options_are_rejected_before_loading_or_output(self) -> None:
        for options in ({"workers": 0}, {"workers": True},
                        {"checkpoint_interval": 0}, {"checkpoint_interval": True}):
            with self.subTest(options=options):
                with patch.object(benchmark, "_execute_task") as execute:
                    with self.assertRaises(ValueError):
                        benchmark.run_benchmark(self.root / "missing.json", self.output, **options)
                execute.assert_not_called()
                self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
