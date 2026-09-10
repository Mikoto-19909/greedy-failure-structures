"""Reference normalization, availability and coverage statistics.

This leaf module has no dependency on benchmark orchestration or artifact I/O.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from statistics import fmean

from .algorithms import ALGORITHMS
from .config import ExperimentConfig
from .contracts import (
    REFERENCE_STATUSES,
    InstanceRecord,
    ReferenceCensoringBiasRecord,
    ReferenceCoverageRecord,
    ReferenceCutoffSensitivityRecord,
    ReferenceStatusRecord,
    RunRecord,
)
from .model import SolutionStatus
from .reproducibility import canonical_json


def _validate_certificate_bound(
    certificate_value: int | None,
    best_bound: int | None,
    instance_identifier: str,
) -> None:
    if (
        certificate_value is not None
        and best_bound is not None
        and best_bound < certificate_value
    ):
        raise ValueError(
            f"algorithm best bound conflicts with certificate for {instance_identifier}"
        )


def _normalize_optima(
    rows: Sequence[RunRecord], instances: Sequence[InstanceRecord] = ()
) -> list[RunRecord]:
    certified = {
        record.instance_id: record.known_optimum
        for record in instances
        if record.known_optimum is not None
    }
    optimal_values: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row.status is SolutionStatus.OPTIMAL and row.coverage is not None:
            optimal_values[row.instance_id].add(row.coverage)
    for identifier, values in optimal_values.items():
        if len(values) > 1:
            raise ValueError(
                f"optimal algorithms disagree for instance {identifier}"
            )
        certificate_value = certified.get(identifier)
        if certificate_value is not None and values != {certificate_value}:
            raise ValueError(
                f"optimal algorithm result conflicts with certificate for {identifier}"
            )
    for row in rows:
        _validate_certificate_bound(
            certified.get(row.instance_id), row.best_bound, row.instance_id
        )
    optimum_by_instance = {
        identifier: next(iter(values)) for identifier, values in optimal_values.items()
    }
    optimum_by_instance.update(certified)
    normalized = []
    for row in rows:
        optimum = optimum_by_instance.get(row.instance_id)
        if (
            optimum is not None
            and row.coverage is not None
            and row.coverage > optimum
        ):
            raise ValueError(
                f"coverage exceeds normalized optimum for instance {row.instance_id}"
            )
        gap = None
        if optimum is not None and optimum > 0 and row.coverage is not None:
            gap = (optimum - row.coverage) / optimum
        normalized.append(replace(row, optimum=optimum, optimality_gap=gap))
    return normalized


def _reference_status_records(
    config: ExperimentConfig,
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord],
) -> list[ReferenceStatusRecord]:
    """Expose every generated instance's reference availability and solver statuses."""

    exact_algorithms = [
        algorithm
        for algorithm in config.algorithms
        if algorithm.enabled and ALGORITHMS[algorithm.name].exact
    ]
    rows_by_source = {
        (row.instance_id, row.algorithm_id): row
        for row in rows
        if ALGORITHMS[row.algorithm].exact
    }
    records: list[ReferenceStatusRecord] = []
    for instance in sorted(
        instances, key=lambda row: (row.config_hash, row.case_id, row.repetition)
    ):
        statuses: dict[str, str] = {}
        optimal_source_ids: list[str] = []
        optimal_source_names: set[str] = set()
        optimum: int | None = instance.known_optimum
        for algorithm in exact_algorithms:
            specification = ALGORITHMS[algorithm.name]
            eligible = (
                algorithm.options.max_set_count is None
                or instance.set_count <= algorithm.options.max_set_count
            )
            row = rows_by_source.get((instance.instance_id, algorithm.algorithm_id))
            if not eligible:
                if row is not None:
                    raise ValueError(
                        "ineligible exact solver unexpectedly produced a run for "
                        f"{instance.instance_id}"
                    )
                statuses[algorithm.algorithm_id] = "not_run"
                continue
            if row is None:
                raise ValueError(
                    "eligible exact solver is missing a completed run for "
                    f"{instance.instance_id}"
                )
            statuses[algorithm.algorithm_id] = row.status.value
            if row.status is SolutionStatus.OPTIMAL:
                optimal_source_ids.append(algorithm.algorithm_id)
                optimal_source_names.add(algorithm.name)
                if optimum is None:
                    optimum = row.coverage

        has_certificate = instance.known_optimum is not None
        reference_source_ids = tuple(
            (["known_optimum_certificate"] if has_certificate else [])
            + optimal_source_ids
        )
        if has_certificate:
            reference_status = "known_optimum_certificate"
        elif optimal_source_ids:
            reference_status = "optimal"
        elif "feasible" in statuses.values():
            reference_status = "feasible"
        elif "timeout" in statuses.values():
            reference_status = "timeout"
        elif "error" in statuses.values():
            reference_status = "error"
        else:
            reference_status = "not_run"
        proof_source_count = len(reference_source_ids)
        cross_validation_status = (
            "not_available"
            if proof_source_count == 0
            else "single_source"
            if proof_source_count == 1
            else "agreement"
        )
        small_cross_validated = (
            "brute_force" in optimal_source_names
            and bool(
                optimal_source_names
                & {
                    "branch_and_bound",
                    "branch_and_bound_enhanced",
                    "cp_sat_oracle",
                }
            )
        )
        records.append(
            ReferenceStatusRecord(
                config_hash=instance.config_hash,
                case_id=instance.case_id,
                instance_id=instance.instance_id,
                repetition=instance.repetition,
                family=instance.family,
                parameters=instance.parameters,
                reference_status=reference_status,
                exact_solver_statuses=canonical_json(statuses),
                reference_source_ids=reference_source_ids,
                proof_source_count=proof_source_count,
                has_known_optimum_certificate=has_certificate,
                provably_optimal=proof_source_count > 0,
                optimum=optimum,
                cross_validation_status=cross_validation_status,
                small_instance_cross_validated=small_cross_validated,
            )
        )
    return records


