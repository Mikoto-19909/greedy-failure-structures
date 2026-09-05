from __future__ import annotations

import dataclasses
import multiprocessing
import pickle
import re
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maxcover
import maxcover.benchmark as benchmark
import maxcover.contracts as contracts
from maxcover.algorithms import ALGORITHMS
from maxcover.config import load_config
from maxcover.generators import GENERATORS


SUPPORTED_CONTRACT_EXPORTS = (
    "AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION",
    "AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT",
    "AlgorithmRunOptions",
    "AlgorithmRunner",
    "AlgorithmSpec",
    "BNB_NODE_REDUCTION_SCHEMA_VERSION",
    "BenchmarkResult",
    "BranchAndBoundNodeReductionRecord",
    "CENSORED_RUNTIME_SCHEMA_VERSION",
    "CONFIDENCE_INTERVAL_SCHEMA_VERSION",
    "CensoredRuntimeRecord",
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
    "OptionSpec",
    "P4_3_COUPLED_FAMILIES",
    "P4_3_INSTANCE_ORIGINS",
    "P4_3_RESEARCH_QUESTION_IDS",
    "PREVIOUS_RECORD_SCHEMA_VERSION",
    "ParameterSpec",
    "QUALITY_RUNTIME_PARETO_SCHEMA_VERSION",
    "QualityRuntimeParetoRecord",
    "RECORD_SCHEMA_VERSION",
    "REFERENCE_CENSORING_BIAS_SCHEMA_VERSION",
    "REFERENCE_COVERAGE_SCHEMA_VERSION",
    "REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION",
    "REFERENCE_STATUSES",
    "REFERENCE_STATUS_SCHEMA_VERSION",
    "RUNTIME_K_ASSOCIATION_SCHEMA_VERSION",
    "RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION",
    "ReferenceCensoringBiasRecord",
    "ReferenceCoverageRecord",
    "ReferenceCutoffSensitivityRecord",
    "ReferenceStatusRecord",
    "RunRecord",
    "RuntimeKAssociationRecord",
    "RuntimeSetCountAssociationRecord",
    "SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION",
    "SearchNodesDominatedRatioAssociationRecord",
    "SummaryRecord",
)

