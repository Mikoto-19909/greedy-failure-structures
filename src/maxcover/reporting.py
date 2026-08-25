"""Dependency-free Markdown and SVG reporting."""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from pathlib import Path

from .algorithms import ALGORITHMS
from .config import ExperimentConfig
from .contracts import (
    AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT,
    BranchAndBoundNodeReductionRecord,
    CensoredRuntimeRecord,
    ConfidenceIntervalRecord,
    DescriptiveStatisticsRecord,
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
    GapClusteringAssociationRecord,
    GreedyFailureRecord,
    HeuristicExactRuntimeRatioRecord,
    InstanceRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    QualityRuntimeParetoRecord,
    RuntimeKAssociationRecord,
    RuntimeSetCountAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
    RunRecord,
)


COLORS = {
    "brute_force": "#6b7280",
    "branch_and_bound": "#7c3aed",
    "branch_and_bound_enhanced": "#2563eb",
    "cp_sat_oracle": "#4f46e5",
    "greedy": "#dc2626",
    "local_search": "#059669",
    "multi_start_local_search": "#0891b2",
    "randomized_greedy": "#d97706",
}


def _automatic_conclusion_status(record: ConfidenceIntervalRecord) -> str:
    """Return the operational eligibility state for an automatic metric claim."""

    if record.sample_count < AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT:
        return "withheld_insufficient_samples"
    if record.interval_status != "estimable":
        return "withheld_unestimable_interval"
    return "eligible"


def _headline_lines(
    config: ExperimentConfig,
    statistics: Sequence[DescriptiveStatisticsRecord],
    instances: Sequence[InstanceRecord],
    confidence_interval_statistics: Sequence[ConfidenceIntervalRecord],
    local_search_recovery_statistics: Sequence[LocalSearchRecoveryRecord] = (),
    censored_runtime_statistics: Sequence[CensoredRuntimeRecord] = (),
) -> list[str]:
    """Build guarded automatic headlines from canonical instance-level rows."""

    interval_by_group = {
        (
            record.config_hash,
            record.case_id,
            record.family,
            record.algorithm_id,
            record.algorithm,
            record.metric,
        ): record
        for record in confidence_interval_statistics
    }
    greedy_gap_groups = [
        row
        for row in statistics
        if row.algorithm == "greedy"
        and row.metric == "optimality_gap"
        and row.mean is not None
    ]
    eligible_gaps: list[
        tuple[DescriptiveStatisticsRecord, ConfidenceIntervalRecord]
    ] = []
    for row in greedy_gap_groups:
        interval = interval_by_group.get(
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
                row.metric,
            )
        )
        if interval is not None and _automatic_conclusion_status(interval) == "eligible":
            eligible_gaps.append((row, interval))

    case_instances: dict[str, list[InstanceRecord]] = {}
    for record in instances:
        case_instances.setdefault(record.case_id, []).append(record)

    def is_classified_adversarial(row: DescriptiveStatisticsRecord) -> bool:
        records = case_instances.get(row.case_id, ())
        return bool(records) and all(
            record.instance_origin == "constructed" and record.is_adversarial
            for record in records
        )

    def is_outside_constructed(row: DescriptiveStatisticsRecord) -> bool:
        records = case_instances.get(row.case_id, ())
        return bool(records) and all(
            record.instance_origin != "constructed" for record in records
        )

    def largest(
        records: Sequence[
            tuple[DescriptiveStatisticsRecord, ConfidenceIntervalRecord]
        ],
    ) -> tuple[DescriptiveStatisticsRecord, ConfidenceIntervalRecord] | None:
        return max(
            records,
            key=lambda item: (
                item[0].mean if item[0].mean is not None else -1.0,
                item[0].case_id,
                item[0].algorithm_id,
            ),
            default=None,
        )

    lines: list[str] = []
    if not greedy_gap_groups:
        lines.append(
            "- No completed exact reference was available, so greedy gaps are unknown."
        )
    elif not eligible_gaps:
        lines.append(
            "- Greedy-gap headline withheld: "
            f"0/{len(greedy_gap_groups)} Case/variant groups meet the automatic-"
            "conclusion gate (requires at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent instance "
            "seeds and an estimable 95% CI)."
        )
    else:
        worst = largest(eligible_gaps)
        assert worst is not None
        row, interval = worst
        assert row.mean is not None
        lines.append(
            "- Largest eligible mean greedy gap: "
            f"**{100 * row.mean:.2f}%** on `{row.case_id}` / "
            f"`{row.algorithm_id}` (n=`{interval.sample_count}`)."
        )

    worst_adversarial = largest(
        [item for item in eligible_gaps if is_classified_adversarial(item[0])]
    )
    if worst_adversarial is not None:
        row, interval = worst_adversarial
        assert row.mean is not None
        lines.append(
            "- Largest eligible mean gap on classified adversarial constructions: "
            f"**{100 * row.mean:.2f}%** on `{row.case_id}` / "
            f"`{row.algorithm_id}` (n=`{interval.sample_count}`)."
        )

    worst_non_constructed = largest(
        [item for item in eligible_gaps if is_outside_constructed(item[0])]
    )
    if worst_non_constructed is not None:
        row, interval = worst_non_constructed
        assert row.mean is not None
        lines.append(
            "- Largest eligible mean gap outside constructed instance families: "
            f"**{100 * row.mean:.2f}%** on `{row.case_id}` / "
            f"`{row.algorithm_id}` (n=`{interval.sample_count}`)."
        )

    exact_algorithm_ids = {
        algorithm.algorithm_id
        for algorithm in config.algorithms
        if ALGORITHMS[algorithm.name].exact
    }
    exact_groups = [
        row
        for row in statistics
        if row.metric == "coverage" and row.algorithm_id in exact_algorithm_ids
    ]
    exact_timeouts = sum(row.timeout_count for row in exact_groups)
    exact_runs = sum(row.run_count for row in exact_groups)

    canonical_recovery = [
        LocalSearchRecoveryRecord.from_csv_row(record.to_csv_row())
        for record in local_search_recovery_statistics
    ]
    eligible_recovery = [
        record
        for record in canonical_recovery
        if record.eligible_pair_count > 0
        and record.mean_gap_recovery_rate is not None
    ]
    recovery_pair_count = sum(
        record.eligible_pair_count for record in eligible_recovery
    )
    if recovery_pair_count:
        recovery_sum = sum(
            record.mean_gap_recovery_rate * record.eligible_pair_count
            for record in eligible_recovery
            if record.mean_gap_recovery_rate is not None
        )
        full_recovery_count = sum(
            record.full_recovery_count for record in eligible_recovery
        )
        lines.append(
            "- Local Search recovered "
            f"**{100 * recovery_sum / recovery_pair_count:.2f}%** of the "
            "recoverable Greedy gap across "
            f"**{recovery_pair_count}** eligible paired instance units in "
            f"**{len(eligible_recovery)}** Case/variant groups; full optimum "
            f"recovery occurred in **{full_recovery_count}/{recovery_pair_count}** "
            "pairs (fixed-corpus descriptive fact)."
        )
    else:
        lines.append(
            "- Local Search gap recovery unavailable: **0** eligible paired "
            "instance units with a completed Greedy failure, completed Local "
            "Search result, and positive normalized exact optimum."
        )

    runtime_by_group = {
        (
            record.config_hash,
            record.case_id,
            record.family,
            record.algorithm_id,
            record.algorithm,
        ): record
        for record in statistics
        if record.metric == "runtime_seconds"
    }
    canonical_censored = [
        CensoredRuntimeRecord.from_csv_row(record.to_csv_row())
        for record in censored_runtime_statistics
        if record.algorithm_id in exact_algorithm_ids
    ]
    exact_runtime_candidates: list[
        tuple[CensoredRuntimeRecord, DescriptiveStatisticsRecord | None]
    ] = []
    for record in canonical_censored:
        runtime = runtime_by_group.get(
            (
                record.config_hash,
                record.case_id,
                record.family,
                record.algorithm_id,
                record.algorithm,
            )
        )
        if record.right_censored_instance_count > 0 or (
            runtime is not None and runtime.mean is not None
        ):
            exact_runtime_candidates.append((record, runtime))

    if exact_runtime_candidates:
        hardest_censored, hardest_runtime = max(
            exact_runtime_candidates,
            key=lambda item: (
                item[0].censoring_rate,
                -1.0
                if item[1] is None or item[1].mean is None
                else item[1].mean,
                item[0].case_id,
                item[0].algorithm_id,
            ),
        )
        completed_mean = (
            "unavailable"
            if hardest_runtime is None or hardest_runtime.mean is None
            else f"{hardest_runtime.mean:.6f} s"
        )
        lines.append(
            "- Operationally hardest observed exact Case/variant: "
            f"`{hardest_censored.case_id}` / "
            f"`{hardest_censored.algorithm_id}` under the fixed rule "
            "“highest instance censoring rate, then highest mean completed "
            f"runtime” (censored instances="
            f"**{hardest_censored.right_censored_instance_count}/"
            f"{hardest_censored.instance_count}**, mean completed runtime="
            f"**{completed_mean}**, errors="
            f"**{hardest_censored.error_run_count}**; machine-specific "
            "fixed-corpus diagnostic, not an intrinsic difficulty ranking)."
        )
    else:
        lines.append(
            "- Operationally hardest exact Case unavailable: no exact variant "
            "has a completed runtime or a right-censored instance."
        )

    lines.extend(
        [
            f"- Exact-method timeouts: **{exact_timeouts}/{exact_runs}** "
            "(factual execution count; not an inferential claim).",
            "- Eligibility is an operational reporting guardrail, not evidence of "
            "significance or population generalizability.",
            "- These are experiment outputs, not general theoretical conclusions.",
        ]
    )
    return lines


