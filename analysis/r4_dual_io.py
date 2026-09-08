"""DUAL configuration, immutable reference association and checkpoint I/O.

No upper-bound or optimum calculation is shared with the verifier.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from r2_design import read_json, write_json, validate_design
from r4_inputs import instance, source_record, output_size, check_resources

VERSION = "r4-l5-dual-v1"
SOURCE_COMMIT = "1a8b1899d927cba202cf7931fe992ecd2b5a1807"
R2_COMMIT = "4a419f338d70068fa988fa97027734cdcda0a036"
LIMITS = {"workers": 1, "wall_seconds": 3600, "memory_bytes": 6 * 1024**3,
          "output_bytes": 2 * 1024**3}
METRICS = ("tightening_initial", "tightening_prefix", "ratio_gain_initial", "ratio_gain_prefix",
           "dual_over_optimum", "dual_ratio", "prefix_ratio", "initial_ratio")
CODE_PATHS = ("analysis/r4_dual.py", "analysis/r4_dual_core.py", "analysis/r4_dual_io.py",
              "analysis/validate_r4_dual.py", "analysis/r4_inputs.py", "analysis/r2_design.py",
              "analysis/validate_r2_budget_grid.py", "src/maxcover")


def configuration(phase, source_design):
    validate_design(source_design)
    if phase not in {"fixture", "preflight", "comparison"}:
        raise ValueError("unknown DUAL phase")
    expected = {"fixture": "fixture", "preflight": "preflight", "comparison": "exploration"}[phase]
    if source_design["phase"] != expected:
        raise ValueError("DUAL/source phase mismatch")
    if phase == "comparison" and source_design != read_json(ROOT / "analysis/r2_f2_config.json"):
        raise ValueError("comparison requires the complete immutable R2 design")
    if phase == "preflight" and (source_design["n_values"], source_design["d_values"],
                                  source_design["repetitions"]) != ([12, 16, 20], [2, 3, 4], 2):
        raise ValueError("preflight requires 18 independent graphs across all nine cells")
    return {"version": VERSION, "phase": phase, "source_commit": SOURCE_COMMIT if phase == "comparison" else None,
            "r2_commit": R2_COMMIT if phase == "comparison" else None,
            "source_design": source_design, "tasks": source_design["tasks"], "limits": dict(LIMITS),
            "method": {"outer": 4, "inner": 3, "conditions": "all_greedy_prefixes_0_to_k",
                       "residual_budget": "full_k", "arithmetic": "integer",
                       "sort": "descending_residual_size_then_original_index"},
            "statistics": {"unit": "original_graph_with_paired_budgets", "inference": "retrospective_descriptive",
                           "metrics": list(METRICS), "summaries": ["mean", "median", "p90_nearest_rank"],
                           "zero_denominator": None},
            "reference_policy": "immutable_published_exact_reference" if phase == "comparison" else "independent_enumeration"}


def validate_configuration(config):
    expected = configuration(config["phase"], config["source_design"])
    for name, value in expected.items():
        if config.get(name) != value:
            raise ValueError(f"DUAL configuration differs: {name}")
    if config["phase"] == "comparison":
        if config.get("design_status") != "frozen" or not re.fullmatch("[0-9a-f]{40}", config.get("code_revision", "")):
            raise ValueError("comparison requires a frozen design and source commit")
        decision = config.get("resource_decision", {})
        for key, limit in (("conservative_wall_seconds", config["limits"]["wall_seconds"]),
                           ("conservative_peak_memory_bytes", config["limits"]["memory_bytes"]),
                           ("conservative_output_bytes", config["limits"]["output_bytes"])):
            value = decision.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= limit:
                raise ValueError(f"missing or excessive resource decision: {key}")
    return config


def check_code_revision(config, root=ROOT):
    """Bind formal/resumed work to its committed calculation and input code.

    Config and prose may be committed later. Unrelated local files are allowed;
    only the actual calculation/input dependency paths are compared to the
    declared revision. This is execution provenance, not a publication freeze.
    """
    if config["phase"] != "comparison":
        return
    revision = config["code_revision"]
    prefix = ["git", "--no-replace-objects", "-C", str(root)]
    tree = subprocess.run(prefix + ["ls-tree", "-r", "--name-only", revision, "--", *CODE_PATHS],
                          capture_output=True, text=True)
    names = set(tree.stdout.splitlines())
    if tree.returncode or not set(CODE_PATHS[:-1]) <= names or not any(n.startswith("src/maxcover/") for n in names):
        raise ValueError("declared DUAL source revision lacks the runnable implementation")
    changed = subprocess.run(prefix + ["diff", "--quiet", revision, "--", *CODE_PATHS], capture_output=True)
    if changed.returncode:
        raise ValueError("DUAL calculation/input code differs from the frozen source revision")
    untracked = subprocess.run(prefix + ["ls-files", "--others", "--exclude-standard", "--", *CODE_PATHS],
                               capture_output=True, text=True)
    if untracked.returncode or any(name.endswith(".py") for name in untracked.stdout.splitlines()):
        raise ValueError("uncommitted Python calculation/input code is outside the frozen source revision")


def _process_is_live(pid):
    """Return OS-observed liveness; permission uncertainty prevents recovery."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("invalid active operation process identity")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: the PID no longer exists.
                return False
            raise RuntimeError(f"cannot establish active process liveness: Windows error {error}")
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise RuntimeError("cannot read active process state")
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as error:
        raise RuntimeError("cannot establish active process liveness") from error
    return True


