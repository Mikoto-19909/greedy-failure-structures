"""Structural gap cartography over canonical benchmark results."""

from __future__ import annotations

import csv
import html
import io
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median, stdev

from .algorithms import ALGORITHMS
from .benchmark import _linear_quantile, _student_t_critical_95, run_benchmark
from .config import ExperimentConfig, load_config
from .contracts import BenchmarkResult, RunRecord
from .reproducibility import atomic_write_text, config_hash, file_sha256


CARTOGRAPHY_SCHEMA_VERSION = 1
STRESSOR_FAMILIES = (
    "high_overlap",
    "clustered",
    "long_tail",
    "duplicate_heavy",
    "dominated_heavy",
    "adversarial",
)
HEURISTIC_ALGORITHMS = (
    "greedy",
    "lazy_greedy",
    "local_search",
    "randomized_greedy",
    "multi_start_local_search",
)
CARTOGRAPHY_FILENAMES = (
    "structural_gap_statistics.csv",
    "paired_control_differences.csv",
    "precision_diagnostics.csv",
    "stressor_strength_gap.svg",
    "family_algorithm_gap.svg",
    "cartography_summary.md",
)
CARTOGRAPHY_OWNED_FILENAMES = (
    *CARTOGRAPHY_FILENAMES,
    "cartography_manifest.json",
)


@dataclass(frozen=True, slots=True)
class CartographyLevel:
    family: str
    strength: float
    strength_label: str
    stressor_case_id: str
    control_case_id: str


@dataclass(frozen=True, slots=True)
class CartographyDesign:
    minimum_instance_seeds: int
    precision_target_half_width: float
    levels: tuple[CartographyLevel, ...]


@dataclass(frozen=True, slots=True)
class _Description:
    sample_count: int
    mean: float | None
    median: float | None
    standard_deviation: float | None
    minimum: float | None
    p25: float | None
    p75: float | None
    maximum: float | None
    ci95_lower: float | None
    ci95_upper: float | None


@dataclass(frozen=True, slots=True)
class _InstanceGap:
    seed: int
    gap: float | None
    run_count: int
    algorithm_seed_count: int


