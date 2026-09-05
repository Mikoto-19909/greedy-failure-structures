"""Controlled synthetic Maximum Coverage instance families."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

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
from ._generators_random import (
    uniform_random,
    high_overlap,
    clustered,
    fixed_size,
    long_tail,
    duplicate_heavy,
    dominated_heavy,
    mixed_cluster,
)
from .contracts import GeneratorSpec, ParameterSpec
from .model import MaximumCoverageInstance


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
