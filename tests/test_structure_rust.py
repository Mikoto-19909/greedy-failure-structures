"""Exact parity and independent set-based checks for the optional Rust kernel."""
from __future__ import annotations

import importlib.util
import math
import random
import struct
from types import SimpleNamespace
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

    def test_old_or_noncallable_native_interface_fails_explicitly(self) -> None:
        for module in (SimpleNamespace(counts=lambda *_: None), SimpleNamespace(counts_packed=None)):
            with patch("maxcover.structure.import_module", return_value=module):
                self.assertIsNone(analyze_instance(MaximumCoverageInstance(1, (0,), 1)).pairwise_overlap_mean_jaccard)
                with self.assertRaisesRegex(ImportError, "rebuild/install"):
                    analyze_instance(MaximumCoverageInstance(1, (0,), 1), backend="rust")


@unittest.skipUnless(importlib.util.find_spec("maxcover_structure_native"), "optional Rust extension not installed")
class RustStructureTests(unittest.TestCase):
    def test_packed_counts_preserve_legacy_values_order_and_byte_order(self) -> None:
        import maxcover_structure_native as native
        for n, masks in ((1, (0,)), (129, (0, 1, 1 << 128, 1, (1 << 128) | 1)),
                         (257, ((1 << 257) - 1, (1 << 256) - 1, (1 << 255) - 1)),
                         (65537, ((1 << 65537) - 1, (1 << 65536) - 1, (1 << 65535) - 1))):
            buffers = [mask.to_bytes((n + 7) // 8, "little") for mask in masks]
            frequencies, pairs, dominated = native.counts(buffers, n)
            packed_frequencies, payload, packed_dominated = native.counts_packed(buffers, n)
            self.assertIsInstance(payload, bytes)
            self.assertEqual(payload, b"".join(struct.pack("<QQ", a, b) for a, b in pairs))
            self.assertEqual(list(struct.iter_unpack("<QQ", payload)), pairs)
            self.assertEqual((packed_frequencies, packed_dominated), (frequencies, dominated))

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
            for function in (native.counts, native.counts_packed):
                with self.subTest(masks=masks, n=n, function=function.__name__), self.assertRaises(ValueError):
                    function(masks, n)

    def test_all_partial_byte_tails_reject_without_poisoning_later_calls(self) -> None:
        import maxcover_structure_native as native
        for n in range(1, 138):
            width = (n + 7) // 8
            invalid = [[bytes(width - 1)], [bytes(width + 1)]]
            if n % 8:
                invalid.append([(1 << n).to_bytes(width, "little")])
            for buffers in invalid:
                for function, extra in ((native.counts, ()), (native.counts_packed, ()), (native.greedy, (1,)),
                                        (native.lazy_greedy, (1,))):
                    with self.subTest(n=n, function=function.__name__), self.assertRaises(ValueError):
                        function(buffers, n, *extra)
            # A rejected call must leave the next valid invocation usable.
            self.assertEqual(native.counts([bytes(width)], n), ([0] * n, [], 0))
            self.assertEqual(native.counts_packed([bytes(width)], n), ([0] * n, b"", 0))
            self.assertEqual(native.greedy([bytes(width)], n, 1), ([0], 1))
            self.assertEqual(native.lazy_greedy([bytes(width)], n, 1), ([(0, 0, 2)], 2, 1))

    def test_computation_errors_propagate(self) -> None:
        with patch("maxcover_structure_native.counts_packed", side_effect=RuntimeError("kernel failed")):
            with self.assertRaisesRegex(RuntimeError, "kernel failed"):
                analyze_instance(MaximumCoverageInstance(1, (0,), 1), backend="rust")

    def test_malformed_payloads_and_zero_denominator_are_not_hidden(self) -> None:
        for payload in (b"x", bytes(15), bytes(17), struct.pack("<QQQQ", 1, 1, 1, 1)):
            with patch("maxcover_structure_native.counts_packed", return_value=([1], payload, 1)):
                with self.assertRaises(ValueError):
                    analyze_instance(MaximumCoverageInstance(1, (0, 1), 1), backend="rust")
        with patch("maxcover_structure_native.counts_packed", return_value=([1], bytes(16), 1)):
            with self.assertRaises(ZeroDivisionError):
                analyze_instance(MaximumCoverageInstance(1, (0, 1), 1), backend="rust")

    def test_public_adapter_uses_packed_and_keeps_empty_pair_semantics(self) -> None:
        import maxcover_structure_native as native
        with patch.object(native, "counts", side_effect=AssertionError("legacy path called")), \
             patch.object(native, "counts_packed", wraps=native.counts_packed) as packed:
            for masks in ((0,), (0, 0, 0), (0, 1, 0, 1)):
                item = MaximumCoverageInstance(1, masks, 1)
                self.assertEqual(analyze_instance(item, backend="rust"), analyze_instance(item))
            self.assertEqual(packed.call_count, 3)

    def test_streaming_sum_consumes_the_original_sequence_once(self) -> None:
        import maxcover_structure_native as native
        item = MaximumCoverageInstance(9, (3, 6, 56, 0, 0), 2)
        expected = analyze_instance(item)
        _, pairs, _ = native.counts([m.to_bytes(2, "little") for m in item.sets], 9)
        original_sum = math.fsum
        seen = []
        def consume(values):
            self.assertIs(iter(values), values)
            seen.extend(values)
            self.assertEqual(list(values), [])
            return original_sum(seen)
        with patch("maxcover.structure.math.fsum", side_effect=consume) as summed:
            self.assertEqual(analyze_instance(item, backend="rust"), expected)
            summed.assert_called_once()
        self.assertEqual(seen, [a / b for a, b in pairs])
        self.assertEqual(len(seen), expected.pairwise_overlap_valid_pairs)