def _bar_chart(
    path: Path,
    title: str,
    labels: list[str],
    values: list[float],
    colors: list[str],
    *,
    y_label: str,
    value_format: str = ".3f",
) -> None:
    width, height = 1000, 560
    left, top, right, bottom = 90, 70, 30, 140
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = max(values, default=1.0)
    if max_value <= 0:
        max_value = 1.0
    slot = plot_width / max(1, len(values))
    bar_width = slot * 0.66

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#111827"/>',
    ]

    for tick in range(6):
        fraction = tick / 5
        y = top + plot_height * (1 - fraction)
        value = max_value * fraction
        parts.extend(
            [
                f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb"/>',
                f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="12">{value:{value_format}}</text>',
            ]
        )

    for index, (label, value, color) in enumerate(zip(labels, values, colors)):
        x = left + index * slot + (slot - bar_width) / 2
        bar_height = plot_height * value / max_value
        y = top + plot_height - bar_height
        safe_label = html.escape(label)
        parts.extend(
            [
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="{color}" rx="3"/>',
                f'<text x="{x + bar_width / 2:.2f}" y="{y - 7:.2f}" text-anchor="middle" font-family="Arial" font-size="11">{value:{value_format}}</text>',
                f'<text x="{x + bar_width / 2:.2f}" y="{top + plot_height + 18}" transform="rotate(35 {x + bar_width / 2:.2f} {top + plot_height + 18})" text-anchor="start" font-family="Arial" font-size="11">{safe_label}</text>',
            ]
        )

    parts.append(
        f'<text x="24" y="{top + plot_height / 2}" transform="rotate(-90 24 {top + plot_height / 2})" text-anchor="middle" font-family="Arial" font-size="14">{html.escape(y_label)}</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_gap_chart(
    path: Path, statistics: Sequence[DescriptiveStatisticsRecord]
) -> None:
    usable = [
        row
        for row in statistics
        if row.metric == "optimality_gap" and row.mean is not None
    ]
    labels = [f"{row.case_id} / {row.algorithm_id}" for row in usable]
    values = [
        100 * row.mean
        for row in usable
        if row.mean is not None
    ]
    colors = [COLORS.get(row.algorithm, "#2563eb") for row in usable]
    _bar_chart(
        path,
        "Mean Optimality Gap by Case and Algorithm Variant",
        labels,
        values,
        colors,
        y_label="Mean gap (%)",
        value_format=".2f",
    )


def _write_runtime_chart(
    path: Path, statistics: Sequence[DescriptiveStatisticsRecord]
) -> None:
    usable = [
        row
        for row in statistics
        if row.metric == "runtime_seconds" and row.mean is not None
    ]
    labels = [f"{row.case_id} / {row.algorithm_id}" for row in usable]
    raw_means = [row.mean for row in usable if row.mean is not None]
    # Log10 milliseconds makes very fast and exact methods visible together.
    values = [max(0.0, math.log10(max(value * 1000, 1e-3)) + 3) for value in raw_means]
    colors = [COLORS.get(row.algorithm, "#2563eb") for row in usable]
    _bar_chart(
        path,
        "Mean Completed Runtime by Case and Algorithm Variant (shifted log scale)",
        labels,
        values,
        colors,
        y_label="log10(milliseconds) + 3",
        value_format=".2f",
    )


ChartRow = tuple[str, float | None, str, str]


