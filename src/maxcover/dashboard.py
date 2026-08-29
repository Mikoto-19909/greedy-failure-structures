"""Local dashboard frontend for the maximum-coverage experiment engine.

The dashboard deliberately stays small and local.  It is a standard-library
HTTP server that exposes the same configuration, benchmark, report, and replay
functions as the command-line interface.  It does not add a database, a remote
job queue, or a second implementation of the experiment logic.
"""

from __future__ import annotations

import csv
import json
import re
import threading
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, Mapping, cast
from urllib.parse import parse_qs, unquote, urlparse

from .algorithms import ALGORITHMS
from .benchmark import REPORT_FILENAMES, plan_benchmark, replay_instance_file, run_benchmark
from .config import load_config


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


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_child(root: Path, relative: str) -> Path:
    """Resolve a user-provided relative path without escaping ``root``."""

    candidate_text = unquote(relative).strip()
    if not candidate_text:
        raise DashboardRequestError("path must not be empty")
    candidate = Path(candidate_text)
    if candidate.is_absolute():
        raise DashboardRequestError("absolute paths are not allowed")
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


@dataclass(slots=True)
class _Job:
    job_id: str
    config: str
    output: str
    workers: int
    force: bool
    status: str = "queued"
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result_name: str | None = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _iso_now()

    def payload(self) -> dict[str, object]:
        return {
            "id": self.job_id,
            "config": self.config,
            "output": self.output,
            "workers": self.workers,
            "force": self.force,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result_name": self.result_name,
        }


