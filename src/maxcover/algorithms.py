"""Reference algorithms for Maximum Coverage."""

from __future__ import annotations

import heapq
import itertools
import math
import random
import time
from importlib.util import find_spec
from typing import Any, cast

from .contracts import AlgorithmRunOptions, AlgorithmSpec, OptionSpec
from .model import MaximumCoverageInstance, Solution, SolutionStatus


def _finish(
    name: str,
    instance: MaximumCoverageInstance,
    selected: tuple[int, ...],
    started: float,
    *,
    status: SolutionStatus,
    best_bound: int | None = None,
    work: int = 0,
    metadata: dict[str, object] | None = None,
) -> Solution:
    selected = tuple(sorted(selected))
    feasible_value = instance.coverage(selected)
    if status is SolutionStatus.OPTIMAL and best_bound is None:
        best_bound = feasible_value
    return Solution(
        algorithm=name,
        selected=selected,
        feasible_value=feasible_value,
        runtime_seconds=time.perf_counter() - started,
        status=status,
        best_bound=best_bound,
        nodes_or_iterations=work,
        metadata={} if metadata is None else metadata,
    )


def greedy(instance: MaximumCoverageInstance) -> Solution:
    """Select the set with the largest marginal gain at each step."""

    started = time.perf_counter()
    selected: list[int] = []
    covered = 0
    available = set(range(instance.set_count))
    iterations = 0

    for _ in range(instance.k):
        iterations += len(available)
        best = max(
            available,
            key=lambda index: (
                (instance.sets[index] & ~covered).bit_count(),
                -index,
            ),
        )
        selected.append(best)
        covered |= instance.sets[best]
        available.remove(best)

    return _finish(
        "greedy",
        instance,
        tuple(selected),
        started,
        status=SolutionStatus.FEASIBLE,
        work=iterations,
    )


def lazy_greedy(instance: MaximumCoverageInstance) -> Solution:
    """Select the same sets as :func:`greedy` with lazy marginal evaluation.

    The priority queue stores previously evaluated marginal gains as upper
    bounds.  Marginal gains only decrease as coverage grows, so a candidate is
    safe to select once its refreshed gain is no smaller than every remaining
    upper bound; the secondary index key preserves the classical Greedy
    tie-breaking rule.
    """

    started = time.perf_counter()
    queue = [(-mask.bit_count(), index) for index, mask in enumerate(instance.sets)]
    heapq.heapify(queue)
    selected: list[int] = []
    covered = 0
    # Building the initial upper-bound queue evaluates every candidate's
    # marginal gain at empty coverage. Count those evaluations so this metric
    # is comparable with dense Greedy's full candidate scan.
    marginal_evaluations = instance.set_count
    priority_queue_pops = 0
    trajectory: list[dict[str, int]] = []

    for iteration in range(instance.k):
        while True:
            _, index = heapq.heappop(queue)
            priority_queue_pops += 1
            gain = (instance.sets[index] & ~covered).bit_count()
            marginal_evaluations += 1
            refreshed = (-gain, index)
            if not queue or refreshed <= queue[0]:
                selected.append(index)
                covered |= instance.sets[index]
                trajectory.append(
                    {
                        "iteration": iteration + 1,
                        "selected_index": index,
                        "marginal_gain": gain,
                        "marginal_evaluations": marginal_evaluations,
                    }
                )
                break
            heapq.heappush(queue, refreshed)

    return _finish(
        "lazy_greedy",
        instance,
        tuple(selected),
        started,
        status=SolutionStatus.FEASIBLE,
        work=marginal_evaluations,
        metadata={
            "schema_version": 1,
            "termination": "completed",
            "search": {
                "initial_candidate_count": instance.set_count,
                "selected_count": len(selected),
                "marginal_evaluations": marginal_evaluations,
                "priority_queue_pops": priority_queue_pops,
            },
            "trajectory": trajectory,
        },
    )


