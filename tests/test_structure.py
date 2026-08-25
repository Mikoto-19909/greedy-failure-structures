from __future__ import annotations

import math
import pickle
import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import (
    branch_and_bound,
    branch_and_bound_enhanced,
    brute_force,
)
from maxcover.generators import clustered, high_overlap, uniform_random
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_id
from maxcover.structure import InstanceStructureMetrics, analyze_instance


def _mask(*elements: int) -> int:
    value = 0
    for element in elements:
        value |= 1 << element
    return value


def _naive(instance: MaximumCoverageInstance) -> dict[str, object]:
    sets = [
        {element for element in range(instance.universe_size) if mask & (1 << element)}
        for mask in instance.sets
    ]
    incidence = sum(map(len, sets))
    pairs = [
        (left, right)
        for index, left in enumerate(sets)
        for right in sets[index + 1 :]
        if left | right
    ]
    jaccards = [len(left & right) / len(left | right) for left, right in pairs]
    frequencies = [
        sum(element in candidate for candidate in sets)
        for element in range(instance.universe_size)
    ]
    gini_numerator = sum(
        abs(left - right) for left in frequencies for right in frequencies
    )
    gini = (
        0.0
        if instance.universe_size == 1 or incidence == 0
        else gini_numerator / (2 * (instance.universe_size - 1) * incidence)
    )
    unique = {frozenset(candidate) for candidate in sets}
    dominated = sum(
        any(candidate < other for other in unique) for candidate in unique
    )
    return {
        "incidence_count": incidence,
        "covered_element_count": len(set().union(*sets)),
        "actual_density": incidence / (instance.universe_size * instance.set_count),
        "mean_set_size": incidence / instance.set_count,
        "pairwise_overlap_mean_jaccard": (
            None if not jaccards else sum(jaccards) / len(jaccards)
        ),
        "pairwise_overlap_total_pairs": instance.set_count * (instance.set_count - 1) // 2,
        "pairwise_overlap_valid_pairs": len(pairs),
        "coverage_skew_gini": gini,
        "unique_set_count": len(unique),
        "duplicate_set_count": instance.set_count - len(unique),
        "duplicate_set_ratio": (instance.set_count - len(unique)) / instance.set_count,
        "dominated_set_count": dominated,
        "dominated_set_ratio": dominated / instance.set_count,
        "dominated_unique_ratio": dominated / len(unique),
        "preprocessed_set_count": len(unique) - dominated,
    }


class StructureMetricTests(unittest.TestCase):
    def test_hand_checked_nested_fixture_and_boundaries(self) -> None:
        nested = MaximumCoverageInstance(
            universe_size=3,
            sets=(0, _mask(0), _mask(0, 1)),
            k=2,
        )
        metrics = analyze_instance(nested)
        self.assertEqual(
            metrics,
            InstanceStructureMetrics(
                incidence_count=3,
                covered_element_count=2,
                actual_density=1 / 3,
                mean_set_size=1,
                pairwise_overlap_mean_jaccard=1 / 6,
                pairwise_overlap_total_pairs=3,
                pairwise_overlap_valid_pairs=3,
                coverage_skew_gini=2 / 3,
                unique_set_count=3,
                duplicate_set_count=0,
                duplicate_set_ratio=0,
                dominated_set_count=2,
                dominated_set_ratio=2 / 3,
                dominated_unique_ratio=2 / 3,
                preprocessed_set_count=1,
            ),
        )

        fixtures = (
            ((0,), None, 0, 0),
            ((_mask(0),), None, 0, 0),
            ((_mask(0), _mask(1)), 0.0, 0, 0),
            ((_mask(0), _mask(0)), 1.0, 1, 0),
            ((0, 0), None, 1, 0),
        )
        for sets, overlap, duplicates, dominated in fixtures:
            with self.subTest(sets=sets):
                instance = MaximumCoverageInstance(3, sets, 1)
                result = analyze_instance(instance)
                self.assertEqual(result.pairwise_overlap_mean_jaccard, overlap)
                self.assertEqual(result.duplicate_set_count, duplicates)
                self.assertEqual(result.dominated_set_count, dominated)
                for field, expected in _naive(instance).items():
                    actual = getattr(result, field)
                    if isinstance(expected, float):
                        self.assertTrue(
                            math.isclose(
                                actual, expected, rel_tol=1e-12, abs_tol=1e-15
                            ),
                            (sets, field, actual, expected),
                        )
                    else:
                        self.assertEqual(actual, expected, (sets, field))

    def test_random_reference_corpus_and_permutation_invariance(self) -> None:
        for seed in range(1000):
            rng = random.Random(seed)
            universe_size = 1 + seed % 31
            set_count = 1 + (7 * seed) % 20
            k = 1 + (11 * seed) % set_count
            sets: list[int] = []
            for set_index in range(set_count):
                if set_index > 0 and set_index % 5 == 0:
                    sets.append(sets[-1])
                elif set_index % 7 == 0:
                    sets.append(0)
                else:
                    probability = (1 + (seed + set_index) % 9) / 10
                    sets.append(
                        sum(
                            1 << element
                            for element in range(universe_size)
                            if rng.random() < probability
                        )
                    )
            instance = MaximumCoverageInstance(universe_size, tuple(sets), k, seed=seed)
            actual = analyze_instance(instance)
            expected = _naive(instance)
            for field, value in expected.items():
                observed = getattr(actual, field)
                if isinstance(value, float):
                    self.assertTrue(
                        math.isclose(observed, value, rel_tol=1e-12, abs_tol=1e-15),
                        (seed, field, observed, value),
                    )
                else:
                    self.assertEqual(observed, value, (seed, field))

            if seed < 200:
                shuffled = list(sets)
                random.Random(seed + 10_000).shuffle(shuffled)
                permuted = analyze_instance(
                    MaximumCoverageInstance(universe_size, tuple(shuffled), k, seed=seed)
                )
                self.assertEqual(actual, permuted)

    def test_instance_inputs_are_defensively_frozen_and_pickle_safe(self) -> None:
        sets = [_mask(0), _mask(1)]
        parameters = {"nested": {"values": [1, 2]}}
        instance = MaximumCoverageInstance(3, sets, 1, parameters=parameters)
        identifier = instance_id(instance)
        sets[0] = 0
        parameters["nested"]["values"].append(3)
        self.assertEqual(instance.sets, (_mask(0), _mask(1)))
        self.assertEqual(instance.parameters["nested"]["values"], (1, 2))
        self.assertEqual(instance_id(instance), identifier)
        with self.assertRaises(TypeError):
            instance.parameters["new"] = 1
        with self.assertRaises(TypeError):
            instance.parameters._items = ()  # type: ignore[attr-defined]
        restored = pickle.loads(pickle.dumps(instance))
        self.assertEqual(restored, instance)
        self.assertEqual(instance_id(restored), identifier)

    def test_preprocessing_metrics_match_exact_search_on_500_structured_instances(
        self,
    ) -> None:
        rng = random.Random(20260720)
        for corpus_seed in range(500):
            universe_size = 1 + corpus_seed % 12
            set_count = 4 + (7 * corpus_seed) % 6
            anchor = rng.getrandbits(universe_size)
            if anchor == 0:
                anchor = 1 << rng.randrange(universe_size)
            sets = [anchor, anchor, anchor & (anchor - 1), 0]
            while len(sets) < set_count:
                sets.append(rng.getrandbits(universe_size))
            instance = MaximumCoverageInstance(
                universe_size=universe_size,
                sets=tuple(sets),
                k=1 + (11 * corpus_seed) % set_count,
            )
            metrics = analyze_instance(instance)
            brute = brute_force(instance, time_limit_seconds=None)
            baseline = branch_and_bound(instance, time_limit_seconds=None)
            enhanced = branch_and_bound_enhanced(instance, time_limit_seconds=None)
            with self.subTest(seed=corpus_seed):
                self.assertEqual(brute.coverage, baseline.coverage)
                self.assertEqual(brute.coverage, enhanced.coverage)
                search = enhanced.metadata["search"]
                self.assertEqual(
                    search["duplicate_sets_removed"], metrics.duplicate_set_count
                )
                self.assertEqual(
                    search["dominated_sets_removed"], metrics.dominated_set_count
                )
                self.assertEqual(
                    search["search_set_count"], metrics.preprocessed_set_count
                )


