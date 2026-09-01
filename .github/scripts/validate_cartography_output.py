"""Independently validate structural gap cartography artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
sys.path.insert(0, str(SOURCE))

from maxcover.config import ExperimentConfig, load_config  # noqa: E402
from maxcover.contracts import RunRecord  # noqa: E402
from maxcover.reproducibility import config_hash, file_sha256  # noqa: E402


FAMILIES = (
    "high_overlap",
    "clustered",
    "long_tail",
    "duplicate_heavy",
    "dominated_heavy",
    "adversarial",
)
ALGORITHMS_IN_REPORT = (
    "greedy",
    "lazy_greedy",
    "local_search",
    "randomized_greedy",
    "multi_start_local_search",
)
OUTPUTS = (
    "structural_gap_statistics.csv",
    "paired_control_differences.csv",
    "precision_diagnostics.csv",
    "stressor_strength_gap.svg",
    "family_algorithm_gap.svg",
    "cartography_summary.md",
)
STATISTICS_FIELDS = (
    "family", "strength", "strength_label", "group", "case_id",
    "paired_case_id", "algorithm_id", "algorithm",
    "expected_instance_seed_count", "observed_instance_seed_count",
    "algorithm_seed_count", "run_count", "valid_gap_count",
    "missing_gap_count", "mean_gap", "median_gap",
    "standard_deviation_gap", "minimum_gap", "p25_gap", "p75_gap",
    "maximum_gap", "ci95_lower", "ci95_upper", "ci_method",
)
PAIRED_FIELDS = (
    "family", "strength", "strength_label", "stressor_case_id",
    "control_case_id", "algorithm_id", "algorithm",
    "expected_paired_seed_count", "stressor_valid_seed_count",
    "control_valid_seed_count", "paired_seed_count",
    "unpaired_or_missing_seed_count", "mean_stressor_gap",
    "mean_control_gap", "mean_paired_gap_difference",
    "median_paired_gap_difference",
    "standard_deviation_paired_gap_difference",
    "minimum_paired_gap_difference", "p25_paired_gap_difference",
    "p75_paired_gap_difference", "maximum_paired_gap_difference",
    "ci95_lower", "ci95_upper", "difference_formula", "ci_method",
)
PRECISION_FIELDS = (
    "family", "strength", "strength_label", "algorithm_id", "algorithm",
    "estimand", "observed_paired_seed_count", "observed_standard_deviation",
    "observed_ci95_half_width", "target_ci95_half_width",
    "estimated_required_seed_count", "precision_status", "planning_method",
)


@dataclass(frozen=True)
class Level:
    family: str
    strength: float
    strength_label: str
    stressor_case_id: str
    control_case_id: str


@dataclass(frozen=True)
class Description:
    count: int
    mean: float | None
    median: float | None
    deviation: float | None
    minimum: float | None
    p25: float | None
    p75: float | None
    maximum: float | None
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class Unit:
    seed: int
    gap: float | None
    run_count: int


def fail(message: str) -> None:
    raise ValueError(message)


def load_design(path: Path) -> tuple[int, float, tuple[Level, ...]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        fail("cartography design schema is invalid")
    minimum = value.get("minimum_instance_seeds")
    target = value.get("precision_target_half_width")
    raw_levels = value.get("levels")
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or minimum < 2
        or isinstance(target, bool)
        or not isinstance(target, (int, float))
        or not math.isfinite(float(target))
        or float(target) <= 0
        or not isinstance(raw_levels, list)
    ):
        fail("cartography design controls are invalid")
    levels: list[Level] = []
    for raw in raw_levels:
        if not isinstance(raw, Mapping):
            fail("cartography design level is not an object")
        try:
            level = Level(
                family=str(raw["family"]),
                strength=float(raw["strength"]),
                strength_label=str(raw["strength_label"]),
                stressor_case_id=str(raw["stressor_case_id"]),
                control_case_id=str(raw["control_case_id"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("cartography design level is invalid") from error
        if level.family not in FAMILIES or not math.isfinite(level.strength):
            fail("cartography design level has an invalid family or strength")
        levels.append(level)
    return minimum, float(target), tuple(levels)


def load_runs(path: Path) -> list[RunRecord]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != RunRecord.CSV_FIELDS:
            fail("raw_results.csv header is invalid")
        return [RunRecord.from_csv_row(row) for row in reader]


def load_rows(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            fail(f"{path.name} header is invalid")
        return list(reader)


def quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _adaptive_simpson(
    function,
    left: float,
    right: float,
    left_value: float,
    midpoint_value: float,
    right_value: float,
    whole: float,
    tolerance: float,
    depth: int,
) -> float:
    midpoint = (left + right) / 2
    left_midpoint = (left + midpoint) / 2
    right_midpoint = (midpoint + right) / 2
    left_midpoint_value = function(left_midpoint)
    right_midpoint_value = function(right_midpoint)
    left_area = (midpoint - left) * (
        left_value + 4 * left_midpoint_value + midpoint_value
    ) / 6
    right_area = (right - midpoint) * (
        midpoint_value + 4 * right_midpoint_value + right_value
    ) / 6
    combined = left_area + right_area
    if depth <= 0 or abs(combined - whole) <= 15 * tolerance:
        return combined + (combined - whole) / 15
    return _adaptive_simpson(
        function,
        left,
        midpoint,
        left_value,
        left_midpoint_value,
        midpoint_value,
        left_area,
        tolerance / 2,
        depth - 1,
    ) + _adaptive_simpson(
        function,
        midpoint,
        right,
        midpoint_value,
        right_midpoint_value,
        right_value,
        right_area,
        tolerance / 2,
        depth - 1,
    )


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    if value == 0:
        return 0.5
    normalizer = math.exp(
        math.lgamma((degrees_of_freedom + 1) / 2)
        - math.lgamma(degrees_of_freedom / 2)
    ) / math.sqrt(degrees_of_freedom * math.pi)

    def density(point: float) -> float:
        return normalizer * (
            1 + point * point / degrees_of_freedom
        ) ** (-(degrees_of_freedom + 1) / 2)

    upper = abs(value)
    midpoint = upper / 2
    whole = upper * (density(0) + 4 * density(midpoint) + density(upper)) / 6
    integral = _adaptive_simpson(
        density,
        0.0,
        upper,
        density(0),
        density(midpoint),
        density(upper),
        whole,
        1e-13,
        24,
    )
    return 0.5 + integral if value > 0 else 0.5 - integral


@lru_cache(maxsize=None)
def student_t_critical_95(degrees_of_freedom: int) -> float:
    if degrees_of_freedom <= 0:
        fail("Student-t degrees of freedom must be positive")
    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < 0.975:
        upper *= 2
    for _ in range(64):
        midpoint = (lower + upper) / 2
        if _student_t_cdf(midpoint, degrees_of_freedom) < 0.975:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2


def validate_student_t_reference_points() -> None:
    references = {
        1: 12.7062047364,
        2: 4.3026527297,
        5: 2.5705818356,
        10: 2.2281388520,
        29: 2.0452296421,
        60: 2.0002978211,
    }
    for degrees_of_freedom, expected in references.items():
        actual = student_t_critical_95(degrees_of_freedom)
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=5e-9):
            fail(
                "independent Student-t implementation failed its reference "
                f"point for df={degrees_of_freedom}"
            )


def describe(values: Sequence[float]) -> Description:
    ordered = sorted(values)
    if not ordered:
        return Description(0, None, None, None, None, None, None, None, None, None)
    mean = statistics.fmean(ordered)
    deviation = statistics.stdev(ordered) if len(ordered) > 1 else None
    margin = (
        None
        if deviation is None
        else student_t_critical_95(len(ordered) - 1)
        * deviation
        / math.sqrt(len(ordered))
    )
    return Description(
        len(ordered),
        mean,
        statistics.median(ordered),
        deviation,
        ordered[0],
        quantile(ordered, 0.25),
        quantile(ordered, 0.75),
        ordered[-1],
        None if margin is None else mean - margin,
        None if margin is None else mean + margin,
    )


def recomputed_gap(row: RunRecord) -> float | None:
    if row.optimum is None or row.optimum <= 0 or row.coverage is None:
        expected = None
    else:
        expected = (row.optimum - row.coverage) / row.optimum
    if expected is None:
        if row.optimality_gap is not None:
            fail(f"raw gap unexpectedly present for {row.run_id}")
    elif row.optimality_gap is None or not math.isclose(
        row.optimality_gap, expected, rel_tol=0.0, abs_tol=5e-10
    ):
        fail(f"raw gap formula mismatch for {row.run_id}")
    return expected


def units_for(
    rows: Sequence[RunRecord],
    case_id: str,
    algorithm_id: str,
    expected_algorithm_seeds: tuple[int | None, ...],
) -> dict[int, Unit]:
    groups: dict[int, list[RunRecord]] = defaultdict(list)
    for row in rows:
        if row.case_id == case_id and row.algorithm_id == algorithm_id:
            groups[row.repetition].append(row)
    units: dict[int, Unit] = {}
    for repetition, group in groups.items():
        seeds = {row.seed for row in group}
        actual_algorithm_seeds = tuple(row.algorithm_seed for row in group)
        if len(seeds) != 1 or None in seeds:
            fail(f"inconsistent instance seeds for {case_id}/{algorithm_id}")
        if (
            len(actual_algorithm_seeds) != len(expected_algorithm_seeds)
            or len(set(actual_algorithm_seeds)) != len(actual_algorithm_seeds)
            or set(actual_algorithm_seeds) != set(expected_algorithm_seeds)
        ):
            fail(f"algorithm seed layout mismatch for {case_id}/{algorithm_id}")
        gaps = [recomputed_gap(row) for row in group]
        valid = [gap for gap in gaps if gap is not None]
        units[repetition] = Unit(
            seed=int(next(iter(seeds))),
            gap=(
                statistics.fmean(valid)
                if len(valid) == len(expected_algorithm_seeds)
                else None
            ),
            run_count=len(group),
        )
    return units


def unique_index(
    rows: Sequence[dict[str, str]], fields: tuple[str, ...], artifact: str
) -> dict[tuple[str, ...], dict[str, str]]:
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in result:
            fail(f"{artifact} contains duplicate key {key!r}")
        result[key] = row
    return result


def expect_text(row: Mapping[str, str], field: str, expected: object) -> None:
    if row.get(field) != str(expected):
        fail(f"{field} mismatch: expected {expected!r}, found {row.get(field)!r}")


def expect_number(
    row: Mapping[str, str], field: str, expected: float | None
) -> None:
    actual = row.get(field, "")
    if expected is None:
        if actual != "":
            fail(f"{field} must be blank")
        return
    try:
        numeric = float(actual)
    except ValueError as error:
        raise ValueError(f"{field} is not numeric") from error
    if not math.isclose(numeric, expected, rel_tol=0.0, abs_tol=5e-10):
        fail(f"{field} mismatch: expected {expected}, found {numeric}")


def expect_description(
    row: Mapping[str, str],
    description: Description,
    fields: tuple[str, ...],
) -> None:
    values = (
        description.mean,
        description.median,
        description.deviation,
        description.minimum,
        description.p25,
        description.p75,
        description.maximum,
        description.lower,
        description.upper,
    )
    for field, expected in zip(fields, values):
        expect_number(row, field, expected)


def required_count(deviation: float | None, target: float) -> int | None:
    if deviation is None:
        return None
    if deviation == 0:
        return 2
    def half_width(count: int) -> float:
        return student_t_critical_95(count - 1) * deviation / math.sqrt(count)

    if half_width(10_000) > target:
        return 10_001
    lower = 2
    upper = 10_000
    while lower < upper:
        midpoint = (lower + upper) // 2
        if half_width(midpoint) <= target:
            upper = midpoint
        else:
            lower = midpoint + 1
    return lower


def validate_manifest(
    output: Path, config_path: Path, design_path: Path, config: ExperimentConfig
) -> None:
    manifest = json.loads(
        (output / "cartography_manifest.json").read_text(encoding="utf-8")
    )
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1:
        fail("cartography manifest schema is invalid")
    expected = {
        "config_hash": config_hash(config),
        "config_sha256": file_sha256(config_path),
        "design_sha256": file_sha256(design_path),
        "raw_results_sha256": file_sha256(output / "raw_results.csv"),
        "gap_formula": "1-coverage/optimum",
        "paired_difference_formula": "stressor_gap-control_gap",
        "repetition_unit": "instance_seed",
        "algorithm_seed_role": "nested_within_instance",
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            fail(f"cartography manifest {field} mismatch")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != set(OUTPUTS):
        fail("cartography manifest output set is invalid")
    for filename in OUTPUTS:
        metadata = outputs[filename]
        if not isinstance(metadata, Mapping) or metadata.get("sha256") != file_sha256(
            output / filename
        ):
            fail(f"cartography manifest checksum mismatch for {filename}")


def validate(config_path: Path, design_path: Path, output: Path) -> None:
    validate_student_t_reference_points()
    config = load_config(config_path)
    minimum, target, levels = load_design(design_path)
    if config.repetitions < minimum:
        fail("configuration does not meet the cartography seed minimum")
    validate_manifest(output, config_path, design_path, config)
    rows = load_runs(output / "raw_results.csv")
    statistics_rows = load_rows(
        output / "structural_gap_statistics.csv", STATISTICS_FIELDS
    )
    paired_rows = load_rows(output / "paired_control_differences.csv", PAIRED_FIELDS)
    precision_rows = load_rows(output / "precision_diagnostics.csv", PRECISION_FIELDS)
    statistics_index = unique_index(
        statistics_rows, ("case_id", "algorithm_id", "group"), "gap statistics"
    )
    paired_index = unique_index(
        paired_rows,
        ("stressor_case_id", "control_case_id", "algorithm_id"),
        "paired differences",
    )
    precision_index = unique_index(
        precision_rows, ("family", "strength_label", "algorithm_id"), "precision"
    )
    algorithm_layout = {
        algorithm.name: (
            algorithm.algorithm_id,
            tuple(algorithm.algorithm_seeds) if algorithm.algorithm_seeds else (None,),
        )
        for algorithm in config.algorithms
        if algorithm.enabled and algorithm.name in ALGORITHMS_IN_REPORT
    }
    visited_statistics: set[tuple[str, ...]] = set()
    visited_paired: set[tuple[str, ...]] = set()
    visited_precision: set[tuple[str, ...]] = set()
    for level in sorted(
        levels, key=lambda item: (FAMILIES.index(item.family), item.strength)
    ):
        for algorithm in ALGORITHMS_IN_REPORT:
            if algorithm not in algorithm_layout:
                fail(f"missing algorithm variant {algorithm}")
            algorithm_id, algorithm_seeds = algorithm_layout[algorithm]
            treatment = units_for(
                rows, level.stressor_case_id, algorithm_id, algorithm_seeds
            )
            control = units_for(
                rows, level.control_case_id, algorithm_id, algorithm_seeds
            )
            for group_name, case_id, paired_id, units in (
                ("stressor", level.stressor_case_id, level.control_case_id, treatment),
                ("control", level.control_case_id, level.stressor_case_id, control),
            ):
                key = (case_id, algorithm_id, group_name)
                row = statistics_index.get(key)
                if row is None:
                    fail(f"missing structural gap row {key!r}")
                visited_statistics.add(key)
                gaps = [unit.gap for unit in units.values() if unit.gap is not None]
                description = describe(gaps)
                for field, value in (
                    ("family", level.family),
                    ("strength_label", level.strength_label),
                    ("group", group_name),
                    ("case_id", case_id),
                    ("paired_case_id", paired_id),
                    ("algorithm_id", algorithm_id),
                    ("algorithm", algorithm),
                    ("expected_instance_seed_count", config.repetitions),
                    ("observed_instance_seed_count", len(units)),
                    ("algorithm_seed_count", len(algorithm_seeds)),
                    ("run_count", sum(unit.run_count for unit in units.values())),
                    ("valid_gap_count", description.count),
                    ("missing_gap_count", config.repetitions - description.count),
                    ("ci_method", "student_t_two_sided"),
                ):
                    expect_text(row, field, value)
                expect_number(row, "strength", level.strength)
                expect_description(
                    row,
                    description,
                    (
                        "mean_gap",
                        "median_gap",
                        "standard_deviation_gap",
                        "minimum_gap",
                        "p25_gap",
                        "p75_gap",
                        "maximum_gap",
                        "ci95_lower",
                        "ci95_upper",
                    ),
                )

            paired_key = (
                level.stressor_case_id,
                level.control_case_id,
                algorithm_id,
            )
            paired = paired_index.get(paired_key)
            if paired is None:
                fail(f"missing paired difference row {paired_key!r}")
            visited_paired.add(paired_key)
            treatment_values: list[float] = []
            control_values: list[float] = []
            differences: list[float] = []
            for repetition in sorted(set(treatment) & set(control)):
                left = treatment[repetition]
                right = control[repetition]
                if left.seed != right.seed:
                    fail(f"paired seed mismatch at repetition {repetition}")
                if left.gap is not None and right.gap is not None:
                    treatment_values.append(left.gap)
                    control_values.append(right.gap)
                    differences.append(left.gap - right.gap)
            description = describe(differences)
            for field, value in (
                ("family", level.family),
                ("strength_label", level.strength_label),
                ("stressor_case_id", level.stressor_case_id),
                ("control_case_id", level.control_case_id),
                ("algorithm_id", algorithm_id),
                ("algorithm", algorithm),
                ("expected_paired_seed_count", config.repetitions),
                (
                    "stressor_valid_seed_count",
                    sum(unit.gap is not None for unit in treatment.values()),
                ),
                (
                    "control_valid_seed_count",
                    sum(unit.gap is not None for unit in control.values()),
                ),
                ("paired_seed_count", description.count),
                (
                    "unpaired_or_missing_seed_count",
                    config.repetitions - description.count,
                ),
                ("difference_formula", "stressor_gap-control_gap"),
                ("ci_method", "paired_student_t_two_sided"),
            ):
                expect_text(paired, field, value)
            expect_number(paired, "strength", level.strength)
            expect_number(
                paired,
                "mean_stressor_gap",
                statistics.fmean(treatment_values) if treatment_values else None,
            )
            expect_number(
                paired,
                "mean_control_gap",
                statistics.fmean(control_values) if control_values else None,
            )
            expect_description(
                paired,
                description,
                (
                    "mean_paired_gap_difference",
                    "median_paired_gap_difference",
                    "standard_deviation_paired_gap_difference",
                    "minimum_paired_gap_difference",
                    "p25_paired_gap_difference",
                    "p75_paired_gap_difference",
                    "maximum_paired_gap_difference",
                    "ci95_lower",
                    "ci95_upper",
                ),
            )

            precision_key = (level.family, level.strength_label, algorithm_id)
            precision = precision_index.get(precision_key)
            if precision is None:
                fail(f"missing precision row {precision_key!r}")
            visited_precision.add(precision_key)
            required = required_count(description.deviation, target)
            half_width = (
                None
                if description.lower is None or description.upper is None
                else (description.upper - description.lower) / 2
            )
            status = (
                "not_estimable"
                if required is None
                else "adequate"
                if description.count >= required
                else "increase_seeds"
            )
            for field, value in (
                ("family", level.family),
                ("strength_label", level.strength_label),
                ("algorithm_id", algorithm_id),
                ("algorithm", algorithm),
                ("estimand", "mean_paired_gap_difference"),
                ("observed_paired_seed_count", description.count),
                ("estimated_required_seed_count", "" if required is None else required),
                ("precision_status", status),
                ("planning_method", "observed_sd_student_t_fixed_half_width"),
            ):
                expect_text(precision, field, value)
            expect_number(precision, "strength", level.strength)
            expect_number(
                precision, "observed_standard_deviation", description.deviation
            )
            expect_number(precision, "observed_ci95_half_width", half_width)
            expect_number(precision, "target_ci95_half_width", target)

    if len(visited_statistics) != len(statistics_rows):
        fail("structural gap statistics contain unexpected rows")
    if len(visited_paired) != len(paired_rows):
        fail("paired differences contain unexpected rows")
    if len(visited_precision) != len(precision_rows):
        fail("precision diagnostics contain unexpected rows")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        validate(args.config.resolve(), args.design.resolve(), args.output.resolve())
    except (csv.Error, KeyError, OSError, TypeError, ValueError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    sys.stdout.write("Cartography artifact validation passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