def randomized_greedy(
    instance: MaximumCoverageInstance,
    *,
    algorithm_seed: int,
    rcl_size: int = 3,
) -> Solution:
    """Choose uniformly from a restricted list of the best marginal gains."""

    if isinstance(algorithm_seed, bool) or not isinstance(algorithm_seed, int):
        raise ValueError("algorithm_seed must be an integer")
    if isinstance(rcl_size, bool) or not isinstance(rcl_size, int) or rcl_size < 1:
        raise ValueError("rcl_size must be a positive integer")

    started = time.perf_counter()
    generator = random.Random(algorithm_seed)
    selected: list[int] = []
    covered = 0
    available = set(range(instance.set_count))
    evaluated = 0
    trajectory: list[dict[str, object]] = []

    for iteration in range(instance.k):
        ranked = sorted(
            available,
            key=lambda index: (
                -(instance.sets[index] & ~covered).bit_count(),
                index,
            ),
        )
        evaluated += len(ranked)
        restricted = ranked[: min(rcl_size, len(ranked))]
        chosen = restricted[generator.randrange(len(restricted))]
        gain = (instance.sets[chosen] & ~covered).bit_count()
        trajectory.append(
            {
                "iteration": iteration + 1,
                "rcl": restricted,
                "selected_index": chosen,
                "marginal_gain": gain,
            }
        )
        selected.append(chosen)
        covered |= instance.sets[chosen]
        available.remove(chosen)

    return _finish(
        "randomized_greedy",
        instance,
        tuple(selected),
        started,
        status=SolutionStatus.FEASIBLE,
        work=evaluated,
        metadata={
            "schema_version": 1,
            "termination": "completed",
            "search": {
                "algorithm_seed": algorithm_seed,
                "rcl_size": rcl_size,
            },
            "trajectory": trajectory,
        },
    )


def brute_force(
    instance: MaximumCoverageInstance,
    *,
    time_limit_seconds: float | None = None,
) -> Solution:
    """Enumerate all k-combinations; intended only as a small-instance oracle."""

    started = time.perf_counter()
    deadline = started + time_limit_seconds if time_limit_seconds else None
    best_selected: tuple[int, ...] = tuple(range(instance.k))
    best_coverage = instance.coverage(best_selected)
    evaluated = 0
    timed_out = False

    for selected in itertools.combinations(range(instance.set_count), instance.k):
        if deadline is not None and time.perf_counter() >= deadline:
            timed_out = True
            break
        evaluated += 1
        value = instance.coverage(selected)
        if value > best_coverage:
            best_coverage = value
            best_selected = selected

    status = (
        SolutionStatus.OPTIMAL
        if not timed_out or best_coverage == instance.universe_size
        else SolutionStatus.TIMEOUT
    )
    return _finish(
        "brute_force",
        instance,
        best_selected,
        started,
        status=status,
        best_bound=(
            best_coverage
            if status is SolutionStatus.OPTIMAL
            else instance.universe_size
        ),
        work=evaluated,
    )


def branch_and_bound(
    instance: MaximumCoverageInstance,
    *,
    time_limit_seconds: float | None = 5.0,
) -> Solution:
    """Exact depth-first search using suffix-union and cardinality bounds."""

    started = time.perf_counter()
    deadline = started + time_limit_seconds if time_limit_seconds else None

    # Large sets first usually produce a strong incumbent early. Original indices
    # remain attached so the returned solution is expressed in input coordinates.
    ordered = sorted(
        enumerate(instance.sets), key=lambda pair: pair[1].bit_count(), reverse=True
    )
    original_indices = [pair[0] for pair in ordered]
    masks = [pair[1] for pair in ordered]
    n = len(masks)

    suffix_union = [0] * (n + 1)
    for index in range(n - 1, -1, -1):
        suffix_union[index] = suffix_union[index + 1] | masks[index]

    incumbent = greedy(instance)
    best_selected = list(incumbent.selected)
    best_value = cast(int, incumbent.coverage)
    nodes = 0
    timed_out = False
    bound_prunes = 0
    cardinality_prunes = 0
    incumbent_updates = 0
    max_depth = 0
    initial_incumbent = best_value

    def search(position: int, chosen: list[int], covered: int) -> None:
        nonlocal best_selected, best_value, nodes, timed_out
        nonlocal bound_prunes, cardinality_prunes, incumbent_updates, max_depth
        nodes += 1
        max_depth = max(max_depth, position)

        if deadline is not None and time.perf_counter() >= deadline:
            timed_out = True
            return

        value = covered.bit_count()
        if value > best_value:
            best_value = value
            best_selected = [original_indices[i] for i in chosen]
            incumbent_updates += 1

        slots = instance.k - len(chosen)
        if slots == 0 or position == n:
            return
        if n - position < slots:
            cardinality_prunes += 1
            return

        # Even taking every remaining element cannot improve the incumbent.
        if (covered | suffix_union[position]).bit_count() <= best_value:
            bound_prunes += 1
            return

        chosen.append(position)
        search(position + 1, chosen, covered | masks[position])
        chosen.pop()
        if timed_out:
            return
        search(position + 1, chosen, covered)

    search(0, [], 0)
    status = (
        SolutionStatus.OPTIMAL
        if not timed_out or best_value == instance.universe_size
        else SolutionStatus.TIMEOUT
    )
    return _finish(
        "branch_and_bound",
        instance,
        tuple(best_selected),
        started,
        status=status,
        best_bound=(
            best_value
            if status is SolutionStatus.OPTIMAL
            else instance.universe_size
        ),
        work=nodes,
        metadata={
            "schema_version": 1,
            "termination": "time_limit" if timed_out else "completed",
            "search": {
                "nodes_visited": nodes,
                "bound_prunes": bound_prunes,
                "cardinality_prunes": cardinality_prunes,
                "incumbent_updates": incumbent_updates,
                "max_depth": max_depth,
                "initial_incumbent": initial_incumbent,
            },
            "trajectory": [],
        },
    )