def _number(value: object, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    numeric = float(value)
    if not math.isfinite(numeric) or (positive and numeric <= 0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{path} must be {qualifier}")
    return numeric


def load_cartography_design(
    path: Path, config: ExperimentConfig
) -> CartographyDesign:
    """Load a small, explicit map from stressor levels to matched controls."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("cartography design root must be an object")
    expected_root = {
        "schema_version",
        "minimum_instance_seeds",
        "precision_target_half_width",
        "levels",
    }
    if set(value) != expected_root:
        raise ValueError("cartography design root fields do not match the schema")
    if value["schema_version"] != CARTOGRAPHY_SCHEMA_VERSION:
        raise ValueError("unsupported cartography design schema version")
    minimum = value["minimum_instance_seeds"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError("minimum_instance_seeds must be an integer of at least 2")
    target = _number(
        value["precision_target_half_width"],
        "precision_target_half_width",
        positive=True,
    )
    raw_levels = value["levels"]
    if not isinstance(raw_levels, list) or not raw_levels:
        raise ValueError("cartography levels must be a non-empty array")

    cases = {case.case_id: case for case in config.cases}
    levels: list[CartographyLevel] = []
    seen_treatments: set[str] = set()
    for index, raw in enumerate(raw_levels):
        path_prefix = f"levels[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path_prefix} must be an object")
        expected = {
            "family",
            "strength",
            "strength_label",
            "stressor_case_id",
            "control_case_id",
        }
        if set(raw) != expected:
            raise ValueError(f"{path_prefix} fields do not match the schema")
        strings: dict[str, str] = {}
        for field in (
            "family",
            "strength_label",
            "stressor_case_id",
            "control_case_id",
        ):
            item = raw[field]
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{path_prefix}.{field} must be a non-empty string")
            strings[field] = item
        family = strings["family"]
        if family not in STRESSOR_FAMILIES:
            raise ValueError(f"{path_prefix}.family is not a cartography stressor")
        stressor_id = strings["stressor_case_id"]
        control_id = strings["control_case_id"]
        if stressor_id in seen_treatments:
            raise ValueError(f"duplicate stressor_case_id {stressor_id!r}")
        seen_treatments.add(stressor_id)
        if stressor_id not in cases or control_id not in cases:
            raise ValueError(f"{path_prefix} references an unknown case_id")
        stressor = cases[stressor_id]
        control = cases[control_id]
        if stressor.family != family or control.family != "uniform":
            raise ValueError(f"{path_prefix} family/control roles are inconsistent")
        if stressor.seed_group is None or stressor.seed_group != control.seed_group:
            raise ValueError(f"{path_prefix} treatment and control need one seed_group")
        stressor_instance = stressor.generate(0)
        control_instance = control.generate(0)
        if (
            stressor_instance.universe_size,
            stressor_instance.set_count,
            stressor_instance.k,
        ) != (
            control_instance.universe_size,
            control_instance.set_count,
            control_instance.k,
        ):
            raise ValueError(f"{path_prefix} treatment/control dimensions differ")
        levels.append(
            CartographyLevel(
                family=family,
                strength=_number(raw["strength"], f"{path_prefix}.strength"),
                strength_label=strings["strength_label"],
                stressor_case_id=stressor_id,
                control_case_id=control_id,
            )
        )

    family_levels: dict[str, list[CartographyLevel]] = defaultdict(list)
    for level in levels:
        family_levels[level.family].append(level)
    if set(family_levels) != set(STRESSOR_FAMILIES):
        raise ValueError("cartography design must contain all six stressor families")
    for family, group in family_levels.items():
        strengths = [level.strength for level in group]
        if len(group) < 2 or len(set(strengths)) != len(strengths):
            raise ValueError(
                f"cartography family {family!r} needs multiple distinct strengths"
            )

    if config.repetitions < minimum:
        raise ValueError(
            f"benchmark has {config.repetitions} instance seeds; design requires {minimum}"
        )
    by_name: dict[str, list[str]] = defaultdict(list)
    for algorithm in config.algorithms:
        if algorithm.enabled:
            by_name[algorithm.name].append(algorithm.algorithm_id)
    for name in HEURISTIC_ALGORITHMS:
        if len(by_name[name]) != 1:
            raise ValueError(
                f"cartography requires exactly one enabled {name!r} variant"
            )
    if not any(
        algorithm.enabled and ALGORITHMS[algorithm.name].exact
        for algorithm in config.algorithms
    ):
        raise ValueError("cartography requires an enabled exact-reference algorithm")
    return CartographyDesign(minimum, target, tuple(levels))


def _describe(values: Sequence[float]) -> _Description:
    ordered = sorted(values)
    if not ordered:
        return _Description(0, None, None, None, None, None, None, None, None, None)
    mean = fmean(ordered)
    deviation = None if len(ordered) < 2 else stdev(ordered)
    lower = None
    upper = None
    if deviation is not None:
        margin = (
            _student_t_critical_95(len(ordered) - 1)
            * deviation
            / math.sqrt(len(ordered))
        )
        lower = mean - margin
        upper = mean + margin
    return _Description(
        len(ordered),
        mean,
        median(ordered),
        deviation,
        ordered[0],
        _linear_quantile(ordered, 0.25),
        _linear_quantile(ordered, 0.75),
        ordered[-1],
        lower,
        upper,
    )


def _round(value: float | None) -> float | str:
    return "" if value is None else float(f"{value:.10f}")


def _artifact_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError("cartography numeric artifact value has an invalid type")
    return float(value)


def _algorithm_layout(
    config: ExperimentConfig,
) -> dict[str, tuple[str, tuple[int | None, ...]]]:
    layout: dict[str, tuple[str, tuple[int | None, ...]]] = {}
    for algorithm in config.algorithms:
        if algorithm.enabled and algorithm.name in HEURISTIC_ALGORITHMS:
            layout[algorithm.name] = (
                algorithm.algorithm_id,
                algorithm.algorithm_seeds
                if algorithm.algorithm_seeds
                else (None,),
            )
    return layout


def _instance_gaps(
    rows: Sequence[RunRecord],
    *,
    case_id: str,
    algorithm_id: str,
    expected_algorithm_seeds: tuple[int | None, ...],
) -> dict[int, _InstanceGap]:
    grouped: dict[int, list[RunRecord]] = defaultdict(list)
    for row in rows:
        if row.case_id == case_id and row.algorithm_id == algorithm_id:
            grouped[row.repetition].append(row)
    result: dict[int, _InstanceGap] = {}
    for repetition, group in grouped.items():
        seeds = {row.seed for row in group}
        if len(seeds) != 1:
            raise ValueError("one cartography instance unit has inconsistent seeds")
        instance_seed = next(iter(seeds))
        if instance_seed is None:
            raise ValueError("cartography instance units require explicit seeds")
        actual_algorithm_seeds = tuple(row.algorithm_seed for row in group)
        if (
            len(actual_algorithm_seeds) != len(expected_algorithm_seeds)
            or len(set(actual_algorithm_seeds)) != len(actual_algorithm_seeds)
            or set(actual_algorithm_seeds) != set(expected_algorithm_seeds)
        ):
            raise ValueError(
                "cartography instance unit algorithm seeds do not match the "
                "configured seed set"
            )
        gaps = [row.optimality_gap for row in group if row.optimality_gap is not None]
        complete = (
            len(group) == len(expected_algorithm_seeds)
            and len(gaps) == len(expected_algorithm_seeds)
        )
        result[repetition] = _InstanceGap(
            seed=instance_seed,
            gap=fmean(gaps) if complete else None,
            run_count=len(group),
            algorithm_seed_count=len(actual_algorithm_seeds),
        )
    return result


def _statistics_row(
    *,
    level: CartographyLevel,
    group: str,
    case_id: str,
    paired_case_id: str,
    algorithm_id: str,
    algorithm: str,
    expected_seed_count: int,
    expected_algorithm_seed_count: int,
    units: Mapping[int, _InstanceGap],
) -> dict[str, object]:
    description = _describe(
        [unit.gap for unit in units.values() if unit.gap is not None]
    )
    return {
        "family": level.family,
        "strength": _round(level.strength),
        "strength_label": level.strength_label,
        "group": group,
        "case_id": case_id,
        "paired_case_id": paired_case_id,
        "algorithm_id": algorithm_id,
        "algorithm": algorithm,
        "expected_instance_seed_count": expected_seed_count,
        "observed_instance_seed_count": len(units),
        "algorithm_seed_count": expected_algorithm_seed_count,
        "run_count": sum(unit.run_count for unit in units.values()),
        "valid_gap_count": description.sample_count,
        "missing_gap_count": expected_seed_count - description.sample_count,
        "mean_gap": _round(description.mean),
        "median_gap": _round(description.median),
        "standard_deviation_gap": _round(description.standard_deviation),
        "minimum_gap": _round(description.minimum),
        "p25_gap": _round(description.p25),
        "p75_gap": _round(description.p75),
        "maximum_gap": _round(description.maximum),
        "ci95_lower": _round(description.ci95_lower),
        "ci95_upper": _round(description.ci95_upper),
        "ci_method": "student_t_two_sided",
    }


def _paired_row(
    *,
    level: CartographyLevel,
    algorithm_id: str,
    algorithm: str,
    expected_seed_count: int,
    treatment: Mapping[int, _InstanceGap],
    control: Mapping[int, _InstanceGap],
) -> tuple[dict[str, object], _Description]:
    differences: list[float] = []
    treatment_gaps: list[float] = []
    control_gaps: list[float] = []
    for repetition in sorted(set(treatment) & set(control)):
        left = treatment[repetition]
        right = control[repetition]
        if left.seed != right.seed:
            raise ValueError(
                f"paired cartography cases do not share a seed at repetition {repetition}"
            )
        if left.gap is None or right.gap is None:
            continue
        treatment_gaps.append(left.gap)
        control_gaps.append(right.gap)
        differences.append(left.gap - right.gap)
    description = _describe(differences)
    treatment_valid = sum(unit.gap is not None for unit in treatment.values())
    control_valid = sum(unit.gap is not None for unit in control.values())
    return (
        {
            "family": level.family,
            "strength": _round(level.strength),
            "strength_label": level.strength_label,
            "stressor_case_id": level.stressor_case_id,
            "control_case_id": level.control_case_id,
            "algorithm_id": algorithm_id,
            "algorithm": algorithm,
            "expected_paired_seed_count": expected_seed_count,
            "stressor_valid_seed_count": treatment_valid,
            "control_valid_seed_count": control_valid,
            "paired_seed_count": description.sample_count,
            "unpaired_or_missing_seed_count": (
                expected_seed_count - description.sample_count
            ),
            "mean_stressor_gap": _round(
                None if not treatment_gaps else fmean(treatment_gaps)
            ),
            "mean_control_gap": _round(
                None if not control_gaps else fmean(control_gaps)
            ),
            "mean_paired_gap_difference": _round(description.mean),
            "median_paired_gap_difference": _round(description.median),
            "standard_deviation_paired_gap_difference": _round(
                description.standard_deviation
            ),
            "minimum_paired_gap_difference": _round(description.minimum),
            "p25_paired_gap_difference": _round(description.p25),
            "p75_paired_gap_difference": _round(description.p75),
            "maximum_paired_gap_difference": _round(description.maximum),
            "ci95_lower": _round(description.ci95_lower),
            "ci95_upper": _round(description.ci95_upper),
            "difference_formula": "stressor_gap-control_gap",
            "ci_method": "paired_student_t_two_sided",
        },
        description,
    )


def _required_sample_count(deviation: float | None, target: float) -> int | None:
    if deviation is None:
        return None
    if deviation == 0:
        return 2
    for count in range(2, 10_001):
        half_width = _student_t_critical_95(count - 1) * deviation / math.sqrt(count)
        if half_width <= target:
            return count
    return 10_001


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty cartography artifact {path.name}")
    fields = tuple(rows[0])
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        if tuple(row) != fields:
            raise ValueError(f"inconsistent cartography row for {path.name}")
        writer.writerow(row)
    atomic_write_text(path, stream.getvalue())


def _svg_text(value: object) -> str:
    return html.escape(str(value), quote=True)


_COLORS = {
    "greedy": "#ef4444",
    "lazy_greedy": "#f59e0b",
    "local_search": "#10b981",
    "randomized_greedy": "#3b82f6",
    "multi_start_local_search": "#8b5cf6",
}
_ALGORITHM_LABELS = {
    "greedy": "Greedy",
    "lazy_greedy": "Lazy Greedy",
    "local_search": "Local Search",
    "randomized_greedy": "Randomized Greedy",
    "multi_start_local_search": "Multi-start LS",
}
_STRENGTH_AXES = {
    "high_overlap": "core fraction",
    "clustered": "within probability",
    "long_tail": "gamma",
    "duplicate_heavy": "copy factor",
    "dominated_heavy": "child count",
    "adversarial": "certified severity",
}


def _render_strength_chart(rows: Sequence[Mapping[str, object]]) -> str:
    stressor = [row for row in rows if row["group"] == "stressor"]
    valid_means = [
        _artifact_float(row["mean_gap"])
        for row in stressor
        if row["mean_gap"] != ""
    ]
    valid_upper = [
        _artifact_float(row["ci95_upper"])
        for row in stressor
        if row["ci95_upper"] != ""
    ]
    maximum = max([0.01, *valid_means, *valid_upper])
    width, height = 1280, 1120
    panel_width, panel_height = 570, 300
    lefts = (90, 690)
    tops = (150, 470, 790)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="640" y="38" text-anchor="middle" font-family="Arial" font-size="24" font-weight="bold">Stressor strength and optimum-relative gap</text>',
        '<text x="640" y="64" text-anchor="middle" font-family="Arial" font-size="13" fill="#475569">points = instance-seed means; bars = 95% Student-t intervals</text>',
    ]
    legend_x = 120
    for algorithm in HEURISTIC_ALGORITHMS:
        color = _COLORS[algorithm]
        lines.extend(
            [
                f'<line x1="{legend_x}" y1="100" x2="{legend_x + 28}" y2="100" stroke="{color}" stroke-width="3"/>',
                f'<text x="{legend_x + 35}" y="105" font-family="Arial" font-size="12">{_svg_text(_ALGORITHM_LABELS[algorithm])}</text>',
            ]
        )
        legend_x += 205
    for family_index, family in enumerate(STRESSOR_FAMILIES):
        left = lefts[family_index % 2]
        top = tops[family_index // 2]
        plot_left, plot_top = left + 56, top + 34
        plot_width, plot_height = panel_width - 76, panel_height - 76
        family_rows = [row for row in stressor if row["family"] == family]
        strengths = sorted(
            {_artifact_float(row["strength"]) for row in family_rows}
        )
        x_min, x_max = min(strengths), max(strengths)
        lines.extend(
            [
                f'<text x="{left}" y="{top + 18}" font-family="Arial" font-size="16" font-weight="bold">{_svg_text(family)}</text>',
                f'<line x1="{plot_left}" y1="{plot_top + plot_height}" x2="{plot_left + plot_width}" y2="{plot_top + plot_height}" stroke="#334155"/>',
                f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_top + plot_height}" stroke="#334155"/>',
                f'<text x="{plot_left - 8}" y="{plot_top + 4}" text-anchor="end" font-family="Arial" font-size="10">{maximum:.1%}</text>',
                f'<text x="{plot_left - 8}" y="{plot_top + plot_height + 4}" text-anchor="end" font-family="Arial" font-size="10">0%</text>',
            ]
        )
        for strength in strengths:
            x = plot_left + (
                0.5 * plot_width
                if x_max == x_min
                else (strength - x_min) / (x_max - x_min) * plot_width
            )
            label = f"{strength:.4g}"
            lines.append(
                f'<text x="{x:.2f}" y="{plot_top + plot_height + 18}" text-anchor="middle" font-family="Arial" font-size="10">{_svg_text(label)}</text>'
            )
        lines.append(
            f'<text x="{plot_left + plot_width / 2:.2f}" y="{plot_top + plot_height + 36}" text-anchor="middle" font-family="Arial" font-size="11" fill="#475569">{_svg_text(_STRENGTH_AXES[family])}</text>'
        )
        for algorithm in HEURISTIC_ALGORITHMS:
            points: list[tuple[float, float, float | None, float | None]] = []
            for row in sorted(
                (item for item in family_rows if item["algorithm"] == algorithm),
                key=lambda item: _artifact_float(item["strength"]),
            ):
                if row["mean_gap"] == "":
                    continue
                strength = _artifact_float(row["strength"])
                x = plot_left + (
                    0.5 * plot_width
                    if x_max == x_min
                    else (strength - x_min) / (x_max - x_min) * plot_width
                )
                mean_gap = _artifact_float(row["mean_gap"])
                y = plot_top + plot_height - mean_gap / maximum * plot_height
                lower = (
                    None
                    if row["ci95_lower"] == ""
                    else _artifact_float(row["ci95_lower"])
                )
                upper = (
                    None
                    if row["ci95_upper"] == ""
                    else _artifact_float(row["ci95_upper"])
                )
                points.append((x, y, lower, upper))
            if len(points) > 1:
                path = " ".join(
                    ("M" if index == 0 else "L") + f" {x:.2f} {y:.2f}"
                    for index, (x, y, _, _) in enumerate(points)
                )
                lines.append(
                    f'<path d="{path}" fill="none" stroke="{_COLORS[algorithm]}" stroke-width="2.5"/>'
                )
            for x, y, lower, upper in points:
                if lower is not None and upper is not None:
                    y_low = plot_top + plot_height - max(0.0, lower) / maximum * plot_height
                    y_high = plot_top + plot_height - min(maximum, upper) / maximum * plot_height
                    lines.append(
                        f'<line x1="{x:.2f}" y1="{y_high:.2f}" x2="{x:.2f}" y2="{y_low:.2f}" stroke="{_COLORS[algorithm]}" stroke-width="1.4"/>'
                    )
                lines.append(
                    f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{_COLORS[algorithm]}"/>'
                )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _render_family_algorithm_chart(rows: Sequence[Mapping[str, object]]) -> str:
    stressor = [row for row in rows if row["group"] == "stressor"]
    coordinates: dict[tuple[str, str], float] = {}
    for family in STRESSOR_FAMILIES:
        for algorithm in HEURISTIC_ALGORITHMS:
            values = [
                _artifact_float(row["mean_gap"])
                for row in stressor
                if row["family"] == family
                and row["algorithm"] == algorithm
                and row["mean_gap"] != ""
            ]
            if values:
                coordinates[(family, algorithm)] = fmean(values)
    maximum = max([0.01, *coordinates.values()])
    width, height = 1180, 620
    left, top, cell_width, cell_height = 220, 130, 178, 66
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="590" y="38" text-anchor="middle" font-family="Arial" font-size="24" font-weight="bold">Family × algorithm gap map</text>',
        '<text x="590" y="64" text-anchor="middle" font-family="Arial" font-size="13" fill="#475569">equal-weight mean of stressor-level instance-seed mean gaps</text>',
    ]
    for column, algorithm in enumerate(HEURISTIC_ALGORITHMS):
        x = left + column * cell_width + cell_width / 2
        lines.append(
            f'<text x="{x:.2f}" y="{top - 18}" text-anchor="middle" font-family="Arial" font-size="11">{_svg_text(_ALGORITHM_LABELS[algorithm])}</text>'
        )
    for row_index, family in enumerate(STRESSOR_FAMILIES):
        y = top + row_index * cell_height
        lines.append(
            f'<text x="{left - 14}" y="{y + cell_height / 2 + 4:.2f}" text-anchor="end" font-family="Arial" font-size="13">{_svg_text(family)}</text>'
        )
        for column, algorithm in enumerate(HEURISTIC_ALGORITHMS):
            x = left + column * cell_width
            value = coordinates.get((family, algorithm))
            ratio = 0.0 if value is None else min(1.0, value / maximum)
            red = 255
            green = round(248 - 150 * ratio)
            blue = round(240 - 170 * ratio)
            fill = f"rgb({red},{green},{blue})"
            label = "n/a" if value is None else f"{value:.2%}"
            lines.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_width - 4}" height="{cell_height - 4}" rx="4" fill="{fill}" stroke="#e2e8f0"/>',
                    f'<text x="{x + (cell_width - 4) / 2:.2f}" y="{y + 37}" text-anchor="middle" font-family="Arial" font-size="14" font-weight="bold">{label}</text>',
                ]
            )
    lines.extend(
        [
            f'<text x="{left}" y="{height - 40}" font-family="Arial" font-size="12" fill="#475569">white = zero; darkest cell = {maximum:.2%}</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines) + "\n"


def write_cartography_artifacts(
    output_dir: Path,
    config_path: Path,
    design_path: Path,
    result: BenchmarkResult,
) -> None:
    """Compute seed-level distributions and paired-control gap contrasts."""

    output_dir = Path(output_dir)
    design = load_cartography_design(design_path, result.config)
    layout = _algorithm_layout(result.config)
    statistics_rows: list[dict[str, object]] = []
    paired_rows: list[dict[str, object]] = []
    precision_rows: list[dict[str, object]] = []
    for level in sorted(
        design.levels,
        key=lambda item: (STRESSOR_FAMILIES.index(item.family), item.strength),
    ):
        for algorithm in HEURISTIC_ALGORITHMS:
            algorithm_id, algorithm_seeds = layout[algorithm]
            algorithm_seed_count = len(algorithm_seeds)
            treatment = _instance_gaps(
                result.rows,
                case_id=level.stressor_case_id,
                algorithm_id=algorithm_id,
                expected_algorithm_seeds=algorithm_seeds,
            )
            control = _instance_gaps(
                result.rows,
                case_id=level.control_case_id,
                algorithm_id=algorithm_id,
                expected_algorithm_seeds=algorithm_seeds,
            )
            statistics_rows.append(
                _statistics_row(
                    level=level,
                    group="stressor",
                    case_id=level.stressor_case_id,
                    paired_case_id=level.control_case_id,
                    algorithm_id=algorithm_id,
                    algorithm=algorithm,
                    expected_seed_count=result.config.repetitions,
                    expected_algorithm_seed_count=algorithm_seed_count,
                    units=treatment,
                )
            )
            statistics_rows.append(
                _statistics_row(
                    level=level,
                    group="control",
                    case_id=level.control_case_id,
                    paired_case_id=level.stressor_case_id,
                    algorithm_id=algorithm_id,
                    algorithm=algorithm,
                    expected_seed_count=result.config.repetitions,
                    expected_algorithm_seed_count=algorithm_seed_count,
                    units=control,
                )
            )
            paired, description = _paired_row(
                level=level,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                expected_seed_count=result.config.repetitions,
                treatment=treatment,
                control=control,
            )
            paired_rows.append(paired)
            required = _required_sample_count(
                description.standard_deviation,
                design.precision_target_half_width,
            )
            actual_half_width = (
                None
                if description.ci95_lower is None or description.ci95_upper is None
                else (description.ci95_upper - description.ci95_lower) / 2
            )
            precision_rows.append(
                {
                    "family": level.family,
                    "strength": _round(level.strength),
                    "strength_label": level.strength_label,
                    "algorithm_id": algorithm_id,
                    "algorithm": algorithm,
                    "estimand": "mean_paired_gap_difference",
                    "observed_paired_seed_count": description.sample_count,
                    "observed_standard_deviation": _round(
                        description.standard_deviation
                    ),
                    "observed_ci95_half_width": _round(actual_half_width),
                    "target_ci95_half_width": _round(
                        design.precision_target_half_width
                    ),
                    "estimated_required_seed_count": (
                        "" if required is None else required
                    ),
                    "precision_status": (
                        "not_estimable"
                        if required is None
                        else "adequate"
                        if description.sample_count >= required
                        else "increase_seeds"
                    ),
                    "planning_method": "observed_sd_student_t_fixed_half_width",
                }
            )

    _write_csv(output_dir / "structural_gap_statistics.csv", statistics_rows)
    _write_csv(output_dir / "paired_control_differences.csv", paired_rows)
    _write_csv(output_dir / "precision_diagnostics.csv", precision_rows)
    atomic_write_text(
        output_dir / "stressor_strength_gap.svg",
        _render_strength_chart(statistics_rows),
    )
    atomic_write_text(
        output_dir / "family_algorithm_gap.svg",
        _render_family_algorithm_chart(statistics_rows),
    )
    adequate = sum(row["precision_status"] == "adequate" for row in precision_rows)
    summary = "\n".join(
        [
            "# Structural gap cartography",
            "",
            "The reported gap is `1 - coverage / optimum`. Randomized-algorithm "
            "seeds are averaged within each generated instance before instance-seed "
            "distribution statistics are computed.",
            "",
            "Paired differences use `stressor_gap - control_gap` for treatment and "
            "uniform-control instances sharing the same configured seed group and "
            "repetition. Intervals are two-sided 95% Student-t intervals.",
            "",
            f"Precision target: CI half-width <= {design.precision_target_half_width:.4f}. "
            f"Adequate paired cells at the current seed count: {adequate}/{len(precision_rows)}.",
            "",
            "Artifacts:",
            "",
            "- `structural_gap_statistics.csv`: mean, median, dispersion, quantiles, and intervals",
            "- `paired_control_differences.csv`: paired seed-level treatment-control contrasts",
            "- `precision_diagnostics.csv`: observed-variance seed-count diagnostics",
            "- `stressor_strength_gap.svg`: strength-gap curves with intervals",
            "- `family_algorithm_gap.svg`: family-by-algorithm gap map",
            "",
        ]
    )
    atomic_write_text(output_dir / "cartography_summary.md", summary)
    manifest = {
        "schema_version": CARTOGRAPHY_SCHEMA_VERSION,
        "config_hash": config_hash(result.config),
        "config_file": Path(config_path).name,
        "config_sha256": file_sha256(config_path),
        "design_file": Path(design_path).name,
        "design_sha256": file_sha256(design_path),
        "raw_results_sha256": file_sha256(output_dir / "raw_results.csv"),
        "gap_formula": "1-coverage/optimum",
        "paired_difference_formula": "stressor_gap-control_gap",
        "repetition_unit": "instance_seed",
        "algorithm_seed_role": "nested_within_instance",
        "outputs": {
            filename: {"sha256": file_sha256(output_dir / filename)}
            for filename in CARTOGRAPHY_FILENAMES
        },
    }
    atomic_write_text(
        output_dir / "cartography_manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def run_cartography(
    config_path: Path,
    design_path: Path,
    output_dir: Path,
    *,
    workers: int = 1,
    force: bool = False,
) -> BenchmarkResult:
    """Run/resume the benchmark and write the cartography-specific artifacts."""

    config = load_config(config_path)
    load_cartography_design(design_path, config)
    if force:
        for filename in CARTOGRAPHY_OWNED_FILENAMES:
            (Path(output_dir) / filename).unlink(missing_ok=True)
    result = run_benchmark(
        config_path,
        output_dir,
        workers=workers,
        force=force,
        checkpoint_interval=100,
    )
    write_cartography_artifacts(output_dir, config_path, design_path, result)
    return result
