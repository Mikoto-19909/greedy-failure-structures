"""Deterministic SVG report renderers."""

from __future__ import annotations

import html
import math
from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import Path
from typing import cast
from .contracts import (
    CensoredRuntimeRecord,
    DescriptiveStatisticsRecord,
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
    GapClusteringAssociationRecord,
    LocalSearchRecoveryRecord,
    QualityRuntimeParetoRecord,
    ReferenceStatusRecord,
    RuntimeKAssociationRecord,
    RuntimeSetCountAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
)
from ._report_labels import (
    COLORS,
    _REFERENCE_STATUS_COLORS,
    _REFERENCE_STATUS_LABELS,
    _algorithm_label,
    _case_label,
    _family_label,
    _predictor_label,
    _status_label,
    _unit_label,
)


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
    labels = [
        f"{_case_label(row.case_id)} / {_algorithm_label(row.algorithm_id)}"
        for row in usable
    ]
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
    labels = [
        f"{_case_label(row.case_id)} / {_algorithm_label(row.algorithm_id)}"
        for row in usable
    ]
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
    visible_subtitle: str | None = None,
) -> str:
    """Render deterministic horizontal bars with explicit sample diagnostics."""

    left, top, bottom = 340, 100, 55
    row_height = 54
    height = max(360, top + row_height * max(1, len(rows)) + bottom)
    plot_width = width - left - right
    display_subtitle = subtitle if visible_subtitle is None else visible_subtitle
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(subtitle)}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(display_subtitle)}</text>',
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
        tick_value = axis_maximum * fraction
        parts.extend(
            [
                f'<line x1="{x:.2f}" y1="{top - 10}" x2="{x:.2f}" y2="{top + row_height * len(rows)}" stroke="#e5e7eb"/>',
                f'<text x="{x:.2f}" y="{top - 18}" text-anchor="middle" font-family="Arial" font-size="11">{tick_value:{value_format}}</text>',
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
        DescriptiveStatisticsRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in statistics
    ]
    rows: list[ChartRow] = []
    for record in sorted(
        (row for row in canonical_statistics if row.metric == "optimality_gap"),
        key=lambda row: (row.family, row.case_id, row.algorithm_id, row.algorithm),
    ):
        detail = (
            f"样本={record.sample_count} {_unit_label(record.repetition_unit)}; "
            f"运行={record.run_count}; 超时={record.timeout_count}; "
            f"错误={record.error_count}; 有效最优参考={record.valid_exact_reference_count}"
        )
        rows.append(
            (
                f"{_family_label(record.family)} / {_case_label(record.case_id)} / "
                f"{_algorithm_label(record.algorithm_id)}",
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
        visible_subtitle="来源：描述性统计；单位：实例种子；固定输入的描述性结果",
    )


def _association_chart_rows(
    density: Sequence[GapDensityAssociationRecord],
    overlap: Sequence[GapOverlapAssociationRecord],
    clustering: Sequence[GapClusteringAssociationRecord],
) -> list[ChartRow]:
    canonical_density = [
        GapDensityAssociationRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in density
    ]
    canonical_overlap = [
        GapOverlapAssociationRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in overlap
    ]
    canonical_clustering = [
        GapClusteringAssociationRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in clustering
    ]
    rows: list[ChartRow] = []
    association_groups: tuple[
        tuple[str, Sequence[
            GapDensityAssociationRecord | GapOverlapAssociationRecord
            | GapClusteringAssociationRecord
        ]], ...
    ] = (
        ("density", canonical_density),
        ("overlap", canonical_overlap),
        ("clustering", canonical_clustering),
    )
    for predictor, records in association_groups:
        for record in sorted(
            records,
            key=lambda row: (row.family, row.algorithm_id, row.algorithm),
        ):
            if isinstance(record, GapClusteringAssociationRecord):
                count = record.eligible_block_count
                unit = "耦合种子区块"
                exclusions = (
                    f"不完整={record.incomplete_block_count}; "
                    f"超时={record.timeout_count}; 错误={record.error_count}"
                )
            else:
                count = record.eligible_instance_count
                unit = _unit_label(record.repetition_unit)
                exclusions = (
                    f"超时={record.timeout_count}; 错误={record.error_count}; "
                    f"不可用={record.unusable_result_count}"
                )
                if isinstance(record, GapOverlapAssociationRecord):
                    exclusions += (
                        f"; 缺少重叠度预测值={record.missing_overlap_predictor_count}"
                    )
            slope = "blank" if record.ols_slope is None else f"{record.ols_slope:.6f}"
            intercept = (
                "blank"
                if record.ols_intercept is None
                else f"{record.ols_intercept:.6f}"
            )
            detail = (
                f"样本={count} {unit}; 状态={_status_label(record.association_status)}; "
                f"OLS 斜率={slope}; 截距={intercept}; {exclusions}"
            )
            rows.append(
                (
                    f"{_predictor_label(predictor)} / {_family_label(record.family)} / "
                    f"{_algorithm_label(record.algorithm_id)}",
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
    display_subtitle = "来源：结构参数关联统计；Pearson 相关系数；仅作描述，不表示因果关系"
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
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(display_subtitle)}</text>',
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
        tick_value = -1.0 + tick * 0.5
        x = left + (tick_value + 1.0) * plot_width / 2
        parts.extend(
            [
                f'<line x1="{x:.2f}" y1="{top - 10}" x2="{x:.2f}" y2="{top + row_height * len(rows)}" stroke="{("#9ca3af" if tick_value == 0 else "#e5e7eb")}"/>',
                f'<text x="{x:.2f}" y="{top - 18}" text-anchor="middle" font-family="Arial" font-size="11">{tick_value:.1f}</text>',
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
    *,
    visible_subtitle: str | None = None,
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
    display_subtitle = subtitle if visible_subtitle is None else visible_subtitle
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(subtitle)}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(display_subtitle)}</text>',
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
            tick_value = -maximum + tick * maximum / 2
            x = left + tick * plot_width / 4
            parts.extend(
                [
                    f'<line x1="{x:.2f}" y1="{plot_top - 10}" x2="{x:.2f}" y2="{plot_top + row_height * row_count}" stroke="{("#9ca3af" if tick == 2 else "#e5e7eb")}"/>',
                    f'<text x="{x:.2f}" y="{plot_top - 18}" text-anchor="middle" font-family="Arial" font-size="10">{tick_value:.6g}</text>',
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
        RuntimeSetCountAssociationRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in set_count_records
    ]
    canonical_k = [
        RuntimeKAssociationRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in k_records
    ]

    def rows_for(records: Sequence[RuntimeSetCountAssociationRecord | RuntimeKAssociationRecord], slope_name: str) -> list[ChartRow]:
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
                f"样本={record.eligible_instance_count} {_unit_label(record.repetition_unit)}; "
                f"案例数={record.case_count}; 状态={_status_label(record.association_status)}; "
                f"Pearson={pearson}; 平均耗时={mean_runtime}; "
                f"未完成实例={record.incomplete_runtime_instance_count}; "
                f"超时={record.timeout_count}; 错误={record.error_count}"
            )
            rows.append(
                (
                    f"{_family_label(record.family)} / {_algorithm_label(record.algorithm_id)}",
                    cast(float | None, getattr(record, slope_name)),
                    COLORS.get(record.algorithm, "#2563eb"),
                    detail,
                )
            )
        return rows

    facets: list[tuple[str, str, Sequence[ChartRow]]] = []
    if canonical_set_count:
        facets.append(
            (
                "集合数量",
                "OLS slope (seconds per set)",
                rows_for(canonical_set_count, "ols_slope_seconds_per_set"),
            )
        )
    if canonical_k:
        facets.append(
            (
                "选择预算 k",
                "OLS slope (seconds per budget unit)",
                rows_for(canonical_k, "ols_slope_seconds_per_budget_unit"),
            )
        )
    return _render_signed_coefficient_chart(
        "Completed Runtime Scaling by Structural Predictor",
        "sources=runtime_set_count_association_statistics.csv + runtime_k_association_statistics.csv; unit=instance_seed; machine-specific descriptive evidence; censored runtime excluded",
        facets,
        visible_subtitle="来源：运行耗时与结构参数关联统计；单位：实例种子；排除删失耗时",
    )


def _render_node_scaling_chart(
    records: Sequence[SearchNodesDominatedRatioAssociationRecord],
) -> str:
    """Render complete BnB search-node slopes versus dominated-set ratio."""

    canonical_records = [
        SearchNodesDominatedRatioAssociationRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
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
            f"样本={record.eligible_instance_count} {_unit_label(record.repetition_unit)}; "
            f"案例数={record.case_count}; 状态={_status_label(record.association_status)}; "
            f"Pearson={pearson}; 平均搜索节点={mean_nodes}; "
            f"最优运行={record.optimal_run_count}/{record.run_count}; "
            f"超时={record.timeout_count}; 错误={record.error_count}"
        )
        rows.append(
            (
                f"{_family_label(record.family)} / {_algorithm_label(record.algorithm_id)}",
                record.ols_slope_nodes_per_ratio_unit,
                COLORS.get(record.algorithm, "#2563eb"),
                detail,
            )
        )
    facets = (
        (
            "被支配集合比例",
            "OLS slope (search nodes per ratio unit)",
            rows,
        ),
    ) if rows else ()
    return _render_signed_coefficient_chart(
        "Branch-and-Bound Node Scaling versus Dominated-Set Ratio",
        "source=search_nodes_dominated_ratio_association_statistics.csv; unit=instance_seed; complete optimal unseeded BnB searches only; descriptive fixed-corpus evidence",
        facets,
        visible_subtitle="来源：搜索节点与结构参数关联统计；单位：实例种子；仅纳入已证明最优的搜索",
    )


def _render_timeout_by_case_chart(
    records: Sequence[CensoredRuntimeRecord],
) -> str:
    """Render right-censoring rates without treating censor times as runtimes."""

    canonical_records = [
        CensoredRuntimeRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
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
            f"样本={record.instance_count} {_unit_label(record.repetition_unit)}; "
            f"状态={_status_label(record.censoring_status)}; 运行={record.run_count}; "
            f"右删失={record.right_censored_run_count} 次/"
            f"{record.right_censored_instance_count} 个实例; "
            f"错误={record.error_run_count} 次/"
            f"{record.error_affected_instance_count} 个实例; "
            f"完全删失={record.fully_right_censored_instance_count}; "
            f"删失样本={record.censoring_sample_count}; "
            f"平均删失时间={mean_censor_time}（仅作诊断）"
        )
        rows.append(
            (
                f"{_family_label(record.family)} / {_case_label(record.case_id)} / "
                f"{_algorithm_label(record.algorithm_id)}",
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
        visible_subtitle="来源：删失运行统计；单位：实例种子；删失时间仅作诊断",
    )


def _render_reference_coverage_chart(
    records: Sequence[ReferenceStatusRecord],
) -> str:
    """Render proved-reference coverage and every missing-reference status."""

    grouped: dict[tuple[str, str], list[ReferenceStatusRecord]] = {}
    for record in records:
        grouped.setdefault((record.family, record.case_id), []).append(record)
    ordered_groups = sorted(grouped.items())
    width = 1080
    left = 245
    plot_width = 540
    row_height = 36
    top = 142
    height = max(260, top + max(1, len(ordered_groups)) * row_height + 58)
    desc = html.escape(
        "source=reference_status.csv; denominator=all generated instances; "
        "missing references remain visible by effective status"
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<desc>{desc}</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="32" y="34" font-family="Arial" font-size="20" font-weight="700">精确参考覆盖率与缺失层</text>',
        '<text x="32" y="58" font-family="Arial" font-size="12" fill="#4b5563">分母为全部生成实例；绿色为可证明最优，其他颜色保留未获得参考的原因</text>',
    ]
    legend_x = 32
    for status in _REFERENCE_STATUS_LABELS:
        color = _REFERENCE_STATUS_COLORS[status]
        label = _REFERENCE_STATUS_LABELS[status]
        parts.extend(
            [
                f'<rect x="{legend_x}" y="78" width="12" height="12" fill="{color}"/>',
                f'<text x="{legend_x + 17}" y="89" font-family="Arial" font-size="11">{label}</text>',
            ]
        )
        legend_x += 112 if status != "known_optimum_certificate" else 128
    if not ordered_groups:
        parts.extend(
            [
                '<rect x="32" y="126" width="1016" height="72" rx="8" fill="#f3f4f6"/>',
                '<text x="540" y="168" text-anchor="middle" font-family="Arial" font-size="14" fill="#4b5563">没有生成实例</text>',
            ]
        )
    for row_index, ((family, case_id), group) in enumerate(ordered_groups):
        y = top + row_index * row_height
        total = len(group)
        counts = {
            status: sum(record.reference_status == status for record in group)
            for status in _REFERENCE_STATUS_LABELS
        }
        proved = sum(record.provably_optimal for record in group)
        parts.append(
            f'<text x="{left - 12}" y="{y + 14}" text-anchor="end" font-family="Arial" font-size="11">{html.escape(_family_label(family))} · {html.escape(_case_label(case_id))}</text>'
        )
        cursor = float(left)
        for status in _REFERENCE_STATUS_LABELS:
            segment_width = plot_width * counts[status] / total
            if segment_width:
                parts.append(
                    f'<rect x="{cursor:.2f}" y="{y}" width="{segment_width:.2f}" height="20" fill="{_REFERENCE_STATUS_COLORS[status]}"/>'
                )
            cursor += segment_width
        parts.extend(
            [
                f'<rect x="{left}" y="{y}" width="{plot_width}" height="20" fill="none" stroke="#374151" stroke-width="0.8"/>',
                f'<text x="{left + plot_width + 14}" y="{y + 14}" font-family="Arial" font-size="11">有证明参考 {proved}/{total} · 缺失 {total - proved}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _render_local_search_recovery_chart(
    records: Sequence[LocalSearchRecoveryRecord],
) -> str:
    canonical_records = [
        LocalSearchRecoveryRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
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
            f"样本={record.eligible_pair_count} 对应的{_unit_label(record.repetition_unit)}; "
            f"可评估比例={eligible_rate}; 实例={record.instance_count}; "
            f"贪心失败数={record.greedy_failure_count}; "
            f"超时={record.greedy_timeout_count + record.local_search_timeout_count}; "
            f"错误={record.greedy_error_count + record.local_search_error_count}"
        )
        rows.append(
            (
                f"{_family_label(record.family)} / {_case_label(record.case_id)} / "
                f"{_algorithm_label(record.greedy_algorithm_id)} → "
                f"{_algorithm_label(record.local_search_algorithm_id)}",
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
        visible_subtitle="来源：局部搜索恢复统计；单位：成对实例种子",
    )


def _render_quality_runtime_pareto_chart(
    records: Sequence[QualityRuntimeParetoRecord],
) -> str:
    title = "Quality-Runtime Pareto Frontier by Case"
    subtitle = (
        "source=quality_runtime_pareto_statistics.csv; common instance_seed units; "
        "runtime is machine-specific"
    )
    display_subtitle = "来源：质量与耗时权衡统计；按共同实例种子对照；耗时随机器变化"
    grouped: dict[tuple[str, str], list[QualityRuntimeParetoRecord]] = {}
    canonical_records = [
        QualityRuntimeParetoRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
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
        f'<text x="{width / 2}" y="60" text-anchor="middle" font-family="Arial" font-size="12" fill="#4b5563">{html.escape(display_subtitle)}</text>',
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
                f'<text x="{left}" y="{panel_top + 20}" font-family="Arial" font-size="15" font-weight="bold">{html.escape(_family_label(family) + " / " + _case_label(case_id))}</text>',
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
                    f'<text x="{right_start}" y="{detail_y}" font-family="Arial" font-size="10" fill="#111827">{html.escape(_algorithm_label(record.algorithm_id))}: 样本={record.eligible_instance_count} {_unit_label(record.repetition_unit)}; 状态={_status_label(record.pareto_status)}</text>',
                    f'<text x="{right_start}" y="{detail_y + 16}" font-family="Arial" font-size="10" fill="#4b5563">差距={gap}; 耗时={runtime}; 超时={record.timeout_count}; 错误={record.error_count}; 无有效参考={record.no_exact_reference_count}</text>',
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
                    f'<text x="{x + 9:.2f}" y="{label_y:.2f}" font-family="Arial" font-size="10">{html.escape(_algorithm_label(record.algorithm_id))}</text>',
                ]
            )
        panel_top += panel_heights[(family, case_id)]
    parts.append("</svg>")
    return "\n".join(parts)