def branch_and_bound_enhanced(
    instance: MaximumCoverageInstance,
    *,
    time_limit_seconds: float | None = 5.0,
    remove_duplicates: bool = True,
    remove_dominated: bool = True,
    bound_strategy: str = "cardinality",
    ordering_strategy: str = "dynamic_marginal",
) -> Solution:
    """Exact search with safe preprocessing and a cardinality-aware bound."""

    if bound_strategy not in {"suffix_union", "cardinality"}:
        raise ValueError("unknown branch-and-bound bound strategy")
    if ordering_strategy not in {"static_size", "dynamic_marginal"}:
        raise ValueError("unknown branch-and-bound ordering strategy")

    started = time.perf_counter()
    deadline = started + time_limit_seconds if time_limit_seconds else None
    candidates = list(enumerate(instance.sets))
    input_set_count = len(candidates)

    duplicate_sets_removed = 0
    if remove_duplicates:
        unique: list[tuple[int, int]] = []
        seen_masks: set[int] = set()
        for original_index, mask in candidates:
            if mask in seen_masks:
                duplicate_sets_removed += 1
                continue
            seen_masks.add(mask)
            unique.append((original_index, mask))
        candidates = unique

    dominated_sets_removed = 0
    if remove_dominated:
        kept: list[tuple[int, int]] = []
        for position, candidate in enumerate(candidates):
            _, mask = candidate
            dominated = any(
                position != other_position
                and mask != other_mask
                and mask | other_mask == other_mask
                for other_position, (_, other_mask) in enumerate(candidates)
            )
            if dominated:
                dominated_sets_removed += 1
            else:
                kept.append(candidate)
        candidates = kept

    candidates.sort(key=lambda item: (-item[1].bit_count(), item[0]))
    incumbent = greedy(instance)
    best_selected = tuple(incumbent.selected)
    best_value = cast(int, incumbent.coverage)
    initial_incumbent = best_value
    nodes = 0
    timed_out = False
    bound_prunes = 0
    cardinality_bound_prunes = 0
    incumbent_updates = 0
    max_depth = 0

    def search(
        remaining: tuple[tuple[int, int], ...],
        chosen: tuple[int, ...],
        covered: int,
        depth: int,
    ) -> None:
        nonlocal best_selected, best_value, nodes, timed_out
        nonlocal bound_prunes, cardinality_bound_prunes
        nonlocal incumbent_updates, max_depth
        nodes += 1
        max_depth = max(max_depth, depth)

        if deadline is not None and time.perf_counter() >= deadline:
            timed_out = True
            return

        value = covered.bit_count()
        if value > best_value:
            best_value = value
            best_selected = tuple(sorted(chosen))
            incumbent_updates += 1

        slots = instance.k - len(chosen)
        if slots == 0 or not remaining or best_value == instance.universe_size:
            return

        union_mask = covered
        marginal_gains: list[int] = []
        for _, mask in remaining:
            union_mask |= mask
            marginal_gains.append((mask & ~covered).bit_count())
        union_bound = union_mask.bit_count()
        upper_bound = union_bound
        if bound_strategy == "cardinality":
            marginal_gains.sort(reverse=True)
            cardinality_bound = min(
                instance.universe_size,
                value + sum(marginal_gains[:slots]),
            )
            upper_bound = min(union_bound, cardinality_bound)
        if upper_bound <= best_value:
            bound_prunes += 1
            if bound_strategy == "cardinality" and union_bound > best_value:
                cardinality_bound_prunes += 1
            return

        if ordering_strategy == "dynamic_marginal":
            branch_position = max(
                range(len(remaining)),
                key=lambda index: (
                    (remaining[index][1] & ~covered).bit_count(),
                    remaining[index][1].bit_count(),
                    -remaining[index][0],
                ),
            )
        else:
            branch_position = 0
        original_index, mask = remaining[branch_position]
        rest = remaining[:branch_position] + remaining[branch_position + 1 :]

        search(rest, chosen + (original_index,), covered | mask, depth + 1)
        if timed_out:
            return
        search(rest, chosen, covered, depth + 1)

    search(tuple(candidates), (), 0, 0)
    status = (
        SolutionStatus.OPTIMAL
        if not timed_out or best_value == instance.universe_size
        else SolutionStatus.TIMEOUT
    )
    return _finish(
        "branch_and_bound_enhanced",
        instance,
        best_selected,
        started,
        status=status,
        best_bound=(
            best_value if status is SolutionStatus.OPTIMAL else instance.universe_size
        ),
        work=nodes,
        metadata={
            "schema_version": 1,
            "termination": "time_limit" if timed_out else "completed",
            "search": {
                "nodes_visited": nodes,
                "bound_prunes": bound_prunes,
                "cardinality_prunes": cardinality_bound_prunes,
                "incumbent_updates": incumbent_updates,
                "max_depth": max_depth,
                "initial_incumbent": initial_incumbent,
                "input_set_count": input_set_count,
                "search_set_count": len(candidates),
                "duplicate_sets_removed": duplicate_sets_removed,
                "dominated_sets_removed": dominated_sets_removed,
                "bound_strategy": bound_strategy,
                "ordering_strategy": ordering_strategy,
            },
            "trajectory": [],
        },
    )