class GeneratorCalibrationTests(unittest.TestCase):
    def _assert_density_calibrated(
        self,
        instance: MaximumCoverageInstance,
        expected_sizes: list[float],
        variances: list[float],
    ) -> None:
        count = instance.set_count
        self.assertGreaterEqual(count, 5000)
        expected_density = sum(expected_sizes) / (instance.universe_size * count)
        standard_error = math.sqrt(sum(variances)) / (instance.universe_size * count)
        actual = analyze_instance(instance).actual_density
        tolerance = 5 * standard_error + 1 / (instance.universe_size * count)
        self.assertLessEqual(abs(actual - expected_density), tolerance)

    @staticmethod
    def _moments(probabilities: list[float]) -> tuple[float, float]:
        mean = sum(probabilities)
        zero = math.prod(1 - probability for probability in probabilities)
        second = sum(p * (1 - p) for p in probabilities) + mean * mean + zero
        repaired_mean = mean + zero
        return repaired_mean, second - repaired_mean * repaired_mean

    def test_existing_random_generators_match_repaired_density_theory(self) -> None:
        count = 5000
        uniform = uniform_random(
            universe_size=20, set_count=count, k=3, density=0.15, seed=1201
        )
        uniform_moments = self._moments([0.15] * 20)
        self._assert_density_calibrated(
            uniform,
            [uniform_moments[0]] * count,
            [uniform_moments[1]] * count,
        )

        overlap = high_overlap(
            universe_size=24,
            set_count=count,
            k=3,
            core_fraction=0.25,
            core_probability=0.8,
            peripheral_probability=0.08,
            seed=1202,
        )
        core_size = round(24 * 0.25)
        overlap_moments = self._moments(
            [0.8] * core_size + [0.08] * (24 - core_size)
        )
        self._assert_density_calibrated(
            overlap,
            [overlap_moments[0]] * count,
            [overlap_moments[1]] * count,
        )

        clustered_instance = clustered(
            universe_size=25,
            set_count=count,
            k=3,
            clusters=4,
            within_probability=0.7,
            outside_probability=0.05,
            seed=1203,
        )
        sizes = [0] * 4
        for element in range(25):
            sizes[min(3, element * 4 // 25)] += 1
        moments = [
            self._moments([0.7] * size + [0.05] * (25 - size))
            for size in sizes
        ]
        self._assert_density_calibrated(
            clustered_instance,
            [moments[index % 4][0] for index in range(count)],
            [moments[index % 4][1] for index in range(count)],
        )


if __name__ == "__main__":
    unittest.main()
