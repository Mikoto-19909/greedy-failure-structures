"""Adversarial Maximum Coverage instance constructions."""

from __future__ import annotations

import math
import random

from ._generator_common import (
    _derived_seed,
    _mask,
    _require_integer,
    _resolve_coupling_seed,
    _sample_unique_ranks,
    _unrank_combination_lexicographic,
)
from .model import MaximumCoverageInstance


def adversarial_greedy_trap(
    *,
    block_size: int,
    distractor_count: int = 4,
    construction_version: int = 1,
    trap_count: int | None = None,
    seed: int = 0,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Create the legacy or provable k=2 greedy-trap construction.

    Version 1 preserves the frozen P3 construction exactly. Version 2 uses a
    common-random-number distractor stream and an integer ``trap_count`` whose
    realized greedy gap has a closed-form certificate.
    """

    block_size = _require_integer("block_size", block_size, minimum=4)
    distractor_count = _require_integer(
        "distractor_count", distractor_count, minimum=0
    )
    seed = _require_integer("seed", seed)
    construction_version = _require_integer(
        "construction_version", construction_version, minimum=1, maximum=2
    )
    if construction_version == 1:
        if trap_count is not None:
            raise ValueError("trap_count must be omitted for construction_version 1")
        if coupling_seed is not None:
            raise ValueError("coupling_seed must be omitted for construction_version 1")
        return _adversarial_greedy_trap_v1(block_size, distractor_count, seed)

    minimum_trap_count = block_size // 2 + 1
    trap_count = _require_integer(
        "trap_count",
        trap_count,
        minimum=minimum_trap_count,
        maximum=block_size,
    )
    resolved_coupling_seed = (
        seed
        if coupling_seed is None
        else _require_integer("coupling_seed", coupling_seed)
    )
    return _adversarial_greedy_trap_v2(
        block_size,
        distractor_count,
        trap_count,
        seed,
        resolved_coupling_seed,
    )


def _adversarial_greedy_trap_v1(
    block_size: int, distractor_count: int, seed: int
) -> MaximumCoverageInstance:
    """Preserve the exact P3 bitmask and random-draw sequence."""

    rng = random.Random(seed)
    universe_size = block_size * 2
    left = tuple(range(block_size))
    right = tuple(range(block_size, universe_size))
    take = block_size // 2 + 1
    trap = _mask((*left[:take], *right[:take]))
    sets = [trap, _mask(left), _mask(right)]

    distractor_size = max(2, block_size // 2)
    for _ in range(distractor_count):
        elements = rng.sample(range(universe_size), distractor_size)
        sets.append(_mask(elements))

    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        2,
        family="adversarial",
        seed=seed,
        parameters={
            "block_size": block_size,
            "distractor_count": distractor_count,
        },
    )


def _potential_distractor_rankings(
    universe_size: int, distractor_count: int, coupling_seed: int
) -> tuple[tuple[int, ...], ...]:
    """Return a fixed candidate stream shared by every paired severity."""

    rng = random.Random(coupling_seed)
    return tuple(
        tuple(rng.sample(range(universe_size), universe_size))
        for _ in range(distractor_count)
    )


def _adversarial_greedy_trap_v2(
    block_size: int,
    distractor_count: int,
    trap_count: int,
    seed: int,
    coupling_seed: int,
) -> MaximumCoverageInstance:
    universe_size = 2 * block_size
    left = tuple(range(block_size))
    right = tuple(range(block_size, universe_size))
    trap_elements = (*left[:trap_count], *right[:trap_count])
    trap_members = frozenset(trap_elements)
    residual_limit = block_size - trap_count
    sets = [_mask(trap_elements), _mask(left), _mask(right)]

    for ranking in _potential_distractor_rankings(
        universe_size, distractor_count, coupling_seed
    ):
        if residual_limit == 0:
            chosen = ranking[:block_size]
        else:
            residual = [element for element in ranking if element not in trap_members]
            covered = [element for element in ranking if element in trap_members]
            new_elements = residual[: residual_limit - 1]
            chosen = (*new_elements, *covered[: block_size - len(new_elements)])
        sets.append(_mask(chosen))

    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        2,
        family="adversarial",
        seed=seed,
        parameters={
            "block_size": block_size,
            "distractor_count": distractor_count,
            "construction_version": 2,
            "trap_count": trap_count,
            "coupling_seed": coupling_seed,
        },
    )


def controlled_adversarial_greedy_trap(
    *,
    block_size: int,
    distractor_count: int,
    trap_count: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Create a certified greedy trap with exact incidence across severities."""

    block_size = _require_integer("block_size", block_size, minimum=4)
    distractor_count = _require_integer(
        "distractor_count", distractor_count, minimum=0
    )
    minimum_trap_count = block_size // 2 + 1
    trap_count = _require_integer(
        "trap_count",
        trap_count,
        minimum=minimum_trap_count,
        maximum=block_size - 1,
    )
    seed = _require_integer("seed", seed)
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
    universe_size = 2 * block_size
    left = tuple(range(block_size))
    right = tuple(range(block_size, universe_size))
    trap_elements = (*left[:trap_count], *right[:trap_count])
    trap = _mask(trap_elements)
    padding_size = 2 * (block_size - trap_count) + 1
    padding = _mask(trap_elements[:padding_size])

    smallest_trap = (
        *left[:minimum_trap_count],
        *right[:minimum_trap_count],
    )
    capacity = math.comb(len(smallest_trap), block_size)
    minimum_level_padding_size = 2 * (block_size - minimum_trap_count) + 1
    forbidden_rank = 0 if minimum_level_padding_size == block_size else None
    available_capacity = capacity - (forbidden_rank is not None)
    if distractor_count > available_capacity:
        raise ValueError(
            "distractor_count must not exceed the distinct controlled "
            "distractor capacity"
        )
    distractor_rng = random.Random(
        _derived_seed(
            resolved_coupling_seed,
            "controlled_adversarial:distractors",
        )
    )
    sampled_ranks = _sample_unique_ranks(
        distractor_rng, available_capacity, distractor_count
    )
    distractors = []
    for sampled_rank in sampled_ranks:
        rank = sampled_rank + 1 if forbidden_rank is not None else sampled_rank
        positions = _unrank_combination_lexicographic(
            len(smallest_trap), block_size, rank
        )
        distractors.append(_mask(smallest_trap[position] for position in positions))

    return MaximumCoverageInstance(
        universe_size,
        (trap, _mask(left), _mask(right), padding, *distractors),
        2,
        family="controlled_adversarial",
        seed=seed,
        parameters={
            "block_size": block_size,
            "distractor_count": distractor_count,
            "trap_count": trap_count,
            "coupling_seed": resolved_coupling_seed,
        },
    )
