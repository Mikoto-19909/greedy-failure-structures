"""Pure renderers shared by in-memory analyses and saved comparisons.

Input is a complete, validated comparison snapshot. Source loading, snapshot
validation and persistence remain caller responsibilities.
"""
from __future__ import annotations

import csv
import io
import json
from html import escape
from typing import Any

_CSV_FIELDS = (
    "source", "config_hash", "case_id", "instance_id", "run_id", "repetition", "seed",
    "population", "family", "universe_size", "set_count", "k", "parameters",
    "algorithm_id", "algorithm", "algorithm_options", "coverage", "optimum",
    "optimality_gap", "runtime_seconds", "status", "selected", "error_message",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _percent(value: Any) -> str:
    return "—" if value is None else f"{100 * value:.4f}%"


def _md(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").replace("<", "&lt;")


def render_snapshot(snapshot: dict[str, Any], format_name: str) -> tuple[bytes, str, str]:
    if format_name not in {"csv", "md", "svg", "json"}:
        raise ValueError("unsupported comparison export format")
    view_id = snapshot["id"]
    filename = f"comparison-{view_id[:8]}.{format_name}"
    if format_name == "json":
        return json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8", filename
    if format_name == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in snapshot["comparison"]["rows"]:
            values = {field: _text(row.get(field)) for field in _CSV_FIELDS}
            # Preserve decimal seed strings. Protect spreadsheet text cells
            # from formulas while retaining numeric metric columns as numbers.
            for field, value in values.items():
                if isinstance(row.get(field), str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                    values[field] = "'" + value
            writer.writerow(values)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", filename
    if format_name == "md":
        return render_markdown(snapshot).encode("utf-8"), "text/markdown; charset=utf-8", filename
    return render_svg(snapshot).encode("utf-8"), "image/svg+xml; charset=utf-8", filename


def render_markdown(snapshot: dict[str, Any]) -> str:
    data = snapshot["comparison"]
    lines = [f"# {_md(snapshot['title'])}", "", f"保存时间：{snapshot['saved_at']}", "",
             "这份摘要来自保存时的完整输入；再次下载不会重新读取或计算源实验。", "",
             "## 来源与筛选", ""]
    lines.extend(f"- {_md(source)}" for source in data["sources"])
    lines.extend(["", "筛选：" + _md(json.dumps(snapshot["filters"], ensure_ascii=False)), "",
                  f"输入 {data['input_records']} 条；汇总范围 {data['filtered_records']} 条；明细导出 {data['total']} 条。", "",
                  "明细结果筛选不改变汇总分母。CSV 是本工作台规范化筛选记录，不是原始 benchmark CSV。", "",
                  "## 描述性结果", "",
                  "| 来源 / 案例 / 算法 / 样本 | n,m,k | 记录 | 可用损失 | 失效数 | 失效比例 | 平均损失 | 最大损失 |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"])
    for row in data["summaries"]:
        label = " / ".join(str(row[key]) for key in ("source", "case_id", "algorithm_id", "population"))
        lines.append(f"| {_md(label)} | {row['universe_size']},{row['set_count']},{row['k']} | {row['records']} | {row['gap_records']} | {row['losses']} | {_percent(row['loss_rate'])} | {_percent(row['mean_gap'])} | {_percent(row['max_gap'])} |")
    lines.extend(["", "## 研究备注", "", snapshot["note"].replace("<", "&lt;") or "未填写。", "",
                  "## 解释边界", "",
                  "各来源与样本类型分别汇总；重复来源不能当作新增独立样本。这里不进行配对推断、显著性检验或因果解释。",
                  "缺失参考不算零损失；功能夹具与筛选反例不能用于估计总体失效率。保存视图不等同独立研究验证或证据发布。", ""])
    return "\n".join(lines)

def render_svg(snapshot: dict[str, Any]) -> str:
    summaries = snapshot["comparison"]["summaries"]
    rows = [row for row in summaries if row["mean_gap"] is not None]
    if not rows:
        raise ValueError("this saved comparison has no mean gaps to plot")
    width, left, plot_width, top, row_height = 1200, 620, 470, 108, 55
    height = top + len(rows) * row_height + 105
    maximum = max(.01, max(row["mean_gap"] for row in rows))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="Arial, Microsoft YaHei, sans-serif" fill="#172133">',
             f'<text x="28" y="30" font-size="20">{escape(snapshot["title"][:70])}</text>',
             '<text x="28" y="55" font-size="13">各组平均相对损失（%）；分组：来源 / 案例 / 算法 / 样本；描述性均值</text>',
             f'<text x="28" y="78" font-size="12">来源：保存的比较 {escape(snapshot["id"][:8])} · {escape(snapshot["saved_at"])}</text>']
    for index, row in enumerate(rows):
        y = top + index * row_height
        source = row["source"]
        label = " / ".join(str(row[key]) for key in ("case_id", "algorithm_id", "population"))
        # Split long source labels across two lines, keeping the full label
        # in the accessible title and the paired Markdown/JSON exports.
        parts.extend([f'<g><title>{escape(source + " / " + label)}</title>',
                      f'<text x="28" y="{y + 4}" font-size="11">{escape(source[:82])}</text>',
                      f'<text x="28" y="{y + 20}" font-size="12">{escape(label[:78])}</text>',
                      f'<rect x="{left}" y="{y - 7}" width="{row["mean_gap"] / maximum * plot_width:.3f}" height="19" fill="#416f9e"/>',
                      f'<text x="{left + plot_width + 12}" y="{y + 7}" font-size="12">{100 * row["mean_gap"]:.4f}%</text></g>'])
    y = top + len(rows) * row_height
    parts.append(f'<line x1="{left}" x2="{left + plot_width}" y1="{y}" y2="{y}" stroke="#8a96a4"/>')
    for fraction in (0, .25, .5, .75, 1):
        x = left + fraction * plot_width
        parts.append(f'<text x="{x}" y="{y + 20}" font-size="11" text-anchor="middle">{100 * maximum * fraction:.3f}</text>')
    parts.extend([f'<text x="{left}" y="{y + 44}" font-size="13">平均相对损失（%）</text>',
                  f'<text x="28" y="{height - 18}" font-size="11">仅绘制有可用均值的分组；完整来源、分母、筛选和限制见同次保存的 Markdown / JSON。</text>',
                  '</g></svg>'])
    return "".join(parts)
