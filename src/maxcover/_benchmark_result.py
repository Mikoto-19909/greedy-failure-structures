"""Private benchmark result contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ._association_contracts import (
    GapClusteringAssociationRecord,
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
)
from ._performance_association_contracts import (
    RuntimeKAssociationRecord,
    RuntimeSetCountAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
)
from ._instance_contracts import InstanceRecord
from ._reference_contracts import (
    ReferenceCensoringBiasRecord,
    ReferenceCoverageRecord,
    ReferenceCutoffSensitivityRecord,
    ReferenceStatusRecord,
)
from ._run_contracts import RunRecord, SummaryRecord
from ._statistics_contracts import (
    CensoredRuntimeRecord,
    ConfidenceIntervalRecord,
    DescriptiveStatisticsRecord,
)
from ._quality_contracts import (
    GreedyFailureRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    QualityRuntimeParetoRecord,
)
from ._performance_contracts import (
    BranchAndBoundNodeReductionRecord,
    HeuristicExactRuntimeRatioRecord,
)

if TYPE_CHECKING:
    from .config import ExperimentConfig


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Typed result returned after a complete benchmark run."""

    config: ExperimentConfig
    rows: tuple[RunRecord, ...]
    summary: tuple[SummaryRecord, ...]
    output_dir: Path
    instances: tuple[InstanceRecord, ...] = ()
    descriptive_statistics: tuple[DescriptiveStatisticsRecord, ...] = ()
    confidence_interval_statistics: tuple[
        ConfidenceIntervalRecord, ...
    ] = ()
    censored_runtime_statistics: tuple[CensoredRuntimeRecord, ...] = ()
    reference_statuses: tuple[ReferenceStatusRecord, ...] = ()
    reference_coverage_statistics: tuple[ReferenceCoverageRecord, ...] = ()
    reference_censoring_bias_statistics: tuple[
        ReferenceCensoringBiasRecord, ...
    ] = ()
    reference_cutoff_sensitivity_statistics: tuple[
        ReferenceCutoffSensitivityRecord, ...
    ] = ()
    greedy_failure_statistics: tuple[GreedyFailureRecord, ...] = ()
    local_search_recovery_statistics: tuple[LocalSearchRecoveryRecord, ...] = ()
    local_search_remaining_gap_statistics: tuple[
        LocalSearchRemainingGapRecord, ...
    ] = ()
    heuristic_exact_runtime_ratio_statistics: tuple[
        HeuristicExactRuntimeRatioRecord, ...
    ] = ()
    bnb_node_reduction_statistics: tuple[
        BranchAndBoundNodeReductionRecord, ...
    ] = ()
    quality_runtime_pareto_statistics: tuple[
        QualityRuntimeParetoRecord, ...
    ] = ()
    gap_density_association_statistics: tuple[
        GapDensityAssociationRecord, ...
    ] = ()
    gap_overlap_association_statistics: tuple[
        GapOverlapAssociationRecord, ...
    ] = ()
    gap_clustering_association_statistics: tuple[
        GapClusteringAssociationRecord, ...
    ] = ()
    runtime_set_count_association_statistics: tuple[
        RuntimeSetCountAssociationRecord, ...
    ] = ()
    runtime_k_association_statistics: tuple[RuntimeKAssociationRecord, ...] = ()
    search_nodes_dominated_ratio_association_statistics: tuple[
        SearchNodesDominatedRatioAssociationRecord, ...
    ] = ()

    def __post_init__(self) -> None:
        from .config import ExperimentConfig

        if not isinstance(self.config, ExperimentConfig):
            raise TypeError("config must be an ExperimentConfig")
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "summary", tuple(self.summary))
        object.__setattr__(self, "instances", tuple(self.instances))
        object.__setattr__(
            self, "descriptive_statistics", tuple(self.descriptive_statistics)
        )
        object.__setattr__(
            self,
            "confidence_interval_statistics",
            tuple(self.confidence_interval_statistics),
        )
        object.__setattr__(
            self,
            "censored_runtime_statistics",
            tuple(self.censored_runtime_statistics),
        )
        object.__setattr__(self, "reference_statuses", tuple(self.reference_statuses))
        object.__setattr__(
            self,
            "reference_coverage_statistics",
            tuple(self.reference_coverage_statistics),
        )
        object.__setattr__(
            self,
            "reference_censoring_bias_statistics",
            tuple(self.reference_censoring_bias_statistics),
        )
        object.__setattr__(
            self,
            "reference_cutoff_sensitivity_statistics",
            tuple(self.reference_cutoff_sensitivity_statistics),
        )
        object.__setattr__(
            self,
            "greedy_failure_statistics",
            tuple(self.greedy_failure_statistics),
        )
        object.__setattr__(
            self,
            "local_search_recovery_statistics",
            tuple(self.local_search_recovery_statistics),
        )
        object.__setattr__(
            self,
            "local_search_remaining_gap_statistics",
            tuple(self.local_search_remaining_gap_statistics),
        )
        object.__setattr__(
            self,
            "heuristic_exact_runtime_ratio_statistics",
            tuple(self.heuristic_exact_runtime_ratio_statistics),
        )
        object.__setattr__(
            self,
            "bnb_node_reduction_statistics",
            tuple(self.bnb_node_reduction_statistics),
        )
        object.__setattr__(
            self,
            "quality_runtime_pareto_statistics",
            tuple(self.quality_runtime_pareto_statistics),
        )
        object.__setattr__(
            self,
            "gap_density_association_statistics",
            tuple(self.gap_density_association_statistics),
        )
        object.__setattr__(
            self,
            "gap_overlap_association_statistics",
            tuple(self.gap_overlap_association_statistics),
        )
        object.__setattr__(
            self,
            "gap_clustering_association_statistics",
            tuple(self.gap_clustering_association_statistics),
        )
        object.__setattr__(
            self,
            "runtime_set_count_association_statistics",
            tuple(self.runtime_set_count_association_statistics),
        )
        object.__setattr__(
            self,
            "runtime_k_association_statistics",
            tuple(self.runtime_k_association_statistics),
        )
        object.__setattr__(
            self,
            "search_nodes_dominated_ratio_association_statistics",
            tuple(self.search_nodes_dominated_ratio_association_statistics),
        )
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        if not all(isinstance(row, RunRecord) for row in self.rows):
            raise TypeError("rows must contain only RunRecord values")
        if not all(isinstance(row, SummaryRecord) for row in self.summary):
            raise TypeError("summary must contain only SummaryRecord values")
        if not all(isinstance(row, InstanceRecord) for row in self.instances):
            raise TypeError("instances must contain only InstanceRecord values")
        if not all(
            isinstance(row, DescriptiveStatisticsRecord)
            for row in self.descriptive_statistics
        ):
            raise TypeError(
                "descriptive_statistics must contain only "
                "DescriptiveStatisticsRecord values"
            )
        if not all(
            isinstance(row, ConfidenceIntervalRecord)
            for row in self.confidence_interval_statistics
        ):
            raise TypeError(
                "confidence_interval_statistics must contain only "
                "ConfidenceIntervalRecord values"
            )
        if not all(
            isinstance(row, CensoredRuntimeRecord)
            for row in self.censored_runtime_statistics
        ):
            raise TypeError(
                "censored_runtime_statistics must contain only "
                "CensoredRuntimeRecord values"
            )
        if not all(
            isinstance(row, ReferenceStatusRecord) for row in self.reference_statuses
        ):
            raise TypeError("reference_statuses must contain ReferenceStatusRecord values")
        if not all(
            isinstance(row, ReferenceCoverageRecord)
            for row in self.reference_coverage_statistics
        ):
            raise TypeError(
                "reference_coverage_statistics must contain ReferenceCoverageRecord values"
            )
        if not all(
            isinstance(row, ReferenceCensoringBiasRecord)
            for row in self.reference_censoring_bias_statistics
        ):
            raise TypeError(
                "reference_censoring_bias_statistics must contain "
                "ReferenceCensoringBiasRecord values"
            )
        if not all(
            isinstance(row, ReferenceCutoffSensitivityRecord)
            for row in self.reference_cutoff_sensitivity_statistics
        ):
            raise TypeError(
                "reference_cutoff_sensitivity_statistics must contain "
                "ReferenceCutoffSensitivityRecord values"
            )
        if not all(
            isinstance(row, GreedyFailureRecord)
            for row in self.greedy_failure_statistics
        ):
            raise TypeError(
                "greedy_failure_statistics must contain only "
                "GreedyFailureRecord values"
            )
        if not all(
            isinstance(row, LocalSearchRecoveryRecord)
            for row in self.local_search_recovery_statistics
        ):
            raise TypeError(
                "local_search_recovery_statistics must contain only "
                "LocalSearchRecoveryRecord values"
            )
        if not all(
            isinstance(row, LocalSearchRemainingGapRecord)
            for row in self.local_search_remaining_gap_statistics
        ):
            raise TypeError(
                "local_search_remaining_gap_statistics must contain only "
                "LocalSearchRemainingGapRecord values"
            )
        if not all(
            isinstance(row, HeuristicExactRuntimeRatioRecord)
            for row in self.heuristic_exact_runtime_ratio_statistics
        ):
            raise TypeError(
                "heuristic_exact_runtime_ratio_statistics must contain only "
                "HeuristicExactRuntimeRatioRecord values"
            )
        if not all(
            isinstance(row, BranchAndBoundNodeReductionRecord)
            for row in self.bnb_node_reduction_statistics
        ):
            raise TypeError(
                "bnb_node_reduction_statistics must contain only "
                "BranchAndBoundNodeReductionRecord values"
            )
        if not all(
            isinstance(row, QualityRuntimeParetoRecord)
            for row in self.quality_runtime_pareto_statistics
        ):
            raise TypeError(
                "quality_runtime_pareto_statistics must contain only "
                "QualityRuntimeParetoRecord values"
            )
        if not all(
            isinstance(row, GapDensityAssociationRecord)
            for row in self.gap_density_association_statistics
        ):
            raise TypeError(
                "gap_density_association_statistics must contain only "
                "GapDensityAssociationRecord values"
            )
        if not all(
            isinstance(row, GapOverlapAssociationRecord)
            for row in self.gap_overlap_association_statistics
        ):
            raise TypeError(
                "gap_overlap_association_statistics must contain only "
                "GapOverlapAssociationRecord values"
            )
        if not all(
            isinstance(row, GapClusteringAssociationRecord)
            for row in self.gap_clustering_association_statistics
        ):
            raise TypeError(
                "gap_clustering_association_statistics must contain only "
                "GapClusteringAssociationRecord values"
            )
        if not all(
            isinstance(row, RuntimeSetCountAssociationRecord)
            for row in self.runtime_set_count_association_statistics
        ):
            raise TypeError(
                "runtime_set_count_association_statistics must contain only "
                "RuntimeSetCountAssociationRecord values"
            )
        if not all(
            isinstance(row, RuntimeKAssociationRecord)
            for row in self.runtime_k_association_statistics
        ):
            raise TypeError(
                "runtime_k_association_statistics must contain only "
                "RuntimeKAssociationRecord values"
            )
        if not all(
            isinstance(row, SearchNodesDominatedRatioAssociationRecord)
            for row in self.search_nodes_dominated_ratio_association_statistics
        ):
            raise TypeError(
                "search_nodes_dominated_ratio_association_statistics must "
                "contain only SearchNodesDominatedRatioAssociationRecord values"
            )


BenchmarkResult.__module__ = "maxcover.contracts"
