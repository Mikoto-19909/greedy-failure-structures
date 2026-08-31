from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.config import load_config, parse_config
from maxcover.model import MaximumCoverageInstance
from maxcover.stressor_audit import (
    analyze_stressor_structure,
    audit_stressor_configs,
    stressor_audit_has_failures,
    stressor_metrics_dict,
)


AUDIT_CONFIGS = (
    "p4_duplicate_heavy.json",
    "p4_dominated_heavy.json",
    "p4_long_tail.json",
    "p6_overlap_scan.json",
    "p6_clustered_scan.json",
    "p4_adversarial_severity.json",
)


def _mask(*elements: int) -> int:
    return sum(1 << element for element in elements)


class SupplementaryStressorMetricTests(unittest.TestCase):
    def test_hand_checked_overlap_concentration_and_cluster_separation(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=4,
            sets=(
                _mask(0, 1),
                _mask(2, 3),
                _mask(0),
                _mask(2),
            ),
            k=2,
            family="clustered",
            parameters={"clusters": 2},
        )

        metrics = analyze_stressor_structure(instance)

        self.assertEqual(metrics.pairwise_overlap_q25_jaccard, 0.0)
        self.assertEqual(metrics.pairwise_overlap_q50_jaccard, 0.0)
        self.assertEqual(metrics.pairwise_overlap_q75_jaccard, 0.375)
        self.assertEqual(metrics.pairwise_overlap_q90_jaccard, 0.5)
        self.assertEqual(metrics.coverage_head_10pct_ratio, 1 / 3)
        self.assertEqual(metrics.cluster_within_mean_jaccard, 0.5)
        self.assertEqual(metrics.cluster_between_mean_jaccard, 0.0)
        self.assertEqual(metrics.cluster_separation_jaccard, 0.5)
        self.assertEqual(
            set(stressor_metrics_dict(metrics)),
            {
                "pairwise_overlap_q25_jaccard",
                "pairwise_overlap_q50_jaccard",
                "pairwise_overlap_q75_jaccard",
                "pairwise_overlap_q90_jaccard",
                "coverage_head_10pct_ratio",
                "cluster_within_mean_jaccard",
                "cluster_between_mean_jaccard",
                "cluster_separation_jaccard",
            },
        )

    def test_empty_pair_domain_is_explicit(self) -> None:
        instance = MaximumCoverageInstance(
            universe_size=3,
            sets=(0,),
            k=1,
            family="custom",
        )

        metrics = analyze_stressor_structure(instance)

        self.assertIsNone(metrics.pairwise_overlap_q25_jaccard)
        self.assertIsNone(metrics.pairwise_overlap_q50_jaccard)
        self.assertIsNone(metrics.pairwise_overlap_q75_jaccard)
        self.assertIsNone(metrics.pairwise_overlap_q90_jaccard)
        self.assertEqual(metrics.coverage_head_10pct_ratio, 0.0)
        self.assertIsNone(metrics.cluster_separation_jaccard)


class CanonicalGeneratorIsolationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configs = [load_config(ROOT / "configs" / name) for name in AUDIT_CONFIGS]
        cls.report = audit_stressor_configs(configs)
        raw_scans = cls.report["scans"]
        assert isinstance(raw_scans, list)
        cls.scans = {
            (scan["family"], scan["scan"]): scan
            for scan in raw_scans
            if isinstance(scan, dict)
        }

    def test_every_requested_family_has_an_audited_scan(self) -> None:
        self.assertEqual(
            {family for family, _ in self.scans},
            {
                "duplicate_heavy",
                "dominated_heavy",
                "long_tail",
                "high_overlap",
                "clustered",
                "adversarial",
            },
        )
        self.assertEqual(self.report["skipped_scans"], [])

    def test_targets_change_monotonically_when_the_parameter_is_an_intensity(self) -> None:
        descriptive = self.scans[("clustered", "cluster_count")]
        self.assertIsNone(descriptive["expected_direction"])
        self.assertIsNone(descriptive["target_monotonic"])
        self.assertEqual(descriptive["assessment"], "descriptive")

        for key, scan in self.scans.items():
            if key == ("clustered", "cluster_count"):
                continue
            with self.subTest(scan=key):
                self.assertTrue(scan["target_monotonic"])

    def test_reverse_checks_expose_current_dimension_confounders(self) -> None:
        duplicate = self.scans[("duplicate_heavy", "duplicate_copy_factor")]
        dominated = self.scans[("dominated_heavy", "dominated_children")]
        overlap = self.scans[("high_overlap", "core_probability")]
        clustered = self.scans[("clustered", "within_probability")]
        long_tail = self.scans[("long_tail", "long_tail_gamma")]

        for scan in (duplicate, dominated):
            controls = scan["confound_controls"]
            self.assertFalse(controls["set_count"])
            self.assertFalse(controls["incidence_level_mean_stable"])

        for scan in (overlap, clustered):
            controls = scan["confound_controls"]
            self.assertTrue(controls["universe_size"])
            self.assertTrue(controls["set_count"])
            self.assertTrue(controls["k"])
            self.assertFalse(controls["incidence_level_mean_stable"])

        long_tail_controls = long_tail["confound_controls"]
        self.assertTrue(long_tail_controls["universe_size"])
        self.assertTrue(long_tail_controls["set_count"])
        self.assertTrue(long_tail_controls["k"])
        self.assertTrue(long_tail_controls["incidence_level_mean_stable"])

    def test_non_target_metrics_and_matched_uniform_controls_are_reported(self) -> None:
        for key, scan in self.scans.items():
            with self.subTest(scan=key):
                controls = scan["confound_controls"]
                self.assertTrue(controls["uniform_control_dimensions_match"])
                ranges = scan["measured_metric_level_mean_ranges"]
                self.assertIn("actual_density_mean", ranges)
                self.assertIn("unique_set_ratio_mean", ranges)
                self.assertIn("coverage_skew_gini_mean", ranges)
                self.assertIn("pairwise_overlap_q50_jaccard_mean", ranges)
                levels = scan["levels"]
                self.assertGreaterEqual(len(levels), 3)
                for level in levels:
                    self.assertEqual(len(level["dimensions"]["universe_size_values"]), 1)
                    self.assertEqual(len(level["dimensions"]["set_count_values"]), 1)
                    self.assertEqual(len(level["dimensions"]["k_values"]), 1)
                    self.assertTrue(
                        level["uniform_control"][
                            "dimensions_match_every_observation"
                        ]
                    )
                    self.assertIn(
                        "unique_set_ratio_mean", level["uniform_control"]
                    )

    def test_adversarial_bait_and_certificate_are_verified_for_every_instance(self) -> None:
        adversarial_scans = [
            scan for (family, _), scan in self.scans.items() if family == "adversarial"
        ]
        self.assertEqual(len(adversarial_scans), 3)
        for scan in adversarial_scans:
            with self.subTest(scan=scan["scan"]):
                checks = scan["adversarial_checks"]
                self.assertTrue(checks["bait_selected_first_every_observation"])
                self.assertTrue(checks["certificate_verified_every_observation"])

    def test_report_round_trips_as_json_and_strict_mode_detects_failures(self) -> None:
        restored = json.loads(json.dumps(self.report, sort_keys=True))
        self.assertEqual(restored["schema_version"], 1)
        self.assertTrue(stressor_audit_has_failures(restored))

    def test_numeric_equivalent_levels_cannot_make_strict_mode_falsely_green(
        self,
    ) -> None:
        config = parse_config(
            {
                "schema_version": 3,
                "name": "equivalent audit levels",
                "repetitions": 2,
                "algorithms": [{"name": "greedy"}],
                "cases": [
                    {
                        "name": "overlap",
                        "family": "high_overlap",
                        "universe_size": 16,
                        "set_count": 6,
                        "k": 2,
                        "core_fraction": 0.25,
                        "peripheral_probability": 0.05,
                        "sweep": {"core_probability": [1, 1.0]},
                    }
                ],
            }
        )

        report = audit_stressor_configs([config])

        self.assertEqual(report["scans"], [])
        self.assertEqual(len(report["skipped_scans"]), 1)
        self.assertTrue(stressor_audit_has_failures(report))


if __name__ == "__main__":
    unittest.main()
