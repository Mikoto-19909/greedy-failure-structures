"""Types shared by benchmark planning and execution."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

from .algorithms import ALGORITHMS
from .certificates import known_optimum_certificate
from .config import CaseConfig, ExperimentConfig
from .contracts import (
    AlgorithmRunOptions,
    InstanceRecord,
    P4_3_COUPLED_FAMILIES,
    P4_3_INSTANCE_ORIGINS,
    P4_3_RESEARCH_QUESTION_IDS,
)
from .generators import GENERATORS
from .model import MaximumCoverageInstance
from .reproducibility import canonical_json, instance_id, run_id
from .structure import analyze_instance


@dataclass(frozen=True, slots=True)
class _PlannedInstance:
    case_id: str
    repetition: int
    instance: MaximumCoverageInstance
    instance_id: str
    coupling_pair_id: str | None = None
    coupling_seed: int | None = None


@dataclass(frozen=True, slots=True)
class _RunTask:
    case_id: str
    repetition: int
    instance: MaximumCoverageInstance
    algorithm_id: str
    algorithm_seed: int | None
    algorithm: str
    options: AlgorithmRunOptions
    option_values: dict[str, object]
    config_hash: str
    instance_id: str
    run_id: str


def _coupling_pair_id(
    *, block_size: int, distractor_count: int, repetition: int
) -> str:
    return (
        "adversarial"
        f"|block_size={block_size}"
        f"|distractor_count={distractor_count}"
        f"|repetition={repetition}"
    )


def _coupling_seed(base_seed: int, pair_id: str) -> int:
    payload = canonical_json({"base_seed": base_seed, "coupling_pair_id": pair_id})
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _case_seed(
    config: ExperimentConfig,
    case: CaseConfig,
    case_index: int,
    repetition: int,
) -> int:
    """Return a stable instance seed, shared only by an explicit seed group."""

    if case.seed_group is None:
        return config.base_seed + case_index * 10_000 + repetition
    payload = canonical_json(
        {"base_seed": config.base_seed, "seed_group": case.seed_group}
    )
    group_offset = int.from_bytes(
        hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big"
    )
    return group_offset + repetition


_STRUCTURAL_COUPLING_INTENSITY = {
    "long_tail": "gamma",
    "duplicate_heavy": "copy_factor",
    "dominated_heavy": "child_count",
    "mixed_cluster": "bridge_fraction",
    "controlled_high_overlap": "shared_core_size",
    "controlled_clustered": "within_core_size",
    "controlled_duplicate": "copy_factor",
    "controlled_dominated": "dominated_pair_count",
    "controlled_adversarial": "trap_count",
}


def _resolved_case_parameters(
    family: str, parameters: Mapping[str, object]
) -> dict[str, object]:
    specification = GENERATORS[family]
    return {
        name: parameters[name] if name in parameters else parameter.default
        for name, parameter in specification.parameters.items()
    }


def _structural_coupling_pair_id(
    *,
    family: str,
    scan_name: str,
    parameters: Mapping[str, object],
    repetition: int,
) -> str:
    """Identify one coupled scan after removing its structural intensity."""

    intensity = _STRUCTURAL_COUPLING_INTENSITY[family]
    fixed_parameters = {
        name: value for name, value in parameters.items() if name != intensity
    }
    return (
        f"{family}|scan={canonical_json(scan_name)}"
        f"|parameters={canonical_json(fixed_parameters)}"
        f"|repetition={repetition}"
    )


def _fixed_size_control_pairs(
    config: ExperimentConfig,
) -> dict[str, str]:
    """Map matched fixed-size/Bernoulli controls to one pairing identity."""

    fixed_cases: dict[tuple[int, int, int, int], list[CaseConfig]] = {}
    uniform_cases: dict[tuple[int, int, int, int], list[CaseConfig]] = {}
    for case in config.cases:
        parameters = case.parameters
        if case.family == "fixed_size" and parameters.get("unique_sets") is False:
            key = (
                int(cast(int, parameters["universe_size"])),
                int(cast(int, parameters["set_count"])),
                int(cast(int, parameters["k"])),
                int(cast(int, parameters["set_size"])),
            )
            fixed_cases.setdefault(key, []).append(case)
        elif (
            case.family == "uniform"
            and parameters.get("paired_set_size") is not None
        ):
            key = (
                int(cast(int, parameters["universe_size"])),
                int(cast(int, parameters["set_count"])),
                int(cast(int, parameters["k"])),
                int(cast(int, parameters["paired_set_size"])),
            )
            uniform_cases.setdefault(key, []).append(case)

    result: dict[str, str] = {}
    for key, controls in uniform_cases.items():
        treatments = fixed_cases.get(key, [])
        if len(treatments) != 1 or len(controls) != 1:
            raise ValueError(
                "paired fixed_size controls require exactly one matching "
                f"fixed_size and uniform case for dimensions {key!r}"
            )
        fixed_case = treatments[0]
        uniform_case = controls[0]
        pair = (
            "fixed_size_uniform"
            f"|fixed_case={canonical_json(fixed_case.case_id)}"
            f"|uniform_case={canonical_json(uniform_case.case_id)}"
            f"|dimensions={canonical_json(key)}"
        )
        result[fixed_case.case_id] = pair
        result[uniform_case.case_id] = pair
    return result


def _instances_for_config(config: ExperimentConfig) -> list[_PlannedInstance]:
    planned: list[_PlannedInstance] = []
    fixed_size_pairs = _fixed_size_control_pairs(config)
    for case_index, case in enumerate(config.cases):
        for repetition in range(config.repetitions):
            seed = _case_seed(config, case, case_index, repetition)
            pair_id = None
            coupled_seed = None
            fixed_size_pair = fixed_size_pairs.get(case.case_id)
            if fixed_size_pair is not None:
                pair_id = f"{fixed_size_pair}|repetition={repetition}"
                coupled_seed = _coupling_seed(config.base_seed, pair_id)
                instance = case.generate(
                    seed,
                    derived_parameters={"coupling_seed": coupled_seed},
                )
            elif case.seed_group is not None and (
                case.family in P4_3_COUPLED_FAMILIES
                or (
                    case.family == "adversarial"
                    and case.parameters.get("construction_version", 1) == 2
                )
            ):
                pair_id = (
                    f"seed_group={canonical_json(case.seed_group)}"
                    f"|repetition={repetition}"
                )
                coupled_seed = seed
                instance = case.generate(
                    seed,
                    derived_parameters={"coupling_seed": coupled_seed},
                )
            elif (
                case.family == "adversarial"
                and case.parameters.get("construction_version", 1) == 2
            ):
                block_size = int(cast(int, case.parameters["block_size"]))
                distractor_count = int(cast(int, case.parameters.get("distractor_count", 4)))
                pair_id = _coupling_pair_id(
                    block_size=block_size,
                    distractor_count=distractor_count,
                    repetition=repetition,
                )
                coupled_seed = _coupling_seed(config.base_seed, pair_id)
                instance = case.generate(
                    seed,
                    derived_parameters={"coupling_seed": coupled_seed},
                )
            elif case.family in _STRUCTURAL_COUPLING_INTENSITY:
                resolved_parameters = _resolved_case_parameters(
                    case.family, case.parameters
                )
                pair_id = _structural_coupling_pair_id(
                    family=case.family,
                    scan_name=case.name,
                    parameters=resolved_parameters,
                    repetition=repetition,
                )
                coupled_seed = _coupling_seed(config.base_seed, pair_id)
                instance = case.generate(
                    seed,
                    derived_parameters={"coupling_seed": coupled_seed},
                )
            else:
                instance = case.generate(seed)
            planned.append(
                _PlannedInstance(
                    case_id=case.case_id,
                    repetition=repetition,
                    instance=instance,
                    instance_id=instance_id(instance),
                    coupling_pair_id=pair_id,
                    coupling_seed=coupled_seed,
                )
            )
    return planned


def _instance_record(
    planned: _PlannedInstance, config_identifier: str
) -> InstanceRecord:
    instance = planned.instance
    metrics = analyze_instance(instance)
    controlled_family = instance.family.startswith("controlled_")
    adversarial_construction = instance.family in {
        "adversarial",
        "controlled_adversarial",
    }
    if instance.family in P4_3_INSTANCE_ORIGINS:
        origin = P4_3_INSTANCE_ORIGINS[instance.family]
    elif adversarial_construction or controlled_family:
        origin = "constructed"
    elif instance.family in {"uniform", "high_overlap", "clustered"}:
        origin = "stochastic"
    else:
        origin = "custom"
    version = instance.parameters.get("construction_version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise ValueError("construction_version must be a positive integer")
    certificate = known_optimum_certificate(instance)
    severity = None
    realized_trap_fraction = None
    is_adversarial = adversarial_construction
    research_question_id = P4_3_RESEARCH_QUESTION_IDS.get(instance.family)
    paired_uniform_control = (
        instance.family == "uniform"
        and instance.parameters.get("paired_set_size") is not None
    )
    if paired_uniform_control:
        research_question_id = P4_3_RESEARCH_QUESTION_IDS["fixed_size"]
    if instance.family == "controlled_adversarial":
        block_size = int(instance.parameters["block_size"])
        trap_count = int(instance.parameters["trap_count"])
        severity = (block_size - trap_count) / (2 * block_size)
        realized_trap_fraction = trap_count / block_size
        is_adversarial = severity > 0
        research_question_id = "controlled_adversarial_severity"
        if instance.parameters.get("coupling_seed") != planned.coupling_seed:
            raise ValueError(
                "controlled adversarial coupling seed conflicts with the instance"
            )
    elif adversarial_construction and version == 2:
        block_size = int(instance.parameters["block_size"])
        trap_count = int(instance.parameters["trap_count"])
        severity = (block_size - trap_count) / (2 * block_size)
        realized_trap_fraction = trap_count / block_size
        is_adversarial = severity > 0
        research_question_id = "adversarial_severity"
        if instance.parameters.get("coupling_seed") != planned.coupling_seed:
            raise ValueError("version-2 coupling seed conflicts with the instance")
    elif instance.family in P4_3_RESEARCH_QUESTION_IDS:
        is_adversarial = False
        if instance.family in P4_3_COUPLED_FAMILIES:
            if instance.parameters.get("coupling_seed") != planned.coupling_seed:
                raise ValueError(
                    f"{instance.family} coupling seed conflicts with the instance"
                )
        elif instance.family == "fixed_size":
            parameter_seed = instance.parameters.get("coupling_seed")
            if parameter_seed is None:
                if (
                    planned.coupling_pair_id is not None
                    or planned.coupling_seed is not None
                ):
                    raise ValueError(
                        "unpaired fixed_size must not carry benchmark coupling fields"
                    )
            elif parameter_seed != planned.coupling_seed:
                raise ValueError(
                    "fixed_size coupling seed conflicts with the instance"
                )
    elif paired_uniform_control:
        is_adversarial = False
        if instance.parameters.get("coupling_seed") != planned.coupling_seed:
            raise ValueError(
                "uniform control coupling seed conflicts with the instance"
            )
    return InstanceRecord(
        config_hash=config_identifier,
        case_id=planned.case_id,
        repetition=planned.repetition,
        instance_id=planned.instance_id,
        seed=instance.seed,
        family=instance.family,
        generator_version=version,
        coupling_pair_id=planned.coupling_pair_id,
        coupling_seed=planned.coupling_seed,
        research_question_id=research_question_id,
        instance_origin=origin,
        is_adversarial=is_adversarial,
        universe_size=instance.universe_size,
        set_count=instance.set_count,
        k=instance.k,
        parameters=canonical_json(instance.parameters),
        incidence_count=metrics.incidence_count,
        covered_element_count=metrics.covered_element_count,
        unique_set_count=metrics.unique_set_count,
        actual_density=metrics.actual_density,
        mean_set_size=metrics.mean_set_size,
        pairwise_overlap_mean_jaccard=metrics.pairwise_overlap_mean_jaccard,
        pairwise_overlap_total_pairs=metrics.pairwise_overlap_total_pairs,
        pairwise_overlap_valid_pairs=metrics.pairwise_overlap_valid_pairs,
        coverage_skew_gini=metrics.coverage_skew_gini,
        duplicate_set_count=metrics.duplicate_set_count,
        duplicate_set_ratio=metrics.duplicate_set_ratio,
        dominated_set_count=metrics.dominated_set_count,
        dominated_set_ratio=metrics.dominated_set_ratio,
        dominated_unique_ratio=metrics.dominated_unique_ratio,
        preprocessed_set_count=metrics.preprocessed_set_count,
        adversarial_severity=severity,
        realized_trap_fraction=realized_trap_fraction,
        known_optimum=None if certificate is None else certificate.value,
        optimum_source=None if certificate is None else certificate.source,
        optimum_selected=None if certificate is None else certificate.selected,
        proof_kind=None if certificate is None else certificate.proof_kind,
    )


def _tasks_for_config(
    config: ExperimentConfig,
    identifier: str,
    instances: Sequence[_PlannedInstance] | None = None,
) -> list[_RunTask]:
    tasks: list[_RunTask] = []
    planned_instances = _instances_for_config(config) if instances is None else instances
    algorithms = tuple(config.algorithms)
    for planned in planned_instances:
        instance = planned.instance
        iid = planned.instance_id
        for algorithm in algorithms:
            if not algorithm.enabled:
                continue
            specification = ALGORITHMS[algorithm.name]
            if not specification.is_eligible(instance, algorithm.options):
                continue
            seeds: tuple[int | None, ...] = (
                algorithm.algorithm_seeds
                if specification.uses_random_seed
                else (None,)
            )
            for algorithm_seed in seeds:
                resolved_options = replace(
                    algorithm.options, algorithm_seed=algorithm_seed
                )
                option_values = specification.option_values(resolved_options)
                tasks.append(
                    _RunTask(
                        case_id=planned.case_id,
                        repetition=planned.repetition,
                        instance=instance,
                        algorithm_id=algorithm.algorithm_id,
                        algorithm_seed=algorithm_seed,
                        algorithm=algorithm.name,
                        options=resolved_options,
                        option_values=option_values,
                        config_hash=identifier,
                        instance_id=iid,
                        run_id=run_id(
                            iid,
                            algorithm.name,
                            option_values,
                            algorithm_version=specification.version,
                            algorithm_seed=algorithm_seed,
                        ),
                    )
                )
    return tasks
