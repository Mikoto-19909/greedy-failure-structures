"""Controlled Maximum Coverage instance constructions."""

from __future__ import annotations

import random

from ._generator_common import (
    _derived_seed,
    _mask,
    _require_integer,
    _resolve_coupling_seed,
    _validate_standard_dimensions,
)
from .model import MaximumCoverageInstance


def _controlled_element_order(
    *,
    universe_size: int,
    required_size: int,
    coupling_seed: int,
    namespace: str,
) -> tuple[int, ...]:
    """Return one stable pool assignment shared across intensity levels."""

    if universe_size < required_size:
        raise ValueError(
            f"universe_size must be at least {required_size} for {namespace}"
        )
    rng = random.Random(_derived_seed(coupling_seed, namespace))
    return tuple(rng.sample(range(universe_size), required_size))


def controlled_high_overlap(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    set_size: int,
    shared_core_size: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Vary one shared core while holding dimensions and incidence exact."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    shared_core_size = _require_integer(
        "shared_core_size", shared_core_size, minimum=0, maximum=set_size - 1
    )
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
    order = _controlled_element_order(
        universe_size=universe_size,
        required_size=(set_count + 1) * set_size,
        coupling_seed=resolved_coupling_seed,
        namespace="controlled_high_overlap:pools",
    )
    core = order[:set_size]
    sets = []
    for index in range(set_count):
        start = set_size + index * set_size
        peripheral = order[start : start + set_size]
        sets.append(
            _mask((*core[:shared_core_size], *peripheral[: set_size - shared_core_size]))
        )
    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="controlled_high_overlap",
        seed=seed,
        parameters={
            "set_size": set_size,
            "shared_core_size": shared_core_size,
            "coupling_seed": resolved_coupling_seed,
        },
    )


def controlled_clustered(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    clusters: int,
    set_size: int,
    within_core_size: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Vary cluster cores while holding dimensions and incidence exact."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    clusters = _require_integer(
        "clusters", clusters, minimum=2, maximum=universe_size
    )
    if set_count < 2 * clusters:
        raise ValueError("set_count must be at least twice clusters")
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    within_core_size = _require_integer(
        "within_core_size", within_core_size, minimum=0, maximum=set_size - 1
    )
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
    order = _controlled_element_order(
        universe_size=universe_size,
        required_size=(clusters + set_count) * set_size,
        coupling_seed=resolved_coupling_seed,
        namespace="controlled_clustered:pools",
    )
    core_span = clusters * set_size
    sets = []
    for index in range(set_count):
        cluster = index % clusters
        core_start = cluster * set_size
        core = order[core_start : core_start + set_size]
        peripheral_start = core_span + index * set_size
        peripheral = order[peripheral_start : peripheral_start + set_size]
        sets.append(
            _mask((*core[:within_core_size], *peripheral[: set_size - within_core_size]))
        )
    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="controlled_clustered",
        seed=seed,
        parameters={
            "clusters": clusters,
            "set_size": set_size,
            "within_core_size": within_core_size,
            "coupling_seed": resolved_coupling_seed,
        },
    )


def controlled_duplicate(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    set_size: int,
    copy_factor: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Vary balanced copies while holding dimensions and incidence exact."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    copy_factor = _require_integer(
        "copy_factor", copy_factor, minimum=1, maximum=set_count
    )
    if set_count % copy_factor:
        raise ValueError("copy_factor must divide set_count")
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
    order = _controlled_element_order(
        universe_size=universe_size,
        required_size=set_count * set_size,
        coupling_seed=resolved_coupling_seed,
        namespace="controlled_duplicate:bases",
    )
    bases = tuple(
        _mask(order[index * set_size : (index + 1) * set_size])
        for index in range(set_count)
    )
    unique_count = set_count // copy_factor
    sets = tuple(
        mask for mask in bases[:unique_count] for _ in range(copy_factor)
    )
    return MaximumCoverageInstance(
        universe_size,
        sets,
        k,
        family="controlled_duplicate",
        seed=seed,
        parameters={
            "set_size": set_size,
            "copy_factor": copy_factor,
            "coupling_seed": resolved_coupling_seed,
        },
    )


def controlled_dominated(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    anchor_size: int,
    child_size: int,
    dominated_pair_count: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Convert disjoint neutral pairs to subset pairs at fixed incidence."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    if set_count % 2:
        raise ValueError("set_count must be even")
    anchor_size = _require_integer(
        "anchor_size", anchor_size, minimum=2, maximum=universe_size
    )
    child_size = _require_integer(
        "child_size", child_size, minimum=1, maximum=anchor_size - 1
    )
    pair_count = set_count // 2
    dominated_pair_count = _require_integer(
        "dominated_pair_count",
        dominated_pair_count,
        minimum=0,
        maximum=pair_count,
    )
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
    pair_span = anchor_size + child_size
    order = _controlled_element_order(
        universe_size=universe_size,
        required_size=pair_count * pair_span,
        coupling_seed=resolved_coupling_seed,
        namespace="controlled_dominated:pairs",
    )
    sets: list[int] = []
    for index in range(pair_count):
        start = index * pair_span
        anchor_elements = order[start : start + anchor_size]
        if index < dominated_pair_count:
            companion_elements = anchor_elements[:child_size]
        else:
            companion_elements = order[
                start + anchor_size : start + anchor_size + child_size
            ]
        sets.extend((_mask(anchor_elements), _mask(companion_elements)))
    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="controlled_dominated",
        seed=seed,
        parameters={
            "anchor_size": anchor_size,
            "child_size": child_size,
            "dominated_pair_count": dominated_pair_count,
            "coupling_seed": resolved_coupling_seed,
        },
    )
