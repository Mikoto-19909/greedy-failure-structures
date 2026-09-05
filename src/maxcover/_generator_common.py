"""Shared deterministic helpers for synthetic instance generators."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterable


def _mask(elements: Iterable[int]) -> int:
    value = 0
    for element in elements:
        value |= 1 << element
    return value


def _require_integer(
    name: str,
    value: object,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def _resolve_coupling_seed(seed: int, coupling_seed: object) -> int:
    if coupling_seed is None:
        return seed
    return _require_integer("coupling_seed", coupling_seed)


def _derived_seed(seed: int, namespace: str, index: int = 0) -> int:
    """Derive a stable child seed without relying on Python's salted hash."""

    payload = f"maxcover\0{namespace}\0{seed}\0{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:16], "big")


def _sample_unique_ranks(
    rng: random.Random, population_size: int, sample_size: int
) -> tuple[int, ...]:
    """Sample integer ranks without replacement and without rejection loops."""

    try:
        return tuple(rng.sample(range(population_size), sample_size))
    except OverflowError:
        # ``random.sample(range(...))`` is limited by ``Py_ssize_t`` even though
        # ``randrange`` supports arbitrary Python integers.  Floyd's algorithm
        # preserves a bounded O(sample_size) path for very large combination
        # spaces.
        selected: set[int] = set()
        result: list[int] = []
        for upper in range(population_size - sample_size, population_size):
            candidate = rng.randrange(upper + 1)
            chosen = upper if candidate in selected else candidate
            selected.add(chosen)
            result.append(chosen)
        rng.shuffle(result)
        return tuple(result)


def _unrank_combination_lexicographic(
    universe_size: int, set_size: int, rank: int
) -> tuple[int, ...]:
    """Return the zero-based lexicographic combination at ``rank``."""

    capacity = math.comb(universe_size, set_size)
    if rank < 0 or rank >= capacity:
        raise ValueError("combination rank is outside the available range")
    if set_size == 0:
        return ()

    result: list[int] = []
    lower = 0
    remaining_rank = rank
    for remaining in range(set_size, 0, -1):
        maximum = universe_size - remaining
        for element in range(lower, maximum + 1):
            suffix_count = math.comb(
                universe_size - element - 1, remaining - 1
            )
            if remaining_rank < suffix_count:
                result.append(element)
                lower = element + 1
                break
            remaining_rank -= suffix_count
    return tuple(result)


def _validate_standard_dimensions(
    universe_size: object,
    set_count: object,
    k: object,
    seed: object,
) -> tuple[int, int, int, int]:
    universe = _require_integer("universe_size", universe_size, minimum=1)
    count = _require_integer("set_count", set_count, minimum=1)
    budget = _require_integer("k", k, minimum=1, maximum=count)
    validated_seed = _require_integer("seed", seed)
    return universe, count, budget, validated_seed
