"""Local dashboard frontend for the maximum-coverage experiment engine.

The dashboard deliberately stays small and local.  It is a standard-library
HTTP server that exposes the same configuration, benchmark, report, and replay
functions as the command-line interface.  It does not add a database, a remote
job queue, or a second implementation of the experiment logic.
"""

from __future__ import annotations

import csv
import ipaddress
import json
import os
import re
import socket
import stat
import threading
import warnings
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, ClassVar, Mapping, cast
from urllib.parse import parse_qs, unquote, urlparse

from .algorithms import ALGORITHMS
from .benchmark import REPORT_FILENAMES, plan_benchmark, replay_instance_file
from .config import load_config
from .dashboard_exports import ComparisonExports
from .dashboard_experiments import ExperimentsConflictError, ExperimentsService
from .dashboard_analysis import StudyAnalysisService
from .dashboard_jobs import JobConflictError, JobService
from .dashboard_local import LocalCatalog
from .dashboard_studies import StudiesService
from .dashboard_workbench import WorkbenchService
from .reproducibility import config_hash


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).with_name("dashboard_ui")
_RESULT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_MAX_REQUEST_BYTES = 1_000_000
_JSON_FIELDS = {"parameters", "algorithm_options", "algorithm_metadata"}
_INTEGER_FIELDS = {
    "repetition",
    "seed",
    "universe_size",
    "set_count",
    "k",
    "algorithm_seed",
    "coverage",
    "best_bound",
    "optimum",
    "nodes_or_iterations",
    "runs",
    "timeouts",
}
_FLOAT_FIELDS = {
    "optimality_gap",
    "runtime_seconds",
    "mean_coverage",
    "mean_optimality_gap",
    "max_optimality_gap",
    "mean_runtime_seconds",
}
_BOOLEAN_FIELDS = {"is_exact", "timed_out"}


class DashboardRequestError(ValueError):
    """A client request is invalid and should receive a 400 response."""

    status = HTTPStatus.BAD_REQUEST


class DashboardConflictError(RuntimeError):
    """A valid request conflicts with the current local dashboard state."""

    status = HTTPStatus.CONFLICT


class DashboardForbiddenError(DashboardRequestError):
    """A state-changing request did not come from this dashboard origin."""

    status = HTTPStatus.FORBIDDEN


class DashboardUnsupportedMediaTypeError(DashboardRequestError):
    """A state-changing request used a content type outside the JSON API."""

    status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def _research_browser_numbers(value: object) -> object:
    """Keep seeds and exact search-space counts beyond JavaScript's integer range."""
    if type(value) is int and abs(value) > 9_007_199_254_740_991:
        return str(value)
    if isinstance(value, dict):
        return {key: _research_browser_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_research_browser_numbers(item) for item in value]
    return value


def _safe_child(root: Path, relative: str) -> Path:
    """Resolve a user-provided relative path without escaping ``root``."""

    candidate_text = unquote(relative).strip()
    if not candidate_text:
        raise DashboardRequestError("path must not be empty")
    candidate = Path(candidate_text)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise DashboardRequestError("absolute paths and parent traversal are not allowed")
    # Keep the path used by data guards identical to the object actually read;
    # an internal link must not redirect a read into an active output directory.
    for item in (root, *[root.joinpath(*candidate.parts[:index]) for index in range(1, len(candidate.parts) + 1)]):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise DashboardRequestError("linked data paths are not supported")
    root_resolved = root.resolve()
    resolved = (root_resolved / candidate).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise DashboardRequestError("path must stay inside the project directory") from error
    return resolved


def _result_dir(results_root: Path, name: str) -> Path:
    if not _RESULT_NAME.fullmatch(name):
        raise DashboardRequestError(
            "result name must contain only letters, numbers, dots, underscores, or hyphens"
        )
    path = _safe_child(results_root, name)
    if not path.is_dir():
        raise DashboardRequestError(f"result directory does not exist: {name}")
    return path