def _render_horizontal_chart(
    title: str,
    subtitle: str,
    rows: Sequence[ChartRow],
    *,
    axis_maximum: float,
    axis_label: str,
    value_format: str,
    width: int = 1750,
    right: int = 690,
) -> str:
    """Render deterministic horizontal bars with explicit sample diagnostics."""

    left, top, bottom = 340, 100, 55
    row_height = 54
    height = max(360, top + row_height * max(1, len(rows)) + bottom)
    plot_width = width - left - right
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(subtitle)}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(subtitle)}</text>',
    ]
    if not rows:
        parts.extend(
            [
                f'<rect x="{left}" y="{top}" width="{plot_width}" height="120" fill="#f9fafb" stroke="#d1d5db"/>',
                f'<text x="{left + plot_width / 2}" y="{top + 66}" text-anchor="middle" font-family="Arial" font-size="16" fill="#6b7280">No applicable typed records</text>',
                "</svg>",
            ]
        )
        return "\n".join(parts)

    for tick in range(6):
        fraction = tick / 5
        x = left + plot_width * fraction
        value = axis_maximum * fraction
        parts.extend(
            [
                f'<line x1="{x:.2f}" y1="{top - 10}" x2="{x:.2f}" y2="{top + row_height * len(rows)}" stroke="#e5e7eb"/>',
                f'<text x="{x:.2f}" y="{top - 18}" text-anchor="middle" font-family="Arial" font-size="11">{value:{value_format}}</text>',
            ]
        )

    for index, (label, value, color, detail) in enumerate(rows):
        y = top + index * row_height
        parts.extend(
            [
                f'<text x="{left - 12}" y="{y + 16}" text-anchor="end" font-family="Arial" font-size="12">{html.escape(label)}</text>',
                f'<text x="{left + plot_width + 14}" y="{y + 24}" font-family="Arial" font-size="10" fill="#6b7280">{html.escape(detail)}</text>',
            ]
        )
        if value is None:
            parts.append(
                f'<text x="{left + 8}" y="{y + 24}" font-family="Arial" font-size="12" fill="#9ca3af">value unavailable</text>'
            )
            continue
        bounded = min(max(value, 0.0), axis_maximum)
        bar_width = 0.0 if axis_maximum == 0 else plot_width * bounded / axis_maximum
        parts.extend(
            [
                f'<rect x="{left}" y="{y + 7}" width="{bar_width:.2f}" height="24" fill="{color}" rx="3"/>',
                f'<text x="{min(left + bar_width + 7, width - right)}" y="{y + 24}" font-family="Arial" font-size="11">{value:{value_format}}</text>',
            ]
        )
    parts.extend(
        [
            f'<text x="{left + plot_width / 2}" y="{height - 18}" text-anchor="middle" font-family="Arial" font-size="13">{html.escape(axis_label)}</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def _render_gap_by_case_chart(
    statistics: Sequence[DescriptiveStatisticsRecord],
) -> str:
    canonical_statistics = [
        DescriptiveStatisticsRecord.from_csv_row(record.to_csv_row())
        for record in statistics
    ]
    rows: list[ChartRow] = []
    for record in sorted(
        (row for row in canonical_statistics if row.metric == "optimality_gap"),
        key=lambda row: (row.family, row.case_id, row.algorithm_id, row.algorithm),
    ):
        detail = (
            f"n={record.sample_count} {record.repetition_unit}; "
            f"runs={record.run_count}; timeout={record.timeout_count}; "
            f"error={record.error_count}; exact_ref={record.valid_exact_reference_count}"
        )
        rows.append(
            (
                f"{record.family} / {record.case_id} / {record.algorithm_id}",
                None if record.mean is None else 100 * record.mean,
                COLORS.get(record.algorithm, "#2563eb"),
                detail,
            )
        )
    return _render_horizontal_chart(
        "Mean Relative Optimality Gap by Case and Algorithm Variant",
        "source=descriptive_statistics.csv; unit=instance_seed; descriptive fixed-corpus evidence",
        rows,
        axis_maximum=100.0,
        axis_label="Mean relative optimality gap (%)",
        value_format=".2f",
    )


def _association_chart_rows(
    density: Sequence[GapDensityAssociationRecord],
    overlap: Sequence[GapOverlapAssociationRecord],
    clustering: Sequence[GapClusteringAssociationRecord],
) -> list[ChartRow]:
    canonical_density = [
        GapDensityAssociationRecord.from_csv_row(record.to_csv_row())
        for record in density
    ]
    canonical_overlap = [
        GapOverlapAssociationRecord.from_csv_row(record.to_csv_row())
        for record in overlap
    ]
    canonical_clustering = [
        GapClusteringAssociationRecord.from_csv_row(record.to_csv_row())
        for record in clustering
    ]
    rows: list[ChartRow] = []
    for predictor, records in (
        ("density", canonical_density),
        ("overlap", canonical_overlap),
        ("clustering", canonical_clustering),
    ):
        for record in sorted(
            records,
            key=lambda row: (row.family, row.algorithm_id, row.algorithm),
        ):
            if isinstance(record, GapClusteringAssociationRecord):
                count = record.eligible_block_count
                unit = "coupling_seed_block"
                exclusions = (
                    f"incomplete={record.incomplete_block_count}; "
                    f"timeout={record.timeout_count}; error={record.error_count}"
                )
            else:
                count = record.eligible_instance_count
                unit = record.repetition_unit
                exclusions = (
                    f"timeout={record.timeout_count}; error={record.error_count}; "
                    f"unusable={record.unusable_result_count}"
                )
                if isinstance(record, GapOverlapAssociationRecord):
                    exclusions += (
                        f"; missing_predictor={record.missing_overlap_predictor_count}"
                    )
            slope = "blank" if record.ols_slope is None else f"{record.ols_slope:.6f}"
            intercept = (
                "blank"
                if record.ols_intercept is None
                else f"{record.ols_intercept:.6f}"
            )
            detail = (
                f"n={count} {unit}; status={record.association_status}; "
                f"OLS slope={slope}; intercept={intercept}; {exclusions}"
            )
            rows.append(
                (
                    f"{predictor} / {record.family} / {record.algorithm_id}",
                    record.pearson_correlation,
                    COLORS.get(record.algorithm, "#2563eb"),
                    detail,
                )
            )
    return rows


def _render_gap_structural_association_chart(
    density: Sequence[GapDensityAssociationRecord],
    overlap: Sequence[GapOverlapAssociationRecord],
    clustering: Sequence[GapClusteringAssociationRecord],
) -> str:
    rows = _association_chart_rows(density, overlap, clustering)
    title = "Gap versus Structural Parameter Associations"
    subtitle = (
        "sources=gap_*_association_statistics.csv; Pearson r; descriptive, non-causal evidence"
    )
    width = 1800
    left, right, top, bottom = 380, 700, 100, 55
    row_height = 54
    height = max(360, top + row_height * max(1, len(rows)) + bottom)
    plot_width = width - left - right
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(subtitle)}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(subtitle)}</text>',
    ]
    if not rows:
        parts.extend(
            [
                f'<rect x="{left}" y="{top}" width="{plot_width}" height="120" fill="#f9fafb" stroke="#d1d5db"/>',
                f'<text x="{left + plot_width / 2}" y="{top + 66}" text-anchor="middle" font-family="Arial" font-size="16" fill="#6b7280">No applicable typed association records</text>',
                "</svg>",
            ]
        )
        return "\n".join(parts)

    for tick in range(5):
        value = -1.0 + tick * 0.5
        x = left + (value + 1.0) * plot_width / 2
        parts.extend(
            [
                f'<line x1="{x:.2f}" y1="{top - 10}" x2="{x:.2f}" y2="{top + row_height * len(rows)}" stroke="{("#9ca3af" if value == 0 else "#e5e7eb")}"/>',
                f'<text x="{x:.2f}" y="{top - 18}" text-anchor="middle" font-family="Arial" font-size="11">{value:.1f}</text>',
            ]
        )
    for index, (label, value, color, detail) in enumerate(rows):
        y = top + index * row_height
        parts.extend(
            [
                f'<text x="{left - 12}" y="{y + 16}" text-anchor="end" font-family="Arial" font-size="12">{html.escape(label)}</text>',
                f'<text x="{left + plot_width + 14}" y="{y + 24}" font-family="Arial" font-size="10" fill="#6b7280">{html.escape(detail)}</text>',
            ]
        )
        if value is None:
            parts.append(
                f'<text x="{left + plot_width / 2 + 8}" y="{y + 24}" font-family="Arial" font-size="11" fill="#9ca3af">r unavailable</text>'
            )
        else:
            x = left + (min(max(value, -1.0), 1.0) + 1.0) * plot_width / 2
            parts.extend(
                [
                    f'<circle cx="{x:.2f}" cy="{y + 21}" r="7" fill="{color}"/>',
                    f'<text x="{x + 10:.2f}" y="{y + 25}" font-family="Arial" font-size="11">r={value:.3f}</text>',
                ]
            )
    parts.extend(
        [
            f'<text x="{left + plot_width / 2}" y="{height - 18}" text-anchor="middle" font-family="Arial" font-size="13">Pearson correlation</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def _render_signed_coefficient_chart(
    title: str,
    subtitle: str,
    facets: Sequence[tuple[str, str, Sequence[ChartRow]]],
) -> str:
    """Render signed, unit-bearing coefficients on one scale per predictor."""

    width = 2200
    left, right, top, bottom = 390, 1090, 100, 55
    row_height = 54
    facet_header_height = 48
    content_height = sum(
        facet_header_height + row_height * max(1, len(rows))
        for _, _, rows in facets
    )
    height = max(360, top + content_height + bottom)
    plot_width = width - left - right
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(subtitle)}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(subtitle)}</text>',
    ]
    if not facets:
        parts.extend(
            [
                f'<rect x="{left}" y="{top}" width="{plot_width}" height="120" fill="#f9fafb" stroke="#d1d5db"/>',
                f'<text x="{left + plot_width / 2}" y="{top + 66}" text-anchor="middle" font-family="Arial" font-size="16" fill="#6b7280">No applicable typed association records</text>',
                "</svg>",
            ]
        )
        return "\n".join(parts)

    facet_top = top
    for facet_name, axis_label, rows in facets:
        row_count = max(1, len(rows))
        plot_top = facet_top + facet_header_height
        maximum = max(
            (abs(value) for _, value, _, _ in rows if value is not None),
            default=1.0,
        )
        if maximum <= 0:
            maximum = 1.0
        parts.append(
            f'<text x="{left}" y="{facet_top + 22}" font-family="Arial" font-size="15" font-weight="bold">{html.escape(facet_name)}; {html.escape(axis_label)}</text>'
        )
        for tick in range(5):
            value = -maximum + tick * maximum / 2
            x = left + tick * plot_width / 4
            parts.extend(
                [
                    f'<line x1="{x:.2f}" y1="{plot_top - 10}" x2="{x:.2f}" y2="{plot_top + row_height * row_count}" stroke="{("#9ca3af" if tick == 2 else "#e5e7eb")}"/>',
                    f'<text x="{x:.2f}" y="{plot_top - 18}" text-anchor="middle" font-family="Arial" font-size="10">{value:.6g}</text>',
                ]
            )
        if not rows:
            parts.append(
                f'<text x="{left + plot_width / 2}" y="{plot_top + 28}" text-anchor="middle" font-family="Arial" font-size="14" fill="#6b7280">No applicable typed records for this predictor</text>'
            )
        for index, (label, value, color, detail) in enumerate(rows):
            y = plot_top + index * row_height
            parts.extend(
                [
                    f'<text x="{left - 12}" y="{y + 16}" text-anchor="end" font-family="Arial" font-size="12">{html.escape(label)}</text>',
                    f'<text x="{left + plot_width + 14}" y="{y + 24}" font-family="Arial" font-size="10" fill="#6b7280">{html.escape(detail)}</text>',
                ]
            )
            if value is None:
                parts.append(
                    f'<text x="{left + plot_width / 2 + 8}" y="{y + 24}" font-family="Arial" font-size="11" fill="#9ca3af">slope unavailable</text>'
                )
                continue
            x = left + (value + maximum) * plot_width / (2 * maximum)
            parts.extend(
                [
                    f'<circle cx="{x:.2f}" cy="{y + 21}" r="7" fill="{color}"/>',
                    f'<text x="{x + 10:.2f}" y="{y + 25}" font-family="Arial" font-size="11">slope={value:.10f}</text>',
                ]
            )
        facet_top = plot_top + row_height * row_count
    parts.extend(
        [
            f'<text x="{left + plot_width / 2}" y="{height - 18}" text-anchor="middle" font-family="Arial" font-size="13">Each predictor uses its own symmetric linear scale; zero is centered</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def _render_runtime_scaling_chart(
    set_count_records: Sequence[RuntimeSetCountAssociationRecord],
    k_records: Sequence[RuntimeKAssociationRecord],
) -> str:
    """Render completed-runtime OLS slopes from the two typed associations."""

    canonical_set_count = [
        RuntimeSetCountAssociationRecord.from_csv_row(record.to_csv_row())
        for record in set_count_records
    ]
    canonical_k = [
        RuntimeKAssociationRecord.from_csv_row(record.to_csv_row())
        for record in k_records
    ]

    def rows_for(records: Sequence[object], slope_name: str) -> list[ChartRow]:
        rows: list[ChartRow] = []
        for record in sorted(
            records,
            key=lambda row: (row.family, row.algorithm_id, row.algorithm),
        ):
            pearson = (
                "blank"
                if record.pearson_correlation is None
                else f"{record.pearson_correlation:.6f}"
            )
            mean_runtime = (
                "blank"
                if record.mean_runtime_seconds is None
                else f"{record.mean_runtime_seconds:.10f}s"
            )
            detail = (
                f"n={record.eligible_instance_count} {record.repetition_unit}; "
                f"cases={record.case_count}; status={record.association_status}; "
                f"Pearson={pearson}; mean_runtime={mean_runtime}; "
                f"incomplete_instances={record.incomplete_runtime_instance_count}; "
                f"timeout={record.timeout_count}; error={record.error_count}"
            )
            rows.append(
                (
                    f"{record.family} / {record.algorithm_id}",
                    getattr(record, slope_name),
                    COLORS.get(record.algorithm, "#2563eb"),
                    detail,
                )
            )
        return rows

    facets: list[tuple[str, str, Sequence[ChartRow]]] = []
    if canonical_set_count:
        facets.append(
            (
                "predictor=set_count",
                "OLS slope (seconds per set)",
                rows_for(canonical_set_count, "ols_slope_seconds_per_set"),
            )
        )
    if canonical_k:
        facets.append(
            (
                "predictor=k",
                "OLS slope (seconds per budget unit)",
                rows_for(canonical_k, "ols_slope_seconds_per_budget_unit"),
            )
        )
    return _render_signed_coefficient_chart(
        "Completed Runtime Scaling by Structural Predictor",
        "sources=runtime_set_count_association_statistics.csv + runtime_k_association_statistics.csv; unit=instance_seed; machine-specific descriptive evidence; censored runtime excluded",
        facets,
    )


def _render_node_scaling_chart(
    records: Sequence[SearchNodesDominatedRatioAssociationRecord],
) -> str:
    """Render complete BnB search-node slopes versus dominated-set ratio."""

    canonical_records = [
        SearchNodesDominatedRatioAssociationRecord.from_csv_row(record.to_csv_row())
        for record in records
    ]
    rows: list[ChartRow] = []
    for record in sorted(
        canonical_records,
        key=lambda row: (row.family, row.algorithm_id, row.algorithm),
    ):
        pearson = (
            "blank"
            if record.pearson_correlation is None
            else f"{record.pearson_correlation:.6f}"
        )
        mean_nodes = (
            "blank"
            if record.mean_search_nodes is None
            else f"{record.mean_search_nodes:.10f}"
        )
        detail = (
            f"n={record.eligible_instance_count} {record.repetition_unit}; "
            f"cases={record.case_count}; status={record.association_status}; "
            f"Pearson={pearson}; mean_nodes={mean_nodes}; "
            f"optimal_runs={record.optimal_run_count}/{record.run_count}; "
            f"timeout={record.timeout_count}; error={record.error_count}"
        )
        rows.append(
            (
                f"{record.family} / {record.algorithm_id}",
                record.ols_slope_nodes_per_ratio_unit,
                COLORS.get(record.algorithm, "#2563eb"),
                detail,
            )
        )
    facets = (
        (
            "predictor=dominated_set_ratio",
            "OLS slope (search nodes per ratio unit)",
            rows,
        ),
    ) if rows else ()
    return _render_signed_coefficient_chart(
        "Branch-and-Bound Node Scaling versus Dominated-Set Ratio",
        "source=search_nodes_dominated_ratio_association_statistics.csv; unit=instance_seed; complete optimal unseeded BnB searches only; descriptive fixed-corpus evidence",
        facets,
    )


def _render_timeout_by_case_chart(
    records: Sequence[CensoredRuntimeRecord],
) -> str:
    """Render right-censoring rates without treating censor times as runtimes."""

    canonical_records = [
        CensoredRuntimeRecord.from_csv_row(record.to_csv_row())
        for record in records
    ]
    rows: list[ChartRow] = []
    for record in sorted(
        canonical_records,
        key=lambda row: (row.family, row.case_id, row.algorithm_id, row.algorithm),
    ):
        mean_censor_time = (
            "blank"
            if record.mean_censor_time_seconds is None
            else f"{record.mean_censor_time_seconds:.10f}s"
        )
        detail = (
            f"n={record.instance_count} {record.repetition_unit}; "
            f"status={record.censoring_status}; runs={record.run_count}; "
            f"right_censored={record.right_censored_run_count} runs/"
            f"{record.right_censored_instance_count} instances; "
            f"errors={record.error_run_count} runs/"
            f"{record.error_affected_instance_count} instances; "
            f"fully_censored={record.fully_right_censored_instance_count}; "
            f"censor_samples={record.censoring_sample_count}; "
            f"mean_censor_time={mean_censor_time} (diagnostic only)"
        )
        rows.append(
            (
                f"{record.family} / {record.case_id} / {record.algorithm_id}",
                100 * record.censoring_rate,
                COLORS.get(record.algorithm, "#2563eb"),
                detail,
            )
        )
    return _render_horizontal_chart(
        "Right-Censored Runtime Rate by Case and Algorithm Variant",
        "source=censored_runtime_statistics.csv; unit=instance_seed; censor time is diagnostic only",
        rows,
        axis_maximum=100.0,
        axis_label="Right-censoring rate (%)",
        value_format=".2f",
        width=2100,
        right=1040,
    )


def _render_local_search_recovery_chart(
    records: Sequence[LocalSearchRecoveryRecord],
) -> str:
    canonical_records = [
        LocalSearchRecoveryRecord.from_csv_row(record.to_csv_row())
        for record in records
    ]
    rows: list[ChartRow] = []
    for record in sorted(
        canonical_records,
        key=lambda row: (
            row.family,
            row.case_id,
            row.greedy_algorithm_id,
            row.local_search_algorithm_id,
        ),
    ):
        eligible_rate = (
            "blank"
            if record.eligible_pair_rate is None
            else f"{100 * record.eligible_pair_rate:.2f}%"
        )
        detail = (
            f"n={record.eligible_pair_count} paired {record.repetition_unit}; "
            f"eligible_rate={eligible_rate}; instances={record.instance_count}; "
            f"greedy_failures={record.greedy_failure_count}; "
            f"timeouts={record.greedy_timeout_count + record.local_search_timeout_count}; "
            f"errors={record.greedy_error_count + record.local_search_error_count}"
        )
        rows.append(
            (
                f"{record.family} / {record.case_id} / "
                f"{record.greedy_algorithm_id}->{record.local_search_algorithm_id}",
                (
                    None
                    if record.mean_gap_recovery_rate is None
                    else 100 * record.mean_gap_recovery_rate
                ),
                COLORS.get(record.algorithm, "#059669"),
                detail,
            )
        )
    return _render_horizontal_chart(
        "Local Search Recovery on Greedy-Failure Instances",
        "source=local_search_recovery_statistics.csv; unit=paired instance_seed",
        rows,
        axis_maximum=100.0,
        axis_label="Mean recoverable gap restored (%)",
        value_format=".2f",
    )


def _render_quality_runtime_pareto_chart(
    records: Sequence[QualityRuntimeParetoRecord],
) -> str:
    title = "Quality-Runtime Pareto Frontier by Case"
    subtitle = (
        "source=quality_runtime_pareto_statistics.csv; common instance_seed units; "
        "runtime is machine-specific"
    )
    grouped: dict[tuple[str, str], list[QualityRuntimeParetoRecord]] = {}
    canonical_records = [
        QualityRuntimeParetoRecord.from_csv_row(record.to_csv_row())
        for record in records
    ]
    for record in sorted(
        canonical_records,
        key=lambda row: (row.family, row.case_id, row.algorithm_id, row.algorithm),
    ):
        grouped.setdefault((record.family, record.case_id), []).append(record)
    width = 1500
    left, plot_width, right_start = 100, 780, 930
    top, minimum_panel_height, bottom = 100, 285, 45
    panel_heights = {
        key: max(minimum_panel_height, 50 + 40 * len(group))
        for key, group in grouped.items()
    }
    height = max(390, top + sum(panel_heights.values()) + bottom)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(subtitle)}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(subtitle)}</text>',
    ]
    if not grouped:
        parts.extend(
            [
                f'<rect x="{left}" y="{top}" width="{plot_width}" height="150" fill="#f9fafb" stroke="#d1d5db"/>',
                f'<text x="{left + plot_width / 2}" y="{top + 80}" text-anchor="middle" font-family="Arial" font-size="16" fill="#6b7280">No applicable typed Pareto records</text>',
                "</svg>",
            ]
        )
        return "\n".join(parts)

    panel_top = top
    for (family, case_id), group in grouped.items():
        plot_top = panel_top + 38
        plot_height = 180
        usable = [
            row
            for row in group
            if row.mean_runtime_seconds is not None
            and row.mean_relative_gap is not None
        ]
        max_runtime = max(
            (row.mean_runtime_seconds or 0.0 for row in usable), default=1.0
        )
        max_gap = max((100 * (row.mean_relative_gap or 0.0) for row in usable), default=1.0)
        if max_runtime <= 0:
            max_runtime = 1.0
        if max_gap <= 0:
            max_gap = 1.0
        parts.extend(
            [
                f'<text x="{left}" y="{panel_top + 20}" font-family="Arial" font-size="15" font-weight="bold">{html.escape(family + " / " + case_id)}</text>',
                f'<line x1="{left}" y1="{plot_top}" x2="{left}" y2="{plot_top + plot_height}" stroke="#111827"/>',
                f'<line x1="{left}" y1="{plot_top + plot_height}" x2="{left + plot_width}" y2="{plot_top + plot_height}" stroke="#111827"/>',
                f'<text x="{left}" y="{plot_top + plot_height + 14}" text-anchor="middle" font-family="Arial" font-size="9">0</text>',
                f'<text x="{left + plot_width}" y="{plot_top + plot_height + 14}" text-anchor="middle" font-family="Arial" font-size="9">{max_runtime:.6f}</text>',
                f'<text x="{left - 8}" y="{plot_top + plot_height + 3}" text-anchor="end" font-family="Arial" font-size="9">0</text>',
                f'<text x="{left - 8}" y="{plot_top + 3}" text-anchor="end" font-family="Arial" font-size="9">{max_gap:.3f}</text>',
                f'<text x="{left + plot_width / 2}" y="{plot_top + plot_height + 28}" text-anchor="middle" font-family="Arial" font-size="12">Mean completed runtime (seconds; linear within Case)</text>',
                f'<text x="25" y="{plot_top + plot_height / 2}" transform="rotate(-90 25 {plot_top + plot_height / 2})" text-anchor="middle" font-family="Arial" font-size="12">Mean relative gap (%)</text>',
            ]
        )
        if not usable:
            parts.append(
                f'<text x="{left + plot_width / 2}" y="{plot_top + plot_height / 2}" text-anchor="middle" font-family="Arial" font-size="14" fill="#6b7280">No evaluable common-instance coordinates</text>'
            )
        for row_index, record in enumerate(group):
            gap = (
                "blank"
                if record.mean_relative_gap is None
                else f"{100 * record.mean_relative_gap:.3f}%"
            )
            runtime = (
                "blank"
                if record.mean_runtime_seconds is None
                else f"{record.mean_runtime_seconds:.6f}s"
            )
            detail_y = plot_top + 12 + row_index * 40
            parts.extend(
                [
                    f'<text x="{right_start}" y="{detail_y}" font-family="Arial" font-size="10" fill="#111827">{html.escape(record.algorithm_id)}: n={record.eligible_instance_count} {html.escape(record.repetition_unit)}; status={record.pareto_status}</text>',
                    f'<text x="{right_start}" y="{detail_y + 16}" font-family="Arial" font-size="10" fill="#4b5563">gap={gap}; runtime={runtime}; timeout={record.timeout_count}; error={record.error_count}; no_ref={record.no_exact_reference_count}</text>',
                ]
            )
            if record not in usable:
                continue
            assert record.mean_runtime_seconds is not None
            assert record.mean_relative_gap is not None
            x = left + plot_width * record.mean_runtime_seconds / max_runtime
            y = plot_top + plot_height * (1 - 100 * record.mean_relative_gap / max_gap)
            color = COLORS.get(record.algorithm, "#2563eb")
            stroke_width = 3 if record.pareto_status == "frontier" else 1
            opacity = "1.0" if record.pareto_status == "frontier" else "0.55"
            label_offsets = (-12, 14, -26, 28)
            label_y = min(
                max(y + label_offsets[row_index % len(label_offsets)], plot_top + 10),
                plot_top + plot_height - 6,
            )
            parts.extend(
                [
                    f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7" fill="{color}" stroke="#111827" stroke-width="{stroke_width}" opacity="{opacity}"/>',
                    f'<text x="{x + 9:.2f}" y="{label_y:.2f}" font-family="Arial" font-size="10">{html.escape(record.algorithm_id)}</text>',
                ]
            )
        panel_top += panel_heights[(family, case_id)]
    parts.append("</svg>")
    return "\n".join(parts)


