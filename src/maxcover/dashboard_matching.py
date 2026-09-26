"""A small adapter for the independent online-matching study."""
from __future__ import annotations

import csv
from http import HTTPStatus
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Any

from .dashboard_paths import linked

STUDY = "independent_research/online_matching_recourse"
_RUN = re.compile(r"\d{8}T\d{12}Z-(?:dev|eval)\Z")
_REPORTS = {
    "results": ("六分支研究结果", "extension_20260925/报告/六分支研究结果.md"),
    "initial": ("第一阶段比较", "报告/研究报告.md"),
    "three": ("三点最优决策", "报告/三点一次预算_极小极大推导.md"),
    "chain": ("链动作与自由首步", "extension_20260925/报告/链动作与自由首步.md"),
    "budget": ("更多请求与策略拆分", "extension_20260925/报告/更多请求与策略拆分.md"),
    "random": ("随机化与原始成本", "extension_20260925/报告/随机化与原始成本.md"),
    "literature": ("文献核查", "extension_20260925/报告/补充文献核查.md"),
}
_ARTIFACTS = {"metrics.csv", "summary.json", "verification.json", "traces.json", "inputs.json"}


class MatchingError(ValueError):
    status = HTTPStatus.BAD_REQUEST


class MatchingBusy(MatchingError):
    status = HTTPStatus.CONFLICT


class OnlineMatchingService:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self._running = threading.Lock()

    def _file(self, relative: str) -> Path:
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise MatchingError("文件必须位于当前算法仓库内")
        for item in (path, *path.parents):
            if item == self.root:
                break
            if linked(item):
                raise MatchingError("研究文件不能通过链接或联接访问")
        return path

    @staticmethod
    def _json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _run_dir(self, identifier: str) -> Path:
        group, separator, name = identifier.partition("/")
        if not separator or group not in {"saved", "local"} or not _RUN.fullmatch(name):
            raise MatchingError("请选择列表中的实验结果")
        parent = f"{STUDY}/output" if group == "saved" else "results/online_matching"
        path = self._file(f"{parent}/{name}")
        if not path.is_dir():
            raise MatchingError("实验结果不存在")
        return path

    def _run_file(self, identifier: str, name: str) -> Path:
        path = self._run_dir(identifier) / name
        return self._file(path.relative_to(self.root).as_posix())

    def library(self) -> dict[str, Any]:
        available = self._file(f"{STUDY}/inputs.json").is_file()
        runs = []
        for group, parent in (("saved", f"{STUDY}/output"), ("local", "results/online_matching")):
            directory = self._file(parent)
            if not directory.is_dir():
                continue
            for child in sorted(directory.iterdir(), reverse=True):
                if not _RUN.fullmatch(child.name):
                    continue
                identifier = f"{group}/{child.name}"
                summary_file = self._run_file(identifier, "summary.json")
                if not summary_file.is_file():
                    continue
                summary = self._json(summary_file)
                all_rows = [r for r in summary["aggregates"] if r["family"] == "all"]
                runs.append({"id": identifier, "split": summary["split"],
                             "origin": "本地复现" if group == "local" else "研究归档",
                             "name": child.name,
                             "sequences": all_rows[0]["sequences"] if all_rows else 0})
        return {"available": available, "runs": runs,
                "reports": [{"id": key, "title": title} for key, (title, _) in _REPORTS.items()]}

    def detail(self, identifier: str) -> dict[str, Any]:
        summary = self._json(self._run_file(identifier, "summary.json"))
        inputs = self._json(self._run_file(identifier, "inputs.json"))
        with self._run_file(identifier, "metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        verification_file = self._run_file(identifier, "verification.json")
        verification = self._json(verification_file) if verification_file.is_file() else None
        if verification is not None:
            # The saved record describes its original run, not these mutable files.
            verification = {**verification, "recorded_status": verification.get("status"),
                            "status": "current_artifacts_not_revalidated"}
        return {"id": identifier, "summary": summary, "rows": rows, "verification": verification,
                "cases": [c for c in inputs["cases"] if c["split"] == summary["split"]]}

    def trace(self, identifier: str, case_id: str, policy: str, budget: int) -> dict[str, Any]:
        if policy not in {"nearest", "single", "priced_chain"}:
            raise MatchingError("未知匹配策略")
        if budget not in ((0,) if policy == "nearest" else (1, 2, 4)):
            raise MatchingError("该策略不支持这个改派预算")
        traces = self._json(self._run_file(identifier, "traces.json"))
        record = next((r for r in traces if r["case_id"] == case_id
                       and r["policy"] == policy and r["budget"] == budget), None)
        if record is None:
            raise MatchingError("结果中没有这个实例和策略")
        inputs = self._json(self._run_file(identifier, "inputs.json"))
        case = next(c for c in inputs["cases"] if c["id"] == case_id)
        return {"case": case, "trace": record}

    def report(self, key: str) -> dict[str, str]:
        if key not in _REPORTS:
            raise MatchingError("未知研究报告")
        title, relative = _REPORTS[key]
        return {"title": title, "text": self._file(f"{STUDY}/{relative}").read_text(encoding="utf-8")}

    def artifact(self, identifier: str, name: str) -> tuple[bytes, str]:
        if name not in _ARTIFACTS:
            raise MatchingError("未知结果文件")
        media = "text/csv; charset=utf-8" if name.endswith(".csv") else "application/json; charset=utf-8"
        return self._run_file(identifier, name).read_bytes(), media

    def run(self, payload: dict[str, object]) -> dict[str, Any]:
        if set(payload) != {"split"} or payload["split"] not in ("dev", "eval"):
            raise MatchingError("只接受固定的开发集或比较集")
        if not self._running.acquire(blocking=False):
            raise MatchingBusy("在线匹配正在计算，请等待当前结果")
        try:
            study = self._file(STUDY)
            runner = self._file(f"{STUDY}/run.py")
            verifier = self._file(f"{STUDY}/verify.py")
            output = self._file("results/online_matching")
            for filename in ("inputs.json", "input_manifest.json", "matching.py", "protocol.md"):
                if not self._file(f"{STUDY}/{filename}").is_file():
                    raise MatchingError(f"研究目录缺少 {filename}")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            options: dict[str, Any] = {"cwd": study, "capture_output": True, "text": True,
                                      "encoding": "utf-8", "env": env, "timeout": 30,
                                      "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            computed = subprocess.run([sys.executable, "-B", str(runner), "--split", str(payload["split"]),
                                       "--output-root", str(output)], **options)
            if computed.returncode:
                raise MatchingError("固定实验运行失败：" + computed.stderr[-2000:])
            directory = Path(computed.stdout.splitlines()[0]).resolve()
            if directory.parent != output.resolve() or not _RUN.fullmatch(directory.name):
                raise MatchingError("实验程序没有返回预期结果位置")
            identifier = "local/" + directory.name
            verified = subprocess.run([sys.executable, "-B", str(verifier), str(directory)], **options)
            if verified.returncode:
                raise MatchingError("本次结果未通过核验：" + verified.stderr[-2000:])
            return self.detail(identifier)
        except subprocess.TimeoutExpired as error:
            raise MatchingError("固定实验超过 30 秒，请查看本地结果目录") from error
        finally:
            self._running.release()
