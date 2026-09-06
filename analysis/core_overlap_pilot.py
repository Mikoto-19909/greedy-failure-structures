"""Analyze the fixed core-overlap pilot from its configuration and CSV inputs.

Run from an uninstalled checkout with --config PATH --results DIR --output DIR.
This offline analysis does not run algorithms or change canonical benchmark data.
Matplotlib is needed only when writing the research figure.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from math import comb
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import ALGORITHMS
from maxcover.benchmark_planning import _instances_for_config, _instance_record, _tasks_for_config
from maxcover.config import load_config
from maxcover.contracts import InstanceRecord, RunRecord
from maxcover.model import MaximumCoverageInstance, SolutionStatus
from maxcover.reproducibility import config_hash


# Derived from the normalized configuration prescribed in the checkpoint plan.
EXPECTED_CONFIG_HASH = "593d362a8a5bdcd8dc0366e9d1cb05238c6a07b8cc0c75419691511c53e8e17d"
STRUCTURAL_FIELDS = (
    "pairwise_overlap_mean_jaccard",
    "actual_density",
    "mean_set_size",
    "covered_element_count",
    "coverage_skew_gini",
)


@dataclass(frozen=True)
class PilotData:
    config_hash: str
    rows: tuple[dict[str, Any], ...]


def _read_rows(payload: bytes, fields: tuple[str, ...], filename: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
    if tuple(reader.fieldnames or ()) != fields:
        raise ValueError(f"{filename}: unexpected CSV fields or order")
    rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"{filename}: malformed CSV row")
    return rows


def load_inputs(config_path: Path, results: Path) -> PilotData:
    """Bind and parse the same CSV bytes, then require every planned pair."""
    config = load_config(config_path)
    identifier = config_hash(config)
    if identifier != EXPECTED_CONFIG_HASH:
        raise ValueError("configuration is not the fixed core-overlap pilot")
    payloads = {name: (results / name).read_bytes()
                for name in ("instances.csv", "raw_results.csv")}
    instances = [InstanceRecord.from_csv_row(row) for row in _read_rows(
        payloads["instances.csv"], InstanceRecord.CSV_FIELDS, "instances.csv"
    )]
    runs = [RunRecord.from_csv_row(row) for row in _read_rows(
        payloads["raw_results.csv"], RunRecord.CSV_FIELDS, "raw_results.csv"
    )]
    cases = {case.case_id: (index, case) for index, case in enumerate(config.cases)}
    planned = _instances_for_config(config)
    expected_instances = {(item.case_id, item.repetition): item for item in planned}
    expected_keys = set(expected_instances)
    expected_runs = {(task.instance_id, task.algorithm_id): task.run_id
                     for task in _tasks_for_config(config, identifier, planned)}
    by_key: dict[tuple[str, int], InstanceRecord] = {}
    by_id: dict[str, InstanceRecord] = {}
    generated: dict[str, MaximumCoverageInstance] = {}
    for record in instances:
        key = (record.case_id, record.repetition)
        if record.config_hash != identifier:
            raise ValueError("instances.csv: config_hash mismatch")
        if key not in expected_keys or key in by_key or record.instance_id in by_id:
            raise ValueError("instances.csv: unexpected or duplicate instance identity")
        expected = expected_instances[key]
        if record.to_csv_row() != _instance_record(expected, identifier).to_csv_row():
            raise ValueError("instances.csv: identity or structural metrics differ from the generated instance")
        by_key[key] = record
        by_id[record.instance_id] = record
        generated[record.instance_id] = expected.instance
    if set(by_key) != expected_keys:
        raise ValueError("instances.csv: incomplete planned repetitions")

    algorithms = {algorithm.algorithm_id: algorithm for algorithm in config.algorithms}
    by_run: dict[tuple[str, str], RunRecord] = {}
    run_ids: set[str] = set()
    for record in runs:
        if record.config_hash != identifier or record.instance_id not in by_id:
            raise ValueError("raw_results.csv: config_hash or instance link mismatch")
        key = (record.instance_id, record.algorithm_id)
        if key in by_run or not record.run_id or record.run_id in run_ids:
            raise ValueError("raw_results.csv: duplicate or empty run identity")
        if record.run_id != expected_runs.get(key):
            raise ValueError("raw_results.csv: run identity differs from the execution plan")
        instance = by_id[record.instance_id]
        for field in ("case_id", "repetition", "seed", "family", "universe_size", "set_count", "k", "parameters"):
            if getattr(record, field) != getattr(instance, field):
                raise ValueError(f"raw_results.csv: instance {field} mismatch")
        if record.case != cases[instance.case_id][1].name:
            raise ValueError("raw_results.csv: case name mismatch")
        algorithm = algorithms.get(record.algorithm_id)
        if (algorithm is None or record.algorithm != algorithm.name or record.algorithm_seed is not None):
            raise ValueError("raw_results.csv: unexpected algorithm identity or seed")
        if json.loads(record.algorithm_options) != ALGORITHMS[algorithm.name].option_values(algorithm.options):
            raise ValueError("raw_results.csv: algorithm options mismatch")
        if (record.status not in {SolutionStatus.FEASIBLE, SolutionStatus.OPTIMAL}
                or json.loads(record.algorithm_metadata)["termination"] != "completed"):
            raise ValueError("raw_results.csv: algorithm did not complete successfully")
        if len(record.selected) > record.k or any(index >= record.set_count for index in record.selected):
            raise ValueError("raw_results.csv: invalid selected indices")
        if generated[record.instance_id].coverage(record.selected) != record.coverage:
            raise ValueError("raw_results.csv: selected sets do not match declared coverage")
        by_run[key] = record
        run_ids.add(record.run_id)
    if set(by_run) != {(instance_id, algorithm_id) for instance_id in by_id for algorithm_id in algorithms}:
        raise ValueError("raw_results.csv: each instance needs Greedy and exact_reference")

    paired_rows: list[dict[str, Any]] = []
    for repetition in range(30):
        row: dict[str, Any] = {"config_hash": identifier, "repetition": repetition}
        for role, case in zip(("treatment", "control"), config.cases):
            instance = by_key[(case.case_id, repetition)]
            greedy = by_run[(instance.instance_id, "greedy")]
            exact = by_run[(instance.instance_id, "exact_reference")]
            optimum = exact.coverage
            if exact.status is not SolutionStatus.OPTIMAL or optimum is None or optimum <= 0:
                raise ValueError("exact_reference must prove a positive optimum")
            if greedy.optimum != optimum or exact.optimum != optimum:
                raise ValueError("run optimum differs from the brute-force reference")
            if greedy.coverage is None or greedy.coverage > optimum:
                raise ValueError("Greedy coverage exceeds the reference or is missing")
            row.update({
                f"{role}_case_id": instance.case_id,
                f"{role}_instance_id": instance.instance_id,
                f"{role}_effective_seed": instance.seed,
                f"{role}_greedy_coverage": greedy.coverage,
                f"{role}_exact_optimum": optimum,
                f"{role}_failure": int(greedy.coverage < optimum),
                f"{role}_gap": (optimum - greedy.coverage) / optimum,
                **{f"{role}_{field}": getattr(instance, field) for field in STRUCTURAL_FIELDS},
            })
        if row["treatment_effective_seed"] != row["control_effective_seed"]:
            raise ValueError("paired effective seeds differ")
        paired_rows.append(row)
    return PilotData(identifier, tuple(paired_rows))


def summarize_pairs(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Use pairs as units; retain successful instances in every gap mean."""
    if not rows:
        raise ValueError("paired sample must not be empty")
    counts = {"n00": 0, "n10": 0, "n01": 0, "n11": 0}
    for row in rows:
        treatment, control = row["treatment_failure"], row["control_failure"]
        if treatment not in (0, 1) or control not in (0, 1):
            raise ValueError("failure indicators must be zero or one")
        counts[f"n{treatment}{control}"] += 1
    n = len(rows)
    discordant = counts["n10"] + counts["n01"]
    tail = sum(comb(discordant, i) for i in range(min(counts["n10"], counts["n01"]) + 1))
    p_value = min(1.0, 2 * tail / 2 ** discordant) if discordant else 1.0
    treatment_failures = counts["n10"] + counts["n11"]
    control_failures = counts["n01"] + counts["n11"]
    return {
        **counts, "n": n,
        "treatment_failures": treatment_failures, "control_failures": control_failures,
        "treatment_failure_rate": treatment_failures / n,
        "control_failure_rate": control_failures / n,
        "delta_failure": (counts["n10"] - counts["n01"]) / n,
        "p_two_sided": p_value,
        "treatment_mean_gap": fmean(row["treatment_gap"] for row in rows),
        "control_mean_gap": fmean(row["control_gap"] for row in rows),
        "delta_gap": fmean(row["treatment_gap"] - row["control_gap"] for row in rows),
    }