def local_search(instance: MaximumCoverageInstance) -> Solution:
    """Improve the greedy solution using deterministic best one-set swaps."""

    started = time.perf_counter()
    initial = greedy(instance)
    selected = set(initial.selected)
    best_value = cast(int, initial.coverage)
    iterations = 0

    while True:
        best_swap: tuple[int, int] | None = None
        swap_value = best_value
        outside = set(range(instance.set_count)) - selected

        for removed in sorted(selected):
            for added in sorted(outside):
                iterations += 1
                candidate = tuple((selected - {removed}) | {added})
                value = instance.coverage(candidate)
                if value > swap_value:
                    swap_value = value
                    best_swap = (removed, added)

        if best_swap is None:
            break
        selected.remove(best_swap[0])
        selected.add(best_swap[1])
        best_value = swap_value

    return _finish(
        "local_search",
        instance,
        tuple(selected),
        started,
        status=SolutionStatus.FEASIBLE,
        work=iterations,
    )


def multi_start_local_search(
    instance: MaximumCoverageInstance,
    *,
    algorithm_seed: int,
    restart_count: int = 8,
    max_iterations_per_restart: int = 1000,
    time_limit_seconds: float | None = 5.0,
) -> Solution:
    """Run deterministic best-improvement swaps from greedy and random starts."""

    if isinstance(algorithm_seed, bool) or not isinstance(algorithm_seed, int):
        raise ValueError("algorithm_seed must be an integer")
    if (
        isinstance(restart_count, bool)
        or not isinstance(restart_count, int)
        or restart_count < 0
    ):
        raise ValueError("restart_count must be a non-negative integer")
    if (
        isinstance(max_iterations_per_restart, bool)
        or not isinstance(max_iterations_per_restart, int)
        or max_iterations_per_restart < 1
    ):
        raise ValueError("max_iterations_per_restart must be a positive integer")
    if time_limit_seconds is not None and (
        isinstance(time_limit_seconds, bool)
        or not isinstance(time_limit_seconds, (int, float))
        or time_limit_seconds <= 0
    ):
        raise ValueError("time_limit_seconds must be positive or None")

    started = time.perf_counter()
    deadline = started + time_limit_seconds if time_limit_seconds else None
    generator = random.Random(algorithm_seed)
    greedy_start = greedy(instance)
    best_selected = tuple(greedy_start.selected)
    best_value = cast(int, greedy_start.coverage)
    total_evaluations = 0
    total_iterations = 0
    completed_restarts = 0
    iteration_limited_restarts = 0
    timed_out = False
    trajectory: list[dict[str, int]] = [
        {"iteration": 0, "coverage": best_value}
    ]

    # A zero restart budget retains the historical single greedy-initialized run.
    starts = max(1, restart_count)
    for restart in range(starts):
        if restart == 0:
            selected = set(greedy_start.selected)
        else:
            selected = set(
                sorted(generator.sample(range(instance.set_count), instance.k))
            )
        current_value = instance.coverage(tuple(selected))
        restart_iterations = 0

        while restart_count == 0 or restart_iterations < max_iterations_per_restart:
            if deadline is not None and time.perf_counter() >= deadline:
                timed_out = True
                break
            best_swap: tuple[int, int] | None = None
            swap_value = current_value
            outside = set(range(instance.set_count)) - selected
            for removed in sorted(selected):
                for added in sorted(outside):
                    if deadline is not None and time.perf_counter() >= deadline:
                        timed_out = True
                        break
                    total_evaluations += 1
                    candidate = tuple((selected - {removed}) | {added})
                    value = instance.coverage(candidate)
                    if value > swap_value:
                        swap_value = value
                        best_swap = (removed, added)
                if timed_out:
                    break
            if timed_out or best_swap is None:
                break
            selected.remove(best_swap[0])
            selected.add(best_swap[1])
            current_value = swap_value
            restart_iterations += 1
            total_iterations += 1
            candidate_selected = tuple(sorted(selected))
            if current_value > best_value or (
                current_value == best_value and candidate_selected < best_selected
            ):
                best_value = current_value
                best_selected = candidate_selected
                trajectory.append(
                    {"iteration": total_iterations, "coverage": best_value}
                )

        candidate_selected = tuple(sorted(selected))
        if current_value > best_value or (
            current_value == best_value and candidate_selected < best_selected
        ):
            best_value = current_value
            best_selected = candidate_selected
            trajectory.append(
                {"iteration": total_iterations, "coverage": best_value}
            )
        if timed_out:
            break
        completed_restarts += 1
        if restart_count > 0 and restart_iterations == max_iterations_per_restart:
            iteration_limited_restarts += 1

    return _finish(
        "multi_start_local_search",
        instance,
        best_selected,
        started,
        status=(SolutionStatus.TIMEOUT if timed_out else SolutionStatus.FEASIBLE),
        work=total_evaluations,
        metadata={
            "schema_version": 1,
            "termination": "time_limit" if timed_out else "completed",
            "search": {
                "algorithm_seed": algorithm_seed,
                "restart_count": restart_count,
                "starts_attempted": starts,
                "completed_restarts": completed_restarts,
                "iterations": total_iterations,
                "iteration_limited_restarts": iteration_limited_restarts,
                "swap_evaluations": total_evaluations,
                "initial_incumbent": greedy_start.coverage,
            },
            "trajectory": trajectory,
        },
    )


