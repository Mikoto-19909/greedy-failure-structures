"""Controlled synthetic Maximum Coverage instance families."""

from __future__ import annotations

import math
import random
import sys
from collections.abc import Iterable, Mapping
from typing import cast

from ._generator_common import (
    _mask,
    _require_integer,
    _resolve_coupling_seed,
    _derived_seed,
    _sample_unique_ranks,
    _unrank_combination_lexicographic,
    _validate_standard_dimensions,
)
from ._generators_adversarial import (
    adversarial_greedy_trap,
    controlled_adversarial_greedy_trap,
)
from ._generators_controlled import (
    controlled_high_overlap,
    controlled_clustered,
    controlled_duplicate,
    controlled_dominated,
)
from .contracts import GeneratorSpec, ParameterSpec
from .model import MaximumCoverageInstance


def _ensure_nonempty(mask: int, universe_size: int, rng: random.Random) -> int:
    return mask or (1 << rng.randrange(universe_size))


def _require_probability(
    name: str,
    value: object,
    *,
    positive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as error:
        interval = "(0, 1]" if positive else "[0, 1]"
        raise ValueError(f"{name} must be in {interval}") from error
    lower_valid = numeric > 0 if positive else numeric >= 0
    if not lower_valid or numeric > 1:
        interval = "(0, 1]" if positive else "[0, 1]"
        raise ValueError(f"{name} must be in {interval}")
    return numeric


def _require_nonnegative_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            f"{name} must be finite and non-negative"
        ) from error
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return numeric


def _require_boolean(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _paired_cardinality_draws(
    universe_size: int, set_count: int, coupling_seed: int
) -> Iterable[tuple[int, ...]]:
    """Yield shared element draws for fixed-size/Bernoulli control pairs."""

    rng = random.Random(
        _derived_seed(coupling_seed, "fixed_size_uniform:elements")
    )
    for _ in range(set_count):
        yield tuple(rng.getrandbits(53) for _ in range(universe_size))


def _sample_stable_rank_prefix(
    rng: random.Random, population_size: int, sample_size: int
) -> tuple[int, ...]:
    """Return a uniform ordered sample whose prefixes are stable across sizes."""

    swaps: dict[int, int] = {}
    result: list[int] = []
    for index in range(sample_size):
        selected_index = rng.randrange(index, population_size)
        selected_value = swaps.get(selected_index, selected_index)
        index_value = swaps.get(index, index)
        if selected_index != index:
            swaps[selected_index] = index_value
        swaps.pop(index, None)
        result.append(selected_value)
    return tuple(result)


def uniform_random(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    density: float,
    seed: int,
    paired_set_size: int | None = None,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    density = _require_probability("density", density, positive=True)
    if paired_set_size is None:
        if coupling_seed is not None:
            raise ValueError(
                "coupling_seed must be omitted without paired_set_size"
            )
        rng = random.Random(seed)
        sets = []
        for _ in range(set_count):
            candidate = _mask(
                element
                for element in range(universe_size)
                if rng.random() < density
            )
            sets.append(_ensure_nonempty(candidate, universe_size, rng))
        parameters: dict[str, object] = {"density": density}
    else:
        paired_set_size = _require_integer(
            "paired_set_size",
            paired_set_size,
            minimum=2,
            maximum=universe_size,
        )
        expected_size = (
            universe_size * density + (1.0 - density) ** universe_size
        )
        if not math.isclose(
            expected_size,
            paired_set_size,
            rel_tol=1e-10,
            abs_tol=1e-10,
        ):
            raise ValueError(
                "density must produce the declared paired_set_size in expectation"
            )
        resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
        denominator = 1 << 53
        sets = []
        for draws in _paired_cardinality_draws(
            universe_size, set_count, resolved_coupling_seed
        ):
            ranked = sorted(
                range(universe_size),
                key=lambda element: (draws[element], element),
            )
            selected = [
                element
                for element, draw in enumerate(draws)
                if (draw + 0.5) / denominator < density
            ]
            sets.append(_mask(selected or ranked[:1]))
        parameters = {
            "density": density,
            "paired_set_size": paired_set_size,
            "coupling_seed": resolved_coupling_seed,
        }
    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="uniform",
        seed=seed,
        parameters=parameters,
    )


def high_overlap(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    core_fraction: float,
    core_probability: float,
    peripheral_probability: float,
    seed: int,
) -> MaximumCoverageInstance:
    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    core_fraction = _require_probability(
        "core_fraction", core_fraction, positive=True
    )
    core_probability = _require_probability(
        "core_probability", core_probability
    )
    peripheral_probability = _require_probability(
        "peripheral_probability", peripheral_probability
    )
    rng = random.Random(seed)
    core_size = max(1, min(universe_size, round(universe_size * core_fraction)))
    sets = []
    for _ in range(set_count):
        elements = []
        for element in range(universe_size):
            probability = (
                core_probability if element < core_size else peripheral_probability
            )
            if rng.random() < probability:
                elements.append(element)
        sets.append(_ensure_nonempty(_mask(elements), universe_size, rng))
    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="high_overlap",
        seed=seed,
        parameters={
            "core_fraction": core_fraction,
            "core_probability": core_probability,
            "peripheral_probability": peripheral_probability,
        },
    )


