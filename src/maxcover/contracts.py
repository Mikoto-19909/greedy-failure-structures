"""Stable contracts shared by algorithms and the experiment runner."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from ._contract_csv import (
    _parse_bool,
    _parse_float,
    _parse_int,
    _required_float,
    _required_int,
    _validate_csv_fields,
)
from ._instance_contracts import (
    INSTANCE_RECORD_SCHEMA_VERSION,
    P4_3_COUPLED_FAMILIES,
    P4_3_INSTANCE_ORIGINS,
    P4_3_RESEARCH_QUESTION_IDS,
    InstanceRecord,
)
from ._registry_contracts import (
    AlgorithmRunOptions,
    AlgorithmRunner,
    AlgorithmSpec,
    GeneratorFactory,
    GeneratorSpec,
    OptionSpec,
    ParameterSpec,
)
from ._run_contracts import (
    PREVIOUS_RECORD_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    RunRecord,
    SummaryRecord,
)
from ._statistics_contracts import (
    AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION,
    AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT,
    BNB_NODE_REDUCTION_SCHEMA_VERSION,
    CENSORED_RUNTIME_SCHEMA_VERSION,
    CONFIDENCE_INTERVAL_SCHEMA_VERSION,
    DESCRIPTIVE_STATISTICS_METRICS,
    DESCRIPTIVE_STATISTICS_SCHEMA_VERSION,
    GREEDY_FAILURE_SCHEMA_VERSION,
    HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION,
    LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION,
    LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION,
    QUALITY_RUNTIME_PARETO_SCHEMA_VERSION,
    BranchAndBoundNodeReductionRecord,
    CensoredRuntimeRecord,
    ConfidenceIntervalRecord,
    DescriptiveStatisticsRecord,
    GreedyFailureRecord,
    HeuristicExactRuntimeRatioRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    QualityRuntimeParetoRecord,
)
from .model import (
    MaximumCoverageInstance,
    Solution,
    SolutionStatus,
    normalize_algorithm_metadata,
)

from ._association_contracts import (
    GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION,
    GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION,
    GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION,
    RUNTIME_K_ASSOCIATION_SCHEMA_VERSION,
    RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION,
    SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION,
    GapClusteringAssociationRecord,
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
    RuntimeKAssociationRecord,
    RuntimeSetCountAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
)

from ._benchmark_result import BenchmarkResult


__all__ = (
    "AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION",
    "AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT",
    "AlgorithmRunOptions",
    "AlgorithmRunner",
    "AlgorithmSpec",
    "Any",
    "BNB_NODE_REDUCTION_SCHEMA_VERSION",
    "BenchmarkResult",
    "BranchAndBoundNodeReductionRecord",
    "CENSORED_RUNTIME_SCHEMA_VERSION",
    "CONFIDENCE_INTERVAL_SCHEMA_VERSION",
    "Callable",
    "CensoredRuntimeRecord",
    "ClassVar",
    "ConfidenceIntervalRecord",
    "DESCRIPTIVE_STATISTICS_METRICS",
    "DESCRIPTIVE_STATISTICS_SCHEMA_VERSION",
    "DescriptiveStatisticsRecord",
    "GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION",
    "GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION",
    "GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION",
    "GREEDY_FAILURE_SCHEMA_VERSION",
    "GapClusteringAssociationRecord",
    "GapDensityAssociationRecord",
    "GapOverlapAssociationRecord",
    "GeneratorFactory",
    "GeneratorSpec",
    "GreedyFailureRecord",
    "HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION",
    "HeuristicExactRuntimeRatioRecord",
    "INSTANCE_RECORD_SCHEMA_VERSION",
    "InstanceRecord",
    "LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION",
    "LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION",
    "LocalSearchRecoveryRecord",
    "LocalSearchRemainingGapRecord",
    "Mapping",
    "MappingProxyType",
    "MaximumCoverageInstance",
    "OptionSpec",
    "P4_3_COUPLED_FAMILIES",
    "P4_3_INSTANCE_ORIGINS",
    "P4_3_RESEARCH_QUESTION_IDS",
    "PREVIOUS_RECORD_SCHEMA_VERSION",
    "ParameterSpec",
    "Path",
    "QUALITY_RUNTIME_PARETO_SCHEMA_VERSION",
    "QualityRuntimeParetoRecord",
    "RECORD_SCHEMA_VERSION",
    "RUNTIME_K_ASSOCIATION_SCHEMA_VERSION",
    "RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION",
    "RunRecord",
    "RuntimeKAssociationRecord",
    "RuntimeSetCountAssociationRecord",
    "SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION",
    "SearchNodesDominatedRatioAssociationRecord",
    "Solution",
    "SolutionStatus",
    "SummaryRecord",
    "TYPE_CHECKING",
    "annotations",
    "dataclass",
    "field",
    "json",
    "math",
    "normalize_algorithm_metadata",
)
