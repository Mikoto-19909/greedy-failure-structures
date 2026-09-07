"""Search an explicitly bounded Maximum Coverage domain for a conjecture's counterexample."""
from __future__ import annotations

import argparse
from itertools import permutations, product
import json
from math import comb, perm
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conjecture_spec import parse_design
from mine_counterexamples import evaluate
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_payload


def candidate_pool(domain):
    size = domain["set_size"]
    return tuple(mask for mask in range(1 << domain["universe_size"])
                 if size is None or mask.bit_count() == size)


def search(design):
    design = parse_design(design)
    domain, budget = design["domain"], design["search"]
    n, m, k = domain["universe_size"], domain["set_count"], domain["k"]
    if comb(m, k) > budget["max_combinations"]:
        raise ValueError("exact reference exceeds max_combinations; reduce the domain or raise the limit")
    pool = candidate_pool(domain)
    total = perm(len(pool), m) if domain["unique_sets"] else len(pool) ** m
    candidates = permutations(pool, m) if domain["unique_sets"] else product(pool, repeat=m)
    scanned, eligible, witness = 0, 0, None
    numerator, denominator = design["claim"]["min_ratio"]
    # Budget counts candidates before the frequency filter, so rejection cannot hide unbounded work.
    while scanned < min(total, budget["max_instances"]):
        masks = next(candidates)
        scanned += 1
        maximum = domain["max_frequency"]
        if maximum is not None and any(
            sum(bool(s & (1 << e)) for s in masks) > maximum for e in range(n)
        ):
            continue
        eligible += 1
        instance = MaximumCoverageInstance(n, masks, k)
        result = evaluate(instance, budget["max_combinations"])
        if result["status"] != "exact":
            raise ValueError("exact reference did not complete")
        if result["greedy"] * denominator < result["optimum"] * numerator:
            witness = {"candidate_number": scanned, "instance": instance_payload(instance),
                       "evaluation": result}
            break
    status = ("counterexample_found" if witness is not None else
              "domain_exhausted" if scanned == total else "budget_exhausted")
    return {"schema_version": 1, "design": design, "status": status,
            "counts": {"candidate_space": total, "scanned": scanned, "eligible": eligible,
                       "rejected": scanned - eligible}, "counterexample": witness}


def write_outputs(document, output):
    from validate_conjecture import validate_document
    validate_document(document)
    output.mkdir(parents=True, exist_ok=False)
    (output / "search.json").write_text(json.dumps(document, ensure_ascii=False, indent=2)
                                        + "\n", encoding="utf-8")
    design, counts, status = document["design"], document["counts"], document["status"]
    domain = design["domain"]
    size_text = domain['set_size'] if domain['set_size'] is not None else '不限'
    frequency_text = domain['max_frequency'] if domain['max_frequency'] is not None else '不限'
    numerator, denominator = design["claim"]["min_ratio"]
    lines = [f"# 猜想搜索：{design['name']}", "",
             f"结论要求：G × {denominator} ≥ O × {numerator}。", "",
             f"固定全集大小 {domain['universe_size']}、集合数 {domain['set_count']}、预算 k={domain['k']}；"
             f"集合大小={size_text}；集合不重复={'是' if domain['unique_sets'] else '否'}；"
             f"元素最大覆盖频数={frequency_text}。", "",
             f"状态：`{status}`。候选空间 {counts['candidate_space']}；"
             f"已检查 {counts['scanned']}；满足全部前提并精确评估 {counts['eligible']}；"
             f"频数条件拒绝 {counts['rejected']}。", ""]
    witness = document["counterexample"]
    if witness is not None:
        (output / "counterexample.json").write_text(
            json.dumps(witness["instance"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = witness["evaluation"]
        lines.extend([f"找到满足前提、违反结论的反例：G={result['greedy']}，O={result['optimum']}。",
                      f"Greedy 选择顺序：{result['greedy_selected']}；最优选择：{result['optimum_selected']}。",
                      "[反例实例](counterexample.json) 可用项目 replay 命令重放。"])
    elif status == "domain_exhausted":
        lines.append("已完整检查指定有限域，未发现反例；不推广到其他规模或约束。")
        if not counts["eligible"]:
            lines.append("该域没有满足全部前提的实例，结论仅为空域上的空真，不能作为经验支持。")
    else:
        lines.append("搜索预算已耗尽，指定有限域尚未检查完；当前未发现反例不能说明猜想成立。")
    lines.extend(["", "按集合位掩码升序枚举有序集合列表，保留所有索引排列；平局选择最小索引。",
                  "写出前已独立重算搜索前缀、计数、停止状态和反例。",
                  "[完整设计与结果](search.json)。", ""])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output already exists; choose a new directory")
        design = json.loads(args.design.read_text(encoding="utf-8-sig"))
        document = search(design)
        write_outputs(document, args.output)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")
    print(f"{document['status']}: {document['counts']}")
    print(f"Verified output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
