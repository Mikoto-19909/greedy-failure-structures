"""Persistent, serial local jobs for the existing counterexample CLI.

The child owns the execution lock and writes its own terminal state. A restarted
server therefore waits for an orphan child instead of repeating its computation.
This queue covers mine/refute only; benchmark retains its existing runner.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import threading
from typing import Any, BinaryIO
import uuid

from .reproducibility import instance_from_payload

LIMITS = {"max_input_bytes": 4_000_000, "max_input_records": 500,
          "max_combinations": 200_000, "max_evaluations": 10_000,
          "max_top": 10, "max_budget": 10_000, "max_timeout_seconds": 600}
_ID = re.compile(r"[0-9a-f]{32}\Z")
_TERMINAL = {"completed", "failed", "interrupted"}


class JobConflictError(ValueError):
    """The queue or requested task cannot accept this operation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any]:
    def finite_number(text: str) -> float:
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("non-finite numbers are not valid job data")
        return number

    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=finite_number, parse_float=finite_number)
    if not isinstance(data, dict):
        raise ValueError("job document must be an object")
    return data


def _write(path: Path, data: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class _FileLock:
    """Nonblocking OS lock, released automatically when its process exits."""

    def __init__(self, path: Path) -> None:
        self.handle: BinaryIO = path.open("a+b")
        if os.fstat(self.handle.fileno()).st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            raise JobConflictError("another local job process owns this queue") from error

    def close(self) -> None:
        self.handle.close()


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("path must be relative to this project")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path must stay within this project")
    return candidate


def _case(instance: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    return {"instance": instance, "evaluation": evaluation,
            "size": {"sets": len(instance["sets"]), "elements": instance["universe_size"],
                     "memberships": sum(len(row) for row in instance["sets"])}}


def _summary(kind: str, document: dict[str, Any]) -> dict[str, Any]:
    cases = []
    if kind == "mine":
        for selected in document["selected"]:
            original = document["inputs"][selected["input_index"]]
            cases.append({"source": original["source"],
                          "original": _case(original["instance"], original["evaluation"]),
                          "reduced": {**_case(selected["instance"], selected["evaluation"]),
                                      "status": selected["status"]}})
        counts = document["counts"]
        status = ("counterexample_found" if counts["failures"] else
                  "combination_limit" if counts["exact"] < counts["input"] else "no_counterexample_in_input")
    else:
        counts, status = document["counts"], document["status"]
        if document["counterexample"] is not None:
            item = document["counterexample"]
            cases.append({"original": _case(item["instance"], item["evaluation"]), "reduced": None})
    return {"status": status, "validated": True, "counts": counts, "cases": cases}


def _validate_record(job: dict[str, Any], job_id: str) -> None:
    """Validate the fields consumed by recovery, execution and result routes."""
    required = {"id", "kind", "status", "params", "created_at", "started_at", "finished_at",
                "output_dir", "input_snapshot", "error", "summary", "retry_of"}
    if required - job.keys() or job["id"] != job_id:
        raise ValueError("missing or inconsistent job metadata")
    kind, status, params = job["kind"], job["status"], job["params"]
    if (kind not in ("mine", "refute") or status not in ("queued", "running", *_TERMINAL)
            or not isinstance(params, dict) or params.get("kind") != kind):
        raise ValueError("invalid job kind, state or parameters")
    if job["output_dir"] != f"results/workbench_jobs/{job_id}/output":
        raise ValueError("output directory does not belong to this job")
    if job["input_snapshot"] not in (("input.json", "input.jsonl") if kind == "mine" else ("design.json",)):
        raise ValueError("invalid frozen input filename")
    if (status == "queued" and (job["started_at"] is not None or job["finished_at"] is not None)
            or status == "running" and job["finished_at"] is not None):
        raise ValueError("job timestamps disagree with its state")
    for field in ("created_at", "started_at", "finished_at"):
        value = job[field]
        nullable = field == "started_at" and status == "queued" or field == "finished_at" and status in ("queued", "running")
        if value is None and nullable:
            continue
        if not isinstance(value, str) or datetime.fromisoformat(value).tzinfo is None:
            raise ValueError(f"invalid {field}")
    if status == "running" and (not isinstance(job.get("owner"), str) or not job["owner"]):
        raise ValueError("running job has no owner")
    if job["retry_of"] is not None and (not isinstance(job["retry_of"], str) or not _ID.fullmatch(job["retry_of"])):
        raise ValueError("invalid retry source")
    if job["error"] is not None and not isinstance(job["error"], str):
        raise ValueError("invalid job error")
    _integer(params.get("timeout_seconds"), "timeout_seconds", 1, 600)
    _integer(params.get("max_combinations"), "max_combinations", 1, 200_000)
    if kind == "mine":
        _integer(params.get("top"), "top", 1, 10)
        _integer(params.get("max_evaluations"), "max_evaluations", 0, 10_000)
        if not isinstance(params.get("input"), str) or not isinstance(params.get("population"), str):
            raise ValueError("invalid mining input or population")
    else:
        n = _integer(params.get("n"), "n", 1, 12)
        m = _integer(params.get("m"), "m", 1, 16)
        _integer(params.get("k"), "k", 1, m)
        _integer(params.get("budget"), "budget", 0, 10_000)
        for field, maximum in (("set_size", n), ("max_frequency", m)):
            if field not in params:
                raise ValueError(f"missing {field}")
            if params[field] is not None:
                _integer(params[field], field, 0, maximum)
        ratio = params.get("min_ratio")
        if type(params.get("unique_sets")) is not bool or not isinstance(ratio, list) or len(ratio) != 2:
            raise ValueError("invalid conjecture premise or ratio")
        denominator = _integer(ratio[1], "ratio denominator", 1, 1_000_000)
        _integer(ratio[0], "ratio numerator", 0, denominator)
    summary = job["summary"]
    if status != "completed":
        if summary is not None:
            raise ValueError("unfinished job cannot have a validated summary")
        return
    if job["error"] is not None or not isinstance(summary, dict) or summary.get("validated") is not True:
        raise ValueError("completed job requires a validated summary without an error")
    states = (("counterexample_found", "combination_limit", "no_counterexample_in_input") if kind == "mine"
              else ("counterexample_found", "domain_exhausted", "budget_exhausted"))
    counts, cases = summary.get("counts"), summary.get("cases")
    if summary.get("status") not in states or not isinstance(counts, dict) or not isinstance(cases, list):
        raise ValueError("invalid result summary")
    fields = ("input", "exact", "failures", "selected") if kind == "mine" else ("candidate_space", "scanned", "eligible", "rejected")
    if any(type(counts.get(field)) is not int or counts[field] < 0 for field in fields):
        raise ValueError("invalid result counts")
    if kind == "mine" and not 0 <= counts["selected"] == len(cases) <= params["top"]:
        raise ValueError("invalid selected-case count")
    if kind == "refute" and len(cases) != int(summary["status"] == "counterexample_found"):
        raise ValueError("invalid counterexample count")
    for case in cases:
        if not isinstance(case, dict) or "original" not in case or "reduced" not in case:
            raise ValueError("invalid saved case")
        for item in (case["original"], case["reduced"]) if kind == "mine" else (case["original"],):
            if not isinstance(item, dict) or any(not isinstance(item.get(field), dict) for field in ("instance", "evaluation", "size")):
                raise ValueError("invalid case instance, evaluation or size")


class JobService:
    """A single local queue backed by results/workbench_jobs/<job-id>/."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.root = _path(self.project_root, "results/workbench_jobs")
        self.root.mkdir(parents=True, exist_ok=True)
        self._owner_lock = _FileLock(self.root / "owner.lock")
        self._owner = uuid.uuid4().hex
        self._mutex = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._recovering = True
        self._thread = threading.Thread(target=self._work, daemon=True, name="maxcover-research-jobs")
        self._thread.start()

    def _job_path(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _ID.fullmatch(job_id):
            raise ValueError("invalid job ID")
        path = _path(self.project_root, f"results/workbench_jobs/{job_id}/job.json")
        if not path.is_file():
            raise ValueError(f"unknown job: {job_id}")
        return path

    def _records(self) -> list[dict[str, Any]]:
        records = []
        for path in self.root.glob("*/job.json"):
            if not path.resolve().is_relative_to(self.root) or not _ID.fullmatch(path.parent.name):
                continue
            try:
                job = _read(path)
                _validate_record(job, path.parent.name)
                records.append(job)
            except (OSError, ValueError) as error:
                records.append({"id": path.parent.name, "kind": "unknown", "status": "failed",
                    "created_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "started_at": None, "finished_at": None, "params": {}, "output_dir": None,
                    "summary": None, "retry_of": None, "corrupt_record": True,
                    "error": f"saved job record is unreadable; original file preserved: {error}"})
        return sorted(records, key=lambda job: (job["created_at"], job["id"]))

    def _public(self, job: dict[str, Any]) -> dict[str, Any]:
        result = {key: value for key, value in job.items() if key != "owner"}
        log = _path(self.project_root, f"results/workbench_jobs/{job['id']}/run.log")
        if log.is_file():
            with log.open("rb") as handle:
                handle.seek(max(0, log.stat().st_size - 16_384))
                result["log_tail"] = handle.read().decode("utf-8", errors="replace")
        else:
            result["log_tail"] = ""
        return result

    def list_jobs(self) -> dict[str, Any]:
        with self._mutex:
            return {"jobs": [self._public(job) for job in reversed(self._records())],
                    "queue_state": "recovering" if self._recovering else "ready", "limits": LIMITS}

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._mutex:
            self._job_path(job_id)
            return self._public(next(job for job in self._records() if job["id"] == job_id))

    def _prepare(self, payload: Mapping[str, object]) -> tuple[dict[str, Any], bytes, str]:
        kind = payload.get("kind")
        common = {"kind", "timeout_seconds", "max_combinations"}
        fields = ({"input", "population", "top", "max_evaluations"} if kind == "mine" else
                  {"n", "m", "k", "set_size", "unique_sets", "max_frequency", "min_ratio", "budget"})
        if not isinstance(kind, str) or kind not in {"mine", "refute"} or set(payload) - common - fields:
            raise ValueError("only mine/refute tasks and their documented fields are accepted")
        params: dict[str, Any] = {"kind": kind,
            "timeout_seconds": _integer(payload.get("timeout_seconds", 120), "timeout_seconds", 1, 600),
            "max_combinations": _integer(payload.get("max_combinations", 20_000), "max_combinations", 1, 200_000)}
        if kind == "mine":
            source = payload.get("input", "experiments/r1_prefix_exchange_v1/paths.jsonl")
            if not isinstance(source, str):
                raise ValueError("input must be a project-relative JSON or JSONL path")
            path = _path(self.project_root, source)
            if path.suffix.lower() not in {".json", ".jsonl"} or not path.is_file():
                raise ValueError("input must be an existing JSON or JSONL file")
            if path.stat().st_size > LIMITS["max_input_bytes"]:
                raise ValueError("input exceeds the 4 MB interactive limit")
            data = path.read_bytes()
            documents = ([json.loads(line) for line in data.decode("utf-8-sig").splitlines() if line.strip()]
                         if path.suffix.lower() == ".jsonl" else [json.loads(data.decode("utf-8-sig"))])
            if not 1 <= len(documents) <= LIMITS["max_input_records"]:
                raise ValueError("input must contain 1 to 500 records")
            for document in documents:
                if not isinstance(document, dict):
                    raise ValueError("each input record must be an object")
                value = document.get("instance", document)
                if not isinstance(value, dict):
                    raise ValueError("instance must be an object")
                _integer(value.get("universe_size"), "universe_size", 1, 256)
                if not isinstance(value.get("sets"), list) or not 1 <= len(value["sets"]) <= 64:
                    raise ValueError("interactive instances require 1 to 64 sets")
                instance = instance_from_payload({"schema_version": 1, "encoding": "elements", **value})
                if instance.universe_size > 256 or instance.set_count > 64 or instance.k < 1:
                    raise ValueError("interactive instances require n<=256, m<=64, and k>=1")
            population = payload.get("population", "pilot" if "input" not in payload else "all")
            if not isinstance(population, str) or not population or len(population) > 80 or any(c in population for c in "\r\n"):
                raise ValueError("population must be a nonempty single-line label")
            params.update(input=source, population=population,
                top=_integer(payload.get("top", 3), "top", 1, 10),
                max_evaluations=_integer(payload.get("max_evaluations", 500), "max_evaluations", 0, 10_000))
            return params, data, "input" + path.suffix.lower()
        n = _integer(payload.get("n", 4), "n", 1, 12)
        m = _integer(payload.get("m", 3), "m", 1, 16)
        k = _integer(payload.get("k", 2), "k", 1, m)
        size, frequency = payload.get("set_size", 2), payload.get("max_frequency")
        if size is not None:
            size = _integer(size, "set_size", 0, n)
        if frequency is not None:
            frequency = _integer(frequency, "max_frequency", 0, m)
        unique = payload.get("unique_sets", True)
        ratio = payload.get("min_ratio", [1, 1])
        if type(unique) is not bool or not isinstance(ratio, list) or len(ratio) != 2:
            raise ValueError("unique_sets must be boolean; min_ratio must be [numerator, denominator]")
        denominator = _integer(ratio[1], "ratio denominator", 1, 1_000_000)
        numerator = _integer(ratio[0], "ratio numerator", 0, denominator)
        budget = _integer(payload.get("budget", 1000), "budget", 0, 10_000)
        params.update(n=n, m=m, k=k, set_size=size, unique_sets=unique,
                      max_frequency=frequency, min_ratio=[numerator, denominator], budget=budget)
        design = {"schema_version": 1, "name": "workbench_conjecture",
            "domain": {"universe_size": n, "set_count": m, "k": k, "set_size": size,
                       "unique_sets": unique, "max_frequency": frequency},
            "claim": {"min_ratio": [numerator, denominator]},
            "search": {"max_instances": budget, "max_combinations": params["max_combinations"]}}
        return params, (json.dumps(design, ensure_ascii=False) + "\n").encode(), "design.json"

    def _enqueue(self, params: dict[str, Any], data: bytes, filename: str,
                 retry_of: str | None = None) -> dict[str, Any]:
        if self._stop.is_set():
            raise JobConflictError("job service is closed")
        if sum(job["status"] == "queued" for job in self._records()) >= 100:
            raise JobConflictError("the local queue already contains 100 pending jobs")
        job_id = uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir(exist_ok=False)
        (directory / filename).write_bytes(data)
        job = {"id": job_id, "kind": params["kind"], "status": "queued", "params": params,
            "created_at": _now(), "started_at": None, "finished_at": None,
            "output_dir": (directory / "output").relative_to(self.project_root).as_posix(),
            "input_snapshot": filename, "error": None, "summary": None, "retry_of": retry_of}
        _write(directory / "job.json", job)
        self._wake.set()
        return self._public(job)

    def submit(self, payload: Mapping[str, object]) -> dict[str, Any]:
        params, data, filename = self._prepare(payload)
        with self._mutex:
            return self._enqueue(params, data, filename)

    def retry(self, job_id: str) -> dict[str, Any]:
        with self._mutex:
            previous = self.get_job(job_id)
            if previous.get("corrupt_record"):
                raise JobConflictError("cannot retry a damaged record; inspect the preserved original file")
            if self._recovering or previous["status"] not in {"failed", "interrupted"}:
                raise JobConflictError("only terminated failed/interrupted jobs can be retried")
            filename = previous["input_snapshot"]
            return self._enqueue(previous["params"], (self._job_path(job_id).parent / filename).read_bytes(), filename, job_id)

    def resume(self, job_id: str) -> dict[str, Any]:
        self._job_path(job_id)
        raise JobConflictError("mine/refute have no checkpoints; retry starts a new search from the frozen input")

    def result(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] != "completed":
            raise JobConflictError("results are available only after independent validation succeeds")
        filename = "counterexamples.json" if job["kind"] == "mine" else "search.json"
        document = _read(_path(self.project_root, f"{job['output_dir']}/{filename}"))
        allowed = self._artifact_names(job)
        return {"job": job, "summary": job["summary"], "document": document,
                "artifacts": [{"name": name, "media_type": self._media(name)} for name in allowed]}

    def _artifact_names(self, job: dict[str, Any]) -> list[str]:
        names = (["README.md", "counterexamples.json"] if job["kind"] == "mine" else
                 ["README.md", "search.json", "design.json", "counterexample.json"])
        if job["kind"] == "mine":
            names.extend(f"counterexample_{i:03d}.json" for i in range(1, job["summary"]["counts"]["selected"] + 1))
        output = _path(self.project_root, job["output_dir"])
        return [name for name in names if (output / name).is_file()]

    @staticmethod
    def _media(name: str) -> str:
        return "application/json; charset=utf-8" if name.endswith(".json") else "text/markdown; charset=utf-8"

    def result_asset(self, job_id: str, filename: str) -> tuple[bytes, str]:
        job = self.get_job(job_id)
        if job["status"] != "completed" or filename not in self._artifact_names(job):
            raise ValueError("unknown completed-job artifact")
        path = _path(self.project_root, job["output_dir"] + "/" + filename)
        return path.read_bytes(), self._media(filename)

    def _recover(self) -> bool:
        try:
            execution = _FileLock(self.root / "execution.lock")
        except JobConflictError:
            return False
        try:
            for job in self._records():
                if job["status"] == "running":
                    job.update(status="interrupted", finished_at=_now(), error="previous process ended without a terminal result; retry is manual")
                    _write(self._job_path(job["id"]), job)
            self._recovering = False
            return True
        finally:
            execution.close()

    def _work(self) -> None:
        try:
            while not self._stop.is_set():
                self._wake.clear()
                with self._mutex:
                    ready = not self._recovering or self._recover()
                    queued = [job for job in self._records() if job["status"] == "queued"] if ready else []
                    job = queued[0] if queued and not self._stop.is_set() else None
                    if job is not None:
                        job.update(status="running", owner=self._owner, started_at=_now())
                        _write(self._job_path(job["id"]), job)
                if job is None:
                    self._wake.wait(0.25)
                    continue
                try:
                    env = {**os.environ, "PYTHONPATH": str(self.project_root / "src"), "PYTHONIOENCODING": "utf-8"}
                    with (self._job_path(job["id"]).parent / "run.log").open("ab") as log:
                        process = subprocess.Popen([sys.executable, "-u", "-m", "maxcover.dashboard_jobs",
                            str(self.project_root), job["id"], self._owner], cwd=self.project_root,
                            env=env, stdout=log, stderr=subprocess.STDOUT)
                        process.wait()
                    with self._mutex:
                        current = next(item for item in self._records() if item["id"] == job["id"])
                        if current["status"] not in _TERMINAL:
                            current.update(status="failed", finished_at=_now(), error=f"worker exited without a result (code {process.returncode})")
                            _write(self._job_path(job["id"]), current)
                except Exception as error:
                    with self._mutex:
                        current = next(item for item in self._records() if item["id"] == job["id"])
                        if not current.get("corrupt_record"):
                            current.update(status="failed", finished_at=_now(), error=str(error))
                            _write(self._job_path(job["id"]), current)
        finally:
            self._owner_lock.close()

    def close(self) -> None:
        """Stop dispatching. An already running bounded job finishes normally."""
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1)


def _execute(root: Path, job_id: str, owner: str) -> int:
    """Child entry: hold the execution lock while running the existing CLI."""
    if not _ID.fullmatch(job_id):
        raise ValueError("invalid job ID")
    queue = _path(root, "results/workbench_jobs")
    execution = _FileLock(queue / "execution.lock")
    path = _path(root, f"results/workbench_jobs/{job_id}/job.json")
    try:
        job = _read(path)
        _validate_record(job, job_id)
    except (OSError, ValueError):
        execution.close()
        raise
    if job["status"] != "running" or job.get("owner") != owner:
        execution.close()
        return 2
    params = job["params"]
    terminal_lock = threading.Lock()
    finished = threading.Event()

    def timeout() -> None:
        with terminal_lock:
            if finished.is_set():
                return
            job.update(status="failed", finished_at=_now(), error="wall-clock budget exhausted; no validated result was produced")
            try:
                _write(path, job)
            finally:
                os._exit(124)

    timer = threading.Timer(params["timeout_seconds"], timeout)
    timer.daemon = True
    timer.start()
    code = 0
    try:
        output = _path(root, job["output_dir"])
        snapshot = _path(root, f"results/workbench_jobs/{job_id}/{job['input_snapshot']}")
        if job["kind"] == "mine":
            args = ["mine", "--input", str(snapshot), "--population", params["population"],
                    "--top", str(params["top"]), "--max-combinations", str(params["max_combinations"]),
                    "--max-evaluations", str(params["max_evaluations"])]
        elif job["kind"] == "refute":
            args = ["refute", "--design", str(snapshot)]
        else:
            raise ValueError("unknown task kind")
        sys.argv = [str(root / "counterexamples.py"), *args, "--output", str(output)]
        try:
            runpy.run_path(str(root / "counterexamples.py"), run_name="__main__")
        except SystemExit as error:
            if error.code not in (None, 0):
                raise ValueError(f"counterexample CLI failed with exit code {error.code}") from error
        document = _read(output / ("counterexamples.json" if job["kind"] == "mine" else "search.json"))
        job.update(status="completed", summary=_summary(job["kind"], document), error=None)
    except Exception as error:
        job.update(status="failed", error=str(error))
        print(f"Job failed: {error}", flush=True)
        code = 1
    finally:
        with terminal_lock:
            finished.set()
            timer.cancel()
            job["finished_at"] = _now()
            _write(path, job)
            execution.close()
    return code


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("internal job worker requires project root, job ID and owner")
    raise SystemExit(_execute(Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3]))
