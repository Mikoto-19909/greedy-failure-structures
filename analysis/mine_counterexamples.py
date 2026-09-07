"""Mine saved instances for Greedy failures and deterministically reduce them.

Input: R1/R1c paths.jsonl or a single instance JSON. Saved scores are not trusted.
Only k and G < O are preserved by reduction; structural families may change.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from math import comb
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import brute_force, greedy
from maxcover.model import MaximumCoverageInstance, SolutionStatus
from maxcover.reproducibility import instance_from_payload, instance_payload


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def read_inputs(path):
    """Use actual ordered sets; source IDs are provenance labels, not rederived IDs."""
    with path.open(encoding="utf-8-sig") as handle:
        if path.suffix.lower() == ".jsonl":
            documents = [(line, json.loads(text)) for line, text in enumerate(handle, 1)
                         if text.strip()]
        else:
            documents = [(1, json.load(handle))]
    if not documents:
        raise ValueError("input contains no instances")
    entries = []
    for line, document in documents:
        if not isinstance(document, dict):
            raise ValueError(f"input record {line} must be an object")
        data = document.get("instance", document)
        if not isinstance(data, dict):
            raise ValueError(f"input record {line}: instance must be an object")
        integer(data.get("k"), "k", 1)
        payload = {**data}
        payload.setdefault("schema_version", 1)
        payload.setdefault("encoding", "elements")
        instance = instance_from_payload(payload)
        entries.append({
            "source": {"path": str(path.resolve()), "record": line,
                       **{key: document[key] for key in
                          ("instance_id", "case_id", "population", "repetition", "seed")
                          if key in document}},
            "instance": instance_payload(instance),
        })
    return entries


def evaluate(instance, max_combinations):
    count = comb(instance.set_count, instance.k)
    if count > max_combinations:
        return {"status": "combination_limit", "combinations": count}
    g = greedy(instance)
    o = brute_force(instance, time_limit_seconds=None)
    if o.status is not SolutionStatus.OPTIMAL or o.nodes_or_iterations != count:
        raise ValueError("exact enumeration did not complete")
    chosen, trace, mask = [], [], 0
    for step in range(instance.k):
        gains = {i: (s & ~mask).bit_count() for i, s in enumerate(instance.sets)
                 if i not in chosen}
        gain = max(gains.values())
        ties = [i for i, value in gains.items() if value == gain]
        index = min(ties)
        chosen.append(index)
        mask |= instance.sets[index]
        trace.append({"step": step + 1, "selected": index, "gain": gain,
                      "ties": ties, "coverage": mask.bit_count()})
    if tuple(sorted(chosen)) != g.selected or mask.bit_count() != g.coverage:
        raise ValueError("trace differs from source Greedy")
    return {"status": "exact", "combinations": count, "greedy": g.coverage,
            "optimum": o.coverage, "greedy_selected": chosen,
            "optimum_selected": list(o.selected), "trace": trace,
            "gap": (o.coverage - g.coverage) / o.coverage if o.coverage else None}


def deletions(instance):
    """Ordered one-step neighbors, preserving relative set/element order."""
    sets, n, k = instance.sets, instance.universe_size, instance.k
    if len(sets) > k:
        for i in range(len(sets)):
            yield {"kind": "set", "index": i}, MaximumCoverageInstance(
                n, sets[:i] + sets[i + 1:], k)
    if n > 1:
        for e in range(n):
            lower = (1 << e) - 1
            reduced = tuple((s & lower) | ((s >> (e + 1)) << e) for s in sets)
            yield {"kind": "element", "index": e}, MaximumCoverageInstance(n - 1, reduced, k)
    for i, s in enumerate(sets):
        for e in range(n):
            if s & (1 << e):
                reduced = sets[:i] + (s & ~(1 << e),) + sets[i + 1:]
                yield {"kind": "membership", "set": i, "element": e}, MaximumCoverageInstance(n, reduced, k)


def shrink(instance, evaluation, *, max_combinations, max_evaluations):
    integer(max_evaluations, "max_evaluations")
    if evaluation["status"] != "exact" or evaluation["greedy"] >= evaluation["optimum"]:
        raise ValueError("reduction requires a verified counterexample")
    current, result, attempts, steps = instance, evaluation, 0, []
    while True:
        for operation, candidate in deletions(current):
            if attempts >= max_evaluations:
                return {"instance": instance_payload(current), "evaluation": result,
                        "status": "budget_exhausted", "evaluations": attempts, "steps": steps}
            candidate_result = evaluate(candidate, max_combinations)
            attempts += 1
            if candidate_result["status"] != "exact":
                raise ValueError("reduction unexpectedly exceeded the exact budget")
            if candidate_result["greedy"] < candidate_result["optimum"]:
                steps.append({"operation": operation, "evaluation_number": attempts})
                current, result = candidate, candidate_result
                break  # Restart all deletion types after each accepted move.
        else:
            return {"instance": instance_payload(current), "evaluation": result,
                    "status": "deletion_minimal", "evaluations": attempts, "steps": steps}


def size(payload):
    return (len(payload["sets"]), payload["universe_size"], sum(map(len, payload["sets"])))


def mine(path, *, top=5, max_combinations=200000, max_evaluations=10000, population=None):
    integer(top, "top", 1)
    integer(max_combinations, "max_combinations", 1)
    integer(max_evaluations, "max_evaluations")
    entries = read_inputs(path)
    if population is not None:
        if not isinstance(population, str) or not population:
            raise ValueError("population must be a nonempty source label")
        entries = [entry for entry in entries if entry["source"].get("population") == population]
        if not entries:
            raise ValueError(f"no input records match population={population!r}")
    failures = []
    for index, entry in enumerate(entries):
        evaluation = evaluate(instance_from_payload(entry["instance"]), max_combinations)
        entry["evaluation"] = evaluation
        if evaluation["status"] == "exact" and evaluation["greedy"] < evaluation["optimum"]:
            failures.append(index)
    failures.sort(key=lambda i: (
        -Fraction(entries[i]["evaluation"]["optimum"] - entries[i]["evaluation"]["greedy"],
                  entries[i]["evaluation"]["optimum"]),
        size(entries[i]["instance"]), i))
    selected = []
    for index in failures[:top]:
        entry = entries[index]
        reduced = shrink(instance_from_payload(entry["instance"]), entry["evaluation"],
                         max_combinations=max_combinations, max_evaluations=max_evaluations)
        selected.append({"input_index": index, **reduced})
    document = {"schema_version": 1,
            "settings": {"top": top, "max_combinations": max_combinations,
                         "max_evaluations": max_evaluations},
            "counts": {"input": len(entries), "exact": sum(
                e["evaluation"]["status"] == "exact" for e in entries),
                "failures": len(failures), "selected": len(selected)},
            "inputs": entries, "selected": selected}
    if population is not None:
        document["settings"]["population"] = population
    return document


def write_outputs(document, output):
    # Verify with set-based computations before making the deliverable visible.
    from validate_counterexamples import validate_document
    validate_document(document)
    output.mkdir(parents=True, exist_ok=False)
    (output / "counterexamples.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = document["counts"]
    lines = ["# Greedy 反例挖掘与缩小", "",
             f"输入 {counts['input']} 个；完成精确评估 {counts['exact']} 个；"
             f"发现反例 {counts['failures']} 个；选择 {counts['selected']} 个缩小。", "",
             "按原始相对损失降序选例，同分按集合数、全集大小、成员关系数和输入顺序排序。",
             "仅保持 k 和 G < O；不保持等长、度序列、损失阈值或失败机制。",
             "deletion_minimal 表示所定义的单步删减均不能保留反例，不表示全局最小。",
             "budget_exhausted 表示缩小尚未完成。超过组合上限的输入不作失败判定。",
             "结果经过有目的筛选，不代表随机模型的失效率。", ""]
    for rank, item in enumerate(document["selected"], 1):
        filename = f"counterexample_{rank:03d}.json"
        # Standard project instance format, directly accepted by the replay CLI.
        (output / filename).write_text(json.dumps(item["instance"], ensure_ascii=False, indent=2)
                                       + "\n", encoding="utf-8")
        original = document["inputs"][item["input_index"]]
        before, after = original["evaluation"], item["evaluation"]
        source = original["source"]
        lines.append(f"- [{rank}: 缩小后实例]({filename})："
                     f"来源记录 {source['record']}"
                     f"（{source.get('population', 'input')} / {source.get('case_id', '')}）；"
                     f"(集合数, 全集大小, 成员关系数) {size(original['instance'])} → {size(item['instance'])}；"
                     f"G/O {before['greedy']}/{before['optimum']} → {after['greedy']}/{after['optimum']}；"
                     f"k={item['instance']['k']}；{item['status']}。")
    lines.extend(["", "原始实例、来源、所有评估、Greedy 轨迹、最优见证和删减记录见 "
                  "[counterexamples.json](counterexamples.json)。", ""])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory (must not exist)")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--max-combinations", type=int, default=200000)
    parser.add_argument("--max-evaluations", type=int, default=10000,
                        help="Candidate evaluations per selected instance; zero disables reduction")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output already exists; choose a new directory")
        document = mine(args.input, top=args.top, max_combinations=args.max_combinations,
                        max_evaluations=args.max_evaluations)
        write_outputs(document, args.output)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(document["counts"]))
    print(f"Verified output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
