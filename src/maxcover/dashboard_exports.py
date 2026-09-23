"""Save local comparison snapshots and export their exact selected records."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .comparison import ComparisonSelection, validate_sources
from .comparison_workflows import assemble_snapshot
from .comparison_rendering import render_markdown, render_snapshot, render_svg
from .dashboard_paths import WorkbenchError, data_file
from .dashboard_workbench import WorkbenchService
from .reproducibility import atomic_write_text

_VIEW_ID = re.compile(r"[0-9a-f]{32}\Z")
_FILTERS = {"case", "algorithm", "population", "outcome"}


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


class ComparisonSnapshotStore:
    """File adapter independent of the comparison reader and renderers."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()

    def path(self, view_id: str) -> Path:
        if not _VIEW_ID.fullmatch(view_id):
            raise WorkbenchError("invalid saved comparison id")
        return data_file(self.root, "results/dashboard_views", view_id + ".json")

    def save(self, snapshot: dict[str, Any]) -> None:
        _finite_json(snapshot)
        _check_comparison(snapshot["comparison"])
        if snapshot["comparison"]["total"] != len(snapshot["comparison"]["rows"]):
            raise WorkbenchError("snapshot requires all selected records")
        path = self.path(snapshot["id"])
        content = json.dumps(snapshot, ensure_ascii=False, allow_nan=False) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content)

    def load(self, view_id: str) -> dict[str, Any]:
        try:
            snapshot = json.loads(self.path(view_id).read_text(encoding="utf-8"))
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


class ComparisonExports:
    def __init__(self, project_root: Path) -> None:
        self.workbench = WorkbenchService(project_root)
        self.store = ComparisonSnapshotStore(project_root)

    def _path(self, view_id: str) -> Path:
        return self.store.path(view_id)

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
        try:
            validate_sources(tuple(sources))
            selection = ComparisonSelection(**filters)
        except ValueError as error:
            raise WorkbenchError(str(error)) from error
        analysis = self.workbench.analyze(sources, selection)
        snapshot = assemble_snapshot(analysis, identifier=uuid.uuid4().hex,
                                     saved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     title=title, note=note)
        self.store.save(snapshot)
        return self.get(snapshot["id"])

    def _read(self, view_id: str) -> dict[str, Any]:
        return self.store.load(view_id)

    def list_views(self) -> dict[str, Any]:
        root = self.store.path("0" * 32).parent
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
        try:
            return render_snapshot(snapshot, format_name)
        except ValueError as error:
            raise WorkbenchError(str(error)) from error

    @staticmethod
    def _markdown(snapshot: dict[str, Any]) -> str:
        return render_markdown(snapshot)

    @staticmethod
    def _svg(snapshot: dict[str, Any]) -> str:
        try:
            return render_svg(snapshot)
        except ValueError as error:
            raise WorkbenchError(str(error)) from error
