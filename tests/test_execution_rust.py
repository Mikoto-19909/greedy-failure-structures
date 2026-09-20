"""Native calls across process boundaries and the existing CSV/resume boundary."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
from functools import partial
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import greedy, lazy_greedy
from maxcover.benchmark import run_benchmark
from maxcover.contracts import RunRecord
from maxcover.model import MaximumCoverageInstance, thaw_json_value
from maxcover.structure import analyze_instance


def _native_result(instance):
    records = []
    for algorithm in (greedy, lazy_greedy):
        result = algorithm(instance, backend="rust")
        records.append({"algorithm": result.algorithm, "selected": result.selected,
                        "coverage": result.feasible_value, "status": result.status.value,
                        "bound": result.best_bound, "work": result.nodes_or_iterations,
                        "metadata": thaw_json_value(result.metadata)})
    return asdict(analyze_instance(instance, backend="rust")), records


def _stable_rows(result):
    rows = []
    for record in result.rows:
        row = record.to_csv_row()
        row.pop("runtime_seconds")
        rows.append(row)
    return rows


@unittest.skipUnless(importlib.util.find_spec("maxcover_structure_native"),
                     "optional Rust extension not installed")
class RustExecutionTests(unittest.TestCase):
    def test_spawned_processes_repeat_exact_results(self):
        from test_lazy_greedy import _reference_instances
        instances = _reference_instances() + (
            MaximumCoverageInstance(129, (0, 1 << 128, 1, (1 << 128) | 1), 4),)
        expected = [_native_result(item) for item in instances]
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
            self.assertEqual(list(pool.map(_native_result, instances * 2)), expected * 2)

    def test_native_solutions_preserve_csv_identities_and_partial_resume(self):
        config = {"schema_version": 2, "name": "native result contract", "base_seed": 1920,
                  "repetitions": 2, "algorithms": [{"name": "greedy"}, {"name": "lazy_greedy"}],
                  "cases": [{"name": "boundary", "family": "uniform", "universe_size": 129,
                             "set_count": 20, "k": 8, "density": 0.2}]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            reference = run_benchmark(config_path, root / "python")
            # Test-only dispatch injection; production registry/defaults stay unchanged.
            with patch("maxcover.algorithms.greedy", wraps=partial(greedy, backend="rust")) as dense, \
                 patch("maxcover.algorithms.lazy_greedy", wraps=partial(lazy_greedy, backend="rust")) as lazy:
                result = run_benchmark(config_path, root / "native")
                self.assertEqual(dense.call_count + lazy.call_count, len(result.rows))
                self.assertEqual(_stable_rows(result), _stable_rows(reference))
                self.assertEqual((root / "native/instances.csv").read_bytes(),
                                 (root / "python/instances.csv").read_bytes())
                raw = root / "native/raw_results.csv"
                with raw.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=RunRecord.CSV_FIELDS)
                    writer.writeheader()
                    writer.writerows(record.to_csv_row() for record in result.rows[:-1])
                dense.reset_mock()
                lazy.reset_mock()
                resumed = run_benchmark(config_path, root / "native")
                self.assertEqual(dense.call_count + lazy.call_count, 1)
                self.assertEqual(_stable_rows(resumed), _stable_rows(reference))
                saved = raw.read_bytes()
                with patch("maxcover_structure_native.greedy", side_effect=AssertionError("rerun")), \
                     patch("maxcover_structure_native.lazy_greedy", side_effect=AssertionError("rerun")):
                    complete = run_benchmark(config_path, root / "native")
                self.assertEqual(raw.read_bytes(), saved)
                self.assertEqual(_stable_rows(complete), _stable_rows(reference))


if __name__ == "__main__":
    unittest.main()
