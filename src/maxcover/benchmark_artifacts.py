"""Runner-owned artifact inventories and path discovery."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import cast

from .contracts import (
    BranchAndBoundNodeReductionRecord,
    CensoredRuntimeRecord,
    ConfidenceIntervalRecord,
    DescriptiveStatisticsRecord,
    GapClusteringAssociationRecord,
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
    GreedyFailureRecord,
    HeuristicExactRuntimeRatioRecord,
    InstanceRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    QualityRuntimeParetoRecord,
    ReferenceCensoringBiasRecord,
    ReferenceCoverageRecord,
    ReferenceCutoffSensitivityRecord,
    ReferenceStatusRecord,
    RunRecord,
    RuntimeKAssociationRecord,
    RuntimeSetCountAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
    SummaryRecord,
)
from .reproducibility import atomic_write_text


REPORT_FILENAMES = (
    "results_summary.md",
    "gap_by_family.svg",
    "runtime_by_algorithm.svg",
    "gap_by_case.svg",
    "gap_vs_structural_parameter.svg",
    "local_search_recovery.svg",
    "quality_runtime_pareto.svg",
    "runtime_scaling.svg",
    "node_scaling.svg",
    "timeout_by_case.svg",
    "reference_coverage_by_case.svg",
)


RUNNER_OWNED_FILENAMES = (
    "raw_results.csv",
    "instances.csv",
    "summary.csv",
    "descriptive_statistics.csv",
    "confidence_interval_statistics.csv",
    "censored_runtime_statistics.csv",
    "reference_status.csv",
    "reference_coverage_statistics.csv",
    "reference_censoring_bias_statistics.csv",
    "reference_cutoff_sensitivity_statistics.csv",
    "greedy_failure_statistics.csv",
    "local_search_recovery_statistics.csv",
    "local_search_remaining_gap_statistics.csv",
    "heuristic_exact_runtime_ratio_statistics.csv",
    "bnb_node_reduction_statistics.csv",
    "quality_runtime_pareto_statistics.csv",
    "gap_density_association_statistics.csv",
    "gap_overlap_association_statistics.csv",
    "gap_clustering_association_statistics.csv",
    "runtime_set_count_association_statistics.csv",
    "runtime_k_association_statistics.csv",
    "search_nodes_dominated_ratio_association_statistics.csv",
    "search_comparison.csv",
    "stochastic_summary.csv",
    "manifest.json",
    *REPORT_FILENAMES,
)


SEARCH_COMPARISON_FIELDS = (
    "case_id",
    "instance_id",
    "baseline_status",
    "enhanced_status",
    "baseline_coverage",
    "enhanced_coverage",
    "baseline_nodes",
    "enhanced_nodes",
    "node_ratio",
    "baseline_runtime_seconds",
    "enhanced_runtime_seconds",
)


STOCHASTIC_SUMMARY_FIELDS = (
    "case_id",
    "instance_id",
    "algorithm_id",
    "algorithm",
    "seed_count",
    "min_coverage",
    "mean_coverage",
    "median_coverage",
    "stddev_coverage",
    "max_coverage",
    "optimum",
    "optimum_hit_rate",
    "better_than_greedy_rate",
    "equal_to_greedy_rate",
    "worse_than_greedy_rate",
    "mean_greedy_gap_recovery_rate",
    "full_optimum_recovery_rate",
    "mean_extra_runtime_seconds",
    "mean_runtime_seconds",
)


def _runner_owned_paths(output_dir: Path) -> list[Path]:
    paths = [output_dir / filename for filename in RUNNER_OWNED_FILENAMES]
    failure_dir = output_dir / "failures"
    if failure_dir.exists():
        paths.extend(sorted(failure_dir.glob("*.json")))
    return paths


def _csv_text(
    rows: (
        Sequence[RunRecord]
        | Sequence[SummaryRecord]
        | Sequence[InstanceRecord]
        | Sequence[DescriptiveStatisticsRecord]
        | Sequence[ConfidenceIntervalRecord]
        | Sequence[CensoredRuntimeRecord]
        | Sequence[GreedyFailureRecord]
        | Sequence[LocalSearchRecoveryRecord]
        | Sequence[LocalSearchRemainingGapRecord]
        | Sequence[HeuristicExactRuntimeRatioRecord]
        | Sequence[BranchAndBoundNodeReductionRecord]
        | Sequence[QualityRuntimeParetoRecord]
        | Sequence[ReferenceStatusRecord]
        | Sequence[ReferenceCoverageRecord]
        | Sequence[ReferenceCensoringBiasRecord]
        | Sequence[ReferenceCutoffSensitivityRecord]
        | Sequence[GapDensityAssociationRecord]
        | Sequence[GapOverlapAssociationRecord]
        | Sequence[GapClusteringAssociationRecord]
        | Sequence[RuntimeSetCountAssociationRecord]
        | Sequence[RuntimeKAssociationRecord]
        | Sequence[SearchNodesDominatedRatioAssociationRecord]
    ),
    fields: tuple[str, ...],
) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(row.to_csv_row() for row in rows)
    return stream.getvalue()


def _canonical_run_records(rows: Sequence[RunRecord]) -> list[RunRecord]:
    """Round-trip through the persisted CSV representation before analysis."""

    stream = io.StringIO(_csv_text(rows, RunRecord.CSV_FIELDS), newline="")
    return [RunRecord.from_csv_row(row) for row in csv.DictReader(stream)]


def _canonical_instance_records(
    rows: Sequence[InstanceRecord],
) -> list[InstanceRecord]:
    """Round-trip instance structure evidence through its persisted CSV form."""

    stream = io.StringIO(
        _csv_text(rows, InstanceRecord.CSV_FIELDS),
        newline="",
    )
    return [InstanceRecord.from_csv_row(row) for row in csv.DictReader(stream)]


def _write_csv(
    path: Path,
    rows: (
        Sequence[RunRecord]
        | Sequence[SummaryRecord]
        | Sequence[InstanceRecord]
        | Sequence[DescriptiveStatisticsRecord]
        | Sequence[ConfidenceIntervalRecord]
        | Sequence[CensoredRuntimeRecord]
        | Sequence[GreedyFailureRecord]
        | Sequence[LocalSearchRecoveryRecord]
        | Sequence[LocalSearchRemainingGapRecord]
        | Sequence[HeuristicExactRuntimeRatioRecord]
        | Sequence[BranchAndBoundNodeReductionRecord]
        | Sequence[QualityRuntimeParetoRecord]
        | Sequence[ReferenceStatusRecord]
        | Sequence[ReferenceCoverageRecord]
        | Sequence[ReferenceCensoringBiasRecord]
        | Sequence[ReferenceCutoffSensitivityRecord]
        | Sequence[GapDensityAssociationRecord]
        | Sequence[GapOverlapAssociationRecord]
        | Sequence[GapClusteringAssociationRecord]
        | Sequence[RuntimeSetCountAssociationRecord]
        | Sequence[RuntimeKAssociationRecord]
        | Sequence[SearchNodesDominatedRatioAssociationRecord]
    ),
    fields: tuple[str, ...],
) -> None:
    atomic_write_text(path, _csv_text(rows, fields))


def _validate_existing_instances(
    path: Path, expected: Sequence[InstanceRecord]
) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", newline="") as handle:
        existing = [InstanceRecord.from_csv_row(row) for row in csv.DictReader(handle)]
    if [row.to_csv_row() for row in existing] != [
        row.to_csv_row() for row in expected
    ]:
        raise ValueError(
            "existing instances.csv does not match the current instance plan; use --force"
        )


def _clean_runner_owned_artifacts(output_dir: Path) -> None:
    for path in _runner_owned_paths(output_dir):
        if path.is_file():
            path.unlink()


def _write_search_comparison(output_dir: Path, rows: Sequence[RunRecord]) -> int:
    baseline = {
        row.instance_id: row for row in rows if row.algorithm_id == "bnb_baseline"
    }
    enhanced = {
        row.instance_id: row for row in rows if row.algorithm_id == "bnb_enhanced"
    }
    paired_ids = sorted(set(baseline) & set(enhanced))
    if not paired_ids:
        return 0
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=SEARCH_COMPARISON_FIELDS, lineterminator="\n"
    )
    writer.writeheader()
    for identifier in paired_ids:
        left = baseline[identifier]
        right = enhanced[identifier]
        ratio = (
            None
            if left.nodes_or_iterations == 0
            else right.nodes_or_iterations / left.nodes_or_iterations
        )
        writer.writerow(
            {
                "case_id": left.case_id,
                "instance_id": identifier,
                "baseline_status": left.status.value,
                "enhanced_status": right.status.value,
                "baseline_coverage": left.coverage,
                "enhanced_coverage": right.coverage,
                "baseline_nodes": left.nodes_or_iterations,
                "enhanced_nodes": right.nodes_or_iterations,
                "node_ratio": "" if ratio is None else f"{ratio:.10f}",
                "baseline_runtime_seconds": f"{left.runtime_seconds:.10f}",
                "enhanced_runtime_seconds": f"{right.runtime_seconds:.10f}",
            }
        )
    atomic_write_text(output_dir / "search_comparison.csv", stream.getvalue())
    return len(paired_ids)


def _write_stochastic_summary(output_dir: Path, rows: Sequence[RunRecord]) -> int:
    groups: dict[tuple[str, str, str, str], list[RunRecord]] = defaultdict(list)
    greedy_by_instance = {
        row.instance_id: row.coverage
        for row in rows
        if row.algorithm == "greedy"
        and row.algorithm_seed is None
        and row.coverage is not None
    }
    for row in rows:
        if row.algorithm_seed is not None and row.coverage is not None:
            groups[
                (row.case_id, row.instance_id, row.algorithm_id, row.algorithm)
            ].append(row)
    if not groups:
        return 0

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=STOCHASTIC_SUMMARY_FIELDS, lineterminator="\n"
    )
    writer.writeheader()
    for key, group in sorted(groups.items()):
        case_id, identifier, algorithm_id, algorithm = key
        ordered = sorted(group, key=lambda row: cast(int, row.algorithm_seed))
        coverages = [row.coverage for row in ordered]
        assert all(coverage is not None for coverage in coverages)
        values = [int(coverage) for coverage in coverages if coverage is not None]
        optimum = next((row.optimum for row in ordered if row.optimum is not None), None)
        greedy_coverage = greedy_by_instance.get(identifier)
        greedy_row = next(
            (
                row
                for row in rows
                if row.instance_id == identifier
                and row.algorithm == "greedy"
                and row.algorithm_seed is None
            ),
            None,
        )
        denominator = len(values)
        recoveries = (
            []
            if optimum is None
            or greedy_coverage is None
            or optimum <= greedy_coverage
            else [
                (value - greedy_coverage) / (optimum - greedy_coverage)
                for value in values
            ]
        )
        writer.writerow(
            {
                "case_id": case_id,
                "instance_id": identifier,
                "algorithm_id": algorithm_id,
                "algorithm": algorithm,
                "seed_count": denominator,
                "min_coverage": min(values),
                "mean_coverage": f"{fmean(values):.10f}",
                "median_coverage": f"{median(values):.10f}",
                "stddev_coverage": f"{pstdev(values):.10f}",
                "max_coverage": max(values),
                "optimum": "" if optimum is None else optimum,
                "optimum_hit_rate": (
                    ""
                    if optimum is None
                    else f"{sum(value == optimum for value in values) / denominator:.10f}"
                ),
                "better_than_greedy_rate": (
                    ""
                    if greedy_coverage is None
                    else f"{sum(value > greedy_coverage for value in values) / denominator:.10f}"
                ),
                "equal_to_greedy_rate": (
                    ""
                    if greedy_coverage is None
                    else f"{sum(value == greedy_coverage for value in values) / denominator:.10f}"
                ),
                "worse_than_greedy_rate": (
                    ""
                    if greedy_coverage is None
                    else f"{sum(value < greedy_coverage for value in values) / denominator:.10f}"
                ),
                "mean_greedy_gap_recovery_rate": (
                    "" if not recoveries else f"{fmean(recoveries):.10f}"
                ),
                "full_optimum_recovery_rate": (
                    ""
                    if optimum is None
                    else f"{sum(value == optimum for value in values) / denominator:.10f}"
                ),
                "mean_extra_runtime_seconds": (
                    ""
                    if greedy_row is None
                    else f"{fmean(row.runtime_seconds for row in ordered) - greedy_row.runtime_seconds:.10f}"
                ),
                "mean_runtime_seconds": f"{fmean(row.runtime_seconds for row in ordered):.10f}",
            }
        )
    atomic_write_text(output_dir / "stochastic_summary.csv", stream.getvalue())
    return len(groups)


def _read_existing(path: Path, expected_config_hash: str) -> dict[str, RunRecord]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        records = [RunRecord.from_csv_row(row) for row in csv.DictReader(handle)]
    result: dict[str, RunRecord] = {}
    for record in records:
        if record.config_hash != expected_config_hash:
            raise ValueError(
                "existing raw_results.csv belongs to a different configuration; "
                "choose another output directory or use --force"
            )
        if not record.run_id:
            raise ValueError("existing raw_results.csv has no resumable run_id")
        if record.run_id in result:
            raise ValueError(f"duplicate run_id in raw_results.csv: {record.run_id}")
        result[record.run_id] = record
    return result
