"""Recompute completed benchmark results from the configuration and CSVs.

Checks run identities, record consistency, supported statistics, and selected
charts. Markdown report wording and layout are outside this check. Shared
statistics and rendering helpers are used; this does not independently
reimplement every calculation. Selection
replay is limited to supported Lazy Greedy and Greedy variants.

This optional detailed check rejects timeout/error runs and requires an optimum
reference for every instance. It is not required for exploratory analysis.
Exit status is 0 for success and 1 for reported validation failures.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import sys
from collections import Counter
from pathlib import Path
from typing import TypeVar


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.benchmark import (  # noqa: E402
    BenchmarkPlan,
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
    _reference_censoring_bias_statistics,
    _reference_coverage_statistics,
    _reference_cutoff_sensitivity_statistics,
    _reference_status_records,
    _runtime_k_association_statistics,
    _runtime_set_count_association_statistics,
    _search_nodes_dominated_ratio_association_statistics,
    _tasks_for_config,
    plan_benchmark,
)
from maxcover.config import ExperimentConfig, load_config  # noqa: E402
from maxcover.contracts import (  # noqa: E402
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
    SummaryRecord,
)
from maxcover.model import MaximumCoverageInstance, SolutionStatus  # noqa: E402
from maxcover._report_charts import (
    _render_gap_by_case_chart,
    _render_gap_structural_association_chart,
    _render_local_search_recovery_chart,
    _render_node_scaling_chart,
    _render_quality_runtime_pareto_chart,
    _render_reference_coverage_chart,
    _render_runtime_scaling_chart,
    _render_timeout_by_case_chart,
)
from maxcover.reproducibility import canonical_json, config_hash  # noqa: E402


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
    ReferenceStatusRecord,
    ReferenceCoverageRecord,
    ReferenceCensoringBiasRecord,
    ReferenceCutoffSensitivityRecord,
)


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


def _dense_greedy_reference(
    instance: MaximumCoverageInstance,
) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...]]:
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


def _lazy_greedy_reference(
    instance: MaximumCoverageInstance,
) -> tuple[int, int, tuple[tuple[int, int, int], ...]]:
    """Replay the Lazy Greedy queue and return its independent work counts."""

    queue = [(-mask.bit_count(), index) for index, mask in enumerate(instance.sets)]
    heapq.heapify(queue)
    covered = 0
    marginal_evaluations = instance.set_count
    priority_queue_pops = 0
    trajectory: list[tuple[int, int, int]] = []

    for iteration in range(instance.k):
        while True:
            _, index = heapq.heappop(queue)
            priority_queue_pops += 1
            gain = (instance.sets[index] & ~covered).bit_count()
            marginal_evaluations += 1
            refreshed = (-gain, index)
            if not queue or refreshed <= queue[0]:
                covered |= instance.sets[index]
                trajectory.append(
                    (index, gain, marginal_evaluations)
                )
                break
            heapq.heappush(queue, refreshed)

    return priority_queue_pops, marginal_evaluations, tuple(trajectory)


def _validate_run_identity(
    config: object, expected_hash: str, rows: list[object]
) -> None:
    planned_instances = _instances_for_config(config)
    tasks = _tasks_for_config(config, expected_hash, planned_instances)
    expected_by_run_id = {task.run_id: task for task in tasks}
    actual_by_run_id = {row.run_id: row for row in rows}
    missing = sorted(set(expected_by_run_id) - set(actual_by_run_id))
    unexpected = sorted(set(actual_by_run_id) - set(expected_by_run_id))
    if missing or unexpected:
        _fail(
            "raw results run_id values do not match the execution plan "
            f"(missing={len(missing)}, unexpected={len(unexpected)})"
        )

    fields = (
        "config_hash",
        "case_id",
        "case",
        "repetition",
        "seed",
        "instance_id",
        "family",
        "universe_size",
        "set_count",
        "k",
        "parameters",
        "algorithm_id",
        "algorithm_seed",
        "algorithm",
        "algorithm_options",
    )
    for run_id, task in expected_by_run_id.items():
        row = actual_by_run_id[run_id]
        expected_values = {
            "config_hash": expected_hash,
            "case_id": task.case_id,
            "case": task.case_id,
            "repetition": task.repetition,
            "seed": task.instance.seed,
            "instance_id": task.instance_id,
            "family": task.instance.family,
            "universe_size": task.instance.universe_size,
            "set_count": task.instance.set_count,
            "k": task.instance.k,
            "parameters": canonical_json(dict(task.instance.parameters)),
            "algorithm_id": task.algorithm_id,
            "algorithm_seed": task.algorithm_seed,
            "algorithm": task.algorithm,
            "algorithm_options": canonical_json(task.option_values),
        }
        for field in fields:
            if getattr(row, field) != expected_values[field]:
                _fail(
                    f"raw result {run_id} field {field!r} does not match "
                    "the execution plan"
                )


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
    if len(lazy_variants) != 1:
        _fail("Lazy Greedy validation requires exactly one Lazy Greedy variant")
    if len(greedy_variants) > 1:
        _fail("Lazy Greedy validation supports at most one Greedy variant")

    planned_instances = _instances_for_config(config)
    instances_by_unit = {
        (planned.case_id, planned.repetition, planned.instance_id): planned.instance
        for planned in planned_instances
    }
    pair_rows: dict[tuple[str, int, str], dict[str, object]] = {}
    expected_algorithms = {lazy_variants[0].algorithm_id: "lazy_greedy"}
    if greedy_variants:
        expected_algorithms[greedy_variants[0].algorithm_id] = "greedy"
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
        if lazy_row is None:
            _fail("each instance unit must contain a Lazy Greedy row")
        instance = instances_by_unit[unit]
        try:
            lazy_coverage = instance.coverage(lazy_row.selected)
        except IndexError as error:
            _fail(f"Lazy Greedy selected index is invalid: {error}")
        if lazy_row.coverage != lazy_coverage:
            _fail("Lazy Greedy coverage does not match the selected sets")
        if greedy_variants:
            if greedy_row is None:
                _fail("each instance unit must contain Greedy and Lazy Greedy rows")
            try:
                greedy_coverage = instance.coverage(greedy_row.selected)
            except IndexError as error:
                _fail(f"Greedy selected index is invalid: {error}")
            if greedy_row.coverage != greedy_coverage:
                _fail("Greedy coverage does not match the selected sets")
            if (
                greedy_row.coverage != lazy_row.coverage
                or greedy_row.selected != lazy_row.selected
            ):
                _fail("Greedy and Lazy Greedy results disagree on an instance unit")

        expected_selected, expected_trajectory = _dense_greedy_reference(instance)
        expected_pops, expected_evaluations, expected_lazy_trajectory = (
            _lazy_greedy_reference(instance)
        )
        dense_evaluations = instance.set_count * instance.k - (
            instance.k * (instance.k - 1) // 2
        )
        if lazy_row.selected != tuple(sorted(expected_selected)):
            _fail("Lazy Greedy selected set does not match the dense reference")
        if greedy_variants:
            assert greedy_row is not None
            if greedy_row.nodes_or_iterations != dense_evaluations:
                _fail("Greedy nodes_or_iterations does not match dense candidate evaluations")

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
        if priority_queue_pops != expected_pops:
            _fail(
                "Lazy Greedy marginal evaluations and priority_queue_pops "
                "do not match an independent heap replay"
            )
        if marginal_evaluations != expected_evaluations:
            _fail(
                "Lazy Greedy marginal evaluations and priority_queue_pops "
                "do not match an independent heap replay"
            )
        if lazy_row.nodes_or_iterations != expected_evaluations:
            _fail("Lazy Greedy work field does not match an independent heap replay")
        if len(trajectory) != instance.k:
            _fail("Lazy Greedy trajectory length does not match k")

        observed_trajectory: list[tuple[int, int]] = []
        observed_count_trajectory: list[tuple[int, int, int]] = []
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
            observed_count_trajectory.append(
                (selected_index, marginal_gain, cumulative)
            )
        if tuple(observed_trajectory) != expected_trajectory:
            _fail("Lazy Greedy trajectory does not match the dense reference")
        if tuple(observed_count_trajectory) != expected_lazy_trajectory:
            _fail("Lazy Greedy trajectory counts do not match an independent heap replay")
        if previous_evaluations != expected_evaluations:
            _fail("Lazy Greedy trajectory does not end at the independently replayed work count")


def _validate_record_consistency(
    config: ExperimentConfig,
    plan: BenchmarkPlan,
    expected_hash: str,
    instances: list[InstanceRecord],
    rows: list[RunRecord],
    summaries: list[SummaryRecord],
) -> None:
    if len(rows) != plan.algorithm_run_count:
        _fail("raw result count does not match the execution plan")
    if len(instances) != plan.instance_count:
        _fail("instance record count does not match the execution plan")
    _validate_run_identity(config, expected_hash, rows)
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


def _validate_canonical_records(
    config: ExperimentConfig,
    rows: list[RunRecord],
    instances: list[InstanceRecord],
) -> tuple[list[RunRecord], list[InstanceRecord]]:
    canonical_rows = _canonical_run_records(
        _normalize_optima(rows, instances)
    )
    canonical_instances = _canonical_instance_records(instances)
    _validate_lazy_greedy_rows(config, canonical_rows)
    if [row.to_csv_row() for row in rows] != [
        row.to_csv_row() for row in canonical_rows
    ]:
        _fail(
            "raw results do not match normalized exact references and "
            "canonical precision"
        )
    return canonical_rows, canonical_instances


def _validate_descriptive_statistics(
    canonical_rows: list[RunRecord],
    descriptive: list[DescriptiveStatisticsRecord],
) -> list[DescriptiveStatisticsRecord]:
    expected_descriptive = _descriptive_statistics(canonical_rows)
    if [record.to_csv_row() for record in descriptive] != [
        record.to_csv_row() for record in expected_descriptive
    ]:
        _fail("descriptive statistics do not match canonical raw results")
    return expected_descriptive


def _validate_confidence_interval_statistics(
    expected_descriptive: list[DescriptiveStatisticsRecord],
    confidence_intervals: list[ConfidenceIntervalRecord],
) -> list[ConfidenceIntervalRecord]:
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
    return expected_confidence_intervals


def _validate_censored_runtime_statistics(
    canonical_rows: list[RunRecord],
    censored_runtime: list[CensoredRuntimeRecord],
) -> list[CensoredRuntimeRecord]:
    expected_censored_runtime = _censored_runtime_statistics(canonical_rows)
    if [record.to_csv_row() for record in censored_runtime] != [
        record.to_csv_row() for record in expected_censored_runtime
    ]:
        _fail(
            "censored-runtime statistics do not match canonical raw results"
        )
    return expected_censored_runtime


def _validate_reference_statistics(
    config: ExperimentConfig,
    canonical_rows: list[RunRecord],
    canonical_instances: list[InstanceRecord],
    reference_statuses: list[ReferenceStatusRecord],
    reference_coverage: list[ReferenceCoverageRecord],
    reference_censoring_bias: list[ReferenceCensoringBiasRecord],
    reference_cutoff_sensitivity: list[ReferenceCutoffSensitivityRecord],
) -> None:
    expected_reference_statuses = _reference_status_records(
        config,
        canonical_rows,
        canonical_instances,
    )
    if [record.to_csv_row() for record in reference_statuses] != [
        record.to_csv_row() for record in expected_reference_statuses
    ]:
        _fail("reference statuses do not match canonical instances and raw results")
    expected_reference_coverage = _reference_coverage_statistics(
        expected_reference_statuses
    )
    if [record.to_csv_row() for record in reference_coverage] != [
        record.to_csv_row() for record in expected_reference_coverage
    ]:
        _fail("reference coverage does not use all generated instances")
    expected_reference_censoring_bias = _reference_censoring_bias_statistics(
        expected_reference_statuses,
        canonical_instances,
    )
    if [record.to_csv_row() for record in reference_censoring_bias] != [
        record.to_csv_row() for record in expected_reference_censoring_bias
    ]:
        _fail("reference censoring-bias comparisons do not match canonical evidence")
    expected_reference_cutoff_sensitivity = (
        _reference_cutoff_sensitivity_statistics(
            config,
            expected_reference_statuses,
        )
    )
    if [record.to_csv_row() for record in reference_cutoff_sensitivity] != [
        record.to_csv_row() for record in expected_reference_cutoff_sensitivity
    ]:
        _fail("reference cutoff sensitivity does not match exact-solver statuses")


def _validate_local_search_recovery_statistics(
    canonical_rows: list[RunRecord],
    local_search_recovery: list[LocalSearchRecoveryRecord],
) -> list[LocalSearchRecoveryRecord]:
    expected_local_search_recovery = _local_search_recovery_statistics(
        canonical_rows
    )
    if [record.to_csv_row() for record in local_search_recovery] != [
        record.to_csv_row() for record in expected_local_search_recovery
    ]:
        _fail(
            "Local Search recovery statistics do not match canonical raw results"
        )
    return expected_local_search_recovery


def _validate_gap_group_coverage(
    canonical_rows: list[RunRecord],
    descriptive: list[DescriptiveStatisticsRecord],
) -> None:
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


def _validate_greedy_failure_statistics(
    canonical_rows: list[RunRecord],
    greedy_failure: list[GreedyFailureRecord],
) -> None:
    expected_greedy_failure = _greedy_failure_statistics(canonical_rows)
    if [record.to_csv_row() for record in greedy_failure] != [
        record.to_csv_row() for record in expected_greedy_failure
    ]:
        _fail("Greedy failure statistics do not match canonical raw results")


def _validate_local_search_remaining_gap_statistics(
    canonical_rows: list[RunRecord],
    local_search_remaining_gap: list[LocalSearchRemainingGapRecord],
) -> None:
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


def _validate_heuristic_exact_runtime_ratio_statistics(
    canonical_rows: list[RunRecord],
    heuristic_exact_runtime_ratio: list[HeuristicExactRuntimeRatioRecord],
) -> None:
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


def _validate_bnb_node_reduction_statistics(
    canonical_rows: list[RunRecord],
    bnb_node_reduction: list[BranchAndBoundNodeReductionRecord],
) -> None:
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


def _validate_quality_runtime_pareto_statistics(
    canonical_rows: list[RunRecord],
    quality_runtime_pareto: list[QualityRuntimeParetoRecord],
) -> None:
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


def _validate_gap_density_association_statistics(
    canonical_rows: list[RunRecord],
    instances: list[InstanceRecord],
    gap_density_association: list[GapDensityAssociationRecord],
) -> None:
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


def _validate_gap_overlap_association_statistics(
    canonical_rows: list[RunRecord],
    instances: list[InstanceRecord],
    gap_overlap_association: list[GapOverlapAssociationRecord],
) -> None:
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


def _validate_gap_clustering_association_statistics(
    canonical_rows: list[RunRecord],
    instances: list[InstanceRecord],
    gap_clustering_association: list[GapClusteringAssociationRecord],
) -> None:
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


def _validate_runtime_set_count_association_statistics(
    canonical_rows: list[RunRecord],
    instances: list[InstanceRecord],
    runtime_set_count_association: list[RuntimeSetCountAssociationRecord],
) -> None:
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


def _validate_runtime_k_association_statistics(
    canonical_rows: list[RunRecord],
    instances: list[InstanceRecord],
    runtime_k_association: list[RuntimeKAssociationRecord],
) -> None:
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


def _validate_search_nodes_dominated_ratio_association_statistics(
    canonical_rows: list[RunRecord],
    instances: list[InstanceRecord],
    search_nodes_dominated_ratio_association: list[SearchNodesDominatedRatioAssociationRecord],
) -> None:
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


def _validate_report_charts(
    output: Path,
    descriptive: list[DescriptiveStatisticsRecord],
    gap_density_association: list[GapDensityAssociationRecord],
    gap_overlap_association: list[GapOverlapAssociationRecord],
    gap_clustering_association: list[GapClusteringAssociationRecord],
    local_search_recovery: list[LocalSearchRecoveryRecord],
    quality_runtime_pareto: list[QualityRuntimeParetoRecord],
    runtime_set_count_association: list[RuntimeSetCountAssociationRecord],
    runtime_k_association: list[RuntimeKAssociationRecord],
    search_nodes_dominated_ratio_association: list[SearchNodesDominatedRatioAssociationRecord],
    censored_runtime: list[CensoredRuntimeRecord],
    reference_statuses: list[ReferenceStatusRecord],
) -> None:
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
        "reference_coverage_by_case.svg": _render_reference_coverage_chart(
            reference_statuses
        ),
    }
    for filename, expected_chart in expected_charts.items():
        actual_chart = (output / filename).read_text(encoding="utf-8")
        if actual_chart != expected_chart:
            _fail(f"{filename} does not match canonical typed records")


def validate(config_path: Path, output: Path) -> None:
    config = load_config(config_path)
    plan = plan_benchmark(config)
    expected_hash = config_hash(config)

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
    reference_statuses = _load_records(
        output / "reference_status.csv",
        ReferenceStatusRecord,
    )
    reference_coverage = _load_records(
        output / "reference_coverage_statistics.csv",
        ReferenceCoverageRecord,
    )
    reference_censoring_bias = _load_records(
        output / "reference_censoring_bias_statistics.csv",
        ReferenceCensoringBiasRecord,
    )
    reference_cutoff_sensitivity = _load_records(
        output / "reference_cutoff_sensitivity_statistics.csv",
        ReferenceCutoffSensitivityRecord,
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
    _validate_record_consistency(
        config,
        plan,
        expected_hash,
        instances,
        rows,
        summaries,
    )
    canonical_rows, canonical_instances = _validate_canonical_records(
        config,
        rows,
        instances,
    )
    expected_descriptive = _validate_descriptive_statistics(
        canonical_rows,
        descriptive,
    )
    _validate_confidence_interval_statistics(
        expected_descriptive,
        confidence_intervals,
    )
    _validate_censored_runtime_statistics(
        canonical_rows,
        censored_runtime,
    )
    _validate_reference_statistics(
        config,
        canonical_rows,
        canonical_instances,
        reference_statuses,
        reference_coverage,
        reference_censoring_bias,
        reference_cutoff_sensitivity,
    )
    _validate_local_search_recovery_statistics(
        canonical_rows,
        local_search_recovery,
    )
    _validate_gap_group_coverage(
        canonical_rows,
        descriptive,
    )
    _validate_greedy_failure_statistics(
        canonical_rows,
        greedy_failure,
    )
    _validate_local_search_remaining_gap_statistics(
        canonical_rows,
        local_search_remaining_gap,
    )
    _validate_heuristic_exact_runtime_ratio_statistics(
        canonical_rows,
        heuristic_exact_runtime_ratio,
    )
    _validate_bnb_node_reduction_statistics(
        canonical_rows,
        bnb_node_reduction,
    )
    _validate_quality_runtime_pareto_statistics(
        canonical_rows,
        quality_runtime_pareto,
    )
    _validate_gap_density_association_statistics(
        canonical_rows,
        instances,
        gap_density_association,
    )
    _validate_gap_overlap_association_statistics(
        canonical_rows,
        instances,
        gap_overlap_association,
    )
    _validate_gap_clustering_association_statistics(
        canonical_rows,
        instances,
        gap_clustering_association,
    )
    _validate_runtime_set_count_association_statistics(
        canonical_rows,
        instances,
        runtime_set_count_association,
    )
    _validate_runtime_k_association_statistics(
        canonical_rows,
        instances,
        runtime_k_association,
    )
    _validate_search_nodes_dominated_ratio_association_statistics(
        canonical_rows,
        instances,
        search_nodes_dominated_ratio_association,
    )
    _validate_report_charts(
        output,
        descriptive,
        gap_density_association,
        gap_overlap_association,
        gap_clustering_association,
        local_search_recovery,
        quality_runtime_pareto,
        runtime_set_count_association,
        runtime_k_association,
        search_nodes_dominated_ratio_association,
        censored_runtime,
        reference_statuses,
    )


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
