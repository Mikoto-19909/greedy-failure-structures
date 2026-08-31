"""Generator-level structural isolation audits.

The benchmark runner records the canonical instance metrics used by the study.
This module adds diagnostics that are useful for checking generator calibration
but are intentionally not part of the frozen ``instances.csv`` contract.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from statistics import fmean

from .algorithms import greedy
from .benchmark import _instances_for_config
from .certificates import known_optimum_certificate
from .config import CaseConfig, ExperimentConfig
from .generators import uniform_random
from .model import MaximumCoverageInstance
from .structure import InstanceStructureMetrics, analyze_instance


AUDIT_SCHEMA_VERSION = 1
DEFAULT_INCIDENCE_RELATIVE_TOLERANCE = 0.02


@dataclass(frozen=True, slots=True)
class StressorStructureMetrics:
    """Exact supplementary metrics computed from one realized instance."""

    pairwise_overlap_q25_jaccard: float | None
    pairwise_overlap_q50_jaccard: float | None
    pairwise_overlap_q75_jaccard: float | None
    pairwise_overlap_q90_jaccard: float | None
    coverage_head_10pct_ratio: float
    cluster_within_mean_jaccard: float | None
    cluster_between_mean_jaccard: float | None
    cluster_separation_jaccard: float | None


@dataclass(frozen=True, slots=True)
class _Observation:
    repetition: int
    level: int | float
    target_value: float
    basic: InstanceStructureMetrics
    supplementary: StressorStructureMetrics
    universe_size: int
    set_count: int
    k: int
    uniform_basic: InstanceStructureMetrics
    uniform_supplementary: StressorStructureMetrics
    uniform_dimensions_match: bool
    greedy_selected_bait_first: bool | None
    certificate_verified: bool | None


@dataclass(frozen=True, slots=True)
class _AuditSpec:
    intensity_parameter: str
    target_metric: str
    expected_direction: str | None
    target: Callable[
        [MaximumCoverageInstance, InstanceStructureMetrics, StressorStructureMetrics],
        float,
    ]


def _quantile(values: Sequence[float], probability: float) -> float | None:
    """Return the deterministic type-7 empirical quantile."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _coverage_frequencies(instance: MaximumCoverageInstance) -> list[int]:
    frequencies = [0] * instance.universe_size
    for mask in instance.sets:
        remaining = mask
        while remaining:
            lowest = remaining & -remaining
            frequencies[lowest.bit_length() - 1] += 1
            remaining ^= lowest
    return frequencies


def analyze_stressor_structure(
    instance: MaximumCoverageInstance,
) -> StressorStructureMetrics:
    """Compute overlap tails, head concentration, and cluster separation."""

    jaccards: list[float] = []
    within: list[float] = []
    between: list[float] = []
    raw_clusters = instance.parameters.get("clusters")
    clusters = (
        raw_clusters
        if instance.family == "clustered"
        and isinstance(raw_clusters, int)
        and not isinstance(raw_clusters, bool)
        else None
    )

    for left_index, left in enumerate(instance.sets):
        for right_index in range(left_index + 1, instance.set_count):
            right = instance.sets[right_index]
            union = left | right
            if union == 0:
                continue
            value = (left & right).bit_count() / union.bit_count()
            jaccards.append(value)
            if clusters is not None:
                destination = (
                    within
                    if left_index % clusters == right_index % clusters
                    else between
                )
                destination.append(value)

    frequencies = _coverage_frequencies(instance)
    incidence_count = sum(frequencies)
    head_count = max(1, math.ceil(instance.universe_size * 0.1))
    head_ratio = (
        0.0
        if incidence_count == 0
        else sum(sorted(frequencies, reverse=True)[:head_count]) / incidence_count
    )
    within_mean = None if not within else math.fsum(within) / len(within)
    between_mean = None if not between else math.fsum(between) / len(between)
    separation = (
        None
        if within_mean is None or between_mean is None
        else within_mean - between_mean
    )
    return StressorStructureMetrics(
        pairwise_overlap_q25_jaccard=_quantile(jaccards, 0.25),
        pairwise_overlap_q50_jaccard=_quantile(jaccards, 0.50),
        pairwise_overlap_q75_jaccard=_quantile(jaccards, 0.75),
        pairwise_overlap_q90_jaccard=_quantile(jaccards, 0.90),
        coverage_head_10pct_ratio=head_ratio,
        cluster_within_mean_jaccard=within_mean,
        cluster_between_mean_jaccard=between_mean,
        cluster_separation_jaccard=separation,
    )


