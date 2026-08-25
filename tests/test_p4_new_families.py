from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import random
import sys
import unittest
from collections import defaultdict
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import (
    branch_and_bound,
    branch_and_bound_enhanced,
    brute_force,
)
from maxcover.benchmark import (
    _instance_record,
    _instances_for_config,
    plan_benchmark,
)
from maxcover.certificates import (
    known_optimum_certificate,
    validate_known_optimum_certificate,
)
from maxcover.config import ConfigurationError, load_config, parse_config
from maxcover.contracts import InstanceRecord
from maxcover.generators import (
    dominated_heavy,
    duplicate_heavy,
    fixed_size,
    long_tail,
    mixed_cluster,
    uniform_random,
)
from maxcover.model import MaximumCoverageInstance, SolutionStatus
from maxcover.structure import analyze_instance


SEED_COUNT = 1_000 if os.environ.get("MAXCOVER_EXTENDED_P4") == "1" else 100


def _mask(elements: tuple[int, ...] | list[int]) -> int:
    value = 0
    for element in elements:
        value |= 1 << element
    return value


def _derived_seed(seed: int, namespace: str, index: int = 0) -> int:
    payload = f"maxcover\0{namespace}\0{seed}\0{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:16], "big")


def _long_tail_reference(
    *,
    universe_size: int,
    set_count: int,
    set_size: int,
    gamma: float,
    coupling_seed: int,
) -> tuple[int, ...]:
    """Frozen literal reference for the paired exponential-race contract."""

    rng = random.Random(coupling_seed)
    rank_order = list(range(universe_size))
    rng.shuffle(rank_order)
    rank_by_element = [0] * universe_size
    for rank, element in enumerate(rank_order):
        rank_by_element[element] = rank

    denominator = 1 << 53
    sets = []
    for _ in range(set_count):
        keys = []
        for element in range(universe_size):
            uniform = (rng.getrandbits(53) + 0.5) / denominator
            if uniform >= 1.0:
                uniform = math.nextafter(1.0, 0.0)
            key = math.log(-math.log(uniform)) + gamma * math.log(
                rank_by_element[element] + 1
            )
            keys.append((key, element))
        sets.append(_mask([element for _, element in sorted(keys)[:set_size]]))
    return tuple(sets)


def _minimal_config(case: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "P4.3 preflight",
        "base_seed": 4300,
        "repetitions": 1,
        "algorithms": [{"name": "greedy"}],
        "cases": [case],
    }


def _fixed_size_qa(seed: int) -> MaximumCoverageInstance:
    cells = ((16, 12, 3, 4), (32, 24, 6, 8))
    universe_size, set_count, k, set_size = cells[seed % len(cells)]
    return fixed_size(
        universe_size=universe_size,
        set_count=set_count,
        k=k,
        set_size=set_size,
        unique_sets=True,
        seed=seed,
    )


def _long_tail_qa(seed: int) -> MaximumCoverageInstance:
    gamma = (0.0, 1.0, 2.0)[seed % 3]
    return long_tail(
        universe_size=32,
        set_count=20,
        k=5,
        set_size=6,
        gamma=gamma,
        seed=seed,
    )


def _duplicate_heavy_qa(seed: int) -> MaximumCoverageInstance:
    copy_factor = (1, 2, 4)[seed % 3]
    return duplicate_heavy(
        universe_size=32,
        base_set_count=8,
        k=4,
        set_size=6,
        copy_factor=copy_factor,
        seed=seed,
    )


def _dominated_heavy_qa(seed: int) -> MaximumCoverageInstance:
    child_count = (0, 2, 4)[seed % 3]
    return dominated_heavy(
        anchor_count=8,
        anchor_size=6,
        k=4,
        child_count=child_count,
        seed=seed,
    )


def _mixed_cluster_qa(seed: int) -> MaximumCoverageInstance:
    bridge_fraction = (0.0, 0.25, 0.5, 0.75)[seed % 4]
    return mixed_cluster(
        universe_size=64,
        set_count=24,
        k=6,
        clusters=4,
        set_size=8,
        bridge_fraction=bridge_fraction,
        seed=seed,
    )


