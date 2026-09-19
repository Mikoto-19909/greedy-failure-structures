"""Read saved R2/R3/R4 artifacts without running or revalidating research.

CSV values are returned verbatim. Preview limits affect presentation only;
complete files remain downloadable, and saved verification is historical.
"""

from __future__ import annotations

import csv
import json
import os
import stat
from http import HTTPStatus
from pathlib import Path
from typing import Any


PREVIEW_LIMIT = 200
NOTICE = "只读展示已有产物；运行、原图验证和派生验证分别记录。历史 passed 不表示本轮重新验证。"
_VERSIONS = {
    "r2-budget-v1": "r2", "r3-first-step-confirm-v1": "r3",
    "r4-prefix-bound-v1": "r4", "r4-l5-dual-v1": "r4_dual",
}
_LABELS = {"r2": "R2 预算扫描", "r3": "R3 配对确认", "r4": "R4 前缀上界",
           "r4_dual": "R4 DUAL 比较", "unknown": "未识别专题"}
_TABLES = {
    "r2": ("cell_summary.csv", "mechanism_summary.csv", "budget_results.csv"),
    "r3": ("base_graph_summary.csv", "endpoint_results.csv"),
    "r4": ("cell_summary.csv", "budget_results.csv"),
    "r4_dual": ("cell_summary.csv", "budget_results.csv"),
}
_STATUSES = ("run_status", "verification", "summary_verification", "analysis_status")
_DOCUMENTS = ("primary_summary.json", "report_facts.json", "config.json", "analysis_timing.json")
_REPORTS = ("report.md", "report.zh-CN.md", "README.md")
_FILES = frozenset(name for names in _TABLES.values() for name in names) | frozenset(
    (*_DOCUMENTS, *_REPORTS, *(name + ".json" for name in _STATUSES)))
_NOTES = {
    "r2": ["统计单位是独立原图；同一原图的多个预算记录相关，不能当成独立样本。",
           "展示保存的精确失效率区间和原图级 bootstrap 逐点区间，不重新计算或作事后挑峰推断。",
           "机制诊断表可能只覆盖预定子样本，不能代替全部原图的分母。"],
    "r3": ["统计单位是独立原图；每图四个端点，先计算两链平均后的 high−low 差值。",
           "primary_summary.json 的 n 是原图数，endpoints 是端点数；保留原主估计和区间。",
           "比较对象是两种构造协议，不将结果解释为 E0 的因果效应。"],
    "r4": ["固定语料描述与认证；同一原图跨预算配对，不增加独立样本数。",
           "G/U 是近似比下界；U>G 仅表示当前界未认证最优，不能据此判定 Greedy 失效。",
           "前缀基线 U=G 当且仅当 U_initial=G；保留原有均值、中位数和 nearest-rank P90。"],
    "r4_dual": ["固定语料上的初始界、前缀界与 DUAL 界配对比较，属于描述性结果。",
                "G/U 是近似比下界；U>G 不证明 Greedy 失效。",
                "独立证书检查与派生一致性检查分别展示；已发布参考的来源/见证核对不等于重新穷举最优值。"],
}


