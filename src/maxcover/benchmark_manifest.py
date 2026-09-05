"""Benchmark Manifest generation and execution provenance."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from .algorithms import ALGORITHMS
from .config import ExperimentConfig
from .contracts import (
    AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION,
    AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT,
    BNB_NODE_REDUCTION_SCHEMA_VERSION,
    CENSORED_RUNTIME_SCHEMA_VERSION,
    CONFIDENCE_INTERVAL_SCHEMA_VERSION,
    DESCRIPTIVE_STATISTICS_METRICS,
    DESCRIPTIVE_STATISTICS_SCHEMA_VERSION,
    GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION,
    GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION,
    GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION,
    GREEDY_FAILURE_SCHEMA_VERSION,
    HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION,
    InstanceRecord,
    LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION,
    LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION,
    QUALITY_RUNTIME_PARETO_SCHEMA_VERSION,
    REFERENCE_CENSORING_BIAS_SCHEMA_VERSION,
    REFERENCE_COVERAGE_SCHEMA_VERSION,
    REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION,
    REFERENCE_STATUS_SCHEMA_VERSION,
    REFERENCE_STATUSES,
    RUNTIME_K_ASSOCIATION_SCHEMA_VERSION,
    RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION,
    SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION,
)
from .reproducibility import atomic_write_text, file_sha256
from .benchmark_artifacts import _runner_owned_paths
from .benchmark_planning import _RunTask


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _git_state() -> dict[str, object]:
    def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    commit = invoke("rev-parse", "HEAD")
    status = invoke("status", "--porcelain")
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": status.returncode != 0 or bool(status.stdout.strip()),
    }


def _write_manifest(
    *,
    output_dir: Path,
    config_path: Path,
    config: ExperimentConfig,
    identifier: str,
    tasks: Sequence[_RunTask],
    instances: Sequence[InstanceRecord],
    started_at: datetime,
    duration_seconds: float,
    workers: int,
    resumed_runs: int,
    git_state: Mapping[str, object],
) -> None:
    ended_at = datetime.now(timezone.utc)
    output_paths = sorted(
        path
        for path in _runner_owned_paths(output_dir)
        if path.is_file() and path.name != "manifest.json"
    )
    seeds = sorted(
        {task.instance.seed for task in tasks if task.instance.seed is not None}
    )
    outputs = {
        path.relative_to(output_dir).as_posix(): {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in output_paths
        if path.is_file()
    }
    algorithms = {
        algorithm.algorithm_id: {
            "name": algorithm.name,
            "version": ALGORITHMS[algorithm.name].version,
            "enabled": algorithm.enabled,
            "algorithm_seeds": list(algorithm.algorithm_seeds),
            "options": ALGORITHMS[algorithm.name].option_values(algorithm.options),
        }
        for algorithm in config.algorithms
    }
    environment: dict[str, str | None] = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "operating_system": platform.platform(),
        "processor": platform.processor()
        or os.environ.get("PROCESSOR_IDENTIFIER", ""),
    }
    if any(
        algorithm.enabled and algorithm.name == "cp_sat_oracle"
        for algorithm in config.algorithms
    ):
        try:
            environment["ortools"] = package_version("ortools")
        except PackageNotFoundError:
            environment["ortools"] = None

    manifest = {
        "schema_version": 1,
        "experiment": config.name,
        "git": dict(git_state),
        "environment": environment,
        "configuration": {
            "path": str(config_path.resolve()),
            "config_hash": identifier,
        },
        "timing": {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": duration_seconds,
        },
        "seeds": {
            "base_seed": config.base_seed,
            "minimum": min(seeds) if seeds else None,
            "maximum": max(seeds) if seeds else None,
            "count": len(seeds),
        },
        "algorithms": algorithms,
        "execution": {
            "workers": workers,
            "planned_instances": len(instances),
            "planned_runs": len(tasks),
            "resumed_runs": resumed_runs,
        },
        "analysis_contract": {
            "schema_version": 1,
            "canonical_aggregate": "descriptive_statistics.csv",
            "canonical_schema_version": DESCRIPTIVE_STATISTICS_SCHEMA_VERSION,
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "runtime_policy": "optimal_or_feasible_only",
            "compatibility_aggregate": "summary.csv",
            "compatibility_semantics": "legacy_raw_run_aggregate",
        },
        "p6_chart_contract": {
            "schema_version": 1,
            "availability": "always",
            "empty_behavior": "deterministic_placeholder_svg",
            "determinism": "stable_sorting_and_fixed_svg_geometry",
            "compatibility_charts": [
                "gap_by_family.svg",
                "runtime_by_algorithm.svg",
            ],
            "canonical_charts": {
                "gap_by_case.svg": ["descriptive_statistics.csv"],
                "gap_vs_structural_parameter.svg": [
                    "gap_density_association_statistics.csv",
                    "gap_overlap_association_statistics.csv",
                    "gap_clustering_association_statistics.csv",
                ],
                "local_search_recovery.svg": [
                    "local_search_recovery_statistics.csv"
                ],
                "quality_runtime_pareto.svg": [
                    "quality_runtime_pareto_statistics.csv"
                ],
                "runtime_scaling.svg": [
                    "runtime_set_count_association_statistics.csv",
                    "runtime_k_association_statistics.csv",
                ],
                "node_scaling.svg": [
                    "search_nodes_dominated_ratio_association_statistics.csv"
                ],
                "timeout_by_case.svg": [
                    "censored_runtime_statistics.csv"
                ],
                "reference_coverage_by_case.svg": [
                    "reference_status.csv",
                    "reference_coverage_statistics.csv",
                ],
            },
            "sample_annotation": "required",
            "repetition_unit_annotation": "required",
            "exclusion_annotation": "required",
            "association_interpretation": "descriptive_non_causal",
            "runtime_interpretation": "machine_specific",
        },
        "reference_coverage_contract": {
            "schema_version": 1,
            "status_artifact": "reference_status.csv",
            "status_artifact_schema_version": REFERENCE_STATUS_SCHEMA_VERSION,
            "coverage_artifact": "reference_coverage_statistics.csv",
            "coverage_artifact_schema_version": REFERENCE_COVERAGE_SCHEMA_VERSION,
            "censoring_bias_artifact": (
                "reference_censoring_bias_statistics.csv"
            ),
            "censoring_bias_artifact_schema_version": (
                REFERENCE_CENSORING_BIAS_SCHEMA_VERSION
            ),
            "cutoff_sensitivity_artifact": (
                "reference_cutoff_sensitivity_statistics.csv"
            ),
            "cutoff_sensitivity_artifact_schema_version": (
                REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION
            ),
            "denominator": "all_generated_instances_within_family_and_parameters",
            "numerator": "instances_with_at_least_one_validated_optimum_proof",
            "reference_status_precedence": list(REFERENCE_STATUSES),
            "solver_status_detail": (
                "all_enabled_configured_exact_variants_per_instance"
            ),
            "ineligible_solver_status": "not_run",
            "certificate_policy": "validated_independent_optimum_proof",
            "cross_validation_policy": (
                "all_optimal_exact_sources_must_agree; small_instance_flag_requires_"
                "brute_force_and_branch_and_bound_or_cp_sat_agreement"
            ),
            "censoring_bias_estimand": (
                "excluded_mean_minus_retained_mean_within_family_and_parameters"
            ),
            "cutoff_sensitivity_denominator": "all_generated_instances",
            "missing_reference_chart": "reference_coverage_by_case.svg",
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
        },
        "confidence_interval_contract": {
            "schema_version": 1,
            "artifact": "confidence_interval_statistics.csv",
            "artifact_schema_version": CONFIDENCE_INTERVAL_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifact": "descriptive_statistics.csv",
            "source_artifact_schema_version": (
                DESCRIPTIVE_STATISTICS_SCHEMA_VERSION
            ),
            "scope": "all_canonical_descriptive_metric_rows",
            "metrics": sorted(DESCRIPTIVE_STATISTICS_METRICS),
            "estimand": "instance_mean",
            "confidence_level": 0.95,
            "method": "student_t_two_sided",
            "critical_value": (
                "inverse_student_t_cdf_via_regularized_incomplete_beta"
            ),
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "standard_error": (
                "sample_standard_deviation/sqrt(sample_count)"
            ),
            "degrees_of_freedom": "sample_count-1",
            "interval_formula": (
                "mean_plus_or_minus_t_0.975_df_times_standard_error"
            ),
            "minimum_sample_count": 2,
            "zero_sample_policy": "no_samples_blank_mean_and_interval",
            "singleton_policy": (
                "insufficient_samples_mean_present_interval_blank"
            ),
            "bounds_policy": "unbounded_no_domain_clipping",
            "runtime_policy": "completed_runtime_samples_only",
            "timeout_policy": (
                "excluded_from_runtime_samples_and_counted"
            ),
            "error_policy": "excluded_from_samples_and_counted",
            "canonical_precision": (
                "descriptive_statistics_csv_round_trip_and_ci_10_decimal_places"
            ),
            "censored_runtime_analysis": "not_in_scope",
            "significance_testing": "not_in_scope",
        },
        "automatic_conclusion_contract": {
            "schema_version": AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION,
            "source_artifact": "confidence_interval_statistics.csv",
            "source_artifact_schema_version": (
                CONFIDENCE_INTERVAL_SCHEMA_VERSION
            ),
            "scope": "automatic_metric_headlines",
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "minimum_independent_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "eligibility_rule": (
                "interval_status_estimable_and_sample_count_at_least_minimum"
            ),
            "headline_metric": "optimality_gap",
            "headline_estimator": "canonical_instance_equal_weight_mean",
            "ineligible_policy": "suppress_metric_claim_and_report_gate_status",
            "factual_execution_count_policy": (
                "permitted_when_explicitly_marked_non_inferential"
            ),
            "threshold_semantics": (
                "operational_reporting_guardrail_not_power_guarantee"
            ),
            "significance_testing": "not_in_scope",
            "population_generalization": "not_in_scope",
        },
        "p6_automatic_fact_contract": {
            "schema_version": 1,
            "scope": "results_summary_headline_checks",
            "source_artifacts": [
                "descriptive_statistics.csv",
                "local_search_recovery_statistics.csv",
                "censored_runtime_statistics.csv",
            ],
            "local_search_recovery": {
                "estimand": "eligible_pair_count_weighted_mean_gap_recovery_rate",
                "unit": "paired_instance_seed_within_case_variant_pair",
                "empty_policy": "explicit_unavailable_zero_eligible_pairs",
                "interpretation": "fixed_corpus_descriptive_fact",
            },
            "hardest_case": {
                "population": "configured_exact_algorithm_variants",
                "selection_rule": (
                    "maximum_instance_censoring_rate_then_maximum_mean_"
                    "completed_runtime_then_stable_identity"
                ),
                "timeout_policy": "right_censoring_precedes_completed_runtime",
                "error_policy": "counted_but_not_used_as_difficulty_evidence",
                "empty_policy": (
                    "explicit_unavailable_without_completed_or_censored_runtime"
                ),
                "interpretation": (
                    "machine_specific_fixed_corpus_operational_diagnostic"
                ),
            },
            "inference": "none",
            "algorithm_ranking": "not_supported",
            "population_generalization": "not_in_scope",
        },
        "censored_runtime_contract": {
            "schema_version": 1,
            "artifact": "censored_runtime_statistics.csv",
            "artifact_schema_version": CENSORED_RUNTIME_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "scope": "all_executed_algorithm_variants",
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "algorithm_seed_layout_policy": "fixed_within_variant",
            "completed_statuses": ["optimal", "feasible"],
            "right_censored_status": "timeout",
            "error_policy": (
                "excluded_from_runtime_observations_and_counted"
            ),
            "time_to_event_source": "runtime_seconds",
            "timeout_time_semantics": (
                "observed_elapsed_time_to_right_censoring"
            ),
            "configured_time_limit_policy": (
                "not_substituted_for_observed_elapsed_time"
            ),
            "within_instance_censor_time": (
                "arithmetic_mean_across_timeout_algorithm_seeds"
            ),
            "across_instance_censor_time": (
                "equal_weight_mean_median_minimum_maximum"
            ),
            "censoring_rate": (
                "instances_with_any_timeout/instance_count"
            ),
            "fully_right_censored_instance": "all_planned_runs_timeout",
            "zero_censoring_policy": "blank_censor_time_statistics",
            "completed_runtime_statistics_source": (
                "descriptive_statistics.csv"
            ),
            "canonical_precision": (
                "raw_results_csv_round_trip_10_decimal_places"
            ),
            "kaplan_meier": "not_in_scope",
            "survival_curve": "not_in_scope",
            "hazard_model": "not_in_scope",
            "restricted_mean_survival_time": "not_in_scope",
            "confidence_interval": "not_in_scope",
        },
        "optimality_gap_contract": {
            "schema_version": 1,
            "artifact": "descriptive_statistics.csv",
            "artifact_schema_version": DESCRIPTIVE_STATISTICS_SCHEMA_VERSION,
            "row_selector": {"metric": "optimality_gap"},
            "scope": "all_executed_algorithm_variants",
            "group_by": [
                "config_hash",
                "case_id",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "gap_scale": "relative",
            "formula": "(optimum-coverage)/optimum",
            "reference_policy": "normalized_exact_optimum",
            "positive_optimum_required": True,
            "zero_optimum_policy": "count_reference_exclude_gap",
            "eligible_statuses": ["optimal", "feasible", "timeout"],
            "timeout_policy": "include_feasible_incumbent_and_count",
            "error_policy": "exclude_and_count",
            "missing_reference_policy": "exclude",
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "within_instance_aggregation": (
                "arithmetic_mean_of_eligible_runs"
            ),
            "mean_aggregation": "equal_weight_mean_of_instance_gaps",
            "maximum_aggregation": "maximum_of_instance_mean_gaps",
            "sample_count_semantics": "eligible_instance_count",
            "zero_sample_policy": "blank_statistics",
            "coverage_above_optimum_policy": "error",
            "canonical_precision": (
                "raw_results_csv_round_trip_10_decimal_places"
            ),
            "absolute_gap_policy": "not_in_scope",
            "compatibility_aggregate_policy": "summary_csv_excluded",
        },
        "greedy_failure_contract": {
            "schema_version": 1,
            "artifact": "greedy_failure_statistics.csv",
            "artifact_schema_version": GREEDY_FAILURE_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "algorithm": "greedy",
            "algorithm_seed_policy": "forbidden",
            "repetition_unit": "instance_seed",
            "reference_policy": "normalized_exact_optimum",
            "zero_optimum_is_reference": True,
            "eligible_statuses": ["feasible"],
            "denominator": "completed_greedy_with_exact_reference",
            "failure_event": "coverage_lt_optimum",
            "success_event": "coverage_eq_optimum",
            "timeout_policy": "excluded_from_denominator_and_counted",
            "error_policy": "excluded_from_denominator_and_counted",
            "missing_reference_policy": "excluded_from_denominator_and_counted",
            "zero_denominator_policy": "blank_rates",
        },
        "local_search_recovery_contract": {
            "schema_version": 1,
            "artifact": "local_search_recovery_statistics.csv",
            "artifact_schema_version": LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "algorithm_pair": ["greedy", "local_search"],
            "variant_pairing": "cross_product_within_case",
            "algorithm_seed_policy": "forbidden",
            "repetition_unit": "instance_seed",
            "reference_policy": "normalized_exact_optimum",
            "zero_optimum_policy": "not_a_greedy_failure",
            "greedy_failure_event": "greedy_coverage_lt_optimum",
            "eligible_statuses": {
                "greedy": ["feasible"],
                "local_search": ["feasible"],
            },
            "denominator": (
                "completed_local_search_on_completed_greedy_failure_with_"
                "exact_reference"
            ),
            "formula": (
                "(local_search_coverage-greedy_coverage)/"
                "(optimum-greedy_coverage)"
            ),
            "aggregation": "equal_weight_mean_of_instance_recovery_rates",
            "timeout_policy": "exclude_pair_and_count_by_algorithm",
            "error_policy": "exclude_pair_and_count_by_algorithm",
            "missing_reference_policy": "exclude_pair",
            "greedy_optimal_policy": "exclude_no_recoverable_gap",
            "local_search_below_greedy_policy": "error",
            "coverage_above_optimum_policy": "error",
            "zero_denominator_policy": "blank_rates",
            "remaining_gap_policy": (
                "separate_local_search_remaining_gap_statistics_artifact"
            ),
            "runtime_policy": "not_in_scope",
        },
        "local_search_remaining_gap_contract": {
            "schema_version": 1,
            "artifact": "local_search_remaining_gap_statistics.csv",
            "artifact_schema_version": (
                LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "algorithm_pair": ["greedy", "local_search"],
            "variant_pairing": "cross_product_within_case",
            "algorithm_seed_policy": "forbidden",
            "repetition_unit": "instance_seed",
            "reference_policy": "normalized_exact_optimum",
            "greedy_failure_event": "greedy_coverage_lt_optimum",
            "eligible_statuses": {
                "greedy": ["feasible"],
                "local_search": ["feasible"],
            },
            "denominator": (
                "completed_local_search_on_completed_greedy_failure_with_"
                "exact_reference"
            ),
            "gap_scale": "relative_to_optimum",
            "formula": "(optimum-local_search_coverage)/optimum",
            "mean_aggregation": (
                "equal_weight_mean_of_eligible_instance_remaining_gaps"
            ),
            "maximum_aggregation": (
                "maximum_of_eligible_instance_remaining_gaps"
            ),
            "zero_gap_event": "local_search_coverage_eq_optimum",
            "timeout_policy": "exclude_pair",
            "error_policy": "exclude_pair",
            "missing_reference_policy": "exclude_pair",
            "greedy_optimal_policy": "exclude_no_recoverable_gap",
            "local_search_below_greedy_policy": "error",
            "coverage_above_optimum_policy": "error",
            "zero_denominator_policy": "blank_statistics",
            "canonical_precision": (
                "raw_results_csv_round_trip_10_decimal_places"
            ),
            "runtime_policy": "not_in_scope",
        },
        "heuristic_exact_runtime_ratio_contract": {
            "schema_version": 1,
            "artifact": "heuristic_exact_runtime_ratio_statistics.csv",
            "artifact_schema_version": (
                HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "scope": "all_executed_heuristic_exact_variant_pairs",
            "variant_pairing": "cross_product_within_case",
            "repetition_unit": "instance_seed",
            "heuristic_algorithm_seed_role": "nested_within_instance",
            "exact_algorithm_seed_policy": "forbidden",
            "eligible_statuses": ["optimal", "feasible"],
            "within_instance_heuristic_runtime": (
                "arithmetic_mean_of_completed_algorithm_seed_runs"
            ),
            "formula": (
                "mean_completed_heuristic_runtime/exact_runtime"
            ),
            "aggregation": {
                "mean": "equal_weight_mean_of_instance_ratios",
                "median": "median_of_instance_ratios",
                "minimum": "minimum_of_instance_ratios",
                "maximum": "maximum_of_instance_ratios",
            },
            "timeout_policy": "exclude_runtime_and_count_by_algorithm",
            "error_policy": "exclude_runtime_and_count_by_algorithm",
            "zero_exact_runtime_policy": "exclude_pair_and_count",
            "zero_eligible_policy": "blank_statistics",
            "canonical_precision": (
                "raw_results_csv_round_trip_10_decimal_places"
            ),
            "censored_runtime_analysis": "not_in_scope",
        },
        "bnb_node_reduction_contract": {
            "schema_version": 1,
            "artifact": "bnb_node_reduction_statistics.csv",
            "artifact_schema_version": BNB_NODE_REDUCTION_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "algorithm_pair": [
                "branch_and_bound",
                "branch_and_bound_enhanced",
            ],
            "variant_pairing": "cross_product_within_case",
            "algorithm_seed_policy": "forbidden",
            "repetition_unit": "instance_seed",
            "eligible_statuses": ["optimal"],
            "objective_agreement_policy": "required",
            "node_source": (
                "nodes_or_iterations_validated_against_metadata_when_present"
            ),
            "formula": "1-enhanced_nodes/baseline_nodes",
            "aggregation": {
                "mean": "equal_weight_mean_of_instance_reductions",
                "median": "median_of_instance_reductions",
                "minimum": "minimum_of_instance_reductions",
                "maximum": "maximum_of_instance_reductions",
                "aggregate": "1-sum_enhanced_nodes/sum_baseline_nodes",
            },
            "timeout_policy": "exclude_pair_and_count_by_algorithm",
            "error_policy": "exclude_pair_and_count_by_algorithm",
            "zero_baseline_nodes_policy": "exclude_pair_and_count",
            "negative_reduction_policy": "retain",
            "zero_eligible_policy": "blank_statistics_and_zero_totals",
            "canonical_precision": (
                "raw_results_csv_round_trip_10_decimal_places"
            ),
            "runtime_policy": "not_in_scope",
        },
        "quality_runtime_pareto_contract": {
            "schema_version": 1,
            "artifact": "quality_runtime_pareto_statistics.csv",
            "artifact_schema_version": QUALITY_RUNTIME_PARETO_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "scope": "all_executed_algorithm_variants",
            "comparison_scope": "within_case",
            "variant_unit_policy": "identical_instance_units",
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "algorithm_seed_layout_policy": "fixed_within_variant",
            "reference_policy": "normalized_positive_exact_optimum",
            "zero_optimum_policy": "exclude_and_count",
            "quality_metric": "mean_relative_optimality_gap",
            "quality_formula": "(optimum-coverage)/optimum",
            "runtime_metric": "mean_completed_runtime_seconds",
            "eligible_statuses": ["optimal", "feasible"],
            "eligible_instance_policy": (
                "positive_reference_and_all_runs_of_all_variants_completed"
            ),
            "within_instance_aggregation": (
                "arithmetic_mean_across_algorithm_seeds"
            ),
            "across_instance_aggregation": (
                "equal_weight_arithmetic_mean"
            ),
            "objectives": {
                "mean_relative_gap": "minimize",
                "mean_runtime_seconds": "minimize",
            },
            "dominance": (
                "no_worse_on_both_objectives_and_strictly_better_on_at_least_one"
            ),
            "tie_policy": "identical_points_are_co_frontier",
            "timeout_policy": (
                "exclude_instance_from_all_points_and_count_by_variant"
            ),
            "error_policy": (
                "exclude_instance_from_all_points_and_count_by_variant"
            ),
            "zero_eligible_policy": "not_evaluable_blank_coordinates",
            "canonical_precision": (
                "raw_results_csv_round_trip_and_coordinates_10_decimal_places"
            ),
            "censored_runtime_analysis": "not_in_scope",
        },
        "gap_density_association_contract": {
            "schema_version": 1,
            "artifact": "gap_density_association_statistics.csv",
            "artifact_schema_version": (
                GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifacts": [
                "instances.csv",
                "raw_results.csv",
            ],
            "scope": "all_executed_algorithm_variants",
            "group_by": [
                "config_hash",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "case_pooling": "within_family_across_executed_cases",
            "cross_family_pooling": "forbidden",
            "predictor": "actual_density",
            "predictor_source": "instances.csv",
            "response": "relative_optimality_gap",
            "response_formula": "(optimum-coverage)/optimum",
            "reference_policy": "normalized_positive_exact_optimum",
            "zero_optimum_policy": "exclude_and_count",
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "algorithm_seed_layout_policy": "fixed_within_variant",
            "within_instance_gap": (
                "arithmetic_mean_across_available_algorithm_seed_gaps"
            ),
            "across_instance_weighting": "equal",
            "timeout_policy": (
                "include_feasible_incumbent_gap_when_available_and_count"
            ),
            "error_policy": "exclude_gap_and_count",
            "minimum_sample_count": 2,
            "statistics": [
                "sample_means",
                "sample_standard_deviations",
                "pearson_correlation",
                "ols_slope_with_intercept",
            ],
            "constant_density_policy": "blank_correlation_and_ols",
            "constant_gap_policy": (
                "blank_correlation_zero_slope_intercept_equals_mean_gap"
            ),
            "canonical_precision": (
                "instances_and_raw_csv_round_trip_then_10_decimal_statistics"
            ),
            "automatic_headline": "not_emitted",
            "automatic_conclusion_minimum_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
            "nonlinear_modeling": "not_in_scope",
        },
        "gap_overlap_association_contract": {
            "schema_version": 1,
            "artifact": "gap_overlap_association_statistics.csv",
            "artifact_schema_version": (
                GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifacts": [
                "instances.csv",
                "raw_results.csv",
            ],
            "scope": "all_executed_algorithm_variants",
            "group_by": [
                "config_hash",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "case_pooling": "within_family_across_executed_cases",
            "cross_family_pooling": "forbidden",
            "predictor": "pairwise_overlap_mean_jaccard",
            "predictor_source": "instances.csv",
            "predictor_definition": (
                "mean_jaccard_across_valid_unordered_candidate_set_pairs"
            ),
            "missing_predictor_policy": "exclude_and_count_not_zero_fill",
            "response": "relative_optimality_gap",
            "response_formula": "(optimum-coverage)/optimum",
            "reference_policy": "normalized_positive_exact_optimum",
            "zero_optimum_policy": "exclude_and_count",
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "algorithm_seed_layout_policy": "fixed_within_variant",
            "within_instance_gap": (
                "arithmetic_mean_across_available_algorithm_seed_gaps"
            ),
            "across_instance_weighting": "equal",
            "timeout_policy": (
                "include_feasible_incumbent_gap_when_available_and_count"
            ),
            "error_policy": "exclude_gap_and_count",
            "minimum_sample_count": 2,
            "statistics": [
                "sample_means",
                "sample_standard_deviations",
                "pearson_correlation",
                "ols_slope_with_intercept",
            ],
            "constant_overlap_policy": "blank_correlation_and_ols",
            "constant_gap_policy": (
                "blank_correlation_zero_slope_intercept_equals_mean_gap"
            ),
            "canonical_precision": (
                "instances_and_raw_csv_round_trip_then_10_decimal_statistics"
            ),
            "automatic_headline": "not_emitted",
            "automatic_conclusion_minimum_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
            "clustering_analysis": "not_in_scope",
            "nonlinear_modeling": "not_in_scope",
        },
        "gap_clustering_association_contract": {
            "schema_version": 1,
            "artifact": "gap_clustering_association_statistics.csv",
            "artifact_schema_version": (
                GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifacts": ["instances.csv", "raw_results.csv"],
            "scope": "mixed_cluster_executed_algorithm_variants_only",
            "required_family": "mixed_cluster",
            "required_research_question_id": "mixed_cluster_bridges",
            "group_by": [
                "config_hash",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "predictor": "realized_bridge_fraction",
            "predictor_source": "instances.csv.parameters",
            "predictor_formula": "bridge_count/set_count",
            "predictor_direction": (
                "higher_means_more_cross_cluster_mixing_not_stronger_clustering"
            ),
            "target_bridge_fraction_policy": "not_used_as_predictor",
            "pairwise_overlap_policy": "not_used_as_clustering_proxy",
            "response": "level_mean_relative_optimality_gap",
            "response_formula": "(optimum-coverage)/optimum",
            "reference_policy": "normalized_positive_exact_optimum",
            "zero_optimum_policy": "exclude_instance_and_invalidate_block",
            "repetition_unit": "coupling_seed_block",
            "coupling_identity": ["coupling_pair_id", "coupling_seed"],
            "block_layout_policy": "fixed_case_levels_across_blocks",
            "complete_block_policy": (
                "all_levels_require_usable_gap_or_drop_block_from_all_levels"
            ),
            "algorithm_seed_role": "nested_within_instance_with_fixed_layout",
            "within_instance_gap": (
                "arithmetic_mean_across_available_algorithm_seed_gaps"
            ),
            "within_level_gap": (
                "arithmetic_mean_across_same_eligible_complete_blocks"
            ),
            "across_level_weighting": "equal",
            "association_coordinates": (
                "case_level_predictor_and_complete_block_mean_gap"
            ),
            "timeout_policy": (
                "include_feasible_incumbent_gap_when_available_and_count"
            ),
            "error_policy": "exclude_gap_invalidate_block_and_count",
            "minimum_level_count": 2,
            "statistics": [
                "level_means",
                "level_sample_standard_deviations",
                "pearson_correlation",
                "ols_slope_with_intercept",
            ],
            "constant_clustering_policy": "blank_correlation_and_ols",
            "constant_gap_policy": (
                "blank_correlation_zero_slope_intercept_equals_mean_gap"
            ),
            "canonical_precision": (
                "instances_and_raw_csv_round_trip_then_10_decimal_statistics"
            ),
            "automatic_headline": "not_emitted",
            "automatic_conclusion_independent_count": "eligible_block_count",
            "automatic_conclusion_minimum_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
            "mixed_effects_modeling": "not_in_scope",
            "nonlinear_modeling": "not_in_scope",
        },
        "runtime_set_count_association_contract": {
            "schema_version": 1,
            "artifact": "runtime_set_count_association_statistics.csv",
            "artifact_schema_version": (
                RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifacts": ["instances.csv", "raw_results.csv"],
            "scope": "all_executed_algorithm_variants",
            "group_by": [
                "config_hash",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "case_pooling": "within_family_across_executed_cases",
            "cross_family_pooling": "forbidden",
            "predictor": "set_count",
            "predictor_source": "instances.csv",
            "predictor_definition": "actual_candidate_set_count",
            "unique_or_preprocessed_set_count_policy": "not_substituted",
            "response": "mean_completed_runtime_seconds",
            "eligible_statuses": ["optimal", "feasible"],
            "complete_instance_policy": (
                "all_planned_algorithm_seed_runs_must_be_completed"
            ),
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "algorithm_seed_layout_policy": "fixed_within_variant",
            "within_instance_runtime": (
                "arithmetic_mean_across_all_completed_algorithm_seed_runs"
            ),
            "across_instance_weighting": "equal",
            "timeout_policy": "exclude_entire_instance_and_count",
            "error_policy": "exclude_entire_instance_and_count",
            "censored_runtime_artifact": "censored_runtime_statistics.csv",
            "minimum_sample_count": 2,
            "statistics": [
                "sample_means",
                "sample_standard_deviations",
                "pearson_correlation",
                "ols_slope_with_intercept",
            ],
            "ols_slope_unit": "seconds_per_candidate_set",
            "constant_set_count_policy": "blank_correlation_and_ols",
            "constant_runtime_policy": (
                "blank_correlation_zero_slope_intercept_equals_mean_runtime"
            ),
            "canonical_precision": (
                "instances_and_raw_csv_round_trip_then_10_decimal_statistics"
            ),
            "automatic_headline": "not_emitted",
            "automatic_conclusion_independent_count": (
                "eligible_instance_count"
            ),
            "automatic_conclusion_minimum_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
            "survival_modeling": "not_in_scope",
            "nonlinear_or_log_modeling": "not_in_scope",
            "asymptotic_complexity_claim": "not_in_scope",
            "cross_machine_runtime_comparison": "not_in_scope",
        },
        "runtime_k_association_contract": {
            "schema_version": 1,
            "artifact": "runtime_k_association_statistics.csv",
            "artifact_schema_version": RUNTIME_K_ASSOCIATION_SCHEMA_VERSION,
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifacts": ["instances.csv", "raw_results.csv"],
            "scope": "all_executed_algorithm_variants",
            "group_by": [
                "config_hash",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "case_pooling": "within_family_across_executed_cases",
            "cross_family_pooling": "forbidden",
            "predictor": "k",
            "predictor_source": "instances.csv",
            "predictor_definition": "actual_instance_selection_budget",
            "selected_count_or_algorithm_option_policy": "not_substituted",
            "response": "mean_completed_runtime_seconds",
            "eligible_statuses": ["optimal", "feasible"],
            "complete_instance_policy": (
                "all_planned_algorithm_seed_runs_must_be_completed"
            ),
            "repetition_unit": "instance_seed",
            "algorithm_seed_role": "nested_within_instance",
            "algorithm_seed_layout_policy": "fixed_within_variant",
            "within_instance_runtime": (
                "arithmetic_mean_across_all_completed_algorithm_seed_runs"
            ),
            "across_instance_weighting": "equal",
            "cross_k_pairing": "not_used_independent_instance_seeds",
            "timeout_policy": "exclude_entire_instance_and_count",
            "error_policy": "exclude_entire_instance_and_count",
            "censored_runtime_artifact": "censored_runtime_statistics.csv",
            "minimum_sample_count": 2,
            "statistics": [
                "sample_means",
                "sample_standard_deviations",
                "pearson_correlation",
                "ols_slope_with_intercept",
            ],
            "ols_slope_unit": "seconds_per_selection_budget_unit",
            "constant_k_policy": "blank_correlation_and_ols",
            "constant_runtime_policy": (
                "blank_correlation_zero_slope_intercept_equals_mean_runtime"
            ),
            "canonical_precision": (
                "instances_and_raw_csv_round_trip_then_10_decimal_statistics"
            ),
            "automatic_headline": "not_emitted",
            "automatic_conclusion_independent_count": (
                "eligible_instance_count"
            ),
            "automatic_conclusion_minimum_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
            "survival_modeling": "not_in_scope",
            "nonlinear_or_log_modeling": "not_in_scope",
            "asymptotic_complexity_claim": "not_in_scope",
            "cross_machine_runtime_comparison": "not_in_scope",
            "quality_stability_claim": "not_in_scope",
        },
        "search_nodes_dominated_ratio_association_contract": {
            "schema_version": 1,
            "artifact": (
                "search_nodes_dominated_ratio_association_statistics.csv"
            ),
            "artifact_schema_version": (
                SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION
            ),
            "availability": "always",
            "empty_behavior": "header_only",
            "source_artifacts": ["instances.csv", "raw_results.csv"],
            "scope": "executed_branch_and_bound_variants_only",
            "algorithms": [
                "branch_and_bound",
                "branch_and_bound_enhanced",
            ],
            "group_by": [
                "config_hash",
                "family",
                "algorithm_id",
                "algorithm",
            ],
            "case_pooling": "within_family_across_executed_cases",
            "cross_family_pooling": "forbidden",
            "predictor": "dominated_set_ratio",
            "predictor_source": "instances.csv",
            "predictor_definition": "dominated_set_count/set_count",
            "dominated_unique_or_preprocessed_policy": "not_substituted",
            "response": "completed_search_nodes",
            "node_source": (
                "nodes_or_iterations_validated_against_metadata_when_present"
            ),
            "eligible_statuses": ["optimal"],
            "repetition_unit": "instance_seed",
            "algorithm_seed_policy": "forbidden",
            "within_instance_run_policy": "exactly_one",
            "across_instance_weighting": "equal",
            "timeout_policy": "exclude_partial_search_and_count",
            "error_policy": "exclude_and_count",
            "minimum_sample_count": 2,
            "statistics": [
                "sample_means",
                "sample_standard_deviations",
                "pearson_correlation",
                "ols_slope_with_intercept",
            ],
            "ols_slope_unit": "search_nodes_per_dominated_ratio_unit",
            "constant_dominated_ratio_policy": "blank_correlation_and_ols",
            "constant_nodes_policy": (
                "blank_correlation_zero_slope_intercept_equals_mean_nodes"
            ),
            "canonical_precision": (
                "instances_and_raw_csv_round_trip_then_10_decimal_statistics"
            ),
            "automatic_headline": "not_emitted",
            "automatic_conclusion_independent_count": (
                "eligible_instance_count"
            ),
            "automatic_conclusion_minimum_sample_count": (
                AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
            ),
            "heuristic_iterations": "not_in_scope",
            "brute_force_enumeration": "not_in_scope",
            "significance_testing": "not_in_scope",
            "causal_inference": "not_in_scope",
            "nonlinear_or_log_modeling": "not_in_scope",
            "asymptotic_complexity_claim": "not_in_scope",
            "cross_machine_comparison": "not_in_scope",
        },
        "outputs": outputs,
    }
    atomic_write_text(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