def _cp_sat_preflight_error() -> str | None:
    if find_spec("ortools") is None:
        return (
            "cp_sat_oracle requires optional dependency OR-Tools; "
            "install with 'pip install -e .[oracle]'"
        )
    return None


def _cp_sat_outcome(
    status_name: str,
    *,
    coverage: int,
    universe_size: int,
    solver_bound: float | None = None,
) -> tuple[SolutionStatus, int | None, bool]:
    """Map an OR-Tools status to our result contract without importing it."""

    if coverage == universe_size and status_name not in {
        "MODEL_INVALID",
        "INFEASIBLE",
    }:
        return SolutionStatus.OPTIMAL, coverage, status_name != "UNKNOWN"
    if status_name == "OPTIMAL":
        return SolutionStatus.OPTIMAL, coverage, True
    if status_name == "FEASIBLE":
        if solver_bound is None or not math.isfinite(solver_bound):
            bound = universe_size
        else:
            bound = math.ceil(solver_bound - 1e-9)
            bound = min(universe_size, max(coverage + 1, bound))
        return SolutionStatus.TIMEOUT, bound, True
    if status_name == "UNKNOWN":
        return SolutionStatus.TIMEOUT, universe_size, False
    if status_name in {"MODEL_INVALID", "INFEASIBLE"}:
        return SolutionStatus.ERROR, None, False
    return SolutionStatus.ERROR, None, False


