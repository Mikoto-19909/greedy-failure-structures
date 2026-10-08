"""Plot saved results and explain two saved examples; never rerun policies."""
import time

START_CPU = time.process_time()

import argparse
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parent
BUDGETS = [1, 2, 4]
COLORS = {"single": "#2769A0", "priced_chain": "#C96C2C"}
POLICIES = {"single": "策略 A：单请求改派", "priced_chain": "策略 B：带代价的链式改派"}
FAMILIES = {"uniform": "均匀布局", "clustered": "局部聚集", "near_far": "远近交替", "paired": "成对间隔"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def aggregate(summary, policy, budget, family="all"):
    return next(row for row in summary["aggregates"] if
                (row["policy"], row["budget"], row["family"]) == (policy, budget, family))


def select(traces, case_id, policy, budget):
    return next(row for row in traces if
                (row["case_id"], row["policy"], row["budget"]) == (case_id, policy, budget))


def costs(trace):
    if trace["policy"] == "prefix_optimum":
        return trace["oracle_costs"]
    return [stage["cost"] for stage in trace["history"]]


def save(fig, folder, name):
    fig.savefig(folder / (name + ".png"), dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(folder / (name + ".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def budget_figure(dev, evaluation, folder):
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), sharey=True)
    for ax, summary, group in zip(axes, [dev, evaluation], ["开发组", "固定比较组"]):
        nearest = aggregate(summary, "nearest", 0)
        optimum = aggregate(summary, "prefix_optimum", None)
        ax.axhline(optimum["reduction_pct"], color="#59636D", lw=1.6, ls=":", label="前缀最优参照")
        for policy, marker in [("single", "o"), ("priced_chain", "s")]:
            yy = [aggregate(summary, policy, b)["reduction_pct"] for b in BUDGETS]
            ax.plot(BUDGETS, yy, marker=marker, ms=7, color=COLORS[policy], lw=2, label=POLICIES[policy])
            for b, value in zip(BUDGETS, yy):
                ax.annotate(f"{value:.2f}%", (b, value), xytext=(0, -19 if policy == "single" else 9),
                            textcoords="offset points", ha="center", fontsize=10, color=COLORS[policy])
        ax.set_title(f"{group}：{nearest['sequences']} 条序列\n不改派阶段成本总和 = {nearest['prefix_sum']}", fontsize=12)
        ax.set_xticks(BUDGETS)
        ax.set_xlabel("每个请求的累计改派上限")
        ax.set_ylim(0, 23)
        ax.grid(axis="y", alpha=.2)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("相对不改派的阶段成本总和降幅（%）")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(.5, -.015))
    fig.suptitle("多给改派次数，是否降低各阶段的总距离？", fontsize=16, fontweight="bold")
    fig.text(.5, .075, "每阶段成本为当时所有请求的距离之和；再对全部阶段和序列求和。两组分别计算，不合并。",
             ha="center", fontsize=10, color="#485460")
    fig.subplots_adjust(top=.79, bottom=.24, wspace=.14)
    save(fig, folder, "01_budget_benefit")


def family_figure(evaluation, folder):
    fig, ax = plt.subplots(figsize=(10.8, 5.5))
    families = list(FAMILIES)
    for policy, offset in [("single", -.18), ("priced_chain", .18)]:
        values = []
        for family in families:
            rows = [aggregate(evaluation, policy, b, family) for b in BUDGETS]
            assert len({r["prefix_sum"] for r in rows}) == 1
            values.append(rows[0]["reduction_pct"])
        bars = ax.bar([i + offset for i in range(len(families))], values, width=.33,
                      color=COLORS[policy], label=POLICIES[policy])
        ax.bar_label(bars, labels=[f"{v:.2f}%" for v in values], padding=4, fontsize=11)
    ax.set_xticks(range(len(families)), [FAMILIES[f] + "\n6 条序列" for f in families])
    ax.set_ylim(0, 34)
    ax.set_ylabel("相对不改派的阶段成本总和降幅（%）")
    ax.set_title("固定比较组：收益集中在哪些布局？\n两策略各自的 1、2、4 次预算结果相同", fontsize=15, pad=18)
    ax.grid(axis="y", alpha=.2)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left")
    fig.text(.5, .025, "均匀与远近交替子集中，不改派已达到每阶段最优；0% 不表示该类所有布局都没有收益。",
             ha="center", fontsize=10, color="#485460")
    fig.subplots_adjust(bottom=.19)
    save(fig, folder, "02_layout_benefit")


def examples_figure(traces, folder):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4))
    configs = [("nearest", 0, "最近空闲点"), ("single", 1, "A1"), ("single", 2, "A2"),
               ("priced_chain", 1, "B1"), ("prefix_optimum", None, "前缀最优")]
    for ax, case_id, title in zip(axes, ["dev_uniform", "dev_budget"],
                                  ["开发例一：一条链移动 5 个不同请求", "开发例二：提前用尽同一请求的预算"]):
        groups = {}
        for policy, budget, label in configs:
            yy = tuple(costs(select(traces, case_id, policy, budget)))
            groups.setdefault(yy, []).append(label)
        for (yy, labels), color, marker in zip(groups.items(), ["#657080", "#2769A0", "#C96C2C", "#53976A"], ["o", "s", "^", "D"]):
            ax.plot(range(1, 7), yy, marker=marker, color=color, lw=2,
                    label=" / ".join(labels) + ("（重合）" if len(labels) > 1 else ""))
            ax.annotate(str(yy[-1]), (6, yy[-1]), xytext=(7, 0), textcoords="offset points", va="center")
        ax.set_title(title, fontsize=12)
        ax.set_xlabel("已到达请求数")
        ax.set_ylabel("当前所有请求的总距离")
        ax.set_xticks(range(1, 7))
        ax.set_xlim(.8, 6.5)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=10, loc="upper left")
    fig.suptitle("两种限制：一次能改几个人，与一个人累计能改几次", fontsize=16, fontweight="bold")
    fig.text(.5, .035, "A1 / A2：单请求策略，预算 1 / 2；B1：带代价的链式策略，预算 1。两例均来自开发组。",
             ha="center", fontsize=10, color="#485460")
    fig.subplots_adjust(top=.79, bottom=.19, wspace=.23)
    save(fig, folder, "03_examples_by_stage")