class P43GeneratorInvariantTests(unittest.TestCase):
    def assert_fixed_size_invariants(
        self, instance: MaximumCoverageInstance
    ) -> None:
        set_size = int(instance.parameters["set_size"])
        self.assertTrue(all(mask.bit_count() == set_size for mask in instance.sets))
        if instance.parameters["unique_sets"]:
            self.assertEqual(len(set(instance.sets)), instance.set_count)
        metrics = analyze_instance(instance)
        self.assertEqual(metrics.incidence_count, instance.set_count * set_size)
        self.assertAlmostEqual(metrics.mean_set_size, set_size, places=15)
        self.assertAlmostEqual(
            metrics.actual_density,
            set_size / instance.universe_size,
            places=15,
        )

    def assert_long_tail_invariants(
        self, instance: MaximumCoverageInstance
    ) -> None:
        set_size = int(instance.parameters["set_size"])
        self.assertTrue(all(mask.bit_count() == set_size for mask in instance.sets))
        metrics = analyze_instance(instance)
        self.assertEqual(metrics.incidence_count, instance.set_count * set_size)
        self.assertAlmostEqual(metrics.mean_set_size, set_size, places=15)
        self.assertAlmostEqual(
            metrics.actual_density,
            set_size / instance.universe_size,
            places=15,
        )

    def assert_duplicate_invariants(
        self, instance: MaximumCoverageInstance
    ) -> None:
        base_count = int(instance.parameters["base_set_count"])
        copy_factor = int(instance.parameters["copy_factor"])
        set_size = int(instance.parameters["set_size"])
        self.assertEqual(instance.set_count, base_count * copy_factor)
        groups = tuple(
            instance.sets[index : index + copy_factor]
            for index in range(0, instance.set_count, copy_factor)
        )
        self.assertTrue(all(len(set(group)) == 1 for group in groups))
        bases = tuple(group[0] for group in groups)
        self.assertEqual(len(set(bases)), base_count)
        self.assertTrue(all(mask.bit_count() == set_size for mask in bases))
        metrics = analyze_instance(instance)
        self.assertEqual(metrics.unique_set_count, base_count)
        self.assertEqual(metrics.duplicate_set_count, base_count * (copy_factor - 1))
        self.assertAlmostEqual(
            metrics.duplicate_set_ratio, 1.0 - 1.0 / copy_factor, places=15
        )

    def assert_dominated_invariants(
        self, instance: MaximumCoverageInstance
    ) -> None:
        anchor_count = int(instance.parameters["anchor_count"])
        anchor_size = int(instance.parameters["anchor_size"])
        child_count = int(instance.parameters["child_count"])
        anchors = instance.sets[:anchor_count]
        children = instance.sets[anchor_count:]
        self.assertEqual(instance.universe_size, anchor_count * anchor_size)
        self.assertEqual(instance.set_count, anchor_count * (child_count + 1))
        self.assertTrue(all(mask.bit_count() == anchor_size for mask in anchors))
        self.assertTrue(
            all(left & right == 0 for left, right in itertools.combinations(anchors, 2))
        )
        self.assertEqual((sum(anchors)).bit_count(), instance.universe_size)
        self.assertEqual(len(children), anchor_count * child_count)
        self.assertEqual(len(set(instance.sets)), instance.set_count)
        for child in children:
            containing = [anchor for anchor in anchors if child & anchor == child]
            self.assertEqual(len(containing), 1)
            self.assertNotEqual(child, 0)
            self.assertNotEqual(child, containing[0])
        metrics = analyze_instance(instance)
        self.assertEqual(metrics.dominated_set_count, len(children))
        self.assertEqual(metrics.preprocessed_set_count, anchor_count)

    def assert_mixed_cluster_invariants(
        self, instance: MaximumCoverageInstance
    ) -> None:
        clusters = int(instance.parameters["clusters"])
        set_size = int(instance.parameters["set_size"])
        coupling_seed = int(instance.parameters["coupling_seed"])
        expected_count = math.floor(
            instance.set_count * float(instance.parameters["bridge_fraction"]) + 0.5
        )
        self.assertEqual(instance.parameters["bridge_count"], expected_count)
        self.assertAlmostEqual(
            float(instance.parameters["realized_bridge_fraction"]),
            expected_count / instance.set_count,
            places=15,
        )
        self.assertTrue(all(mask.bit_count() == set_size for mask in instance.sets))
        metrics = analyze_instance(instance)
        self.assertAlmostEqual(metrics.mean_set_size, set_size, places=15)
        self.assertAlmostEqual(
            metrics.actual_density,
            set_size / instance.universe_size,
            places=15,
        )

        elements = list(range(instance.universe_size))
        random.Random(
            _derived_seed(coupling_seed, "mixed_cluster:partition")
        ).shuffle(elements)
        cluster_elements: list[set[int]] = [set() for _ in range(clusters)]
        for position, element in enumerate(elements):
            cluster_elements[position % clusters].add(element)
        bridge_indices = {
            index
            for _, index in sorted(
                (
                    _derived_seed(
                        coupling_seed,
                        "mixed_cluster:bridge-rank",
                        index,
                    ),
                    index,
                )
                for index in range(instance.set_count)
            )[:expected_count]
        }
        lower_bridge_size = set_size // 2
        upper_bridge_size = set_size - lower_bridge_size
        for index, mask in enumerate(instance.sets):
            members = {
                element
                for element in range(instance.universe_size)
                if mask & (1 << element)
            }
            preferred = index % clusters
            adjacent = (preferred + 1) % clusters
            if index in bridge_indices:
                self.assertEqual(
                    len(members & cluster_elements[preferred]),
                    lower_bridge_size,
                )
                self.assertEqual(
                    len(members & cluster_elements[adjacent]),
                    upper_bridge_size,
                )
                self.assertLessEqual(
                    members,
                    cluster_elements[preferred] | cluster_elements[adjacent],
                )
            else:
                self.assertLessEqual(members, cluster_elements[preferred])

    def test_seeded_qa_corpus_is_deterministic_and_satisfies_hard_invariants(
        self,
    ) -> None:
        families = (
            (_fixed_size_qa, self.assert_fixed_size_invariants),
            (_long_tail_qa, self.assert_long_tail_invariants),
            (_duplicate_heavy_qa, self.assert_duplicate_invariants),
            (_dominated_heavy_qa, self.assert_dominated_invariants),
            (_mixed_cluster_qa, self.assert_mixed_cluster_invariants),
        )
        for seed in range(SEED_COUNT):
            for factory, assertion in families:
                with self.subTest(factory=factory.__name__, seed=seed):
                    instance = factory(seed)
                    self.assertEqual(instance, factory(seed))
                    assertion(instance)

    def test_fixed_size_follows_frozen_sampling_and_combinadic_contract(self) -> None:
        universe_size = 8
        set_count = 10
        set_size = 3
        for unique_sets in (False, True):
            for seed in range(10):
                with self.subTest(unique_sets=unique_sets, seed=seed):
                    rng = random.Random(seed)
                    if unique_sets:
                        combinations = tuple(
                            itertools.combinations(range(universe_size), set_size)
                        )
                        ranks = rng.sample(range(len(combinations)), set_count)
                        expected = tuple(_mask(combinations[rank]) for rank in ranks)
                    else:
                        expected = tuple(
                            _mask(rng.sample(range(universe_size), set_size))
                            for _ in range(set_count)
                        )
                    actual = fixed_size(
                        universe_size=universe_size,
                        set_count=set_count,
                        k=3,
                        set_size=set_size,
                        unique_sets=unique_sets,
                        seed=seed,
                    )
                    self.assertEqual(actual.sets, expected)

    def test_long_tail_follows_frozen_paired_exponential_race_contract(self) -> None:
        for seed in range(100):
            for gamma in (0.0, 0.5, 2.0):
                with self.subTest(seed=seed, gamma=gamma):
                    tailed = long_tail(
                        universe_size=16,
                        set_count=12,
                        k=3,
                        set_size=4,
                        gamma=gamma,
                        seed=10_000 + seed,
                        coupling_seed=seed,
                    )
                    self.assertEqual(
                        tailed.sets,
                        _long_tail_reference(
                            universe_size=16,
                            set_count=12,
                            set_size=4,
                            gamma=gamma,
                            coupling_seed=seed,
                        ),
                    )

    def test_positive_gamma_increases_aggregate_coverage_skew(self) -> None:
        control = []
        tailed = []
        for seed in range(100):
            control.append(
                analyze_instance(
                    long_tail(
                        universe_size=32,
                        set_count=20,
                        k=5,
                        set_size=6,
                        gamma=0,
                        seed=seed,
                    )
                ).coverage_skew_gini
            )
            tailed.append(
                analyze_instance(
                    long_tail(
                        universe_size=32,
                        set_count=20,
                        k=5,
                        set_size=6,
                        gamma=2,
                        seed=seed,
                    )
                ).coverage_skew_gini
            )
        self.assertGreater(math.fsum(tailed), math.fsum(control))

    def test_duplicate_optimum_equals_its_unique_base_optimum(self) -> None:
        for seed in range(10):
            base = fixed_size(
                universe_size=12,
                set_count=6,
                k=3,
                set_size=4,
                unique_sets=True,
                seed=seed,
            )
            duplicate = duplicate_heavy(
                universe_size=12,
                base_set_count=6,
                k=3,
                set_size=4,
                copy_factor=3,
                seed=20_000 + seed,
                coupling_seed=seed,
            )
            self.assertEqual(duplicate.sets[::3], base.sets)
            self.assertEqual(brute_force(duplicate).coverage, brute_force(base).coverage)

    def test_dominated_known_optimum_is_the_disjoint_anchor_value(self) -> None:
        for seed in range(10):
            instance = dominated_heavy(
                anchor_count=5,
                anchor_size=4,
                k=3,
                child_count=3,
                seed=seed,
            )
            self.assertEqual(brute_force(instance).coverage, 12)
            certificate = known_optimum_certificate(instance)
            self.assertIsNotNone(certificate)
            assert certificate is not None
            self.assertEqual(certificate.value, 12)
            self.assertEqual(certificate.selected, (0, 1, 2))
            self.assertEqual(certificate.proof_kind, "disjoint_anchors")
            validate_known_optimum_certificate(instance, certificate)


