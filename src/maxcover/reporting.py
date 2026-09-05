"""Public report artifact writer."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from .config import ExperimentConfig
from .contracts import (
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
    ReferenceCensoringBiasRecord,
    ReferenceCoverageRecord,
    ReferenceCutoffSensitivityRecord,
    ReferenceStatusRecord,
    RuntimeKAssociationRecord,
    RuntimeSetCountAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
    RunRecord,
)
from . import (
    _report_charts,
    _report_markdown,
)


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
    reference_statuses: Sequence[ReferenceStatusRecord] = (),
    reference_coverage_statistics: Sequence[ReferenceCoverageRecord] = (),
    reference_censoring_bias_statistics: Sequence[
        ReferenceCensoringBiasRecord
    ] = (),
    reference_cutoff_sensitivity_statistics: Sequence[
        ReferenceCutoffSensitivityRecord
    ] = (),
) -> None:
    _report_markdown._write_markdown(
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
        reference_statuses,
        reference_coverage_statistics,
        reference_censoring_bias_statistics,
        reference_cutoff_sensitivity_statistics,
    )
    _report_charts._write_gap_chart(output_dir / "gap_by_family.svg", statistics)
    _report_charts._write_runtime_chart(output_dir / "runtime_by_algorithm.svg", statistics)
    (output_dir / "gap_by_case.svg").write_text(
        _report_charts._render_gap_by_case_chart(statistics), encoding="utf-8"
    )
    (output_dir / "gap_vs_structural_parameter.svg").write_text(
        _report_charts._render_gap_structural_association_chart(
            gap_density_association_statistics,
            gap_overlap_association_statistics,
            gap_clustering_association_statistics,
        ),
        encoding="utf-8",
    )
    (output_dir / "local_search_recovery.svg").write_text(
        _report_charts._render_local_search_recovery_chart(local_search_recovery_statistics),
        encoding="utf-8",
    )
    (output_dir / "quality_runtime_pareto.svg").write_text(
        _report_charts._render_quality_runtime_pareto_chart(quality_runtime_pareto_statistics),
        encoding="utf-8",
    )
    (output_dir / "runtime_scaling.svg").write_text(
        _report_charts._render_runtime_scaling_chart(
            runtime_set_count_association_statistics,
            runtime_k_association_statistics,
        ),
        encoding="utf-8",
    )
    (output_dir / "node_scaling.svg").write_text(
        _report_charts._render_node_scaling_chart(
            search_nodes_dominated_ratio_association_statistics
        ),
        encoding="utf-8",
    )
    (output_dir / "timeout_by_case.svg").write_text(
        _report_charts._render_timeout_by_case_chart(censored_runtime_statistics),
        encoding="utf-8",
    )
    (output_dir / "reference_coverage_by_case.svg").write_text(
        _report_charts._render_reference_coverage_chart(reference_statuses),
        encoding="utf-8",
    )
