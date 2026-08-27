"""Functional and contract tests for the deterministic lazy-greedy variant."""

from __future__ import annotations

import json
import csv
import hashlib
import importlib.util
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import ALGORITHMS, greedy, lazy_greedy
from maxcover.benchmark import plan_benchmark, run_benchmark
from maxcover.config import load_config
from maxcover.contracts import AlgorithmRunOptions
from maxcover.generators import (
    adversarial_greedy_trap,
    clustered,
    dominated_heavy,
    duplicate_heavy,
    fixed_size,
    high_overlap,
    long_tail,
    mixed_cluster,
    uniform_random,
)
from maxcover.model import MaximumCoverageInstance


def _load_output_validator():
    path = ROOT / ".github" / "scripts" / "validate_benchmark_output.py"
    spec = importlib.util.spec_from_file_location("lazy_output_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["lazy_output_validator"] = module
    spec.loader.exec_module(module)
    return module


def _mask(elements: range | tuple[int, ...]) -> int:
    value = 0
    for element in elements:
        value |= 1 << element
    return value


def _dense_greedy(instance: MaximumCoverageInstance) -> tuple[tuple[int, ...], int]:
    """Independent dense reference for the classical greedy contract."""

    selected: list[int] = []
    covered = 0
    available = set(range(instance.set_count))
    for _ in range(instance.k):
        best = max(
            available,
            key=lambda index: (
                (instance.sets[index] & ~covered).bit_count(),
                -index,
            ),
        )
        selected.append(best)
        covered |= instance.sets[best]
        available.remove(best)
    return tuple(selected), covered.bit_count()


def _reference_instances() -> tuple[MaximumCoverageInstance, ...]:
    return (
        MaximumCoverageInstance(
            universe_size=8,
            sets=(
                _mask(range(0, 4)),
                _mask(range(4, 8)),
                _mask(range(0, 3)),
                _mask(range(4, 7)),
                0,
            ),
            k=3,
            family="custom",
        ),
        MaximumCoverageInstance(
            universe_size=4,
            sets=(0, 0, 0),
            k=3,
            family="custom",
        ),
        uniform_random(
            universe_size=30,
            set_count=12,
            k=4,
            density=0.2,
            seed=101,
        ),
        high_overlap(
            universe_size=30,
            set_count=12,
            k=4,
            core_fraction=0.3,
            core_probability=0.75,
            peripheral_probability=0.08,
            seed=102,
        ),
        clustered(
            universe_size=30,
            set_count=12,
            k=4,
            clusters=3,
            within_probability=0.65,
            outside_probability=0.04,
            seed=103,
        ),
        fixed_size(
            universe_size=30,
            set_count=12,
            k=4,
            set_size=6,
            unique_sets=True,
            seed=104,
        ),
        long_tail(
            universe_size=30,
            set_count=12,
            k=4,
            set_size=6,
            gamma=1.5,
            seed=105,
        ),
        duplicate_heavy(
            universe_size=30,
            base_set_count=6,
            k=4,
            set_size=6,
            copy_factor=2,
            seed=106,
        ),
        dominated_heavy(
            anchor_count=5,
            anchor_size=6,
            k=3,
            child_count=2,
            seed=107,
        ),
        mixed_cluster(
            universe_size=32,
            set_count=12,
            k=4,
            clusters=4,
            set_size=6,
            bridge_fraction=0.5,
            seed=108,
        ),
        adversarial_greedy_trap(
            block_size=12,
            distractor_count=4,
            seed=109,
        ),
        adversarial_greedy_trap(
            block_size=12,
            distractor_count=4,
            construction_version=2,
            trap_count=9,
            seed=110,
            coupling_seed=111,
        ),
    )


class LazyGreedyTests(unittest.TestCase):
    def test_matches_an_independent_dense_reference(self) -> None:
        for instance in _reference_instances():
            with self.subTest(family=instance.family, seed=instance.seed):
                expected_selected, expected_coverage = _dense_greedy(instance)
                actual = lazy_greedy(instance)
                trajectory = actual.metadata["trajectory"]
                observed_sequence = tuple(
                    point["selected_index"] for point in trajectory
                )
                self.assertEqual(observed_sequence, expected_selected)
                self.assertEqual(actual.selected, tuple(sorted(expected_selected)))
                self.assertEqual(actual.coverage, expected_coverage)

    def test_matches_reference_on_a_seeded_uniform_corpus(self) -> None:
        for seed in range(250):
            set_count = 4 + (7 * seed) % 27
            instance = uniform_random(
                universe_size=8 + (11 * seed) % 113,
                set_count=set_count,
                k=1 + (13 * seed) % set_count,
                density=0.03 + (seed % 15) * 0.03,
                seed=50_000 + seed,
            )
            expected_selected, expected_coverage = _dense_greedy(instance)
            actual = lazy_greedy(instance)
            observed_sequence = tuple(
                point["selected_index"] for point in actual.metadata["trajectory"]
            )
            with self.subTest(seed=seed):
                self.assertEqual(observed_sequence, expected_selected)
                self.assertEqual(actual.coverage, expected_coverage)

    def test_metadata_and_work_accounting_are_deterministic(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=20,
            sets=(
                _mask(range(0, 10)),
                _mask(range(10, 20)),
                _mask(range(0, 9)),
                _mask(range(10, 19)),
                _mask(range(1, 8)),
                _mask(range(11, 18)),
            ),
            k=2,
            family="custom",
        )
        first = lazy_greedy(instance)
        second = lazy_greedy(instance)
        search = first.metadata["search"]
        self.assertEqual(first.selected, second.selected)
        self.assertEqual(first.coverage, second.coverage)
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(search["marginal_evaluations"], first.nodes_or_iterations)
        self.assertEqual(
            search["marginal_evaluations"],
            search["initial_candidate_count"] + search["priority_queue_pops"],
        )
        self.assertEqual(search["selected_count"], instance.k)
        self.assertEqual(len(first.metadata["trajectory"]), instance.k)
        cumulative = 0
        for point in first.metadata["trajectory"]:
            self.assertGreaterEqual(point["marginal_evaluations"], cumulative)
            cumulative = point["marginal_evaluations"]
        dense_evaluations = instance.set_count * instance.k - (
            instance.k * (instance.k - 1) // 2
        )
        self.assertEqual(greedy(instance).nodes_or_iterations, dense_evaluations)
        self.assertEqual(search["initial_candidate_count"], instance.set_count)
        self.assertLess(first.nodes_or_iterations, greedy(instance).nodes_or_iterations)

    def test_registry_exposes_lazy_greedy_as_deterministic_without_options(self) -> None:
        specification = ALGORITHMS["lazy_greedy"]
        self.assertFalse(specification.exact)
        self.assertFalse(specification.uses_random_seed)
        self.assertEqual(specification.version, 2)
        self.assertEqual(specification.option_values(AlgorithmRunOptions()), {})
        instance = _reference_instances()[0]
        result = specification.run(instance, AlgorithmRunOptions())
        self.assertEqual(result.algorithm, "lazy_greedy")
        with self.assertRaisesRegex(ValueError, "does not support"):
            specification.run(
                instance,
                AlgorithmRunOptions(time_limit_seconds=1.0),
            )

    def test_bundled_configuration_has_a_paired_reference_plan(self) -> None:
        config = load_config(ROOT / "configs" / "p3_lazy_greedy.json")
        plan = plan_benchmark(config)
        self.assertEqual(plan.instance_count, 40)
        self.assertEqual(plan.algorithm_run_count, 120)
        self.assertEqual(
            dict(plan.runs_by_algorithm),
            {"bnb_reference": 40, "greedy_baseline": 40, "lazy_greedy": 40},
        )

    def test_benchmark_preserves_greedy_and_lazy_greedy_results(self) -> None:
        value = {
            "schema_version": 3,
            "name": "lazy greedy integration",
            "base_seed": 2201,
            "repetitions": 2,
            "algorithms": [
                {"id": "greedy_baseline", "name": "greedy"},
                {"id": "lazy_greedy", "name": "lazy_greedy"},
            ],
            "cases": [
                {
                    "name": "tiny",
                    "family": "uniform",
                    "universe_size": 40,
                    "set_count": 12,
                    "k": 4,
                    "density": 0.2,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(value), encoding="utf-8")
            output = root / "output"
            result = run_benchmark(config_path, output, workers=2)

            by_instance: dict[str, dict[str, object]] = defaultdict(dict)
            for row in result.rows:
                if row.algorithm in {"greedy", "lazy_greedy"}:
                    by_instance[row.instance_id][row.algorithm] = row
            report = (output / "results_summary.md").read_text(encoding="utf-8")

        self.assertEqual(len(by_instance), 2)
        for rows in by_instance.values():
            self.assertEqual(rows["greedy"].coverage, rows["lazy_greedy"].coverage)
            self.assertEqual(rows["greedy"].selected, rows["lazy_greedy"].selected)
        self.assertIn("lazy_greedy", report)

    def test_output_validator_rejects_lazy_counter_tampering(self) -> None:
        value = {
            "schema_version": 3,
            "name": "lazy greedy validator",
            "base_seed": 2202,
            "repetitions": 1,
            "algorithms": [
                {
                    "id": "bnb_reference",
                    "name": "branch_and_bound_enhanced",
                    "options": {"time_limit_seconds": 10.0},
                },
                {"id": "greedy_baseline", "name": "greedy"},
                {"id": "lazy_greedy", "name": "lazy_greedy"},
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
            config_path.write_text(json.dumps(value), encoding="utf-8")
            output = root / "output"
            run_benchmark(config_path, output, workers=1)

            raw_path = output / "raw_results.csv"
            with raw_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                if row["algorithm"] == "lazy_greedy":
                    metadata = json.loads(row["algorithm_metadata"])
                    metadata["search"]["priority_queue_pops"] += 1
                    row["algorithm_metadata"] = json.dumps(
                        metadata,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    break
            else:
                self.fail("the benchmark did not produce a Lazy Greedy row")
            with raw_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = raw_path.read_bytes()
            manifest["outputs"]["raw_results.csv"] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

            validator = _load_output_validator()
            with self.assertRaisesRegex(ValueError, "marginal evaluations"):
                validator.validate(config_path.resolve(), output.resolve())

    def test_tie_breaking_prefers_lower_index(self) -> None:
        """When two sets have identical marginal gain, the lower index wins."""
        instance = MaximumCoverageInstance(
            universe_size=4,
            sets=(
                _mask((0, 1)),
                _mask((2, 3)),
                _mask((0, 1)),
                _mask((2, 3)),
            ),
            k=2,
            family="custom",
        )
        result = lazy_greedy(instance)
        dense_selected, _ = _dense_greedy(instance)
        trajectory_indices = tuple(
            point["selected_index"] for point in result.metadata["trajectory"]
        )
        self.assertEqual(trajectory_indices, dense_selected)
        self.assertEqual(trajectory_indices, (0, 1))

    def test_zero_and_full_coverage_instances(self) -> None:
        """Zero-gain sets and a full-coverage single step both terminate cleanly."""
        zero = MaximumCoverageInstance(
            universe_size=3, sets=(0, 0, 0), k=2, family="custom",
        )
        result_zero = lazy_greedy(zero)
        self.assertEqual(result_zero.coverage, 0)
        self.assertEqual(len(result_zero.metadata["trajectory"]), 2)
        dense_sel, dense_cov = _dense_greedy(zero)
        self.assertEqual(result_zero.coverage, dense_cov)
        traj = tuple(p["selected_index"] for p in result_zero.metadata["trajectory"])
        self.assertEqual(traj, dense_sel)

        full = MaximumCoverageInstance(
            universe_size=4,
            sets=(_mask(range(4)), _mask(range(2))),
            k=1,
            family="custom",
        )
        result_full = lazy_greedy(full)
        self.assertEqual(result_full.coverage, 4)
        dense_sel_f, dense_cov_f = _dense_greedy(full)
        self.assertEqual(result_full.coverage, dense_cov_f)
        traj_f = tuple(p["selected_index"] for p in result_full.metadata["trajectory"])
        self.assertEqual(traj_f, dense_sel_f)

    def test_k_equals_set_count(self) -> None:
        """When k equals the number of sets, every set is selected."""
        instance = MaximumCoverageInstance(
            universe_size=6,
            sets=(_mask(range(0, 3)), _mask(range(3, 6)), _mask(range(1, 4))),
            k=3,
            family="custom",
        )
        result = lazy_greedy(instance)
        self.assertEqual(len(result.selected), 3)
        dense_sel, dense_cov = _dense_greedy(instance)
        self.assertEqual(result.coverage, dense_cov)
        traj = tuple(p["selected_index"] for p in result.metadata["trajectory"])
        self.assertEqual(traj, dense_sel)

    def test_serial_and_parallel_metadata_are_identical(self) -> None:
        """workers=1 and workers=2 produce identical lazy_greedy metadata."""
        value = {
            "schema_version": 3,
            "name": "serial parallel check",
            "base_seed": 2210,
            "repetitions": 1,
            "algorithms": [
                {"id": "greedy_baseline", "name": "greedy"},
                {"id": "lazy_id", "name": "lazy_greedy"},
            ],
            "cases": [
                {
                    "name": "small",
                    "family": "uniform",
                    "universe_size": 20,
                    "set_count": 8,
                    "k": 3,
                    "density": 0.2,
                }
            ],
        }
        serial_rows = {}
        parallel_rows = {}
        for tag, workers, store in [("serial", 1, serial_rows), ("parallel", 2, parallel_rows)]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cfg = root / "config.json"
                cfg.write_text(json.dumps(value), encoding="utf-8")
                out = root / "output"
                run_benchmark(cfg, out, workers=workers)
                raw = out / "raw_results.csv"
                with raw.open(encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        if row["algorithm"] == "lazy_greedy":
                            store[tag] = row
        for key in ("coverage", "selected", "algorithm_metadata"):
            self.assertEqual(
                serial_rows["serial"][key],
                parallel_rows["parallel"][key],
                f"mismatch on {key} between serial and parallel",
            )


if __name__ == "__main__":
    unittest.main()
