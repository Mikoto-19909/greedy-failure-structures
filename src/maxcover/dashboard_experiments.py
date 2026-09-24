"""Local experiment annotations and editable copies of benchmark configurations."""
from __future__ import annotations

from contextlib import closing
import hashlib
from http import HTTPStatus
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Any
import uuid
import warnings

from .benchmark import plan_benchmark
from .config import parse_config
from .dashboard_jobs import JobConflictError, _FileLock
from .dashboard_workbench import WorkbenchService
from .reproducibility import config_hash


class ExperimentsConflictError(ValueError):
    status = HTTPStatus.CONFLICT


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{label} must be text of at most {maximum} characters")
    return value


def _json(text: str, maximum: int = 1_000_000) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError(f"nonfinite JSON number: {value}")

    value = json.loads(_text(text, "config text", maximum), object_pairs_hook=pairs, parse_constant=constant)
    # Reject overflowed float literals too; parse_config then enforces the schema.
    json.dumps(value, allow_nan=False)
    if not isinstance(value, dict):
        raise ValueError("configuration must be a JSON object")
    return value


def _revision(raw: bytes) -> str:
    # Optimistic editing token, unrelated to the normalized experiment identity.
    return hashlib.sha256(raw).hexdigest()


_GUIDED_FIELDS = ("universe_size", "set_count", "k", "density")
_GUIDED_ALGORITHMS = {"greedy", "lazy_greedy", "brute_force"}


def _guided_form(data: dict[str, Any]) -> dict[str, Any]:
    """Describe raw supported fields without normalizing legacy configurations."""
    reason = ""
    cases, algorithms = data.get("cases"), data.get("algorithms")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 3:
        reason = "当前格式不是版本 3，请使用完整配置编辑。"
    elif not isinstance(cases, list) or len(cases) != 1 or not isinstance(cases[0], dict):
        reason = "表单只支持一个数据组，请使用完整配置编辑。"
    elif cases[0].get("family") != "uniform" or "sweep" in cases[0]:
        reason = "表单只支持无参数扫描的均匀随机数据组，请使用完整配置编辑。"
    elif any(key not in cases[0] for key in _GUIDED_FIELDS):
        reason = "数据组缺少表单字段，请使用完整配置编辑。"
    elif not isinstance(algorithms, list) or not algorithms or any(
        not isinstance(item, dict) or not isinstance(item.get("name"), str)
        or item["name"] not in _GUIDED_ALGORITHMS for item in algorithms
    ):
        reason = "表单只支持贪心、惰性贪心和穷举，请使用完整配置编辑。"
    if reason:
        return {"supported": False, "reason": reason}
    return {"supported": True, "reason": "单组均匀随机配置；其他字段保持原值。",
            "case": {key: str(data["cases"][0][key]) for key in _GUIDED_FIELDS},
            "algorithms": [{"name": item["name"], "id": item.get("id", item["name"]),
                            "enabled": item.get("enabled", True)} for item in data["algorithms"]]}


def _apply_guided(data: dict[str, Any], guided: Any) -> None:
    description = _guided_form(data)
    if not description["supported"]:
        raise ValueError(description["reason"])
    if not isinstance(guided, dict) or set(guided) != {"case", "enabled"}:
        raise ValueError("guided requires case and enabled")
    values, enabled = guided["case"], guided["enabled"]
    if not isinstance(values, dict) or set(values) != set(_GUIDED_FIELDS):
        raise ValueError("guided case requires universe_size, set_count, k and density")
    if (not isinstance(enabled, list) or len(enabled) != len(data["algorithms"])
            or any(type(value) is not bool for value in enabled)):
        raise ValueError("guided enabled requires one boolean per existing algorithm")
    for key in _GUIDED_FIELDS:
        value = _text(values[key], key, 100)
        if key != "density" and not re.fullmatch(r"-?\d+", value, flags=re.ASCII):
            raise ValueError(f"{key} must be integer text")
        data["cases"][0][key] = float(value) if key == "density" else int(value)
    for item, flag in zip(data["algorithms"], enabled):
        item["enabled"] = flag


def _changes(before: Any, after: Any, path: str = "$") -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child = f"{path}[{json.dumps(key, ensure_ascii=False)}]"
            if key not in before or key not in after:
                result.append({"path": child, "before": json.dumps(before[key], ensure_ascii=False) if key in before else "(absent)",
                               "after": json.dumps(after[key], ensure_ascii=False) if key in after else "(absent)"})
            else:
                result.extend(_changes(before[key], after[key], child))
    elif isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before) or index >= len(after):
                result.append({"path": child, "before": json.dumps(before[index], ensure_ascii=False) if index < len(before) else "(absent)",
                               "after": json.dumps(after[index], ensure_ascii=False) if index < len(after) else "(absent)"})
            else:
                result.extend(_changes(before[index], after[index], child))
    elif before != after or type(before) is not type(after):
        result.append({"path": path, "before": json.dumps(before, ensure_ascii=False),
                       "after": json.dumps(after, ensure_ascii=False)})
    return result