def _basic_metric(name: str) -> Callable[
    [MaximumCoverageInstance, InstanceStructureMetrics, StressorStructureMetrics],
    float,
]:
    def metric(
        instance: MaximumCoverageInstance,
        basic: InstanceStructureMetrics,
        supplementary: StressorStructureMetrics,
    ) -> float:
        del instance, supplementary
        value = getattr(basic, name)
        if value is None:
            raise ValueError(f"target metric {name!r} is undefined")
        return float(value)

    return metric


def _supplementary_metric(name: str) -> Callable[
    [MaximumCoverageInstance, InstanceStructureMetrics, StressorStructureMetrics],
    float,
]:
    def metric(
        instance: MaximumCoverageInstance,
        basic: InstanceStructureMetrics,
        supplementary: StressorStructureMetrics,
    ) -> float:
        del instance, basic
        value = getattr(supplementary, name)
        if value is None:
            raise ValueError(f"target metric {name!r} is undefined")
        return float(value)

    return metric


def _adversarial_severity(
    instance: MaximumCoverageInstance,
    basic: InstanceStructureMetrics,
    supplementary: StressorStructureMetrics,
) -> float:
    del basic, supplementary
    block_size = instance.parameters.get("block_size")
    trap_count = instance.parameters.get("trap_count")
    if (
        isinstance(block_size, bool)
        or not isinstance(block_size, int)
        or isinstance(trap_count, bool)
        or not isinstance(trap_count, int)
    ):
        raise ValueError("adversarial audit requires integer block_size and trap_count")
    return (block_size - trap_count) / (2 * block_size)


_AUDIT_SPECS: Mapping[tuple[str, str], _AuditSpec] = {
    ("duplicate_heavy", "copy_factor"): _AuditSpec(
        "copy_factor", "duplicate_set_ratio", "increasing", _basic_metric("duplicate_set_ratio")
    ),
    ("dominated_heavy", "child_count"): _AuditSpec(
        "child_count", "dominated_set_ratio", "increasing", _basic_metric("dominated_set_ratio")
    ),
    ("long_tail", "gamma"): _AuditSpec(
        "gamma", "coverage_skew_gini", "increasing", _basic_metric("coverage_skew_gini")
    ),
    ("high_overlap", "core_fraction"): _AuditSpec(
        "core_fraction",
        "pairwise_overlap_mean_jaccard",
        "increasing",
        _basic_metric("pairwise_overlap_mean_jaccard"),
    ),
    ("high_overlap", "core_probability"): _AuditSpec(
        "core_probability",
        "pairwise_overlap_mean_jaccard",
        "increasing",
        _basic_metric("pairwise_overlap_mean_jaccard"),
    ),
    ("clustered", "within_probability"): _AuditSpec(
        "within_probability",
        "cluster_separation_jaccard",
        "increasing",
        _supplementary_metric("cluster_separation_jaccard"),
    ),
    ("clustered", "outside_probability"): _AuditSpec(
        "outside_probability",
        "cluster_separation_jaccard",
        "decreasing",
        _supplementary_metric("cluster_separation_jaccard"),
    ),
    ("clustered", "clusters"): _AuditSpec(
        "clusters",
        "cluster_separation_jaccard",
        None,
        _supplementary_metric("cluster_separation_jaccard"),
    ),
    ("adversarial", "trap_count"): _AuditSpec(
        "trap_count", "adversarial_severity", "decreasing", _adversarial_severity
    ),
}


def _control_seed(instance: MaximumCoverageInstance, repetition: int) -> int:
    payload = (
        f"stressor-audit-uniform-control\0{instance.family}\0{instance.seed}\0"
        f"{repetition}\0{instance.universe_size}\0{instance.set_count}\0{instance.k}"
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:16], "big")


def _uniform_control(
    instance: MaximumCoverageInstance,
    basic: InstanceStructureMetrics,
    repetition: int,
) -> MaximumCoverageInstance:
    return uniform_random(
        universe_size=instance.universe_size,
        set_count=instance.set_count,
        k=instance.k,
        density=basic.actual_density,
        seed=_control_seed(instance, repetition),
    )


def _varied_parameters(cases: Sequence[CaseConfig]) -> tuple[str, ...]:
    names = set().union(*(set(case.parameters) for case in cases))
    varied: list[str] = []
    for name in sorted(names):
        values = [case.parameters.get(name) for case in cases]
        if any(value != values[0] for value in values[1:]):
            varied.append(name)
    return tuple(varied)