def clustered(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    clusters: int,
    within_probability: float,
    outside_probability: float,
    seed: int,
) -> MaximumCoverageInstance:
    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    clusters = _require_integer(
        "clusters", clusters, minimum=2, maximum=universe_size
    )
    within_probability = _require_probability(
        "within_probability", within_probability
    )
    outside_probability = _require_probability(
        "outside_probability", outside_probability
    )
    rng = random.Random(seed)
    sets = []
    for set_index in range(set_count):
        preferred = set_index % clusters
        elements = []
        for element in range(universe_size):
            element_cluster = min(clusters - 1, element * clusters // universe_size)
            probability = (
                within_probability
                if element_cluster == preferred
                else outside_probability
            )
            if rng.random() < probability:
                elements.append(element)
        sets.append(_ensure_nonempty(_mask(elements), universe_size, rng))
    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="clustered",
        seed=seed,
        parameters={
            "clusters": clusters,
            "within_probability": within_probability,
            "outside_probability": outside_probability,
        },
    )


def fixed_size(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    set_size: int,
    unique_sets: bool,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Generate uniformly sampled sets with an exact cardinality."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    unique_sets = _require_boolean("unique_sets", unique_sets)
    if coupling_seed is not None:
        if unique_sets:
            raise ValueError(
                "unique_sets must be false for a paired uniform control"
            )
        resolved_coupling_seed = _require_integer(
            "coupling_seed", coupling_seed
        )
        sets = tuple(
            _mask(
                sorted(
                    range(universe_size),
                    key=lambda element: (draws[element], element),
                )[:set_size]
            )
            for draws in _paired_cardinality_draws(
                universe_size, set_count, resolved_coupling_seed
            )
        )
        parameters: dict[str, object] = {
            "set_size": set_size,
            "unique_sets": unique_sets,
            "coupling_seed": resolved_coupling_seed,
        }
    elif unique_sets:
        rng = random.Random(seed)
        capacity = math.comb(universe_size, set_size)
        if set_count > capacity:
            raise ValueError(
                "set_count must not exceed the number of distinct fixed-size sets"
            )
        ranks = _sample_unique_ranks(rng, capacity, set_count)
        sets = tuple(
            _mask(
                _unrank_combination_lexicographic(
                    universe_size, set_size, rank
                )
            )
            for rank in ranks
        )
        parameters = {
            "set_size": set_size,
            "unique_sets": unique_sets,
        }
    else:
        rng = random.Random(seed)
        population = range(universe_size)
        sets = tuple(
            _mask(rng.sample(population, set_size)) for _ in range(set_count)
        )
        parameters = {
            "set_size": set_size,
            "unique_sets": unique_sets,
        }

    return MaximumCoverageInstance(
        universe_size,
        sets,
        k,
        family="fixed_size",
        seed=seed,
        parameters=parameters,
    )


def long_tail(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    set_size: int,
    gamma: float,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Generate fixed-size sets from continuous rank-based long-tail weights."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    gamma = _require_nonnegative_number("gamma", gamma)
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)

    rng = random.Random(resolved_coupling_seed)

    rank_order = list(range(universe_size))
    rng.shuffle(rank_order)
    rank_by_element = [0] * universe_size
    for rank, element in enumerate(rank_order):
        rank_by_element[element] = rank

    # Dividing every key by gamma preserves ordering and avoids overflow for
    # extreme but finite gamma values.  Ordinary research levels retain the
    # literal frozen formula below.
    maximum_log_rank = math.log(universe_size) if universe_size > 1 else 0.0
    normalize_key = (
        gamma > 0
        and maximum_log_rank > 0
        and gamma > sys.float_info.max / maximum_log_rank
    )
    sets: list[int] = []
    denominator = 1 << 53
    for _ in range(set_count):
        keys: list[tuple[float, int]] = []
        for element in range(universe_size):
            draw = rng.getrandbits(53)
            uniform = (draw + 0.5) / denominator
            if uniform >= 1.0:
                uniform = math.nextafter(1.0, 0.0)
            noise = math.log(-math.log(uniform))
            rank_log = math.log(rank_by_element[element] + 1)
            key = (
                rank_log + noise / gamma
                if normalize_key
                else noise + gamma * rank_log
            )
            keys.append((key, element))
        selected = (element for _, element in sorted(keys)[:set_size])
        sets.append(_mask(selected))

    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="long_tail",
        seed=seed,
        parameters={
            "set_size": set_size,
            "gamma": gamma,
            "coupling_seed": resolved_coupling_seed,
        },
    )


