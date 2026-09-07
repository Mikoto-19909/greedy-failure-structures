"""Exploratory fixed-degree witnesses for E0 and first-step irrecoverability.

This bounded BFS selects examples by outcomes. It is not the R3 confirmation
protocol, a random sample, or an estimator of the protocol effect.
"""
from __future__ import annotations

from collections import Counter, deque
from itertools import combinations
import json
from pathlib import Path

from mine_counterexamples import evaluate, integer
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_from_payload, instance_payload

TARGETS = ("same-e0-flip", "lower-e0-worse", "first-step-flip")


def load_source(path, *, record=1, k=None):
    integer(record, "record", 1)
    with path.open(encoding="utf-8-sig") as handle:
        if path.suffix.lower() == ".jsonl":
            text = next((line for number, line in enumerate(handle, 1) if number == record), None)
            if text is None or not text.strip():
                raise ValueError("record must name a nonempty physical JSONL line")
            document = json.loads(text)
        else:
            if record != 1:
                raise ValueError("single JSON input only supports record=1")
            document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("input must be an instance object")
    data = document.get("instance", document)
    if not isinstance(data, dict):
        raise ValueError("instance must be an object")
    task = data.get("task", {})
    payload = dict(data)
    # R2 graph records hold dimensions in task and evaluate several k values.
    if "universe_size" not in payload and isinstance(task, dict) and "n" in task:
        payload["universe_size"] = task["n"]
    selected_k = k if k is not None else payload.get("k")
    integer(selected_k, "k (use --k for a multi-budget graph)", 1)
    payload.update(k=selected_k)
    payload.setdefault("schema_version", 1)
    payload.setdefault("encoding", "elements")
    instance = instance_from_payload(payload)
    source = {"path": str(path.resolve()), "record": record, "k_override": k,
              **{key: document[key] for key in ("instance_id", "case_id", "population", "seed")
                 if key in document}}
    if isinstance(task, dict) and task:
        source["task"] = task
    return instance, source


def evaluate_r3(instance, limit):
    if instance.universe_size > 64 or instance.set_count > 32:
        raise ValueError("R3 example search supports at most 64 elements and 32 sets")
    degrees = [s.bit_count() for s in instance.sets]
    if len(set(degrees)) != 1:
        raise ValueError("R3 first-step analysis requires equal-sized sets so Greedy first selects index 0")
    result = evaluate(instance, limit)
    if result["status"] != "exact":
        raise ValueError("exact reference exceeds max_combinations")
    forced, selected = -1, None
    for rest in combinations(range(1, instance.set_count), instance.k - 1):
        choice = (0, *rest)
        value = instance.coverage(choice)
        if value > forced:
            forced, selected = value, list(choice)
    frequencies = [sum(bool(s & (1 << a)) for s in instance.sets)
                   for a in range(instance.universe_size)]
    intersections = [(a & b).bit_count() for a, b in combinations(instance.sets, 2)]
    e0 = sum((instance.sets[0] & s).bit_count() for s in instance.sets[1:])
    first_loss = forced < result["optimum"]
    final_failure = result["greedy"] < result["optimum"]
    return {**result, "forced_optimum": forced, "forced_selected": selected,
            "first_step_irrecoverable": first_loss, "final_failure": final_failure,
            "late_failure": final_failure and not first_loss, "e0": e0,
            "row_degrees": degrees, "element_frequencies": frequencies,
            "global_intersection_total": sum(intersections),
            "intersection_profile": [list(pair) for pair in sorted(Counter(intersections).items())],
            "unique_set_count": len(set(instance.sets))}


def switches(masks, n):
    """All legal 2x2 switches, ordered by (row_i,row_j,removed_i,removed_j)."""
    for i, j in combinations(range(len(masks)), 2):
        left = [a for a in range(n) if masks[i] & ~masks[j] & (1 << a)]
        right = [b for b in range(n) if masks[j] & ~masks[i] & (1 << b)]
        for a in left:
            for b in right:
                after = list(masks)
                after[i] ^= (1 << a) | (1 << b)
                after[j] ^= (1 << a) | (1 << b)
                yield [i, j, a, b], tuple(after)


def matches(before, after, settings):
    if before["first_step_irrecoverable"] == after["first_step_irrecoverable"]:
        return False
    if settings["same_optimum"] and before["optimum"] != after["optimum"]:
        return False
    target = settings["target"]
    if target == "same-e0-flip":
        return before["e0"] == after["e0"]
    if target == "lower-e0-worse":
        return ((after["e0"] - before["e0"]) *
                (int(after["first_step_irrecoverable"]) - int(before["first_step_irrecoverable"]))) < 0
    return True


