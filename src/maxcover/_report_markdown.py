"""Markdown report text and headline formatting."""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import Path
from typing import cast
from .algorithms import ALGORITHMS
from .config import ExperimentConfig
from .contracts import (
    AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT,
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
from ._report_labels import (
    _REFERENCE_STATUS_LABELS,
)


def _automatic_conclusion_status(record: ConfidenceIntervalRecord) -> str:
    """Return the operational eligibility state for an automatic metric claim."""

    if record.sample_count < AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT:
        return "withheld_insufficient_samples"
    if record.interval_status != "estimable":
        return "withheld_unestimable_interval"
    return "eligible"


def _headline_lines(
    config: ExperimentConfig,
    statistics: Sequence[DescriptiveStatisticsRecord],
    instances: Sequence[InstanceRecord],
    confidence_interval_statistics: Sequence[ConfidenceIntervalRecord],
    local_search_recovery_statistics: Sequence[LocalSearchRecoveryRecord] = (),
    censored_runtime_statistics: Sequence[CensoredRuntimeRecord] = (),
) -> list[str]:
    """Build guarded automatic headlines from canonical instance-level rows."""

    interval_by_group = {
        (
            record.config_hash,
            record.case_id,
            record.family,
            record.algorithm_id,
            record.algorithm,
            record.metric,
        ): record
        for record in confidence_interval_statistics
    }
    greedy_gap_groups = [
        row
        for row in statistics
        if row.algorithm == "greedy"
        and row.metric == "optimality_gap"
        and row.mean is not None
    ]
    eligible_gaps: list[
        tuple[DescriptiveStatisticsRecord, ConfidenceIntervalRecord]
    ] = []
    for row in greedy_gap_groups:
        interval = interval_by_group.get(
            (
                row.config_hash,
                row.case_id,
                row.family,
                row.algorithm_id,
                row.algorithm,
                row.metric,
            )
        )
        if interval is not None and _automatic_conclusion_status(interval) == "eligible":
            eligible_gaps.append((row, interval))

    case_instances: dict[str, list[InstanceRecord]] = {}
    for instance_record in instances:
        case_instances.setdefault(instance_record.case_id, []).append(instance_record)

    def is_classified_adversarial(row: DescriptiveStatisticsRecord) -> bool:
        records = case_instances.get(row.case_id, ())
        return bool(records) and all(
            record.instance_origin == "constructed" and record.is_adversarial
            for record in records
        )

    def is_outside_constructed(row: DescriptiveStatisticsRecord) -> bool:
        records = case_instances.get(row.case_id, ())
        return bool(records) and all(
            record.instance_origin != "constructed" for record in records
        )

    def largest(
        records: Sequence[
            tuple[DescriptiveStatisticsRecord, ConfidenceIntervalRecord]
        ],
    ) -> tuple[DescriptiveStatisticsRecord, ConfidenceIntervalRecord] | None:
        return max(
            records,
            key=lambda item: (
                item[0].mean if item[0].mean is not None else -1.0,
                item[0].case_id,
                item[0].algorithm_id,
            ),
            default=None,
        )

    lines: list[str] = []
    if not greedy_gap_groups:
        lines.append(
            "- No completed exact reference was available, so greedy gaps are unknown."
        )
    elif not eligible_gaps:
        lines.append(
            "- Greedy-gap headline withheld: "
            f"0/{len(greedy_gap_groups)} Case/variant groups meet the automatic-"
            "conclusion gate (requires at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent instance "
            "seeds and an estimable 95% CI)."
        )
    else:
        worst = largest(eligible_gaps)
        assert worst is not None
        row, interval = worst
        assert row.mean is not None
        lines.append(
            "- Largest eligible mean greedy gap: "
            f"**{100 * row.mean:.2f}%** on `{row.case_id}` / "
            f"`{row.algorithm_id}` (n=`{interval.sample_count}`)."
        )

    worst_adversarial = largest(
        [item for item in eligible_gaps if is_classified_adversarial(item[0])]
    )
    if worst_adversarial is not None:
        row, interval = worst_adversarial
        assert row.mean is not None
        lines.append(
            "- Largest eligible mean gap on classified adversarial constructions: "
            f"**{100 * row.mean:.2f}%** on `{row.case_id}` / "
            f"`{row.algorithm_id}` (n=`{interval.sample_count}`)."
        )

    worst_non_constructed = largest(
        [item for item in eligible_gaps if is_outside_constructed(item[0])]
    )
    if worst_non_constructed is not None:
        row, interval = worst_non_constructed
        assert row.mean is not None
        lines.append(
            "- Largest eligible mean gap outside constructed instance families: "
            f"**{100 * row.mean:.2f}%** on `{row.case_id}` / "
            f"`{row.algorithm_id}` (n=`{interval.sample_count}`)."
        )

    exact_algorithm_ids = {
        algorithm.algorithm_id
        for algorithm in config.algorithms
        if ALGORITHMS[algorithm.name].exact
    }
    exact_groups = [
        row
        for row in statistics
        if row.metric == "coverage" and row.algorithm_id in exact_algorithm_ids
    ]
    exact_timeouts = sum(row.timeout_count for row in exact_groups)
    exact_runs = sum(row.run_count for row in exact_groups)

    # Preserve the existing producer/parser round trip: to_csv_row keeps
    # native numeric scalars in numeric fields, while from_csv_row advertises
    # a string-only reader interface. Cast only each record's own output.
    canonical_recovery = [
        LocalSearchRecoveryRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in local_search_recovery_statistics
    ]
    eligible_recovery = [
        record
        for record in canonical_recovery
        if record.eligible_pair_count > 0
        and record.mean_gap_recovery_rate is not None
    ]
    recovery_pair_count = sum(
        record.eligible_pair_count for record in eligible_recovery
    )
    if recovery_pair_count:
        recovery_sum = sum(
            record.mean_gap_recovery_rate * record.eligible_pair_count
            for record in eligible_recovery
            if record.mean_gap_recovery_rate is not None
        )
        full_recovery_count = sum(
            record.full_recovery_count for record in eligible_recovery
        )
        lines.append(
            "- Local Search recovered "
            f"**{100 * recovery_sum / recovery_pair_count:.2f}%** of the "
            "recoverable Greedy gap across "
            f"**{recovery_pair_count}** eligible paired instance units in "
            f"**{len(eligible_recovery)}** Case/variant groups; full optimum "
            f"recovery occurred in **{full_recovery_count}/{recovery_pair_count}** "
            "pairs (fixed-corpus descriptive fact)."
        )
    else:
        lines.append(
            "- Local Search gap recovery unavailable: **0** eligible paired "
            "instance units with a completed Greedy failure, completed Local "
            "Search result, and positive normalized exact optimum."
        )

    runtime_by_group = {
        (
            record.config_hash,
            record.case_id,
            record.family,
            record.algorithm_id,
            record.algorithm,
        ): record
        for record in statistics
        if record.metric == "runtime_seconds"
    }
    canonical_censored = [
        CensoredRuntimeRecord.from_csv_row(cast(Mapping[str, str], record.to_csv_row()))
        for record in censored_runtime_statistics
        if record.algorithm_id in exact_algorithm_ids
    ]
    exact_runtime_candidates: list[
        tuple[CensoredRuntimeRecord, DescriptiveStatisticsRecord | None]
    ] = []
    for censored_record in canonical_censored:
        runtime = runtime_by_group.get(
            (
                censored_record.config_hash,
                censored_record.case_id,
                censored_record.family,
                censored_record.algorithm_id,
                censored_record.algorithm,
            )
        )
        if censored_record.right_censored_instance_count > 0 or (
            runtime is not None and runtime.mean is not None
        ):
            exact_runtime_candidates.append((censored_record, runtime))

    if exact_runtime_candidates:
        hardest_censored, hardest_runtime = max(
            exact_runtime_candidates,
            key=lambda item: (
                item[0].censoring_rate,
                -1.0
                if item[1] is None or item[1].mean is None
                else item[1].mean,
                item[0].case_id,
                item[0].algorithm_id,
            ),
        )
        completed_mean = (
            "unavailable"
            if hardest_runtime is None or hardest_runtime.mean is None
            else f"{hardest_runtime.mean:.6f} s"
        )
        lines.append(
            "- Operationally hardest observed exact Case/variant: "
            f"`{hardest_censored.case_id}` / "
            f"`{hardest_censored.algorithm_id}` under the fixed rule "
            "“highest instance censoring rate, then highest mean completed "
            f"runtime” (censored instances="
            f"**{hardest_censored.right_censored_instance_count}/"
            f"{hardest_censored.instance_count}**, mean completed runtime="
            f"**{completed_mean}**, errors="
            f"**{hardest_censored.error_run_count}**; machine-specific "
            "fixed-corpus diagnostic, not an intrinsic difficulty ranking)."
        )
    else:
        lines.append(
            "- Operationally hardest exact Case unavailable: no exact variant "
            "has a completed runtime or a right-censored instance."
        )

    lines.extend(
        [
            f"- Exact-method timeouts: **{exact_timeouts}/{exact_runs}** "
            "(factual execution count; not an inferential claim).",
            "- Eligibility is an operational reporting guardrail, not evidence of "
            "significance or population generalizability.",
            "- These are experiment outputs, not general theoretical conclusions.",
        ]
    )
    return lines


def _write_markdown(
    path: Path,
    config_path: Path,
    config: ExperimentConfig,
    rows: Sequence[RunRecord],
    statistics: Sequence[DescriptiveStatisticsRecord],
    instances: Sequence[InstanceRecord],
    greedy_failure_statistics: Sequence[GreedyFailureRecord],
    local_search_recovery_statistics: Sequence[LocalSearchRecoveryRecord],
    local_search_remaining_gap_statistics: Sequence[
        LocalSearchRemainingGapRecord
    ],
    heuristic_exact_runtime_ratio_statistics: Sequence[
        HeuristicExactRuntimeRatioRecord
    ],
    bnb_node_reduction_statistics: Sequence[
        BranchAndBoundNodeReductionRecord
    ],
    quality_runtime_pareto_statistics: Sequence[
        QualityRuntimeParetoRecord
    ],
    gap_density_association_statistics: Sequence[
        GapDensityAssociationRecord
    ],
    gap_overlap_association_statistics: Sequence[
        GapOverlapAssociationRecord
    ],
    gap_clustering_association_statistics: Sequence[
        GapClusteringAssociationRecord
    ],
    runtime_set_count_association_statistics: Sequence[
        RuntimeSetCountAssociationRecord
    ],
    runtime_k_association_statistics: Sequence[RuntimeKAssociationRecord],
    search_nodes_dominated_ratio_association_statistics: Sequence[
        SearchNodesDominatedRatioAssociationRecord
    ],
    confidence_interval_statistics: Sequence[
        ConfidenceIntervalRecord
    ],
    censored_runtime_statistics: Sequence[CensoredRuntimeRecord],
    reference_statuses: Sequence[ReferenceStatusRecord],
    reference_coverage_statistics: Sequence[ReferenceCoverageRecord],
    reference_censoring_bias_statistics: Sequence[
        ReferenceCensoringBiasRecord
    ],
    reference_cutoff_sensitivity_statistics: Sequence[
        ReferenceCutoffSensitivityRecord
    ],
) -> None:
    lines = [
        f"# Results: {config.name}",
        "",
        "## Reproducibility",
        "",
        f'- Configuration: `{config_path.resolve().as_posix()}`',
        f"- Base seed: `{config.base_seed}`",
        f"- Repetitions per case: `{config.repetitions}`",
        f'- Raw algorithm runs: `{len(rows)}`',
        "- Runtime environment: Python standard library only",
        "",
        "## Headline checks",
        "",
    ]
    lines.extend(
        _headline_lines(
            config,
            statistics,
            instances,
            confidence_interval_statistics,
            local_search_recovery_statistics,
            censored_runtime_statistics,
        )
    )
    lines.extend(
        [
            "",
            "## P5.1 descriptive aggregate",
            "",
            "The independent unit is one generated instance seed. Algorithm seeds are "
            "averaged within that unit. Runtime statistics exclude timeout and error "
            "runs; their rates remain explicit.",
            "",
            "| Case | Family | Variant | Instances | Runs | Mean/median coverage | Mean/P95 gap | Mean completed runtime (s) | Timeout rate | Exact refs |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    grouped_statistics: dict[
        tuple[str, str, str, str], dict[str, DescriptiveStatisticsRecord]
    ] = {}
    for row in statistics:
        grouped_statistics.setdefault(
            (row.case_id, row.family, row.algorithm_id, row.algorithm), {}
        )[row.metric] = row
    for aggregate_key, metric_rows in sorted(grouped_statistics.items()):
        case_id, family, algorithm_id, _algorithm = aggregate_key
        coverage = metric_rows["coverage"]
        gap = metric_rows["optimality_gap"]
        runtime = metric_rows["runtime_seconds"]
        coverage_text = (
            "n/a"
            if coverage.mean is None or coverage.median is None
            else f"{coverage.mean:.4f} / {coverage.median:.4f}"
        )
        gap_text = (
            "n/a"
            if gap.mean is None or gap.p95 is None
            else f"{100 * gap.mean:.2f}% / {100 * gap.p95:.2f}%"
        )
        runtime_text = "n/a" if runtime.mean is None else f"{runtime.mean:.6f}"
        lines.append(
            f"| {case_id} | {family} | {algorithm_id} | "
            f"{coverage.instance_count} | {coverage.run_count} | "
            f"{coverage_text} | {gap_text} | {runtime_text} | "
            f"{100 * coverage.timeout_rate:.2f}% | "
            f"{coverage.valid_exact_reference_count}/{coverage.instance_count} |"
        )
    lines.extend(
        [
            "",
            "## Exact-reference coverage and censoring diagnostics",
            "",
            "Reference coverage is the number of generated instances with a "
            "validated optimum proof divided by all generated instances in the "
            "same family and parameter slice. A known-optimum certificate is an "
            "independent proof source. Missing references remain classified as "
            "feasible-only, timeout, error, or not-run instead of disappearing "
            "from gap analysis.",
            "",
            "| Family | Parameters | Generated | Proved references | Coverage | "
            "Certificate / solver proofs | Cross-validated | Status counts |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    coverage_groups: dict[
        tuple[str, str, str], dict[str, ReferenceCoverageRecord]
    ] = {}
    for coverage_record in reference_coverage_statistics:
        coverage_groups.setdefault(
            (coverage_record.config_hash, coverage_record.family, coverage_record.parameters), {}
        )[coverage_record.status] = coverage_record
    small_cross_validation_counts: dict[tuple[str, str], int] = {}
    for status_record in reference_statuses:
        cross_validation_key = (status_record.family, status_record.parameters)
        small_cross_validation_counts[cross_validation_key] = (
            small_cross_validation_counts.get(cross_validation_key, 0)
            + int(status_record.small_instance_cross_validated)
        )
    if not coverage_groups:
        lines.append(
            "| n/a | n/a | 0 | 0 | n/a | 0 / 0 | 0 / 0 | no generated instances |"
        )
    for (_config_hash, family, parameters), status_rows in sorted(
        coverage_groups.items()
    ):
        first = next(iter(status_rows.values()))
        status_text = "; ".join(
            f"{_REFERENCE_STATUS_LABELS[status]}="
            f"{status_rows[status].status_instance_count}"
            for status in _REFERENCE_STATUS_LABELS
        )
        safe_parameters = parameters.replace("|", "\\|")
        small_count = small_cross_validation_counts.get((family, parameters), 0)
        lines.append(
            f"| {family} | `{safe_parameters}` | "
            f"{first.generated_instance_count} | "
            f"{first.provably_optimal_instance_count} | "
            f"{100 * first.reference_coverage:.2f}% | "
            f"{first.certificate_reference_count} / "
            f"{first.solver_reference_count} | "
            f"{first.cross_validated_instance_count} / {small_count} small | "
            f"{status_text} |"
        )
    lines.extend(
        [
            "",
            "Retained instances have a validated optimum; excluded instances do "
            "not. The difference is excluded mean minus retained mean within the "
            "same family and parameter slice. It is descriptive and is left "
            "blank unless both groups have observations.",
            "",
            "| Family | Parameters | Metric | Retained n / mean | Excluded n / "
            "mean | Excluded - retained | Status |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    estimable_bias = [
        record
        for record in reference_censoring_bias_statistics
        if record.comparison_status == "estimable"
    ]
    if not estimable_bias:
        lines.append(
            "| n/a | n/a | no slice contains both retained and excluded "
            "observations | 0 / n/a | 0 / n/a | n/a | missing_group |"
        )
    for bias_record in estimable_bias:
        assert bias_record.retained_mean is not None
        assert bias_record.excluded_mean is not None
        assert bias_record.excluded_minus_retained is not None
        safe_parameters = bias_record.parameters.replace("|", "\\|")
        lines.append(
            f"| {bias_record.family} | `{safe_parameters}` | {bias_record.metric} | "
            f"{bias_record.retained_observation_count} / {bias_record.retained_mean:.10f} | "
            f"{bias_record.excluded_observation_count} / {bias_record.excluded_mean:.10f} | "
            f"{bias_record.excluded_minus_retained:.10f} | "
            f"{bias_record.comparison_status} |"
        )
    lines.extend(
        [
            "",
            "Each exact variant retains its configured time and set-count "
            "cutoffs. Comparing rows with different cutoffs is the sensitivity "
            "analysis; solver coverage excludes certificates, while effective "
            "coverage includes either that solver's proof or a validated "
            "certificate.",
            "",
            "| Family | Parameters | Exact variant | Time cutoff (s) | Set cutoff | "
            "Statuses O/F/T/E/NR | Solver coverage | Effective coverage |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    if not reference_cutoff_sensitivity_statistics:
        lines.append(
            "| n/a | n/a | no configured exact variant | n/a | n/a | "
            "0/0/0/0/0 | n/a | n/a |"
        )
    for cutoff_record in reference_cutoff_sensitivity_statistics:
        time_cutoff = (
            "none"
            if cutoff_record.time_limit_seconds is None
            else f"{cutoff_record.time_limit_seconds:.10f}"
        )
        set_cutoff = "none" if cutoff_record.max_set_count is None else str(cutoff_record.max_set_count)
        safe_parameters = cutoff_record.parameters.replace("|", "\\|")
        lines.append(
            f"| {cutoff_record.family} | `{safe_parameters}` | {cutoff_record.algorithm_id} | "
            f"{time_cutoff} | {set_cutoff} | "
            f"{cutoff_record.optimal_count}/{cutoff_record.feasible_count}/"
            f"{cutoff_record.timeout_count}/{cutoff_record.error_count}/{cutoff_record.not_run_count} | "
            f"{100 * cutoff_record.solver_reference_coverage:.2f}% | "
            f"{100 * cutoff_record.effective_reference_coverage:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## P5.3 95% confidence intervals for instance means",
            "",
            "Each row reuses the canonical P5.1 instance-level samples and "
            "reports a two-sided Student-t interval for the mean. Algorithm "
            "seeds remain nested within each instance. At least two samples "
            "are required; singleton and empty groups retain explicit statuses "
            "with blank interval bounds. Runtime intervals use completed "
            "runtime samples only and do not estimate censored runtimes.",
            "",
            "| Case | Family | Variant | Metric | n | Mean | 95% CI | df | "
            "Status | T/E |",
            "|---|---|---|---|---:|---:|---:|---:|---|---:|",
        ]
    )
    if not confidence_interval_statistics:
        lines.append(
            "| n/a | n/a | no metric groups | n/a | 0 | n/a | n/a | 0 | "
            "no_samples | 0/0 |"
        )
    for interval_record in confidence_interval_statistics:
        mean = "n/a" if interval_record.mean is None else f"{interval_record.mean:.10f}"
        interval = (
            "n/a"
            if interval_record.lower_bound is None or interval_record.upper_bound is None
            else f"[{interval_record.lower_bound:.10f}, {interval_record.upper_bound:.10f}]"
        )
        lines.append(
            f"| {interval_record.case_id} | {interval_record.family} | "
            f"{interval_record.algorithm_id} | {interval_record.metric} | "
            f"{interval_record.sample_count} | {mean} | {interval} | "
            f"{interval_record.degrees_of_freedom} | {interval_record.interval_status} | "
            f"{interval_record.timeout_count}/{interval_record.error_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.3 automatic-conclusion eligibility",
            "",
            "Automatic metric headlines require an estimable confidence interval "
            "and at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent instance "
            "seeds. Rows below the threshold remain visible as descriptive "
            "evidence but cannot feed an automatic claim. This fixed threshold "
            "is a reporting guardrail, not a statistical-power guarantee.",
            "",
            "| Case | Family | Variant | Metric | Independent n | Minimum n | "
            "CI status | Automatic conclusion |",
            "|---|---|---|---|---:|---:|---|---|",
        ]
    )
    if not confidence_interval_statistics:
        lines.append(
            "| n/a | n/a | no metric groups | n/a | 0 | "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} | no_samples | "
            "withheld_insufficient_samples |"
        )
    for interval_record in confidence_interval_statistics:
        lines.append(
            f"| {interval_record.case_id} | {interval_record.family} | {interval_record.algorithm_id} | "
            f"{interval_record.metric} | {interval_record.sample_count} | "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} | "
            f"{interval_record.interval_status} | "
            f"{_automatic_conclusion_status(interval_record)} |"
        )
    lines.extend(
        [
            "",
            "## P5.3 censored-runtime diagnostics",
            "",
            "Timeout elapsed times are reported separately as right-censored "
            "runtime observations and are never mixed with completed-runtime "
            "statistics. Algorithm seeds are averaged within each instance; "
            "the table then summarizes those instance-equal censor times. "
            "This diagnostic does not fit a survival curve or infer latent "
            "completion times.",
            "",
            "| Case | Family | Variant | Instances | Runs | Completed runs | "
            "Right-censored runs | Censored instances | Rate | Mean / median "
            "censor time (s) | Range (s) | Fully censored | Error affected | "
            "Status |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---:|---|",
        ]
    )
    if not censored_runtime_statistics:
        lines.append(
            "| n/a | n/a | no executed variants | 0 | 0 | 0 | 0 | 0 | "
            "n/a | n/a | n/a | 0 | 0 | no_runtime_observations |"
        )
    for censored_record in censored_runtime_statistics:
        if censored_record.mean_censor_time_seconds is None:
            center = "n/a"
            time_range = "n/a"
        else:
            assert censored_record.median_censor_time_seconds is not None
            assert censored_record.minimum_censor_time_seconds is not None
            assert censored_record.maximum_censor_time_seconds is not None
            center = (
                f"{censored_record.mean_censor_time_seconds:.10f} / "
                f"{censored_record.median_censor_time_seconds:.10f}"
            )
            time_range = (
                f"{censored_record.minimum_censor_time_seconds:.10f}–"
                f"{censored_record.maximum_censor_time_seconds:.10f}"
            )
        lines.append(
            f"| {censored_record.case_id} | {censored_record.family} | "
            f"{censored_record.algorithm_id} | {censored_record.instance_count} | "
            f"{censored_record.run_count} | {censored_record.completed_run_count} | "
            f"{censored_record.right_censored_run_count} | "
            f"{censored_record.right_censored_instance_count} | "
            f"{100 * censored_record.censoring_rate:.2f}% | {center} | "
            f"{time_range} | "
            f"{censored_record.fully_right_censored_instance_count} | "
            f"{censored_record.error_affected_instance_count} | "
            f"{censored_record.censoring_status} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 classical Greedy failure rate",
            "",
            "The rate is conditional on instance units where classical Greedy "
            "completed and a normalized exact reference is available. Timeout, "
            "error, and missing-reference units are excluded from the denominator "
            "and reported separately.",
            "",
            "| Case | Family | Variant | Instances | Completed | Eligible | Failures / denominator | Optimal ties | Failure rate | Timeouts | Errors | No exact ref |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not greedy_failure_statistics:
        lines.append(
            "| n/a | n/a | no classical Greedy configured | 0 | 0 | 0 | "
            "0/0 | 0 | n/a | 0 | 0 | 0 |"
        )
    for failure_record in greedy_failure_statistics:
        failure_rate = (
            "n/a"
            if failure_record.failure_rate is None
            else f"{100 * failure_record.failure_rate:.2f}%"
        )
        lines.append(
            f"| {failure_record.case_id} | {failure_record.family} | {failure_record.algorithm_id} | "
            f"{failure_record.instance_count} | {failure_record.completed_count} | "
            f"{failure_record.eligible_pair_count} | "
            f"{failure_record.failure_count}/{failure_record.eligible_pair_count} | "
            f"{failure_record.optimal_tie_count} | {failure_rate} | "
            f"{failure_record.timeout_count} | {failure_record.error_count} | "
            f"{failure_record.no_exact_reference_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 mean/max relative optimality gap",
            "",
            "All executed algorithm variants are reported separately. Each "
            "instance seed has equal weight: eligible algorithm-seed gaps are "
            "averaged within the instance before mean and maximum are computed "
            "across instances. Timeout incumbents may contribute a quality gap; "
            "errors, missing exact references, and zero optima do not.",
            "",
            "| Case | Family | Variant | Gap samples / instances | Exact refs | Mean gap | Max gap | Timeouts | Errors |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    gap_statistics = sorted(
        (row for row in statistics if row.metric == "optimality_gap"),
        key=lambda row: (
            row.config_hash,
            row.case_id,
            row.family,
            row.algorithm_id,
            row.algorithm,
        ),
    )
    if not gap_statistics:
        lines.append("| n/a | n/a | no algorithm variants | 0/0 | 0/0 | n/a | n/a | 0 | 0 |")
    for gap_record in gap_statistics:
        mean_gap = (
            "n/a" if gap_record.mean is None else f"{100 * gap_record.mean:.2f}%"
        )
        max_gap = (
            "n/a" if gap_record.maximum is None else f"{100 * gap_record.maximum:.2f}%"
        )
        lines.append(
            f"| {gap_record.case_id} | {gap_record.family} | {gap_record.algorithm_id} | "
            f"{gap_record.sample_count}/{gap_record.instance_count} | "
            f"{gap_record.valid_exact_reference_count}/{gap_record.instance_count} | "
            f"{mean_gap} | {max_gap} | {gap_record.timeout_count} | "
            f"{gap_record.error_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 Local Search recovery rate",
            "",
            "The recoverable gap is defined only where classical Greedy "
            "completed below a normalized exact optimum. Paired completed Local "
            "Search runs contribute `(LS - Greedy) / (OPT - Greedy)`; each "
            "instance seed has equal weight. Timeout, error, missing-reference, "
            "and already-optimal Greedy units are excluded from the mean.",
            "",
            "| Case | Family | Greedy variant | Local Search variant | "
            "Greedy failures | Eligible pairs | Mean gap recovery | "
            "Full recoveries | Greedy T/E | Local Search T/E |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not local_search_recovery_statistics:
        lines.append(
            "| n/a | n/a | n/a | no paired classical Greedy and Local Search "
            "variants configured | 0 | 0 | n/a | 0/0 | 0/0 | 0/0 |"
        )
    for recovery_record in local_search_recovery_statistics:
        recovery_rate = (
            "n/a"
            if recovery_record.mean_gap_recovery_rate is None
            else f"{100 * recovery_record.mean_gap_recovery_rate:.2f}%"
        )
        lines.append(
            f"| {recovery_record.case_id} | {recovery_record.family} | "
            f"{recovery_record.greedy_algorithm_id} | "
            f"{recovery_record.local_search_algorithm_id} | "
            f"{recovery_record.greedy_failure_count} | {recovery_record.eligible_pair_count} | "
            f"{recovery_rate} | "
            f"{recovery_record.full_recovery_count}/{recovery_record.eligible_pair_count} | "
            f"{recovery_record.greedy_timeout_count}/{recovery_record.greedy_error_count} | "
            f"{recovery_record.local_search_timeout_count}/"
            f"{recovery_record.local_search_error_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 remaining gap after Local Search recovery",
            "",
            "This metric uses the same eligible deterministic Greedy/Local "
            "Search pairs as the recovery rate. For each completed pair where "
            "Greedy is below a normalized exact optimum, the remaining relative "
            "gap is `(OPT - LS) / OPT`; instance seeds have equal weight.",
            "",
            "| Case | Family | Greedy variant | Local Search variant | "
            "Eligible pairs | Mean remaining gap | Max remaining gap | "
            "Zero remaining gap |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    if not local_search_remaining_gap_statistics:
        lines.append(
            "| n/a | n/a | n/a | no paired classical Greedy and Local Search "
            "variants configured | 0 | n/a | n/a | 0/0 |"
        )
    for remaining_gap_record in local_search_remaining_gap_statistics:
        mean_gap = (
            "n/a"
            if remaining_gap_record.mean_remaining_relative_gap is None
            else f"{100 * remaining_gap_record.mean_remaining_relative_gap:.2f}%"
        )
        maximum_gap = (
            "n/a"
            if remaining_gap_record.maximum_remaining_relative_gap is None
            else f"{100 * remaining_gap_record.maximum_remaining_relative_gap:.2f}%"
        )
        lines.append(
            f"| {remaining_gap_record.case_id} | {remaining_gap_record.family} | "
            f"{remaining_gap_record.greedy_algorithm_id} | "
            f"{remaining_gap_record.local_search_algorithm_id} | "
            f"{remaining_gap_record.eligible_pair_count} | {mean_gap} | {maximum_gap} | "
            f"{remaining_gap_record.zero_remaining_gap_count}/"
            f"{remaining_gap_record.eligible_pair_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 heuristic/exact runtime ratio",
            "",
            "Each heuristic variant is paired with each exact variant in the "
            "same case. Completed heuristic algorithm-seed runtimes are averaged "
            "within an instance and divided by its positive completed exact "
            "runtime; instance ratios then receive equal weight. Timeout, error, "
            "and zero exact-runtime denominators are excluded and counted.",
            "",
            "| Case | Family | Heuristic variant | Exact variant | Eligible | "
            "Mean | Median | Min | Max | Heuristic T/E | Exact T/E | "
            "Zero exact runtime |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not heuristic_exact_runtime_ratio_statistics:
        lines.append(
            "| n/a | n/a | no heuristic/exact variant pair configured | n/a | "
            "0 | n/a | n/a | n/a | n/a | 0/0 | 0/0 | 0 |"
        )
    for runtime_ratio_record in heuristic_exact_runtime_ratio_statistics:
        values: tuple[float | None, ...] = (
            runtime_ratio_record.mean_runtime_ratio,
            runtime_ratio_record.median_runtime_ratio,
            runtime_ratio_record.minimum_runtime_ratio,
            runtime_ratio_record.maximum_runtime_ratio,
        )
        formatted = [
            "n/a" if value is None else f"{value:.4f}x"
            for value in values
        ]
        lines.append(
            f"| {runtime_ratio_record.case_id} | {runtime_ratio_record.family} | "
            f"{runtime_ratio_record.heuristic_algorithm_id} | {runtime_ratio_record.exact_algorithm_id} | "
            f"{runtime_ratio_record.eligible_pair_count}/{runtime_ratio_record.instance_count} | "
            f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
            f"{formatted[3]} | {runtime_ratio_record.heuristic_timeout_count}/"
            f"{runtime_ratio_record.heuristic_error_count} | {runtime_ratio_record.exact_timeout_count}/"
            f"{runtime_ratio_record.exact_error_count} | "
            f"{runtime_ratio_record.zero_exact_runtime_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 Branch-and-Bound node reduction",
            "",
            "Each baseline Branch-and-Bound variant is paired with each "
            "enhanced Branch-and-Bound variant in the same case. Only pairs "
            "where both searches prove the same optimum and the baseline "
            "visited at least one node contribute "
            "`1 - enhanced_nodes / baseline_nodes`; instance seeds receive "
            "equal weight. Timeout, error, and zero baseline-node units are "
            "excluded and counted. Negative values are retained when the "
            "enhanced search visits more nodes.",
            "",
            "| Case | Family | Baseline variant | Enhanced variant | Eligible | "
            "Mean | Median | Min | Max | Aggregate | Nodes baseline/enhanced | "
            "Baseline T/E | Enhanced T/E | Zero baseline nodes |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if not bnb_node_reduction_statistics:
        lines.append(
            "| n/a | n/a | no baseline/enhanced BnB variant pair configured | "
            "n/a | 0 | n/a | n/a | n/a | n/a | n/a | 0/0 | 0/0 | 0/0 | 0 |"
        )
    for node_reduction_record in bnb_node_reduction_statistics:
        values = (
            node_reduction_record.mean_node_reduction,
            node_reduction_record.median_node_reduction,
            node_reduction_record.minimum_node_reduction,
            node_reduction_record.maximum_node_reduction,
            node_reduction_record.aggregate_node_reduction,
        )
        formatted = [
            "n/a" if value is None else f"{100 * value:.2f}%"
            for value in values
        ]
        lines.append(
            f"| {node_reduction_record.case_id} | {node_reduction_record.family} | "
            f"{node_reduction_record.baseline_algorithm_id} | "
            f"{node_reduction_record.enhanced_algorithm_id} | "
            f"{node_reduction_record.eligible_pair_count}/{node_reduction_record.instance_count} | "
            f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
            f"{formatted[3]} | {formatted[4]} | "
            f"{node_reduction_record.total_baseline_nodes}/"
            f"{node_reduction_record.total_enhanced_nodes} | "
            f"{node_reduction_record.baseline_timeout_count}/"
            f"{node_reduction_record.baseline_error_count} | "
            f"{node_reduction_record.enhanced_timeout_count}/"
            f"{node_reduction_record.enhanced_error_count} | "
            f"{node_reduction_record.zero_baseline_nodes_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.2 quality-runtime Pareto frontier",
            "",
            "All executed algorithm variants in a case are compared on a "
            "common fully observed instance set: the normalized exact optimum "
            "must be positive and every planned run of every variant must "
            "complete. Algorithm seeds are averaged within an instance, then "
            "instances receive equal weight. Both mean relative gap and mean "
            "runtime are minimized. A point is dominated only when another "
            "variant is no worse on both axes and strictly better on at least "
            "one; identical points share the frontier.",
            "",
            "| Case | Family | Variant | Eligible | Mean gap | Mean runtime "
            "(s) | Pareto status | Dominated by | T/E | References valid/zero/"
            "missing |",
            "|---|---|---|---:|---:|---:|---|---|---:|---:|",
        ]
    )
    if not quality_runtime_pareto_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0 | n/a | n/a | "
            "not_evaluable | n/a | 0/0 | 0/0/0 |"
        )
    for pareto_record in quality_runtime_pareto_statistics:
        pareto_gap_text = (
            "n/a"
            if pareto_record.mean_relative_gap is None
            else f"{100 * pareto_record.mean_relative_gap:.4f}%"
        )
        pareto_runtime_text = (
            "n/a"
            if pareto_record.mean_runtime_seconds is None
            else f"{pareto_record.mean_runtime_seconds:.6f}"
        )
        dominators = (
            ", ".join(pareto_record.dominated_by_algorithm_ids)
            if pareto_record.dominated_by_algorithm_ids
            else "n/a"
        )
        lines.append(
            f"| {pareto_record.case_id} | {pareto_record.family} | "
            f"{pareto_record.algorithm_id} | "
            f"{pareto_record.eligible_instance_count}/{pareto_record.instance_count} | "
            f"{pareto_gap_text} | {pareto_runtime_text} | {pareto_record.pareto_status} | {dominators} | "
            f"{pareto_record.timeout_count}/{pareto_record.error_count} | "
            f"{pareto_record.valid_exact_reference_count}/"
            f"{pareto_record.zero_optimum_count}/"
            f"{pareto_record.no_exact_reference_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 gap vs actual-density association",
            "",
            "Rows pool executed Cases only within the same instance family and "
            "algorithm variant. The independent unit is one instance seed; "
            "algorithm-seed gaps are averaged inside that instance. The "
            "predictor is measured `instances.csv.actual_density`, not the "
            "generator target. Pearson correlation and an OLS line are "
            "descriptive only: no p-value, significance, causality, or "
            "cross-family generalization is claimed. This section emits no "
            "automatic numerical headline; fewer than "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent samples "
            "cannot pass the automatic-conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct density | "
            "Mean density | Mean gap | Density SD | Gap SD | Pearson r | "
            "OLS slope | OLS intercept | Status | T/E | References "
            "valid/zero/missing/unusable |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not gap_density_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0 | "
            "0/0/0/0 |"
        )
    for density_record in gap_density_association_statistics:
        values = (
            density_record.mean_actual_density,
            density_record.mean_relative_gap,
            density_record.density_sample_standard_deviation,
            density_record.gap_sample_standard_deviation,
            density_record.pearson_correlation,
            density_record.ols_slope,
            density_record.ols_intercept,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {density_record.family} | {', '.join(density_record.case_ids)} | "
            f"{density_record.algorithm_id} | "
            f"{density_record.eligible_instance_count}/{density_record.instance_count} | "
            f"{density_record.distinct_density_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{density_record.association_status} | "
            f"{density_record.timeout_count}/{density_record.error_count} | "
            f"{density_record.valid_exact_reference_count}/"
            f"{density_record.zero_optimum_count}/"
            f"{density_record.no_exact_reference_count}/"
            f"{density_record.unusable_result_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 gap vs measured pairwise-overlap association",
            "",
            "Rows pool executed Cases only within the same instance family and "
            "algorithm variant. The independent unit is one instance seed; "
            "algorithm-seed gaps are averaged inside that instance. The "
            "predictor is measured "
            "`instances.csv.pairwise_overlap_mean_jaccard`; null overlap "
            "means no valid Jaccard pair and is excluded and counted, never "
            "filled with zero. Pearson correlation and an OLS line are "
            "descriptive only: no p-value, significance, causality, "
            "clustering equivalence, or cross-family generalization is "
            "claimed. This section emits no automatic numerical headline; "
            "fewer than "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} independent samples "
            "cannot pass the automatic-conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct overlap | "
            "Mean overlap | Mean gap | Overlap SD | Gap SD | Pearson r | "
            "OLS slope | OLS intercept | Status | T/E | References "
            "valid/zero/missing/unusable/missing predictor |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not gap_overlap_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0 | "
            "0/0/0/0/0 |"
        )
    for overlap_record in gap_overlap_association_statistics:
        values = (
            overlap_record.mean_pairwise_overlap_jaccard,
            overlap_record.mean_relative_gap,
            overlap_record.overlap_sample_standard_deviation,
            overlap_record.gap_sample_standard_deviation,
            overlap_record.pearson_correlation,
            overlap_record.ols_slope,
            overlap_record.ols_intercept,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {overlap_record.family} | {', '.join(overlap_record.case_ids)} | "
            f"{overlap_record.algorithm_id} | "
            f"{overlap_record.eligible_instance_count}/{overlap_record.instance_count} | "
            f"{overlap_record.distinct_overlap_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{overlap_record.association_status} | "
            f"{overlap_record.timeout_count}/{overlap_record.error_count} | "
            f"{overlap_record.valid_exact_reference_count}/"
            f"{overlap_record.zero_optimum_count}/"
            f"{overlap_record.no_exact_reference_count}/"
            f"{overlap_record.unusable_result_count}/"
            f"{overlap_record.missing_overlap_predictor_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 gap vs mixed-cluster bridge intensity",
            "",
            "Only the P4 `mixed_cluster_bridges` paired scan is eligible. "
            "The predictor is measured `realized_bridge_fraction` from "
            "typed instance parameters; higher values mean more "
            "cross-cluster mixing, not stronger clustering. "
            "`coupling_pair_id`/`coupling_seed` define independent blocks. "
            "A block contributes only when every Case level has a usable "
            "gap, after which each level mean uses the same blocks and the "
            "association is fitted across level-mean coordinates. No "
            "p-value, significance, causal effect, mixed-effects inference, "
            "or population generalization is claimed. This section emits "
            "no automatic numerical headline; the conclusion guardrail "
            "uses eligible blocks, not levels or instance points, and "
            "requires at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} blocks.",
            "",
            "| Variant | Cases/levels | Blocks eligible/total | Instances "
            "eligible/total | Mean bridge fraction | Mean level gap | "
            "Bridge SD | Level-gap SD | Pearson r | OLS slope | "
            "OLS intercept | Status | T/E | References "
            "valid/zero/missing/unusable/usable |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
            "---:|---:|",
        ]
    )
    if not gap_clustering_association_statistics:
        lines.append(
            "| no mixed-cluster variant executed | 0/0 | 0/0 | 0/0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_complete_blocks | "
            "0/0 | 0/0/0/0/0 |"
        )
    for clustering_record in gap_clustering_association_statistics:
        values = (
            clustering_record.mean_realized_bridge_fraction,
            clustering_record.mean_level_relative_gap,
            clustering_record.bridge_fraction_sample_standard_deviation,
            clustering_record.gap_level_mean_sample_standard_deviation,
            clustering_record.pearson_correlation,
            clustering_record.ols_slope,
            clustering_record.ols_intercept,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {clustering_record.algorithm_id} | "
            f"{clustering_record.case_count}/{clustering_record.distinct_clustering_level_count} | "
            f"{clustering_record.eligible_block_count}/"
            f"{clustering_record.independent_block_count} | "
            f"{clustering_record.eligible_instance_count}/{clustering_record.instance_count} | "
            f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
            f"{formatted[3]} | {formatted[4]} | {formatted[5]} | "
            f"{formatted[6]} | {clustering_record.association_status} | "
            f"{clustering_record.timeout_count}/{clustering_record.error_count} | "
            f"{clustering_record.valid_exact_reference_count}/"
            f"{clustering_record.zero_optimum_count}/"
            f"{clustering_record.no_exact_reference_count}/"
            f"{clustering_record.unusable_result_count}/"
            f"{clustering_record.usable_gap_instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 completed runtime vs candidate-set count",
            "",
            "Rows pool executed Cases only within the same instance family "
            "and algorithm variant. The predictor is typed "
            "`instances.csv.set_count`. An instance contributes only when "
            "all planned algorithm-seed runs complete as optimal or "
            "feasible; their runtimes are averaged inside that instance, "
            "then instance seeds are equally weighted. Timeout/error makes "
            "the whole instance ineligible, and timeout elapsed time remains "
            "separate in `censored_runtime_statistics.csv`. Pearson "
            "correlation and OLS seconds-per-set are descriptive only: no "
            "significance, causality, asymptotic complexity, nonlinear "
            "scaling, cross-family, or cross-machine claim is made. This "
            "section emits no automatic numerical headline; at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} eligible instance "
            "seeds would be required by the conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct set count | "
            "Mean set count | Mean runtime (s) | Set-count SD | Runtime SD "
            "(s) | Pearson r | OLS slope (s/set) | OLS intercept (s) | "
            "Status | Completed/T/E | Incomplete instances |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not runtime_set_count_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0/0 | 0 |"
        )
    for runtime_set_count_record in runtime_set_count_association_statistics:
        values = (
            runtime_set_count_record.mean_set_count,
            runtime_set_count_record.mean_runtime_seconds,
            runtime_set_count_record.set_count_sample_standard_deviation,
            runtime_set_count_record.runtime_sample_standard_deviation_seconds,
            runtime_set_count_record.pearson_correlation,
            runtime_set_count_record.ols_slope_seconds_per_set,
            runtime_set_count_record.ols_intercept_seconds,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {runtime_set_count_record.family} | {', '.join(runtime_set_count_record.case_ids)} | "
            f"{runtime_set_count_record.algorithm_id} | "
            f"{runtime_set_count_record.eligible_instance_count}/{runtime_set_count_record.instance_count} | "
            f"{runtime_set_count_record.distinct_set_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{runtime_set_count_record.association_status} | "
            f"{runtime_set_count_record.completed_run_count}/{runtime_set_count_record.timeout_count}/"
            f"{runtime_set_count_record.error_count} | "
            f"{runtime_set_count_record.incomplete_runtime_instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 completed runtime vs selection budget k",
            "",
            "Rows pool executed Cases only within the same instance family "
            "and algorithm variant. The predictor is typed `instances.csv.k`, "
            "not selected-set count or an algorithm option. An instance "
            "contributes only when all planned algorithm-seed runs complete "
            "as optimal or feasible; their runtimes are averaged inside that "
            "instance, then instance seeds are equally weighted. Timeout/error "
            "makes the whole instance ineligible, and timeout elapsed time "
            "remains separate in `censored_runtime_statistics.csv`. Pearson "
            "correlation and OLS seconds-per-budget-unit are descriptive only: "
            "no significance, causality, asymptotic complexity, nonlinear "
            "scaling, quality stability, cross-family, or cross-machine claim "
            "is made. This section emits no automatic numerical headline; at "
            "least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} eligible instance "
            "seeds would be required by the conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct k | Mean k | "
            "Mean runtime (s) | k SD | Runtime SD (s) | Pearson r | OLS slope "
            "(s/budget unit) | OLS intercept (s) | Status | Completed/T/E | "
            "Incomplete instances |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|---:|",
        ]
    )
    if not runtime_k_association_statistics:
        lines.append(
            "| n/a | n/a | no algorithm variant executed | 0/0 | 0 | n/a | "
            "n/a | n/a | n/a | n/a | n/a | n/a | no_samples | 0/0/0 | 0 |"
        )
    for runtime_k_record in runtime_k_association_statistics:
        values = (
            runtime_k_record.mean_k,
            runtime_k_record.mean_runtime_seconds,
            runtime_k_record.k_sample_standard_deviation,
            runtime_k_record.runtime_sample_standard_deviation_seconds,
            runtime_k_record.pearson_correlation,
            runtime_k_record.ols_slope_seconds_per_budget_unit,
            runtime_k_record.ols_intercept_seconds,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {runtime_k_record.family} | {', '.join(runtime_k_record.case_ids)} | "
            f"{runtime_k_record.algorithm_id} | "
            f"{runtime_k_record.eligible_instance_count}/{runtime_k_record.instance_count} | "
            f"{runtime_k_record.distinct_k_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{runtime_k_record.association_status} | "
            f"{runtime_k_record.completed_run_count}/{runtime_k_record.timeout_count}/"
            f"{runtime_k_record.error_count} | "
            f"{runtime_k_record.incomplete_runtime_instance_count} |"
        )
    lines.extend(
        [
            "",
            "## P5.4 completed BnB search nodes vs dominated-set ratio",
            "",
            "Rows include only Branch-and-Bound variants and pool executed "
            "Cases only within the same instance family and algorithm variant. "
            "The predictor is typed `instances.csv.dominated_set_ratio` "
            "(`dominated_set_count / set_count`), not the unique-set ratio or "
            "preprocessed set count. Only optimal runs contribute complete "
            "`nodes_or_iterations`; timeout partial searches and errors are "
            "excluded and counted. Instance seeds are equally weighted. "
            "Pearson correlation and OLS nodes-per-ratio-unit are descriptive "
            "only: no significance, causality, asymptotic complexity, "
            "cross-family, cross-machine, or algorithm-ranking claim is made. "
            "This section emits no automatic numerical headline; at least "
            f"{AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT} eligible instance "
            "seeds would be required by the conclusion guardrail.",
            "",
            "| Family | Cases | Variant | Eligible | Distinct ratios | Mean "
            "dominated ratio | Mean nodes | Ratio SD | Node SD | Pearson r | "
            "OLS slope (nodes/ratio unit) | OLS intercept (nodes) | Status | "
            "Optimal/T/E |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---|---:|",
        ]
    )
    if not search_nodes_dominated_ratio_association_statistics:
        lines.append(
            "| n/a | n/a | no BnB variant executed | 0/0 | 0 | n/a | n/a | "
            "n/a | n/a | n/a | n/a | n/a | no_samples | 0/0/0 |"
        )
    for node_association_record in search_nodes_dominated_ratio_association_statistics:
        values = (
            node_association_record.mean_dominated_set_ratio,
            node_association_record.mean_search_nodes,
            node_association_record.dominated_ratio_sample_standard_deviation,
            node_association_record.search_nodes_sample_standard_deviation,
            node_association_record.pearson_correlation,
            node_association_record.ols_slope_nodes_per_ratio_unit,
            node_association_record.ols_intercept_nodes,
        )
        formatted = [
            "n/a" if value is None else f"{value:.10f}"
            for value in values
        ]
        lines.append(
            f"| {node_association_record.family} | {', '.join(node_association_record.case_ids)} | "
            f"{node_association_record.algorithm_id} | "
            f"{node_association_record.eligible_instance_count}/{node_association_record.instance_count} | "
            f"{node_association_record.distinct_dominated_ratio_count} | {formatted[0]} | "
            f"{formatted[1]} | {formatted[2]} | {formatted[3]} | "
            f"{formatted[4]} | {formatted[5]} | {formatted[6]} | "
            f"{node_association_record.association_status} | "
            f"{node_association_record.optimal_run_count}/{node_association_record.timeout_count}/"
            f"{node_association_record.error_count} |"
        )
    lines.extend(
        [
            "",
            "## Next analysis questions",
            "",
            "1. Does greedy degradation persist across seeds and larger instances?",
            "2. Which controlled parameter best predicts the observed gap?",
            "3. When does local search recover the greedy loss, and at what runtime cost?",
            "4. Which structures cause branch-and-bound runtime transitions?",
            "5. Are conclusions stable when the set budget `k` changes?",
            "",
            "See `raw_results.csv` before making any external claim with a numerical result.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
