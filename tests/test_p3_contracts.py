from __future__ import annotations

import math
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import ALGORITHMS
from maxcover.benchmark import plan_benchmark, run_benchmark
from maxcover.config import ConfigurationError, parse_config
from maxcover.contracts import (
    AlgorithmRunOptions,
    GreedyFailureRecord,
    OptionSpec,
    RunRecord,
    SummaryRecord,
)
from maxcover.model import Solution, SolutionStatus


def _config(algorithms: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "P3 contracts",
        "repetitions": 1,
        "algorithms": algorithms,
        "cases": [
            {
                "name": "tiny",
                "family": "uniform",
                "universe_size": 10,
                "set_count": 4,
                "k": 2,
                "density": 0.2,
            }
        ],
    }


class P3ContractTests(unittest.TestCase):
    def test_solution_metadata_uses_shared_envelope_and_rejects_nan(self) -> None:
        solution = Solution(
            algorithm="greedy",
            selected=(0,),
            feasible_value=1,
            runtime_seconds=0.0,
            status=SolutionStatus.FEASIBLE,
        )
        self.assertEqual(solution.metadata["schema_version"], 1)
        self.assertEqual(solution.metadata["termination"], "completed")
        with self.assertRaises(TypeError):
            solution.metadata["termination"] = "error"
        with self.assertRaises(ValueError):
            Solution(
                algorithm="greedy",
                selected=(0,),
                feasible_value=1,
                runtime_seconds=0.0,
                status=SolutionStatus.FEASIBLE,
                metadata={
                    "schema_version": 1,
                    "termination": "completed",
                    "search": {"bad": math.nan},
                    "trajectory": [],
                },
            )

    def test_algorithm_options_preserve_common_fields_and_generic_values(self) -> None:
        options = AlgorithmRunOptions(
            time_limit_seconds=2,
            max_set_count=9,
            values={"strategy": "dynamic"},
        )
        self.assertEqual(options.time_limit_seconds, 2.0)
        self.assertEqual(options.get("max_set_count"), 9)
        self.assertEqual(options.get("strategy"), "dynamic")
        with self.assertRaises(TypeError):
            options.values["strategy"] = "static"

        specification = OptionSpec(
            (str,), "string", choices=frozenset({"static", "dynamic"})
        )
        self.assertEqual(
            specification.validate("algorithm", "strategy", "dynamic"),
            "dynamic",
        )
        with self.assertRaises(ValueError):
            specification.validate("algorithm", "strategy", "unknown")

    def test_config_v3_accepts_ids_and_validates_seed_arrays(self) -> None:
        seeded_greedy = replace(ALGORITHMS["greedy"], uses_random_seed=True)
        with patch.dict(ALGORITHMS, {"greedy": seeded_greedy}):
            config = parse_config(
                _config(
                    [
                        {
                            "id": "greedy_variant",
                            "name": "greedy",
                            "algorithm_seeds": [3, 7],
                        }
                    ]
                )
            )
        self.assertEqual(config.schema_version, 3)
        self.assertEqual(config.algorithms[0].algorithm_id, "greedy_variant")
        self.assertEqual(config.algorithms[0].algorithm_seeds, (3, 7))

        for seeds in ([], [1, 1], [True]):
            with self.subTest(seeds=seeds), self.assertRaises(ConfigurationError):
                parse_config(
                    _config(
                        [
                            {
                                "id": "greedy_variant",
                                "name": "greedy",
                                "algorithm_seeds": seeds,
                            }
                        ]
                    )
                )

        with self.assertRaisesRegex(ConfigurationError, "rejects algorithm_seeds"):
            parse_config(
                _config(
                    [
                        {
                            "id": "deterministic_greedy",
                            "name": "greedy",
                            "algorithm_seeds": [3],
                        }
                    ]
                )
            )

    def test_seeded_execution_expands_ids_records_and_resume(self) -> None:
        seeded_greedy = replace(ALGORITHMS["greedy"], uses_random_seed=True)
        value = _config(
            [
                {
                    "id": "seeded_greedy",
                    "name": "greedy",
                    "algorithm_seeds": [3, 7],
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(value), encoding="utf-8")
            output = root / "output"
            with patch.dict(ALGORITHMS, {"greedy": seeded_greedy}):
                config = parse_config(value)
                self.assertEqual(plan_benchmark(config).algorithm_run_count, 2)
                first = run_benchmark(config_path, output)
                resumed = run_benchmark(config_path, output)
                self.assertEqual(first.greedy_failure_statistics, ())
                self.assertEqual(resumed.greedy_failure_statistics, ())
                self.assertEqual(
                    (output / "greedy_failure_statistics.csv").read_text(
                        encoding="utf-8"
                    ),
                    ",".join(GreedyFailureRecord.CSV_FIELDS) + "\n",
                )

        self.assertEqual([row.algorithm_seed for row in first.rows], [3, 7])
        self.assertEqual(len({row.run_id for row in first.rows}), 2)
        self.assertEqual(
            [row.run_id for row in first.rows],
            [row.run_id for row in resumed.rows],
        )
        self.assertTrue(
            all(
                json.loads(row.algorithm_options)["algorithm_seed"]
                == row.algorithm_seed
                for row in first.rows
            )
        )

    def test_record_v3_rows_migrate_to_v4_metadata_defaults(self) -> None:
        current = RunRecord(
            case="case",
            repetition=0,
            seed=1,
            family="uniform",
            universe_size=4,
            set_count=2,
            k=1,
            parameters="{}",
            algorithm="greedy",
            algorithm_options="{}",
            status=SolutionStatus.FEASIBLE,
            coverage=1,
            best_bound=None,
            optimum=None,
            optimality_gap=None,
            runtime_seconds=0.0,
            nodes_or_iterations=1,
            selected=(0,),
        )
        legacy = {name: str(value) for name, value in current.to_csv_row().items()}
        for field in ("algorithm_id", "algorithm_seed", "algorithm_metadata"):
            legacy.pop(field)
        legacy["schema_version"] = "3"
        restored = RunRecord.from_csv_row(legacy)
        self.assertEqual(restored.algorithm_id, "greedy")
        self.assertIsNone(restored.algorithm_seed)
        self.assertIn('"schema_version":1', restored.algorithm_metadata)

        summary = SummaryRecord(
            case="case",
            family="uniform",
            algorithm="greedy",
            runs=1,
            mean_coverage=1.0,
            mean_optimality_gap=None,
            max_optimality_gap=None,
            mean_runtime_seconds=0.0,
            timeouts=0,
        )
        legacy_summary = {
            name: str(value) for name, value in summary.to_csv_row().items()
        }
        legacy_summary.pop("algorithm_id")
        legacy_summary["schema_version"] = "3"
        restored_summary = SummaryRecord.from_csv_row(legacy_summary)
        self.assertEqual(restored_summary.algorithm_id, "greedy")


if __name__ == "__main__":
    unittest.main()