def search_pair(instance, source, *, target="same-e0-flip", same_optimum=False,
                max_states=200, max_switches=10000, max_combinations=200000):
    if target not in TARGETS or type(same_optimum) is not bool:
        raise ValueError("invalid R3 target or same_optimum flag")
    integer(max_states, "max_states", 1)
    integer(max_switches, "max_switches")
    integer(max_combinations, "max_combinations", 1)
    settings = {"target": target, "same_optimum": same_optimum, "max_states": max_states,
                "max_switches": max_switches, "max_combinations": max_combinations}
    original = evaluate_r3(instance, max_combinations)
    nodes = [(instance.sets, None, None)]
    seen, queue = {instance.sets}, deque([0])
    attempted, pair = 0, None
    status = "component_exhausted"
    stop = False
    while queue and not stop:
        parent = queue.popleft()
        for operation, masks in switches(nodes[parent][0], instance.universe_size):
            if attempted == max_switches:
                status, stop = "switch_budget_exhausted", True
                break
            attempted += 1
            if masks in seen:
                continue
            if len(nodes) == max_states:
                status, stop = "state_budget_exhausted", True
                break
            candidate = MaximumCoverageInstance(instance.universe_size, masks, instance.k)
            result = evaluate_r3(candidate, max_combinations)
            seen.add(masks)
            nodes.append((masks, parent, operation))
            index = len(nodes) - 1
            if matches(original, result, settings):
                path = []
                cursor = index
                while nodes[cursor][1] is not None:
                    path.append(nodes[cursor][2])
                    cursor = nodes[cursor][1]
                pair = {"instance": instance_payload(candidate), "evaluation": result,
                        "switches": list(reversed(path))}
                status, stop = "pair_found", True
                break
            queue.append(index)
    return {"schema_version": 1, "purpose": "r3_counterexample_exploration", "source": source,
            "settings": settings, "status": status,
            "counts": {"states": len(nodes), "switches": attempted},
            "original": {"instance": instance_payload(instance), "evaluation": original}, "pair": pair}


def write_outputs(document, output):
    from validate_r3_counterexamples import validate_document
    validate_document(document)
    output.mkdir(parents=True, exist_ok=False)
    (output / "pair.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "original.json").write_text(json.dumps(document["original"]["instance"], ensure_ascii=False, indent=2)
                                         + "\n", encoding="utf-8")
    lines = ["# R3 保度成对反例", "",
             f"搜索目标：`{document['settings']['target']}`；要求 O 相同：{'是' if document['settings']['same_optimum'] else '否'}。",
             f"状态：`{document['status']}`；精确评估状态数 {document['counts']['states']}；"
             f"已检查合法交换 {document['counts']['switches']}。", "",
             "E0 为集合 0 与其他集合的交集总量；O1 为强制保留集合 0 的精确最优值。",
             "首步不可恢复是 O1<O，最终 Greedy 失败是 G<O，两者分别报告。", ""]
    for name, item in (("原始实例", document["original"]), ("配对实例", document["pair"])):
        if item is None:
            continue
        value = item["evaluation"]
        lines.extend([f"## {name}", "",
                      f"E0={value['e0']}，G={value['greedy']}，O={value['optimum']}，O1={value['forced_optimum']}。",
                      f"首步不可恢复={'是' if value['first_step_irrecoverable'] else '否'}；"
                      f"最终失败={'是' if value['final_failure'] else '否'}；"
                      f"首步可恢复但最终失败={'是' if value['late_failure'] else '否'}。",
                      f"逐集合大小：{value['row_degrees']}；逐元素频数：{value['element_frequencies']}。",
                      f"全局交集总量={value['global_intersection_total']}；不同集合数={value['unique_set_count']}；"
                      f"交集大小/对数分布={value['intersection_profile']}。", ""])
    if document["pair"] is not None:
        (output / "counterexample.json").write_text(
            json.dumps(document["pair"]["instance"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines.extend(["每次交换 [i,j,a,b] 把 a 从 Si 移到 Sj，同时把 b 从 Sj 移到 Si。",
                      f"可重放交换路径：{document['pair']['switches']}。", "",
                      "[原始实例](original.json) / [配对实例](counterexample.json)。"])
    elif document["status"] == "component_exhausted":
        lines.append("已穷尽从该原图通过所定义合法交换可达的状态，未找到所选目标；不推广到其他原图。")
    else:
        lines.append("搜索预算耗尽，可达空间尚未检查完；不能据此断言不存在配对实例或交换。")
    lines.extend(["", "只保持全集、集合数、k、索引标签和逐项两侧度数；其他连接性质可能同时改变。",
                  "按结果选出的例子不代表协议效应、独立样本或失效率。",
                  "本工具枚举合法交换并按结局选例，不模拟 F3 的固定长度随机提议协议，",
                  "不执行确认样本、不修改原设计，也不能用一个反例否定协议均值的统计假设。",
                  "[完整搜索设置、来源、独立核验所需结果](pair.json)。", ""])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
