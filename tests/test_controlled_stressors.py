from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import brute_force, greedy
from maxcover.benchmark import _instances_for_config, run_benchmark
from maxcover.certificates import known_optimum_certificate
from maxcover.cli import DEFAULT_STRESSOR_AUDIT_CONFIGS
from maxcover.config import load_config
from maxcover.generators import (
    controlled_adversarial_greedy_trap,
    controlled_clustered,
    controlled_dominated,
    controlled_duplicate,
    controlled_high_overlap,
)
from maxcover.stressor_audit import (
    analyze_stressor_structure,
    audit_stressor_configs,
    stressor_audit_has_failures,
)
from maxcover.structure import analyze_instance


CONTROLLED_CONFIG = ROOT / "configs" / "p7_controlled_stressors.json"
LEGACY_CONFIGS = (
    "p4_duplicate_heavy.json",
    "p4_dominated_heavy.json",
    "p6_overlap_scan.json",
    "p6_clustered_scan.json",
    "p4_adversarial_severity.json",
)


class ControlledGeneratorInvariantTests(unittest.TestCase):
    def test_overlap_holds_dimensions_and_incidence_while_target_increases(self) -> None:
        set_size = 8
        instances = [
            controlled_high_overlap(
                universe_size=200,
                set_count=24,
                k=5,
                set_size=set_size,
                shared_core_size=core_size,
                seed=100 + core_size,
                coupling_seed=991,
            )
            for core_size in (0, 2, 4, 6)
        ]

        observed = []
        for core_size, instance in zip((0, 2, 4, 6), instances, strict=True):
            metrics = analyze_instance(instance)
            expected = core_size / (2 * set_size - core_size)
            self.assertEqual(
                (instance.universe_size, instance.set_count, instance.k),
                (200, 24, 5),
            )
            self.assertEqual(metrics.incidence_count, 24 * set_size)
            self.assertEqual(metrics.duplicate_set_count, 0)
            self.assertEqual(metrics.dominated_set_count, 0)
            self.assertAlmostEqual(
                metrics.pairwise_overlap_mean_jaccard or 0.0,
                expected,
                places=15,
            )
            observed.append(metrics.pairwise_overlap_mean_jaccard or 0.0)
        self.assertTrue(all(left < right for left, right in zip(observed, observed[1:])))

    def test_clustered_holds_dimensions_and_incidence_while_separation_increases(
        self,
    ) -> None:
        set_size = 8
        observed = []
        for core_size in (0, 2, 4, 6):
            instance = controlled_clustered(
                universe_size=224,
                set_count=24,
                k=5,
                clusters=4,
                set_size=set_size,
                within_core_size=core_size,
                seed=200 + core_size,
                coupling_seed=992,
            )
            basic = analyze_instance(instance)
            structure = analyze_stressor_structure(instance)
            expected = core_size / (2 * set_size - core_size)
            self.assertEqual(
                (instance.universe_size, instance.set_count, instance.k),
                (224, 24, 5),
            )
            self.assertEqual(basic.incidence_count, 24 * set_size)
            self.assertEqual(basic.duplicate_set_count, 0)
            self.assertEqual(basic.dominated_set_count, 0)
            self.assertAlmostEqual(
                structure.cluster_within_mean_jaccard or 0.0,
                expected,
                places=15,
            )
            self.assertEqual(structure.cluster_between_mean_jaccard, 0.0)
            self.assertAlmostEqual(
                structure.cluster_separation_jaccard or 0.0,
                expected,
                places=15,
            )
            observed.append(structure.cluster_separation_jaccard or 0.0)
        self.assertTrue(all(left < right for left, right in zip(observed, observed[1:])))

    def test_duplicate_holds_dimensions_and_incidence_while_ratio_increases(self) -> None:
        observed = []
        for copy_factor in (1, 2, 3, 4):
            instance = controlled_duplicate(
                universe_size=160,
                set_count=24,
                k=4,
                set_size=6,
                copy_factor=copy_factor,
                seed=300 + copy_factor,
                coupling_seed=993,
            )
            metrics = analyze_instance(instance)
            self.assertEqual(
                (instance.universe_size, instance.set_count, instance.k),
                (160, 24, 4),
            )
            self.assertEqual(metrics.incidence_count, 24 * 6)
            self.assertEqual(metrics.unique_set_count, 24 // copy_factor)
            self.assertAlmostEqual(
                metrics.duplicate_set_ratio,
                1 - 1 / copy_factor,
                places=15,
            )
            self.assertEqual(metrics.dominated_set_count, 0)
            observed.append(metrics.duplicate_set_ratio)
        self.assertTrue(all(left < right for left, right in zip(observed, observed[1:])))

    def test_dominated_holds_dimensions_and_incidence_while_ratio_increases(self) -> None:
        observed = []
        for dominated_pairs in (0, 2, 4, 6):
            instance = controlled_dominated(
                universe_size=96,
                set_count=16,
                k=4,
                anchor_size=6,
                child_size=3,
                dominated_pair_count=dominated_pairs,
                seed=400 + dominated_pairs,
                coupling_seed=994,
            )
            metrics = analyze_instance(instance)
            self.assertEqual(
                (instance.universe_size, instance.set_count, instance.k),
                (96, 16, 4),
            )
            self.assertEqual(metrics.incidence_count, 8 * (6 + 3))
            self.assertEqual(metrics.duplicate_set_count, 0)
            self.assertEqual(metrics.dominated_set_count, dominated_pairs)
            self.assertAlmostEqual(
                metrics.dominated_set_ratio,
                dominated_pairs / 16,
                places=15,
            )
            observed.append(metrics.dominated_set_ratio)
        self.assertTrue(all(left < right for left, right in zip(observed, observed[1:])))

    def test_adversarial_holds_incidence_bait_certificate_and_dominance(self) -> None:
        block_size = 12
        distractor_count = 8
        incidences = set()
        dominated_counts = set()
        severities = []
        distractor_streams = set()
        for trap_count in (7, 8, 9, 10, 11):
            instance = controlled_adversarial_greedy_trap(
                block_size=block_size,
                distractor_count=distractor_count,
                trap_count=trap_count,
                seed=500 + trap_count,
                coupling_seed=995,
            )
            metrics = analyze_instance(instance)
            solution = greedy(instance)
            certificate = known_optimum_certificate(instance)
            self.assertEqual(
                (instance.universe_size, instance.set_count, instance.k),
                (2 * block_size, 4 + distractor_count, 2),
            )
            incidences.add(metrics.incidence_count)
            dominated_counts.add(metrics.dominated_set_count)
            distractor_streams.add(instance.sets[4:])
            self.assertEqual(solution.selected, (0, 1))
            self.assertEqual(solution.coverage, block_size + trap_count)
            self.assertIsNotNone(certificate)
            assert certificate is not None
            self.assertEqual(certificate.value, 2 * block_size)
            self.assertEqual(certificate.selected, (1, 2))
            severities.append((2 * block_size - solution.coverage) / (2 * block_size))

        self.assertEqual(incidences, {(distractor_count + 4) * block_size + 1})
        self.assertEqual(dominated_counts, {distractor_count + 1})
        self.assertEqual(len(distractor_streams), 1)
        self.assertTrue(
            all(left > right for left, right in zip(severities, severities[1:]))
        )

    def test_small_controlled_adversarial_certificate_matches_exact_search(self) -> None:
        for trap_count in (5, 6, 7):
            instance = controlled_adversarial_greedy_trap(
                block_size=8,
                distractor_count=4,
                trap_count=trap_count,
                seed=trap_count,
                coupling_seed=996,
            )
            self.assertEqual(
                brute_force(instance, time_limit_seconds=None).coverage,
                instance.universe_size,
            )

    def test_controlled_shape_and_capacity_errors_are_explicit(self) -> None:
        invalid = (
            (
                lambda: controlled_high_overlap(
                    universe_size=71,
                    set_count=8,
                    k=3,
                    set_size=8,
                    shared_core_size=4,
                    seed=1,
                ),
                "universe_size",
            ),
            (
                lambda: controlled_clustered(
                    universe_size=80,
                    set_count=7,
                    k=3,
                    clusters=4,
                    set_size=8,
                    within_core_size=4,
                    seed=1,
                ),
                "set_count",
            ),
            (
                lambda: controlled_duplicate(
                    universe_size=160,
                    set_count=24,
                    k=4,
                    set_size=6,
                    copy_factor=5,
                    seed=1,
                ),
                "copy_factor",
            ),
            (
                lambda: controlled_dominated(
                    universe_size=96,
                    set_count=15,
                    k=4,
                    anchor_size=6,
                    child_size=3,
                    dominated_pair_count=2,
                    seed=1,
                ),
                "set_count",
            ),
            (
                lambda: controlled_adversarial_greedy_trap(
                    block_size=8,
                    distractor_count=4,
                    trap_count=8,
                    seed=1,
                ),
                "trap_count",
            ),
        )
        for generate, message in invalid:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    generate()


class ControlledAuditIntegrationTests(unittest.TestCase):
    def test_default_controlled_audit_passes_every_scan(self) -> None:
        self.assertEqual(DEFAULT_STRESSOR_AUDIT_CONFIGS, (CONTROLLED_CONFIG,))
        config = load_config(CONTROLLED_CONFIG)
        report = audit_stressor_configs([config])
        scans = report["scans"]
        assert isinstance(scans, list)

        self.assertEqual(report["skipped_scans"], [])
        self.assertFalse(stressor_audit_has_failures(report))
        self.assertEqual(
            {scan["family"] for scan in scans},
            {
                "controlled_high_overlap",
                "controlled_clustered",
                "controlled_duplicate",
                "controlled_dominated",
                "long_tail",
                "controlled_adversarial",
            },
        )
        for scan in scans:
            with self.subTest(scan=scan["scan"]):
                self.assertEqual(scan["assessment"], "pass")
                controls = scan["confound_controls"]
                self.assertTrue(controls["universe_size"])
                self.assertTrue(controls["set_count"])
                self.assertTrue(controls["k"])
                self.assertTrue(controls["incidence_level_mean_stable"])
                self.assertTrue(controls["uniform_control_dimensions_match"])
                self.assertIn(
                    "covered_element_count_mean",
                    scan["measured_metric_level_mean_ranges"],
                )

    def test_legacy_configs_remain_explicitly_confounded(self) -> None:
        report = audit_stressor_configs(
            [load_config(ROOT / "configs" / name) for name in LEGACY_CONFIGS]
        )
        self.assertTrue(stressor_audit_has_failures(report))
        scans = report["scans"]
        assert isinstance(scans, list)
        self.assertTrue(any(scan["assessment"] == "fail" for scan in scans))

    def test_controlled_sweep_levels_share_one_coupling_stream(self) -> None:
        config = load_config(CONTROLLED_CONFIG)
        grouped: dict[tuple[str, int], list[object]] = defaultdict(list)
        for planned in _instances_for_config(config):
            grouped[(planned.instance.family, planned.repetition)].append(planned)

        for (family, repetition), group in grouped.items():
            with self.subTest(family=family, repetition=repetition):
                self.assertEqual(len({item.coupling_pair_id for item in group}), 1)
                self.assertNotIn(None, {item.coupling_pair_id for item in group})
                self.assertEqual(len({item.coupling_seed for item in group}), 1)
                coupling_seed = group[0].coupling_seed
                self.assertIsNotNone(coupling_seed)
                self.assertTrue(
                    all(
                        item.instance.parameters["coupling_seed"] == coupling_seed
                        for item in group
                    )
                )

    def test_controlled_families_persist_through_the_benchmark_record_path(self) -> None:
        config = {
            "schema_version": 3,
            "name": "controlled record integration",
            "base_seed": 17,
            "repetitions": 1,
            "algorithms": [{"name": "greedy"}],
            "cases": [
                {
                    "name": "overlap",
                    "family": "controlled_high_overlap",
                    "universe_size": 72,
                    "set_count": 8,
                    "k": 3,
                    "set_size": 8,
                    "shared_core_size": 4,
                },
                {
                    "name": "clustered",
                    "family": "controlled_clustered",
                    "universe_size": 80,
                    "set_count": 8,
                    "k": 3,
                    "clusters": 2,
                    "set_size": 8,
                    "within_core_size": 4,
                },
                {
                    "name": "duplicate",
                    "family": "controlled_duplicate",
                    "universe_size": 48,
                    "set_count": 8,
                    "k": 3,
                    "set_size": 5,
                    "copy_factor": 2,
                },
                {
                    "name": "dominated",
                    "family": "controlled_dominated",
                    "universe_size": 40,
                    "set_count": 8,
                    "k": 3,
                    "anchor_size": 6,
                    "child_size": 3,
                    "dominated_pair_count": 2,
                },
                {
                    "name": "adversarial",
                    "family": "controlled_adversarial",
                    "block_size": 8,
                    "distractor_count": 4,
                    "trap_count": 5,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = run_benchmark(config_path, root / "output")

        self.assertEqual(len(result.instances), 5)
        records = {record.family: record for record in result.instances}
        for family in (
            "controlled_high_overlap",
            "controlled_clustered",
            "controlled_duplicate",
            "controlled_dominated",
        ):
            self.assertEqual(records[family].instance_origin, "constructed")
            self.assertFalse(records[family].is_adversarial)
        adversarial = records["controlled_adversarial"]
        self.assertEqual(adversarial.instance_origin, "constructed")
        self.assertTrue(adversarial.is_adversarial)
        self.assertIsNotNone(adversarial.adversarial_severity)
        self.assertEqual(adversarial.known_optimum, 16)
        self.assertEqual(adversarial.optimum_selected, (1, 2))


if __name__ == "__main__":
    unittest.main()
