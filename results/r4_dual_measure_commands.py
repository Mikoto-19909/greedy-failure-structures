"""Local R4 DUAL command evidence: four fixed CLI stages and Windows memory sampling.

The formal data directory is created by the producer. Logs live in its sibling
<output>_commands directory so measurement does not invalidate a fresh output.
This script does not generate inputs, select samples or alter the fixed design.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("production", "verification", "analysis", "derived")


class ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class WindowsProcessTree:
    def __init__(self, root_pid):
        if os.name != "nt":
            raise RuntimeError("this local measurement helper requires Windows")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        for name in ("Process32FirstW", "Process32NextW"):
            function = getattr(self.kernel, name)
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
            function.restype = wintypes.BOOL
        self.kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetExitCodeProcess.restype = wintypes.BOOL
        self.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        self.psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        self.root_pid = root_pid
        self.handles = {}
        self.processes = {}
        self.sample_count = 0
        self.peak_simultaneous = 0
        self.errors = []

    def snapshot(self):
        handle = self.kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "cannot enumerate measurement process tree")
        entries = {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            available = self.kernel.Process32FirstW(handle, ctypes.byref(entry))
            while available:
                entries[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
                available = self.kernel.Process32NextW(handle, ctypes.byref(entry))
        finally:
            self.kernel.CloseHandle(handle)
        return entries

    def sample(self):
        entries = self.snapshot()
        descendants = {self.root_pid, *self.handles}
        while True:
            added = {pid for pid, (parent, _) in entries.items() if parent in descendants} - descendants
            if not added:
                break
            descendants.update(added)
        for pid in sorted(descendants - self.handles.keys()):
            if pid not in entries:
                continue
            handle = self.kernel.OpenProcess(0x1010, False, pid)  # query limited + VM read
            if not handle:
                error = {"pid": pid, "operation": "OpenProcess", "windows_error": ctypes.get_last_error()}
                if error not in self.errors:
                    self.errors.append(error)
                continue
            parent, executable = entries[pid]
            self.handles[pid] = handle
            self.processes[pid] = {"pid": pid, "parent_pid": parent, "executable": executable,
                                   "sampled_peak_working_set_bytes": 0,
                                   "lifetime_peak_working_set_bytes": 0, "samples": 0}
        simultaneous, living = 0, False
        for pid, handle in self.handles.items():
            code = wintypes.DWORD()
            if self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                living = living or code.value == 259
            counters = MemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if self.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                row = self.processes[pid]
                row["samples"] += 1
                row["sampled_peak_working_set_bytes"] = max(row["sampled_peak_working_set_bytes"], counters.WorkingSetSize)
                row["lifetime_peak_working_set_bytes"] = max(row["lifetime_peak_working_set_bytes"], counters.PeakWorkingSetSize)
                simultaneous += counters.WorkingSetSize
        self.sample_count += 1
        self.peak_simultaneous = max(self.peak_simultaneous, simultaneous)
        return living

    def result(self):
        return {"sample_count": self.sample_count,
                "sampled_peak_simultaneous_tree_working_set_bytes": self.peak_simultaneous,
                "sum_observed_process_peak_counters_bytes": sum(row["lifetime_peak_working_set_bytes"]
                                                                    for row in self.processes.values()),
                "observed_processes": list(self.processes.values()), "measurement_errors": self.errors,
                "memory_scope": "observed command root and full descendant tree, including Python launcher and Git; monitor excluded",
                "memory_limitations": "Sampling can miss short processes and final between-sample spikes. Simultaneous values are sequential near-simultaneous working-set observations; shared pages may count in more than one process. Summed observed OS peak counters are not an exact process-tree upper bound or measured simultaneous memory."}

    def close(self):
        for handle in self.handles.values():
            self.kernel.CloseHandle(handle)
        self.handles.clear()


def run_command(name, command, evidence_directory, *, cwd=ROOT, interval=0.1):
    """Run one child command, preserve logs and return its actual exit/measurements."""
    evidence_directory = Path(evidence_directory)
    evidence_directory.mkdir(parents=True, exist_ok=True)
    identity = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    log_path = evidence_directory / (name + "-" + identity + ".log")
    result = {"stage": name, "command": [str(item) for item in command], "cwd": str(Path(cwd).resolve()),
              "started_utc": datetime.now(timezone.utc).isoformat(), "log_path": str(log_path.resolve()),
              "sampling_interval_seconds": interval}
    started = time.perf_counter()
    tree = None
    try:
        with log_path.open("wb") as log:
            child = subprocess.Popen(result["command"], cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            tree = WindowsProcessTree(child.pid)
            while True:
                living = tree.sample()
                if child.poll() is not None and not living:
                    break
                time.sleep(interval)
            result["exit_code"] = child.wait()
            result.update(tree.result())
    finally:
        if tree is not None:
            tree.close()
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        result["complete_process_wall_seconds"] = time.perf_counter() - started
        result["timing_scope"] = "Popen, full command process tree lifetime, monitor sampling and log close; includes monitoring overhead. Stage wall is not added again to internal component costs."
        with (evidence_directory / "command_runs.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/r4_dual_comparison_v1")
    parser.add_argument("--source", type=Path, default=ROOT / "results/frozen-r4-calibration-v1")
    parser.add_argument("--config", type=Path, default=ROOT / "analysis/r4_dual_config.json")
    parser.add_argument("--start-at", choices=STAGES, default="production")
    args = parser.parse_args(argv)
    python = str(ROOT / ".venv/Scripts/python.exe")
    output, source, config = map(lambda value: str(value.resolve()), (args.output, args.source, args.config))
    evidence = Path(output).with_name(Path(output).name + "_commands")
    commands = [
        [python, "analysis/r4_dual.py", "run", "--config", config, "--source", source, "--output", output],
        [python, "analysis/validate_r4_dual.py", "--source", source, "--output", output],
        [python, "analysis/r4_dual.py", "analyze", "--source", source, "--output", output],
        [python, "analysis/validate_r4_dual.py", "--summaries-only", "--output", output],
    ]
    if (Path(output) / "config.json").exists():
        commands[0].append("--resume")
    for index in range(STAGES.index(args.start_at), len(STAGES)):
        result = run_command(STAGES[index], commands[index], evidence)
        print(json.dumps({key: result[key] for key in ("stage", "exit_code", "complete_process_wall_seconds",
                                                        "sampled_peak_simultaneous_tree_working_set_bytes")}), flush=True)
        if result["exit_code"]:
            return result["exit_code"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
