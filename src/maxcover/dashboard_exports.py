"""Save local comparison snapshots and export their exact selected records."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import uuid
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from .dashboard_workbench import WorkbenchError, WorkbenchService
from .reproducibility import atomic_write_text

_VIEW_ID = re.compile(r"[0-9a-f]{32}\Z")
_FILTERS = {"case", "algorithm", "population", "outcome"}
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


def _finite_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise WorkbenchError("saved comparison contains a non-finite number")
    if isinstance(value, dict):
        for child in value.values():
            _finite_json(child)
    elif isinstance(value, list):
        for child in value:
            _finite_json(child)


def _check_comparison(data: dict[str, Any]) -> None:
    for field in ("input_records", "filtered_records", "total"):
        if type(data.get(field)) is not int or data[field] < 0:
            raise WorkbenchError("saved comparison counts are invalid")
    if not data["total"] <= data["filtered_records"] <= data["input_records"]:
        raise WorkbenchError("saved comparison counts disagree")
    if not all(isinstance(source, str) for source in data["sources"]):
        raise WorkbenchError("saved comparison sources are invalid")
    for row in data["rows"]:
        if not isinstance(row, dict) or not all(isinstance(row.get(field), str) for field in
                ("source", "case_id", "instance_id", "algorithm_id", "population", "status")):
            raise WorkbenchError("saved comparison row is invalid")
        if not isinstance(row.get("selected"), list) or not all(type(index) is int and index >= 0 for index in row["selected"]):
            raise WorkbenchError("saved comparison selected sets are invalid")
    for row in data["summaries"]:
        if not isinstance(row, dict) or not all(isinstance(row.get(field), str) for field in
                ("source", "case_id", "algorithm_id", "population")):
            raise WorkbenchError("saved comparison summary is invalid")
        for field in ("universe_size", "set_count", "k", "records", "gap_records", "missing_gap", "losses", "errors", "timeouts"):
            if type(row.get(field)) is not int or row[field] < 0:
                raise WorkbenchError("saved comparison summary counts are invalid")
        for field in ("loss_rate", "mean_gap", "max_gap"):
            if field not in row or (row[field] is not None and
                    (type(row[field]) not in (int, float) or not 0 <= row[field] <= 1)):
                raise WorkbenchError("saved comparison gap summary is invalid")
        if not row["losses"] <= row["gap_records"] <= row["records"] or row["missing_gap"] != row["records"] - row["gap_records"]:
            raise WorkbenchError("saved comparison summary denominators disagree")
    if sum(row["records"] for row in data["summaries"]) != data["filtered_records"]:
        raise WorkbenchError("saved comparison summary total disagrees")


class ComparisonExports:
    def __init__(self, project_root: Path) -> None:
        self.workbench = WorkbenchService(project_root)

    def _path(self, view_id: str) -> Path:
        if not _VIEW_ID.fullmatch(view_id):
            raise WorkbenchError("invalid saved comparison id")
        return self.workbench._file("results/dashboard_views", view_id + ".json")

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) - {"title", "note", "sources", "filters"}:
            raise WorkbenchError("unknown saved comparison field")
        title, note = payload.get("title", ""), payload.get("note", "")
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise WorkbenchError("title must contain 1 to 120 characters")
        if not isinstance(note, str) or len(note) > 4000:
            raise WorkbenchError("note must contain at most 4000 characters")
        sources, filters = payload.get("sources"), payload.get("filters", {})
        if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
            raise WorkbenchError("sources must be a list of source paths")
        if not isinstance(filters, dict) or set(filters) - _FILTERS or not all(isinstance(value, str) for value in filters.values()):
            raise WorkbenchError("invalid comparison filters")
        result = self.workbench.compare(sources, include_all=True, **filters)
        # Save the actual selected rows, not a path-only view that changes when
        # the input file is replaced. All files stay in ignored local results.
        snapshot: dict[str, Any] = {"id": uuid.uuid4().hex, "title": title.strip(), "note": note,
                    "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "filters": {"case": "", "algorithm": "", "population": "research", "outcome": "all", **filters},
                    "comparison": result}
        path = self._path(snapshot["id"])
        content = json.dumps(snapshot, ensure_ascii=False, allow_nan=False) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content)
        return self.get(snapshot["id"])

    def _read(self, view_id: str) -> dict[str, Any]:
        try:
            snapshot = json.loads(self._path(view_id).read_text(encoding="utf-8"))
            _finite_json(snapshot)
            if (not isinstance(snapshot, dict) or snapshot.get("id") != view_id
                    or not isinstance(snapshot.get("title"), str)
                    or not isinstance(snapshot.get("note"), str)
                    or not isinstance(snapshot.get("saved_at"), str)
                    or not isinstance(snapshot.get("filters"), dict)):
                raise WorkbenchError("invalid saved comparison document")
            data = snapshot["comparison"]
            if (not isinstance(data, dict) or not isinstance(data.get("rows"), list)
                    or not isinstance(data.get("summaries"), list) or not isinstance(data.get("sources"), list)
                    or data.get("total") != len(data["rows"])):
                raise WorkbenchError("saved comparison records are inconsistent")
            _check_comparison(data)
            return snapshot
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise WorkbenchError(f"Cannot read saved comparison {view_id}: {error}") from error

    def list_views(self) -> dict[str, Any]:
        root = self.workbench._file("results/dashboard_views", "index.json").parent
        views = []
        if root.is_dir():
            for path in sorted(root.glob("*.json"), reverse=True):
                if not _VIEW_ID.fullmatch(path.stem):
                    continue
                try:
                    snapshot = self._read(path.stem)
                    views.append({key: snapshot[key] for key in ("id", "title", "saved_at")} | {
                        "sources": snapshot["comparison"]["sources"], "total": snapshot["comparison"]["total"],
                        "error": None})
                except WorkbenchError as error:
                    views.append({"id": path.stem, "error": str(error)})
        views.sort(key=lambda view: view.get("saved_at", ""), reverse=True)
        return {"views": views}

    def get(self, view_id: str) -> dict[str, Any]:
        snapshot = self._read(view_id)
        data = snapshot["comparison"]
        return {**snapshot, "comparison": {**data, "rows": data["rows"][:50]},
                "preview_records": min(50, len(data["rows"]))}

    def artifact(self, view_id: str, format_name: str) -> tuple[bytes, str, str]:
        if format_name not in {"csv", "md", "svg", "json"}:
            raise WorkbenchError("unsupported comparison export format")
        snapshot = self._read(view_id)
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
            return self._markdown(snapshot).encode("utf-8"), "text/markdown; charset=utf-8", filename
        return self._svg(snapshot).encode("utf-8"), "image/svg+xml; charset=utf-8", filename

    @staticmethod
    def _markdown(snapshot: dict[str, Any]) -> str:
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

    @staticmethod
    def _svg(snapshot: dict[str, Any]) -> str:
        summaries = snapshot["comparison"]["summaries"]
        rows = [row for row in summaries if row["mean_gap"] is not None]
        if not rows:
            raise WorkbenchError("this saved comparison has no mean gaps to plot")
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