def _parse_csv_value(field: str, value: str | None) -> object:
    if value is None or value == "":
        return None
    if field in _JSON_FIELDS:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if field == "selected":
        try:
            return [int(item) for item in value.split()]
        except ValueError:
            return value
    if field in _BOOLEAN_FIELDS:
        return value.lower() == "true"
    if field in _INTEGER_FIELDS:
        try:
            return int(value)
        except ValueError:
            return value
    if field in _FLOAT_FIELDS:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _read_csv(path: Path, *, limit: int | None = None) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows: list[dict[str, object]] = []
        for index, row in enumerate(csv.DictReader(handle)):
            if limit is not None and index >= limit:
                break
            rows.append({field: _parse_csv_value(field, value) for field, value in row.items()})
        return rows


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class DashboardService:
    """Application services used by the HTTP handler and unit tests."""

    def __init__(self, project_root: Path = PROJECT_ROOT) -> None:
        self.project_root = Path(project_root).resolve()
        self.configs_root = self.project_root / "configs"
        self.results_root = self.project_root / "results"
        self._lock = threading.RLock()
        self.workbench = WorkbenchService(self.project_root)
        self.exports = ComparisonExports(self.project_root)
        self.experiments = ExperimentsService(self.project_root)
        self.analysis = StudyAnalysisService(self.project_root)
        self.studies = StudiesService(self.project_root)
        self.local_catalog = LocalCatalog(self.project_root)
        self._index_rebuild_lock = threading.Lock()
        self._research_jobs: JobService | None = None
        self._closed = False

    @property
    def research_jobs(self) -> JobService:
        with self._lock:
            if self._closed:
                raise DashboardConflictError("dashboard service is closed")
            if self._research_jobs is None:
                self._research_jobs = JobService(self.project_root)
            return self._research_jobs

    def close(self) -> None:
        with self._lock:
            self._closed = True
            jobs = self._research_jobs
        if jobs is not None:
            jobs.close()

    def read_artifacts(self, paths: list[str], operation: Callable[[], Any]) -> Any:
        """Hold dispatch coordination until all requested file reads are closed."""
        try:
            with self.research_jobs.reading_outputs(paths):
                return operation()
        except JobConflictError as error:
            raise DashboardConflictError(str(error)) from error
        except ValueError as error:
            if getattr(error, "status", None) is not None:
                raise
            raise DashboardRequestError(str(error)) from error

    def scan_artifacts(self, operation: Callable[[set[str]], Any]) -> Any:
        def scan() -> Any:
            active = {job["output_dir"] for job in self.research_jobs.list_jobs()["jobs"]
                      if job.get("kind") == "benchmark" and job.get("status") == "running"}
            if os.name == "nt" and active and self.results_root.is_dir():
                names = {Path(path).name.casefold() for path in active}
                active.update(path.relative_to(self.project_root).as_posix()
                              for path in self.results_root.iterdir() if path.name.casefold() in names)
            return operation(active)
        return self.read_artifacts([], scan)

    def local_index_status(self) -> dict[str, object]:
        return {"workbench": self.workbench.index.status(), "studies": self.studies.index.status()}

    def rebuild_local_index(self) -> dict[str, object]:
        if not self._index_rebuild_lock.acquire(blocking=False):
            raise DashboardConflictError("the local index is already being rebuilt")
        try:
            self.studies.index.clear()
            result = self.workbench.rebuild_index()
            sources = self.studies.library()["sources"]
            study_errors = []
            for source in sources:
                try:
                    detail = self.studies.detail(source["source"])
                    if detail["errors"]:
                        study_errors.append({"source": source["source"], "errors": detail["errors"]})
                except ValueError as error:
                    study_errors.append({"source": source["source"], "error": str(error)})
            return {"index": self.local_index_status(), "workbench_sources": result["sources"],
                    "study_sources": len(sources), "errors": [*result["errors"], *study_errors]}
        finally:
            self._index_rebuild_lock.release()

    def list_configs(self) -> dict[str, object]:
        configs = []
        if self.configs_root.is_dir():
            for path in sorted(self.configs_root.rglob("*.json")):
                if path.is_symlink():
                    continue
                relative = path.relative_to(self.configs_root).as_posix()
                try:
                    if _safe_child(self.configs_root, relative) != path.resolve():
                        continue
                except DashboardRequestError:
                    continue
                configs.append(
                    {
                        "name": path.name,
                        "path": relative,
                        "size": path.stat().st_size,
                    }
                )
        return {"configs": configs}

    def list_algorithms(self) -> dict[str, object]:
        return {
            "algorithms": [
                {
                    "name": name,
                    "exact": specification.exact,
                    "uses_random_seed": specification.uses_random_seed,
                }
                for name, specification in sorted(ALGORITHMS.items())
            ]
        }

    def inspect_config(self, relative_path: str) -> dict[str, object]:
        path = _safe_child(self.configs_root, relative_path)
        if path.suffix.lower() != ".json" or not path.is_file():
            raise DashboardRequestError("config must be an existing JSON file in configs/")
        try:
            source = _read_json(path)
        except (OSError, json.JSONDecodeError) as error:
            return {"path": path.relative_to(self.configs_root).as_posix(), "valid": False, "error": str(error)}

        try:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                config = load_config(path)
                plan = plan_benchmark(config)
        except Exception as error:
            return {
                "path": path.relative_to(self.configs_root).as_posix(),
                "source": source,
                "valid": False,
                "error": str(error),
            }
        return {
            "path": path.relative_to(self.configs_root).as_posix(),
            "source": source,
            "valid": True,
            "config_hash": config_hash(config),
            "warnings": [str(item.message) for item in captured],
            "plan": {
                "name": plan.name,
                "case_ids": list(plan.case_ids),
                "repetitions": plan.repetitions,
                "instance_count": plan.instance_count,
                "algorithm_run_count": plan.algorithm_run_count,
                "runs_by_algorithm": [
                    {"algorithm": algorithm, "runs": runs}
                    for algorithm, runs in plan.runs_by_algorithm
                ],
            },
        }

    def start_run(self, payload: Mapping[str, object]) -> dict[str, object]:
        try:
            return self.research_jobs.submit({**payload, "kind": "benchmark"})
        except JobConflictError as error:
            raise DashboardConflictError(str(error)) from error
        except ValueError as error:
            raise DashboardRequestError(str(error)) from error

    def list_jobs(self) -> dict[str, object]:
        jobs = self.research_jobs.list_jobs()["jobs"]
        return {"jobs": [job for job in jobs if job.get("kind") == "benchmark"]}

    def get_job(self, job_id: str) -> dict[str, object]:
        try:
            job = self.research_jobs.get_job(job_id)
            if job.get("kind") != "benchmark":
                raise DashboardRequestError("this is not a Benchmark task")
            return job
        except ValueError as error:
            raise DashboardRequestError(str(error)) from error

    def list_results(self, excluded: set[str] | None = None) -> dict[str, object]:
        results = []
        if self.results_root.is_dir():
            for path in sorted(self.results_root.iterdir(), key=lambda item: item.name.lower()):
                if excluded and path.relative_to(self.project_root).as_posix() in excluded:
                    continue
                if path.is_symlink() or not path.is_dir() or not _RESULT_NAME.fullmatch(path.name):
                    continue
                summary_path = _safe_child(path, "summary.csv")
                raw_path = _safe_child(path, "raw_results.csv")
                if not summary_path.is_file() and not raw_path.is_file():
                    continue
                failure_dir = path / "failures"
                results.append(
                    {
                        "name": path.name,
                        "has_summary": summary_path.is_file(),
                        "has_raw_results": raw_path.is_file(),
                        "modified_at": datetime.fromtimestamp(
                            max(artifact.stat().st_mtime for artifact in (summary_path, raw_path)
                                if artifact.is_file()), timezone.utc
                        ).isoformat(timespec="seconds"),
                        "failure_count": len(
                            [
                                failure
                                for failure in failure_dir.glob("*.json")
                                if not failure.is_symlink() and failure.is_file()
                            ]
                        )
                        if failure_dir.is_dir() and not failure_dir.is_symlink()
                        else 0,
                    }
                )
        return {"results": results}

    def get_result(self, name: str) -> dict[str, object]:
        path = _result_dir(self.results_root, name)
        summary_path = _safe_child(path, "summary.csv")
        raw_path = _safe_child(path, "raw_results.csv")
        if not summary_path.is_file() and not raw_path.is_file():
            raise DashboardRequestError("result has no canonical CSV artifacts")
        incomplete = self._incomplete_result(name)
        artifacts = [
            {
                "name": filename,
                "url": f"/api/artifact?result={name}&file={filename}",
            }
            for filename in REPORT_FILENAMES
            if not incomplete and _safe_child(path, filename).is_file()
        ]
        return {
            "name": name,
            "summary": _read_csv(summary_path) if not incomplete and summary_path.is_file() else [],
            "runs": _read_csv(raw_path, limit=2000) if raw_path.is_file() else [],
            "run_limit": 2000,
            "artifacts": artifacts,
            "incomplete": incomplete,
        }

    def _incomplete_result(self, name: str) -> bool:
        latest = next((job for job in self._research_jobs.list_jobs()["jobs"]
                       if job.get("kind") == "benchmark" and Path(job.get("output_dir", "")) == Path("results") / name), None) if self._research_jobs is not None else None
        return latest is not None and latest["status"] != "completed"

    def list_replays(self, excluded: set[str] | None = None) -> dict[str, object]:
        replays: list[dict[str, object]] = []
        if self.results_root.is_dir():
            for result_dir in sorted(self.results_root.iterdir(), key=lambda item: item.name.lower()):
                if excluded and result_dir.relative_to(self.project_root).as_posix() in excluded:
                    continue
                if (
                    result_dir.is_symlink()
                    or not result_dir.is_dir()
                    or not _RESULT_NAME.fullmatch(result_dir.name)
                ):
                    continue
                failure_dir = result_dir / "failures"
                if failure_dir.is_symlink() or not failure_dir.is_dir():
                    continue
                for path in sorted(failure_dir.glob("*.json")):
                    if path.is_symlink() or not path.is_file():
                        continue
                    try:
                        document = _read_json(path)
                        replay = document.get("replay", {}) if isinstance(document, Mapping) else {}
                        replays.append(
                            {
                                "path": path.relative_to(self.results_root).as_posix(),
                                "result": result_dir.name,
                                "run_id": document.get("run_id") if isinstance(document, Mapping) else None,
                                "algorithm": replay.get("algorithm") if isinstance(replay, Mapping) else None,
                                "algorithm_id": replay.get("algorithm_id") if isinstance(replay, Mapping) else None,
                            }
                        )
                    except (OSError, json.JSONDecodeError):
                        continue
        return {"replays": replays}

    def replay(self, payload: Mapping[str, object]) -> dict[str, object]:
        instance_value = payload.get("instance")
        if not isinstance(instance_value, str):
            raise DashboardRequestError("instance is required")
        instance_path = _safe_child(self.results_root, instance_value)
        if instance_path.suffix.lower() != ".json" or not instance_path.is_file():
            raise DashboardRequestError("instance must be an existing JSON replay file in results/")
        algorithm_value = payload.get("algorithm")
        if algorithm_value is not None and (
            not isinstance(algorithm_value, str) or algorithm_value not in ALGORITHMS
        ):
            raise DashboardRequestError("algorithm must be a registered algorithm")
        solution, matches = replay_instance_file(instance_path, cast(str | None, algorithm_value))
        return {
            "algorithm": solution.algorithm,
            "status": solution.status.value,
            "coverage": solution.coverage,
            "selected": list(solution.selected),
            "matches": matches,
        }

    def artifact(self, result_name: str, filename: str) -> tuple[bytes, str]:
        if self._incomplete_result(result_name):
            raise DashboardConflictError("latest attempt is incomplete; reports are available after completion")
        result_path = _result_dir(self.results_root, result_name)
        if filename not in REPORT_FILENAMES:
            raise DashboardRequestError("artifact is not available")
        path = _safe_child(result_path, filename)
        if not path.is_file():
            raise DashboardRequestError("artifact is not available")
        content_type = "image/svg+xml; charset=utf-8" if path.suffix == ".svg" else "text/markdown; charset=utf-8"
        return path.read_bytes(), content_type