def duplicate_heavy(
    *,
    universe_size: int,
    base_set_count: int,
    k: int,
    set_size: int,
    copy_factor: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Replicate each unique fixed-size base set consecutively."""

    universe_size = _require_integer(
        "universe_size", universe_size, minimum=1
    )
    base_set_count = _require_integer(
        "base_set_count", base_set_count, minimum=1
    )
    k = _require_integer("k", k, minimum=1, maximum=base_set_count)
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    copy_factor = _require_integer("copy_factor", copy_factor, minimum=1)
    seed = _require_integer("seed", seed)
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)

    base_capacity = math.comb(universe_size, set_size)
    if base_set_count > base_capacity:
        raise ValueError(
            "base_set_count must not exceed the number of distinct "
            "fixed-size sets"
        )

    base = fixed_size(
        universe_size=universe_size,
        set_count=base_set_count,
        k=k,
        set_size=set_size,
        unique_sets=True,
        seed=resolved_coupling_seed,
    )
    sets = tuple(
        mask
        for mask in base.sets
        for _ in range(copy_factor)
    )
    return MaximumCoverageInstance(
        universe_size,
        sets,
        k,
        family="duplicate_heavy",
        seed=seed,
        parameters={
            "base_set_count": base_set_count,
            "set_size": set_size,
            "copy_factor": copy_factor,
            "coupling_seed": resolved_coupling_seed,
        },
    )


def _proper_subset_elements(anchor_size: int, rank: int) -> tuple[int, ...]:
    """Unrank the proper subsets ordered by cardinality then lexicographically."""

    remaining_rank = rank
    for cardinality in range(1, anchor_size):
        level_size = math.comb(anchor_size, cardinality)
        if remaining_rank < level_size:
            return _unrank_combination_lexicographic(
                anchor_size, cardinality, remaining_rank
            )
        remaining_rank -= level_size
    raise ValueError("proper-subset rank is outside the available range")


def dominated_heavy(
    *,
    anchor_count: int,
    anchor_size: int,
    k: int,
    child_count: int,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Create disjoint anchors followed by unique strict subsets of each anchor."""

    anchor_count = _require_integer("anchor_count", anchor_count, minimum=1)
    anchor_size = _require_integer("anchor_size", anchor_size, minimum=1)
    k = _require_integer("k", k, minimum=1, maximum=anchor_count)
    child_count = _require_integer("child_count", child_count, minimum=0)
    seed = _require_integer("seed", seed)
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)
    child_capacity = (1 << anchor_size) - 2
    if child_count > child_capacity:
        raise ValueError(
            "child_count must not exceed the number of unique non-empty "
            "proper subsets per anchor"
        )

    anchors = tuple(
        _mask(
            range(
                anchor_index * anchor_size,
                (anchor_index + 1) * anchor_size,
            )
        )
        for anchor_index in range(anchor_count)
    )
    children: list[int] = []
    for anchor_index in range(anchor_count):
        child_rng = random.Random(
            _derived_seed(
                resolved_coupling_seed,
                "dominated_heavy:children",
                anchor_index,
            )
        )
        ranks = sorted(
            _sample_stable_rank_prefix(
                child_rng, child_capacity, child_count
            )
        )
        offset = anchor_index * anchor_size
        for rank in ranks:
            local_elements = _proper_subset_elements(anchor_size, rank)
            children.append(_mask(offset + element for element in local_elements))

    return MaximumCoverageInstance(
        anchor_count * anchor_size,
        (*anchors, *children),
        k,
        family="dominated_heavy",
        seed=seed,
        parameters={
            "anchor_count": anchor_count,
            "anchor_size": anchor_size,
            "child_count": child_count,
            "coupling_seed": resolved_coupling_seed,
        },
    )


