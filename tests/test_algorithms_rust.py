"""Optional native algorithms: exact results and independent set definitions."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import itertools
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import greedy, lazy_greedy
from maxcover.model import MaximumCoverageInstance


def set_reference(instance):
    """Use sets and a sorted bound table, never production bit operations/heap."""
    candidates = [set(i for i in range(instance.universe_size) if mask & (1 << i))
                  for mask in instance.sets]
    covered, selected, gains = set(), [], []
    available = set(range(instance.set_count))
    for _ in range(instance.k):
        chosen = min(available, key=lambda i: (-len(candidates[i] - covered), i))
        selected.append(chosen)
        gains.append(len(candidates[chosen] - covered))
        covered.update(candidates[chosen])
        available.remove(chosen)
    coverage = len(covered)

    bounds = {i: len(candidate) for i, candidate in enumerate(candidates)}
    covered, trajectory = set(), []
    evaluations, pops = len(candidates), 0
    for step in range(instance.k):
        while True:
            chosen = min(bounds, key=lambda i: (-bounds[i], i))
            del bounds[chosen]
            gain = len(candidates[chosen] - covered)
            evaluations += 1
            pops += 1
            if not bounds or (-gain, chosen) <= min((-b, i) for i, b in bounds.items()):
                covered.update(candidates[chosen])
                trajectory.append({"iteration": step + 1, "selected_index": chosen,
                                   "marginal_gain": gain, "marginal_evaluations": evaluations})
                break
            bounds[chosen] = gain
    return selected, gains, coverage, trajectory, evaluations, pops


class AlgorithmBackendTests(unittest.TestCase):
    def test_defaults_do_not_load_native_and_unknown_backend_is_rejected(self):
        instance = MaximumCoverageInstance(1, (0, 1), 2)
        with patch("maxcover.algorithms.import_module", side_effect=ModuleNotFoundError("native")):
            for algorithm in (greedy, lazy_greedy):
                self.assertEqual(algorithm(instance).selected, (0, 1))
                with self.assertRaises(ValueError):
                    algorithm(instance, backend="typo")
                with self.assertRaises(ModuleNotFoundError):
                    algorithm(instance, backend="rust")


@unittest.skipUnless(importlib.util.find_spec("maxcover_structure_native"),
                     "optional Rust extension not installed")
class RustAlgorithmTests(unittest.TestCase):
    def check_instance(self, instance):
        selected, gains, coverage, trajectory, evaluations, pops = set_reference(instance)
        for algorithm in (greedy, lazy_greedy):
            actual = algorithm(instance, backend="rust")
            reference = algorithm(instance)
            self.assertEqual(replace(actual, runtime_seconds=0),
                             replace(reference, runtime_seconds=0))
            self.assertEqual(actual.selected, tuple(sorted(selected)))
            self.assertEqual(actual.feasible_value, coverage)
            self.assertEqual(len(actual.selected), instance.k)
            if algorithm is greedy:
                import maxcover_structure_native as native
                width = (instance.universe_size + 7) // 8
                ordered, work = native.greedy(
                    [mask.to_bytes(width, "little") for mask in instance.sets],
                    instance.universe_size, instance.k)
                self.assertEqual(ordered, selected)
                self.assertEqual(work, actual.nodes_or_iterations)
                self.assertEqual(actual.nodes_or_iterations,
                                 sum(instance.set_count - i for i in range(instance.k)))
            else:
                self.assertEqual(actual.metadata["trajectory"], trajectory)
                self.assertEqual([row["selected_index"] for row in trajectory], selected)
                self.assertEqual([row["marginal_gain"] for row in trajectory], gains)
                self.assertEqual(actual.nodes_or_iterations, evaluations)
                self.assertEqual(actual.metadata["search"]["priority_queue_pops"], pops)

    def test_exhaustive_three_element_three_candidate_instances(self):
        for masks in itertools.product(range(8), repeat=3):
            for k in (1, 2, 3):
                with self.subTest(masks=masks, k=k):
                    self.check_instance(MaximumCoverageInstance(3, masks, k))

    def test_word_boundaries_duplicates_nesting_and_seeded_inputs(self):
        rng = random.Random(1909)
        for n in (1, 7, 8, 63, 64, 65, 127, 128, 129, 257, 1025):
            full, high = (1 << n) - 1, 1 << (n - 1)
            fixtures = [(0,), (0, 0, 0, 0), (full, full, 0, high),
                        (0, 1, high, high | 1, full)]
            fixtures += [tuple(rng.getrandbits(n) for _ in range(rng.randrange(2, 20)))
                         for _ in range(20)]
            for masks in fixtures:
                for k in sorted({1, len(masks), max(1, len(masks) // 2)}):
                    with self.subTest(n=n, masks=masks, k=k):
                        self.check_instance(MaximumCoverageInstance(n, masks, k))

    def test_sparse_large_universe_and_input_immutability(self):
        instance = MaximumCoverageInstance(65537, (1 << 65536, 1, 0, (1 << 32768) | 1), 4)
        before = instance.sets
        self.check_instance(instance)
        self.assertIs(instance.sets, before)

    def test_existing_generator_families_match_independent_definition(self):
        from test_lazy_greedy import _reference_instances
        for instance in _reference_instances():
            with self.subTest(family=instance.family, seed=instance.seed):
                self.check_instance(instance)

    def test_seeded_sparse_dense_nested_and_duplicate_mixtures(self):
        rng = random.Random(20260919)
        for case in range(600):
            n = rng.choice((7, 63, 64, 65, 129, 257, 1025))
            m = rng.randrange(1, 49)
            masks = []
            for index in range(m):
                mode = case % 5
                if mode == 0:
                    mask = sum(1 << bit for bit in rng.sample(range(n), min(n, 3)))
                elif mode == 1 and masks:
                    mask = rng.choice(masks)
                elif mode == 2 and masks:
                    mask = masks[-1] & rng.getrandbits(n)
                elif mode == 3:
                    mask = rng.choice((0, (1 << n) - 1, 1 << (n - 1)))
                else:
                    mask = rng.getrandbits(n)
                masks.append(mask)
            instance = MaximumCoverageInstance(n, tuple(masks), rng.randrange(1, m + 1))
            with self.subTest(case=case, n=n, m=m, k=instance.k):
                self.check_instance(instance)

    def test_element_embedding_and_replication_preserve_decisions(self):
        rng = random.Random(20260920)
        for case in range(80):
            masks = tuple(rng.randrange(1 << 9) for _ in range(12))
            base = MaximumCoverageInstance(9, masks, 8)
            positions = rng.sample(range(257), 9)
            embedded = MaximumCoverageInstance(257, tuple(
                sum(1 << positions[bit] for bit in range(9) if mask & (1 << bit))
                for mask in masks), 8)
            replicated = MaximumCoverageInstance(129, tuple(
                sum((1 << bit) | (1 << (bit + 64)) | (1 << (bit + 120))
                    for bit in range(9) if mask & (1 << bit)) for mask in masks), 8)
            for algorithm in (greedy, lazy_greedy):
                expected = algorithm(base)
                for changed, factor in ((embedded, 1), (replicated, 3)):
                    with self.subTest(case=case, algorithm=algorithm.__name__, factor=factor):
                        actual = algorithm(changed, backend="rust")
                        self.assertEqual(actual.selected, expected.selected)
                        self.assertEqual(actual.feasible_value, expected.feasible_value * factor)
                        self.assertEqual(actual.nodes_or_iterations, expected.nodes_or_iterations)
                        if algorithm is lazy_greedy:
                            self.assertEqual(actual.metadata["search"], expected.metadata["search"])
                            self.assertEqual(actual.metadata["trajectory"], [
                                {**row, "marginal_gain": row["marginal_gain"] * factor}
                                for row in expected.metadata["trajectory"]])

    def test_native_rejects_invalid_masks_and_budgets(self):
        import maxcover_structure_native as native
        cases = (([], 1, 1), ([b""], 0, 1), ([b""], 1, 1),
                 ([b"\x80"], 7, 1), ([b"\x00\x02"], 9, 1),
                 ([b"\x00"], 1, 0), ([b"\x00"], 1, 2))
        for algorithm in (native.greedy, native.lazy_greedy):
            for masks, n, k in cases:
                with self.subTest(algorithm=algorithm.__name__, n=n, k=k), self.assertRaises(ValueError):
                    algorithm(masks, n, k)
            with self.assertRaises(OverflowError):
                algorithm([b"\x00"], 1, -1)
            with self.assertRaises(TypeError):
                algorithm(None, 1, 1)

    def test_native_errors_propagate_without_python_fallback(self):
        instance = MaximumCoverageInstance(1, (1,), 1)
        for algorithm in (greedy, lazy_greedy):
            with patch(f"maxcover_structure_native.{algorithm.__name__}",
                       side_effect=RuntimeError("kernel failed")):
                with self.assertRaisesRegex(RuntimeError, "kernel failed"):
                    algorithm(instance, backend="rust")


if __name__ == "__main__":
    unittest.main()
