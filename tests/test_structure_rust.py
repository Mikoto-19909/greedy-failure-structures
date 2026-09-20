"""Exact parity and independent set-based checks for the optional Rust kernel."""
from __future__ import annotations

import importlib.util
import random
import unittest
from unittest.mock import patch

from test_structure import _naive
from maxcover.model import MaximumCoverageInstance
from maxcover.structure import analyze_instance


class StructureBackendTests(unittest.TestCase):
    def test_unknown_backend_and_missing_extension(self) -> None:
        instance = MaximumCoverageInstance(1, (0,), 1)
        with self.assertRaises(ValueError):
            analyze_instance(instance, backend="typo")
        with patch("maxcover.structure.import_module", side_effect=ModuleNotFoundError):
            analyze_instance(instance)
            with self.assertRaises(ModuleNotFoundError):
                analyze_instance(instance, backend="rust")


@unittest.skipUnless(importlib.util.find_spec("maxcover_structure_native"), "optional Rust extension not installed")
class RustStructureTests(unittest.TestCase):
    def test_raw_counts_preserve_element_and_pair_order(self) -> None:
        import maxcover_structure_native as native
        candidates = [set(), {0, 64}, {64, 128}, {0, 64}, set()]
        masks = [sum(1 << bit for bit in candidate).to_bytes(17, "little") for candidate in candidates]
        frequencies, pairs, dominated = native.counts(masks, 129)
        self.assertEqual(frequencies, [sum(bit in candidate for candidate in candidates) for bit in range(129)])
        self.assertEqual(pairs, [(len(left & right), len(left | right))
                                for i, left in enumerate(candidates)
                                for right in candidates[i + 1:] if left | right])
        self.assertEqual(dominated, 1)

    def test_exact_parity_and_independent_definition(self) -> None:
        rng = random.Random(1709)
        for n in (1, 7, 8, 63, 64, 65, 127, 128, 129, 257):
            fixtures = [(0,), (0, 0), (0, 1, (1 << n) - 1), ((1 << (n - 1)),) * 3]
            fixtures += [tuple(rng.getrandbits(n) for _ in range(rng.randrange(1, 25))) for _ in range(30)]
            for masks in fixtures:
                instance = MaximumCoverageInstance(n, masks, 1)
                with self.subTest(n=n, masks=masks):
                    actual = analyze_instance(instance, backend="rust")
                    self.assertEqual(actual, analyze_instance(instance))
                    for name, expected in _naive(instance).items():
                        if isinstance(expected, float):
                            self.assertAlmostEqual(getattr(actual, name), expected, places=14)
                        else:
                            self.assertEqual(getattr(actual, name), expected)

    def test_native_rejects_invalid_buffers(self) -> None:
        import maxcover_structure_native as native
        for masks, n in (([], 1), ([b""], 0), ([b""], 1), ([b"\x80"], 7), ([b"\x00\x02"], 9)):
            with self.subTest(masks=masks, n=n), self.assertRaises(ValueError):
                native.counts(masks, n)

    def test_all_partial_byte_tails_reject_without_poisoning_later_calls(self) -> None:
        import maxcover_structure_native as native
        for n in range(1, 138):
            width = (n + 7) // 8
            invalid = [[bytes(width - 1)], [bytes(width + 1)]]
            if n % 8:
                invalid.append([(1 << n).to_bytes(width, "little")])
            for buffers in invalid:
                for function, extra in ((native.counts, ()), (native.greedy, (1,)),
                                        (native.lazy_greedy, (1,))):
                    with self.subTest(n=n, function=function.__name__), self.assertRaises(ValueError):
                        function(buffers, n, *extra)
            # A rejected call must leave the next valid invocation usable.
            self.assertEqual(native.counts([bytes(width)], n), ([0] * n, [], 0))
            self.assertEqual(native.greedy([bytes(width)], n, 1), ([0], 1))
            self.assertEqual(native.lazy_greedy([bytes(width)], n, 1), ([(0, 0, 2)], 2, 1))

    def test_computation_errors_propagate(self) -> None:
        with patch("maxcover_structure_native.counts", side_effect=RuntimeError("kernel failed")):
            with self.assertRaisesRegex(RuntimeError, "kernel failed"):
                analyze_instance(MaximumCoverageInstance(1, (0,), 1), backend="rust")