def mixed_cluster(
    *,
    universe_size: int,
    set_count: int,
    k: int,
    clusters: int,
    set_size: int,
    bridge_fraction: float,
    seed: int,
    coupling_seed: int | None = None,
) -> MaximumCoverageInstance:
    """Mix fixed-size cluster specialists with adjacent-cluster bridges."""

    universe_size, set_count, k, seed = _validate_standard_dimensions(
        universe_size, set_count, k, seed
    )
    clusters = _require_integer(
        "clusters", clusters, minimum=2, maximum=universe_size
    )
    set_size = _require_integer(
        "set_size", set_size, minimum=1, maximum=universe_size
    )
    bridge_fraction = _require_probability("bridge_fraction", bridge_fraction)
    resolved_coupling_seed = _resolve_coupling_seed(seed, coupling_seed)

    elements = list(range(universe_size))
    cluster_rng = random.Random(
        _derived_seed(resolved_coupling_seed, "mixed_cluster:partition")
    )
    cluster_rng.shuffle(elements)
    cluster_elements: list[list[int]] = [[] for _ in range(clusters)]
    for position, element in enumerate(elements):
        cluster_elements[position % clusters].append(element)

    lower_bridge_size = set_size // 2
    upper_bridge_size = set_size - lower_bridge_size
    bridge_count = math.floor(set_count * bridge_fraction + 0.5)
    if bridge_count > 0 and set_size < 2:
        raise ValueError("set_size must be at least 2 when bridges are generated")
    bridge_keys = tuple(
        (
            _derived_seed(
                resolved_coupling_seed,
                "mixed_cluster:bridge-rank",
                index,
            ),
            index,
        )
        for index in range(set_count)
    )
    bridge_indices = {
        index for _, index in sorted(bridge_keys)[:bridge_count]
    }

    requires_specialists = bridge_count < set_count
    requires_bridges = bridge_count > 0
    for index in range(set_count):
        preferred = index % clusters
        adjacent = (preferred + 1) % clusters
        if requires_specialists and len(cluster_elements[preferred]) < set_size:
            raise ValueError(
                "set_size must fit every potential specialist preferred cluster"
            )
        if requires_bridges:
            enough_capacity = (
                len(cluster_elements[preferred]) >= lower_bridge_size
                and len(cluster_elements[adjacent]) >= upper_bridge_size
            )
            if not enough_capacity:
                raise ValueError(
                    "set_size must fit both cluster sides for every potential bridge"
                )

    sets: list[int] = []
    for index in range(set_count):
        preferred = index % clusters
        adjacent = (preferred + 1) % clusters
        candidate_rng = random.Random(
            _derived_seed(
                resolved_coupling_seed,
                "mixed_cluster:candidate",
                index,
            )
        )
        preferred_ranking = candidate_rng.sample(
            cluster_elements[preferred], len(cluster_elements[preferred])
        )
        adjacent_ranking = candidate_rng.sample(
            cluster_elements[adjacent], len(cluster_elements[adjacent])
        )
        if index in bridge_indices:
            selected = (
                *preferred_ranking[:lower_bridge_size],
                *adjacent_ranking[:upper_bridge_size],
            )
        else:
            selected = tuple(preferred_ranking[:set_size])
        sets.append(_mask(selected))

    return MaximumCoverageInstance(
        universe_size,
        tuple(sets),
        k,
        family="mixed_cluster",
        seed=seed,
        parameters={
            "clusters": clusters,
            "set_size": set_size,
            "bridge_fraction": bridge_fraction,
            "bridge_count": bridge_count,
            "realized_bridge_fraction": bridge_count / set_count,
            "coupling_seed": resolved_coupling_seed,
        },
    )