class RuntimeBudget:
    """Account DUAL commands and recover conservatively after a hard stop.

    Normal wall time includes checkpoint I/O.  A hard kill leaves the last
    measured elapsed time and the UTC start.  Recovery charges through the
    recovery instant, including possible downtime, and labels that charge
    separately from measured wall time.  A live PID is never recovered.
    """
    def __init__(self, output, design, operation):
        self.output, self.design, self.operation = Path(output), design, operation
        self.log = self.output / "execution.jsonl"
        self.active_path = self.output / "active_operation.json"
        self.lock_handle = None
        self.active = None
        self.prior = 0.0
        self.history_ids = set()

    def _read_history(self):
        # Read only after acquiring the OS lock: another command may have
        # finished between construction of this object and entry.
        self.prior = 0.0
        self.history_ids = set()
        if self.log.exists():
            for line in self.log.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                measured = entry["wall_seconds"]
                charged = entry.get("charged_wall_seconds", measured)
                if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                        for value in (measured, charged)) or charged < measured):
                    raise ValueError("invalid DUAL execution resource history")
                self.prior += charged
                if "operation_id" in entry:
                    if entry["operation_id"] in self.history_ids:
                        raise ValueError("duplicate DUAL operation accounting")
                    self.history_ids.add(entry["operation_id"])

    def _acquire_lock(self):
        handle = (self.output / ".operation.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError("DUAL output has a live operation lock; do not resume concurrently") from error
        self.lock_handle = handle

    def _release_lock(self):
        if self.lock_handle is not None:
            # Closing releases the OS-held lock, including on hard process
            # termination. Keep the path so its inode cannot change mid-race.
            self.lock_handle.close()
            self.lock_handle = None

    def _append(self, entry):
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, allow_nan=False) + "\n")
            handle.flush()

    def __enter__(self):
        self.output.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        try:
            return self._enter_owned()
        except BaseException:
            self._release_lock()
            raise

    def _enter_owned(self):
        self._read_history()
        if self.active_path.exists():
            active = read_json(self.active_path)
            if _process_is_live(active["pid"]):
                raise RuntimeError("DUAL output has a live operation; do not resume concurrently")
            elapsed, began = active["elapsed_seconds"], active["started_epoch_seconds"]
            if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                    for value in (elapsed, began)) or began > time.time()):
                raise ValueError("invalid interrupted DUAL resource checkpoint")
            if active["operation_id"] not in self.history_ids:
                charged = max(elapsed, time.time() - began)
                self._append({"operation": active["operation"], "operation_id": active["operation_id"],
                              "wall_seconds": elapsed, "charged_wall_seconds": charged,
                              "unmeasured_tail_seconds_upper_bound": charged - elapsed,
                              "status": "recovered_hard_interruption"})
                self.prior += charged
            self.active_path.unlink()
        self.started = time.perf_counter()
        self.active = {"operation": self.operation, "operation_id": uuid.uuid4().hex,
                       "pid": os.getpid(), "started_epoch_seconds": time.time(), "elapsed_seconds": 0.0}
        # Exclusive creation prevents two newly launched commands from claiming
        # the same otherwise empty output at the same time.
        with self.active_path.open("x", encoding="utf-8") as handle:
            json.dump(self.active, handle, allow_nan=False)
        try:
            self.check()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def check(self):
        elapsed = time.perf_counter() - self.started
        self.active["elapsed_seconds"] = elapsed
        write_json(self.active_path, self.active)
        if self.prior + elapsed >= self.design["limits"]["wall_seconds"]:
            raise RuntimeError("cumulative DUAL wall budget exhausted; preserve checkpoints")

    def __exit__(self, kind, value, traceback):
        try:
            elapsed = time.perf_counter() - self.started
            self._append({"operation": self.operation, "operation_id": self.active["operation_id"],
                          "wall_seconds": elapsed, "charged_wall_seconds": elapsed,
                          "status": "complete" if kind is None else "interrupted"})
            self.active_path.unlink()
        finally:
            self.active = None
            self._release_lock()


