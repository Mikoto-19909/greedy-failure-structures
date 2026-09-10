"""Association eligibility and budget projection on fixed saved records."""
from __future__ import annotations

import csv
import pickle
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover import benchmark_associations as associations
from maxcover.contracts import InstanceRecord, RunRecord

FUNCTIONS = (
    associations._gap_density_association_statistics,
    associations._gap_overlap_association_statistics,
    associations._gap_clustering_association_statistics,
    associations._runtime_set_count_association_statistics,
    associations._runtime_k_association_statistics,
    associations._search_nodes_dominated_ratio_association_statistics,
)


class AssociationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "tests/fixtures/benchmark_compatibility"
        with (fixture / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
            cls.rows = [RunRecord.from_csv_row(row) for row in csv.DictReader(handle)]
        with (fixture / "instances.csv").open(encoding="utf-8", newline="") as handle:
            cls.instances = [InstanceRecord.from_csv_row(row) for row in csv.DictReader(handle)]

    def test_saved_inputs_and_empty_inputs_preserve_records(self):
        before = pickle.dumps((self.rows, self.instances), protocol=4)
        for function in FUNCTIONS:
            with self.subTest(function=function.__name__):
                records = function(self.rows, self.instances)
                self.assertTrue(records)
                self.assertIn("estimable", {record.association_status for record in records})
                self.assertEqual(function([], []), [])
        self.assertEqual(pickle.dumps((self.rows, self.instances), protocol=4), before)

    def test_duplicate_and_missing_instance_records_are_rejected(self):
        for function in FUNCTIONS:
            with self.subTest(function=function.__name__, invalid="duplicate"):
                with self.assertRaisesRegex(ValueError, "requires unique"):
                    function(self.rows, self.instances + [self.instances[0]])
            with self.subTest(function=function.__name__, invalid="missing"):
                with self.assertRaisesRegex(ValueError, "no matching instance"):
                    function(self.rows, [])

    def test_budget_projection_preserves_units_and_constant_status(self):
        rows = [replace(row, runtime_seconds=3.0 * row.k) for row in self.rows
                if row.family == "uniform" and row.algorithm == "greedy"]
        records = associations._runtime_k_association_statistics(rows, self.instances)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.predictor, "k")
        self.assertEqual(record.distinct_k_count, 2)
        self.assertEqual(record.association_status, "estimable")
        self.assertEqual(record.pearson_correlation, 1.0)
        self.assertEqual(record.ols_slope_seconds_per_budget_unit, 3.0)
        self.assertEqual(record.ols_intercept_seconds, 0.0)
        constant = associations._runtime_k_association_statistics(
            [row for row in rows if row.k == 2], self.instances)[0]
        self.assertEqual(constant.association_status, "constant_k")
        self.assertIsNone(constant.ols_slope_seconds_per_budget_unit)


if __name__ == "__main__":
    unittest.main()