class _DashboardHTTPServer(ThreadingHTTPServer):
    service: DashboardService

    def __init__(self, address: tuple[str, int], service: DashboardService) -> None:
        if not _is_loopback_hostname(address[0]):
            raise ValueError("dashboard host must be a loopback address")
        self.address_family = (
            socket.AF_INET6 if _is_ipv6_hostname(address[0]) else socket.AF_INET
        )
        self.service = service
        super().__init__(address, _DashboardRequestHandler)

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self.service.close()


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    """Translate HTTP requests into :class:`DashboardService` operations."""

    server: _DashboardHTTPServer
    _STATIC_FILES: ClassVar[dict[str, tuple[str, str]]] = {
        "": ("index.html", "text/html; charset=utf-8"),
        "index.html": ("index.html", "text/html; charset=utf-8"),
        "app.js": ("app.js", "text/javascript; charset=utf-8"),
        "report.js": ("report.js", "text/javascript; charset=utf-8"),
        "workbench": ("workbench.html", "text/html; charset=utf-8"),
        "workbench.js": ("workbench.js", "text/javascript; charset=utf-8"),
        "workbench.css": ("workbench.css", "text/css; charset=utf-8"),
        "research": ("research.html", "text/html; charset=utf-8"),
        "research.js": ("research.js", "text/javascript; charset=utf-8"),
        "research.css": ("research.css", "text/css; charset=utf-8"),
        "experiments": ("experiments.html", "text/html; charset=utf-8"),
        "experiments.js": ("experiments.js", "text/javascript; charset=utf-8"),
        "experiments.css": ("experiments.css", "text/css; charset=utf-8"),
        "research-analysis": ("study-analysis.html", "text/html; charset=utf-8"),
        "study-analysis.js": ("study-analysis.js", "text/javascript; charset=utf-8"),
        "study-analysis.css": ("study-analysis.css", "text/css; charset=utf-8"),
        "styles.css": ("styles.css", "text/css; charset=utf-8"),
        "favicon.svg": ("favicon.svg", "image/svg+xml; charset=utf-8"),
        "fonts/space-grotesk-latin-600-normal.woff2": ("fonts/space-grotesk-latin-600-normal.woff2", "font/woff2"),
        "fonts/space-grotesk-latin-700-normal.woff2": ("fonts/space-grotesk-latin-700-normal.woff2", "font/woff2"),
        "fonts/ibm-plex-mono-latin-400-normal.woff2": ("fonts/ibm-plex-mono-latin-400-normal.woff2", "font/woff2"),
        "fonts/ibm-plex-mono-latin-600-normal.woff2": ("fonts/ibm-plex-mono-latin-600-normal.woff2", "font/woff2"),
    }

    def log_message(self, format: str, *args: object) -> None:
        # The dashboard is normally used from a terminal; request noise obscures
        # benchmark progress, so errors are returned to the browser instead.
        del format, args

    def _send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        if self.path.startswith(("/api/studies/", "/api/research/")):
            payload = _research_browser_numbers(payload)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _error(self, error: Exception) -> None:
        status = getattr(error, "status", HTTPStatus.INTERNAL_SERVER_ERROR)
        message = str(error) or error.__class__.__name__
        self._send_json({"error": message}, cast(HTTPStatus, status))

    def _request_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise DashboardRequestError("Content-Length must be an integer") from error
        if length <= 0 or length > _MAX_REQUEST_BYTES:
            raise DashboardRequestError("request body is empty or too large")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise DashboardRequestError("request body must be valid JSON") from error
        if not isinstance(value, dict):
            raise DashboardRequestError("request body must be a JSON object")
        return value

    def _validate_state_change(self) -> None:
        """Require a browser request to prove same-origin JSON intent."""

        origin = self.headers.get("Origin")
        host = self.headers.get("Host")
        if not origin or not host:
            raise DashboardForbiddenError(
                "state-changing requests require a same-origin Origin header"
            )
        parsed_origin = urlparse(origin)
        parsed_host = urlparse(f"//{host}")
        try:
            origin_port = parsed_origin.port or 80
            host_port = parsed_host.port or 80
        except ValueError:
            raise DashboardForbiddenError("state-changing requests must be same-origin") from None
        if (
            parsed_origin.scheme.lower() != "http"
            or not _is_loopback_hostname(parsed_origin.hostname)
            or not _is_loopback_hostname(parsed_host.hostname)
            or origin_port != host_port
            or parsed_origin.path not in {"", "/"}
            or parsed_origin.query
            or parsed_origin.fragment
        ):
            raise DashboardForbiddenError("state-changing requests must be same-origin")
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise DashboardUnsupportedMediaTypeError(
                "state-changing requests must use application/json"
            )

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            service = self.server.service
            if path == "/healthz":
                self._send_json({"ok": True})
            elif path == "/api/configs":
                self._send_json(service.list_configs())
            elif path == "/api/algorithms":
                self._send_json(service.list_algorithms())
            elif path == "/api/config":
                self._send_json(service.inspect_config(_one_query(query, "path")))
            elif path == "/api/experiments/annotations":
                self._send_json(service.experiments.annotations())
            elif path == "/api/experiments/config":
                self._send_json(service.experiments.read_config(_one_query(query, "path")))
            elif path == "/api/jobs":
                self._send_json(service.list_jobs())
            elif path.startswith("/api/jobs/"):
                self._send_json(service.get_job(path.rsplit("/", 1)[1]))
            elif path == "/api/results":
                self._send_json(service.scan_artifacts(service.list_results))
            elif path == "/api/local/index":
                self._send_json(service.local_index_status())
            elif path == "/api/local/archive":
                self._send_json({"entries": service.local_catalog.list(_one_query(query, "kind")),
                                 **service.local_catalog.status()})
            elif path == "/api/studies/library":
                self._send_json(service.scan_artifacts(service.studies.library))
            elif path in {"/api/studies/analysis", "/api/studies/records"}:
                filters: dict[str, str] = {key: _one_query(query, key) for key in ("n", "d", "k", "loss_only") if key in query}
                source = _one_query(query, "source")
                if path.endswith("/analysis"):
                    self._send_json(service.read_artifacts([source], lambda: service.analysis.overview(source, filters)))
                else:
                    self._send_json(service.read_artifacts([source], lambda: service.analysis.records(source, filters,
                        offset=_int_query(query, "offset", 0), limit=_int_query(query, "limit", 50))))
            elif path == "/api/studies/pairs":
                self._send_json(service.read_artifacts([_one_query(query, "source")], lambda: service.analysis.pairs(_one_query(query, "source"),
                    n=_int_query(query, "n"), d=_int_query(query, "d"),
                    k_a=_int_query(query, "k_a"), k_b=_int_query(query, "k_b"),
                    metric=_one_query(query, "metric") if "metric" in query else "relative_gap")))
            elif path in {"/api/studies/instance", "/api/studies/instance-export"}:
                operation = service.analysis.export_instance if path.endswith("-export") else service.analysis.instance
                payload = service.read_artifacts([_one_query(query, "source")], lambda: operation(_one_query(query, "source"), _one_query(query, "base_graph_id"),
                    k=_int_query(query, "k") if "k" in query else None,
                    direction=_int_query(query, "direction") if "direction" in query else None,
                    replica=_int_query(query, "replica") if "replica" in query else None))
                if path.endswith("-export"):
                    self._send_download(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                        "application/json; charset=utf-8", "study-instance.json")
                else:
                    self._send_json(payload)
            elif path == "/api/studies/detail":
                self._send_json(service.read_artifacts([_one_query(query, "source")], lambda: service.studies.detail(_one_query(query, "source"))))
            elif path == "/api/studies/artifact":
                filename = _one_query(query, "file")
                body, content_type = service.read_artifacts([_one_query(query, "source")], lambda: service.studies.artifact(_one_query(query, "source"), filename))
                self._send_download(body, content_type, filename)
            elif path == "/api/research/jobs":
                self._send_json(service.research_jobs.list_jobs())
            elif path.startswith("/api/research/jobs/"):
                parts = path.split("/")
                if len(parts) == 5:
                    self._send_json(service.research_jobs.get_job(parts[4]))
                elif len(parts) == 6 and parts[5] == "result":
                    self._send_json(service.research_jobs.result(parts[4]))
                elif len(parts) == 7 and parts[5] == "files":
                    body, content_type = service.research_jobs.result_asset(parts[4], parts[6])
                    self._send_download(body, content_type, parts[6])
                else:
                    raise DashboardRequestError("unknown research job endpoint")
            elif path == "/api/workbench/library":
                self._send_json(service.scan_artifacts(service.workbench.library))
            elif path == "/api/workbench/views":
                self._send_json(service.exports.list_views())
            elif path.startswith("/api/workbench/views/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[5] == "artifact":
                    body, content_type, filename = service.exports.artifact(parts[4], _one_query(query, "format"))
                    self._send_download(body, content_type, filename)
                elif len(parts) == 5:
                    self._send_json(service.exports.get(parts[4]))
                else:
                    raise DashboardRequestError("unknown saved comparison endpoint")
            elif path == "/api/workbench/compare":
                try:
                    page = int(_one_query(query, "page")) if "page" in query else 0
                except ValueError as error:
                    raise DashboardRequestError("page must be a non-negative integer") from error
                self._send_json(service.read_artifacts(query.get("source", []), lambda: service.workbench.compare(
                    query.get("source", []),
                    case=_one_query(query, "case") if "case" in query else "",
                    algorithm=_one_query(query, "algorithm") if "algorithm" in query else "",
                    population=_one_query(query, "population") if "population" in query else "research",
                    outcome=_one_query(query, "outcome") if "outcome" in query else "all",
                    page=page,
                )))
            elif path in {"/api/workbench/detail", "/api/workbench/export"}:
                action = service.workbench.export if path.endswith("/export") else service.workbench.detail
                self._send_json(service.read_artifacts([_one_query(query, "source")], lambda: action(_one_query(query, "source"), _one_query(query, "key"))))
            elif path == "/api/result":
                self._send_json(service.read_artifacts(["results/" + _one_query(query, "name")], lambda: service.get_result(_one_query(query, "name"))))
            elif path == "/api/replay-files":
                self._send_json(service.scan_artifacts(service.list_replays))
            elif path == "/api/artifact":
                body, content_type = service.read_artifacts(["results/" + _one_query(query, "result")], lambda: service.artifact(
                    _one_query(query, "result"), _one_query(query, "file")
                ))
                self._send_bytes(body, content_type)
            else:
                self._serve_static(path)
        except (DashboardRequestError, DashboardConflictError, OSError, ValueError) as error:
            if self.path.startswith("/api/experiments/") and isinstance(error, ValueError):
                self._error(DashboardConflictError(str(error)) if isinstance(error, ExperimentsConflictError)
                            else DashboardRequestError(str(error)))
            elif self.path.startswith("/api/research/") and isinstance(error, ValueError):
                self._error(DashboardConflictError(str(error)) if isinstance(error, JobConflictError)
                            else DashboardRequestError(str(error)))
            else:
                self._error(error)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._validate_state_change()
            payload = self._request_json()
            service = self.server.service
            if self.path == "/api/validate":
                self._send_json(service.inspect_config(_required_string(payload, "config")))
            elif self.path == "/api/run":
                self._send_json(service.start_run(payload), HTTPStatus.ACCEPTED)
            elif self.path == "/api/replay":
                replay_path = unquote(_required_string(payload, "instance")).strip()
                self._send_json(service.read_artifacts(["results/" + replay_path], lambda: service.replay(payload)))
            elif self.path == "/api/workbench/views":
                sources = payload.get("sources")
                if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
                    raise DashboardRequestError("sources must be a list of paths")
                self._send_json(service.read_artifacts(sources, lambda: service.exports.save(payload)), HTTPStatus.CREATED)
            elif self.path.startswith("/api/experiments/"):
                operations = {
                    "/api/experiments/annotation": service.experiments.set_annotation,
                    "/api/experiments/config-copy": service.experiments.copy_config,
                    "/api/experiments/config-preview": service.experiments.preview_config,
                    "/api/experiments/config-save": service.experiments.save_config,
                }
                if self.path not in operations:
                    raise DashboardRequestError("unknown experiment management endpoint")
                if self.path.endswith("/annotation"):
                    self._send_json(service.read_artifacts([_required_string(payload, "source")], lambda: operations[self.path](payload)))
                else:
                    self._send_json(operations[self.path](payload))
            elif self.path == "/api/local/index/rebuild":
                if payload:
                    raise DashboardRequestError("index rebuild accepts an empty object")
                self._send_json(service.read_artifacts(["results"], service.rebuild_local_index))
            elif self.path == "/api/local/archive":
                if set(payload) != {"kind", "id", "archived"} or type(payload["archived"]) is not bool:
                    raise DashboardRequestError("archive requires kind, id and a boolean archived flag")
                self._send_json(service.local_catalog.set_archived(_required_string(payload, "kind"),
                    _required_string(payload, "id"), cast(bool, payload["archived"])))
            elif self.path == "/api/research/jobs":
                self._send_json(service.research_jobs.submit(payload), HTTPStatus.ACCEPTED)
            elif self.path.startswith("/api/research/jobs/"):
                parts = self.path.split("/")
                job_operations = {"retry": service.research_jobs.retry, "resume": service.research_jobs.resume,
                              "pause": service.research_jobs.pause, "cancel": service.research_jobs.cancel}
                if len(parts) == 6 and parts[5] in job_operations and not payload:
                    self._send_json(job_operations[parts[5]](parts[4]), HTTPStatus.ACCEPTED)
                else:
                    raise DashboardRequestError("unknown research operation or nonempty retry payload")
            else:
                raise DashboardRequestError("unknown API endpoint")
        except (DashboardRequestError, DashboardConflictError, OSError, ValueError) as error:
            if self.path.startswith("/api/experiments/") and isinstance(error, ValueError):
                if isinstance(error, DashboardRequestError):
                    self._error(error)
                else:
                    self._error(DashboardConflictError(str(error)) if isinstance(error, ExperimentsConflictError)
                                else DashboardRequestError(str(error)))
            elif self.path.startswith("/api/research/") and isinstance(error, ValueError):
                # Preserve Origin/media-type errors; map the CLI adapter's
                # validation and queue-conflict exceptions to client responses.
                if isinstance(error, DashboardRequestError):
                    self._error(error)
                else:
                    self._error(DashboardConflictError(str(error)) if isinstance(error, JobConflictError)
                                else DashboardRequestError(str(error)))
            else:
                self._error(error)

    def _serve_static(self, request_path: str) -> None:
        key = request_path.lstrip("/")
        if key not in self._STATIC_FILES:
            raise DashboardRequestError("not found")
        filename, content_type = self._STATIC_FILES[key]
        path = STATIC_ROOT / filename
        self._send_bytes(path.read_bytes(), content_type)

    def _send_download(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _one_query(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    if len(values) != 1:
        raise DashboardRequestError(f"query parameter {key!r} is required exactly once")
    return values[0]


def _int_query(query: Mapping[str, list[str]], key: str, default: int | None = None) -> int:
    if key not in query and default is not None:
        return default
    try:
        return int(_one_query(query, key))
    except ValueError as error:
        raise DashboardRequestError(f"query parameter {key!r} must be an integer") from error


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise DashboardRequestError(f"{key} is required")
    return value


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_ipv6_hostname(hostname: str) -> bool:
    try:
        return ipaddress.ip_address(hostname).version == 6
    except ValueError:
        return False


def serve_dashboard(
    host: str = "127.0.0.1", port: int = 8501, *, project_root: Path = PROJECT_ROOT
) -> None:
    """Serve the local dashboard until interrupted."""

    if not 0 <= port <= 65_535:
        raise ValueError("port must be between 0 and 65535")
    if not _is_loopback_hostname(host):
        raise ValueError("dashboard host must be a loopback address")
    service = DashboardService(project_root)
    server = _DashboardHTTPServer((host, port), service)
    address = server.server_address
    actual_host = cast(str, address[0])
    actual_port = cast(int, address[1])
    display_host = f"[{actual_host}]" if ":" in actual_host else actual_host
    print(f"Dashboard running at http://{display_host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.shutdown()
        server.server_close()


__all__ = ("DashboardService", "serve_dashboard")