def _reference_coverage_statistics(
    statuses: Sequence[ReferenceStatusRecord],
) -> list[ReferenceCoverageRecord]:
    groups: dict[tuple[str, str, str], list[ReferenceStatusRecord]] = defaultdict(list)
    for record in statuses:
        groups[(record.config_hash, record.family, record.parameters)].append(record)
    statistics: list[ReferenceCoverageRecord] = []
    for (config_identifier, family, parameters), group in sorted(groups.items()):
        generated_count = len(group)
        provably_optimal_count = sum(record.provably_optimal for record in group)
        certificate_count = sum(record.has_known_optimum_certificate for record in group)
        solver_reference_count = sum(
            "optimal" in json.loads(record.exact_solver_statuses).values()
            for record in group
        )
        cross_validated_count = sum(
            record.cross_validation_status == "agreement" for record in group
        )
        case_ids = tuple(sorted({record.case_id for record in group}))
        for status in REFERENCE_STATUSES:
            status_count = sum(record.reference_status == status for record in group)
            statistics.append(
                ReferenceCoverageRecord(
                    config_hash=config_identifier,
                    family=family,
                    parameters=parameters,
                    case_count=len(case_ids),
                    case_ids=case_ids,
                    status=status,
                    generated_instance_count=generated_count,
                    status_instance_count=status_count,
                    status_rate=status_count / generated_count,
                    provably_optimal_instance_count=provably_optimal_count,
                    reference_coverage=provably_optimal_count / generated_count,
                    certificate_reference_count=certificate_count,
                    solver_reference_count=solver_reference_count,
                    cross_validated_instance_count=cross_validated_count,
                )
            )
    return statistics


_REFERENCE_BIAS_METRICS = (
    "universe_size",
    "set_count",
    "k",
    "actual_density",
    "mean_set_size",
    "pairwise_overlap_mean_jaccard",
    "coverage_skew_gini",
    "duplicate_set_ratio",
    "dominated_set_ratio",
    "adversarial_severity",
    "realized_trap_fraction",
)


