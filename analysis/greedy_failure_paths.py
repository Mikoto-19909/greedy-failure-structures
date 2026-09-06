"""R1: exact prefix reachability and deterministic exchange diagnostics.

Run with --design analysis/r1_prefix_exchange_design.json --output DIR.
The study reuses the complete old pilot and keeps synthetic fixtures separate.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from itertools import combinations
from pathlib import Path
from statistics import fmean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import greedy, local_search
from maxcover.benchmark_planning import _instances_for_config
from maxcover.config import load_config
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import config_hash, instance_id


INSTANCE_FIELDS = (
    "population", "case_id", "repetition", "instance_id", "greedy", "optimal",
    "first_failure_step", "mechanism", "one_swap", "two_swap", "one_swap_moves",
    "two_swap_moves", "one_swap_evaluations", "two_swap_evaluations", "two_swap_status",
    "greedy_gap", "one_swap_gap", "two_swap_gap",
)
CASE_FIELDS = (
    "case_id", "n", "greedy_failures", "tie_avoidable", "one_step_limit",
    "first_loss_1", "first_loss_2", "first_loss_3", "first_loss_4",
    "one_swap_recovered", "two_swap_recovered", "one_swap_stalls", "two_swap_stalls",
    "two_swap_incomplete", "mean_greedy_gap", "mean_one_swap_gap", "mean_two_swap_gap",
    "tie_avoidable_among_failures", "tie_avoidable_among_all",
)


def covered(instance: MaximumCoverageInstance, selected) -> int:
    mask = 0
    for index in selected:
        mask |= instance.sets[index]
    return mask.bit_count()


def completion_table(instance: MaximumCoverageInstance, limit: int):
    count = math.comb(instance.set_count, instance.k)
    if count > limit:
        raise ValueError(f"exhaustive completion needs {count} choices; limit is {limit}")
    return [(choice, sum(1 << i for i in choice), covered(instance, choice))
            for choice in combinations(range(instance.set_count), instance.k)]


def best_completion(table, prefix):
    required = sum(1 << i for i in prefix)
    choices = [item for item in table if item[1] & required == required]
    best = min(choices, key=lambda item: (-item[2], item[0]))
    return best[2], list(best[0]), len(choices)


def exchange_trace(instance, initial, maximum_size, values, budget=None):
    selected = tuple(sorted(initial))
    used = 0
    moves = 0
    rounds = []
    while True:
        value = values[selected]
        best_value = value
        best_move = None
        count = 0
        stopped = False
        outside = tuple(i for i in range(instance.set_count) if i not in selected)
        for size in range(1, min(maximum_size, instance.k, len(outside)) + 1):
            for removed in combinations(selected, size):
                for added in combinations(outside, size):
                    if budget is not None and used + count >= budget:
                        stopped = True
                        break
                    candidate = tuple(sorted((set(selected) - set(removed)) | set(added)))
                    count += 1
                    candidate_value = values[candidate]
                    # Enumeration order implements the declared (size, removed, added) tie rule.
                    if candidate_value > best_value:
                        best_value = candidate_value
                        best_move = (removed, added, candidate)
                if stopped:
                    break
            if stopped:
                break
        used += count
        before = list(selected)
        if stopped or best_move is None:
            status = "budget_exhausted" if stopped else "local_optimum"
            removed, added, after = [], [], before
            after_value = value
        else:
            removed, added, candidate = best_move
            removed, added, after = list(removed), list(added), list(candidate)
            after_value = best_value
            status = "improved"
            selected = candidate
            moves += 1
        rounds.append({"round": len(rounds) + 1, "before": before,
                       "before_coverage": value, "removed": removed, "added": added,
                       "after": after, "after_coverage": after_value,
                       "evaluations": count, "status": status})
        if status != "improved":
            return {"selected": list(selected), "coverage": value, "evaluations": used,
                    "exchanges": moves, "status": status, "rounds": rounds}


def analyze_instance(instance, *, max_completions=200000, max_two_swap_evaluations=100000):
    if max_completions < 1 or max_two_swap_evaluations < 0:
        raise ValueError("analysis budgets must be nonnegative and allow a completion")
    table = completion_table(instance, max_completions)
    optimum, witness, count = best_completion(table, ())
    values = {choice: value for choice, _, value in table}
    prefix = []
    prefixes = []
    ties = []
    mask = 0
    first_failure = None
    for step in range(instance.k + 1):
        reachable, completion, feasible_count = best_completion(table, prefix)
        prefixes.append({"step": step, "prefix": list(prefix), "coverage": mask.bit_count(),
                         "optimal_completion": reachable, "completion_selected": completion,
                         "completion_count": feasible_count})
        if first_failure is None and reachable < optimum:
            first_failure = step
        if step == instance.k:
            break
        gains = {index: (instance.sets[index] & ~mask).bit_count()
                 for index in range(instance.set_count) if index not in prefix}
        maximum = max(gains.values())
        candidates = [index for index, gain in gains.items() if gain == maximum]
        chosen = min(candidates)
        for index in candidates:
            bound, completion, feasible_count = best_completion(table, [*prefix, index])
            ties.append({"step": step + 1, "candidate": index, "marginal_gain": maximum,
                         "chosen": index == chosen, "optimal_completion": bound,
                         "completion_selected": completion, "completion_count": feasible_count,
                         "preserves_optimum": bound == optimum})
        prefix.append(chosen)
        mask |= instance.sets[chosen]
    greedy_result = greedy(instance)
    if sorted(prefix) != list(greedy_result.selected) or mask.bit_count() != greedy_result.coverage:
        raise ValueError("recorded decision path differs from the source greedy algorithm")
    one = exchange_trace(instance, prefix, 1, values)
    source_one = local_search(instance)
    if (one["selected"] != list(source_one.selected) or one["coverage"] != source_one.coverage
            or one["evaluations"] != source_one.nodes_or_iterations):
        raise ValueError("one-swap trace differs from source local_search")
    two = exchange_trace(instance, one["selected"], 2, values, max_two_swap_evaluations)
    if first_failure is None:
        mechanism = "optimal"
    elif any(row["preserves_optimum"] for row in ties if row["step"] == first_failure):
        mechanism = "tie_avoidable"
    else:
        mechanism = "one_step_limit"
    return {"greedy_selected": prefix, "optimum": optimum, "optimum_selected": witness,
            "optimal_solution_count": sum(value == optimum for _, _, value in table),
            "completion_count": count, "prefixes": prefixes, "ties": ties,
            "first_failure_step": first_failure, "mechanism": mechanism,
            "one_swap": one, "two_swap": two}


def population(design):
    # Reuse the existing pilot input checks. The R1 exact enumeration separately
    # checks the recorded reference values and reconstructed greedy endpoint.
    from core_overlap_pilot import load_inputs
    config_path = ROOT / design["config"]
    results = ROOT / design["source_results"]
    load_inputs(config_path, results)
    config = load_config(config_path)
    identifier = config_hash(config)
    with (results / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
        raw = {(row["instance_id"], row["algorithm_id"]): row for row in csv.DictReader(handle)}
    entries = []
    for planned in _instances_for_config(config):
        instance = planned.instance
        g = raw[(planned.instance_id, "greedy")]
        o = raw[(planned.instance_id, "exact_reference")]
        base = {"instance_id": planned.instance_id, "population": "pilot",
                "case_id": planned.case_id, "repetition": planned.repetition,
                "seed": instance.seed, "config_hash": identifier,
                "universe_size": instance.universe_size, "k": instance.k,
                "sets": [[e for e in range(instance.universe_size) if mask & (1 << e)] for mask in instance.sets],
                "source_greedy_selected": [int(i) for i in g["selected"].split()],
                "source_optimum": int(o["coverage"])}
        entries.append((base, instance))
    for fixture in design["fixtures"]:
        instance = MaximumCoverageInstance(
            universe_size=fixture["universe_size"], k=fixture["k"],
            sets=tuple(sum(1 << e for e in group) for group in fixture["sets"]),
            parameters={"r1_fixture": fixture["name"]},
        )
        entries.append(({"instance_id": instance_id(instance), "population": "fixture",
                         "case_id": fixture["name"], "repetition": None, "seed": None,
                         "config_hash": None, "universe_size": instance.universe_size,
                         "k": instance.k, "sets": fixture["sets"],
                         "source_greedy_selected": None, "source_optimum": None}, instance))
    return entries


def gap(value, optimum):
    return (optimum-value)/optimum if optimum else None


def instance_summary(row):
    optimum = row["optimum"]
    g = row["prefixes"][-1]["coverage"]
    one, two = row["one_swap"], row["two_swap"]
    return {**{field: row[field] for field in INSTANCE_FIELDS[:4]},
            "greedy": g, "optimal": optimum, "first_failure_step": row["first_failure_step"],
            "mechanism": row["mechanism"], "one_swap": one["coverage"], "two_swap": two["coverage"],
            "one_swap_moves": one["exchanges"], "two_swap_moves": two["exchanges"],
            "one_swap_evaluations": one["evaluations"], "two_swap_evaluations": two["evaluations"],
            "two_swap_status": two["status"], "greedy_gap": gap(g, optimum),
            "one_swap_gap": gap(one["coverage"], optimum), "two_swap_gap": gap(two["coverage"], optimum)}


def case_summaries(rows):
    result = []
    for case in sorted({row["case_id"] for row in rows if row["population"] == "pilot"}):
        group = [instance_summary(row) for row in rows if row["population"] == "pilot" and row["case_id"] == case]
        failures = [row for row in group if row["greedy"] < row["optimal"]]
        tied = sum(row["mechanism"] == "tie_avoidable" for row in group)
        item = {"case_id": case, "n": len(group), "greedy_failures": len(failures),
                "tie_avoidable": tied, "one_step_limit": sum(row["mechanism"] == "one_step_limit" for row in group),
                **{f"first_loss_{t}": sum(row["first_failure_step"] == t for row in group) for t in range(1, 5)},
                "one_swap_recovered": sum(row["one_swap"] == row["optimal"] for row in failures),
                "two_swap_recovered": sum(row["two_swap"] == row["optimal"] for row in failures),
                "one_swap_stalls": sum(row["one_swap"] < row["optimal"] for row in group),
                "two_swap_stalls": sum(row["two_swap"] < row["optimal"] and row["two_swap_status"] == "local_optimum" for row in group),
                "two_swap_incomplete": sum(row["two_swap_status"] != "local_optimum" for row in group),
                **{f"mean_{field}": fmean(row[field] for row in group if row[field] is not None)
                   for field in ("greedy_gap", "one_swap_gap", "two_swap_gap")},
                "tie_avoidable_among_failures": tied/len(failures) if failures else None,
                "tie_avoidable_among_all": tied/len(group)}
        result.append(item)
    return result


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: "" if value is None else format(value, ".12g") if isinstance(value, float) else value
                         for key, value in row.items()} for row in rows)


def render_figure(cases, output):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    plt.rcParams["svg.hashsalt"] = "r1-prefix-exchange"
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), layout="constrained")
    colors = ("#2563eb", "#dc6b35")
    labels = ("High overlap", "Uniform control")
    for i, row in enumerate(cases):
        axes[0].bar([t + (i-.5)*.34 for t in range(1, 5)],
                    [row[f"first_loss_{t}"] for t in range(1, 5)], width=.34,
                    color=colors[i], label=f"{labels[i]} (n={row['n']})")
        axes[1].plot(range(3), [100*row[f"mean_{phase}_gap"] for phase in ("greedy", "one_swap", "two_swap")],
                     marker="o", color=colors[i], label=labels[i])
    axes[0].set(xticks=range(1, 5), xlabel="First loss of optimal reachability (step)", ylabel="Instances")
    axes[1].set(xticks=range(3), xticklabels=["Greedy", "1-swap", "Up to 2-swap"], ylabel="Mean relative gap (%)")
    for axis in axes:
        axis.set_ylim(bottom=0)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=.2)
        axis.legend(frameon=False, fontsize=8)
    fig.suptitle("R1 exploratory reanalysis of the existing 30 paired seeds", fontsize=12)
    fig.savefig(output / "r1_prefix_exchange.svg", metadata={"Date": None})
    fig.savefig(output / "r1_prefix_exchange.png", dpi=150)
    plt.close(fig)


def run(design_path, output, *, plot=True):
    design = json.loads(design_path.read_text(encoding="utf-8"))
    entries = population(design)
    if output.exists() and any(output.iterdir()):
        raise ValueError("use a new or empty output directory")
    # Complete enumeration budgets are checked before creating output.
    for _, instance in entries:
        if math.comb(instance.set_count, instance.k) > design["max_completions"]:
            raise ValueError("completion budget cannot cover the specified population")
    rows = []
    for base, instance in entries:
        result = analyze_instance(instance, max_completions=design["max_completions"],
                                  max_two_swap_evaluations=design["max_two_swap_evaluations"])
        if base["population"] == "pilot":
            if sorted(result["greedy_selected"]) != sorted(base["source_greedy_selected"]) or result["optimum"] != base["source_optimum"]:
                raise ValueError("reconstructed greedy or exact result differs from the saved pilot")
        rows.append({**base, **result})
    output.mkdir(parents=True, exist_ok=True)
    (output / "paths.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    write_csv(output / "instance_summary.csv", [instance_summary(row) for row in rows], INSTANCE_FIELDS)
    cases = case_summaries(rows)
    write_csv(output / "case_summary.csv", cases, CASE_FIELDS)
    if plot:
        render_figure(cases, output)
    print(f"Completed {sum(row['population']=='pilot' for row in rows)} pilot instances and {sum(row['population']=='fixture' for row in rows)} fixtures; output: {output}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=ROOT / "analysis/r1_prefix_exchange_design.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args(argv)
    run(args.design, args.output, plot=not args.no_plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
