"""Runner-owned artifact inventories and path discovery."""

from __future__ import annotations

from pathlib import Path


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