class P43PreflightAndExactnessTests(unittest.TestCase):
    def test_invalid_parameters_and_boolean_substitutes_report_exact_paths(self) -> None:
        valid_cases = {
            "fixed_size": {
                "name": "fixed",
                "family": "fixed_size",
                "universe_size": 8,
                "set_count": 6,
                "k": 2,
                "set_size": 3,
                "unique_sets": True,
            },
            "long_tail": {
                "name": "tail",
                "family": "long_tail",
                "universe_size": 8,
                "set_count": 6,
                "k": 2,
                "set_size": 3,
                "gamma": 1.0,
            },
            "duplicate_heavy": {
                "name": "duplicates",
                "family": "duplicate_heavy",
                "universe_size": 8,
                "base_set_count": 6,
                "k": 2,
                "set_size": 3,
                "copy_factor": 2,
            },
            "dominated_heavy": {
                "name": "dominated",
                "family": "dominated_heavy",
                "anchor_count": 5,
                "anchor_size": 4,
                "k": 2,
                "child_count": 2,
            },
            "mixed_cluster": {
                "name": "mixed",
                "family": "mixed_cluster",
                "universe_size": 16,
                "set_count": 8,
                "k": 2,
                "clusters": 4,
                "set_size": 4,
                "bridge_fraction": 0.25,
            },
        }
        invalid = (
            ("fixed_size", "unique_sets", 1),
            ("fixed_size", "set_size", 0),
            ("long_tail", "gamma", True),
            ("long_tail", "gamma", -0.1),
            ("long_tail", "gamma", 10**1_000),
            ("duplicate_heavy", "copy_factor", True),
            ("duplicate_heavy", "copy_factor", 0),
            ("dominated_heavy", "child_count", True),
            ("dominated_heavy", "child_count", -1),
            ("mixed_cluster", "bridge_fraction", True),
            ("mixed_cluster", "bridge_fraction", 1.01),
            ("mixed_cluster", "bridge_fraction", 10**1_000),
        )
        for family, field, value in invalid:
            case = dict(valid_cases[family])
            case[field] = value
            with self.subTest(family=family, field=field, value=value):
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(_minimal_config(case))
                self.assertIn(
                    f"$.cases[0].{field}",
                    {path for path, _ in caught.exception.issues},
                )

    def test_cross_parameter_capacity_errors_are_rejected(self) -> None:
        invalid_calls = (
            lambda: fixed_size(
                universe_size=3,
                set_count=4,
                k=1,
                set_size=3,
                unique_sets=True,
                seed=0,
            ),
            lambda: long_tail(
                universe_size=4,
                set_count=4,
                k=1,
                set_size=5,
                gamma=1,
                seed=0,
            ),
            lambda: duplicate_heavy(
                universe_size=3,
                base_set_count=4,
                k=1,
                set_size=3,
                copy_factor=2,
                seed=0,
            ),
            lambda: dominated_heavy(
                anchor_count=3,
                anchor_size=2,
                k=1,
                child_count=3,
                seed=0,
            ),
            lambda: mixed_cluster(
                universe_size=12,
                set_count=8,
                k=2,
                clusters=4,
                set_size=4,
                bridge_fraction=0.25,
                seed=0,
            ),
            lambda: mixed_cluster(
                universe_size=8,
                set_count=4,
                k=1,
                clusters=4,
                set_size=1,
                bridge_fraction=0.25,
                seed=0,
            ),
            lambda: uniform_random(
                universe_size=8,
                set_count=4,
                k=1,
                density=1e-12,
                paired_set_size=1,
                seed=0,
            ),
        )
        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call):
                with self.assertRaises(ValueError):
                    invalid_call()

    def test_cross_parameter_capacity_errors_have_parameter_paths(self) -> None:
        invalid_cases = (
            (
                {
                    "name": "duplicates",
                    "family": "duplicate_heavy",
                    "universe_size": 3,
                    "base_set_count": 4,
                    "k": 1,
                    "set_size": 3,
                    "copy_factor": 2,
                },
                "$.cases[0].base_set_count",
            ),
            (
                {
                    "name": "mixed",
                    "family": "mixed_cluster",
                    "universe_size": 12,
                    "set_count": 8,
                    "k": 2,
                    "clusters": 4,
                    "set_size": 4,
                    "bridge_fraction": 0.25,
                },
                "$.cases[0].set_size",
            ),
            (
                {
                    "name": "degenerate_bridge",
                    "family": "mixed_cluster",
                    "universe_size": 8,
                    "set_count": 4,
                    "k": 1,
                    "clusters": 4,
                    "set_size": 1,
                    "bridge_fraction": 0.25,
                },
                "$.cases[0].set_size",
            ),
            (
                {
                    "name": "impossible_expected_size",
                    "family": "uniform",
                    "universe_size": 8,
                    "set_count": 4,
                    "k": 1,
                    "density": 1e-12,
                    "paired_set_size": 1,
                },
                "$.cases[0].paired_set_size",
            ),
        )
        for case, expected_path in invalid_cases:
            with self.subTest(family=case["family"]):
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(_minimal_config(case))
                self.assertIn(
                    expected_path,
                    {path for path, _ in caught.exception.issues},
                )

    def test_mixed_cluster_accepts_all_bridge_capacity_without_specialists(self) -> None:
        instance = mixed_cluster(
            universe_size=7,
            set_count=4,
            k=1,
            clusters=4,
            set_size=2,
            bridge_fraction=1.0,
            seed=2,
            coupling_seed=2,
        )
        self.assertEqual(instance.parameters["bridge_count"], 4)
        self.assertTrue(all(mask.bit_count() == 2 for mask in instance.sets))

    def test_dominated_child_stream_is_nested_across_sampling_thresholds(self) -> None:
        small = dominated_heavy(
            anchor_count=2,
            anchor_size=6,
            k=1,
            child_count=5,
            seed=10,
            coupling_seed=2,
        )
        large = dominated_heavy(
            anchor_count=2,
            anchor_size=6,
            k=1,
            child_count=6,
            seed=11,
            coupling_seed=2,
        )
        anchor_count = 2
        self.assertEqual(
            small.sets[:anchor_count], large.sets[:anchor_count]
        )
        self.assertLessEqual(
            set(small.sets[anchor_count:]),
            set(large.sets[anchor_count:]),
        )

    def test_small_instances_have_zero_exact_algorithm_disagreement(self) -> None:
        for seed in range(10):
            instances = (
                fixed_size(
                    universe_size=10,
                    set_count=8,
                    k=3,
                    set_size=3,
                    unique_sets=True,
                    seed=seed,
                ),
                long_tail(
                    universe_size=10,
                    set_count=8,
                    k=3,
                    set_size=3,
                    gamma=1.5,
                    seed=seed,
                ),
                duplicate_heavy(
                    universe_size=10,
                    base_set_count=5,
                    k=2,
                    set_size=3,
                    copy_factor=2,
                    seed=seed,
                ),
                dominated_heavy(
                    anchor_count=4,
                    anchor_size=3,
                    k=2,
                    child_count=2,
                    seed=seed,
                ),
                mixed_cluster(
                    universe_size=12,
                    set_count=8,
                    k=2,
                    clusters=3,
                    set_size=2,
                    bridge_fraction=0.5,
                    seed=seed,
                ),
            )
            for instance in instances:
                with self.subTest(seed=seed, family=instance.family):
                    solutions = (
                        brute_force(instance, time_limit_seconds=None),
                        branch_and_bound(instance, time_limit_seconds=None),
                        branch_and_bound_enhanced(
                            instance, time_limit_seconds=None
                        ),
                    )
                    self.assertEqual(
                        {solution.status for solution in solutions},
                        {SolutionStatus.OPTIMAL},
                    )
                    self.assertEqual(
                        {solution.coverage for solution in solutions},
                        {solutions[0].coverage},
                    )