def _monotonic(values: Sequence[float], direction: str | None) -> bool | None:
    if direction is None:
        return None
    if len(values) < 2:
        return False
    pairs = zip(values, values[1:])
    if direction == "increasing":
        return all(left < right for left, right in pairs)
    if direction == "decreasing":
        return all(left > right for left, right in pairs)
    raise ValueError(f"unsupported audit direction {direction!r}")


def _mean_optional(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return None if not present else fmean(present)


def _relative_range(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("relative range requires at least one value")
    center = fmean(values)
    difference = max(values) - min(values)
    if center == 0:
        scale = max(abs(value) for value in values)
        return 0.0 if scale == 0 else difference / scale
    return difference / abs(center)


def _metric_level_ranges(
    level_summaries: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, float]]:
    names: set[str] = set()
    for summary in level_summaries:
        metrics = summary.get("metrics")
        if isinstance(metrics, Mapping):
            names.update(str(name) for name in metrics)
    result: dict[str, dict[str, float]] = {}
    for name in sorted(names):
        values: list[float] = []
        for summary in level_summaries:
            metrics = summary.get("metrics")
            if not isinstance(metrics, Mapping):
                break
            value = metrics.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                break
            values.append(float(value))
        if len(values) != len(level_summaries):
            continue
        result[name] = {
            "absolute_range": max(values) - min(values),
            "relative_range": _relative_range(values),
        }
    return result


def _level_summary(level: int | float, rows: Sequence[_Observation]) -> dict[str, object]:
    basics = [row.basic for row in rows]
    supplementary = [row.supplementary for row in rows]
    control_basics = [row.uniform_basic for row in rows]
    control_supplementary = [row.uniform_supplementary for row in rows]
    return {
        "level": level,
        "sample_count": len(rows),
        "target_mean": fmean(row.target_value for row in rows),
        "dimensions": {
            "universe_size_values": sorted({row.universe_size for row in rows}),
            "set_count_values": sorted({row.set_count for row in rows}),
            "k_values": sorted({row.k for row in rows}),
        },
        "metrics": {
            "incidence_count_mean": fmean(item.incidence_count for item in basics),
            "actual_density_mean": fmean(item.actual_density for item in basics),
            "unique_set_ratio_mean": fmean(
                item.unique_set_count / row.set_count
                for item, row in zip(basics, rows, strict=True)
            ),
            "duplicate_set_ratio_mean": fmean(item.duplicate_set_ratio for item in basics),
            "dominated_set_ratio_mean": fmean(item.dominated_set_ratio for item in basics),
            "dominated_unique_ratio_mean": fmean(
                item.dominated_unique_ratio for item in basics
            ),
            "pairwise_overlap_mean_jaccard_mean": _mean_optional(
                [item.pairwise_overlap_mean_jaccard for item in basics]
            ),
            "pairwise_overlap_q25_jaccard_mean": _mean_optional(
                [item.pairwise_overlap_q25_jaccard for item in supplementary]
            ),
            "pairwise_overlap_q50_jaccard_mean": _mean_optional(
                [item.pairwise_overlap_q50_jaccard for item in supplementary]
            ),
            "pairwise_overlap_q75_jaccard_mean": _mean_optional(
                [item.pairwise_overlap_q75_jaccard for item in supplementary]
            ),
            "pairwise_overlap_q90_jaccard_mean": _mean_optional(
                [item.pairwise_overlap_q90_jaccard for item in supplementary]
            ),
            "coverage_skew_gini_mean": fmean(item.coverage_skew_gini for item in basics),
            "coverage_head_10pct_ratio_mean": fmean(
                item.coverage_head_10pct_ratio for item in supplementary
            ),
            "cluster_within_mean_jaccard_mean": _mean_optional(
                [item.cluster_within_mean_jaccard for item in supplementary]
            ),
            "cluster_between_mean_jaccard_mean": _mean_optional(
                [item.cluster_between_mean_jaccard for item in supplementary]
            ),
            "cluster_separation_jaccard_mean": _mean_optional(
                [item.cluster_separation_jaccard for item in supplementary]
            ),
        },
        "uniform_control": {
            "dimensions_match_every_observation": all(
                row.uniform_dimensions_match for row in rows
            ),
            "incidence_count_mean": fmean(
                item.incidence_count for item in control_basics
            ),
            "actual_density_mean": fmean(item.actual_density for item in control_basics),
            "unique_set_ratio_mean": fmean(
                item.unique_set_count / row.set_count
                for item, row in zip(control_basics, rows, strict=True)
            ),
            "duplicate_set_ratio_mean": fmean(
                item.duplicate_set_ratio for item in control_basics
            ),
            "dominated_set_ratio_mean": fmean(
                item.dominated_set_ratio for item in control_basics
            ),
            "pairwise_overlap_mean_jaccard_mean": _mean_optional(
                [item.pairwise_overlap_mean_jaccard for item in control_basics]
            ),
            "coverage_skew_gini_mean": fmean(
                item.coverage_skew_gini for item in control_basics
            ),
            "coverage_head_10pct_ratio_mean": fmean(
                item.coverage_head_10pct_ratio for item in control_supplementary
            ),
        },
    }


def _audit_scan(
    *,
    config: ExperimentConfig,
    scan_name: str,
    cases: Sequence[CaseConfig],
    observations_by_case: Mapping[str, Sequence[tuple[int, MaximumCoverageInstance]]],
    incidence_relative_tolerance: float,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    family = cases[0].family
    varied = _varied_parameters(cases)
    supported = [name for name in varied if (family, name) in _AUDIT_SPECS]
    if len(supported) != 1:
        return None, {
            "configuration": config.name,
            "scan": scan_name,
            "family": family,
            "reason": "scan must vary exactly one registered stressor parameter",
            "varied_parameters": list(varied),
        }
    intensity = supported[0]
    spec = _AUDIT_SPECS[(family, intensity)]
    rows: list[_Observation] = []
    for case in cases:
        raw_level = case.parameters[intensity]
        if isinstance(raw_level, bool) or not isinstance(raw_level, (int, float)):
            raise ValueError(f"audit level {intensity!r} must be numeric")
        for repetition, instance in observations_by_case[case.case_id]:
            basic = analyze_instance(instance)
            supplementary = analyze_stressor_structure(instance)
            control = _uniform_control(instance, basic, repetition)
            control_basic = analyze_instance(control)
            control_supplementary = analyze_stressor_structure(control)
            bait_first: bool | None = None
            certificate_verified: bool | None = None
            if family == "adversarial":
                bait_first = greedy(instance).selected[0] == 0
                certificate_verified = known_optimum_certificate(instance) is not None
            rows.append(
                _Observation(
                    repetition=repetition,
                    level=raw_level,
                    target_value=spec.target(instance, basic, supplementary),
                    basic=basic,
                    supplementary=supplementary,
                    universe_size=instance.universe_size,
                    set_count=instance.set_count,
                    k=instance.k,
                    uniform_basic=control_basic,
                    uniform_supplementary=control_supplementary,
                    uniform_dimensions_match=(
                        control.universe_size == instance.universe_size
                        and control.set_count == instance.set_count
                        and control.k == instance.k
                    ),
                    greedy_selected_bait_first=bait_first,
                    certificate_verified=certificate_verified,
                )
            )

    grouped: dict[int | float, list[_Observation]] = defaultdict(list)
    for row in rows:
        grouped[row.level].append(row)
    level_summaries = [
        _level_summary(level, grouped[level]) for level in sorted(grouped)
    ]
    target_means: list[float] = []
    incidence_means: list[float] = []
    control_incidence_relative_errors: list[float] = []
    for summary in level_summaries:
        target_mean = summary["target_mean"]
        metrics = summary["metrics"]
        control_summary = summary["uniform_control"]
        if (
            isinstance(target_mean, bool)
            or not isinstance(target_mean, (int, float))
            or not isinstance(metrics, Mapping)
            or not isinstance(control_summary, Mapping)
        ):
            raise TypeError("internal stressor level summary has invalid mappings")
        target_means.append(float(target_mean))
        incidence = metrics["incidence_count_mean"]
        control_incidence = control_summary["incidence_count_mean"]
        if (
            isinstance(incidence, bool)
            or not isinstance(incidence, (int, float))
            or isinstance(control_incidence, bool)
            or not isinstance(control_incidence, (int, float))
        ):
            raise TypeError("internal stressor incidence summary is not numeric")
        numeric_incidence = float(incidence)
        incidence_means.append(numeric_incidence)
        control_incidence_relative_errors.append(
            abs(float(control_incidence) - numeric_incidence) / numeric_incidence
        )
    incidence_relative_range = _relative_range(incidence_means)
    maximum_control_incidence_error = max(control_incidence_relative_errors)
    target_monotonic = _monotonic(target_means, spec.expected_direction)
    adversarial_checks: dict[str, object] | None = None
    if family == "adversarial":
        bait_values = [row.greedy_selected_bait_first for row in rows]
        certificate_values = [row.certificate_verified for row in rows]
        adversarial_checks = {
            "bait_selected_first_every_observation": all(
                value is True for value in bait_values
            ),
            "certificate_verified_every_observation": all(
                value is True for value in certificate_values
            ),
        }

    exact_dimensions = {
        "universe_size": len({row.universe_size for row in rows}) == 1,
        "set_count": len({row.set_count for row in rows}) == 1,
        "k": len({row.k for row in rows}) == 1,
    }
    assessable = target_monotonic is not None
    passes = (
        assessable
        and target_monotonic is True
        and all(exact_dimensions.values())
        and incidence_relative_range <= incidence_relative_tolerance
        and all(row.uniform_dimensions_match for row in rows)
        and (
            adversarial_checks is None
            or all(value is True for value in adversarial_checks.values())
        )
    )
    return {
        "configuration": config.name,
        "scan": scan_name,
        "family": family,
        "intensity_parameter": spec.intensity_parameter,
        "target_metric": spec.target_metric,
        "expected_direction": spec.expected_direction,
        "target_monotonic": target_monotonic,
        "assessment": "pass" if passes else "descriptive" if not assessable else "fail",
        "confound_controls": {
            **exact_dimensions,
            "incidence_level_mean_relative_range": incidence_relative_range,
            "incidence_level_mean_stable": (
                incidence_relative_range <= incidence_relative_tolerance
            ),
            "uniform_control_dimensions_match": all(
                row.uniform_dimensions_match for row in rows
            ),
            "uniform_control_maximum_incidence_relative_error": (
                maximum_control_incidence_error
            ),
        },
        "measured_metric_level_mean_ranges": _metric_level_ranges(level_summaries),
        "adversarial_checks": adversarial_checks,
        "levels": level_summaries,
    }, None


def audit_stressor_configs(
    configs: Sequence[ExperimentConfig],
    *,
    incidence_relative_tolerance: float = DEFAULT_INCIDENCE_RELATIVE_TOLERANCE,
) -> dict[str, object]:
    """Audit stressor scans from one or more benchmark configurations."""

    if (
        isinstance(incidence_relative_tolerance, bool)
        or not isinstance(incidence_relative_tolerance, (int, float))
        or not math.isfinite(incidence_relative_tolerance)
        or incidence_relative_tolerance < 0
    ):
        raise ValueError("incidence_relative_tolerance must be finite and non-negative")
    scans: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for config in configs:
        case_by_id = {case.case_id: case for case in config.cases}
        observations_by_case: dict[
            str, list[tuple[int, MaximumCoverageInstance]]
        ] = defaultdict(list)
        for planned in _instances_for_config(config):
            observations_by_case[planned.case_id].append(
                (planned.repetition, planned.instance)
            )
        grouped_cases: dict[tuple[str, str], list[CaseConfig]] = defaultdict(list)
        for case in config.cases:
            grouped_cases[(case.name, case.family)].append(case_by_id[case.case_id])
        for (scan_name, family), cases in grouped_cases.items():
            if family == "uniform" or len(cases) < 2:
                continue
            scan, reason = _audit_scan(
                config=config,
                scan_name=scan_name,
                cases=cases,
                observations_by_case=observations_by_case,
                incidence_relative_tolerance=float(incidence_relative_tolerance),
            )
            if scan is not None:
                scans.append(scan)
            if reason is not None:
                skipped.append(reason)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "incidence_level_mean_relative_tolerance": float(
            incidence_relative_tolerance
        ),
        "uniform_control_policy": (
            "same realized universe_size, set_count, k, and matched treatment density"
        ),
        "scans": scans,
        "skipped_scans": skipped,
    }


def stressor_audit_has_failures(report: Mapping[str, object]) -> bool:
    """Return whether a report contains a failed scan or a skipped scan."""

    raw_scans = report.get("scans")
    if not isinstance(raw_scans, list):
        raise ValueError("audit report scans must be a list")
    failed = any(
        isinstance(scan, Mapping) and scan.get("assessment") == "fail"
        for scan in raw_scans
    )
    raw_skipped = report.get("skipped_scans")
    if not isinstance(raw_skipped, list):
        raise ValueError("audit report skipped_scans must be a list")
    return failed or bool(raw_skipped)


def stressor_metrics_dict(metrics: StressorStructureMetrics) -> dict[str, object]:
    """Return the stable JSON-ready field mapping for one supplementary record."""

    return asdict(metrics)
