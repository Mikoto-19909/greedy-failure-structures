"""Exact instance-level structural metrics for Maximum Coverage inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import MaximumCoverageInstance


@dataclass(frozen=True, slots=True)
class InstanceStructureMetrics:
    """Exact structural facts derived only from an instance's final bitmasks."""

    incidence_count: int
    covered_element_count: int
    actual_density: float
    mean_set_size: float
    pairwise_overlap_mean_jaccard: float | None
    pairwise_overlap_total_pairs: int
    pairwise_overlap_valid_pairs: int
    coverage_skew_gini: float
    unique_set_count: int
    duplicate_set_count: int
    duplicate_set_ratio: float
    dominated_set_count: int
    dominated_set_ratio: float
    dominated_unique_ratio: float
    preprocessed_set_count: int


def _coverage_frequencies(instance: MaximumCoverageInstance) -> list[int]:
    frequencies = [0] * instance.universe_size
    for mask in instance.sets:
        remaining = mask
        while remaining:
            lowest = remaining & -remaining
            frequencies[lowest.bit_length() - 1] += 1
            remaining ^= lowest
    return frequencies


def _coverage_gini(frequencies: list[int], incidence_count: int) -> float:
    if len(frequencies) == 1 or incidence_count == 0:
        return 0.0
    ordered = sorted(frequencies)
    numerator = sum(
        (2 * index - len(ordered) - 1) * value
        for index, value in enumerate(ordered, start=1)
    )
    return numerator / ((len(ordered) - 1) * incidence_count)


def analyze_instance(instance: MaximumCoverageInstance) -> InstanceStructureMetrics:
    """Compute the frozen P4.1 metric contract without sampling or side effects."""

    sizes = [mask.bit_count() for mask in instance.sets]
    incidence_count = sum(sizes)
    set_count = instance.set_count
    universe_size = instance.universe_size
    frequencies = _coverage_frequencies(instance)

    total_pairs = set_count * (set_count - 1) // 2
    jaccards: list[float] = []
    for left_index, left in enumerate(instance.sets):
        for right in instance.sets[left_index + 1 :]:
            union = left | right
            if union == 0:
                continue
            jaccards.append((left & right).bit_count() / union.bit_count())
    valid_pairs = len(jaccards)
    mean_jaccard = None if valid_pairs == 0 else math.fsum(jaccards) / valid_pairs

    unique_masks = tuple(dict.fromkeys(instance.sets))
    dominated = sum(
        any(mask != other and mask & other == mask for other in unique_masks)
        for mask in unique_masks
    )
    unique_count = len(unique_masks)
    duplicate_count = set_count - unique_count

    return InstanceStructureMetrics(
        incidence_count=incidence_count,
        covered_element_count=sum(frequency > 0 for frequency in frequencies),
        actual_density=incidence_count / (universe_size * set_count),
        mean_set_size=incidence_count / set_count,
        pairwise_overlap_mean_jaccard=mean_jaccard,
        pairwise_overlap_total_pairs=total_pairs,
        pairwise_overlap_valid_pairs=valid_pairs,
        coverage_skew_gini=_coverage_gini(frequencies, incidence_count),
        unique_set_count=unique_count,
        duplicate_set_count=duplicate_count,
        duplicate_set_ratio=duplicate_count / set_count,
        dominated_set_count=dominated,
        dominated_set_ratio=dominated / set_count,
        dominated_unique_ratio=dominated / unique_count,
        preprocessed_set_count=unique_count - dominated,
    )