def structural_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    diagnostics = {}
    for field in STRUCTURAL_FIELDS:
        treatment = [row[f"treatment_{field}"] for row in rows]
        control = [row[f"control_{field}"] for row in rows]
        diagnostics[field] = {
            "treatment_mean": fmean(treatment), "treatment_min": min(treatment), "treatment_max": max(treatment),
            "control_mean": fmean(control), "control_min": min(control), "control_max": max(control),
            "paired_mean_difference": fmean(a - b for a, b in zip(treatment, control)),
        }
    return diagnostics


def conclusion_key(summary: Mapping[str, Any], diagnostics: Mapping[str, Mapping[str, float]]) -> str:
    if diagnostics["pairwise_overlap_mean_jaccard"]["paired_mean_difference"] <= 0:
        return "structure_not_separated"
    if summary["p_two_sided"] >= 0.05:
        return "inconclusive"
    return "positive" if summary["delta_failure"] > 0 else "negative"


def render_chart(summary: Mapping[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    with plt.rc_context({"svg.hashsalt": "core_overlap_pilot_v1", "font.family": "DejaVu Sans"}):
        figure, axis = plt.subplots(figsize=(6, 4), layout="constrained")
        bars = axis.bar(["High overlap", "Uniform control"],
                        [summary["treatment_failure_rate"], summary["control_failure_rate"]],
                        color=["#286788", "#b65d37"], width=0.55)
        axis.set(ylim=(0, 1), ylabel="Greedy failure rate", title="Fixed matched-control pilot")
        for bar, failures in zip(bars, [summary["treatment_failures"], summary["control_failures"]]):
            axis.annotate(f"{failures}/{summary['n']}",
                          (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                          xytext=(0, -14 if bar.get_height() > 0.94 else 5),
                          textcoords="offset points", ha="center")
        figure.savefig(path, metadata={"Date": None})
        plt.close(figure)


def report_text(data: PilotData) -> str:
    summary = summarize_pairs(data.rows)
    diagnostics = structural_diagnostics(data.rows)
    conclusions = {
        "positive": "该固定参数配置下，高重叠处理组失效率较高，配对样本提供方向性证据。",
        "negative": "该固定参数配置下，高重叠处理组失效率较低，观察方向与原假设相反。",
        "inconclusive": "报告上述样本差值；本轮未获得足够的失效率差异证据。",
        "structure_not_separated": "处理组平均 Jaccard 未高于对照，本次处理未形成预期结构差异；保留全部结果。",
    }
    lines = ["# 高重叠结构固定对照实验", "",
             "预定设计：30 个种子对、60 个实例；每个实例运行 Greedy 与穷举参考。",
             "维度为 48 个元素、16 个候选集合、预算 4；配置与种子批次在正式运行前提交。",
             "本分析检查样本配对、完成状态和最优参考，并从实例重算所选集合的覆盖量。",
             "失手由整数覆盖量小于穷举最优值判定；全部零 gap 实例进入辅助均值。", "",
             f"配置哈希：`{data.config_hash}`。", "", "## 结构诊断", "",
             "| 指标 | 处理组均值 [最小, 最大] | 对照组均值 [最小, 最大] | 配对均值差 |",
             "| --- | --- | --- | --- |"]
    for field, values in diagnostics.items():
        lines.append(f"| {field} | {values['treatment_mean']:.10g} [{values['treatment_min']:.10g}, {values['treatment_max']:.10g}] "
                     f"| {values['control_mean']:.10g} [{values['control_min']:.10g}, {values['control_max']:.10g}] "
                     f"| {values['paired_mean_difference']:.10g} |")
    lines += ["", "## 失效率与 gap", "",
              "四格计数的第一位表示处理组，第二位表示对照组；1 为失手。", "",
              "| 指标 | 数值 |", "| --- | --- |"]
    for name in ("n00", "n10", "n01", "n11"):
        lines.append(f"| {name} | {summary[name]} |")
    for role in ("treatment", "control"):
        lines.append(f"| {role} failure rate | {summary[role + '_failures']}/{summary['n']} = {summary[role + '_failure_rate']:.10g} |")
    for name in ("delta_failure", "p_two_sided", "treatment_mean_gap", "control_mean_gap", "delta_gap"):
        lines.append(f"| {name} | {summary[name]:.10g} |")
    lines += ["", "主检验为双侧精确 McNemar，预定 alpha=0.05；辅助 gap 不另作显著性搜索。",
              "抽样单位是种子对。没有方向不一致的配对时 p=1，不能据此证明总体等价。", "",
              "![Greedy failure rates](failure_rate.svg)", "", "## 判断", "",
              conclusions[conclusion_key(summary, diagnostics)], "",
              "结论针对这两种生成机制在固定参数下的比较。理论期望集合大小匹配，",
              "但集合大小分布、实际密度、可覆盖并集和集中程度仍可能变化；上表保留这些诊断。",
              "该比较不能把差异单独归因于重叠度，也不支持强度趋势或向其他规模推广。",
              "完成预定样本后停止，不因方向、p 值或结构诊断追加种子。", ""]
    return "\n".join(lines)


def write_analysis(data: PilotData, output: Path) -> None:
    # Import the optional plotting dependency before creating any output.
    import matplotlib

    if output.exists() and any(output.iterdir()):
        raise ValueError("analysis output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    with (output / "paired_instances.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data.rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(data.rows)
    (output / "report.md").write_text(report_text(data), encoding="utf-8", newline="\n")
    render_chart(summarize_pairs(data.rows), output / "failure_rate.svg")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = load_inputs(args.config, args.results)
        write_analysis(data, args.output)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ImportError) as error:
        print(f"core overlap analysis: {error}", file=sys.stderr)
        return 1
    print(f"PASS: analyzed {len(data.rows)} complete pairs; wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
