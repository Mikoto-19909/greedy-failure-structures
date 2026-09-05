"""Configuration-driven, resumable, and deterministic benchmark runner."""

from __future__ import annotations

import json
import multiprocessing
import tempfile
import time
from collections.abc import Iterable, Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .algorithms import ALGORITHMS
from .benchmark_artifacts import (
    REPORT_FILENAMES,
    RUNNER_OWNED_FILENAMES,
    SEARCH_COMPARISON_FIELDS,
    STOCHASTIC_SUMMARY_FIELDS,
    _canonical_instance_records,
    _canonical_run_records,
    _clean_runner_owned_artifacts,
    _csv_text,
    _read_existing,
    _runner_owned_paths,
    _validate_existing_instances,
    _write_csv,
    _write_search_comparison,
    _write_stochastic_summary,
)
from .benchmark_manifest import PROJECT_ROOT, _git_state, _write_manifest
from .benchmark_statistics import (
    _validate_certificate_bound,
    _normalize_optima,
    _reference_status_records,
    _reference_coverage_statistics,
    _REFERENCE_BIAS_METRICS,
    _reference_censoring_bias_statistics,
    _reference_cutoff_sensitivity_statistics,
    _summarize,
    _MetricDescription,
    _linear_quantile,
    _describe_values,
    _DescriptiveCommon,
    _descriptive_statistics,
    _beta_continued_fraction,
    _regularized_incomplete_beta,
    _student_t_cdf,
    _student_t_critical_95,
    _ten_decimal,
    _ConfidenceIntervalCommon,
    _confidence_interval_statistics,
    _censored_runtime_statistics,
    _greedy_failure_statistics,
    _LocalSearchPairAnalysis,
    _local_search_pair_analyses,
    _local_search_recovery_statistics,
    _local_search_remaining_gap_statistics,
    _runtime_ratio_variant_units,
    _heuristic_exact_runtime_ratio_statistics,
    _bnb_variant_units,
    _bnb_node_reduction_statistics,
    _pareto_variant_units,
    _quality_runtime_pareto_statistics,
    _deterministic_variant_units,
    _increment_heuristic_status,
)
from .benchmark_associations import (
    _gap_density_association_statistics,
    _gap_overlap_association_statistics,
    _gap_clustering_association_statistics,
    _runtime_set_count_association_statistics,
    _RuntimeKInstanceProjection,
    _runtime_k_association_statistics,
    _search_nodes_dominated_ratio_association_statistics,
)
from .benchmark_planning import (
    _PlannedInstance,
    _RunTask,
    _STRUCTURAL_COUPLING_INTENSITY,
    _case_seed,
    _coupling_pair_id,
    _coupling_seed,
    _fixed_size_control_pairs,
    _instance_record,
    _instances_for_config,
    _resolved_case_parameters,
    _structural_coupling_pair_id,
    _tasks_for_config,
)
from .certificates import known_optimum_certificate
from .config import ExperimentConfig, load_config
from .contracts import (
    AlgorithmRunOptions,
    BenchmarkResult,
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
from .model import MaximumCoverageInstance, Solution, SolutionStatus
from .reporting import write_report_artifacts
from .reproducibility import (
    atomic_write_text,
    canonical_json,
    config_hash,
    instance_id,
    instance_payload,
    load_instance,
    run_id,
)


@dataclass(frozen=True, slots=True)
class BenchmarkPlan:
    """A side-effect-free size estimate for one expanded experiment."""

    name: str
    case_ids: tuple[str, ...]
    repetitions: int
    instance_count: int
    algorithm_run_count: int
    runs_by_algorithm: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class _CompletedRun:
    task: _RunTask
    solution: Solution
    error_message: str = ""


def plan_benchmark(config: ExperimentConfig) -> BenchmarkPlan:
    """Count expanded instances and eligible algorithm runs without running them."""

    _fixed_size_control_pairs(config)
    counts = {
        algorithm.algorithm_id: 0
        for algorithm in config.algorithms
        if algorithm.enabled
    }
    for case_index, case in enumerate(config.cases):
        seed = _case_seed(config, case, case_index, 0)
        instance = case.generate(seed)
        for algorithm in config.algorithms:
            if not algorithm.enabled:
                continue
            specification = ALGORITHMS[algorithm.name]
            if specification.is_eligible(instance, algorithm.options):
                seed_count = (
                    len(algorithm.algorithm_seeds)
                    if specification.uses_random_seed
                    else 1
                )
                counts[algorithm.algorithm_id] += config.repetitions * seed_count
    return BenchmarkPlan(
        name=config.name,
        case_ids=tuple(case.case_id for case in config.cases),
        repetitions=config.repetitions,
        instance_count=len(config.cases) * config.repetitions,
        algorithm_run_count=sum(counts.values()),
        runs_by_algorithm=tuple(counts.items()),
    )


def _run_algorithms(
    instance: MaximumCoverageInstance, config: ExperimentConfig
) -> list[Solution]:
    solutions = []
    for algorithm in config.algorithms:
        if not algorithm.enabled:
            continue
        specification = ALGORITHMS[algorithm.name]
        if specification.is_eligible(instance, algorithm.options):
            solutions.append(specification.run(instance, algorithm.options))
    return solutions


def _rows_for_instance(
    *,
    case_name: str,
    repetition: int,
    instance: MaximumCoverageInstance,
    solutions: list[Solution],
    options_by_algorithm: Mapping[str, Mapping[str, object]] | None = None,
    config_identifier: str = "",
) -> list[RunRecord]:
    """Build records for one instance (kept as a focused public test seam)."""

    optimal_values = [
        solution.optimal_value
        for solution in solutions
        if solution.optimal_value is not None
    ]
    certificate = known_optimum_certificate(instance)
    identifier = instance_id(instance)
    if certificate is not None and any(
        value != certificate.value for value in optimal_values
    ):
        raise ValueError("an optimal algorithm result conflicts with the instance certificate")
    if len(set(optimal_values)) > 1:
        raise ValueError("optimal algorithms disagree on the instance optimum")
    for solution in solutions:
        _validate_certificate_bound(
            None if certificate is None else certificate.value,
            solution.best_bound,
            identifier,
        )
    optimum = (
        certificate.value
        if certificate is not None
        else optimal_values[0]
        if optimal_values
        else None
    )
    rows: list[RunRecord] = []
    for solution in solutions:
        values = dict((options_by_algorithm or {}).get(solution.algorithm, {}))
        specification = ALGORITHMS.get(solution.algorithm)
        version = 1 if specification is None else specification.version
        gap = None
        if optimum is not None and optimum > 0 and solution.feasible_value is not None:
            gap = (optimum - solution.feasible_value) / optimum
        rows.append(
            RunRecord(
                config_hash=config_identifier,
                case_id=case_name,
                instance_id=identifier,
                run_id=run_id(
                    identifier,
                    solution.algorithm,
                    values,
                    algorithm_version=version,
                ),
                case=case_name,
                repetition=repetition,
                seed=instance.seed,
                family=instance.family,
                universe_size=instance.universe_size,
                set_count=instance.set_count,
                k=instance.k,
                parameters=canonical_json(dict(instance.parameters)),
                algorithm_id=solution.algorithm,
                algorithm=solution.algorithm,
                algorithm_options=canonical_json(values),
                algorithm_metadata=canonical_json(dict(solution.metadata)),
                status=solution.status,
                coverage=solution.feasible_value,
                best_bound=solution.best_bound,
                optimum=optimum,
                optimality_gap=gap,
                runtime_seconds=solution.runtime_seconds,
                nodes_or_iterations=solution.nodes_or_iterations,
                selected=solution.selected,
            )
        )
    return rows


def _execute_task(task: _RunTask) -> _CompletedRun:
    specification = ALGORITHMS[task.algorithm]
    started = time.perf_counter()
    try:
        solution = specification.run(task.instance, task.options)
    # Preserve a replayable failure instead of losing completed experiment progress.
    except Exception as error:
        solution = Solution(
            algorithm=task.algorithm,
            selected=(),
            feasible_value=None,
            runtime_seconds=time.perf_counter() - started,
            status=SolutionStatus.ERROR,
        )
        return _CompletedRun(task, solution, f"{type(error).__name__}: {error}")
    return _CompletedRun(task, solution)


def _record_for_completed(completed: _CompletedRun) -> RunRecord:
    task = completed.task
    solution = completed.solution
    return RunRecord(
        config_hash=task.config_hash,
        case_id=task.case_id,
        instance_id=task.instance_id,
        run_id=task.run_id,
        case=task.case_id,
        repetition=task.repetition,
        seed=task.instance.seed,
        family=task.instance.family,
        universe_size=task.instance.universe_size,
        set_count=task.instance.set_count,
        k=task.instance.k,
        parameters=canonical_json(dict(task.instance.parameters)),
        algorithm_id=task.algorithm_id,
        algorithm_seed=task.algorithm_seed,
        algorithm=task.algorithm,
        algorithm_options=canonical_json(task.option_values),
        algorithm_metadata=canonical_json(dict(solution.metadata)),
        status=solution.status,
        coverage=solution.feasible_value,
        best_bound=solution.best_bound,
        optimum=None,
        optimality_gap=None,
        runtime_seconds=solution.runtime_seconds,
        nodes_or_iterations=solution.nodes_or_iterations,
        selected=solution.selected,
        error_message=completed.error_message,
    )


def _write_replay_artifact(output_dir: Path, completed: _CompletedRun) -> None:
    if completed.solution.status not in {SolutionStatus.TIMEOUT, SolutionStatus.ERROR}:
        return
    task = completed.task
    expected = {
        "status": completed.solution.status.value,
        "coverage": completed.solution.coverage,
        "selected": list(completed.solution.selected),
        "error_message": completed.error_message,
    }
    artifact = {
        "artifact_type": "maxcover-replay",
        "run_id": task.run_id,
        "instance_id": task.instance_id,
        "instance": instance_payload(task.instance, encoding="elements"),
        "replay": {
            "algorithm_id": task.algorithm_id,
            "algorithm": task.algorithm,
            "algorithm_version": ALGORITHMS[task.algorithm].version,
            "algorithm_seed": task.algorithm_seed,
            "options": task.option_values,
            "expected": expected,
        },
    }
    filename = f"{task.run_id}.json"
    atomic_write_text(
        output_dir / "failures" / filename,
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def replay_instance_file(
    path: Path, algorithm: str | None = None
) -> tuple[Solution, bool | None]:
    """Replay a serialized instance and compare deterministic result fields."""

    instance, document = load_instance(path)
    metadata = document.get("replay", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("replay metadata must be an object")
    selected_algorithm = algorithm or metadata.get("algorithm")
    if not isinstance(selected_algorithm, str) or selected_algorithm not in ALGORITHMS:
        raise ValueError("replay requires a registered algorithm")
    raw_options = metadata.get("options", {})
    if not isinstance(raw_options, Mapping):
        raise ValueError("replay options must be an object")
    options = AlgorithmRunOptions(
        time_limit_seconds=raw_options.get("time_limit_seconds"),
        max_set_count=raw_options.get("max_set_count"),
        values={
            key: value
            for key, value in raw_options.items()
            if key not in {"time_limit_seconds", "max_set_count", "algorithm_seed"}
        },
        algorithm_seed=raw_options.get("algorithm_seed"),
    )
    solution = ALGORITHMS[selected_algorithm].run(instance, options)
    expected = metadata.get("expected")
    matches: bool | None = None
    if isinstance(expected, Mapping):
        matches = (
            solution.coverage == expected.get("coverage")
            and list(solution.selected) == expected.get("selected")
        )
    return solution, matches


def run_benchmark(
    config_path: Path,
    output_dir: Path,
    *,
    workers: int = 1,
    force: bool = False,
    expected_config_hash: str | None = None,
    checkpoint_interval: int = 1,
) -> BenchmarkResult:
    """Run or resume an experiment with atomic periodic checkpoints."""

    if isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0:
        raise ValueError("workers must be a positive integer")
    if (
        isinstance(checkpoint_interval, bool)
        or not isinstance(checkpoint_interval, int)
        or checkpoint_interval <= 0
    ):
        raise ValueError("checkpoint_interval must be a positive integer")
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    git_state = _git_state()
    config = load_config(config_path)
    identifier = config_hash(config)
    if expected_config_hash is not None and identifier != expected_config_hash:
        raise ValueError(
            "configuration changed after preflight; validate it again"
        )
    planned_instances = _instances_for_config(config)
    instance_records = [
        _instance_record(planned, identifier) for planned in planned_instances
    ]
    tasks = _tasks_for_config(config, identifier, planned_instances)
    expected_ids = [task.run_id for task in tasks]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("the expanded benchmark plan contains duplicate run_id values")
    output_dir.mkdir(parents=True, exist_ok=True)
    if force:
        _clean_runner_owned_artifacts(output_dir)
    existing = (
        {}
        if force
        else _read_existing(output_dir / "raw_results.csv", identifier)
    )
    if not force:
        _validate_existing_instances(output_dir / "instances.csv", instance_records)
    expected_set = set(expected_ids)
    unexpected = sorted(set(existing) - expected_set)
    if unexpected:
        raise ValueError(
            "existing raw_results.csv contains runs outside the current plan; "
            "use --force"
        )
    _write_csv(
        output_dir / "instances.csv", instance_records, InstanceRecord.CSV_FIELDS
    )
    pending = [task for task in tasks if task.run_id not in existing]
    records = dict(existing)

    if workers == 1:
        completed_runs: Iterable[_CompletedRun] = map(_execute_task, pending)
        executor = None
    else:
        context = multiprocessing.get_context("spawn")
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=context)
        completed_runs = executor.map(_execute_task, pending)
    try:
        for completed_index, completed in enumerate(completed_runs, start=1):
            record = _record_for_completed(completed)
            records[record.run_id] = record
            _write_replay_artifact(output_dir, completed)
            if completed_index % checkpoint_interval == 0:
                checkpoint_rows = [
                    records[run_identifier]
                    for run_identifier in expected_ids
                    if run_identifier in records
                ]
                checkpoint = _normalize_optima(checkpoint_rows, instance_records)
                _write_csv(
                    output_dir / "raw_results.csv", checkpoint, RunRecord.CSV_FIELDS
                )
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    all_rows = _normalize_optima(
        [records[run_identifier] for run_identifier in expected_ids],
        instance_records,
    )
    _write_csv(output_dir / "raw_results.csv", all_rows, RunRecord.CSV_FIELDS)
    canonical_rows = _canonical_run_records(all_rows)
    summary = _summarize(canonical_rows)
    _write_csv(output_dir / "summary.csv", summary, SummaryRecord.CSV_FIELDS)
    descriptive_statistics = _descriptive_statistics(canonical_rows)
    _write_csv(
        output_dir / "descriptive_statistics.csv",
        descriptive_statistics,
        DescriptiveStatisticsRecord.CSV_FIELDS,
    )
    confidence_interval_statistics = _confidence_interval_statistics(
        descriptive_statistics
    )
    _write_csv(
        output_dir / "confidence_interval_statistics.csv",
        confidence_interval_statistics,
        ConfidenceIntervalRecord.CSV_FIELDS,
    )
    censored_runtime_statistics = _censored_runtime_statistics(
        canonical_rows
    )
    _write_csv(
        output_dir / "censored_runtime_statistics.csv",
        censored_runtime_statistics,
        CensoredRuntimeRecord.CSV_FIELDS,
    )
    greedy_failure_statistics = _greedy_failure_statistics(canonical_rows)
    _write_csv(
        output_dir / "greedy_failure_statistics.csv",
        greedy_failure_statistics,
        GreedyFailureRecord.CSV_FIELDS,
    )
    local_search_recovery_statistics = _local_search_recovery_statistics(
        canonical_rows
    )
    _write_csv(
        output_dir / "local_search_recovery_statistics.csv",
        local_search_recovery_statistics,
        LocalSearchRecoveryRecord.CSV_FIELDS,
    )
    local_search_remaining_gap_statistics = (
        _local_search_remaining_gap_statistics(canonical_rows)
    )
    _write_csv(
        output_dir / "local_search_remaining_gap_statistics.csv",
        local_search_remaining_gap_statistics,
        LocalSearchRemainingGapRecord.CSV_FIELDS,
    )
    heuristic_exact_runtime_ratio_statistics = (
        _heuristic_exact_runtime_ratio_statistics(canonical_rows)
    )
    _write_csv(
        output_dir / "heuristic_exact_runtime_ratio_statistics.csv",
        heuristic_exact_runtime_ratio_statistics,
        HeuristicExactRuntimeRatioRecord.CSV_FIELDS,
    )
    bnb_node_reduction_statistics = _bnb_node_reduction_statistics(
        canonical_rows
    )
    _write_csv(
        output_dir / "bnb_node_reduction_statistics.csv",
        bnb_node_reduction_statistics,
        BranchAndBoundNodeReductionRecord.CSV_FIELDS,
    )
    quality_runtime_pareto_statistics = _quality_runtime_pareto_statistics(
        canonical_rows
    )
    _write_csv(
        output_dir / "quality_runtime_pareto_statistics.csv",
        quality_runtime_pareto_statistics,
        QualityRuntimeParetoRecord.CSV_FIELDS,
    )
    canonical_instances = _canonical_instance_records(instance_records)
    reference_statuses = _reference_status_records(
        config,
        canonical_rows,
        canonical_instances,
    )
    _write_csv(
        output_dir / "reference_status.csv",
        reference_statuses,
        ReferenceStatusRecord.CSV_FIELDS,
    )
    reference_coverage_statistics = _reference_coverage_statistics(
        reference_statuses
    )
    _write_csv(
        output_dir / "reference_coverage_statistics.csv",
        reference_coverage_statistics,
        ReferenceCoverageRecord.CSV_FIELDS,
    )
    reference_censoring_bias_statistics = (
        _reference_censoring_bias_statistics(
            reference_statuses,
            canonical_instances,
        )
    )
    _write_csv(
        output_dir / "reference_censoring_bias_statistics.csv",
        reference_censoring_bias_statistics,
        ReferenceCensoringBiasRecord.CSV_FIELDS,
    )
    reference_cutoff_sensitivity_statistics = (
        _reference_cutoff_sensitivity_statistics(config, reference_statuses)
    )
    _write_csv(
        output_dir / "reference_cutoff_sensitivity_statistics.csv",
        reference_cutoff_sensitivity_statistics,
        ReferenceCutoffSensitivityRecord.CSV_FIELDS,
    )
    gap_density_association_statistics = (
        _gap_density_association_statistics(
            canonical_rows,
            canonical_instances,
        )
    )
    _write_csv(
        output_dir / "gap_density_association_statistics.csv",
        gap_density_association_statistics,
        GapDensityAssociationRecord.CSV_FIELDS,
    )
    gap_overlap_association_statistics = (
        _gap_overlap_association_statistics(
            canonical_rows,
            canonical_instances,
        )
    )
    _write_csv(
        output_dir / "gap_overlap_association_statistics.csv",
        gap_overlap_association_statistics,
        GapOverlapAssociationRecord.CSV_FIELDS,
    )
    gap_clustering_association_statistics = (
        _gap_clustering_association_statistics(
            canonical_rows,
            canonical_instances,
        )
    )
    _write_csv(
        output_dir / "gap_clustering_association_statistics.csv",
        gap_clustering_association_statistics,
        GapClusteringAssociationRecord.CSV_FIELDS,
    )
    runtime_set_count_association_statistics = (
        _runtime_set_count_association_statistics(
            canonical_rows,
            canonical_instances,
        )
    )
    _write_csv(
        output_dir / "runtime_set_count_association_statistics.csv",
        runtime_set_count_association_statistics,
        RuntimeSetCountAssociationRecord.CSV_FIELDS,
    )
    runtime_k_association_statistics = _runtime_k_association_statistics(
        canonical_rows,
        canonical_instances,
    )
    _write_csv(
        output_dir / "runtime_k_association_statistics.csv",
        runtime_k_association_statistics,
        RuntimeKAssociationRecord.CSV_FIELDS,
    )
    search_nodes_dominated_ratio_association_statistics = (
        _search_nodes_dominated_ratio_association_statistics(
            canonical_rows,
            canonical_instances,
        )
    )
    _write_csv(
        output_dir
        / "search_nodes_dominated_ratio_association_statistics.csv",
        search_nodes_dominated_ratio_association_statistics,
        SearchNodesDominatedRatioAssociationRecord.CSV_FIELDS,
    )
    _write_search_comparison(output_dir, canonical_rows)
    _write_stochastic_summary(output_dir, canonical_rows)
    with tempfile.TemporaryDirectory(prefix=".report-", dir=output_dir) as temporary:
        temporary_dir = Path(temporary)
        write_report_artifacts(
            temporary_dir,
            config_path,
            config,
            canonical_rows,
            descriptive_statistics,
            instance_records,
            greedy_failure_statistics=greedy_failure_statistics,
            local_search_recovery_statistics=local_search_recovery_statistics,
            local_search_remaining_gap_statistics=(
                local_search_remaining_gap_statistics
            ),
            heuristic_exact_runtime_ratio_statistics=(
                heuristic_exact_runtime_ratio_statistics
            ),
            bnb_node_reduction_statistics=bnb_node_reduction_statistics,
            quality_runtime_pareto_statistics=(
                quality_runtime_pareto_statistics
            ),
            gap_density_association_statistics=(
                gap_density_association_statistics
            ),
            gap_overlap_association_statistics=(
                gap_overlap_association_statistics
            ),
            gap_clustering_association_statistics=(
                gap_clustering_association_statistics
            ),
            runtime_set_count_association_statistics=(
                runtime_set_count_association_statistics
            ),
            runtime_k_association_statistics=runtime_k_association_statistics,
            search_nodes_dominated_ratio_association_statistics=(
                search_nodes_dominated_ratio_association_statistics
            ),
            confidence_interval_statistics=(
                confidence_interval_statistics
            ),
            censored_runtime_statistics=censored_runtime_statistics,
            reference_statuses=reference_statuses,
            reference_coverage_statistics=reference_coverage_statistics,
            reference_censoring_bias_statistics=(
                reference_censoring_bias_statistics
            ),
            reference_cutoff_sensitivity_statistics=(
                reference_cutoff_sensitivity_statistics
            ),
        )
        for filename in REPORT_FILENAMES:
            atomic_write_text(
                output_dir / filename,
                (temporary_dir / filename).read_text(encoding="utf-8"),
            )
    duration_seconds = time.perf_counter() - started
    _write_manifest(
        output_dir=output_dir,
        config_path=config_path,
        config=config,
        identifier=identifier,
        tasks=tasks,
        instances=instance_records,
        started_at=started_at,
        duration_seconds=duration_seconds,
        workers=workers,
        resumed_runs=len(existing),
        git_state=git_state,
    )
    return BenchmarkResult(
        config=config,
        rows=tuple(canonical_rows),
        summary=tuple(summary),
        output_dir=output_dir,
        instances=tuple(instance_records),
        descriptive_statistics=tuple(descriptive_statistics),
        confidence_interval_statistics=tuple(
            confidence_interval_statistics
        ),
        censored_runtime_statistics=tuple(censored_runtime_statistics),
        reference_statuses=tuple(reference_statuses),
        reference_coverage_statistics=tuple(reference_coverage_statistics),
        reference_censoring_bias_statistics=tuple(
            reference_censoring_bias_statistics
        ),
        reference_cutoff_sensitivity_statistics=tuple(
            reference_cutoff_sensitivity_statistics
        ),
        greedy_failure_statistics=tuple(greedy_failure_statistics),
        local_search_recovery_statistics=tuple(
            local_search_recovery_statistics
        ),
        local_search_remaining_gap_statistics=tuple(
            local_search_remaining_gap_statistics
        ),
        heuristic_exact_runtime_ratio_statistics=tuple(
            heuristic_exact_runtime_ratio_statistics
        ),
        bnb_node_reduction_statistics=tuple(
            bnb_node_reduction_statistics
        ),
        quality_runtime_pareto_statistics=tuple(
            quality_runtime_pareto_statistics
        ),
        gap_density_association_statistics=tuple(
            gap_density_association_statistics
        ),
        gap_overlap_association_statistics=tuple(
            gap_overlap_association_statistics
        ),
        gap_clustering_association_statistics=tuple(
            gap_clustering_association_statistics
        ),
        runtime_set_count_association_statistics=tuple(
            runtime_set_count_association_statistics
        ),
        runtime_k_association_statistics=tuple(runtime_k_association_statistics),
        search_nodes_dominated_ratio_association_statistics=tuple(
            search_nodes_dominated_ratio_association_statistics
        ),
    )


def summarize_benchmark(config_path: Path, output_dir: Path) -> BenchmarkResult:
    """Rebuild derived artifacts from a complete existing benchmark checkpoint."""

    config = load_config(config_path)
    identifier = config_hash(config)
    planned_instances = _instances_for_config(config)
    instance_records = [
        _instance_record(planned, identifier) for planned in planned_instances
    ]
    tasks = _tasks_for_config(config, identifier, planned_instances)
    expected_ids = [task.run_id for task in tasks]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("the expanded benchmark plan contains duplicate run_id values")

    raw_results_path = output_dir / "raw_results.csv"
    instances_path = output_dir / "instances.csv"
    if not raw_results_path.is_file():
        raise ValueError(f"missing canonical benchmark artifact: {raw_results_path}")
    if not instances_path.is_file():
        raise ValueError(f"missing canonical benchmark artifact: {instances_path}")

    existing = _read_existing(raw_results_path, identifier)
    _validate_existing_instances(instances_path, instance_records)
    expected_set = set(expected_ids)
    unexpected = sorted(set(existing) - expected_set)
    if unexpected:
        raise ValueError(
            "existing raw_results.csv contains runs outside the current plan"
        )
    missing = [
        run_identifier
        for run_identifier in expected_ids
        if run_identifier not in existing
    ]
    if missing:
        raise ValueError(
            "existing raw_results.csv is incomplete for summarize: "
            f"missing {len(missing)} planned run(s)"
        )

    # With every planned run present, the shared runner executes no algorithm and
    # deterministically rebuilds all typed statistics, reports, charts, and Manifest.
    return run_benchmark(config_path, output_dir)