def _reference_censoring_bias_statistics(
    statuses: Sequence[ReferenceStatusRecord],
    instances: Sequence[InstanceRecord],
) -> list[ReferenceCensoringBiasRecord]:
    status_by_instance = {record.instance_id: record for record in statuses}
    groups: dict[tuple[str, str, str], list[InstanceRecord]] = defaultdict(list)
    for instance in instances:
        groups[(instance.config_hash, instance.family, instance.parameters)].append(
            instance
        )
    statistics: list[ReferenceCensoringBiasRecord] = []
    for (config_identifier, family, parameters), group in sorted(groups.items()):
        retained = [
            instance
            for instance in group
            if status_by_instance[instance.instance_id].provably_optimal
        ]
        excluded = [
            instance
            for instance in group
            if not status_by_instance[instance.instance_id].provably_optimal
        ]
        case_ids = tuple(sorted({instance.case_id for instance in group}))
        for metric in _REFERENCE_BIAS_METRICS:
            retained_values = [
                float(value)
                for instance in retained
                if (value := getattr(instance, metric)) is not None
            ]
            excluded_values = [
                float(value)
                for instance in excluded
                if (value := getattr(instance, metric)) is not None
            ]
            retained_mean = fmean(retained_values) if retained_values else None
            excluded_mean = fmean(excluded_values) if excluded_values else None
            difference = (
                None
                if retained_mean is None or excluded_mean is None
                else excluded_mean - retained_mean
            )
            statistics.append(
                ReferenceCensoringBiasRecord(
                    config_hash=config_identifier,
                    family=family,
                    parameters=parameters,
                    case_count=len(case_ids),
                    case_ids=case_ids,
                    metric=metric,
                    retained_instance_count=len(retained),
                    excluded_instance_count=len(excluded),
                    retained_observation_count=len(retained_values),
                    excluded_observation_count=len(excluded_values),
                    retained_mean=retained_mean,
                    excluded_mean=excluded_mean,
                    excluded_minus_retained=difference,
                    comparison_status=(
                        "estimable"
                        if retained_values and excluded_values
                        else "missing_group"
                    ),
                )
            )
    return statistics


def _reference_cutoff_sensitivity_statistics(
    config: ExperimentConfig,
    statuses: Sequence[ReferenceStatusRecord],
) -> list[ReferenceCutoffSensitivityRecord]:
    exact_algorithms = [
        algorithm
        for algorithm in config.algorithms
        if algorithm.enabled and ALGORITHMS[algorithm.name].exact
    ]
    groups: dict[tuple[str, str, str], list[ReferenceStatusRecord]] = defaultdict(list)
    for record in statuses:
        groups[(record.config_hash, record.family, record.parameters)].append(record)
    statistics: list[ReferenceCutoffSensitivityRecord] = []
    for (config_identifier, family, parameters), group in sorted(groups.items()):
        case_ids = tuple(sorted({record.case_id for record in group}))
        for algorithm in exact_algorithms:
            solver_statuses = [
                json.loads(record.exact_solver_statuses)[algorithm.algorithm_id]
                for record in group
            ]
            status_counts = {
                status: solver_statuses.count(status)
                for status in REFERENCE_STATUSES[1:]
            }
            certificate_count = sum(
                record.has_known_optimum_certificate for record in group
            )
            effective_count = sum(
                record.has_known_optimum_certificate or solver_status == "optimal"
                for record, solver_status in zip(group, solver_statuses)
            )
            generated_count = len(group)
            statistics.append(
                ReferenceCutoffSensitivityRecord(
                    config_hash=config_identifier,
                    family=family,
                    parameters=parameters,
                    case_count=len(case_ids),
                    case_ids=case_ids,
                    algorithm_id=algorithm.algorithm_id,
                    algorithm=algorithm.name,
                    time_limit_seconds=algorithm.options.time_limit_seconds,
                    max_set_count=algorithm.options.max_set_count,
                    generated_instance_count=generated_count,
                    eligible_instance_count=(
                        generated_count - status_counts["not_run"]
                    ),
                    optimal_count=status_counts["optimal"],
                    feasible_count=status_counts["feasible"],
                    timeout_count=status_counts["timeout"],
                    error_count=status_counts["error"],
                    not_run_count=status_counts["not_run"],
                    certificate_count=certificate_count,
                    solver_reference_coverage=(
                        status_counts["optimal"] / generated_count
                    ),
                    effective_reference_coverage=effective_count / generated_count,
                )
            )
    return statistics
