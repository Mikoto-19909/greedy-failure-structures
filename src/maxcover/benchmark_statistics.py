"""Canonical benchmark statistics and reference analyses."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from statistics import fmean, median, stdev
from typing import TypedDict

from .algorithms import ALGORITHMS
from .config import ExperimentConfig
from .contracts import (
    BranchAndBoundNodeReductionRecord,
    CensoredRuntimeRecord,
    ConfidenceIntervalRecord,
    DescriptiveStatisticsRecord,
    GreedyFailureRecord,
    HeuristicExactRuntimeRatioRecord,
    InstanceRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    QualityRuntimeParetoRecord,
    REFERENCE_STATUSES,
    ReferenceCensoringBiasRecord,
    ReferenceCoverageRecord,
    ReferenceCutoffSensitivityRecord,
    ReferenceStatusRecord,
    RunRecord,
    SummaryRecord,
)
from .model import SolutionStatus
from .reproducibility import canonical_json


# Preserve existing imports while reference processing lives in its own module.
from ._benchmark_reference import (
    _validate_certificate_bound,
    _normalize_optima,
    _reference_status_records,
    _reference_coverage_statistics,
    _REFERENCE_BIAS_METRICS,
    _reference_censoring_bias_statistics,
    _reference_cutoff_sensitivity_statistics,
)


# Preserve existing imports while quality analysis lives in its own module.
from ._benchmark_quality import (
    _greedy_failure_statistics,
    _LocalSearchPairAnalysis,
    _local_search_pair_analyses,
    _local_search_recovery_statistics,
    _local_search_remaining_gap_statistics,
    _deterministic_variant_units,
    _increment_heuristic_status,
)


def _summarize(rows: Sequence[RunRecord]) -> list[SummaryRecord]:
    groups: dict[tuple[str, str, str, str], list[RunRecord]] = defaultdict(list)
    for row in rows:
        groups[(row.case, row.family, row.algorithm_id, row.algorithm)].append(row)
    summary: list[SummaryRecord] = []
    for (case, family, algorithm_id, algorithm), group in sorted(groups.items()):
        gaps = [row.optimality_gap for row in group if row.optimality_gap is not None]
        runtimes = [row.runtime_seconds for row in group]
        coverages = [row.coverage for row in group if row.coverage is not None]
        summary.append(
            SummaryRecord(
                case=case,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                runs=len(group),
                mean_coverage=None if not coverages else fmean(coverages),
                mean_optimality_gap=None if not gaps else fmean(gaps),
                max_optimality_gap=None if not gaps else max(gaps),
                mean_runtime_seconds=fmean(runtimes),
                timeouts=sum(row.timed_out for row in group),
            )
        )
    return summary


@dataclass(frozen=True, slots=True)
class _MetricDescription:
    sample_count: int
    mean: float | None
    median: float | None
    standard_deviation: float | None
    minimum: float | None
    p25: float | None
    p75: float | None
    p95: float | None
    maximum: float | None


def _linear_quantile(values: Sequence[float], probability: float) -> float | None:
    """Return a Hyndman-Fan type-7 quantile without external dependencies."""

    if not values:
        return None
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    interpolated = lower_value + (upper_value - lower_value) * weight
    return min(max(interpolated, lower_value), upper_value)


def _describe_values(values: Sequence[float]) -> _MetricDescription:
    ordered = sorted(values)
    if not ordered:
        return _MetricDescription(0, None, None, None, None, None, None, None, None)
    return _MetricDescription(
        sample_count=len(ordered),
        mean=fmean(ordered),
        median=_linear_quantile(ordered, 0.5),
        standard_deviation=None if len(ordered) < 2 else stdev(ordered),
        minimum=ordered[0],
        p25=_linear_quantile(ordered, 0.25),
        p75=_linear_quantile(ordered, 0.75),
        p95=_linear_quantile(ordered, 0.95),
        maximum=ordered[-1],
    )


class _DescriptiveCommon(TypedDict):
    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    repetition_unit: str
    instance_count: int
    run_count: int
    timeout_count: int
    timeout_rate: float
    error_count: int
    error_rate: float
    valid_exact_reference_count: int
    exact_reference_rate: float


def _descriptive_statistics(
    rows: Sequence[RunRecord],
) -> list[DescriptiveStatisticsRecord]:
    """Build the canonical P5 aggregate using generated instances as units."""

    groups: dict[
        tuple[str, str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    records: list[DescriptiveStatisticsRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, case_id, family, algorithm_id, algorithm = key
        units: dict[tuple[str, str, int, str], list[RunRecord]] = defaultdict(list)
        for row in group:
            units[
                (row.config_hash, row.case_id, row.repetition, row.instance_id)
            ].append(row)

        coverage_values: list[float] = []
        gap_values: list[float] = []
        runtime_values: list[float] = []
        exact_reference_count = 0
        for unit_rows in units.values():
            algorithm_seeds = [row.algorithm_seed for row in unit_rows]
            if len(set(algorithm_seeds)) != len(algorithm_seeds):
                raise ValueError(
                    "algorithm_seed values must be unique within one instance unit"
                )
            if len(unit_rows) > 1 and any(
                seed is None for seed in algorithm_seeds
            ) and any(seed is not None for seed in algorithm_seeds):
                raise ValueError(
                    "one instance unit cannot mix seeded and unseeded runs"
                )

            references = {row.optimum for row in unit_rows}
            if len(references) > 1:
                raise ValueError(
                    "normalized optimum must be consistently absent or identical "
                    "within one instance unit"
                )
            reference = next(iter(references))
            exact_reference_count += reference is not None

            if any(
                row.optimum is not None
                and row.coverage is not None
                and row.coverage > row.optimum
                for row in unit_rows
            ):
                raise ValueError(
                    "coverage exceeds normalized optimum within one instance unit"
                )

            unit_coverages = [
                float(row.coverage)
                for row in unit_rows
                if row.coverage is not None
            ]
            if unit_coverages:
                coverage_values.append(fmean(unit_coverages))

            unit_gaps = [
                row.optimality_gap
                for row in unit_rows
                if row.optimality_gap is not None
            ]
            if unit_gaps:
                gap_values.append(fmean(unit_gaps))

            unit_runtimes = [
                row.runtime_seconds
                for row in unit_rows
                if row.status in {SolutionStatus.OPTIMAL, SolutionStatus.FEASIBLE}
            ]
            if unit_runtimes:
                runtime_values.append(fmean(unit_runtimes))

        run_count = len(group)
        instance_count = len(units)
        timeout_count = sum(
            row.status is SolutionStatus.TIMEOUT for row in group
        )
        error_count = sum(row.status is SolutionStatus.ERROR for row in group)
        common: _DescriptiveCommon = {
            "config_hash": config_identifier,
            "case_id": case_id,
            "family": family,
            "algorithm_id": algorithm_id,
            "algorithm": algorithm,
            "repetition_unit": "instance_seed",
            "instance_count": instance_count,
            "run_count": run_count,
            "timeout_count": timeout_count,
            "timeout_rate": timeout_count / run_count,
            "error_count": error_count,
            "error_rate": error_count / run_count,
            "valid_exact_reference_count": exact_reference_count,
            "exact_reference_rate": exact_reference_count / instance_count,
        }
        for metric, values in (
            ("coverage", coverage_values),
            ("optimality_gap", gap_values),
            ("runtime_seconds", runtime_values),
        ):
            description = _describe_values(values)
            records.append(
                DescriptiveStatisticsRecord(
                    **common,
                    metric=metric,
                    sample_count=description.sample_count,
                    mean=description.mean,
                    median=description.median,
                    standard_deviation=description.standard_deviation,
                    minimum=description.minimum,
                    p25=description.p25,
                    p75=description.p75,
                    p95=description.p95,
                    maximum=description.maximum,
                )
            )
    return records


def _beta_continued_fraction(a: float, b: float, value: float) -> float:
    """Evaluate the incomplete-beta continued fraction deterministically."""

    maximum_iterations = 200
    epsilon = 3e-14
    minimum_float = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * value / qap
    if abs(d) < minimum_float:
        d = minimum_float
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        doubled = 2 * iteration
        coefficient = (
            iteration
            * (b - iteration)
            * value
            / ((qam + doubled) * (a + doubled))
        )
        d = 1.0 + coefficient * d
        if abs(d) < minimum_float:
            d = minimum_float
        c = 1.0 + coefficient / c
        if abs(c) < minimum_float:
            c = minimum_float
        d = 1.0 / d
        result *= d * c

        coefficient = (
            -(a + iteration)
            * (qab + iteration)
            * value
            / ((a + doubled) * (qap + doubled))
        )
        d = 1.0 + coefficient * d
        if abs(d) < minimum_float:
            d = minimum_float
        c = 1.0 + coefficient / c
        if abs(c) < minimum_float:
            c = minimum_float
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= epsilon:
            return result
    raise ArithmeticError("incomplete-beta continued fraction did not converge")


def _regularized_incomplete_beta(
    a: float, b: float, value: float
) -> float:
    """Return the regularized incomplete beta function I_x(a, b)."""

    if a <= 0 or b <= 0:
        raise ValueError("beta shape parameters must be positive")
    if not 0 <= value <= 1:
        raise ValueError("beta value must be between 0 and 1")
    if value == 0:
        return 0.0
    if value == 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(value)
        + b * math.log1p(-value)
    )
    if value < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, value) / a
    return 1.0 - (
        front
        * _beta_continued_fraction(b, a, 1.0 - value)
        / b
    )


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    """Return the Student-t cumulative probability without dependencies."""

    if (
        isinstance(degrees_of_freedom, bool)
        or not isinstance(degrees_of_freedom, int)
        or degrees_of_freedom <= 0
    ):
        raise ValueError("degrees_of_freedom must be a positive integer")
    if not math.isfinite(value):
        if value == math.inf:
            return 1.0
        if value == -math.inf:
            return 0.0
        raise ValueError("Student-t value must not be NaN")
    if value == 0:
        return 0.5
    beta_value = degrees_of_freedom / (
        degrees_of_freedom + value * value
    )
    tail = 0.5 * _regularized_incomplete_beta(
        degrees_of_freedom / 2.0,
        0.5,
        beta_value,
    )
    return 1.0 - tail if value > 0 else tail


def _student_t_critical_95(degrees_of_freedom: int) -> float:
    """Return t_(0.975, df) by deterministic bracketing and bisection."""

    if (
        isinstance(degrees_of_freedom, bool)
        or not isinstance(degrees_of_freedom, int)
        or degrees_of_freedom <= 0
    ):
        raise ValueError("degrees_of_freedom must be a positive integer")
    target = 0.975
    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < target:
        upper *= 2.0
    for _ in range(80):
        midpoint = (lower + upper) / 2.0
        if _student_t_cdf(midpoint, degrees_of_freedom) < target:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _ten_decimal(value: float) -> float:
    return float(f"{value:.10f}")


class _ConfidenceIntervalCommon(TypedDict):
    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    metric: str
    estimand: str
    confidence_level: float
    method: str
    repetition_unit: str
    instance_count: int
    sample_count: int
    run_count: int
    timeout_count: int
    error_count: int
    valid_exact_reference_count: int
    degrees_of_freedom: int


def _confidence_interval_statistics(
    statistics: Sequence[DescriptiveStatisticsRecord],
) -> list[ConfidenceIntervalRecord]:
    """Build 95% Student-t intervals from canonical P5.1 metric rows."""

    records: list[ConfidenceIntervalRecord] = []
    for source in statistics:
        canonical = DescriptiveStatisticsRecord.from_csv_row(
            {
                name: str(value)
                for name, value in source.to_csv_row().items()
            }
        )
        sample_count = canonical.sample_count
        common: _ConfidenceIntervalCommon = {
            "config_hash": canonical.config_hash,
            "case_id": canonical.case_id,
            "family": canonical.family,
            "algorithm_id": canonical.algorithm_id,
            "algorithm": canonical.algorithm,
            "metric": canonical.metric,
            "estimand": "instance_mean",
            "confidence_level": 0.95,
            "method": "student_t_two_sided",
            "repetition_unit": canonical.repetition_unit,
            "instance_count": canonical.instance_count,
            "sample_count": sample_count,
            "run_count": canonical.run_count,
            "timeout_count": canonical.timeout_count,
            "error_count": canonical.error_count,
            "valid_exact_reference_count": (
                canonical.valid_exact_reference_count
            ),
            "degrees_of_freedom": max(sample_count - 1, 0),
        }
        if sample_count == 0:
            records.append(
                ConfidenceIntervalRecord(
                    **common,
                    mean=None,
                    standard_error=None,
                    critical_value=None,
                    lower_bound=None,
                    upper_bound=None,
                    interval_status="no_samples",
                )
            )
            continue
        assert canonical.mean is not None
        if sample_count == 1:
            records.append(
                ConfidenceIntervalRecord(
                    **common,
                    mean=canonical.mean,
                    standard_error=None,
                    critical_value=None,
                    lower_bound=None,
                    upper_bound=None,
                    interval_status="insufficient_samples",
                )
            )
            continue

        assert canonical.standard_deviation is not None
        standard_error = _ten_decimal(
            canonical.standard_deviation / math.sqrt(sample_count)
        )
        critical_value = _ten_decimal(
            _student_t_critical_95(sample_count - 1)
        )
        mean = canonical.mean
        margin = standard_error * critical_value
        records.append(
            ConfidenceIntervalRecord(
                **common,
                mean=mean,
                standard_error=standard_error,
                critical_value=critical_value,
                lower_bound=_ten_decimal(mean - margin),
                upper_bound=_ten_decimal(mean + margin),
                interval_status="estimable",
            )
        )
    return records


def _censored_runtime_statistics(
    rows: Sequence[RunRecord],
) -> list[CensoredRuntimeRecord]:
    """Report timeout elapsed times as right-censored runtime observations."""

    groups: dict[
        tuple[str, str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    records: list[CensoredRuntimeRecord] = []
    completed_statuses = {
        SolutionStatus.OPTIMAL,
        SolutionStatus.FEASIBLE,
    }
    for key, group in sorted(groups.items()):
        config_identifier, case_id, family, algorithm_id, algorithm = key
        units: dict[
            tuple[str, str, int, str], list[RunRecord]
        ] = defaultdict(list)
        for row in group:
            units[
                (row.config_hash, row.case_id, row.repetition, row.instance_id)
            ].append(row)

        expected_seed_layout: tuple[int | None, ...] | None = None
        censor_times: list[float] = []
        completed_run_count = 0
        right_censored_run_count = 0
        error_run_count = 0
        completed_instance_count = 0
        right_censored_instance_count = 0
        error_affected_instance_count = 0
        fully_right_censored_instance_count = 0
        for unit_rows in units.values():
            seeds = [row.algorithm_seed for row in unit_rows]
            if len(set(seeds)) != len(seeds):
                raise ValueError(
                    "censored-runtime statistics require unique algorithm "
                    "seeds within each instance"
                )
            if any(seed is None for seed in seeds) and any(
                seed is not None for seed in seeds
            ):
                raise ValueError(
                    "censored-runtime statistics cannot mix seeded and "
                    "unseeded runs within one instance"
                )
            seed_layout = tuple(
                sorted(
                    seeds,
                    key=lambda seed: (
                        seed is not None,
                        -1 if seed is None else seed,
                    ),
                )
            )
            if expected_seed_layout is None:
                expected_seed_layout = seed_layout
            elif seed_layout != expected_seed_layout:
                raise ValueError(
                    "censored-runtime statistics require a fixed algorithm "
                    "seed layout within each variant"
                )

            completed_rows = [
                row for row in unit_rows if row.status in completed_statuses
            ]
            timeout_rows = [
                row
                for row in unit_rows
                if row.status is SolutionStatus.TIMEOUT
            ]
            error_rows = [
                row
                for row in unit_rows
                if row.status is SolutionStatus.ERROR
            ]
            if (
                len(completed_rows) + len(timeout_rows) + len(error_rows)
                != len(unit_rows)
            ):
                raise ValueError(
                    "censored-runtime statistics received an unsupported "
                    "solution status"
                )
            completed_run_count += len(completed_rows)
            right_censored_run_count += len(timeout_rows)
            error_run_count += len(error_rows)
            if completed_rows:
                completed_instance_count += 1
            if timeout_rows:
                right_censored_instance_count += 1
                censor_times.append(
                    _ten_decimal(
                        fmean(row.runtime_seconds for row in timeout_rows)
                    )
                )
            if error_rows:
                error_affected_instance_count += 1
            if len(timeout_rows) == len(unit_rows):
                fully_right_censored_instance_count += 1

        if censor_times:
            mean_censor_time = _ten_decimal(fmean(censor_times))
            median_censor_time = _ten_decimal(median(censor_times))
            minimum_censor_time = min(censor_times)
            maximum_censor_time = max(censor_times)
            censoring_status = (
                "all_runtime_observations_right_censored"
                if completed_run_count == 0
                else "right_censoring_present"
            )
        else:
            mean_censor_time = None
            median_censor_time = None
            minimum_censor_time = None
            maximum_censor_time = None
            censoring_status = (
                "no_runtime_observations"
                if completed_run_count == 0
                else "no_censoring"
            )
        instance_count = len(units)
        records.append(
            CensoredRuntimeRecord(
                config_hash=config_identifier,
                case_id=case_id,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                repetition_unit="instance_seed",
                instance_count=instance_count,
                run_count=len(group),
                completed_run_count=completed_run_count,
                right_censored_run_count=right_censored_run_count,
                error_run_count=error_run_count,
                completed_instance_count=completed_instance_count,
                right_censored_instance_count=(
                    right_censored_instance_count
                ),
                error_affected_instance_count=(
                    error_affected_instance_count
                ),
                fully_right_censored_instance_count=(
                    fully_right_censored_instance_count
                ),
                censoring_sample_count=len(censor_times),
                censoring_rate=_ten_decimal(
                    right_censored_instance_count / instance_count
                ),
                mean_censor_time_seconds=mean_censor_time,
                median_censor_time_seconds=median_censor_time,
                minimum_censor_time_seconds=minimum_censor_time,
                maximum_censor_time_seconds=maximum_censor_time,
                censoring_status=censoring_status,
            )
        )
    return records


def _runtime_ratio_variant_units(
    rows: Sequence[RunRecord],
    label: str,
    *,
    exact: bool,
) -> dict[tuple[str, str, int, str], list[RunRecord]]:
    units: dict[tuple[str, str, int, str], list[RunRecord]] = defaultdict(list)
    for row in rows:
        unit = (row.config_hash, row.case_id, row.repetition, row.instance_id)
        units[unit].append(row)
    for unit_rows in units.values():
        algorithm_seeds = [row.algorithm_seed for row in unit_rows]
        if len(set(algorithm_seeds)) != len(algorithm_seeds):
            raise ValueError(
                f"{label} runtime-ratio statistics require unique algorithm seeds"
            )
        if len(unit_rows) > 1 and any(
            seed is None for seed in algorithm_seeds
        ) and any(seed is not None for seed in algorithm_seeds):
            raise ValueError(
                f"{label} runtime-ratio statistics cannot mix seeded and "
                "unseeded runs"
            )
        if exact and (
            len(unit_rows) != 1 or unit_rows[0].algorithm_seed is not None
        ):
            raise ValueError(
                "exact runtime-ratio variants require one unseeded run per "
                "instance unit"
            )
    return dict(units)


def _heuristic_exact_runtime_ratio_statistics(
    rows: Sequence[RunRecord],
) -> list[HeuristicExactRuntimeRatioRecord]:
    """Compare completed heuristic runtime with paired completed exact runtime."""

    groups: dict[
        tuple[str, str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    heuristic_groups = [
        (key, group)
        for key, group in groups.items()
        if not ALGORITHMS[key[4]].exact
    ]
    exact_groups = [
        (key, group)
        for key, group in groups.items()
        if ALGORITHMS[key[4]].exact
    ]
    completed_statuses = {
        SolutionStatus.OPTIMAL,
        SolutionStatus.FEASIBLE,
    }
    records: list[HeuristicExactRuntimeRatioRecord] = []
    for heuristic_key, heuristic_group in sorted(heuristic_groups):
        (
            config_identifier,
            case_id,
            family,
            heuristic_algorithm_id,
            heuristic_algorithm,
        ) = heuristic_key
        matching_exact_groups = [
            (key, group)
            for key, group in exact_groups
            if key[:3] == heuristic_key[:3]
        ]
        for exact_key, exact_group in sorted(matching_exact_groups):
            exact_algorithm_id = exact_key[3]
            exact_algorithm = exact_key[4]
            heuristic_units = _runtime_ratio_variant_units(
                heuristic_group,
                "heuristic",
                exact=False,
            )
            exact_units = _runtime_ratio_variant_units(
                exact_group,
                "exact",
                exact=True,
            )
            if heuristic_units.keys() != exact_units.keys():
                raise ValueError(
                    "runtime-ratio statistics require identical instance units "
                    "for paired heuristic and exact variants"
                )

            ratios: list[float] = []
            zero_exact_runtime_count = 0
            for unit in sorted(heuristic_units):
                heuristic_completed = [
                    row.runtime_seconds
                    for row in heuristic_units[unit]
                    if row.status in completed_statuses
                ]
                exact_completed = [
                    row.runtime_seconds
                    for row in exact_units[unit]
                    if row.status in completed_statuses
                ]
                if exact_completed and exact_completed[0] == 0:
                    zero_exact_runtime_count += 1
                if (
                    not heuristic_completed
                    or not exact_completed
                    or exact_completed[0] == 0
                ):
                    continue
                ratios.append(fmean(heuristic_completed) / exact_completed[0])

            heuristic_run_count = len(heuristic_group)
            exact_run_count = len(exact_group)
            heuristic_completed_run_count = sum(
                row.status in completed_statuses for row in heuristic_group
            )
            exact_completed_run_count = sum(
                row.status in completed_statuses for row in exact_group
            )
            records.append(
                HeuristicExactRuntimeRatioRecord(
                    config_hash=config_identifier,
                    case_id=case_id,
                    family=family,
                    heuristic_algorithm_id=heuristic_algorithm_id,
                    heuristic_algorithm=heuristic_algorithm,
                    exact_algorithm_id=exact_algorithm_id,
                    exact_algorithm=exact_algorithm,
                    repetition_unit="instance_seed",
                    instance_count=len(heuristic_units),
                    heuristic_run_count=heuristic_run_count,
                    heuristic_completed_run_count=(
                        heuristic_completed_run_count
                    ),
                    heuristic_timeout_count=sum(
                        row.status is SolutionStatus.TIMEOUT
                        for row in heuristic_group
                    ),
                    heuristic_error_count=sum(
                        row.status is SolutionStatus.ERROR
                        for row in heuristic_group
                    ),
                    exact_run_count=exact_run_count,
                    exact_completed_run_count=exact_completed_run_count,
                    exact_timeout_count=sum(
                        row.status is SolutionStatus.TIMEOUT
                        for row in exact_group
                    ),
                    exact_error_count=sum(
                        row.status is SolutionStatus.ERROR
                        for row in exact_group
                    ),
                    eligible_pair_count=len(ratios),
                    zero_exact_runtime_count=zero_exact_runtime_count,
                    mean_runtime_ratio=None if not ratios else fmean(ratios),
                    median_runtime_ratio=None if not ratios else median(ratios),
                    minimum_runtime_ratio=None if not ratios else min(ratios),
                    maximum_runtime_ratio=None if not ratios else max(ratios),
                )
            )
    return records


def _bnb_variant_units(
    rows: Sequence[RunRecord], label: str
) -> dict[tuple[str, str, int, str], RunRecord]:
    units: dict[tuple[str, str, int, str], RunRecord] = {}
    allowed_statuses = {
        SolutionStatus.OPTIMAL,
        SolutionStatus.TIMEOUT,
        SolutionStatus.ERROR,
    }
    for row in rows:
        if row.algorithm_seed is not None:
            raise ValueError(
                f"{label} BnB node-reduction statistics forbid algorithm seeds"
            )
        if row.status not in allowed_statuses:
            raise ValueError(
                f"{label} BnB node-reduction records must be optimal, "
                "timeout, or error"
            )
        unit = (row.config_hash, row.case_id, row.repetition, row.instance_id)
        if unit in units:
            raise ValueError(
                f"{label} BnB node-reduction statistics require exactly one "
                "run per instance unit"
            )
        if row.status is not SolutionStatus.ERROR:
            metadata = json.loads(row.algorithm_metadata)
            search = metadata.get("search")
            nodes = (
                search.get("nodes_visited")
                if isinstance(search, dict)
                else None
            )
            if nodes is not None and (
                isinstance(nodes, bool)
                or not isinstance(nodes, int)
                or nodes < 0
                or nodes != row.nodes_or_iterations
            ):
                raise ValueError(
                    f"{label} BnB nodes_or_iterations must match "
                    "algorithm_metadata.search.nodes_visited"
                )
        units[unit] = row
    return units


def _bnb_node_reduction_statistics(
    rows: Sequence[RunRecord],
) -> list[BranchAndBoundNodeReductionRecord]:
    """Compare completed baseline and enhanced BnB search-node counts."""

    groups: dict[
        tuple[str, str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        if row.algorithm in {
            "branch_and_bound",
            "branch_and_bound_enhanced",
        }:
            groups[
                (
                    row.config_hash,
                    row.case_id,
                    row.family,
                    row.algorithm_id,
                    row.algorithm,
                )
            ].append(row)

    baseline_groups = [
        (key, group)
        for key, group in groups.items()
        if key[4] == "branch_and_bound"
    ]
    enhanced_groups = [
        (key, group)
        for key, group in groups.items()
        if key[4] == "branch_and_bound_enhanced"
    ]
    records: list[BranchAndBoundNodeReductionRecord] = []
    for baseline_key, baseline_group in sorted(baseline_groups):
        (
            config_identifier,
            case_id,
            family,
            baseline_algorithm_id,
            baseline_algorithm,
        ) = baseline_key
        matching_enhanced_groups = [
            (key, group)
            for key, group in enhanced_groups
            if key[:3] == baseline_key[:3]
        ]
        for enhanced_key, enhanced_group in sorted(matching_enhanced_groups):
            enhanced_algorithm_id = enhanced_key[3]
            enhanced_algorithm = enhanced_key[4]
            baseline_units = _bnb_variant_units(
                baseline_group, "baseline"
            )
            enhanced_units = _bnb_variant_units(
                enhanced_group, "enhanced"
            )
            if baseline_units.keys() != enhanced_units.keys():
                raise ValueError(
                    "BnB node-reduction statistics require identical "
                    "instance units for paired variants"
                )

            reductions: list[float] = []
            zero_baseline_nodes_count = 0
            total_baseline_nodes = 0
            total_enhanced_nodes = 0
            for unit in sorted(baseline_units):
                baseline = baseline_units[unit]
                enhanced = enhanced_units[unit]
                if (
                    baseline.status is SolutionStatus.OPTIMAL
                    and baseline.nodes_or_iterations == 0
                ):
                    zero_baseline_nodes_count += 1
                if not (
                    baseline.status is SolutionStatus.OPTIMAL
                    and enhanced.status is SolutionStatus.OPTIMAL
                ):
                    continue
                if baseline.coverage != enhanced.coverage:
                    raise ValueError(
                        "paired optimal BnB variants must agree on coverage"
                    )
                if baseline.nodes_or_iterations == 0:
                    continue
                baseline_nodes = baseline.nodes_or_iterations
                enhanced_nodes = enhanced.nodes_or_iterations
                total_baseline_nodes += baseline_nodes
                total_enhanced_nodes += enhanced_nodes
                reductions.append(1 - enhanced_nodes / baseline_nodes)

            baseline_optimal_count = sum(
                row.status is SolutionStatus.OPTIMAL for row in baseline_group
            )
            enhanced_optimal_count = sum(
                row.status is SolutionStatus.OPTIMAL for row in enhanced_group
            )
            aggregate_reduction = (
                None
                if not reductions
                else 1 - total_enhanced_nodes / total_baseline_nodes
            )
            records.append(
                BranchAndBoundNodeReductionRecord(
                    config_hash=config_identifier,
                    case_id=case_id,
                    family=family,
                    baseline_algorithm_id=baseline_algorithm_id,
                    baseline_algorithm=baseline_algorithm,
                    enhanced_algorithm_id=enhanced_algorithm_id,
                    enhanced_algorithm=enhanced_algorithm,
                    repetition_unit="instance_seed",
                    instance_count=len(baseline_units),
                    baseline_run_count=len(baseline_group),
                    baseline_optimal_count=baseline_optimal_count,
                    baseline_timeout_count=sum(
                        row.status is SolutionStatus.TIMEOUT
                        for row in baseline_group
                    ),
                    baseline_error_count=sum(
                        row.status is SolutionStatus.ERROR
                        for row in baseline_group
                    ),
                    enhanced_run_count=len(enhanced_group),
                    enhanced_optimal_count=enhanced_optimal_count,
                    enhanced_timeout_count=sum(
                        row.status is SolutionStatus.TIMEOUT
                        for row in enhanced_group
                    ),
                    enhanced_error_count=sum(
                        row.status is SolutionStatus.ERROR
                        for row in enhanced_group
                    ),
                    eligible_pair_count=len(reductions),
                    zero_baseline_nodes_count=zero_baseline_nodes_count,
                    total_baseline_nodes=total_baseline_nodes,
                    total_enhanced_nodes=total_enhanced_nodes,
                    mean_node_reduction=(
                        None if not reductions else fmean(reductions)
                    ),
                    median_node_reduction=(
                        None if not reductions else median(reductions)
                    ),
                    minimum_node_reduction=(
                        None if not reductions else min(reductions)
                    ),
                    maximum_node_reduction=(
                        None if not reductions else max(reductions)
                    ),
                    aggregate_node_reduction=aggregate_reduction,
                )
            )
    return records


def _pareto_variant_units(
    rows: Sequence[RunRecord], label: str
) -> dict[tuple[str, str, int, str], list[RunRecord]]:
    units: dict[tuple[str, str, int, str], list[RunRecord]] = defaultdict(list)
    for row in rows:
        unit = (row.config_hash, row.case_id, row.repetition, row.instance_id)
        units[unit].append(row)

    expected_seed_layout: tuple[int | None, ...] | None = None
    for unit, unit_rows in units.items():
        seeds = [row.algorithm_seed for row in unit_rows]
        if len(set(seeds)) != len(seeds):
            raise ValueError(
                f"{label} Pareto statistics require unique algorithm seeds "
                "within each instance"
            )
        if any(seed is None for seed in seeds) and any(
            seed is not None for seed in seeds
        ):
            raise ValueError(
                f"{label} Pareto statistics cannot mix seeded and unseeded runs"
            )
        layout = (
            (None,)
            if seeds and seeds[0] is None
            else tuple(sorted(seed for seed in seeds if seed is not None))
        )
        if expected_seed_layout is None:
            expected_seed_layout = layout
        elif layout != expected_seed_layout:
            raise ValueError(
                f"{label} Pareto statistics require the same algorithm-seed "
                "layout on every instance"
            )
        units[unit] = sorted(
            unit_rows,
            key=lambda row: (
                row.algorithm_seed is not None,
                -1 if row.algorithm_seed is None else row.algorithm_seed,
                row.run_id,
            ),
        )
    return dict(units)


def _quality_runtime_pareto_statistics(
    rows: Sequence[RunRecord],
) -> list[QualityRuntimeParetoRecord]:
    """Build Case-local Pareto points from fully observed common instances."""

    groups: dict[
        tuple[str, str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    contexts: dict[
        tuple[str, str, str],
        list[tuple[tuple[str, str, str, str, str], list[RunRecord]]],
    ] = defaultdict(list)
    for key, group in groups.items():
        contexts[key[:3]].append((key, group))

    completed_statuses = {
        SolutionStatus.OPTIMAL,
        SolutionStatus.FEASIBLE,
    }
    records: list[QualityRuntimeParetoRecord] = []
    for context, variants in sorted(contexts.items()):
        sorted_variants = sorted(variants)
        algorithm_ids = [key[3] for key, _ in sorted_variants]
        if len(set(algorithm_ids)) != len(algorithm_ids):
            raise ValueError(
                "Pareto statistics require unique algorithm IDs within a Case"
            )

        units_by_variant = {
            key: _pareto_variant_units(group, key[3])
            for key, group in sorted_variants
        }
        first_units = next(iter(units_by_variant.values()))
        for units in units_by_variant.values():
            if units.keys() != first_units.keys():
                raise ValueError(
                    "Pareto statistics require identical instance units for "
                    "all variants in a Case"
                )
        instance_count = len(first_units)

        optimum_by_unit: dict[tuple[str, str, int, str], int | None] = {}
        for unit in sorted(first_units):
            references = {
                row.optimum
                for units in units_by_variant.values()
                for row in units[unit]
            }
            if len(references) != 1:
                raise ValueError(
                    "Pareto statistics require one consistent normalized exact "
                    "reference per instance"
                )
            optimum_by_unit[unit] = next(iter(references))

        valid_reference_count = sum(
            optimum is not None for optimum in optimum_by_unit.values()
        )
        zero_optimum_count = sum(
            optimum == 0 for optimum in optimum_by_unit.values()
        )
        eligible_units = [
            unit
            for unit, optimum in sorted(optimum_by_unit.items())
            if optimum is not None
            and optimum > 0
            and all(
                row.status in completed_statuses
                for units in units_by_variant.values()
                for row in units[unit]
            )
        ]

        points: dict[str, tuple[float, float]] = {}
        base_values: dict[
            str,
            tuple[
                tuple[str, str, str, str, str],
                list[RunRecord],
            ],
        ] = {}
        for key, group in sorted_variants:
            algorithm_id = key[3]
            instance_gaps: list[float] = []
            instance_runtimes: list[float] = []
            for unit in eligible_units:
                unit_rows = units_by_variant[key][unit]
                gaps = [row.optimality_gap for row in unit_rows]
                if any(gap is None for gap in gaps):
                    raise ValueError(
                        "eligible Pareto runs require a relative optimality gap"
                    )
                instance_gaps.append(
                    fmean(gap for gap in gaps if gap is not None)
                )
                instance_runtimes.append(
                    fmean(row.runtime_seconds for row in unit_rows)
                )
            if eligible_units:
                point = (
                    float(f"{fmean(instance_gaps):.10f}"),
                    float(f"{fmean(instance_runtimes):.10f}"),
                )
                points[algorithm_id] = point
            base_values[algorithm_id] = (key, group)

        for algorithm_id in sorted(base_values):
            key, group = base_values[algorithm_id]
            if not eligible_units:
                status = "not_evaluable"
                dominators: tuple[str, ...] = ()
                mean_gap = None
                mean_runtime = None
            else:
                mean_gap, mean_runtime = points[algorithm_id]
                dominators = tuple(
                    sorted(
                        other_id
                        for other_id, (other_gap, other_runtime) in points.items()
                        if other_id != algorithm_id
                        and other_gap <= mean_gap
                        and other_runtime <= mean_runtime
                        and (
                            other_gap < mean_gap
                            or other_runtime < mean_runtime
                        )
                    )
                )
                status = "dominated" if dominators else "frontier"
            records.append(
                QualityRuntimeParetoRecord(
                    config_hash=context[0],
                    case_id=context[1],
                    family=context[2],
                    algorithm_id=algorithm_id,
                    algorithm=key[4],
                    repetition_unit="instance_seed",
                    instance_count=instance_count,
                    run_count=len(group),
                    completed_run_count=sum(
                        row.status in completed_statuses for row in group
                    ),
                    timeout_count=sum(
                        row.status is SolutionStatus.TIMEOUT for row in group
                    ),
                    error_count=sum(
                        row.status is SolutionStatus.ERROR for row in group
                    ),
                    valid_exact_reference_count=valid_reference_count,
                    zero_optimum_count=zero_optimum_count,
                    no_exact_reference_count=(
                        instance_count - valid_reference_count
                    ),
                    eligible_instance_count=len(eligible_units),
                    mean_relative_gap=mean_gap,
                    mean_runtime_seconds=mean_runtime,
                    pareto_status=status,
                    dominated_by_algorithm_ids=dominators,
                )
            )
    return records