_INTEGER = ParameterSpec((int,), "integer")
_NUMBER = ParameterSpec((int, float), "number")


GENERATORS: dict[str, GeneratorSpec] = {
    "uniform": GeneratorSpec(
        name="uniform",
        factory=uniform_random,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "density": _NUMBER,
            "paired_set_size": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            ),
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "high_overlap": GeneratorSpec(
        name="high_overlap",
        factory=high_overlap,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "core_fraction": _NUMBER,
            "core_probability": _NUMBER,
            "peripheral_probability": _NUMBER,
        },
    ),
    "clustered": GeneratorSpec(
        name="clustered",
        factory=clustered,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "clusters": _INTEGER,
            "within_probability": _NUMBER,
            "outside_probability": _NUMBER,
        },
    ),
    "fixed_size": GeneratorSpec(
        name="fixed_size",
        factory=fixed_size,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "set_size": _INTEGER,
            "unique_sets": ParameterSpec((bool,), "boolean"),
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "long_tail": GeneratorSpec(
        name="long_tail",
        factory=long_tail,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "set_size": _INTEGER,
            "gamma": _NUMBER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "duplicate_heavy": GeneratorSpec(
        name="duplicate_heavy",
        factory=duplicate_heavy,
        parameters={
            "universe_size": _INTEGER,
            "base_set_count": _INTEGER,
            "k": _INTEGER,
            "set_size": _INTEGER,
            "copy_factor": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "dominated_heavy": GeneratorSpec(
        name="dominated_heavy",
        factory=dominated_heavy,
        parameters={
            "anchor_count": _INTEGER,
            "anchor_size": _INTEGER,
            "k": _INTEGER,
            "child_count": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "mixed_cluster": GeneratorSpec(
        name="mixed_cluster",
        factory=mixed_cluster,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "clusters": _INTEGER,
            "set_size": _INTEGER,
            "bridge_fraction": _NUMBER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "controlled_high_overlap": GeneratorSpec(
        name="controlled_high_overlap",
        factory=controlled_high_overlap,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "set_size": _INTEGER,
            "shared_core_size": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "controlled_clustered": GeneratorSpec(
        name="controlled_clustered",
        factory=controlled_clustered,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "clusters": _INTEGER,
            "set_size": _INTEGER,
            "within_core_size": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "controlled_duplicate": GeneratorSpec(
        name="controlled_duplicate",
        factory=controlled_duplicate,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "set_size": _INTEGER,
            "copy_factor": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "controlled_dominated": GeneratorSpec(
        name="controlled_dominated",
        factory=controlled_dominated,
        parameters={
            "universe_size": _INTEGER,
            "set_count": _INTEGER,
            "k": _INTEGER,
            "anchor_size": _INTEGER,
            "child_size": _INTEGER,
            "dominated_pair_count": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "controlled_adversarial": GeneratorSpec(
        name="controlled_adversarial",
        factory=controlled_adversarial_greedy_trap,
        parameters={
            "block_size": _INTEGER,
            "distractor_count": _INTEGER,
            "trap_count": _INTEGER,
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
    "adversarial": GeneratorSpec(
        name="adversarial",
        factory=adversarial_greedy_trap,
        parameters={
            "block_size": _INTEGER,
            "distractor_count": ParameterSpec(
                (int,), "integer", default=4
            ),
            "construction_version": ParameterSpec(
                (int,), "integer", default=1
            ),
            "trap_count": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            ),
        },
        derived_parameters={
            "coupling_seed": ParameterSpec(
                (int, type(None)), "integer or null", default=None
            )
        },
    ),
}


def from_spec(
    spec: Mapping[str, object], seed: int
) -> MaximumCoverageInstance:
    if not isinstance(spec, Mapping):
        raise ValueError("generator specification must be a mapping")
    if "family" not in spec:
        raise ValueError("generator specification is missing required field 'family'")
    family = spec["family"]
    if not isinstance(family, str):
        raise ValueError("generator specification field 'family' must be a string")
    if family not in GENERATORS:
        raise ValueError(f"unknown instance family: {family!r}")
    parameters = {key: value for key, value in spec.items() if key != "family"}
    return cast(
        MaximumCoverageInstance,
        GENERATORS[family].generate(parameters, seed),
    )