def cp_sat_oracle(
    instance: MaximumCoverageInstance,
    *,
    time_limit_seconds: float | None = 5.0,
) -> Solution:
    """Solve maximum coverage with the optional single-worker CP-SAT oracle."""

    try:
        from ortools.sat.python import cp_model
    except ImportError as error:
        raise RuntimeError(
            "cp_sat_oracle requires OR-Tools; install with "
            "'pip install -e .[oracle]'"
        ) from error

    started = time.perf_counter()
    fallback = greedy(instance)
    fallback_selected = tuple(fallback.selected)
    fallback_covered = 0
    for index in fallback_selected:
        fallback_covered |= instance.sets[index]

    model = cp_model.CpModel()
    selected_variables = [
        model.NewBoolVar(f"x_{index}") for index in range(instance.set_count)
    ]
    covered_variables = [
        model.NewBoolVar(f"y_{element}")
        for element in range(instance.universe_size)
    ]
    model.Add(sum(selected_variables) <= instance.k)
    for element, covered_variable in enumerate(covered_variables):
        covering = [
            selected_variables[index]
            for index, mask in enumerate(instance.sets)
            if mask & (1 << element)
        ]
        if covering:
            model.Add(covered_variable <= sum(covering))
        else:
            model.Add(covered_variable == 0)
    model.Maximize(sum(covered_variables))
    for index, variable in enumerate(selected_variables):
        model.AddHint(variable, int(index in fallback_selected))
    for element, variable in enumerate(covered_variables):
        model.AddHint(variable, int(bool(fallback_covered & (1 << element))))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    if time_limit_seconds is not None:
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    raw_status = solver.Solve(model)
    status_name = solver.StatusName(raw_status).upper()

    has_solver_incumbent = status_name in {"OPTIMAL", "FEASIBLE"}
    solver_selected = (
        tuple(
            index
            for index, variable in enumerate(selected_variables)
            if solver.Value(variable)
        )
        if has_solver_incumbent
        else fallback_selected
    )
    solver_coverage = instance.coverage(solver_selected)
    fallback_coverage = cast(int, fallback.coverage)
    status, best_bound, use_solver_incumbent = _cp_sat_outcome(
        status_name,
        coverage=solver_coverage if has_solver_incumbent else fallback_coverage,
        universe_size=instance.universe_size,
        solver_bound=(solver.BestObjectiveBound() if has_solver_incumbent else None),
    )
    if status is SolutionStatus.ERROR:
        return Solution(
            algorithm="cp_sat_oracle",
            selected=(),
            feasible_value=None,
            runtime_seconds=time.perf_counter() - started,
            status=SolutionStatus.ERROR,
            metadata={
                "schema_version": 1,
                "termination": "error",
                "search": {"cp_sat_status": status_name},
                "trajectory": [],
            },
        )
    selected = solver_selected if use_solver_incumbent else fallback_selected
    return _finish(
        "cp_sat_oracle",
        instance,
        selected,
        started,
        status=status,
        best_bound=best_bound,
        work=int(solver.NumBranches()),
        metadata={
            "schema_version": 1,
            "termination": (
                "completed"
                if status is SolutionStatus.OPTIMAL
                else "time_limit"
            ),
            "search": {
                "cp_sat_status": status_name,
                "best_objective_bound": best_bound,
                "used_greedy_fallback": not use_solver_incumbent,
                "num_conflicts": int(solver.NumConflicts()),
                "num_branches": int(solver.NumBranches()),
            },
            "trajectory": [],
        },
    )