def examples_report(dev_folder, evaluation_folder, traces):
    report_folder = evaluation_folder
    report_folder.mkdir(exist_ok=True)
    evidence = Path(os.path.relpath(dev_folder, report_folder)).as_posix()
    figure = Path(os.path.relpath(evaluation_folder / "figures/03_examples_by_stage.png", report_folder)).as_posix()
    cases = {case["id"]: case for case in read(dev_folder / "inputs.json")["cases"]}
    text = ["# 两个逐步分配例子", "", "长链例说明一次改变多个不同请求可以有收益；预算耗尽例说明过早追求当前最优可能损害后续阶段。",
            "两例均来自开发组，曾用于理解和选择策略。它们不能作为独立的正式检验。", "",
            "A1、A2 分别表示单请求改派策略的 1 次、2 次预算。B1 表示带代价的链式策略的 1 次预算。",
            "A 每阶段最多改变一个旧请求，选当前总距离最小的合法动作。B 可以改变一条链上的多个旧请求；每个改派的附加代价等于服务点移动距离除以两倍剩余次数。B 按当前总距离加附加代价选择动作。",
            "前缀最优（Prefix optimum）只对已经到达的请求计算最小总距离。首次分配不计改派。", "",
            f"证据：[固定输入]({evidence}/inputs.json)；[逐步记录]({evidence}/traces.json)。下文用 case_id、policy、budget、t 定位记录。", "",
            f"![两个开发例的阶段成本]({figure})", ""]
    configs = [("nearest", 0, "最近空闲点"), ("single", 1, "A1"), ("single", 2, "A2"), ("priced_chain", 1, "B1")]
    for case_id, heading in [("dev_uniform", "例一：给每人一次机会，也可以移动整条链"),
                              ("dev_budget", "例二：第二阶段省下 1，却让后面四个阶段各多花 4")]:
        case = cases[case_id]
        servers = case["servers"]
        requests = [case["requests"][i] for i in case["order"]]
        text += ["## " + heading, "", f"实例编号：`{case_id}`。服务点坐标为 `{servers}`。请求按 `{requests}` 的顺序到达。", "",
                 "下表的分配向量按到达顺序排列。例如 `[0, 10]` 表示第一个请求去坐标 0，第二个请求去坐标 10。", "",
                 "### 各阶段成本", "", "| 阶段 | 新请求坐标 | 最近空闲点 | A1 | A2 | B1 | 前缀最优 |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for t in range(1, 7):
            values = [costs(select(traces, case_id, p, b))[t-1] for p, b, _ in configs]
            oracle = select(traces, case_id, "nearest", 0)["oracle_costs"][t-1]
            text.append("| " + " | ".join(map(str, [t, requests[t-1], *values, oracle])) + " |")
        shown = configs if case_id == "dev_budget" else [configs[0], configs[1], configs[3]]
        for policy, budget, name in shown:
            trace = select(traces, case_id, policy, budget)
            text += ["", f"### {name} 的分配变化", "", f"记录键：`policy={policy}`，`budget={budget}`。", "",
                     "| 阶段 | 按到达顺序的服务点坐标 | 本阶段旧请求的实际改派 | 累计改派总数 |", "| --- | --- | --- | --- |"]
            old = []
            for stage in trace["history"]:
                assignment = stage["assignment"]
                move_text = "<br>".join(f"请求 {i+1}（坐标 {requests[i]}）：{servers[old[i]]}→{servers[assignment[i]]}"
                                     for i in stage["moves"]) or "无"
                positions = [servers[s] for s in assignment]
                text.append(f"| {stage['t']} | `{positions}` | {move_text} | {sum(stage['counts'])} |")
                old = assignment
        if case_id == "dev_uniform":
            text += ["", "**第六阶段，B1 从空闲点开始反向执行 5 次旧请求改派。** 每个旧请求只改一次，随后将新请求直接分配到坐标 0。总距离为 `5×6+1=31`。A1 只能移动一个旧请求，得到 `4×4+6+39=61`。最近空闲点得到 `5×4+49=69`。定位：本例三个策略的 `t=6`。", "",
                     "A2 的六阶段分配与 A1 相同。本例的限制是每阶段只允许移动一个旧请求；增加单人终身预算没有改变这个动作集合。"]
        else:
            text += ["", "**A1 在第二阶段把请求 1 从服务点 3 改到 0。** 当前成本从不改派的 3 降到 2。第三个请求恰好位于 0，但请求 1 已用尽预算。新请求只能去服务点 5，阶段成本变为 7。定位：`policy=single,budget=1,t=2/3`。", "",
                     "A2 在第三阶段再次移动请求 1：服务点 0→5。新请求直接占用 0，阶段成本恢复为 3。B1 在第二阶段没有改派：节省 1 小于其改派代价 1.5。因此第三阶段仍可直接使用服务点 0。定位：`single,budget=2,t=3` 与 `priced_chain,budget=1,t=2/3`。", "",
                     "A1 六阶段成本总和为 37，A2 为 21，B1 与最近空闲点均为 22。A1 比最近空闲点多 15，等于第二阶段节省 1 后在四个阶段各多花 4。这是固定例中的反例，不说明少改派总是更好。"]
        text.append("")
    (report_folder / "分步例子.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", required=True, type=Path)
    parser.add_argument("--dev", required=True, type=Path)
    args = parser.parse_args()
    evaluation_folder, dev_folder = ROOT / args.eval, ROOT / args.dev
    evaluation, dev = read(evaluation_folder / "summary.json"), read(dev_folder / "summary.json")
    eval_traces, dev_traces = read(evaluation_folder / "traces.json"), read(dev_folder / "traces.json")
    assert evaluation["split"] == "eval" and dev["split"] == "dev"
    assert evaluation["source_sha256"] == dev["source_sha256"]
    for summary, traces in [(evaluation, eval_traces), (dev, dev_traces)]:
        for row in summary["aggregates"]:
            selected = [trace for trace in traces if (trace["policy"], trace["budget"]) == (row["policy"], row["budget"])
                        and (row["family"] == "all" or trace["family"] == row["family"])]
            assert sum(sum(costs(trace)) for trace in selected) == row["prefix_sum"]
    font_manager.findfont("Microsoft YaHei", fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei"], "axes.unicode_minus": False,
                         "svg.fonttype": "path", "font.size": 11})
    folder = evaluation_folder / "figures"
    folder.mkdir(exist_ok=True)
    budget_figure(dev, evaluation, folder)
    family_figure(evaluation, folder)
    examples_figure(dev_traces, folder)
    examples_report(dev_folder, evaluation_folder, dev_traces)
    runtime = {"analysis_process_cpu_seconds": time.process_time() - START_CPU,
               "new_sequences": 0, "figures": 3, "formats": ["png", "svg"]}
    (evaluation_folder / "analysis_runtime.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(runtime, ensure_ascii=False))


if __name__ == "__main__":
    main()