class SourceAccess:
    """Read formal inputs from fixed Git objects, never a mutable passed flag.

    The source commit contains both the published R2 inputs and F4 reference
    copies. Their exact equality, regenerated seed and public instance identity
    are checked. The new verifier checks witness coverage and bound arithmetic.
    """
    def __init__(self, source, config):
        self.source, self.config, self.process = Path(source), config, None

    def __enter__(self):
        try:
            if self.config["phase"] == "comparison":
                self.process = subprocess.Popen(["git", "--no-replace-objects", "-C", str(self.source), "cat-file", "--batch"],
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                design = self._json("results/r4_source/results/r2_grid_v1/config.json")
                baseline = self._json("results/r4_calibration_v1/config.json")
                if baseline["source_design"] != design or baseline["source_commit"] != R2_COMMIT:
                    raise ValueError("published baseline/source design association differs")
            else:
                design = read_json(self.source / "config.json")
            if design != self.config["source_design"]:
                raise ValueError("source design differs")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _json(self, path):
        request = f"{SOURCE_COMMIT}:{path}\n".encode("utf-8")
        self.process.stdin.write(request)
        self.process.stdin.flush()
        header = self.process.stdout.readline().split()
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError("immutable published source object is unavailable")
        data = self.process.stdout.read(int(header[2]))
        if self.process.stdout.read(1) != b"\n":
            raise ValueError("truncated source object")
        return json.loads(data)

    def record(self, task):
        if self.config["phase"] != "comparison":
            row = source_record(self.source, task)
            return {**row, "baseline_values": None}
        name = task["base_graph_id"] + ".json"
        raw = self._json("results/r4_source/results/r2_grid_v1/graphs/" + name)
        baseline = self._json("results/r4_calibration_v1/graphs/" + name)
        row = {key: raw[key] for key in ("task", "sets", "values")}
        if (raw["status"] != "complete" or raw["task"] != task or baseline["task"] != task
                or baseline["status"] != "complete" or baseline["source"] != row
                or baseline["source_commit"] != R2_COMMIT or baseline["version"] != "r4-prefix-bound-v1"):
            raise ValueError("immutable reference/baseline association differs")
        # Same input/identity infrastructure as F4, without accepting live data.
        from maxcover._generators_random import fixed_size
        from maxcover.reproducibility import instance_id
        generated = fixed_size(universe_size=task["n"], set_count=task["n"], k=1,
                               set_size=task["d"], unique_sets=False, seed=task["seed"])
        if instance(row["sets"], task, 1).sets != generated.sets:
            raise ValueError("published sets differ from frozen seed")
        if [v["k"] for v in row["values"]] != task["budgets"]:
            raise ValueError("published budget records missing")
        for value in row["values"]:
            if value["instance_id"] != instance_id(instance(row["sets"], task, value["k"])):
                raise ValueError("published instance identity differs")
        return {**row, "baseline_values": baseline["values"]}

    def __exit__(self, *_):
        if self.process is not None:
            self.process.stdin.close()
            self.process.stdout.close()
            self.process.wait(timeout=10)
            self.process = None


def load_records(output, config, partial=False):
    """Yield one graph at a time in fixed order; never trust run_status alone."""
    paths = {p.stem: p for p in (Path(output) / "graphs").glob("*.json")}
    expected = {t["base_graph_id"] for t in config["tasks"]}
    if set(paths) - expected or (not partial and set(paths) != expected):
        raise ValueError("missing or unexpected DUAL graph checkpoints")
    for task in config["tasks"]:
        if task["base_graph_id"] in paths:
            row = read_json(paths[task["base_graph_id"]])
            if row["task"] != task or row["status"] != "complete":
                raise ValueError("checkpoint task/completion differs")
            yield row


def write_checkpoint(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