def _run_greedy(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    del options
    return greedy(instance)


def _run_lazy_greedy(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    del options
    return lazy_greedy(instance)


def _run_local_search(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    del options
    return local_search(instance)


def _run_randomized_greedy(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    assert options.algorithm_seed is not None
    return randomized_greedy(
        instance,
        algorithm_seed=options.algorithm_seed,
        rcl_size=int(cast(Any, options.get("rcl_size", 3))),
    )


def _run_multi_start_local_search(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    assert options.algorithm_seed is not None
    return multi_start_local_search(
        instance,
        algorithm_seed=options.algorithm_seed,
        restart_count=int(cast(Any, options.get("restart_count", 8))),
        max_iterations_per_restart=int(
            cast(Any, options.get("max_iterations_per_restart", 1000))
        ),
        time_limit_seconds=options.time_limit_seconds,
    )


def _run_cp_sat_oracle(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    return cp_sat_oracle(
        instance, time_limit_seconds=options.time_limit_seconds
    )


def _run_brute_force(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    return brute_force(instance, time_limit_seconds=options.time_limit_seconds)


def _run_branch_and_bound(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    return branch_and_bound(instance, time_limit_seconds=options.time_limit_seconds)


def _run_branch_and_bound_enhanced(
    instance: MaximumCoverageInstance, options: AlgorithmRunOptions
) -> Solution:
    return branch_and_bound_enhanced(
        instance,
        time_limit_seconds=options.time_limit_seconds,
        remove_duplicates=bool(options.get("remove_duplicates", True)),
        remove_dominated=bool(options.get("remove_dominated", True)),
        bound_strategy=str(options.get("bound_strategy", "cardinality")),
        ordering_strategy=str(
            options.get("ordering_strategy", "dynamic_marginal")
        ),
    )


ALGORITHMS: dict[str, AlgorithmSpec] = {
    "greedy": AlgorithmSpec(
        name="greedy",
        exact=False,
        runner=_run_greedy,
    ),
    "lazy_greedy": AlgorithmSpec(
        name="lazy_greedy",
        exact=False,
        runner=_run_lazy_greedy,
        version=2,
    ),
    "local_search": AlgorithmSpec(
        name="local_search",
        exact=False,
        runner=_run_local_search,
    ),
    "randomized_greedy": AlgorithmSpec(
        name="randomized_greedy",
        exact=False,
        runner=_run_randomized_greedy,
        uses_random_seed=True,
        option_specs={
            "rcl_size": OptionSpec(
                (int,), "positive integer", default=3, minimum=1
            ),
        },
    ),
    "multi_start_local_search": AlgorithmSpec(
        name="multi_start_local_search",
        exact=False,
        runner=_run_multi_start_local_search,
        uses_random_seed=True,
        supported_options=frozenset({"time_limit_seconds"}),
        default_time_limit_seconds=5.0,
        option_specs={
            "restart_count": OptionSpec(
                (int,), "non-negative integer", default=8, minimum=0
            ),
            "max_iterations_per_restart": OptionSpec(
                (int,), "positive integer", default=1000, minimum=1
            ),
        },
    ),
    "brute_force": AlgorithmSpec(
        name="brute_force",
        exact=True,
        runner=_run_brute_force,
        supported_options=frozenset({"time_limit_seconds", "max_set_count"}),
        time_limit_config_key="exact_time_limit_seconds",
        default_time_limit_seconds=5.0,
        set_count_limit_config_key="brute_force_set_cutoff",
        default_max_set_count=18,
    ),
    "cp_sat_oracle": AlgorithmSpec(
        name="cp_sat_oracle",
        exact=True,
        runner=_run_cp_sat_oracle,
        supported_options=frozenset({"time_limit_seconds"}),
        default_time_limit_seconds=5.0,
        preflight_error=_cp_sat_preflight_error,
    ),
    "branch_and_bound": AlgorithmSpec(
        name="branch_and_bound",
        exact=True,
        runner=_run_branch_and_bound,
        version=2,
        supported_options=frozenset({"time_limit_seconds"}),
        time_limit_config_key="exact_time_limit_seconds",
        default_time_limit_seconds=5.0,
    ),
    "branch_and_bound_enhanced": AlgorithmSpec(
        name="branch_and_bound_enhanced",
        exact=True,
        runner=_run_branch_and_bound_enhanced,
        supported_options=frozenset({"time_limit_seconds"}),
        time_limit_config_key="exact_time_limit_seconds",
        default_time_limit_seconds=5.0,
        option_specs={
            "remove_duplicates": OptionSpec((bool,), "boolean", default=True),
            "remove_dominated": OptionSpec((bool,), "boolean", default=True),
            "bound_strategy": OptionSpec(
                (str,),
                "string",
                default="cardinality",
                choices=frozenset({"suffix_union", "cardinality"}),
            ),
            "ordering_strategy": OptionSpec(
                (str,),
                "string",
                default="dynamic_marginal",
                choices=frozenset({"static_size", "dynamic_marginal"}),
            ),
        },
    ),
}