EXPECTED_CONTRACT_STAR_EXPORTS = (
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
    "REFERENCE_CENSORING_BIAS_SCHEMA_VERSION",
    "REFERENCE_COVERAGE_SCHEMA_VERSION",
    "REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION",
    "REFERENCE_STATUSES",
    "REFERENCE_STATUS_SCHEMA_VERSION",
    "RUNTIME_K_ASSOCIATION_SCHEMA_VERSION",
    "RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION",
    "ReferenceCensoringBiasRecord",
    "ReferenceCoverageRecord",
    "ReferenceCutoffSensitivityRecord",
    "ReferenceStatusRecord",
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

EXPECTED_PACKAGE_ROOT_EXPORTS = (
    "AlgorithmRunOptions", "AlgorithmSpec", "AlgorithmConfig",
    "AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION",
    "AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT", "BenchmarkResult",
    "BenchmarkPlan", "BNB_NODE_REDUCTION_SCHEMA_VERSION",
    "BranchAndBoundNodeReductionRecord", "CENSORED_RUNTIME_SCHEMA_VERSION",
    "CensoredRuntimeRecord", "CONFIG_SCHEMA_VERSION", "CaseConfig",
    "CONFIDENCE_INTERVAL_SCHEMA_VERSION", "ConfidenceIntervalRecord",
    "ConfigurationError", "DESCRIPTIVE_STATISTICS_SCHEMA_VERSION",
    "DescriptiveStatisticsRecord", "ExperimentConfig", "GENERATORS",
    "GeneratorSpec", "GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION",
    "GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION",
    "GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION", "GapDensityAssociationRecord",
    "GapOverlapAssociationRecord", "GapClusteringAssociationRecord",
    "GREEDY_FAILURE_SCHEMA_VERSION", "GreedyFailureRecord",
    "HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION",
    "HeuristicExactRuntimeRatioRecord", "INSTANCE_RECORD_SCHEMA_VERSION",
    "INSTANCE_SCHEMA_VERSION", "InstanceRecord",
    "LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION", "LocalSearchRecoveryRecord",
    "LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION", "LocalSearchRemainingGapRecord",
    "InstanceStructureMetrics", "KnownOptimumCertificate", "LegacyConfigWarning",
    "MaximumCoverageInstance", "OptionSpec", "ParameterSpec",
    "QUALITY_RUNTIME_PARETO_SCHEMA_VERSION", "QualityRuntimeParetoRecord",
    "RECORD_SCHEMA_VERSION", "RUNTIME_K_ASSOCIATION_SCHEMA_VERSION",
    "RuntimeKAssociationRecord", "RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION",
    "RuntimeSetCountAssociationRecord",
    "SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION",
    "SearchNodesDominatedRatioAssociationRecord", "RunRecord", "Solution",
    "SolutionStatus", "SummaryRecord", "branch_and_bound",
    "branch_and_bound_enhanced", "brute_force", "cp_sat_oracle", "config_hash",
    "analyze_instance", "greedy", "instance_from_payload", "instance_id",
    "instance_payload", "lazy_greedy", "local_search", "multi_start_local_search",
    "known_optimum_certificate", "randomized_greedy", "load_config",
    "parse_config", "plan_benchmark", "replay_instance_file", "run_benchmark",
    "summarize_benchmark", "run_id", "validate_known_optimum_certificate",
)

EXPECTED_CLASS_MODULES = (
    "InstanceRecord", "RunRecord", "SummaryRecord",
    "DescriptiveStatisticsRecord", "ConfidenceIntervalRecord",
    "CensoredRuntimeRecord", "GreedyFailureRecord", "LocalSearchRecoveryRecord",
    "LocalSearchRemainingGapRecord", "HeuristicExactRuntimeRatioRecord",
    "BranchAndBoundNodeReductionRecord", "QualityRuntimeParetoRecord",
    "GapDensityAssociationRecord", "GapOverlapAssociationRecord",
    "GapClusteringAssociationRecord", "RuntimeSetCountAssociationRecord",
    "RuntimeKAssociationRecord", "SearchNodesDominatedRatioAssociationRecord",
    "BenchmarkResult", "AlgorithmRunOptions", "OptionSpec", "ParameterSpec",
    "GeneratorSpec", "AlgorithmSpec",
)

EXPECTED_CSV_FIELDS = {
    "InstanceRecord": "config_hash,case_id,repetition,instance_id,seed,coupling_pair_id,coupling_seed,family,generator_version,research_question_id,instance_origin,is_adversarial,universe_size,set_count,k,parameters,incidence_count,covered_element_count,unique_set_count,actual_density,mean_set_size,pairwise_overlap_mean_jaccard,pairwise_overlap_total_pairs,pairwise_overlap_valid_pairs,coverage_skew_gini,duplicate_set_count,duplicate_set_ratio,dominated_set_count,dominated_set_ratio,dominated_unique_ratio,preprocessed_set_count,adversarial_severity,realized_trap_fraction,known_optimum,optimum_source,optimum_selected,proof_kind,schema_version",
    "RunRecord": "config_hash,case_id,instance_id,run_id,case,repetition,seed,family,universe_size,set_count,k,parameters,algorithm_id,algorithm_seed,algorithm,algorithm_options,algorithm_metadata,status,coverage,best_bound,optimum,optimality_gap,runtime_seconds,is_exact,timed_out,nodes_or_iterations,selected,error_message,schema_version",
    "SummaryRecord": "case,family,algorithm_id,algorithm,runs,mean_coverage,mean_optimality_gap,max_optimality_gap,mean_runtime_seconds,timeouts,schema_version",
    "DescriptiveStatisticsRecord": "config_hash,case_id,family,algorithm_id,algorithm,metric,repetition_unit,instance_count,sample_count,run_count,timeout_count,timeout_rate,error_count,error_rate,valid_exact_reference_count,exact_reference_rate,mean,median,standard_deviation,minimum,p25,p75,p95,maximum,schema_version",
    "ConfidenceIntervalRecord": "config_hash,case_id,family,algorithm_id,algorithm,metric,estimand,confidence_level,method,repetition_unit,instance_count,sample_count,run_count,timeout_count,error_count,valid_exact_reference_count,degrees_of_freedom,mean,standard_error,critical_value,lower_bound,upper_bound,interval_status,schema_version",
    "CensoredRuntimeRecord": "config_hash,case_id,family,algorithm_id,algorithm,repetition_unit,instance_count,run_count,completed_run_count,right_censored_run_count,error_run_count,completed_instance_count,right_censored_instance_count,error_affected_instance_count,fully_right_censored_instance_count,censoring_sample_count,censoring_rate,mean_censor_time_seconds,median_censor_time_seconds,minimum_censor_time_seconds,maximum_censor_time_seconds,censoring_status,schema_version",
    "GreedyFailureRecord": "config_hash,case_id,family,algorithm_id,algorithm,repetition_unit,instance_count,run_count,completed_count,timeout_count,timeout_rate,error_count,error_rate,valid_exact_reference_count,exact_reference_rate,no_exact_reference_count,eligible_pair_count,eligible_pair_rate,failure_count,optimal_tie_count,failure_rate,optimal_tie_rate,schema_version",
    "LocalSearchRecoveryRecord": "config_hash,case_id,family,greedy_algorithm_id,local_search_algorithm_id,algorithm,repetition_unit,instance_count,greedy_completed_count,greedy_timeout_count,greedy_error_count,local_search_completed_count,local_search_timeout_count,local_search_error_count,valid_exact_reference_count,greedy_failure_count,eligible_pair_count,eligible_pair_rate,mean_gap_recovery_rate,full_recovery_count,full_recovery_rate,schema_version",
    "LocalSearchRemainingGapRecord": "config_hash,case_id,family,greedy_algorithm_id,local_search_algorithm_id,algorithm,repetition_unit,instance_count,valid_exact_reference_count,greedy_failure_count,eligible_pair_count,mean_remaining_relative_gap,maximum_remaining_relative_gap,zero_remaining_gap_count,zero_remaining_gap_rate,schema_version",
    "HeuristicExactRuntimeRatioRecord": "config_hash,case_id,family,heuristic_algorithm_id,heuristic_algorithm,exact_algorithm_id,exact_algorithm,repetition_unit,instance_count,heuristic_run_count,heuristic_completed_run_count,heuristic_timeout_count,heuristic_error_count,exact_run_count,exact_completed_run_count,exact_timeout_count,exact_error_count,eligible_pair_count,zero_exact_runtime_count,mean_runtime_ratio,median_runtime_ratio,minimum_runtime_ratio,maximum_runtime_ratio,schema_version",
    "BranchAndBoundNodeReductionRecord": "config_hash,case_id,family,baseline_algorithm_id,baseline_algorithm,enhanced_algorithm_id,enhanced_algorithm,repetition_unit,instance_count,baseline_run_count,baseline_optimal_count,baseline_timeout_count,baseline_error_count,enhanced_run_count,enhanced_optimal_count,enhanced_timeout_count,enhanced_error_count,eligible_pair_count,zero_baseline_nodes_count,total_baseline_nodes,total_enhanced_nodes,mean_node_reduction,median_node_reduction,minimum_node_reduction,maximum_node_reduction,aggregate_node_reduction,schema_version",
    "QualityRuntimeParetoRecord": "config_hash,case_id,family,algorithm_id,algorithm,repetition_unit,instance_count,run_count,completed_run_count,timeout_count,error_count,valid_exact_reference_count,zero_optimum_count,no_exact_reference_count,eligible_instance_count,mean_relative_gap,mean_runtime_seconds,pareto_status,dominated_by_algorithm_ids,schema_version",
    "GapDensityAssociationRecord": "config_hash,family,algorithm_id,algorithm,predictor,response,repetition_unit,case_count,case_ids,instance_count,run_count,timeout_count,error_count,valid_exact_reference_count,zero_optimum_count,no_exact_reference_count,unusable_result_count,eligible_instance_count,distinct_density_count,mean_actual_density,mean_relative_gap,density_sample_standard_deviation,gap_sample_standard_deviation,pearson_correlation,ols_slope,ols_intercept,association_status,schema_version",
    "GapOverlapAssociationRecord": "config_hash,family,algorithm_id,algorithm,predictor,response,repetition_unit,case_count,case_ids,instance_count,run_count,timeout_count,error_count,valid_exact_reference_count,zero_optimum_count,no_exact_reference_count,unusable_result_count,missing_overlap_predictor_count,eligible_instance_count,distinct_overlap_count,mean_pairwise_overlap_jaccard,mean_relative_gap,overlap_sample_standard_deviation,gap_sample_standard_deviation,pearson_correlation,ols_slope,ols_intercept,association_status,schema_version",
    "GapClusteringAssociationRecord": "config_hash,family,algorithm_id,algorithm,predictor,response,repetition_unit,case_count,case_ids,clustering_levels,instance_count,run_count,independent_block_count,clustering_level_count,distinct_clustering_level_count,eligible_block_count,incomplete_block_count,timeout_count,error_count,valid_exact_reference_count,zero_optimum_count,no_exact_reference_count,unusable_result_count,usable_gap_instance_count,eligible_instance_count,mean_realized_bridge_fraction,mean_level_relative_gap,bridge_fraction_sample_standard_deviation,gap_level_mean_sample_standard_deviation,pearson_correlation,ols_slope,ols_intercept,association_status,schema_version",
    "RuntimeSetCountAssociationRecord": "config_hash,family,algorithm_id,algorithm,predictor,response,repetition_unit,case_count,case_ids,instance_count,run_count,completed_run_count,timeout_count,error_count,incomplete_runtime_instance_count,eligible_instance_count,distinct_set_count,mean_set_count,mean_runtime_seconds,set_count_sample_standard_deviation,runtime_sample_standard_deviation_seconds,pearson_correlation,ols_slope_seconds_per_set,ols_intercept_seconds,association_status,schema_version",
    "RuntimeKAssociationRecord": "config_hash,family,algorithm_id,algorithm,predictor,response,repetition_unit,case_count,case_ids,instance_count,run_count,completed_run_count,timeout_count,error_count,incomplete_runtime_instance_count,eligible_instance_count,distinct_k_count,mean_k,mean_runtime_seconds,k_sample_standard_deviation,runtime_sample_standard_deviation_seconds,pearson_correlation,ols_slope_seconds_per_budget_unit,ols_intercept_seconds,association_status,schema_version",
    "SearchNodesDominatedRatioAssociationRecord": "config_hash,family,algorithm_id,algorithm,predictor,response,repetition_unit,case_count,case_ids,instance_count,run_count,optimal_run_count,timeout_count,error_count,eligible_instance_count,distinct_dominated_ratio_count,mean_dominated_set_ratio,mean_search_nodes,dominated_ratio_sample_standard_deviation,search_nodes_sample_standard_deviation,pearson_correlation,ols_slope_nodes_per_ratio_unit,ols_intercept_nodes,association_status,schema_version",
}


def _record_fixtures() -> tuple[object, ...]:
    c = contracts
    common_hash = "8bd88eb091586f02a3c7dec5bcb4d4ba62bf299f99e9a0360dccdcc1b905ec0b"
    common = dict(config_hash=common_hash, case_id="tiny", family="uniform")
    association = dict(
        config_hash=common_hash, family="uniform", algorithm_id="branch_and_bound",
        algorithm="branch_and_bound", repetition_unit="instance_seed",
        case_count=1, case_ids=("tiny",), instance_count=1, run_count=1,
    )
    return (
        c.InstanceRecord(
            config_hash=common_hash, case_id="tiny", repetition=0,
            instance_id="df3371b68afd1a347e502b8965222b668305268ea47c8040197c442795460570",
            seed=10, family="uniform", generator_version=1,
            instance_origin="stochastic", is_adversarial=False, universe_size=20,
            set_count=8, k=3, parameters='{"density":0.2}', incidence_count=32,
            covered_element_count=16, unique_set_count=8, actual_density=0.2,
            mean_set_size=4.0, pairwise_overlap_mean_jaccard=0.11652494331065759,
            pairwise_overlap_total_pairs=28, pairwise_overlap_valid_pairs=28,
            coverage_skew_gini=0.41118421052631576, duplicate_set_count=0,
            duplicate_set_ratio=0.0, dominated_set_count=1, dominated_set_ratio=0.125,
            dominated_unique_ratio=0.125, preprocessed_set_count=7,
        ),
        c.RunRecord(
            case="status", repetition=0, seed=None, family="custom", universe_size=5,
            set_count=3, k=1, parameters="{}", algorithm="timed_out_exact",
            algorithm_options="{}", status=c.SolutionStatus.TIMEOUT, coverage=2,
            best_bound=5, optimum=None, optimality_gap=None, runtime_seconds=0.01,
            nodes_or_iterations=0, selected=(0,), case_id="status",
            instance_id="47b57879d0b2a6d7adc52521d970f1d494b2fcfc154e80d9454781bf238dddc0",
            run_id="44a6b076791d21c5d226855e9357919e063b1cd1df727ad8b11378a9f7160bb6",
            algorithm_id="timed_out_exact",
            algorithm_metadata='{"schema_version":1,"search":{},"termination":"completed","trajectory":[]}',
        ),
        c.SummaryRecord("tiny", "uniform", "branch_and_bound", 1, 14.0, 0.0, 0.0, 0.001, 0, "branch_and_bound"),
        c.DescriptiveStatisticsRecord(**common, algorithm_id="branch_and_bound", algorithm="branch_and_bound", metric="coverage", repetition_unit="instance_seed", instance_count=1, sample_count=1, run_count=1, timeout_count=0, timeout_rate=0.0, error_count=0, error_rate=0.0, valid_exact_reference_count=1, exact_reference_rate=1.0, mean=14.0, median=14.0, standard_deviation=None, minimum=14.0, p25=14.0, p75=14.0, p95=14.0, maximum=14.0),
        c.ConfidenceIntervalRecord(**common, algorithm_id="branch_and_bound", algorithm="branch_and_bound", metric="coverage", estimand="instance_mean", confidence_level=0.95, method="student_t_two_sided", repetition_unit="instance_seed", instance_count=1, sample_count=1, run_count=1, timeout_count=0, error_count=0, valid_exact_reference_count=1, degrees_of_freedom=0, mean=14.0, standard_error=None, critical_value=None, lower_bound=None, upper_bound=None, interval_status="insufficient_samples"),
        c.CensoredRuntimeRecord(**common, algorithm_id="branch_and_bound", algorithm="branch_and_bound", repetition_unit="instance_seed", instance_count=1, run_count=1, completed_run_count=1, right_censored_run_count=0, error_run_count=0, completed_instance_count=1, right_censored_instance_count=0, error_affected_instance_count=0, fully_right_censored_instance_count=0, censoring_sample_count=0, censoring_rate=0.0, mean_censor_time_seconds=None, median_censor_time_seconds=None, minimum_censor_time_seconds=None, maximum_censor_time_seconds=None, censoring_status="no_censoring"),
        c.GreedyFailureRecord(**common, algorithm_id="greedy", algorithm="greedy", repetition_unit="instance_seed", instance_count=1, run_count=1, completed_count=1, timeout_count=0, timeout_rate=0.0, error_count=0, error_rate=0.0, valid_exact_reference_count=1, exact_reference_rate=1.0, no_exact_reference_count=0, eligible_pair_count=1, eligible_pair_rate=1.0, failure_count=0, optimal_tie_count=1, failure_rate=0.0, optimal_tie_rate=1.0),
        c.LocalSearchRecoveryRecord(**common, greedy_algorithm_id="greedy", local_search_algorithm_id="local_search", algorithm="local_search", repetition_unit="instance_seed", instance_count=1, greedy_completed_count=1, greedy_timeout_count=0, greedy_error_count=0, local_search_completed_count=1, local_search_timeout_count=0, local_search_error_count=0, valid_exact_reference_count=1, greedy_failure_count=0, eligible_pair_count=0, eligible_pair_rate=None, mean_gap_recovery_rate=None, full_recovery_count=0, full_recovery_rate=None),
        c.LocalSearchRemainingGapRecord(**common, greedy_algorithm_id="greedy", local_search_algorithm_id="local_search", algorithm="local_search", repetition_unit="instance_seed", instance_count=1, valid_exact_reference_count=1, greedy_failure_count=0, eligible_pair_count=0, mean_remaining_relative_gap=None, maximum_remaining_relative_gap=None, zero_remaining_gap_count=0, zero_remaining_gap_rate=None),
        c.HeuristicExactRuntimeRatioRecord(**common, heuristic_algorithm_id="greedy", heuristic_algorithm="greedy", exact_algorithm_id="branch_and_bound", exact_algorithm="branch_and_bound", repetition_unit="instance_seed", instance_count=1, heuristic_run_count=1, heuristic_completed_run_count=1, heuristic_timeout_count=0, heuristic_error_count=0, exact_run_count=1, exact_completed_run_count=1, exact_timeout_count=0, exact_error_count=0, eligible_pair_count=1, zero_exact_runtime_count=0, mean_runtime_ratio=0.5, median_runtime_ratio=0.5, minimum_runtime_ratio=0.5, maximum_runtime_ratio=0.5),
        c.BranchAndBoundNodeReductionRecord(**common, baseline_algorithm_id="bnb_baseline", baseline_algorithm="branch_and_bound", enhanced_algorithm_id="bnb_enhanced", enhanced_algorithm="branch_and_bound_enhanced", repetition_unit="instance_seed", instance_count=1, baseline_run_count=1, baseline_optimal_count=1, baseline_timeout_count=0, baseline_error_count=0, enhanced_run_count=1, enhanced_optimal_count=1, enhanced_timeout_count=0, enhanced_error_count=0, eligible_pair_count=1, zero_baseline_nodes_count=0, total_baseline_nodes=10, total_enhanced_nodes=5, mean_node_reduction=0.5, median_node_reduction=0.5, minimum_node_reduction=0.5, maximum_node_reduction=0.5, aggregate_node_reduction=0.5),
        c.QualityRuntimeParetoRecord(**common, algorithm_id="branch_and_bound", algorithm="branch_and_bound", repetition_unit="instance_seed", instance_count=1, run_count=1, completed_run_count=1, timeout_count=0, error_count=0, valid_exact_reference_count=1, zero_optimum_count=0, no_exact_reference_count=0, eligible_instance_count=1, mean_relative_gap=0.0, mean_runtime_seconds=0.001, pareto_status="frontier"),
        c.GapDensityAssociationRecord(**association, predictor="actual_density", response="relative_optimality_gap", timeout_count=0, error_count=0, valid_exact_reference_count=1, zero_optimum_count=0, no_exact_reference_count=0, unusable_result_count=0, eligible_instance_count=1, distinct_density_count=1, mean_actual_density=0.2, mean_relative_gap=0.0, density_sample_standard_deviation=None, gap_sample_standard_deviation=None, pearson_correlation=None, ols_slope=None, ols_intercept=None, association_status="insufficient_samples"),
        c.GapOverlapAssociationRecord(**association, predictor="pairwise_overlap_mean_jaccard", response="relative_optimality_gap", timeout_count=0, error_count=0, valid_exact_reference_count=1, zero_optimum_count=0, no_exact_reference_count=0, unusable_result_count=0, missing_overlap_predictor_count=0, eligible_instance_count=1, distinct_overlap_count=1, mean_pairwise_overlap_jaccard=0.1, mean_relative_gap=0.0, overlap_sample_standard_deviation=None, gap_sample_standard_deviation=None, pearson_correlation=None, ols_slope=None, ols_intercept=None, association_status="insufficient_samples"),
        c.GapClusteringAssociationRecord(config_hash=common_hash, family="mixed_cluster", algorithm_id="exact", algorithm="brute_force", predictor="realized_bridge_fraction", response="level_mean_relative_optimality_gap", repetition_unit="coupling_seed_block", case_count=2, case_ids=("level0", "level1"), clustering_levels=(0.0, 0.5), instance_count=2, run_count=2, independent_block_count=1, clustering_level_count=2, distinct_clustering_level_count=2, eligible_block_count=1, incomplete_block_count=0, timeout_count=0, error_count=0, valid_exact_reference_count=2, zero_optimum_count=0, no_exact_reference_count=0, unusable_result_count=0, usable_gap_instance_count=2, eligible_instance_count=2, mean_realized_bridge_fraction=0.25, mean_level_relative_gap=0.0, bridge_fraction_sample_standard_deviation=0.3535533906, gap_level_mean_sample_standard_deviation=0.0, pearson_correlation=None, ols_slope=0.0, ols_intercept=0.0, association_status="constant_gap"),
        c.RuntimeSetCountAssociationRecord(**association, predictor="set_count", response="mean_completed_runtime_seconds", completed_run_count=1, timeout_count=0, error_count=0, incomplete_runtime_instance_count=0, eligible_instance_count=1, distinct_set_count=1, mean_set_count=8.0, mean_runtime_seconds=0.001, set_count_sample_standard_deviation=None, runtime_sample_standard_deviation_seconds=None, pearson_correlation=None, ols_slope_seconds_per_set=None, ols_intercept_seconds=None, association_status="insufficient_samples"),
        c.RuntimeKAssociationRecord(**association, predictor="k", response="mean_completed_runtime_seconds", completed_run_count=1, timeout_count=0, error_count=0, incomplete_runtime_instance_count=0, eligible_instance_count=1, distinct_k_count=1, mean_k=3.0, mean_runtime_seconds=0.001, k_sample_standard_deviation=None, runtime_sample_standard_deviation_seconds=None, pearson_correlation=None, ols_slope_seconds_per_budget_unit=None, ols_intercept_seconds=None, association_status="insufficient_samples"),
        c.SearchNodesDominatedRatioAssociationRecord(**association, predictor="dominated_set_ratio", response="completed_search_nodes", optimal_run_count=1, timeout_count=0, error_count=0, eligible_instance_count=1, distinct_dominated_ratio_count=1, mean_dominated_set_ratio=0.125, mean_search_nodes=13.0, dominated_ratio_sample_standard_deviation=None, search_nodes_sample_standard_deviation=None, pearson_correlation=None, ols_slope_nodes_per_ratio_unit=None, ols_intercept_nodes=None, association_status="insufficient_samples"),
    )


def _unpickle_in_spawn(payload: bytes, queue: multiprocessing.Queue) -> None:
    restored = pickle.loads(payload)
    queue.put((type(restored).__module__, type(restored).__qualname__, pickle.dumps(restored)))


class ContractsCompatibilityTests(unittest.TestCase):
    def test_public_record_api_preserves_csv_helper_errors(self) -> None:
        run_record = _record_fixtures()[1]
        valid = {
            name: "" if value is None else str(value)
            for name, value in run_record.to_csv_row().items()
        }
        mutations = (
            ({name: value for name, value in valid.items() if name != "case"}, "CSV row is missing field(s): case"),
            ({**valid, "extra": "value"}, "CSV row has unknown field(s): 'extra'"),
            ({**valid, "repetition": "not-an-integer"}, "CSV field 'repetition' must be an integer"),
            ({**valid, "runtime_seconds": "infinite"}, "CSV field 'runtime_seconds' must be a number"),
            ({**valid, "timed_out": "true"}, "CSV field 'timed_out' must be 'True' or 'False'"),
        )
        for row, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, f"^{re.escape(message)}$"
            ):
                contracts.RunRecord.from_csv_row(row)

    def test_supported_exports_and_star_import_surface_are_exact(self) -> None:
        self.assertTrue(set(SUPPORTED_CONTRACT_EXPORTS).issubset(vars(contracts)))
        namespace: dict[str, object] = {}
        exec("from maxcover.contracts import *", namespace)
        actual = tuple(sorted(name for name in namespace if name != "__builtins__"))
        self.assertEqual(actual, EXPECTED_CONTRACT_STAR_EXPORTS)

    def test_package_root_export_order_and_identity_are_frozen(self) -> None:
        self.assertEqual(tuple(maxcover.__all__), EXPECTED_PACKAGE_ROOT_EXPORTS)
        for name in EXPECTED_PACKAGE_ROOT_EXPORTS:
            if hasattr(contracts, name):
                with self.subTest(name=name):
                    self.assertIs(getattr(maxcover, name), getattr(contracts, name))
            if name in {"BenchmarkPlan", "plan_benchmark", "replay_instance_file",
                        "run_benchmark", "summarize_benchmark"}:
                with self.subTest(benchmark_export=name):
                    self.assertIs(getattr(maxcover, name), getattr(benchmark, name))

    def test_csv_headers_schema_column_and_class_modules_are_frozen(self) -> None:
        for name, rendered_fields in EXPECTED_CSV_FIELDS.items():
            cls = getattr(contracts, name)
            expected = tuple(rendered_fields.split(","))
            with self.subTest(name=name):
                self.assertEqual(cls.CSV_FIELDS, expected)
                self.assertEqual(cls.CSV_FIELDS[-1], "schema_version")
                self.assertEqual(len(cls.CSV_FIELDS), len(set(cls.CSV_FIELDS)))
        for name in EXPECTED_CLASS_MODULES:
            with self.subTest(name=name):
                self.assertEqual(getattr(contracts, name).__module__, "maxcover.contracts")

    def test_migrated_dataclasses_remain_frozen_and_slotted(self) -> None:
        values = (
            *_record_fixtures(),
            contracts.BenchmarkResult(load_config(ROOT / "configs" / "p3_bnb_ablation.json"), (), (), Path("compatibility-output")),
            contracts.AlgorithmRunOptions(),
            contracts.OptionSpec((int,), "integer", default=1),
            contracts.ParameterSpec((int,), "integer", default=1),
            GENERATORS["uniform"],
            ALGORITHMS["greedy"],
        )
        self.assertEqual(tuple(type(value).__name__ for value in values), EXPECTED_CLASS_MODULES)
        for value in values:
            with self.subTest(name=type(value).__name__):
                self.assertTrue(dataclasses.is_dataclass(value))
                self.assertFalse(hasattr(value, "__dict__"))
                field_name = dataclasses.fields(value)[0].name
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, field_name, getattr(value, field_name))

    def test_record_pickles_load_in_a_fresh_spawn_process(self) -> None:
        context = multiprocessing.get_context("spawn")
        values = (contracts.AlgorithmRunOptions(values={"restarts": 2}), *_record_fixtures())
        for value in values:
            with self.subTest(name=type(value).__name__):
                payload = pickle.dumps(value)
                queue = context.Queue()
                process = context.Process(target=_unpickle_in_spawn, args=(payload, queue))
                process.start()
                module, qualname, restored_payload = queue.get(timeout=15)
                process.join(timeout=15)
                self.assertEqual(process.exitcode, 0)
                self.assertEqual(module, "maxcover.contracts")
                self.assertEqual(qualname, type(value).__qualname__)
                self.assertEqual(pickle.loads(restored_payload), value)
                queue.close()

    def test_baseline_pickle_successes_do_not_regress(self) -> None:
        values = {
            "OptionSpec": contracts.OptionSpec((int,), "integer", default=1),
            "ParameterSpec": contracts.ParameterSpec((int,), "integer", default=1),
            "GeneratorSpec": GENERATORS["uniform"],
        }
        for name, value in values.items():
            with self.subTest(name=name):
                pickle.loads(pickle.dumps(value))


if __name__ == "__main__":
    unittest.main()
