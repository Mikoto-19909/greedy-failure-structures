"""Structural associations for benchmark instance records."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from statistics import fmean

from .benchmark_statistics import _ten_decimal
from .contracts import (
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
    GapClusteringAssociationRecord,
    InstanceRecord,
    RunRecord,
    RuntimeSetCountAssociationRecord,
    RuntimeKAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
)
from .model import SolutionStatus


def _gap_density_association_statistics(
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord],
) -> list[GapDensityAssociationRecord]:
    """Associate instance-equal relative gaps with actual density by family."""

    instance_by_unit: dict[
        tuple[str, str, int, str], InstanceRecord
    ] = {}
    for supplied_instance in instances:
        unit = (
            supplied_instance.config_hash,
            supplied_instance.case_id,
            supplied_instance.repetition,
            supplied_instance.instance_id,
        )
        if unit in instance_by_unit:
            raise ValueError(
                "gap-density association requires unique instance records"
            )
        instance_by_unit[unit] = supplied_instance

    groups: dict[
        tuple[str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    records: list[GapDensityAssociationRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, family, algorithm_id, algorithm = key
        units: dict[
            tuple[str, str, int, str], list[RunRecord]
        ] = defaultdict(list)
        for row in group:
            unit = (
                row.config_hash,
                row.case_id,
                row.repetition,
                row.instance_id,
            )
            instance = instance_by_unit.get(unit)
            if instance is None:
                raise ValueError(
                    "gap-density association row has no matching instance"
                )
            if instance.family != row.family:
                raise ValueError(
                    "gap-density association family conflicts with instance"
                )
            units[unit].append(row)

        expected_seed_layout: tuple[int | None, ...] | None = None
        densities: list[float] = []
        gaps: list[float] = []
        valid_reference_count = 0
        zero_optimum_count = 0
        no_reference_count = 0
        unusable_result_count = 0
        for unit, unit_rows in sorted(units.items()):
            seeds = [row.algorithm_seed for row in unit_rows]
            if len(set(seeds)) != len(seeds):
                raise ValueError(
                    "gap-density association requires unique algorithm seeds "
                    "within each instance"
                )
            if any(seed is None for seed in seeds) and any(
                seed is not None for seed in seeds
            ):
                raise ValueError(
                    "gap-density association cannot mix seeded and unseeded "
                    "runs within one instance"
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
                    "gap-density association requires a fixed algorithm-seed "
                    "layout across pooled instances"
                )

            references = {row.optimum for row in unit_rows}
            if len(references) != 1:
                raise ValueError(
                    "gap-density association requires one normalized exact "
                    "reference per instance"
                )
            reference = next(iter(references))
            if reference is None:
                no_reference_count += 1
                continue
            if reference < 0:
                raise ValueError(
                    "gap-density association exact references must be "
                    "non-negative"
                )
            valid_reference_count += 1
            if reference == 0:
                zero_optimum_count += 1
                continue

            unit_gaps = [
                row.optimality_gap
                for row in unit_rows
                if row.optimality_gap is not None
            ]
            if not unit_gaps:
                unusable_result_count += 1
                continue
            if any(not 0 <= gap <= 1 for gap in unit_gaps):
                raise ValueError(
                    "gap-density association gaps must be between 0 and 1"
                )
            instance = instance_by_unit[unit]
            densities.append(_ten_decimal(instance.actual_density))
            gaps.append(
                _ten_decimal(
                    fmean(gap for gap in unit_gaps if gap is not None)
                )
            )

        sample_count = len(densities)
        distinct_density_count = len(set(densities))
        if sample_count == 0:
            mean_density = None
            mean_gap = None
            density_sd = None
            gap_sd = None
            correlation = None
            slope = None
            intercept = None
            status = "no_samples"
        else:
            raw_mean_density = fmean(densities)
            raw_mean_gap = fmean(gaps)
            mean_density = _ten_decimal(raw_mean_density)
            mean_gap = _ten_decimal(raw_mean_gap)
            if sample_count == 1:
                density_sd = None
                gap_sd = None
                correlation = None
                slope = None
                intercept = None
                status = "insufficient_samples"
            else:
                centered_density = [
                    value - raw_mean_density for value in densities
                ]
                centered_gap = [value - raw_mean_gap for value in gaps]
                density_sum_squares = sum(
                    value * value for value in centered_density
                )
                gap_sum_squares = sum(
                    value * value for value in centered_gap
                )
                cross_product = sum(
                    density_value * gap_value
                    for density_value, gap_value in zip(
                        centered_density,
                        centered_gap,
                        strict=True,
                    )
                )
                density_sd = _ten_decimal(
                    math.sqrt(density_sum_squares / (sample_count - 1))
                )
                gap_sd = _ten_decimal(
                    math.sqrt(gap_sum_squares / (sample_count - 1))
                )
                if density_sum_squares == 0:
                    correlation = None
                    slope = None
                    intercept = None
                    status = "constant_density"
                elif gap_sum_squares == 0:
                    correlation = None
                    slope = 0.0
                    intercept = mean_gap
                    status = "constant_gap"
                else:
                    raw_correlation = cross_product / math.sqrt(
                        density_sum_squares * gap_sum_squares
                    )
                    correlation = _ten_decimal(
                        min(1.0, max(-1.0, raw_correlation))
                    )
                    slope = _ten_decimal(
                        cross_product / density_sum_squares
                    )
                    intercept = _ten_decimal(
                        raw_mean_gap
                        - (cross_product / density_sum_squares)
                        * raw_mean_density
                    )
                    status = "estimable"

        case_ids = tuple(sorted({row.case_id for row in group}))
        records.append(
            GapDensityAssociationRecord(
                config_hash=config_identifier,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                predictor="actual_density",
                response="relative_optimality_gap",
                repetition_unit="instance_seed",
                case_count=len(case_ids),
                case_ids=case_ids,
                instance_count=len(units),
                run_count=len(group),
                timeout_count=sum(
                    row.status is SolutionStatus.TIMEOUT for row in group
                ),
                error_count=sum(
                    row.status is SolutionStatus.ERROR for row in group
                ),
                valid_exact_reference_count=valid_reference_count,
                zero_optimum_count=zero_optimum_count,
                no_exact_reference_count=no_reference_count,
                unusable_result_count=unusable_result_count,
                eligible_instance_count=sample_count,
                distinct_density_count=distinct_density_count,
                mean_actual_density=mean_density,
                mean_relative_gap=mean_gap,
                density_sample_standard_deviation=density_sd,
                gap_sample_standard_deviation=gap_sd,
                pearson_correlation=correlation,
                ols_slope=slope,
                ols_intercept=intercept,
                association_status=status,
            )
        )
    return records


def _gap_overlap_association_statistics(
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord],
) -> list[GapOverlapAssociationRecord]:
    """Associate instance-equal relative gaps with measured overlap by family."""

    instance_by_unit: dict[
        tuple[str, str, int, str], InstanceRecord
    ] = {}
    for supplied_instance in instances:
        unit = (
            supplied_instance.config_hash,
            supplied_instance.case_id,
            supplied_instance.repetition,
            supplied_instance.instance_id,
        )
        if unit in instance_by_unit:
            raise ValueError(
                "gap-overlap association requires unique instance records"
            )
        instance_by_unit[unit] = supplied_instance

    groups: dict[
        tuple[str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    records: list[GapOverlapAssociationRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, family, algorithm_id, algorithm = key
        units: dict[
            tuple[str, str, int, str], list[RunRecord]
        ] = defaultdict(list)
        for row in group:
            unit = (
                row.config_hash,
                row.case_id,
                row.repetition,
                row.instance_id,
            )
            instance = instance_by_unit.get(unit)
            if instance is None:
                raise ValueError(
                    "gap-overlap association row has no matching instance"
                )
            if instance.family != row.family:
                raise ValueError(
                    "gap-overlap association family conflicts with instance"
                )
            units[unit].append(row)

        expected_seed_layout: tuple[int | None, ...] | None = None
        overlaps: list[float] = []
        gaps: list[float] = []
        valid_reference_count = 0
        zero_optimum_count = 0
        no_reference_count = 0
        unusable_result_count = 0
        missing_overlap_count = 0
        for unit, unit_rows in sorted(units.items()):
            seeds = [row.algorithm_seed for row in unit_rows]
            if len(set(seeds)) != len(seeds):
                raise ValueError(
                    "gap-overlap association requires unique algorithm seeds "
                    "within each instance"
                )
            if any(seed is None for seed in seeds) and any(
                seed is not None for seed in seeds
            ):
                raise ValueError(
                    "gap-overlap association cannot mix seeded and unseeded "
                    "runs within one instance"
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
                    "gap-overlap association requires a fixed algorithm-seed "
                    "layout across pooled instances"
                )

            references = {row.optimum for row in unit_rows}
            if len(references) != 1:
                raise ValueError(
                    "gap-overlap association requires one normalized exact "
                    "reference per instance"
                )
            reference = next(iter(references))
            if reference is None:
                no_reference_count += 1
                continue
            if reference < 0:
                raise ValueError(
                    "gap-overlap association exact references must be "
                    "non-negative"
                )
            valid_reference_count += 1
            if reference == 0:
                zero_optimum_count += 1
                continue

            unit_gaps = [
                row.optimality_gap
                for row in unit_rows
                if row.optimality_gap is not None
            ]
            if not unit_gaps:
                unusable_result_count += 1
                continue
            if any(not 0 <= gap <= 1 for gap in unit_gaps):
                raise ValueError(
                    "gap-overlap association gaps must be between 0 and 1"
                )
            instance = instance_by_unit[unit]
            overlap = instance.pairwise_overlap_mean_jaccard
            if overlap is None:
                missing_overlap_count += 1
                continue
            overlaps.append(_ten_decimal(overlap))
            gaps.append(
                _ten_decimal(
                    fmean(gap for gap in unit_gaps if gap is not None)
                )
            )

        sample_count = len(overlaps)
        distinct_overlap_count = len(set(overlaps))
        if sample_count == 0:
            mean_overlap = None
            mean_gap = None
            overlap_sd = None
            gap_sd = None
            correlation = None
            slope = None
            intercept = None
            status = "no_samples"
        else:
            raw_mean_overlap = fmean(overlaps)
            raw_mean_gap = fmean(gaps)
            mean_overlap = _ten_decimal(raw_mean_overlap)
            mean_gap = _ten_decimal(raw_mean_gap)
            if sample_count == 1:
                overlap_sd = None
                gap_sd = None
                correlation = None
                slope = None
                intercept = None
                status = "insufficient_samples"
            else:
                centered_overlap = [
                    value - raw_mean_overlap for value in overlaps
                ]
                centered_gap = [value - raw_mean_gap for value in gaps]
                overlap_sum_squares = sum(
                    value * value for value in centered_overlap
                )
                gap_sum_squares = sum(
                    value * value for value in centered_gap
                )
                cross_product = sum(
                    overlap_value * gap_value
                    for overlap_value, gap_value in zip(
                        centered_overlap,
                        centered_gap,
                        strict=True,
                    )
                )
                overlap_sd = _ten_decimal(
                    math.sqrt(overlap_sum_squares / (sample_count - 1))
                )
                gap_sd = _ten_decimal(
                    math.sqrt(gap_sum_squares / (sample_count - 1))
                )
                if overlap_sd == 0:
                    correlation = None
                    slope = None
                    intercept = None
                    status = "constant_overlap"
                elif gap_sd == 0:
                    correlation = None
                    slope = 0.0
                    intercept = mean_gap
                    status = "constant_gap"
                else:
                    raw_correlation = cross_product / math.sqrt(
                        overlap_sum_squares * gap_sum_squares
                    )
                    correlation = _ten_decimal(
                        min(1.0, max(-1.0, raw_correlation))
                    )
                    slope = _ten_decimal(
                        cross_product / overlap_sum_squares
                    )
                    intercept = _ten_decimal(
                        raw_mean_gap
                        - (cross_product / overlap_sum_squares)
                        * raw_mean_overlap
                    )
                    status = "estimable"

        case_ids = tuple(sorted({row.case_id for row in group}))
        records.append(
            GapOverlapAssociationRecord(
                config_hash=config_identifier,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                predictor="pairwise_overlap_mean_jaccard",
                response="relative_optimality_gap",
                repetition_unit="instance_seed",
                case_count=len(case_ids),
                case_ids=case_ids,
                instance_count=len(units),
                run_count=len(group),
                timeout_count=sum(
                    row.status is SolutionStatus.TIMEOUT for row in group
                ),
                error_count=sum(
                    row.status is SolutionStatus.ERROR for row in group
                ),
                valid_exact_reference_count=valid_reference_count,
                zero_optimum_count=zero_optimum_count,
                no_exact_reference_count=no_reference_count,
                unusable_result_count=unusable_result_count,
                missing_overlap_predictor_count=missing_overlap_count,
                eligible_instance_count=sample_count,
                distinct_overlap_count=distinct_overlap_count,
                mean_pairwise_overlap_jaccard=mean_overlap,
                mean_relative_gap=mean_gap,
                overlap_sample_standard_deviation=overlap_sd,
                gap_sample_standard_deviation=gap_sd,
                pearson_correlation=correlation,
                ols_slope=slope,
                ols_intercept=intercept,
                association_status=status,
            )
        )
    return records


def _gap_clustering_association_statistics(
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord],
) -> list[GapClusteringAssociationRecord]:
    """Associate mixed-cluster level-mean gaps with realized bridge fraction."""

    instance_by_unit: dict[
        tuple[str, str, int, str], InstanceRecord
    ] = {}
    for supplied_instance in instances:
        unit = (
            supplied_instance.config_hash,
            supplied_instance.case_id,
            supplied_instance.repetition,
            supplied_instance.instance_id,
        )
        if unit in instance_by_unit:
            raise ValueError(
                "gap-clustering association requires unique instance records"
            )
        instance_by_unit[unit] = supplied_instance

    groups: dict[
        tuple[str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        if row.family != "mixed_cluster":
            continue
        groups[
            (
                row.config_hash,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    records: list[GapClusteringAssociationRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, family, algorithm_id, algorithm = key
        units: dict[
            tuple[str, str, int, str], list[RunRecord]
        ] = defaultdict(list)
        block_units: dict[
            tuple[str, int], dict[str, tuple[str, str, int, str]]
        ] = defaultdict(dict)
        case_levels: dict[str, float] = {}
        id_to_seed: dict[str, int] = {}
        seed_to_id: dict[int, str] = {}

        for row in group:
            unit = (
                row.config_hash,
                row.case_id,
                row.repetition,
                row.instance_id,
            )
            instance = instance_by_unit.get(unit)
            if instance is None:
                raise ValueError(
                    "gap-clustering association row has no matching instance"
                )
            if instance.family != "mixed_cluster":
                raise ValueError(
                    "gap-clustering association requires mixed_cluster instances"
                )
            if instance.research_question_id != "mixed_cluster_bridges":
                raise ValueError(
                    "gap-clustering association requires the mixed-cluster "
                    "bridge research question"
                )
            coupling_id = instance.coupling_pair_id
            coupling_seed = instance.coupling_seed
            if coupling_id is None or coupling_seed is None:
                raise ValueError(
                    "gap-clustering association requires coupling identity"
                )
            existing_seed = id_to_seed.setdefault(coupling_id, coupling_seed)
            if existing_seed != coupling_seed:
                raise ValueError(
                    "gap-clustering coupling ID maps to multiple seeds"
                )
            existing_id = seed_to_id.setdefault(coupling_seed, coupling_id)
            if existing_id != coupling_id:
                raise ValueError(
                    "gap-clustering coupling seed maps to multiple IDs"
                )
            try:
                parameters = json.loads(instance.parameters)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "gap-clustering instance parameters must be JSON"
                ) from error
            if not isinstance(parameters, dict):
                raise ValueError(
                    "gap-clustering instance parameters must be an object"
                )
            realized = parameters.get("realized_bridge_fraction")
            if (
                isinstance(realized, bool)
                or not isinstance(realized, (int, float))
                or not math.isfinite(realized)
                or not 0 <= realized <= 1
            ):
                raise ValueError(
                    "gap-clustering requires a finite realized bridge fraction"
                )
            level = _ten_decimal(float(realized))
            previous_level = case_levels.setdefault(row.case_id, level)
            if previous_level != level:
                raise ValueError(
                    "gap-clustering Case level changes across coupling blocks"
                )

            units[unit].append(row)
            block = (coupling_id, coupling_seed)
            previous_unit = block_units[block].setdefault(row.case_id, unit)
            if previous_unit != unit:
                raise ValueError(
                    "gap-clustering block has multiple instances for one Case"
                )

        case_ids = tuple(sorted(case_levels))
        expected_case_set = set(case_ids)
        for block, by_case in block_units.items():
            if set(by_case) != expected_case_set:
                raise ValueError(
                    "gap-clustering requires a fixed Case-level layout "
                    "across coupling blocks"
                )
            if len(by_case) != len(case_ids):
                raise ValueError(
                    "gap-clustering block contains duplicate Case levels"
                )

        expected_seed_layout: tuple[int | None, ...] | None = None
        gap_by_unit: dict[tuple[str, str, int, str], float | None] = {}
        valid_reference_count = 0
        zero_optimum_count = 0
        no_reference_count = 0
        unusable_result_count = 0
        usable_gap_count = 0
        for unit, unit_rows in sorted(units.items()):
            seeds = [row.algorithm_seed for row in unit_rows]
            if len(set(seeds)) != len(seeds):
                raise ValueError(
                    "gap-clustering association requires unique algorithm "
                    "seeds within each instance"
                )
            if any(seed is None for seed in seeds) and any(
                seed is not None for seed in seeds
            ):
                raise ValueError(
                    "gap-clustering association cannot mix seeded and "
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
                    "gap-clustering association requires a fixed "
                    "algorithm-seed layout"
                )

            references = {row.optimum for row in unit_rows}
            if len(references) != 1:
                raise ValueError(
                    "gap-clustering association requires one normalized "
                    "exact reference per instance"
                )
            reference = next(iter(references))
            if reference is None:
                no_reference_count += 1
                gap_by_unit[unit] = None
                continue
            if reference < 0:
                raise ValueError(
                    "gap-clustering exact references must be non-negative"
                )
            valid_reference_count += 1
            if reference == 0:
                zero_optimum_count += 1
                gap_by_unit[unit] = None
                continue
            unit_gaps = [
                row.optimality_gap
                for row in unit_rows
                if row.optimality_gap is not None
            ]
            if not unit_gaps:
                unusable_result_count += 1
                gap_by_unit[unit] = None
                continue
            if any(not 0 <= gap <= 1 for gap in unit_gaps):
                raise ValueError(
                    "gap-clustering gaps must be between 0 and 1"
                )
            usable_gap_count += 1
            gap_by_unit[unit] = _ten_decimal(
                fmean(gap for gap in unit_gaps if gap is not None)
            )

        eligible_blocks: list[tuple[str, int]] = []
        for block, by_case in sorted(block_units.items()):
            if all(gap_by_unit[by_case[case_id]] is not None for case_id in case_ids):
                eligible_blocks.append(block)
        block_count = len(block_units)
        eligible_block_count = len(eligible_blocks)
        incomplete_block_count = block_count - eligible_block_count
        clustering_levels = tuple(case_levels[case_id] for case_id in case_ids)
        distinct_level_count = len(set(clustering_levels))

        if eligible_block_count == 0:
            mean_predictor = None
            mean_gap = None
            predictor_sd = None
            gap_sd = None
            correlation = None
            slope = None
            intercept = None
            status = "no_complete_blocks"
        else:
            level_gaps: list[float] = []
            for case_id in case_ids:
                values = [
                    gap_by_unit[block_units[block][case_id]]
                    for block in eligible_blocks
                ]
                level_gaps.append(
                    _ten_decimal(
                        fmean(value for value in values if value is not None)
                    )
                )
            raw_mean_predictor = fmean(clustering_levels)
            raw_mean_gap = fmean(level_gaps)
            mean_predictor = _ten_decimal(raw_mean_predictor)
            mean_gap = _ten_decimal(raw_mean_gap)
            if len(case_ids) == 1:
                predictor_sd = None
                gap_sd = None
                correlation = None
                slope = None
                intercept = None
                status = "insufficient_levels"
            else:
                centered_predictor = [
                    value - raw_mean_predictor for value in clustering_levels
                ]
                centered_gap = [value - raw_mean_gap for value in level_gaps]
                predictor_sum_squares = sum(
                    value * value for value in centered_predictor
                )
                gap_sum_squares = sum(value * value for value in centered_gap)
                cross_product = sum(
                    predictor_value * gap_value
                    for predictor_value, gap_value in zip(
                        centered_predictor,
                        centered_gap,
                        strict=True,
                    )
                )
                predictor_sd = _ten_decimal(
                    math.sqrt(
                        predictor_sum_squares / (len(case_ids) - 1)
                    )
                )
                gap_sd = _ten_decimal(
                    math.sqrt(gap_sum_squares / (len(case_ids) - 1))
                )
                if predictor_sd == 0:
                    correlation = None
                    slope = None
                    intercept = None
                    status = "constant_clustering"
                elif gap_sd == 0:
                    correlation = None
                    slope = 0.0
                    intercept = mean_gap
                    status = "constant_gap"
                else:
                    raw_correlation = cross_product / math.sqrt(
                        predictor_sum_squares * gap_sum_squares
                    )
                    correlation = _ten_decimal(
                        min(1.0, max(-1.0, raw_correlation))
                    )
                    slope = _ten_decimal(
                        cross_product / predictor_sum_squares
                    )
                    intercept = _ten_decimal(
                        raw_mean_gap
                        - (cross_product / predictor_sum_squares)
                        * raw_mean_predictor
                    )
                    status = "estimable"

        records.append(
            GapClusteringAssociationRecord(
                config_hash=config_identifier,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                predictor="realized_bridge_fraction",
                response="level_mean_relative_optimality_gap",
                repetition_unit="coupling_seed_block",
                case_count=len(case_ids),
                case_ids=case_ids,
                clustering_levels=clustering_levels,
                instance_count=len(units),
                run_count=len(group),
                independent_block_count=block_count,
                clustering_level_count=len(case_ids),
                distinct_clustering_level_count=distinct_level_count,
                eligible_block_count=eligible_block_count,
                incomplete_block_count=incomplete_block_count,
                timeout_count=sum(
                    row.status is SolutionStatus.TIMEOUT for row in group
                ),
                error_count=sum(
                    row.status is SolutionStatus.ERROR for row in group
                ),
                valid_exact_reference_count=valid_reference_count,
                zero_optimum_count=zero_optimum_count,
                no_exact_reference_count=no_reference_count,
                unusable_result_count=unusable_result_count,
                usable_gap_instance_count=usable_gap_count,
                eligible_instance_count=(
                    eligible_block_count * len(case_ids)
                ),
                mean_realized_bridge_fraction=mean_predictor,
                mean_level_relative_gap=mean_gap,
                bridge_fraction_sample_standard_deviation=predictor_sd,
                gap_level_mean_sample_standard_deviation=gap_sd,
                pearson_correlation=correlation,
                ols_slope=slope,
                ols_intercept=intercept,
                association_status=status,
            )
        )
    return records


def _runtime_set_count_association_statistics(
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord | _RuntimeKInstanceProjection],
) -> list[RuntimeSetCountAssociationRecord]:
    """Associate complete instance runtimes with set count by family."""

    instance_by_unit: dict[
        tuple[str, str, int, str], InstanceRecord | _RuntimeKInstanceProjection
    ] = {}
    for supplied_instance in instances:
        unit = (
            supplied_instance.config_hash,
            supplied_instance.case_id,
            supplied_instance.repetition,
            supplied_instance.instance_id,
        )
        if unit in instance_by_unit:
            raise ValueError(
                "runtime-set-count association requires unique instances"
            )
        instance_by_unit[unit] = supplied_instance

    groups: dict[
        tuple[str, str, str, str], list[RunRecord]
    ] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.config_hash,
                row.family,
                row.algorithm_id,
                row.algorithm,
            )
        ].append(row)

    completed_statuses = {SolutionStatus.OPTIMAL, SolutionStatus.FEASIBLE}
    records: list[RuntimeSetCountAssociationRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, family, algorithm_id, algorithm = key
        units: dict[
            tuple[str, str, int, str], list[RunRecord]
        ] = defaultdict(list)
        for row in group:
            unit = (
                row.config_hash,
                row.case_id,
                row.repetition,
                row.instance_id,
            )
            instance = instance_by_unit.get(unit)
            if instance is None:
                raise ValueError(
                    "runtime-set-count association row has no matching instance"
                )
            if instance.family != row.family:
                raise ValueError(
                    "runtime-set-count association family conflicts with instance"
                )
            if instance.set_count != row.set_count:
                raise ValueError(
                    "runtime-set-count association set count conflicts with instance"
                )
            units[unit].append(row)

        expected_seed_layout: tuple[int | None, ...] | None = None
        set_counts: list[float] = []
        runtimes: list[float] = []
        incomplete_instance_count = 0
        for unit, unit_rows in sorted(units.items()):
            seeds = [row.algorithm_seed for row in unit_rows]
            if len(set(seeds)) != len(seeds):
                raise ValueError(
                    "runtime-set-count association requires unique algorithm "
                    "seeds within each instance"
                )
            if any(seed is None for seed in seeds) and any(
                seed is not None for seed in seeds
            ):
                raise ValueError(
                    "runtime-set-count association cannot mix seeded and "
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
                    "runtime-set-count association requires a fixed "
                    "algorithm-seed layout across pooled instances"
                )

            if any(row.status not in completed_statuses for row in unit_rows):
                incomplete_instance_count += 1
                continue
            unit_runtimes = [row.runtime_seconds for row in unit_rows]
            if any(
                not math.isfinite(runtime) or runtime < 0
                for runtime in unit_runtimes
            ):
                raise ValueError(
                    "runtime-set-count association completed runtimes must "
                    "be finite and non-negative"
                )
            instance = instance_by_unit[unit]
            set_counts.append(_ten_decimal(float(instance.set_count)))
            runtimes.append(_ten_decimal(fmean(unit_runtimes)))

        sample_count = len(set_counts)
        distinct_set_count = len(set(set_counts))
        if sample_count == 0:
            mean_set_count = None
            mean_runtime = None
            set_count_sd = None
            runtime_sd = None
            correlation = None
            slope = None
            intercept = None
            status = "no_samples"
        else:
            raw_mean_set_count = fmean(set_counts)
            raw_mean_runtime = fmean(runtimes)
            mean_set_count = _ten_decimal(raw_mean_set_count)
            mean_runtime = _ten_decimal(raw_mean_runtime)
            if sample_count == 1:
                set_count_sd = None
                runtime_sd = None
                correlation = None
                slope = None
                intercept = None
                status = "insufficient_samples"
            else:
                centered_set_counts = [
                    value - raw_mean_set_count for value in set_counts
                ]
                centered_runtimes = [
                    value - raw_mean_runtime for value in runtimes
                ]
                set_count_sum_squares = sum(
                    value * value for value in centered_set_counts
                )
                runtime_sum_squares = sum(
                    value * value for value in centered_runtimes
                )
                cross_product = sum(
                    set_count_value * runtime_value
                    for set_count_value, runtime_value in zip(
                        centered_set_counts,
                        centered_runtimes,
                        strict=True,
                    )
                )
                set_count_sd = _ten_decimal(
                    math.sqrt(set_count_sum_squares / (sample_count - 1))
                )
                runtime_sd = _ten_decimal(
                    math.sqrt(runtime_sum_squares / (sample_count - 1))
                )
                if set_count_sd == 0:
                    correlation = None
                    slope = None
                    intercept = None
                    status = "constant_set_count"
                elif runtime_sd == 0:
                    correlation = None
                    slope = 0.0
                    intercept = mean_runtime
                    status = "constant_runtime"
                else:
                    raw_correlation = cross_product / math.sqrt(
                        set_count_sum_squares * runtime_sum_squares
                    )
                    correlation = _ten_decimal(
                        min(1.0, max(-1.0, raw_correlation))
                    )
                    raw_slope = cross_product / set_count_sum_squares
                    slope = _ten_decimal(raw_slope)
                    intercept = _ten_decimal(
                        raw_mean_runtime
                        - raw_slope * raw_mean_set_count
                    )
                    status = "estimable"

        case_ids = tuple(sorted({row.case_id for row in group}))
        records.append(
            RuntimeSetCountAssociationRecord(
                config_hash=config_identifier,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                predictor="set_count",
                response="mean_completed_runtime_seconds",
                repetition_unit="instance_seed",
                case_count=len(case_ids),
                case_ids=case_ids,
                instance_count=len(units),
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
                incomplete_runtime_instance_count=incomplete_instance_count,
                eligible_instance_count=sample_count,
                distinct_set_count=distinct_set_count,
                mean_set_count=mean_set_count,
                mean_runtime_seconds=mean_runtime,
                set_count_sample_standard_deviation=set_count_sd,
                runtime_sample_standard_deviation_seconds=runtime_sd,
                pearson_correlation=correlation,
                ols_slope_seconds_per_set=slope,
                ols_intercept_seconds=intercept,
                association_status=status,
            )
        )
    return records


@dataclass(frozen=True, slots=True)
class _RuntimeKInstanceProjection:
    """Minimal instance view that reuses the runtime association estimator."""

    config_hash: str
    case_id: str
    repetition: int
    instance_id: str
    family: str
    set_count: int


def _runtime_k_association_statistics(
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord],
) -> list[RuntimeKAssociationRecord]:
    """Associate complete instance runtimes with selection budget by family."""

    projected_rows = [replace(row, set_count=row.k) for row in rows]
    projected_instances = [
        _RuntimeKInstanceProjection(
            config_hash=instance.config_hash,
            case_id=instance.case_id,
            repetition=instance.repetition,
            instance_id=instance.instance_id,
            family=instance.family,
            set_count=instance.k,
        )
        for instance in instances
    ]
    projected_records = _runtime_set_count_association_statistics(
        projected_rows,
        projected_instances,
    )
    return [
        RuntimeKAssociationRecord(
            config_hash=record.config_hash,
            family=record.family,
            algorithm_id=record.algorithm_id,
            algorithm=record.algorithm,
            predictor="k",
            response=record.response,
            repetition_unit=record.repetition_unit,
            case_count=record.case_count,
            case_ids=record.case_ids,
            instance_count=record.instance_count,
            run_count=record.run_count,
            completed_run_count=record.completed_run_count,
            timeout_count=record.timeout_count,
            error_count=record.error_count,
            incomplete_runtime_instance_count=(
                record.incomplete_runtime_instance_count
            ),
            eligible_instance_count=record.eligible_instance_count,
            distinct_k_count=record.distinct_set_count,
            mean_k=record.mean_set_count,
            mean_runtime_seconds=record.mean_runtime_seconds,
            k_sample_standard_deviation=(
                record.set_count_sample_standard_deviation
            ),
            runtime_sample_standard_deviation_seconds=(
                record.runtime_sample_standard_deviation_seconds
            ),
            pearson_correlation=record.pearson_correlation,
            ols_slope_seconds_per_budget_unit=(
                record.ols_slope_seconds_per_set
            ),
            ols_intercept_seconds=record.ols_intercept_seconds,
            association_status=(
                "constant_k"
                if record.association_status == "constant_set_count"
                else record.association_status
            ),
        )
        for record in projected_records
    ]


def _search_nodes_dominated_ratio_association_statistics(
    rows: Sequence[RunRecord],
    instances: Sequence[InstanceRecord],
) -> list[SearchNodesDominatedRatioAssociationRecord]:
    """Associate completed BnB search nodes with dominated-set ratio."""

    instance_by_unit: dict[
        tuple[str, str, int, str], InstanceRecord
    ] = {}
    for supplied_instance in instances:
        unit = (
            supplied_instance.config_hash,
            supplied_instance.case_id,
            supplied_instance.repetition,
            supplied_instance.instance_id,
        )
        if unit in instance_by_unit:
            raise ValueError(
                "search-nodes dominated-ratio association requires unique "
                "instances"
            )
        instance_by_unit[unit] = supplied_instance

    groups: dict[tuple[str, str, str, str], list[RunRecord]] = defaultdict(list)
    for row in rows:
        if row.algorithm not in {
            "branch_and_bound",
            "branch_and_bound_enhanced",
        }:
            continue
        groups[
            (row.config_hash, row.family, row.algorithm_id, row.algorithm)
        ].append(row)

    records: list[SearchNodesDominatedRatioAssociationRecord] = []
    for key, group in sorted(groups.items()):
        config_identifier, family, algorithm_id, algorithm = key
        units: dict[tuple[str, str, int, str], RunRecord] = {}
        for row in group:
            if row.algorithm_seed is not None:
                raise ValueError(
                    "search-nodes dominated-ratio association forbids "
                    "algorithm seeds"
                )
            if row.status not in {
                SolutionStatus.OPTIMAL,
                SolutionStatus.TIMEOUT,
                SolutionStatus.ERROR,
            }:
                raise ValueError(
                    "search-nodes dominated-ratio BnB records must be "
                    "optimal, timeout, or error"
                )
            unit = (
                row.config_hash,
                row.case_id,
                row.repetition,
                row.instance_id,
            )
            if unit in units:
                raise ValueError(
                    "search-nodes dominated-ratio association requires "
                    "exactly one run per instance unit"
                )
            instance = instance_by_unit.get(unit)
            if instance is None:
                raise ValueError(
                    "search-nodes dominated-ratio row has no matching instance"
                )
            if (
                instance.family != row.family
                or instance.set_count != row.set_count
                or instance.k != row.k
            ):
                raise ValueError(
                    "search-nodes dominated-ratio row conflicts with instance"
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
                        "search-nodes dominated-ratio nodes_or_iterations must "
                        "match algorithm_metadata.search.nodes_visited"
                    )
            units[unit] = row

        ratios: list[float] = []
        search_nodes: list[float] = []
        for unit, row in sorted(units.items()):
            if row.status is not SolutionStatus.OPTIMAL:
                continue
            instance = instance_by_unit[unit]
            ratios.append(_ten_decimal(instance.dominated_set_ratio))
            search_nodes.append(_ten_decimal(float(row.nodes_or_iterations)))

        sample_count = len(ratios)
        distinct_ratio_count = len(set(ratios))
        if sample_count == 0:
            mean_ratio = None
            mean_nodes = None
            ratio_sd = None
            node_sd = None
            correlation = None
            slope = None
            intercept = None
            status = "no_samples"
        else:
            raw_mean_ratio = fmean(ratios)
            raw_mean_nodes = fmean(search_nodes)
            mean_ratio = _ten_decimal(raw_mean_ratio)
            mean_nodes = _ten_decimal(raw_mean_nodes)
            if sample_count == 1:
                ratio_sd = None
                node_sd = None
                correlation = None
                slope = None
                intercept = None
                status = "insufficient_samples"
            else:
                centered_ratios = [value - raw_mean_ratio for value in ratios]
                centered_nodes = [
                    value - raw_mean_nodes for value in search_nodes
                ]
                ratio_sum_squares = sum(
                    value * value for value in centered_ratios
                )
                node_sum_squares = sum(
                    value * value for value in centered_nodes
                )
                cross_product = sum(
                    ratio * nodes
                    for ratio, nodes in zip(
                        centered_ratios, centered_nodes, strict=True
                    )
                )
                ratio_sd = _ten_decimal(
                    math.sqrt(ratio_sum_squares / (sample_count - 1))
                )
                node_sd = _ten_decimal(
                    math.sqrt(node_sum_squares / (sample_count - 1))
                )
                if ratio_sd == 0:
                    correlation = None
                    slope = None
                    intercept = None
                    status = "constant_dominated_ratio"
                elif node_sd == 0:
                    correlation = None
                    slope = 0.0
                    intercept = mean_nodes
                    status = "constant_nodes"
                else:
                    raw_correlation = cross_product / math.sqrt(
                        ratio_sum_squares * node_sum_squares
                    )
                    correlation = _ten_decimal(
                        min(1.0, max(-1.0, raw_correlation))
                    )
                    raw_slope = cross_product / ratio_sum_squares
                    slope = _ten_decimal(raw_slope)
                    intercept = _ten_decimal(
                        raw_mean_nodes - raw_slope * raw_mean_ratio
                    )
                    status = "estimable"

        case_ids = tuple(sorted({row.case_id for row in group}))
        optimal_run_count = sum(
            row.status is SolutionStatus.OPTIMAL for row in group
        )
        records.append(
            SearchNodesDominatedRatioAssociationRecord(
                config_hash=config_identifier,
                family=family,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                predictor="dominated_set_ratio",
                response="completed_search_nodes",
                repetition_unit="instance_seed",
                case_count=len(case_ids),
                case_ids=case_ids,
                instance_count=len(units),
                run_count=len(group),
                optimal_run_count=optimal_run_count,
                timeout_count=sum(
                    row.status is SolutionStatus.TIMEOUT for row in group
                ),
                error_count=sum(
                    row.status is SolutionStatus.ERROR for row in group
                ),
                eligible_instance_count=sample_count,
                distinct_dominated_ratio_count=distinct_ratio_count,
                mean_dominated_set_ratio=mean_ratio,
                mean_search_nodes=mean_nodes,
                dominated_ratio_sample_standard_deviation=ratio_sd,
                search_nodes_sample_standard_deviation=node_sd,
                pearson_correlation=correlation,
                ols_slope_nodes_per_ratio_unit=slope,
                ols_intercept_nodes=intercept,
                association_status=status,
            )
        )
    return records