class ExperimentsService:
    def __init__(self, project_root: Path) -> None:
        self.root = Path(os.path.abspath(project_root))
        self.workbench = WorkbenchService(self.root)

    def _path(self, relative: str) -> Path:
        parsed = Path(relative)
        if (not relative or parsed.is_absolute() or ".." in parsed.parts
                or relative != parsed.as_posix() or ":" in relative):
            raise ValueError("path must be a plain relative project path")
        for item in (self.root, *(self.root.joinpath(*parsed.parts[:i]) for i in range(1, len(parsed.parts) + 1))):
            try:
                info = item.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("linked local paths are not supported")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError("local paths must be ordinary files or directories")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("hard-linked local files are not supported")
        return self.root / parsed

    def _config(self, relative: Any) -> Path:
        name = _text(relative, "config path", 1000)
        path = self._path("configs/" + name)
        if path.suffix != ".json" or not path.is_file():
            raise ValueError("config must be an existing JSON file under configs/")
        return path

    def _source(self, source: Any) -> str:
        name = _text(source, "source", 1000)
        if name.split("/")[0] not in {"results", "experiments"}:
            raise ValueError("experiment source must be under results/ or experiments/")
        if not any(self._path(name + "/" + filename).is_file() for filename in ("raw_results.csv", "paths.jsonl")):
            raise ValueError("experiment source must contain benchmark or R1 records")
        self.workbench._read(name, include_raw=False)
        return name

    def _database(self, create: bool = False) -> Path:
        directory = self._path("results/.dashboard_local")
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        path = self._path("results/.dashboard_local/experiments.sqlite3")
        for suffix in ("-journal", "-wal", "-shm"):
            self._path("results/.dashboard_local/experiments.sqlite3" + suffix)
        return path

    def annotations(self) -> dict[str, Any]:
        path = self._database()
        if not path.exists():
            return {"annotations": {}, "themes": [], "tags": []}
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)) as connection:
                rows = connection.execute("SELECT source, theme, tags, notes, revision FROM experiments").fetchall()
            annotations = {}
            for source, theme, encoded, notes, revision in rows:
                tags = json.loads(encoded)
                self._validate_annotation({"source": source, "theme": theme, "tags": tags, "notes": notes,
                                           "expected_revision": revision}, check_source=False)
                annotations[source] = {"source": source, "theme": theme, "tags": tags, "notes": notes, "revision": revision}
            return {"annotations": annotations, "themes": sorted({item["theme"] for item in annotations.values() if item["theme"]}),
                    "tags": sorted({tag for item in annotations.values() for tag in item["tags"]})}
        except (sqlite3.Error, OSError, TypeError, ValueError) as error:
            raise ValueError(f"Cannot read experiment annotations: {error}") from error

    def _validate_annotation(self, payload: dict[str, Any], *, check_source: bool = True) -> None:
        if set(payload) != {"source", "theme", "tags", "notes", "expected_revision"}:
            raise ValueError("annotation requires source, theme, tags, notes and expected_revision")
        if check_source:
            self._source(payload["source"])
        else:
            _text(payload["source"], "source", 1000)
        _text(payload["theme"], "theme", 120)
        _text(payload["notes"], "notes", 10000)
        tags = payload["tags"]
        if not isinstance(tags, list) or len(tags) > 30:
            raise ValueError("tags must be a list of at most 30 labels")
        for tag in tags:
            if not _text(tag, "tag", 80).strip():
                raise ValueError("tags must not be empty")
        if type(payload["expected_revision"]) is not int or payload["expected_revision"] < 0:
            raise ValueError("expected_revision must be a nonnegative integer")

    def set_annotation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_annotation(payload)
        item = {"source": payload["source"], "theme": payload["theme"].strip(),
                "tags": sorted(set(tag.strip() for tag in payload["tags"])), "notes": payload["notes"],
                "revision": payload["expected_revision"] + 1}
        try:
            with closing(sqlite3.connect(self._database(True), timeout=10)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE IF NOT EXISTS experiments (source TEXT PRIMARY KEY, theme TEXT NOT NULL, tags TEXT NOT NULL, notes TEXT NOT NULL, revision INTEGER NOT NULL)")
                found = connection.execute("SELECT revision FROM experiments WHERE source=?", (item["source"],)).fetchone()
                if (found[0] if found else 0) != payload["expected_revision"]:
                    raise ExperimentsConflictError("experiment annotations changed; reload before saving")
                self._source(item["source"])
                connection.execute("INSERT OR REPLACE INTO experiments VALUES (?, ?, ?, ?, ?)",
                                   (item["source"], item["theme"], json.dumps(item["tags"], ensure_ascii=False), item["notes"], item["revision"]))
        except sqlite3.Error as error:
            raise ValueError(f"Cannot save experiment annotations: {error}") from error
        return item

    def _origin(self, relative: str) -> dict[str, Any] | None:
        match = re.fullmatch(r"local/([0-9a-f]{32})\.json", relative)
        if not match:
            return None
        path = self._path(f"results/.dashboard_local/config_origins/{match[1]}.json")
        if not path.exists():
            return None
        origin = _json(path.read_text(encoding="utf-8"), 2_100_000)
        if set(origin) != {"path", "source", "text"} or origin["path"] != relative or not isinstance(origin["source"], str):
            raise ValueError("invalid local configuration origin")
        _json(origin["text"])
        return origin

    def _preview(self, text: str) -> dict[str, Any]:
        data = _json(text)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            config = parse_config(data)
            plan = plan_benchmark(config)
        return {"text": text, "valid": True, "config_hash": config_hash(config),
                "guided": _guided_form(data),
                "basics": {"name": config.name, "base_seed": str(config.base_seed), "repetitions": str(config.repetitions)},
                "warnings": [str(item.message) for item in captured],
                "plan": {"name": plan.name, "case_ids": list(plan.case_ids), "repetitions": plan.repetitions,
                         "instance_count": plan.instance_count, "algorithm_run_count": plan.algorithm_run_count,
                         "runs_by_algorithm": [{"algorithm": name, "runs": count} for name, count in plan.runs_by_algorithm]}}

    def read_config(self, relative: str) -> dict[str, Any]:
        raw = self._config(relative).read_bytes()
        text = raw.decode("utf-8-sig")
        origin = self._origin(relative)
        try:
            result = self._preview(text)
        except ValueError as error:
            result = {"text": text, "valid": False, "error": str(error), "basics": {}}
        result.update(path=relative, revision=_revision(raw), editable=origin is not None,
                      origin_source=origin["source"] if origin else None)
        return result

    def preview_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not set(payload) <= {"text", "base_path", "basics", "guided"} or "text" not in payload:
            raise ValueError("preview requires text, with optional base_path, basics and guided")
        text = _text(payload["text"], "config text", 1_000_000)
        data = _json(text)
        if "basics" in payload:
            basics = payload["basics"]
            if not isinstance(basics, dict) or set(basics) != {"name", "base_seed", "repetitions"}:
                raise ValueError("basics requires name, base_seed and repetitions")
            data["name"] = _text(basics["name"], "name", 1000)
            for key in ("base_seed", "repetitions"):
                value = _text(basics[key], key, 100)
                if not re.fullmatch(r"-?\d+", value, flags=re.ASCII):
                    raise ValueError(f"{key} must be integer text")
                data[key] = int(value)
        if "guided" in payload:
            _apply_guided(data, payload["guided"])
        if "basics" in payload or "guided" in payload:
            text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        result = self._preview(text)
        result["changes"] = []
        if "base_path" in payload:
            path = self._config(payload["base_path"])
            saved = _json(path.read_text(encoding="utf-8-sig"))
            result["changes"] = _changes(saved, data)
            origin = self._origin(payload["base_path"])
            result["origin_changes"] = _changes(_json(origin["text"]), data) if origin else []
        return result

    def copy_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"source", "expected_revision"}:
            raise ValueError("copy requires source and expected_revision")
        raw = self._config(payload["source"]).read_bytes()
        if payload["expected_revision"] != _revision(raw):
            raise ExperimentsConflictError("template changed; reload before copying")
        self._preview(raw.decode("utf-8-sig"))
        identifier = uuid.uuid4().hex
        relative = f"local/{identifier}.json"
        target = self._path("configs/" + relative)
        origin = self._path(f"results/.dashboard_local/config_origins/{identifier}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        origin.parent.mkdir(parents=True, exist_ok=True)
        with origin.open("x", encoding="utf-8") as handle:
            json.dump({"path": relative, "source": payload["source"], "text": raw.decode("utf-8-sig")}, handle, ensure_ascii=False)
        with target.open("xb") as handle:
            handle.write(raw)
        return self.read_config(relative)

    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"path", "text", "expected_revision"}:
            raise ValueError("save requires path, text and expected_revision")
        path = self._config(payload["path"])
        if self._origin(payload["path"]) is None:
            raise ValueError("only copies created by this workbench can be edited")
        text = _text(payload["text"], "config text", 1_000_000)
        self._preview(text)
        lock_path = self._path("configs/local/.editing.lock")
        try:
            lock = _FileLock(lock_path)
        except (OSError, JobConflictError) as error:
            raise ExperimentsConflictError("another configuration edit is being saved; retry") from error
        temporary: str | None = None
        try:
            path = self._config(payload["path"])
            if payload["expected_revision"] != _revision(path.read_bytes()):
                raise ExperimentsConflictError("configuration changed; reload before saving")
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(text)
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            lock.close()
        return self.read_config(payload["path"])