class P43ConfigurationAndPairingTests(unittest.TestCase):
    def test_all_family_configs_parse_and_include_control_plus_three_levels(self) -> None:
        configurations = {
            "long_tail": ("p4_long_tail.json", "gamma", 0.0),
            "duplicate_heavy": (
                "p4_duplicate_heavy.json",
                "copy_factor",
                1,
            ),
            "dominated_heavy": (
                "p4_dominated_heavy.json",
                "child_count",
                0,
            ),
            "mixed_cluster": (
                "p4_mixed_cluster.json",
                "bridge_fraction",
                0.0,
            ),
        }
        for family, (filename, intensity, control) in configurations.items():
            with self.subTest(family=family):
                config = load_config(ROOT / "configs" / filename)
                cases = [case for case in config.cases if case.family == family]
                levels = {case.parameters[intensity] for case in cases}
                self.assertIn(control, levels)
                self.assertGreaterEqual(len(levels - {control}), 3)

        fixed_config = load_config(ROOT / "configs" / "p4_fixed_size.json")
        fixed_cases = [case for case in fixed_config.cases if case.family == "fixed_size"]
        uniform_cases = [case for case in fixed_config.cases if case.family == "uniform"]
        self.assertGreaterEqual(len(fixed_cases), 4)
        self.assertEqual(len(fixed_cases), len(uniform_cases))
        fixed_by_size = {
            int(case.parameters["set_size"]): case for case in fixed_cases
        }
        for uniform_case in uniform_cases:
            universe_size = int(uniform_case.parameters["universe_size"])
            density = float(uniform_case.parameters["density"])
            expected_size = round(
                universe_size * density + (1.0 - density) ** universe_size,
                10,
            )
            self.assertEqual(expected_size, round(expected_size))
            fixed_case = fixed_by_size[int(round(expected_size))]
            for dimension in ("universe_size", "set_count", "k"):
                self.assertEqual(
                    fixed_case.parameters[dimension],
                    uniform_case.parameters[dimension],
                )

        expected_instances = {
            "p4_fixed_size.json": 80,
            "p4_long_tail.json": 40,
            "p4_duplicate_heavy.json": 40,
            "p4_dominated_heavy.json": 40,
            "p4_mixed_cluster.json": 40,
        }
        for filename, instance_count in expected_instances.items():
            with self.subTest(plan=filename):
                plan = plan_benchmark(load_config(ROOT / "configs" / filename))
                self.assertEqual(plan.instance_count, instance_count)
                self.assertEqual(plan.algorithm_run_count, instance_count * 5)
                self.assertEqual(
                    dict(plan.runs_by_algorithm)["brute_force"],
                    instance_count,
                )

    def test_paired_configs_share_coupling_keys_and_frozen_base_randomness(self) -> None:
        specifications = (
            ("p4_long_tail.json", "long_tail", "gamma"),
            ("p4_duplicate_heavy.json", "duplicate_heavy", "copy_factor"),
            ("p4_dominated_heavy.json", "dominated_heavy", "child_count"),
            ("p4_mixed_cluster.json", "mixed_cluster", "bridge_fraction"),
        )
        for filename, family, intensity in specifications:
            config = load_config(ROOT / "configs" / filename)
            grouped: dict[int, list[object]] = defaultdict(list)
            for planned in _instances_for_config(config):
                if planned.instance.family == family:
                    grouped[planned.repetition].append(planned)
            for repetition, group in grouped.items():
                with self.subTest(family=family, repetition=repetition):
                    self.assertEqual(len(group), 4)
                    self.assertEqual(len({item.coupling_pair_id for item in group}), 1)
                    self.assertNotIn(None, {item.coupling_pair_id for item in group})
                    self.assertEqual(len({item.coupling_seed for item in group}), 1)
                    self.assertNotIn(None, {item.coupling_seed for item in group})
                    for item in group:
                        self.assertEqual(
                            item.instance.parameters["coupling_seed"],
                            item.coupling_seed,
                        )

                    ordered = sorted(
                        group, key=lambda item: item.instance.parameters[intensity]
                    )
                    coupling_seed = ordered[0].coupling_seed
                    assert coupling_seed is not None
                    if family == "long_tail":
                        for item in ordered:
                            instance = item.instance
                            self.assertEqual(
                                instance.sets,
                                _long_tail_reference(
                                    universe_size=instance.universe_size,
                                    set_count=instance.set_count,
                                    set_size=int(instance.parameters["set_size"]),
                                    gamma=float(instance.parameters["gamma"]),
                                    coupling_seed=coupling_seed,
                                ),
                            )
                    elif family == "duplicate_heavy":
                        bases = []
                        for item in ordered:
                            copy_factor = int(item.instance.parameters["copy_factor"])
                            bases.append(item.instance.sets[::copy_factor])
                        self.assertEqual(len(set(bases)), 1)
                    elif family == "dominated_heavy":
                        anchor_count = int(ordered[0].instance.parameters["anchor_count"])
                        anchors = {
                            item.instance.sets[:anchor_count] for item in ordered
                        }
                        self.assertEqual(len(anchors), 1)
                        previous: set[int] = set()
                        for item in ordered:
                            children = set(item.instance.sets[anchor_count:])
                            self.assertLessEqual(previous, children)
                            previous = children
                    else:
                        for left, right in itertools.pairwise(ordered):
                            left_count = int(left.instance.parameters["bridge_count"])
                            right_count = int(right.instance.parameters["bridge_count"])
                            changed = sum(
                                before != after
                                for before, after in zip(
                                    left.instance.sets,
                                    right.instance.sets,
                                    strict=True,
                                )
                            )
                            self.assertEqual(changed, right_count - left_count)

    def test_fixed_size_controls_share_coupling_and_element_draws(self) -> None:
        config = load_config(ROOT / "configs" / "p4_fixed_size.json")
        grouped: dict[tuple[int, int], list[object]] = defaultdict(list)
        for planned in _instances_for_config(config):
            parameters = planned.instance.parameters
            if planned.instance.family == "fixed_size":
                paired_size = int(parameters["set_size"])
            else:
                paired_size = int(parameters["paired_set_size"])
            grouped[(planned.repetition, paired_size)].append(planned)

        self.assertEqual(len(grouped), 40)
        denominator = 1 << 53
        for (repetition, paired_size), group in grouped.items():
            with self.subTest(repetition=repetition, paired_size=paired_size):
                self.assertEqual(len(group), 2)
                self.assertEqual(
                    {item.instance.family for item in group},
                    {"fixed_size", "uniform"},
                )
                self.assertEqual(len({item.coupling_pair_id for item in group}), 1)
                self.assertNotIn(None, {item.coupling_pair_id for item in group})
                self.assertEqual(len({item.coupling_seed for item in group}), 1)
                coupling_seed = group[0].coupling_seed
                assert coupling_seed is not None
                by_family = {item.instance.family: item.instance for item in group}
                fixed = by_family["fixed_size"]
                uniform = by_family["uniform"]
                density = float(uniform.parameters["density"])

                rng = random.Random(
                    _derived_seed(
                        coupling_seed,
                        "fixed_size_uniform:elements",
                    )
                )
                for index in range(fixed.set_count):
                    draws = tuple(
                        rng.getrandbits(53) for _ in range(fixed.universe_size)
                    )
                    ranked = sorted(
                        range(fixed.universe_size),
                        key=lambda element: (draws[element], element),
                    )
                    expected_fixed = _mask(ranked[:paired_size])
                    selected_uniform = [
                        element
                        for element, draw in enumerate(draws)
                        if (draw + 0.5) / denominator < density
                    ]
                    if not selected_uniform:
                        selected_uniform = ranked[:1]
                    self.assertEqual(fixed.sets[index], expected_fixed)
                    self.assertEqual(
                        uniform.sets[index],
                        _mask(selected_uniform),
                    )

    def test_paired_uniform_control_requires_one_matching_fixed_case(self) -> None:
        config = parse_config(
            _minimal_config(
                {
                    "name": "orphan_control",
                    "family": "uniform",
                    "universe_size": 32,
                    "set_count": 4,
                    "k": 1,
                    "density": 0.2499968604411672,
                    "paired_set_size": 8,
                }
            )
        )
        with self.assertRaisesRegex(
            ValueError,
            "exactly one matching fixed_size and uniform case",
        ):
            plan_benchmark(config)

    def test_mixed_cluster_record_accepts_only_referenced_small_clusters(
        self,
    ) -> None:
        config = parse_config(
            _minimal_config(
                {
                    "name": "partial_cluster_cycle",
                    "family": "mixed_cluster",
                    "universe_size": 7,
                    "set_count": 2,
                    "k": 1,
                    "clusters": 4,
                    "set_size": 2,
                    "bridge_fraction": 0.0,
                }
            )
        )
        planned = _instances_for_config(config)[0]
        record = _instance_record(planned, "f" * 64)
        self.assertEqual(record.family, "mixed_cluster")
        self.assertEqual(record.mean_set_size, 2)

    def test_bnb_ablations_change_exactly_one_structural_option(self) -> None:
        specifications = (
            (
                "p4_duplicate_heavy.json",
                "bnb_without_deduplication",
                "bnb_with_deduplication",
                "remove_duplicates",
            ),
            (
                "p4_dominated_heavy.json",
                "bnb_without_dominance",
                "bnb_with_dominance",
                "remove_dominated",
            ),
        )

        def resolved_options(algorithm: object) -> dict[str, object]:
            options = algorithm.options
            return {
                "time_limit_seconds": options.time_limit_seconds,
                "max_set_count": options.max_set_count,
                **dict(options.values),
            }

        for filename, before_id, after_id, changed_option in specifications:
            config = load_config(ROOT / "configs" / filename)
            algorithms = {
                algorithm.algorithm_id: algorithm for algorithm in config.algorithms
            }
            before = algorithms[before_id]
            after = algorithms[after_id]
            self.assertEqual(before.name, "branch_and_bound_enhanced")
            self.assertEqual(after.name, "branch_and_bound_enhanced")
            before_options = resolved_options(before)
            after_options = resolved_options(after)
            differences = {
                name
                for name in before_options
                if before_options[name] != after_options[name]
            }
            self.assertEqual(differences, {changed_option})
            self.assertIs(before_options[changed_option], False)
            self.assertIs(after_options[changed_option], True)

    def test_instance_records_freeze_p4_3_provenance_and_round_trip(self) -> None:
        specifications = (
            (
                "p4_fixed_size.json",
                "fixed_size",
                "fixed_size_set_size_variation",
                "stochastic",
                True,
            ),
            (
                "p4_long_tail.json",
                "long_tail",
                "long_tail_coverage_skew",
                "stochastic",
                True,
            ),
            (
                "p4_duplicate_heavy.json",
                "duplicate_heavy",
                "duplicate_heavy_redundancy",
                "stochastic",
                True,
            ),
            (
                "p4_dominated_heavy.json",
                "dominated_heavy",
                "dominated_heavy_pruning",
                "constructed",
                True,
            ),
            (
                "p4_mixed_cluster.json",
                "mixed_cluster",
                "mixed_cluster_bridges",
                "stochastic",
                True,
            ),
        )
        research_ids = set()
        for filename, family, question, origin, coupled in specifications:
            config = load_config(ROOT / "configs" / filename)
            planned = next(
                item
                for item in _instances_for_config(config)
                if item.instance.family == family
            )
            record = _instance_record(planned, "f" * 64)
            research_ids.add(record.research_question_id)
            self.assertEqual(record.research_question_id, question)
            self.assertEqual(record.instance_origin, origin)
            self.assertFalse(record.is_adversarial)
            self.assertIsNone(record.adversarial_severity)
            self.assertIsNone(record.realized_trap_fraction)
            self.assertEqual(record.coupling_pair_id is not None, coupled)
            self.assertEqual(record.coupling_seed is not None, coupled)
            restored = InstanceRecord.from_csv_row(
                {
                    name: str(value)
                    for name, value in record.to_csv_row().items()
                }
            )
            self.assertEqual(restored.to_csv_row(), record.to_csv_row())

            if family == "dominated_heavy":
                self.assertEqual(
                    record.known_optimum,
                    record.k * int(planned.instance.parameters["anchor_size"]),
                )
                self.assertEqual(record.optimum_selected, tuple(range(record.k)))
                self.assertEqual(record.proof_kind, "disjoint_anchors")
            else:
                self.assertIsNone(record.known_optimum)
                self.assertIsNone(record.proof_kind)
        self.assertEqual(len(research_ids), 5)

        fixed_config = load_config(ROOT / "configs" / "p4_fixed_size.json")
        uniform_planned = next(
            item
            for item in _instances_for_config(fixed_config)
            if item.instance.family == "uniform"
        )
        uniform_record = _instance_record(uniform_planned, "f" * 64)
        self.assertEqual(
            uniform_record.research_question_id,
            "fixed_size_set_size_variation",
        )
        self.assertEqual(
            uniform_record.coupling_pair_id,
            uniform_planned.coupling_pair_id,
        )
        self.assertEqual(
            uniform_record.coupling_seed,
            uniform_planned.coupling_seed,
        )
        self.assertIsNotNone(uniform_record.coupling_pair_id)
        self.assertIsNotNone(uniform_record.coupling_seed)
        restored_uniform = InstanceRecord.from_csv_row(
            {
                name: str(value)
                for name, value in uniform_record.to_csv_row().items()
            }
        )
        self.assertEqual(
            restored_uniform.to_csv_row(),
            uniform_record.to_csv_row(),
        )
        stripped_uniform = {
            name: str(value)
            for name, value in uniform_record.to_csv_row().items()
        }
        stripped_uniform["research_question_id"] = ""
        stripped_uniform["coupling_pair_id"] = ""
        stripped_uniform["coupling_seed"] = ""
        with self.assertRaisesRegex(
            ValueError,
            "paired uniform",
        ):
            InstanceRecord.from_csv_row(stripped_uniform)

    def test_instance_records_reject_invalid_p4_3_parameters(self) -> None:
        mutations = (
            ("p4_fixed_size.json", "fixed_size", "set_size", True),
            ("p4_long_tail.json", "long_tail", "gamma", True),
            (
                "p4_duplicate_heavy.json",
                "duplicate_heavy",
                "copy_factor",
                0,
            ),
            (
                "p4_dominated_heavy.json",
                "dominated_heavy",
                "child_count",
                True,
            ),
            (
                "p4_mixed_cluster.json",
                "mixed_cluster",
                "bridge_count",
                -1,
            ),
        )
        for filename, family, field, value in mutations:
            config = load_config(ROOT / "configs" / filename)
            planned = next(
                item
                for item in _instances_for_config(config)
                if item.instance.family == family
            )
            record = _instance_record(planned, "f" * 64)
            parameters = json.loads(record.parameters)
            parameters[field] = value
            with self.subTest(family=family, field=field):
                with self.assertRaises((TypeError, ValueError)):
                    replace(
                        record,
                        parameters=json.dumps(
                            parameters,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )

        config = load_config(ROOT / "configs" / "p4_long_tail.json")
        planned = _instances_for_config(config)[0]
        record = _instance_record(planned, "f" * 64)
        parameters = json.loads(record.parameters)
        parameters["coupling_seed"] = True
        with self.assertRaises((TypeError, ValueError)):
            replace(
                record,
                coupling_seed=1,
                parameters=json.dumps(
                    parameters,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

    def test_unique_fixed_size_record_requires_unique_measured_sets(self) -> None:
        config = parse_config(
            _minimal_config(
                {
                    "name": "unique_fixed",
                    "family": "fixed_size",
                    "universe_size": 8,
                    "set_count": 4,
                    "k": 2,
                    "set_size": 3,
                    "unique_sets": True,
                }
            )
        )
        record = _instance_record(
            _instances_for_config(config)[0],
            "f" * 64,
        )
        with self.assertRaisesRegex(ValueError, "unique_sets"):
            replace(
                record,
                unique_set_count=record.set_count - 1,
                duplicate_set_count=1,
                duplicate_set_ratio=1 / record.set_count,
                preprocessed_set_count=record.set_count - 1,
            )

    def test_disjoint_anchor_proof_is_rejected_for_other_families(self) -> None:
        config = load_config(ROOT / "configs" / "p4_dominated_heavy.json")
        planned = _instances_for_config(config)[0]
        record = _instance_record(planned, "f" * 64)
        with self.assertRaisesRegex(
            ValueError,
            "disjoint_anchors proof requires a dominated_heavy instance",
        ):
            replace(
                record,
                family="custom_family",
                instance_origin="custom",
                research_question_id=None,
                coupling_pair_id=None,
                coupling_seed=None,
            )

    def test_independent_scan_blocks_have_distinct_coupling_identities(self) -> None:
        base_case = {
            "family": "long_tail",
            "universe_size": 16,
            "set_count": 8,
            "k": 2,
            "set_size": 4,
            "sweep": {"gamma": [0.0, 1.0]},
        }
        first = {"name": "first_scan", **base_case}
        second = {"name": "second_scan", **base_case}
        config = parse_config(
            {
                "schema_version": 3,
                "name": "independent scans",
                "base_seed": 4310,
                "repetitions": 2,
                "algorithms": [{"name": "greedy"}],
                "cases": [first, second],
            }
        )
        grouped: dict[tuple[str, int], set[str | None]] = defaultdict(set)
        for planned in _instances_for_config(config):
            grouped[(planned.instance.parameters["gamma"], planned.repetition)].add(
                planned.coupling_pair_id
            )
        for repetition in range(2):
            control_ids = grouped[(0.0, repetition)]
            treatment_ids = grouped[(1.0, repetition)]
            self.assertEqual(control_ids, treatment_ids)
            self.assertEqual(len(control_ids), 2)


if __name__ == "__main__":
    unittest.main()