def _write_markdown(
    path: Path,
    config_path: Path,
    config: ExperimentConfig,
    rows: Sequence[RunRecord],
    statistics: Sequence[DescriptiveStatisticsRecord],
    instances: Sequence[InstanceRecord],
    greedy_failure_statistics: Sequence[GreedyFailureRecord],
    local_search_recovery_statistics: Sequence[LocalSearchRecoveryRecord],
    local_search_remaining_gap_statistics: Sequence[
        LocalSearchRemainingGapRecord
    ],
    heuristic_exact_runtime_ratio_statistics: Sequence[
        HeuristicExactRuntimeRatioRecord
    ],
    bnb_node_reduction_statistics: Sequence[
        BranchAndBoundNodeReductionRecord
    ],
    quality_runtime_pareto_statistics: Sequence[
        QualityRuntimeParetoRecord
    ],
    gap_density_association_statistics: Sequence[
        GapDensityAssociationRecord
    ],
    gap_overlap_association_statistics: Sequence[
        GapOverlapAssociationRecord
    ],
    gap_clustering_association_statistics: Sequence[
        GapClusteringAssociationRecord
    ],
    runtime_set_count_association_statistics: Sequence[
        RuntimeSetCountAssociationRecord
    ],
    runtime_k_association_statistics: Sequence[RuntimeKAssociationRecord],
    search_nodes_dominated_ratio_association_statistics: Sequence[
        SearchNodesDominatedRatioAssociationRecord
    ],
    confidence_interval_statistics: Sequence[
        ConfidenceIntervalRecord
    ],
    censored_runtime_statistics: Sequence[CensoredRuntimeRecord],
) -> None:
    lines = [
        f"# Results: {config.name}",
        "",
        "## Reproducibility",
        "",
        f'- Configuration: `{config_path.resolve().as_posix()}`',
        f"- Base seed: `{config.base_seed}`",
        f"- Repetitions per case: `{config.repetitions}`",
        f'- Raw algorithm runs: `{len(rows)}`',
        "- Runtime environment: Python standard library only",
        "",
        "## Headline checks",
        "",
    ]
    lines.extend(
        _headline_lines(
            config,
            statistics,
            instances,
            confidence_interval_statistics,
            local_search_recovery_statistics,
            censored_runtime_statistics,
        )
    )
    lines.extend(
        [
            "",
            "## P5.1 descriptive aggregate",
            "",
            "The independent unit is one generated instance seed. Algorithm seeds are "
            "averaged within that unit. Runtime statistics exclude timeout and error "
            "runs; their rates remain explicit.",
            "",
            "| Case | Family | Variant | Instances | Runs | Mean/median coverage | Mean/P95 gap | Mean completed runtime (s) | Timeout rate | Exact refs |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    grouped_statistics: dict[
        tuple[str, str, str, str], dict[str, DescriptiveStatisticsRecord]
    ] = {}
    for row in statistics:
        grouped_statistics.setdefault(
            (row.case_id, row.family, row.algorithm_id, row.algorithm), {}
        )[row.metric] = row
    for key, metric_rows in sorted(grouped_statistics.items()):
        case_id, family, algorithm_id, _algorithm = key
        coverage = metric_rows["coverage"]
        gap = metric_rows["optimality_gap"]
        runtime = metric_rows["runtime_seconds"]
        coverage_text = (
            "n/a"
            if coverage.mean is None or coverage.median is None
            else f"{coverage.mean:.4f} / {coverage.median:.4f}"
        )
        gap_text = (
            "n/a"
            if gap.mean is None or gap.p95 is None
            else f"{100 * gap.mean:.2f}% / {100 * gap.p95:.2f}%"
        )
        runtime_text = "n/a" if runtime.mean is None else f"{runtime.mean:.6f}"
        lines.append(
            f"| {case_id} | {family} | {algorithm_id} | "
            f"{coverage.instance_count} | {coverage.run_count} | "
            f"{coverage_text} | {gap_text} | {runtime_text} | "
            f"{100 * coverage.timeout_rate:.2f}% | "
            f"{coverage.valid_exact_reference_count}/{coverage.instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.3 95% confidence intervals for instance means",
            "",
            "Each row reuses the canonical P5.1 instance-level samples and "
            "reports a two-sided Student-t interval for the mean. Algorithm "
            "seeds remain nested within each instance. At least two samples "
            "are required; singleton and empty groups retain explicit statuses "
            "with blank interval bounds. Runtime intervals use completed "
            "runtime samples only and do not estimate censored runtimes.",
            "",
            "| Case | Family | Variant | Metric | n | Mean | 95% CI | df | "
            "Status | T/E |",
            "|---|---|---|---|---:|---:|---:|---:|---|---:|",
        ]
    )
    if not confidence_interval_statistics:
        lines.append(
            "| n/a | n/a | no metric groups | n/a | 0 | n/a | n/a | 0 | "
            "no_samples | 0/0 |"
        )
    for record in confidence_interval_statistics:
        mean = "n/a" if record.mean is None else f"{record.mean:.10f}"
        interval = (
            "n/a"
            if record.lower_bound is None or record.upper_bound is None
            else f"[{record.lower_bound:.10f}, {record.upper_bound:.10f}]"
        )
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.algorithm_id} | {record.metric} | "
            f"{record.sample_count} | {mean} | {interval} | "
            f"{record.degrees_of_freedom} | {record.interval_status} | "
            f"{record.timeout_count}/{record.error_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.3 automatic-conclusion eligibility",
            "",
            "Automatic metric headlines require an estimable confidence interval "
            "and at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent instance "
            "seeds. Rows below the threshold remain visible as descriptive "
            "evidence but cannot feed an automatic claim. This fixed threshold "
            "is a reporting guardrail, not a statistical-power guarantee.",
            "",
            "| Case | Family | Variant | Metric | Independent n | Minimum n | "
            "CI status | Automatic conclusion |",
            "|---|---|---|---|---:|---:|---|---|",
        ]
    )
    if not confidence_interval_statistics:
        lines.append(
            "| n/a | n/a | no metric groups | n/a | 0 | "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} | no_samples | "
            "withheld_insufficient_samples |"
        )
    for record in confidence_interval_statistics:
        lines.append(
            f"| {record.case_id} | {record.family} | {record.algorithm_id} | "
            f"{record.metric} | {record.sample_count} | "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} | "
            f"{record.interval_status} | "
            f"{_automatic_conclusion_status(record)} |"
        )
    lines.extend(
        [
            "",
            "## P5.3 censored-runtime diagnostics",
            "",
            "Timeout elapsed times are reported separately as right-censored "
            "runtime observations and are never mixed with completed-runtime "
            "statistics. Algorithm seeds are averaged within each instance; "
            "the table then summarizes those instance-equal censor times. "
            "This diagnostic does not fit a survival curve or infer latent "
            "completion times.",
            "",
            "| Case | Family | Variant | Instances | Runs | Completed runs | "
            "Right-censored runs | Censored instances | Rate | Mean / median "
            "censor time (s) | Range (s) | Fully censored | Error affected | "
            "Status |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---:|---|",
        ]
    )
    if not censored_runtime_statistics:
        lines.append(
            "| n/a | n/a | no executed variants | 0 | 0 | 0 | 0 | 0 | "
            "n/a | n/a | n/a | 0 | 0 | no_runtime_observations |"
        )
    for record in censored_runtime_statistics:
        if record.mean_censor_time_seconds is None:
            center = "n/a"
            time_range = "n/a"
        else:
            assert record.median_censor_time_seconds is not None
            assert record.minimum_censor_time_seconds is not None
            assert record.maximum_censor_time_seconds is not None
            center = (
                f"{record.mean_censor_time_seconds:.10f} / "
                f"{record.median_censor_time_seconds:.10f}"
            )
            time_range = (
                f"{record.minimum_censor_time_seconds:.10f}–"
                f"{record.maximum_censor_time_seconds:.10f}"
            )
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.algorithm_id} | {record.instance_count} | "
            f"{record.run_count} | {record.completed_run_count} | "
            f"{record.right_censored_run_count} | "
            f"{record.right_censored_instance_count} | "
            f"{100 * record.censoring_rate:.2f}% | {center} | "
            f"{time_range} | "
            f"{record.fully_right_censored_instance_count} | "
            f"{record.error_affected_instance_count} | "
            f"{record.censoring_status} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 classical Greedy failure rate",
            "",
            "The rate is conditional on instance units where classical Greedy "
            "completed and a normalized exact reference is available. Timeout, "
            "error, and missing-reference units are excluded from the denominator "
            "and reported separately.",
            "",
            "| Case | Family | Variant | Instances | Completed | Eligible | Failures / denominator | Optimal ties | Failure rate | Timeouts | Errors | No exact ref |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not greedy_failure_statistics:
        lines.append(
            "| n/a | n/a | no classical Greedy configured | 0 | 0 | 0 | "
            "0/0 | 0 | n/a | 0 | 0 | 0 |"
        )
    for record in greedy_failure_statistics:
        failure_rate = (
            "n/a"
            if record.failure_rate is None
            else f"{100 * record.failure_rate:.2f}%"
        )
        lines.append(
            f"| {record.case_id} | {record.family} | {record.algorithm_id} | "
            f"{record.instance_count} | {record.completed_count} | "
            f"{record.eligible_pair_count} | "
            f"{record.failure_count}/{record.eligible_pair_count} | "
            f"{record.optimal_tie_count} | {failure_rate} | "
            f"{record.timeout_count} | {record.error_count} | "
            f"{record.no_exact_reference_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 mean/max relative optimality gap",
            "",
            "All executed algorithm variants are reported separately. Each "
            "instance seed has equal weight: eligible algorithm-seed gaps are "
            "averaged within the instance before mean and maximum are computed "
            "across instances. Timeout incumbents may contribute a quality gap; "
            "errors, missing exact references, and zero optima do not.",
            "",
            "| Case | Family | Variant | Gap samples / instances | Exact refs | Mean gap | Max gap | Timeouts | Errors |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    gap_statistics = sorted(
        (row for row in statistics if row.metric == "optimality_gap"),
        key=lambda row: (
            row.config_hash,
            row.case_id,
            row.family,
            row.algorithm_id,
            row.algorithm,
        ),
    )
    if not gap_statistics:
        lines.append("| n/a | n/a | no algorithm variants | 0/0 | 0/0 | n/a | n/a | 0 | 0 |")
    for record in gap_statistics:
        mean_gap = (
            "n/a" if record.mean is None else f"{100 * record.mean:.2f}%"
        )
        max_gap = (
            "n/a" if record.maximum is None else f"{100 * record.maximum:.2f}%"
        )
        lines.append(
            f"| {record.case_id} | {record.family} | {record.algorithm_id} | "
            f"{record.sample_count}/{record.instance_count} | "
            f"{record.valid_exact_reference_count}/{record.instance_count} | "
            f"{mean_gap} | {max_gap} | {record.timeout_count} | "
            f"{record.error_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 Local Search recovery rate",
            "",
            "The recoverable gap is defined only where classical Greedy "
            "completed below a normalized exact optimum. Paired completed Local "
            "Search runs contribute `(LS - Greedy) / (OPT - Greedy)`; each "
            "instance seed has equal weight. Timeout, error, missing-reference, "
            "and already-optimal Greedy units are excluded from the mean.",
            "",
            "| Case | Family | Greedy variant | Local Search variant | "
            "Greedy failures | Eligible pairs | Mean gap recovery | "
            "Full recoveries | Greedy T/E | Local Search T/E |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not local_search_recovery_statistics:
        lines.append(
            "| n/a | n/a | n/a | no paired classical Greedy and Local Search "
            "variants configured | 0 | 0 | n/a | 0/0 | 0/0 | 0/0 |"
        )
    for record in local_search_recovery_statistics:
        recovery_rate = (
            "n/a"
            if record.mean_gap_recovery_rate is None
            else f"{100 * record.mean_gap_recovery_rate:.2f}%"
        )
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.greedy_algorithm_id} | "
            f"{record.local_search_algorithm_id} | "
            f"{record.greedy_failure_count} | {record.eligible_pair_count} | "
            f"{recovery_rate} | "
            f"{record.full_recovery_count}/{record.eligible_pair_count} | "
            f"{record.greedy_timeout_count}/{record.greedy_error_count} | "
            f"{record.local_search_timeout_count}/"
            f"{record.local_search_error_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 remaining gap after Local Search recovery",
            "",
            "This metric uses the same eligible deterministic Greedy/Local "
            "Search pairs as the recovery rate. For each completed pair where "
            "Greedy is below a normalized exact optimum, the remaining relative "
            "gap is `(OPT - LS) / OPT`; instance seeds have equal weight.",
            "",
            "| Case | Family | Greedy variant | Local Search variant | "
            "Eligible pairs | Mean remaining gap | Max remaining gap | "
            "Zero remaining gap |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    if not local_search_remaining_gap_statistics:
        lines.append(
            "| n/a | n/a | n/a | no paired classical Greedy and Local Search "
            "variants configured | 0 | n/a | n/a | 0/0 |"
        )
    for record in local_search_remaining_gap_statistics:
        mean_gap = (
            "n/a"
            if record.mean_remaining_relative_gap is None
            else f"{100 * record.mean_remaining_relative_gap:.2f}%"
        )
        maximum_gap = (
            "n/a"
            if record.maximum_remaining_relative_gap is None
            else f"{100 * record.maximum_remaining_relative_gap:.2f}%"
        )
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.greedy_algorithm_id} | "
            f"{record.local_search_algorithm_id} | "
            f"{record.eligible_pair_count} | {mean_gap} | {maximum_gap} | "
            f"{record.zero_remaining_gap_count}/"
            f"{record.eligible_pair_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 heuristic/exact runtime ratio",
            "",
            "Each heuristic variant is paired with each exact variant in the "
            "same case. Completed heuristic algorithm-seed runtimes are averaged "
            "within an instance and divided by its positive completed exact "
            "runtime; instance ratios then receive equal weight. Timeout, error, "
            "and zero exact-runtime denominators are excluded and counted.",
            "",
            "| Case | Family | Heuristic variant | Exact variant | Eligible | "
            "Mean | Median | Min | Max | Heuristic T/E | Exact T/E | "
            "Zero exact runtime |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not heuristic_exact_runtime_ratio_statistics:
        lines.append(
            "| n/a | n/a | no heuristic/exact variant pair configured | n/a | "
            "0 | n/a | n/a | n/a | n/a | 0/0 | 0/0 | 0 |"
        )
    for record in heuristic_exact_runtime_ratio_statistics:
        values = (
            record.mean_runtime_ratio,
            record.median_runtime_ratio,
            record.minimum_runtime_ratio,
            record.maximum_runtime_ratio,
        )
        formatted = [
            "n/a" if value is None else f"{value:.4f}x"
            for value in values
        ]
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.heuristic_algorithm_id} | {record.exact_algorithm_id} | "
            f"{record.eligible_pair_count}/{record.instance_count} | "
            f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
            f"{formatted[3]} | {record.heuristic_timeout_count}/"
            f"{record.heuristic_error_count} | {record.exact_timeout_count}/"
            f"{record.exact_error_count} | "
            f"{record.zero_exact_runtime_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 Branch-and-Bound node reduction",
            "",
            "Each baseline Branch-and-Bound variant is paired with each "
            "enhanced Branch-and-Bound variant in the same case. Only pairs "
            "where both searches prove the same optimum and the baseline "
            "visited at least one node contribute "
            "`1 - enhanced_nodes / baseline_nodes`; instance seeds receive "
            "equal weight. Timeout, error, and zero baseline-node units are "
            "excluded and counted. Negative values are retained when the "
            "enhanced search visits more nodes.",
            "",
            "| Case | Family | Baseline variant | Enhanced variant | Eligible | "
            "Mean | Median | Min | Max | Aggregate | Nodes baseline/enhanced | "
            "Baseline T/E | Enhanced T/E | Zero baseline nodes |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not bnb_node_reduction_statistics:
        lines.append(
            "| n/a | n/a | no baseline/enhanced BnB variant pair configured | "
            "n/a | 0 | n/a | n/a | n/a | n/a | n/a | 0/0 | 0/0 | 0/0 | 0 |"
        )
    for record in bnb_node_reduction_statistics:
        values = (
            record.mean_node_reduction,
            record.median_node_reduction,
            record.minimum_node_reduction,
            record.maximum_node_reduction,
            record.aggregate_node_reduction,
        )
        formatted = [
            "n/a" if value is None else f"{100 * value:.2f}%"
            for value in values
        ]
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.baseline_algorithm_id} | "
            f"{record.enhanced_algorithm_id} | "
            f"{record.eligible_pair_count}/{record.instance_count} | "
            f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
            f"{formatted[3]} | {formatted[4]} | "
            f"{record.total_baseline_nodes}/"
            f"{record.total_enhanced_nodes} | "
            f"{record.baseline_timeout_count}/"
            f"{record.baseline_error_count} | "
            f"{record.enhanced_timeout_count}/"
            f"{record.enhanced_error_count} | "
            f"{record.zero_baseline_nodes_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 quality-runtime Pareto frontier",
            "",
            "All executed algorithm variants in a case are compared on a "
            "common fully observed instance set: the normalized exact optimum "
            "must be positive and every planned run of every variant must "
            "complete. Algorithm seeds are averaged within an instance, then "
            "instances receive equal weight. Both mean relative gap and mean "
            "runtime are minimized. A point is dominated only when another "
            "variant is no worse on both axes and strictly better on at least "
            "one; identical points share the frontier.",
            "",
            "| Case | Family | Variant | Eligible | Mean gap | Mean runtime "
            "(s) | Pareto status | Dominated by | T/E | References valid/zero/"
            "missing |",
            "|---|---|---|---:|---:|---:|---|---|---:|---:|",
        ]
    )
    if not quality_runtime_pareto_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0 | n/a | n/a | "
            "not_evaluable | n/a | 0/0 | 0/0/0 |"
        )
    for record in quality_runtime_pareto_statistics:
        gap = (
            "n/a"
            if record.mean_relative_gap is None
            else f"{100 * record.mean_relative_gap:.4f}%"
        )
        runtime = (
            "n/a"
            if record.mean_runtime_seconds is None
            else f"{record.mean_runtime_seconds:.6f}"
        )
        dominators = (
            ", ".join(record.dominated_by_algorithm_ids)
            if record.dominated_by_algorithm_ids
            else "n/a"
        )
        lines.append(
            f"| {record.case_id} | {record.family} | "
            f"{record.algorithm_id} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{gap} | {runtime} | {record.pareto_status} | {dominators} | "
            f"{record.timeout_count}/{record.error_count} | "
            f"{record.valid_exact_reference_count}/"
            f"{record.zero_optimum_count}/"
            f"{record.no_exact_reference_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 gap vs actual-density association",
            "",
            "Rows pool executed Cases only within the same instance family and "
            "algorithm variant. The independent unit is one instance seed; "
            "algorithm-seed gaps are averaged inside that instance. The "
            "predictor is measured `instances.csv.actual_density`, not the "
            "generator target. Pearson correlation and an OLS line are "
            "descriptive only: no p-value, significance, causality, or "
            "cross-family generalization is claimed. This section emits no "
            "automatic numerical headline; fewer than "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent samples "
            "cannot pass the automatic-conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct density | "
            "Mean density | Mean gap | Density SD | Gap SD | Pearson r | "
            "OLS slope | OLS intercept | Status | T/E | References "
            "valid/zero/missing/unusable |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not gap_density_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0 | "
            "0/0/0/0 |"
        )
    for record in gap_density_association_statistics:
        values = (
            record.mean_actual_density,
            record.mean_relative_gap,
            record.density_sample_standard_deviation,
            record.gap_sample_standard_deviation,
            record.pearson_correlation,
            record.ols_slope,
            record.ols_intercept,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {record.family} | {', '.join(record.case_ids)} | "
            f"{record.algorithm_id} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{record.distinct_density_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{record.association_status} | "
            f"{record.timeout_count}/{record.error_count} | "
            f"{record.valid_exact_reference_count}/"
            f"{record.zero_optimum_count}/"
            f"{record.no_exact_reference_count}/"
            f"{record.unusable_result_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 gap vs measured pairwise-overlap association",
            "",
            "Rows pool executed Cases only within the same instance family and "
            "algorithm variant. The independent unit is one instance seed; "
            "algorithm-seed gaps are averaged inside that instance. The "
            "predictor is measured "
            "`instances.csv.pairwise_overlap_mean_jaccard`; null overlap "
            "means no valid Jaccard pair and is excluded and counted, never "
            "filled with zero. Pearson correlation and an OLS line are "
            "descriptive only: no p-value, significance, causality, "
            "clustering equivalence, or cross-family generalization is "
            "claimed. This section emits no automatic numerical headline; "
            "fewer than "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent samples "
            "cannot pass the automatic-conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct overlap | "
            "Mean overlap | Mean gap | Overlap SD | Gap SD | Pearson r | "
            "OLS slope | OLS intercept | Status | T/E | References "
            "valid/zero/missing/unusable/missing predictor |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not gap_overlap_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0 | "
            "0/0/0/0/0 |"
        )
    for record in gap_overlap_association_statistics:
        values = (
            record.mean_pairwise_overlap_jaccard,
            record.mean_relative_gap,
            record.overlap_sample_standard_deviation,
            record.gap_sample_standard_deviation,
            record.pearson_correlation,
            record.ols_slope,
            record.ols_intercept,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {record.family} | {', '.join(record.case_ids)} | "
            f"{record.algorithm_id} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{record.distinct_overlap_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{record.association_status} | "
            f"{record.timeout_count}/{record.error_count} | "
            f"{record.valid_exact_reference_count}/"
            f"{record.zero_optimum_count}/"
            f"{record.no_exact_reference_count}/"
            f"{record.unusable_result_count}/"
            f"{record.missing_overlap_predictor_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 gap vs mixed-cluster bridge intensity",
            "",
            "Only the P4 `mixed_cluster_bridges` paired scan is eligible. "
            "The predictor is measured `realized_bridge_fraction` from "
            "typed instance parameters; higher values mean more "
            "cross-cluster mixing, not stronger clustering. "
            "`coupling_pair_id`/`coupling_seed` define independent blocks. "
            "A block contributes only when every Case level has a usable "
            "gap, after which each level mean uses the same blocks and the "
            "association is fitted across level-mean coordinates. No "
            "p-value, significance, causal effect, mixed-effects inference, "
            "or population generalization is claimed. This section emits "
            "no automatic numerical headline; the conclusion guardrail "
            "uses eligible blocks, not levels or instance points, and "
            "requires at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} blocks.",
            "",
            "| Variant | Cases/levels | Blocks eligible/total | Instances "
            "eligible/total | Mean bridge fraction | Mean level gap | "
            "Bridge SD | Level-gap SD | Pearson r | OLS slope | "
            "OLS intercept | Status | T/E | References "
            "valid/zero/missing/unusable/usable |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
            "---:|---:|",
        ]
    )
    if not gap_clustering_association_statistics:
        lines.append(
            "| no mixed-cluster variant executed | 0/0 | 0/0 | 0/0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_complete_blocks | "
            "0/0 | 0/0/0/0/0 |"
        )
    for record in gap_clustering_association_statistics:
        values = (
            record.mean_realized_bridge_fraction,
            record.mean_level_relative_gap,
            record.bridge_fraction_sample_standard_deviation,
            record.gap_level_mean_sample_standard_deviation,
            record.pearson_correlation,
            record.ols_slope,
            record.ols_intercept,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {record.algorithm_id} | "
            f"{record.case_count}/{record.distinct_clustering_level_count} | "
            f"{record.eligible_block_count}/"
            f"{record.independent_block_count} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
            f"{formatted[3]} | {formatted[4]} | {formatted[5]} | "
            f"{formatted[6]} | {record.association_status} | "
            f"{record.timeout_count}/{record.error_count} | "
            f"{record.valid_exact_reference_count}/"
            f"{record.zero_optimum_count}/"
            f"{record.no_exact_reference_count}/"
            f"{record.unusable_result_count}/"
            f"{record.usable_gap_instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 completed runtime vs candidate-set count",
            "",
            "Rows pool executed Cases only within the same instance family "
            "and algorithm variant. The predictor is typed "
            "`instances.csv.set_count`. An instance contributes only when "
            "all planned algorithm-seed runs complete as optimal or "
            "feasible; their runtimes are averaged inside that instance, "
            "then instance seeds are equally weighted. Timeout/error makes "
            "the whole instance ineligible, and timeout elapsed time remains "
            "separate in `censored_runtime_statistics.csv`. Pearson "
            "correlation and OLS seconds-per-set are descriptive only: no "
            "significance, causality, asymptotic complexity, nonlinear "
            "scaling, cross-family, or cross-machine claim is made. This "
            "section emits no automatic numerical headline; at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} eligible instance "
            "seeds would be required by the conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct set count | "
            "Mean set count | Mean runtime (s) | Set-count SD | Runtime SD "
            "(s) | Pearson r | OLS slope (s/set) | OLS intercept (s) | "
            "Status | Completed/T/E | Incomplete instances |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not runtime_set_count_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0/0 | 0 |"
        )
    for record in runtime_set_count_association_statistics:
        values = (
            record.mean_set_count,
            record.mean_runtime_seconds,
            record.set_count_sample_standard_deviation,
            record.runtime_sample_standard_deviation_seconds,
            record.pearson_correlation,
            record.ols_slope_seconds_per_set,
            record.ols_intercept_seconds,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {record.family} | {', '.join(record.case_ids)} | "
            f"{record.algorithm_id} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{record.distinct_set_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{record.association_status} | "
            f"{record.completed_run_count}/{record.timeout_count}/"
            f"{record.error_count} | "
            f"{record.incomplete_runtime_instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 completed runtime vs selection budget k",
            "",
            "Rows pool executed Cases only within the same instance family "
            "and algorithm variant. The predictor is typed `instances.csv.k`, "
            "not selected-set count or an algorithm option. An instance "
            "contributes only when all planned algorithm-seed runs complete "
            "as optimal or feasible; their runtimes are averaged inside that "
            "instance, then instance seeds are equally weighted. Timeout/error "
            "makes the whole instance ineligible, and timeout elapsed time "
            "remains separate in `censored_runtime_statistics.csv`. Pearson "
            "correlation and OLS seconds-per-budget-unit are descriptive only: "
            "no significance, causality, asymptotic complexity, nonlinear "
            "scaling, quality stability, cross-family, or cross-machine claim "
            "is made. This section emits no automatic numerical headline; at "
            "least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} eligible instance "
            "seeds would be required by the conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct k | Mean k | "
            "Mean runtime (s) | k SD | Runtime SD (s) | Pearson r | OLS slope "
            "(s/budget unit) | OLS intercept (s) | Status | Completed/T/E | "
            "Incomplete instances |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not runtime_k_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0/0 | 0 |"
        )
    for record in runtime_k_association_statistics:
        values = (
            record.mean_k,
            record.mean_runtime_seconds,
            record.k_sample_standard_deviation,
            record.runtime_sample_standard_deviation_seconds,
            record.pearson_correlation,
            record.ols_slope_seconds_per_budget_unit,
            record.ols_intercept_seconds,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {record.family} | {', '.join(record.case_ids)} | "
            f"{record.algorithm_id} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{record.distinct_k_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{record.association_status} | "
            f"{record.completed_run_count}/{record.timeout_count}/"
            f"{record.error_count} | "
            f"{record.incomplete_runtime_instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 completed BnB search nodes vs dominated-set ratio",
            "",
            "Rows include only Branch-and-Bound variants and pool executed "
            "Cases only within the same instance family and algorithm variant. "
            "The predictor is typed `instances.csv.dominated_set_ratio` "
            "(`dominated_set_count / set_count`), not the unique-set ratio or "
            "preprocessed set count. Only optimal runs contribute complete "
            "`nodes_or_iterations`; timeout partial searches and errors are "
            "excluded and counted. Instance seeds are equally weighted. "
            "Pearson correlation and OLS nodes-per-ratio-unit are descriptive "
            "only: no significance, causality, asymptotic complexity, "
            "cross-family, cross-machine, or algorithm-ranking claim is made. "
            "This section emits no automatic numerical headline; at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} eligible instance "
            "seeds would be required by the conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct ratios | Mean "
            "dominated ratio | Mean nodes | Ratio SD | Node SD | Pearson r | "
            "OLS slope (nodes/ratio unit) | OLS intercept (nodes) | Status | "
            "Optimal/T/E |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|",
        ]
    )
    if not search_nodes_dominated_ratio_association_statistics:
        lines.append(
            "| n/a | n/a | no BnB variant executed | 0/0 | 0 | n/a | n/a | "
            "n/a | n/a | n/a | n/a | n/a | no_samples | 0/0/0 |"
        )
    for record in search_nodes_dominated_ratio_association_statistics:
        values = (
            record.mean_dominated_set_ratio,
            record.mean_search_nodes,
            record.dominated_ratio_sample_standard_deviation,
            record.search_nodes_sample_standard_deviation,
            record.pearson_correlation,
            record.ols_slope_nodes_per_ratio_unit,
            record.ols_intercept_nodes,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {record.family} | {', '.join(record.case_ids)} | "
            f"{record.algorithm_id} | "
            f"{record.eligible_instance_count}/{record.instance_count} | "
            f"{record.distinct_dominated_ratio_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{record.association_status} | "
            f"{record.optimal_run_count}/{record.timeout_count}/"
            f"{record.error_count} |"
        )
    lines.extend(
        [
            "",
            "## Next analysis questions",
            "",
            "1. Does greedy degradation persist across seeds and larger instances?",
            "2. Which controlled parameter best predicts the observed gap?",
            "3. When does local search recover the greedy loss, and at what runtime cost?",
            "4. Which structures cause branch-and-bound runtime transitions?",
            "5. Are conclusions stable when the set budget `k` changes?",
            "",
            "See `raw_results.csv` before making any external claim with a numerical result.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report_artifacts(
    output_dir: Path,
    config_path: Path,
    config: ExperimentConfig,
    rows: Sequence[RunRecord],
    statistics: Sequence[DescriptiveStatisticsRecord],
    instances: Sequence[InstanceRecord] = (),
    greedy_failure_statistics: Sequence[GreedyFailureRecord] = (),
    local_search_recovery_statistics: Sequence[LocalSearchRecoveryRecord] = (),
    local_search_remaining_gap_statistics: Sequence[
        LocalSearchRemainingGapRecord
    ] = (),
    heuristic_exact_runtime_ratio_statistics: Sequence[
        HeuristicExactRuntimeRatioRecord
    ] = (),
    bnb_node_reduction_statistics: Sequence[
        BranchAndBoundNodeReductionRecord
    ] = (),
    quality_runtime_pareto_statistics: Sequence[
        QualityRuntimeParetoRecord
    ] = (),
    gap_density_association_statistics: Sequence[
        GapDensityAssociationRecord
    ] = (),
    gap_overlap_association_statistics: Sequence[
        GapOverlapAssociationRecord
    ] = (),
    gap_clustering_association_statistics: Sequence[
        GapClusteringAssociationRecord
    ] = (),
    runtime_set_count_association_statistics: Sequence[
        RuntimeSetCountAssociationRecord
    ] = (),
    runtime_k_association_statistics: Sequence[RuntimeKAssociationRecord] = (),
    search_nodes_dominated_ratio_association_statistics: Sequence[
        SearchNodesDominatedRatioAssociationRecord
    ] = (),
    confidence_interval_statistics: Sequence[
        ConfidenceIntervalRecord
    ] = (),
    censored_runtime_statistics: Sequence[CensoredRuntimeRecord] = (),
) -> None:
    _write_markdown(
        output_dir / "results_summary.md",
        config_path,
        config,
        rows,
        statistics,
        instances,
        greedy_failure_statistics,
        local_search_recovery_statistics,
        local_search_remaining_gap_statistics,
        heuristic_exact_runtime_ratio_statistics,
        bnb_node_reduction_statistics,
        quality_runtime_pareto_statistics,
        gap_density_association_statistics,
        gap_overlap_association_statistics,
        gap_clustering_association_statistics,
        runtime_set_count_association_statistics,
        runtime_k_association_statistics,
        search_nodes_dominated_ratio_association_statistics,
        confidence_interval_statistics,
        censored_runtime_statistics,
    )
    _write_gap_chart(output_dir / "gap_by_family.svg", statistics)
    _write_runtime_chart(output_dir / "runtime_by_algorithm.svg", statistics)
    (output_dir / "gap_by_case.svg").write_text(
        _render_gap_by_case_chart(statistics), encoding="utf-8"
    )
    (output_dir / "gap_vs_structural_parameter.svg").write_text(
        _render_gap_structural_association_chart(
            gap_density_association_statistics,
            gap_overlap_association_statistics,
            gap_clustering_association_statistics,
        ),
        encoding="utf-8",
    )
    (output_dir / "local_search_recovery.svg").write_text(
        _render_local_search_recovery_chart(local_search_recovery_statistics),
        encoding="utf-8",
    )
    (output_dir / "quality_runtime_pareto.svg").write_text(
        _render_quality_runtime_pareto_chart(quality_runtime_pareto_statistics),
        encoding="utf-8",
    )
    (output_dir / "runtime_scaling.svg").write_text(
        _render_runtime_scaling_chart(
            runtime_set_count_association_statistics,
            runtime_k_association_statistics,
        ),
        encoding="utf-8",
    )
    (output_dir / "node_scaling.svg").write_text(
        _render_node_scaling_chart(
            search_nodes_dominated_ratio_association_statistics
        ),
        encoding="utf-8",
    )
    (output_dir / "timeout_by_case.svg").write_text(
        _render_timeout_by_case_chart(censored_runtime_statistics),
        encoding="utf-8",
    )
