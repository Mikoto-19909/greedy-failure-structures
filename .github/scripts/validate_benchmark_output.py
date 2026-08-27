"""Validate a completed benchmark using the project's own public contracts.

Why this exists separately from the benchmark itself
---------------------------------------------------
`manifest.json` carries a checksum, and verifying it proves the files were not
altered after they were written. It cannot prove they were written correctly: a
run that computed a statistic wrongly, wrote a CSV under the wrong schema
version, or pooled algorithm seeds without averaging them in-instance first
produces output whose checksum matches perfectly.

So this reads the artifacts back and recomputes what they claim from the
configuration alone. Prefer it over trusting the manifest checksum by itself.

Scope, and one coupling worth stating
-------------------------------------
The recomputation imports statistics helpers from `maxcover.benchmark` that are
private by name. That is a real coupling: an internal refactor of `benchmark.py`
can break this validator, which is the opposite of what an independent check
should depend on. Promoting those helpers to a public API is the correct fix, but
it touches the reproducibility contracts around `run_id`, so it is left as
separate work rather than bundled into the change that first made this validator
available here.

Exit status is 0 when every artifact validates and 1 otherwise, so it works as a
CI gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import TypeVar


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import (  # noqa: E402
    _bnb_node_reduction_statistics,
    _canonical_instance_records,
    _canonical_run_records,
    _censored_runtime_statistics,
    _confidence_interval_statistics,
    _descriptive_statistics,
    _greedy_failure_statistics,
    _gap_density_association_statistics,
    _gap_overlap_association_statistics,
    _gap_clustering_association_statistics,
    _heuristic_exact_runtime_ratio_statistics,
    _local_search_recovery_statistics,
    _local_search_remaining_gap_statistics,
    _normalize_optima,
    _instances_for_config,
    _quality_runtime_pareto_statistics,
    _runtime_k_association_statistics,
    _runtime_set_count_association_statistics,
    _search_nodes_dominated_ratio_association_statistics,
    plan_benchmark,
)
from maxcover.config import load_config  # noqa: E402
from maxcover.contracts import (  # noqa: E402
    AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION,
    AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT,
    BNB_NODE_REDUCTION_SCHEMA_VERSION,
    BranchAndBoundNodeReductionRecord,
    CENSORED_RUNTIME_SCHEMA_VERSION,
    CensoredRuntimeRecord,
    CONFIDENCE_INTERVAL_SCHEMA_VERSION,
    ConfidenceIntervalRecord,
    DESCRIPTIVE_STATISTICS_METRICS,
    DESCRIPTIVE_STATISTICS_SCHEMA_VERSION,
    DescriptiveStatisticsRecord,
    GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION,
    GapDensityAssociationRecord,
    GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION,
    GapOverlapAssociationRecord,
    GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION,
    GapClusteringAssociationRecord,
    GREEDY_FAILURE_SCHEMA_VERSION,
    GreedyFailureRecord,
    HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION,
    HeuristicExactRuntimeRatioRecord,
    InstanceRecord,
    LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION,
    LocalSearchRecoveryRecord,
    LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION,
    LocalSearchRemainingGapRecord,
    QUALITY_RUNTIME_PARETO_SCHEMA_VERSION,
    QualityRuntimeParetoRecord,
    RUNTIME_K_ASSOCIATION_SCHEMA_VERSION,
    RuntimeKAssociationRecord,
    RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION,
    RuntimeSetCountAssociationRecord,
    SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION,
    SearchNodesDominatedRatioAssociationRecord,
    RunRecord,
    SummaryRecord,
)
from maxcover.model import SolutionStatus  # noqa: E402
from maxcover.reporting import (  # noqa: E402
    _headline_lines,
    _render_gap_by_case_chart,
    _render_gap_structural_association_chart,
    _render_local_search_recovery_chart,
    _render_node_scaling_chart,
    _render_quality_runtime_pareto_chart,
    _render_runtime_scaling_chart,
    _render_timeout_by_case_chart,
)
from maxcover.reproducibility import config_hash  # noqa: E402


Record = TypeVar(
    "Record",
    InstanceRecord,
    RunRecord,
    SummaryRecord,
    DescriptiveStatisticsRecord,
    GreedyFailureRecord,
    LocalSearchRecoveryRecord,
    LocalSearchRemainingGapRecord,
    HeuristicExactRuntimeRatioRecord,
    BranchAndBoundNodeReductionRecord,
    QualityRuntimeParetoRecord,
    ConfidenceIntervalRecord,
    CensoredRuntimeRecord,
    GapDensityAssociationRecord,
    GapOverlapAssociationRecord,
    GapClusteringAssociationRecord,
    RuntimeSetCountAssociationRecord,
    RuntimeKAssociationRecord,
    SearchNodesDominatedRatioAssociationRecord,
)

# The manifest's own schema version, as written by `benchmark.py`.
#
# Declared here rather than imported because `benchmark.py` writes the value
# inline and exposes no constant for it. Introducing one would mean editing a
# 5000-line module that is exempt from type checking, which does not belong in
# the change that first brings this validator into the repository. The coupling
# is therefore explicit and asserted by tests/test_output_validation.py, so a
# future bump fails loudly here instead of passing silently.
MANIFEST_SCHEMA_VERSION = 1

REQUIRED_OUTPUTS = {
    "bnb_node_reduction_statistics.csv",
    "censored_runtime_statistics.csv",
    "confidence_interval_statistics.csv",
    "descriptive_statistics.csv",
    "gap_by_family.svg",
    "gap_by_case.svg",
    "gap_vs_structural_parameter.svg",
    "greedy_failure_statistics.csv",
    "gap_density_association_statistics.csv",
    "gap_overlap_association_statistics.csv",
    "gap_clustering_association_statistics.csv",
    "runtime_set_count_association_statistics.csv",
    "runtime_k_association_statistics.csv",
    "search_nodes_dominated_ratio_association_statistics.csv",
    "heuristic_exact_runtime_ratio_statistics.csv",
    "instances.csv",
    "local_search_recovery_statistics.csv",
    "local_search_remaining_gap_statistics.csv",
    "local_search_recovery.svg",
    "quality_runtime_pareto_statistics.csv",
    "quality_runtime_pareto.svg",
    "runtime_scaling.svg",
    "node_scaling.svg",
    "timeout_by_case.svg",
    "raw_results.csv",
    "results_summary.md",
    "runtime_by_algorithm.svg",
    "summary.csv",
}


def _fail(message: str) -> None:
    raise ValueError(message)


def _load_records(
    path: Path, record_type: type[Record], *, allow_empty: bool = False
) -> list[Record]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != record_type.CSV_FIELDS:
            _fail(f"{path.name} header does not match {record_type.__name__}")
        records = [record_type.from_csv_row(row) for row in reader]
    if not records and not allow_empty:
        _fail(f"{path.name} contains no records")
    return records


def _non_negative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{label} must be a non-negative integer")
    return value


def _dense_greedy_reference(instance: object) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...]]:
    """Recompute the deterministic dense-Greedy trajectory independently."""

    selected: list[int] = []
    trajectory: list[tuple[int, int]] = []
    covered = 0
    available = set(range(instance.set_count))
    for iteration in range(instance.k):
        best = max(
            available,
            key=lambda index: (
                (instance.sets[index] & ~covered).bit_count(),
                -index,
            ),
        )
        gain = (instance.sets[best] & ~covered).bit_count()
        selected.append(best)
        trajectory.append((best, gain))
        covered |= instance.sets[best]
        available.remove(best)
    return tuple(selected), tuple(trajectory)


def _validate_declared_algorithm_rows(config: object, plan: object, rows: list[object]) -> None:
    expected = Counter()
    algorithms_by_id = {
        algorithm.algorithm_id: algorithm for algorithm in config.algorithms
        if algorithm.enabled
    }
    for algorithm_id, count in plan.runs_by_algorithm:
        expected[(algorithm_id, algorithms_by_id[algorithm_id].name)] = count
    actual = Counter((row.algorithm_id, row.algorithm) for row in rows)
    if actual != expected:
        _fail("raw results algorithm variants do not match the execution plan")


def _validate_lazy_greedy_rows(config: object, rows: list[object]) -> None:
    lazy_variants = [
        algorithm for algorithm in config.algorithms
        if algorithm.enabled and algorithm.name == "lazy_greedy"
    ]
    if not lazy_variants:
        return
    greedy_variants = [
        algorithm for algorithm in config.algorithms
        if algorithm.enabled and algorithm.name == "greedy"
    ]
    if len(lazy_variants) != 1 or len(greedy_variants) != 1:
        _fail("Lazy Greedy validation requires exactly one Greedy and one Lazy Greedy variant")

    planned_instances = _instances_for_config(config)
    instances_by_unit = {
        (planned.case_id, planned.repetition, planned.instance_id): planned.instance
        for planned in planned_instances
    }
    pair_rows: dict[tuple[str, int, str], dict[str, object]] = {}
    expected_algorithms = {
        greedy_variants[0].algorithm_id: "greedy",
        lazy_variants[0].algorithm_id: "lazy_greedy",
    }
    for row in rows:
        algorithm_name = expected_algorithms.get(row.algorithm_id)
        if algorithm_name is None:
            continue
        unit = (row.case_id, row.repetition, row.instance_id)
        by_algorithm = pair_rows.setdefault(unit, {})
        if algorithm_name in by_algorithm:
            _fail("Lazy Greedy pairing contains duplicate algorithm rows")
        by_algorithm[algorithm_name] = row

    if set(pair_rows) != set(instances_by_unit):
        _fail("Lazy Greedy pairing does not cover exactly the planned instance units")

    for unit, by_algorithm in sorted(pair_rows.items()):
        greedy_row = by_algorithm.get("greedy")
        lazy_row = by_algorithm.get("lazy_greedy")
        if greedy_row is None or lazy_row is None:
            _fail("each instance unit must contain Greedy and Lazy Greedy rows")
        if greedy_row.coverage != lazy_row.coverage or greedy_row.selected != lazy_row.selected:
            _fail("Greedy and Lazy Greedy results disagree on an instance unit")

        instance = instances_by_unit[unit]
        expected_selected, expected_trajectory = _dense_greedy_reference(instance)
        dense_evaluations = instance.set_count * instance.k - (
            instance.k * (instance.k - 1) // 2
        )
        if greedy_row.nodes_or_iterations != dense_evaluations:
            _fail("Greedy nodes_or_iterations does not match dense candidate evaluations")
        if lazy_row.selected != tuple(sorted(expected_selected)):
            _fail("Lazy Greedy selected set does not match the dense reference")

        try:
            metadata = json.loads(lazy_row.algorithm_metadata)
        except json.JSONDecodeError as error:
            _fail(f"Lazy Greedy metadata is not valid JSON: {error}")
        search = metadata.get("search")
        trajectory = metadata.get("trajectory")
        if not isinstance(search, dict) or not isinstance(trajectory, list):
            _fail("Lazy Greedy metadata must contain search and trajectory")
        initial = _non_negative_integer(
            search.get("initial_candidate_count"),
            "Lazy Greedy initial_candidate_count",
        )
        marginal_evaluations = _non_negative_integer(
            search.get("marginal_evaluations"),
            "Lazy Greedy marginal_evaluations",
        )
        priority_queue_pops = _non_negative_integer(
            search.get("priority_queue_pops"),
            "Lazy Greedy priority_queue_pops",
        )
        selected_count = _non_negative_integer(
            search.get("selected_count"),
            "Lazy Greedy selected_count",
        )
        if initial != instance.set_count or selected_count != instance.k:
            _fail("Lazy Greedy metadata dimensions do not match the instance")
        if marginal_evaluations != initial + priority_queue_pops:
            _fail("Lazy Greedy marginal evaluations do not include initial queue evaluation")
        if lazy_row.nodes_or_iterations != marginal_evaluations:
            _fail("Lazy Greedy work field does not match marginal_evaluations")
        if len(trajectory) != instance.k:
            _fail("Lazy Greedy trajectory length does not match k")

        observed_trajectory: list[tuple[int, int]] = []
        previous_evaluations = initial
        for iteration, point in enumerate(trajectory, start=1):
            if not isinstance(point, dict) or point.get("iteration") != iteration:
                _fail("Lazy Greedy trajectory has an invalid iteration")
            selected_index = _non_negative_integer(
                point.get("selected_index"),
                "Lazy Greedy trajectory selected_index",
            )
            marginal_gain = _non_negative_integer(
                point.get("marginal_gain"),
                "Lazy Greedy trajectory marginal_gain",
            )
            cumulative = _non_negative_integer(
                point.get("marginal_evaluations"),
                "Lazy Greedy trajectory marginal_evaluations",
            )
            if cumulative < previous_evaluations:
                _fail("Lazy Greedy trajectory evaluation counts are not monotone")
            previous_evaluations = cumulative
            observed_trajectory.append((selected_index, marginal_gain))
        if tuple(observed_trajectory) != expected_trajectory:
            _fail("Lazy Greedy trajectory does not match the dense reference")
        if previous_evaluations != marginal_evaluations:
            _fail("Lazy Greedy trajectory does not end at the reported work count")


def _markdown_section(
    document: str, heading: str, next_heading: str
) -> list[str]:
    lines = document.splitlines()
    try:
        start = lines.index(heading) + 1
        end = lines.index(next_heading, start)
    except ValueError as error:
        _fail(f"results_summary.md is missing section boundary: {error}")
    while start < end and lines[start] == "":
        start += 1
    while end > start and lines[end - 1] == "":
        end -= 1
    return lines[start:end]


def _validate_manifest(output: Path, manifest: dict[str, object]) -> None:
    # The manifest's own schema version, before anything inside it is trusted.
    #
    # This was missing, and a test written from the declaration rather than from
    # this function found it: a manifest could claim any schema version at all
    # and still validate, because only the `outputs` array was ever examined.
    # That is the failure this whole script exists to catch — output that was
    # written wrongly rather than altered afterwards — appearing in the checker
    # itself. Every artifact's own schema version is verified elsewhere; the
    # container's was not.
    declared = manifest.get("schema_version")
    if declared != MANIFEST_SCHEMA_VERSION:
        _fail(
            f"manifest schema_version is {declared!r}, expected "
            f"{MANIFEST_SCHEMA_VERSION}"
        )

    listed = manifest.get("outputs")
    if not isinstance(listed, dict):
        _fail("manifest outputs must be an object")
    missing = REQUIRED_OUTPUTS - listed.keys()
    if missing:
        _fail(f"manifest is missing required outputs: {sorted(missing)}")

    output_root = output.resolve()
    for filename, raw_metadata in listed.items():
        if not isinstance(filename, str) or not isinstance(raw_metadata, dict):
            _fail("manifest output entries must map filenames to objects")
        artifact = (output / filename).resolve()
        try:
            artifact.relative_to(output_root)
        except ValueError:
            _fail(f"manifest output escapes output directory: {filename!r}")
        if not artifact.is_file():
            _fail(f"manifest output does not exist: {filename}")
        payload = artifact.read_bytes()
        if raw_metadata.get("bytes") != len(payload):
            _fail(f"byte count mismatch for {filename}")
        if raw_metadata.get("sha256") != hashlib.sha256(payload).hexdigest():
            _fail(f"SHA-256 mismatch for {filename}")


def validate(config_path: Path, output: Path) -> None:
    config = load_config(config_path)
    plan = plan_benchmark(config)
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        _fail("manifest.json does not exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        _fail("manifest root must be an object")
    _validate_manifest(output, manifest)

    configuration = manifest.get("configuration")
    execution = manifest.get("execution")
    if not isinstance(configuration, dict) or not isinstance(execution, dict):
        _fail("manifest configuration and execution sections must be objects")
    expected_hash = config_hash(config)
    if configuration.get("config_hash") != expected_hash:
        _fail("manifest configuration hash does not match the input config")
    if execution.get("planned_runs") != plan.algorithm_run_count:
        _fail("manifest planned run count does not match the execution plan")
    if execution.get("planned_instances") != plan.instance_count:
        _fail("manifest planned instance count does not match the execution plan")
    analysis_contract = manifest.get("analysis_contract")
    expected_analysis_contract = {
        "schema_version": 1,
        "canonical_aggregate": "descriptive_statistics.csv",
        "canonical_schema_version": DESCRIPTIVE_STATISTICS_SCHEMA_VERSION,
        "repetition_unit": "instance_seed",
        "algorithm_seed_role": "nested_within_instance",
        "runtime_policy": "optimal_or_feasible_only",
        "compatibility_aggregate": "summary.csv",
        "compatibility_semantics": "legacy_raw_run_aggregate",
    }
    if analysis_contract != expected_analysis_contract:
        _fail("manifest analysis contract is missing or inconsistent")
    expected_p6_chart_contract = {
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
        },
        "sample_annotation": "required",
        "repetition_unit_annotation": "required",
        "exclusion_annotation": "required",
        "association_interpretation": "descriptive_non_causal",
        "runtime_interpretation": "machine_specific",
    }
    if manifest.get("p6_chart_contract") != expected_p6_chart_contract:
        _fail("manifest P6 chart contract is missing or inconsistent")
    confidence_interval_contract = manifest.get(
        "confidence_interval_contract"
    )
    expected_confidence_interval_contract = {
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
        "timeout_policy": "excluded_from_runtime_samples_and_counted",
        "error_policy": "excluded_from_samples_and_counted",
        "canonical_precision": (
            "descriptive_statistics_csv_round_trip_and_ci_10_decimal_places"
        ),
        "censored_runtime_analysis": "not_in_scope",
        "significance_testing": "not_in_scope",
    }
    if confidence_interval_contract != expected_confidence_interval_contract:
        _fail(
            "manifest confidence-interval contract is missing or inconsistent"
        )
    automatic_conclusion_contract = manifest.get(
        "automatic_conclusion_contract"
    )
    expected_automatic_conclusion_contract = {
        "schema_version": AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION,
        "source_artifact": "confidence_interval_statistics.csv",
        "source_artifact_schema_version": CONFIDENCE_INTERVAL_SCHEMA_VERSION,
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
        "ineligible_policy": (
            "suppress_metric_claim_and_report_gate_status"
        ),
        "factual_execution_count_policy": (
            "permitted_when_explicitly_marked_non_inferential"
        ),
        "threshold_semantics": (
            "operational_reporting_guardrail_not_power_guarantee"
        ),
        "significance_testing": "not_in_scope",
        "population_generalization": "not_in_scope",
    }
    if automatic_conclusion_contract != expected_automatic_conclusion_contract:
        _fail(
            "manifest automatic-conclusion contract is missing or inconsistent"
        )
    p6_automatic_fact_contract = manifest.get("p6_automatic_fact_contract")
    expected_p6_automatic_fact_contract = {
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
    }
    if p6_automatic_fact_contract != expected_p6_automatic_fact_contract:
        _fail("manifest P6 automatic-fact contract is missing or inconsistent")
    censored_runtime_contract = manifest.get("censored_runtime_contract")
    expected_censored_runtime_contract = {
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
        "error_policy": "excluded_from_runtime_observations_and_counted",
        "time_to_event_source": "runtime_seconds",
        "timeout_time_semantics": "observed_elapsed_time_to_right_censoring",
        "configured_time_limit_policy": (
            "not_substituted_for_observed_elapsed_time"
        ),
        "within_instance_censor_time": (
            "arithmetic_mean_across_timeout_algorithm_seeds"
        ),
        "across_instance_censor_time": (
            "equal_weight_mean_median_minimum_maximum"
        ),
        "censoring_rate": "instances_with_any_timeout/instance_count",
        "fully_right_censored_instance": "all_planned_runs_timeout",
        "zero_censoring_policy": "blank_censor_time_statistics",
        "completed_runtime_statistics_source": "descriptive_statistics.csv",
        "canonical_precision": (
            "raw_results_csv_round_trip_10_decimal_places"
        ),
        "kaplan_meier": "not_in_scope",
        "survival_curve": "not_in_scope",
        "hazard_model": "not_in_scope",
        "restricted_mean_survival_time": "not_in_scope",
        "confidence_interval": "not_in_scope",
    }
    if censored_runtime_contract != expected_censored_runtime_contract:
        _fail(
            "manifest censored-runtime contract is missing or inconsistent"
        )
    optimality_gap_contract = manifest.get("optimality_gap_contract")
    expected_optimality_gap_contract = {
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
        "within_instance_aggregation": "arithmetic_mean_of_eligible_runs",
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
    }
    if optimality_gap_contract != expected_optimality_gap_contract:
        _fail("manifest optimality-gap contract is missing or inconsistent")
    greedy_failure_contract = manifest.get("greedy_failure_contract")
    expected_greedy_failure_contract = {
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
    }
    if greedy_failure_contract != expected_greedy_failure_contract:
        _fail("manifest Greedy failure contract is missing or inconsistent")
    local_search_recovery_contract = manifest.get(
        "local_search_recovery_contract"
    )
    expected_local_search_recovery_contract = {
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
    }
    if local_search_recovery_contract != expected_local_search_recovery_contract:
        _fail("manifest Local Search recovery contract is missing or inconsistent")
    local_search_remaining_gap_contract = manifest.get(
        "local_search_remaining_gap_contract"
    )
    expected_local_search_remaining_gap_contract = {
        "schema_version": 1,
        "artifact": "local_search_remaining_gap_statistics.csv",
        "artifact_schema_version": LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION,
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
    }
    if (
        local_search_remaining_gap_contract
        != expected_local_search_remaining_gap_contract
    ):
        _fail(
            "manifest Local Search remaining-gap contract is missing or "
            "inconsistent"
        )
    heuristic_exact_runtime_ratio_contract = manifest.get(
        "heuristic_exact_runtime_ratio_contract"
    )
    expected_heuristic_exact_runtime_ratio_contract = {
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
        "formula": "mean_completed_heuristic_runtime/exact_runtime",
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
    }
    if (
        heuristic_exact_runtime_ratio_contract
        != expected_heuristic_exact_runtime_ratio_contract
    ):
        _fail(
            "manifest heuristic/exact runtime-ratio contract is missing or "
            "inconsistent"
        )
    bnb_node_reduction_contract = manifest.get(
        "bnb_node_reduction_contract"
    )
    expected_bnb_node_reduction_contract = {
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
    }
    if bnb_node_reduction_contract != expected_bnb_node_reduction_contract:
        _fail(
            "manifest Branch-and-Bound node-reduction contract is missing or "
            "inconsistent"
        )
    quality_runtime_pareto_contract = manifest.get(
        "quality_runtime_pareto_contract"
    )
    expected_quality_runtime_pareto_contract = {
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
        "across_instance_aggregation": "equal_weight_arithmetic_mean",
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
    }
    if quality_runtime_pareto_contract != expected_quality_runtime_pareto_contract:
        _fail(
            "manifest quality-runtime Pareto contract is missing or inconsistent"
        )
    gap_density_association_contract = manifest.get(
        "gap_density_association_contract"
    )
    expected_gap_density_association_contract = {
        "schema_version": 1,
        "artifact": "gap_density_association_statistics.csv",
        "artifact_schema_version": GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION,
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
    }
    if (
        gap_density_association_contract
        != expected_gap_density_association_contract
    ):
        _fail(
            "manifest gap-density association contract is missing or "
            "inconsistent"
        )
    gap_overlap_association_contract = manifest.get(
        "gap_overlap_association_contract"
    )
    expected_gap_overlap_association_contract = {
        "schema_version": 1,
        "artifact": "gap_overlap_association_statistics.csv",
        "artifact_schema_version": GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION,
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
    }
    if (
        gap_overlap_association_contract
        != expected_gap_overlap_association_contract
    ):
        _fail(
            "manifest gap-overlap association contract is missing or "
            "inconsistent"
        )
    gap_clustering_association_contract = manifest.get(
        "gap_clustering_association_contract"
    )
    expected_gap_clustering_association_contract = {
        "schema_version": 1,
        "artifact": "gap_clustering_association_statistics.csv",
        "artifact_schema_version": GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION,
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
    }
    if (
        gap_clustering_association_contract
        != expected_gap_clustering_association_contract
    ):
        _fail(
            "manifest gap-clustering association contract is missing or "
            "inconsistent"
        )
    runtime_set_count_association_contract = manifest.get(
        "runtime_set_count_association_contract"
    )
    expected_runtime_set_count_association_contract = {
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
        "automatic_conclusion_independent_count": "eligible_instance_count",
        "automatic_conclusion_minimum_sample_count": (
            AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT
        ),
        "significance_testing": "not_in_scope",
        "causal_inference": "not_in_scope",
        "survival_modeling": "not_in_scope",
        "nonlinear_or_log_modeling": "not_in_scope",
        "asymptotic_complexity_claim": "not_in_scope",
        "cross_machine_runtime_comparison": "not_in_scope",
    }
    if (
        runtime_set_count_association_contract
        != expected_runtime_set_count_association_contract
    ):
        _fail(
            "manifest runtime-set-count association contract is missing or "
            "inconsistent"
        )
    runtime_k_association_contract = manifest.get(
        "runtime_k_association_contract"
    )
    expected_runtime_k_association_contract = {
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
        "automatic_conclusion_independent_count": "eligible_instance_count",
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
    }
    if runtime_k_association_contract != expected_runtime_k_association_contract:
        _fail(
            "manifest runtime-k association contract is missing or inconsistent"
        )
    search_nodes_dominated_ratio_contract = manifest.get(
        "search_nodes_dominated_ratio_association_contract"
    )
    expected_search_nodes_dominated_ratio_contract = {
        "schema_version": 1,
        "artifact": "search_nodes_dominated_ratio_association_statistics.csv",
        "artifact_schema_version": (
            SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION
        ),
        "availability": "always",
        "empty_behavior": "header_only",
        "source_artifacts": ["instances.csv", "raw_results.csv"],
        "scope": "executed_branch_and_bound_variants_only",
        "algorithms": ["branch_and_bound", "branch_and_bound_enhanced"],
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
        "automatic_conclusion_independent_count": "eligible_instance_count",
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
    }
    if (
        search_nodes_dominated_ratio_contract
        != expected_search_nodes_dominated_ratio_contract
    ):
        _fail(
            "manifest search-nodes dominated-ratio association contract is "
            "missing or inconsistent"
        )

    instances = _load_records(output / "instances.csv", InstanceRecord)
    rows = _load_records(output / "raw_results.csv", RunRecord)
    summaries = _load_records(output / "summary.csv", SummaryRecord)
    descriptive = _load_records(
        output / "descriptive_statistics.csv", DescriptiveStatisticsRecord
    )
    confidence_intervals = _load_records(
        output / "confidence_interval_statistics.csv",
        ConfidenceIntervalRecord,
    )
    censored_runtime = _load_records(
        output / "censored_runtime_statistics.csv",
        CensoredRuntimeRecord,
        allow_empty=True,
    )
    greedy_failure = _load_records(
        output / "greedy_failure_statistics.csv",
        GreedyFailureRecord,
        allow_empty=True,
    )
    local_search_recovery = _load_records(
        output / "local_search_recovery_statistics.csv",
        LocalSearchRecoveryRecord,
        allow_empty=True,
    )
    local_search_remaining_gap = _load_records(
        output / "local_search_remaining_gap_statistics.csv",
        LocalSearchRemainingGapRecord,
        allow_empty=True,
    )
    heuristic_exact_runtime_ratio = _load_records(
        output / "heuristic_exact_runtime_ratio_statistics.csv",
        HeuristicExactRuntimeRatioRecord,
        allow_empty=True,
    )
    bnb_node_reduction = _load_records(
        output / "bnb_node_reduction_statistics.csv",
        BranchAndBoundNodeReductionRecord,
        allow_empty=True,
    )
    quality_runtime_pareto = _load_records(
        output / "quality_runtime_pareto_statistics.csv",
        QualityRuntimeParetoRecord,
        allow_empty=True,
    )
    gap_density_association = _load_records(
        output / "gap_density_association_statistics.csv",
        GapDensityAssociationRecord,
        allow_empty=True,
    )
    gap_overlap_association = _load_records(
        output / "gap_overlap_association_statistics.csv",
        GapOverlapAssociationRecord,
        allow_empty=True,
    )
    gap_clustering_association = _load_records(
        output / "gap_clustering_association_statistics.csv",
        GapClusteringAssociationRecord,
        allow_empty=True,
    )
    runtime_set_count_association = _load_records(
        output / "runtime_set_count_association_statistics.csv",
        RuntimeSetCountAssociationRecord,
        allow_empty=True,
    )
    runtime_k_association = _load_records(
        output / "runtime_k_association_statistics.csv",
        RuntimeKAssociationRecord,
        allow_empty=True,
    )
    search_nodes_dominated_ratio_association = _load_records(
        output / "search_nodes_dominated_ratio_association_statistics.csv",
        SearchNodesDominatedRatioAssociationRecord,
        allow_empty=True,
    )
    if len(rows) != plan.algorithm_run_count:
        _fail("raw result count does not match the execution plan")
    if len(instances) != plan.instance_count:
        _fail("instance record count does not match the execution plan")
    _validate_declared_algorithm_rows(config, plan, rows)
    instance_keys = {
        (record.case_id, record.repetition, record.instance_id)
        for record in instances
    }
    if len(instance_keys) != len(instances):
        _fail("instances.csv contains duplicate composite instance keys")
    if {record.config_hash for record in instances} != {expected_hash}:
        _fail("instance records contain an unexpected configuration hash")
    if len({row.run_id for row in rows}) != len(rows):
        _fail("raw results contain duplicate run_id values")
    if {row.config_hash for row in rows} != {expected_hash}:
        _fail("raw results contain an unexpected configuration hash")
    if {row.case_id for row in rows} != set(plan.case_ids):
        _fail("raw result case IDs do not match the execution plan")
    if any(
        (row.case_id, row.repetition, row.instance_id) not in instance_keys
        for row in rows
    ):
        _fail("a raw result does not link to exactly one instance record")

    bad_statuses = {
        row.status.value
        for row in rows
        if row.status in {SolutionStatus.ERROR, SolutionStatus.TIMEOUT}
    }
    if bad_statuses:
        _fail(f"starter benchmark produced non-accepted statuses: {sorted(bad_statuses)}")
    if any(row.coverage is None for row in rows):
        _fail("starter benchmark contains a result without a feasible coverage value")

    instance_ids = {row.instance_id for row in rows}
    referenced_ids = {row.instance_id for row in rows if row.optimum is not None}
    if referenced_ids != instance_ids:
        _fail("not every starter instance has an exact optimum reference")
    raw_groups = Counter(
        (row.case, row.family, row.algorithm_id, row.algorithm) for row in rows
    )
    summary_groups = {
        (summary.case, summary.family, summary.algorithm_id, summary.algorithm): summary.runs
        for summary in summaries
    }
    if summary_groups != dict(raw_groups):
        _fail("summary groups or run counts do not match the raw results")
    canonical_rows = _canonical_run_records(
        _normalize_optima(rows, instances)
    )
    _validate_lazy_greedy_rows(config, canonical_rows)
    if [row.to_csv_row() for row in rows] != [
        row.to_csv_row() for row in canonical_rows
    ]:
        _fail(
            "raw results do not match normalized exact references and "
            "canonical precision"
        )
    expected_descriptive = _descriptive_statistics(canonical_rows)
    if [record.to_csv_row() for record in descriptive] != [
        record.to_csv_row() for record in expected_descriptive
    ]:
        _fail("descriptive statistics do not match canonical raw results")
    expected_confidence_intervals = _confidence_interval_statistics(
        expected_descriptive
    )
    if [record.to_csv_row() for record in confidence_intervals] != [
        record.to_csv_row() for record in expected_confidence_intervals
    ]:
        _fail(
            "confidence intervals do not match canonical descriptive "
            "statistics recomputed from raw results"
        )
    expected_censored_runtime = _censored_runtime_statistics(canonical_rows)
    if [record.to_csv_row() for record in censored_runtime] != [
        record.to_csv_row() for record in expected_censored_runtime
    ]:
        _fail(
            "censored-runtime statistics do not match canonical raw results"
        )
    expected_local_search_recovery = _local_search_recovery_statistics(
        canonical_rows
    )
    if [record.to_csv_row() for record in local_search_recovery] != [
        record.to_csv_row() for record in expected_local_search_recovery
    ]:
        _fail(
            "Local Search recovery statistics do not match canonical raw results"
        )
    report = (output / "results_summary.md").read_text(encoding="utf-8")
    actual_headlines = _markdown_section(
        report,
        "## Headline checks",
        "## P5.1 descriptive aggregate",
    )
    expected_headlines = _headline_lines(
        config,
        expected_descriptive,
        instances,
        expected_confidence_intervals,
        expected_local_search_recovery,
        expected_censored_runtime,
    )
    if actual_headlines != expected_headlines:
        _fail(
            "automatic conclusion headlines do not match the canonical "
            "small-sample eligibility gate or P6 automatic-fact contract"
        )
    expected_gap_groups = {
        (
            row.config_hash,
            row.case_id,
            row.family,
            row.algorithm_id,
            row.algorithm,
        )
        for row in canonical_rows
    }
    actual_gap_groups = [
        (
            row.config_hash,
            row.case_id,
            row.family,
            row.algorithm_id,
            row.algorithm,
        )
        for row in descriptive
        if row.metric == "optimality_gap"
    ]
    if (
        len(actual_gap_groups) != len(expected_gap_groups)
        or set(actual_gap_groups) != expected_gap_groups
    ):
        _fail(
            "descriptive statistics must contain exactly one optimality-gap "
            "row per algorithm variant and case"
        )
    expected_greedy_failure = _greedy_failure_statistics(canonical_rows)
    if [record.to_csv_row() for record in greedy_failure] != [
        record.to_csv_row() for record in expected_greedy_failure
    ]:
        _fail("Greedy failure statistics do not match canonical raw results")
    expected_local_search_remaining_gap = (
        _local_search_remaining_gap_statistics(canonical_rows)
    )
    if [record.to_csv_row() for record in local_search_remaining_gap] != [
        record.to_csv_row()
        for record in expected_local_search_remaining_gap
    ]:
        _fail(
            "Local Search remaining-gap statistics do not match canonical raw "
            "results"
        )
    expected_heuristic_exact_runtime_ratio = (
        _heuristic_exact_runtime_ratio_statistics(canonical_rows)
    )
    if [record.to_csv_row() for record in heuristic_exact_runtime_ratio] != [
        record.to_csv_row()
        for record in expected_heuristic_exact_runtime_ratio
    ]:
        _fail(
            "heuristic/exact runtime-ratio statistics do not match canonical "
            "raw results"
        )
    expected_bnb_node_reduction = _bnb_node_reduction_statistics(
        canonical_rows
    )
    if [record.to_csv_row() for record in bnb_node_reduction] != [
        record.to_csv_row() for record in expected_bnb_node_reduction
    ]:
        _fail(
            "Branch-and-Bound node-reduction statistics do not match "
            "canonical raw results"
        )
    expected_quality_runtime_pareto = _quality_runtime_pareto_statistics(
        canonical_rows
    )
    if [record.to_csv_row() for record in quality_runtime_pareto] != [
        record.to_csv_row() for record in expected_quality_runtime_pareto
    ]:
        _fail(
            "quality-runtime Pareto statistics do not match canonical raw "
            "results"
        )
    expected_gap_density_association = (
        _gap_density_association_statistics(
            canonical_rows,
            _canonical_instance_records(instances),
        )
    )
    if [record.to_csv_row() for record in gap_density_association] != [
        record.to_csv_row()
        for record in expected_gap_density_association
    ]:
        _fail(
            "gap-density association statistics do not match canonical "
            "instance and raw evidence"
        )
    expected_gap_overlap_association = (
        _gap_overlap_association_statistics(
            canonical_rows,
            _canonical_instance_records(instances),
        )
    )
    if [record.to_csv_row() for record in gap_overlap_association] != [
        record.to_csv_row()
        for record in expected_gap_overlap_association
    ]:
        _fail(
            "gap-overlap association statistics do not match canonical "
            "instance and raw evidence"
        )
    expected_gap_clustering_association = (
        _gap_clustering_association_statistics(
            canonical_rows,
            _canonical_instance_records(instances),
        )
    )
    if [record.to_csv_row() for record in gap_clustering_association] != [
        record.to_csv_row()
        for record in expected_gap_clustering_association
    ]:
        _fail(
            "gap-clustering association statistics do not match canonical "
            "instance and raw evidence"
        )
    expected_runtime_set_count_association = (
        _runtime_set_count_association_statistics(
            canonical_rows,
            _canonical_instance_records(instances),
        )
    )
    if [record.to_csv_row() for record in runtime_set_count_association] != [
        record.to_csv_row()
        for record in expected_runtime_set_count_association
    ]:
        _fail(
            "runtime-set-count association statistics do not match canonical "
            "instance and raw evidence"
        )
    expected_runtime_k_association = _runtime_k_association_statistics(
        canonical_rows,
        _canonical_instance_records(instances),
    )
    if [record.to_csv_row() for record in runtime_k_association] != [
        record.to_csv_row() for record in expected_runtime_k_association
    ]:
        _fail(
            "runtime-k association statistics do not match canonical instance "
            "and raw evidence"
        )
    expected_search_nodes_dominated_ratio_association = (
        _search_nodes_dominated_ratio_association_statistics(
            canonical_rows,
            _canonical_instance_records(instances),
        )
    )
    if [
        record.to_csv_row()
        for record in search_nodes_dominated_ratio_association
    ] != [
        record.to_csv_row()
        for record in expected_search_nodes_dominated_ratio_association
    ]:
        _fail(
            "search-nodes dominated-ratio association statistics do not match "
            "canonical instance and raw evidence"
        )
    expected_charts = {
        "gap_by_case.svg": _render_gap_by_case_chart(descriptive),
        "gap_vs_structural_parameter.svg": (
            _render_gap_structural_association_chart(
                gap_density_association,
                gap_overlap_association,
                gap_clustering_association,
            )
        ),
        "local_search_recovery.svg": _render_local_search_recovery_chart(
            local_search_recovery
        ),
        "quality_runtime_pareto.svg": _render_quality_runtime_pareto_chart(
            quality_runtime_pareto
        ),
        "runtime_scaling.svg": _render_runtime_scaling_chart(
            runtime_set_count_association,
            runtime_k_association,
        ),
        "node_scaling.svg": _render_node_scaling_chart(
            search_nodes_dominated_ratio_association
        ),
        "timeout_by_case.svg": _render_timeout_by_case_chart(
            censored_runtime
        ),
    }
    for filename, expected_chart in expected_charts.items():
        actual_chart = (output / filename).read_text(encoding="utf-8")
        if actual_chart != expected_chart:
            _fail(f"{filename} does not match canonical typed records")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate(args.config.resolve(), args.output.resolve())
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"CI artifact validation failed: {error}", file=sys.stderr)
        return 1
    print("CI artifact validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