class StudiesError(ValueError):
    status = HTTPStatus.BAD_REQUEST


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0)
                                     & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 16 * 1024 * 1024:
        raise StudiesError("JSON exceeds the 16 MiB display limit; download the original file")
    with path.open(encoding="utf-8-sig") as handle:
        value = json.load(handle, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise StudiesError("expected a JSON object")
    return value


def _columns(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        columns = next(csv.reader(handle, strict=True), [])
    if not columns or any(not name.strip() for name in columns) or len(set(columns)) != len(columns):
        raise StudiesError("CSV requires nonempty, unique column names")
    return columns


class StudiesService:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()

    def _path(self, source: str, filename: str | None = None) -> Path:
        if not isinstance(source, str) or "\x00" in source or ":" in source or "\\" in source:
            raise StudiesError("source must be a relative path under results/ or experiments/")
        relative = Path(source)
        if (relative.is_absolute() or not relative.parts or relative.parts[0] not in {"results", "experiments"}
                or ".." in relative.parts or source != relative.as_posix()):
            raise StudiesError("source must be a relative path under results/ or experiments/")
        if filename is not None and filename not in _FILES:
            raise StudiesError("unsupported study artifact")
        path = self.root / relative
        if filename is not None:
            path /= filename
        for candidate in (path, *path.parents):
            if candidate == self.root:
                break
            if candidate.exists() or candidate.is_symlink():
                if _linked(candidate):
                    raise StudiesError("linked or reparse data paths are not supported")
        try:
            path.resolve().relative_to(self.root / relative.parts[0])
        except ValueError as error:
            raise StudiesError("source escapes its data directory") from error
        return path

    def _description(self, source: str) -> dict[str, Any]:
        directory = self._path(source)
        if not directory.is_dir():
            raise StudiesError("study source directory does not exist")
        files, errors = [], []
        for name in sorted(_FILES):
            try:
                if self._path(source, name).is_file():
                    files.append(name)
            except (OSError, ValueError) as error:
                errors.append({"file": name, "error": str(error)})
        kind = "unknown"
        if "config.json" in files:
            try:
                version = _json(self._path(source, "config.json")).get("version", "")
                if isinstance(version, str):
                    kind = _VERSIONS.get(version.removesuffix("-fixture"), "unknown")
            except (OSError, ValueError) as error:
                errors.append({"file": "config.json", "error": str(error)})
        if kind == "unknown" and {"endpoint_results.csv", "base_graph_summary.csv"} & set(files):
            kind = "r3"
        if kind == "unknown" and "budget_results.csv" in files:
            try:
                columns = set(_columns(self._path(source, "budget_results.csv")))
                if {"dual_upper", "prefix_upper"} <= columns:
                    kind = "r4_dual"
                elif {"upper", "initial_upper"} <= columns:
                    kind = "r4"
                elif {"base_graph_id", "k", "greedy", "optimum", "relative_gap"} <= columns:
                    kind = "r2"
            except (OSError, ValueError, csv.Error) as error:
                errors.append({"file": "budget_results.csv", "error": str(error)})
        if kind == "unknown":
            errors.append({"file": source, "error": "no recognized R2/R3/R4 schema"})
        return {"source": source, "kind": kind, "label": _LABELS[kind], "title": _LABELS[kind],
                "statistical_unit": "独立原图（预算记录或端点不能替代原图数）",
                "files": files, "source_files": files, "errors": errors,
                "error": "; ".join(item["error"] for item in errors) or None}

    def library(self) -> dict[str, Any]:
        sources = []
        for name in ("results", "experiments"):
            base = self.root / name
            if not base.is_dir() or _linked(base):
                continue
            for directory, children, files in os.walk(base, followlinks=False):
                here = Path(directory)
                children[:] = sorted(child for child in children if not child.startswith(".")
                                     and child != "graphs" and not _linked(here / child))
                markers = {"budget_results.csv", "endpoint_results.csv", "base_graph_summary.csv"}
                if not (markers & set(files) or "config.json" in files):
                    continue
                source = here.relative_to(self.root).as_posix()
                try:
                    entry = self._description(source)
                    if entry["kind"] != "unknown" or markers & set(files):
                        sources.append(entry)
                        children[:] = []
                except (OSError, ValueError) as error:
                    sources.append({"source": source, "kind": "unknown", "label": "不可读取专题",
                                    "error": str(error)})
        return {"sources": sorted(sources, key=lambda item: item["source"]), "notice": NOTICE}

    def _table(self, source: str, filename: str) -> dict[str, Any]:
        result: dict[str, Any] = {"name": filename, "columns": [], "rows": [], "total": None,
                                  "shown": 0, "truncated": False, "limit": PREVIEW_LIMIT, "error": None}
        try:
            path = self._path(source, filename)
            columns = _columns(path)
            rows: list[dict[str, str]] = []
            total = 0
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, strict=True)
                next(reader)
                for values in reader:
                    if len(values) != len(columns):
                        raise StudiesError(f"CSV row {reader.line_num} has a different width from the header")
                    total += 1
                    if len(rows) < PREVIEW_LIMIT:
                        rows.append(dict(zip(columns, values)))
            result.update(columns=columns, rows=rows, total=total, shown=len(rows), truncated=total > len(rows))
        except (OSError, ValueError, csv.Error) as error:
            result["error"] = str(error)
        return result

    def _document(self, source: str, filename: str) -> dict[str, Any]:
        result: dict[str, Any] = {"name": filename, "present": False, "data": None,
                                  "error": None, "omitted_fields": []}
        try:
            path = self._path(source, filename)
            if path.is_file():
                result["present"] = True
                value = _json(path)
                # Per-graph records and expanded frozen designs belong in the
                # original download, not a several-thousand-entry status card.
                omitted = [key for key in ("graphs", "tasks", "source_design") if key in value]
                result.update(data={key: item for key, item in value.items() if key not in omitted},
                              omitted_fields=omitted)
        except (OSError, ValueError) as error:
            result["error"] = str(error)
        return result

    def detail(self, source: str) -> dict[str, Any]:
        result = self._description(source)
        if result["kind"] == "unknown" and not result["files"]:
            raise StudiesError("no recognized study artifacts in source")
        tables = [self._table(source, name) for name in _TABLES.get(result["kind"], ())]
        documents = [self._document(source, name) for name in _DOCUMENTS if name in result["files"]]
        statuses = {name: self._document(source, name + ".json") for name in _STATUSES}
        errors = list(result["errors"])
        for artifact in [*tables, *documents, *statuses.values()]:
            if artifact["error"]:
                failure = {"file": artifact["name"], "error": artifact["error"]}
                if failure not in errors:
                    errors.append(failure)
        result.update(tables=tables, documents=documents, statuses=statuses,
                      notes=_NOTES.get(result["kind"], []), errors=errors, notice=NOTICE)
        return result

    def artifact(self, source: str, filename: str) -> tuple[bytes, str]:
        path = self._path(source, filename)
        description = self._description(source)
        if filename not in description["source_files"]:
            raise StudiesError("study artifact does not exist")
        media = {".csv": "text/csv; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".md": "text/markdown; charset=utf-8"}
        try:
            return path.read_bytes(), media[path.suffix]
        except OSError as error:
            raise StudiesError(str(error)) from error