class DashboardService:
    """Application services used by the HTTP handler and unit tests."""

    def __init__(self, project_root: Path = PROJECT_ROOT) -> None:
        self.project_root = Path(project_root).resolve()
        self.configs_root = self.project_root / "configs"
        self.results_root = self.project_root / "results"
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.RLock()

    def list_configs(self) -> dict[str, object]:
        configs = []
        if self.configs_root.is_dir():
            for path in sorted(self.configs_root.glob("*.json")):
                if path.is_symlink():
                    continue
                configs.append(
                    {
                        "name": path.name,
                        "path": path.relative_to(self.configs_root).as_posix(),
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
            return {"path": path.name, "valid": False, "error": str(error)}

        try:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                config = load_config(path)
                plan = plan_benchmark(config)
        except Exception as error:
            return {
                "path": path.name,
                "source": source,
                "valid": False,
                "error": str(error),
            }
        return {
            "path": path.name,
            "source": source,
            "valid": True,
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
        config_value = payload.get("config")
        if not isinstance(config_value, str):
            raise DashboardRequestError("config is required")
        config_info = self.inspect_config(config_value)
        if config_info.get("valid") is not True:
            raise DashboardRequestError(cast(str, config_info.get("error", "invalid configuration")))

        output_value = payload.get("output")
        output_name = output_value if isinstance(output_value, str) else Path(config_value).stem
        if not _RESULT_NAME.fullmatch(output_name):
            raise DashboardRequestError(
                "output must be a simple result name using letters, numbers, dots, underscores, or hyphens"
            )
        workers_value = payload.get("workers", 1)
        if isinstance(workers_value, bool) or not isinstance(workers_value, int) or not 1 <= workers_value <= 32:
            raise DashboardRequestError("workers must be an integer from 1 to 32")
        force_value = payload.get("force", False)
        if not isinstance(force_value, bool):
            raise DashboardRequestError("force must be a boolean")
        self.results_root.mkdir(parents=True, exist_ok=True)
        _safe_child(self.results_root, output_name)

        with self._lock:
            active = next(
                (job for job in self._jobs.values() if job.status in {"queued", "running"}),
                None,
            )
            if active is not None:
                raise DashboardConflictError(
                    f"a benchmark is already {active.status}: {active.job_id}"
                )
            job = _Job(
                job_id=uuid.uuid4().hex,
                config=config_value,
                output=output_name,
                workers=workers_value,
                force=force_value,
            )
            self._jobs[job.job_id] = job
            thread = threading.Thread(
                target=self._run_job,
                args=(job.job_id,),
                name=f"maxcover-dashboard-{job.job_id[:8]}",
                daemon=True,
            )
            thread.start()
        return job.payload()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = _iso_now()
        try:
            run_benchmark(
                self.configs_root / job.config,
                self.results_root / job.output,
                workers=job.workers,
                force=job.force,
            )
        except Exception as error:
            with self._lock:
                job.status = "failed"
                job.error = str(error)
                job.finished_at = _iso_now()
            return
        with self._lock:
            job.status = "completed"
            job.result_name = job.output
            job.finished_at = _iso_now()

    def list_jobs(self) -> dict[str, object]:
        with self._lock:
            jobs = [job.payload() for job in self._jobs.values()]
        return {"jobs": list(reversed(jobs[-20:]))}

    def get_job(self, job_id: str) -> dict[str, object]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise DashboardRequestError(f"unknown job: {job_id}")
            return job.payload()

    def list_results(self) -> dict[str, object]:
        results = []
        if self.results_root.is_dir():
            for path in sorted(self.results_root.iterdir(), key=lambda item: item.name.lower()):
                if path.is_symlink() or not path.is_dir() or not _RESULT_NAME.fullmatch(path.name):
                    continue
                summary_path = _safe_child(path, "summary.csv")
                raw_path = _safe_child(path, "raw_results.csv")
                failure_dir = path / "failures"
                results.append(
                    {
                        "name": path.name,
                        "has_summary": summary_path.is_file(),
                        "has_raw_results": raw_path.is_file(),
                        "modified_at": datetime.fromtimestamp(
                            path.stat().st_mtime, timezone.utc
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
        artifacts = [
            {
                "name": filename,
                "url": f"/api/artifact?result={name}&file={filename}",
            }
            for filename in REPORT_FILENAMES
            if _safe_child(path, filename).is_file()
        ]
        manifest: object = None
        manifest_path = _safe_child(path, "manifest.json")
        if manifest_path.is_file():
            try:
                manifest = _read_json(manifest_path)
            except (OSError, json.JSONDecodeError):
                manifest = None
        return {
            "name": name,
            "summary": _read_csv(summary_path) if summary_path.is_file() else [],
            "runs": _read_csv(raw_path, limit=2000) if raw_path.is_file() else [],
            "run_limit": 2000,
            "manifest": manifest,
            "artifacts": artifacts,
        }

    def list_replays(self) -> dict[str, object]:
        replays: list[dict[str, object]] = []
        if self.results_root.is_dir():
            for result_dir in sorted(self.results_root.iterdir(), key=lambda item: item.name.lower()):
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
        self.service = service
        super().__init__(address, _DashboardRequestHandler)


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    """Translate HTTP requests into :class:`DashboardService` operations."""

    server: _DashboardHTTPServer
    _STATIC_FILES: ClassVar[dict[str, tuple[str, str]]] = {
        "": ("index.html", "text/html; charset=utf-8"),
        "index.html": ("index.html", "text/html; charset=utf-8"),
        "app.js": ("app.js", "text/javascript; charset=utf-8"),
        "styles.css": ("styles.css", "text/css; charset=utf-8"),
        "favicon.svg": ("favicon.svg", "image/svg+xml; charset=utf-8"),
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
        loopback_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            parsed_origin.scheme.lower() != "http"
            or parsed_origin.netloc.lower() != host.lower()
            or parsed_origin.hostname not in loopback_hosts
            or parsed_host.hostname not in loopback_hosts
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
            elif path == "/api/jobs":
                self._send_json(service.list_jobs())
            elif path.startswith("/api/jobs/"):
                self._send_json(service.get_job(path.rsplit("/", 1)[1]))
            elif path == "/api/results":
                self._send_json(service.list_results())
            elif path == "/api/result":
                self._send_json(service.get_result(_one_query(query, "name")))
            elif path == "/api/replay-files":
                self._send_json(service.list_replays())
            elif path == "/api/artifact":
                body, content_type = service.artifact(
                    _one_query(query, "result"), _one_query(query, "file")
                )
                self._send_bytes(body, content_type)
            else:
                self._serve_static(path)
        except (DashboardRequestError, DashboardConflictError, OSError, ValueError) as error:
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
                self._send_json(service.replay(payload))
            else:
                raise DashboardRequestError("unknown API endpoint")
        except (DashboardRequestError, DashboardConflictError, OSError, ValueError) as error:
            self._error(error)

    def _serve_static(self, request_path: str) -> None:
        key = request_path.lstrip("/")
        if key not in self._STATIC_FILES:
            raise DashboardRequestError("not found")
        filename, content_type = self._STATIC_FILES[key]
        path = STATIC_ROOT / filename
        self._send_bytes(path.read_bytes(), content_type)


def _one_query(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    if len(values) != 1:
        raise DashboardRequestError(f"query parameter {key!r} is required exactly once")
    return values[0]


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise DashboardRequestError(f"{key} is required")
    return value


def serve_dashboard(
    host: str = "127.0.0.1", port: int = 8501, *, project_root: Path = PROJECT_ROOT
) -> None:
    """Serve the local dashboard until interrupted."""

    if not 0 <= port <= 65_535:
        raise ValueError("port must be between 0 and 65535")
    service = DashboardService(project_root)
    server = _DashboardHTTPServer((host, port), service)
    address = server.server_address
    actual_host = cast(str, address[0])
    actual_port = cast(int, address[1])
    print(f"Dashboard running at http://{actual_host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.shutdown()
        server.server_close()


__all__ = ("DashboardService", "serve_dashboard")
