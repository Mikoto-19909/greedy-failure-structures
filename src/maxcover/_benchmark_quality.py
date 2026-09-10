"""Greedy failure and deterministic Local Search quality analyses."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

from .algorithms import ALGORITHMS
from .contracts import (
    GreedyFailureRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    RunRecord,
)
from .model import SolutionStatus


def _greedy_failure_statistics(
    rows: Sequence[RunRecord],
) -> list[GreedyFailureRecord]:
    """Compute conditional classical-Greedy failures on completed instance units."""

    # The P5.2 metric is defined only for the registry's deterministic classical
    # Greedy. A test or extension may replace that implementation with a seeded
    # algorithm under the same name; that is a stochastic-analysis subject.
    if ALGORITHMS["greedy"].uses_random_seed:
        return []

    groups: dict[
        tuple[str, str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        if row.algorithm != "greedy":
            continue
        groups[
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    records: list[GreedyFailureRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, case_id, family, algorithm_id, algorithm = key
        units: dict[tuple[str, str, int, str], list[RunRecord]] = defaultdict(list)
        for row in group:
            if row.algorithm_seed is not None:
                raise ValueError(
                    "classical greedy failure statistics forbid algorithm seeds"
                )
            units[
                (row.config_hash, row.case_id, row.repetition, row.instance_id)
            ].append(row)

        duplicate_units = [
            unit for unit, unit_rows in units.items() if len(unit_rows) != 1
        ]
        if duplicate_units:
            raise ValueError(
                "classical greedy failure statistics require exactly one run "
                "per instance unit"
            )

        completed_count = 0
        timeout_count = 0
        error_count = 0
        valid_exact_reference_count = 0
        eligible_pair_count = 0
        failure_count = 0
        optimal_tie_count = 0
        for unit_rows in units.values():
            row = unit_rows[0]
            if row.status is SolutionStatus.FEASIBLE:
                completed_count += 1
            elif row.status is SolutionStatus.TIMEOUT:
                timeout_count += 1
            elif row.status is SolutionStatus.ERROR:
                error_count += 1
            else:
                raise ValueError(
                    "classical greedy records must be feasible, timeout, or error"
                )

            if row.optimum is None:
                continue
            valid_exact_reference_count += 1
            if row.coverage is not None and row.coverage > row.optimum:
                raise ValueError(
                    "classical greedy coverage exceeds its normalized exact optimum"
                )
            if row.status is not SolutionStatus.FEASIBLE:
                continue
            if row.coverage is None:
                raise ValueError(
                    "completed classical greedy records require feasible coverage"
                )
            eligible_pair_count += 1
            if row.coverage < row.optimum:
                failure_count += 1
            else:
                optimal_tie_count += 1

        instance_count = len(units)
        records.append(
            GreedyFailureRecord(
                config_hash=config_identifier,
                case_id=case_id,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                repetition_unit="instance_seed",
                instance_count=instance_count,
                run_count=len(group),
                completed_count=completed_count,
                timeout_count=timeout_count,
                timeout_rate=timeout_count / instance_count,
                error_count=error_count,
                error_rate=error_count / instance_count,
                valid_exact_reference_count=valid_exact_reference_count,
                exact_reference_rate=valid_exact_reference_count / instance_count,
                no_exact_reference_count=(
                    instance_count - valid_exact_reference_count
                ),
                eligible_pair_count=eligible_pair_count,
                eligible_pair_rate=eligible_pair_count / instance_count,
                failure_count=failure_count,
                optimal_tie_count=optimal_tie_count,
                failure_rate=(
                    None
                    if eligible_pair_count == 0
                    else failure_count / eligible_pair_count
                ),
                optimal_tie_rate=(
                    None
                    if eligible_pair_count == 0
                    else optimal_tie_count / eligible_pair_count
                ),
            )
        )
    return records


@dataclass(frozen=True, slots=True)
class _LocalSearchPairAnalysis:
    config_hash: str
    case_id: str
    family: str
    greedy_algorithm_id: str
    local_search_algorithm_id: str
    instance_count: int
    greedy_completed_count: int
    greedy_timeout_count: int
    greedy_error_count: int
    local_search_completed_count: int
    local_search_timeout_count: int
    local_search_error_count: int
    valid_exact_reference_count: int
    greedy_failure_count: int
    recoveries: tuple[float, ...]
    remaining_relative_gaps: tuple[float, ...]
    full_recovery_count: int


def _local_search_pair_analyses(
    rows: Sequence[RunRecord],
) -> list[_LocalSearchPairAnalysis]:
    """Build canonical deterministic Greedy/Local Search pair observations."""

    if (
        ALGORITHMS["greedy"].uses_random_seed
        or ALGORITHMS["local_search"].uses_random_seed
    ):
        return []

    greedy_groups: dict[
        tuple[str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    local_groups: dict[
        tuple[str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        key = (row.config_hash, row.case_id, row.family, row.algorithm_id)
        if row.algorithm == "greedy":
            greedy_groups[key].append(row)
        elif row.algorithm == "local_search":
            local_groups[key].append(row)

    analyses: list[_LocalSearchPairAnalysis] = []
    for greedy_key, greedy_group in sorted(greedy_groups.items()):
        config_identifier, case_id, family, greedy_algorithm_id = greedy_key
        matching_local_groups = [
            (key, group)
            for key, group in local_groups.items()
            if key[:3] == greedy_key[:3]
        ]
        for local_key, local_group in sorted(matching_local_groups):
            local_search_algorithm_id = local_key[3]
            greedy_units = _deterministic_variant_units(
                greedy_group, "classical Greedy"
            )
            local_units = _deterministic_variant_units(
                local_group, "Local Search"
            )
            if greedy_units.keys() != local_units.keys():
                raise ValueError(
                    "Local Search recovery requires identical instance units "
                    "for paired Greedy and Local Search variants"
                )

            greedy_completed_count = 0
            greedy_timeout_count = 0
            greedy_error_count = 0
            local_completed_count = 0
            local_timeout_count = 0
            local_error_count = 0
            valid_exact_reference_count = 0
            greedy_failure_count = 0
            recoveries: list[float] = []
            remaining_relative_gaps: list[float] = []
            full_recovery_count = 0

            for unit in sorted(greedy_units):
                greedy_row = greedy_units[unit]
                local_row = local_units[unit]
                greedy_completed_count, greedy_timeout_count, greedy_error_count = (
                    _increment_heuristic_status(
                        greedy_row,
                        "classical Greedy",
                        greedy_completed_count,
                        greedy_timeout_count,
                        greedy_error_count,
                    )
                )
                local_completed_count, local_timeout_count, local_error_count = (
                    _increment_heuristic_status(
                        local_row,
                        "Local Search",
                        local_completed_count,
                        local_timeout_count,
                        local_error_count,
                    )
                )
                if greedy_row.optimum != local_row.optimum:
                    raise ValueError(
                        "paired Greedy and Local Search rows have inconsistent "
                        "normalized exact references"
                    )
                optimum = greedy_row.optimum
                if optimum is None:
                    continue
                valid_exact_reference_count += 1
                for label, row in (
                    ("classical Greedy", greedy_row),
                    ("Local Search", local_row),
                ):
                    if row.coverage is not None and row.coverage > optimum:
                        raise ValueError(
                            f"{label} coverage exceeds its normalized exact optimum"
                        )
                if greedy_row.status is not SolutionStatus.FEASIBLE:
                    continue
                if greedy_row.coverage is None:
                    raise ValueError(
                        "completed classical Greedy records require feasible coverage"
                    )
                if greedy_row.coverage == optimum:
                    continue
                greedy_failure_count += 1
                if local_row.status is not SolutionStatus.FEASIBLE:
                    continue
                if local_row.coverage is None:
                    raise ValueError(
                        "completed Local Search records require feasible coverage"
                    )
                if local_row.coverage < greedy_row.coverage:
                    raise ValueError(
                        "Local Search coverage cannot be below its paired Greedy "
                        "coverage"
                    )
                recovery = (
                    (local_row.coverage - greedy_row.coverage)
                    / (optimum - greedy_row.coverage)
                )
                recoveries.append(recovery)
                remaining_relative_gaps.append(
                    (optimum - local_row.coverage) / optimum
                )
                if local_row.coverage == optimum:
                    full_recovery_count += 1

            instance_count = len(greedy_units)
            analyses.append(
                _LocalSearchPairAnalysis(
                    config_hash=config_identifier,
                    case_id=case_id,
                    family=family,
                    greedy_algorithm_id=greedy_algorithm_id,
                    local_search_algorithm_id=local_search_algorithm_id,
                    instance_count=instance_count,
                    greedy_completed_count=greedy_completed_count,
                    greedy_timeout_count=greedy_timeout_count,
                    greedy_error_count=greedy_error_count,
                    local_search_completed_count=local_completed_count,
                    local_search_timeout_count=local_timeout_count,
                    local_search_error_count=local_error_count,
                    valid_exact_reference_count=valid_exact_reference_count,
                    greedy_failure_count=greedy_failure_count,
                    recoveries=tuple(recoveries),
                    remaining_relative_gaps=tuple(remaining_relative_gaps),
                    full_recovery_count=full_recovery_count,
                )
            )
    return analyses


def _local_search_recovery_statistics(
    rows: Sequence[RunRecord],
) -> list[LocalSearchRecoveryRecord]:
    """Compute the Greedy gap recovered by deterministic Local Search."""

    records: list[LocalSearchRecoveryRecord] = []
    for analysis in _local_search_pair_analyses(rows):
        eligible_pair_count = len(analysis.recoveries)
        records.append(
            LocalSearchRecoveryRecord(
                config_hash=analysis.config_hash,
                case_id=analysis.case_id,
                family=analysis.family,
                greedy_algorithm_id=analysis.greedy_algorithm_id,
                local_search_algorithm_id=analysis.local_search_algorithm_id,
                algorithm="local_search",
                repetition_unit="instance_seed",
                instance_count=analysis.instance_count,
                greedy_completed_count=analysis.greedy_completed_count,
                greedy_timeout_count=analysis.greedy_timeout_count,
                greedy_error_count=analysis.greedy_error_count,
                local_search_completed_count=analysis.local_search_completed_count,
                local_search_timeout_count=analysis.local_search_timeout_count,
                local_search_error_count=analysis.local_search_error_count,
                valid_exact_reference_count=(
                    analysis.valid_exact_reference_count
                ),
                greedy_failure_count=analysis.greedy_failure_count,
                eligible_pair_count=eligible_pair_count,
                eligible_pair_rate=(
                    None
                    if analysis.greedy_failure_count == 0
                    else eligible_pair_count / analysis.greedy_failure_count
                ),
                mean_gap_recovery_rate=(
                    None
                    if not analysis.recoveries
                    else fmean(analysis.recoveries)
                ),
                full_recovery_count=analysis.full_recovery_count,
                full_recovery_rate=(
                    None
                    if not analysis.recoveries
                    else analysis.full_recovery_count / eligible_pair_count
                ),
            )
        )
    return records


def _local_search_remaining_gap_statistics(
    rows: Sequence[RunRecord],
) -> list[LocalSearchRemainingGapRecord]:
    """Compute Local Search's remaining relative optimum gap after Greedy fails."""

    records: list[LocalSearchRemainingGapRecord] = []
    for analysis in _local_search_pair_analyses(rows):
        gaps = analysis.remaining_relative_gaps
        eligible_pair_count = len(gaps)
        zero_gap_count = sum(gap == 0 for gap in gaps)
        records.append(
            LocalSearchRemainingGapRecord(
                config_hash=analysis.config_hash,
                case_id=analysis.case_id,
                family=analysis.family,
                greedy_algorithm_id=analysis.greedy_algorithm_id,
                local_search_algorithm_id=analysis.local_search_algorithm_id,
                algorithm="local_search",
                repetition_unit="instance_seed",
                instance_count=analysis.instance_count,
                valid_exact_reference_count=(
                    analysis.valid_exact_reference_count
                ),
                greedy_failure_count=analysis.greedy_failure_count,
                eligible_pair_count=eligible_pair_count,
                mean_remaining_relative_gap=(
                    None if not gaps else fmean(gaps)
                ),
                maximum_remaining_relative_gap=(
                    None if not gaps else max(gaps)
                ),
                zero_remaining_gap_count=zero_gap_count,
                zero_remaining_gap_rate=(
                    None if not gaps else zero_gap_count / eligible_pair_count
                ),
            )
        )
    return records


def _deterministic_variant_units(
    rows: Sequence[RunRecord], label: str
) -> dict[tuple[str, str, int, str], RunRecord]:
    units: dict[tuple[str, str, int, str], RunRecord] = {}
    for row in rows:
        if row.algorithm_seed is not None:
            raise ValueError(f"{label} recovery statistics forbid algorithm seeds")
        unit = (row.config_hash, row.case_id, row.repetition, row.instance_id)
        if unit in units:
            raise ValueError(
                f"{label} recovery statistics require exactly one run per "
                "instance unit"
            )
        units[unit] = row
    return units


def _increment_heuristic_status(
    row: RunRecord,
    label: str,
    completed: int,
    timeout: int,
    error: int,
) -> tuple[int, int, int]:
    if row.status is SolutionStatus.FEASIBLE:
        return completed + 1, timeout, error
    if row.status is SolutionStatus.TIMEOUT:
        return completed, timeout + 1, error
    if row.status is SolutionStatus.ERROR:
        return completed, timeout, error + 1
    raise ValueError(f"{label} records must be feasible, timeout, or error")
