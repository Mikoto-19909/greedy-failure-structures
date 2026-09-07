"""R2 input design and file I/O; no objective or statistical calculations."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

VERSION = "r2-budget-v1"
LAMBDA = ((1, 4), (1, 2), (3, 4), (1, 1), (3, 2), (2, 1))


def seed_for(phase, n, d, repetition, purpose="graph"):
    text = json.dumps([VERSION, phase, n, d, repetition, purpose], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def budgets(n, d):
    return sorted({1, n, *(min(n, (a * n + b * d - 1) // (b * d)) for a, b in LAMBDA)})


def make_design(phase, ns=(12, 16, 20), ds=(2, 3, 4), repetitions=200, diagnostic_count=32):
    tasks = [{"base_graph_id": f"r2-{phase}-n{n}-d{d}-r{r:04d}", "n": n, "d": d,
              "repetition": r, "seed": seed_for(phase, n, d, r), "budgets": budgets(n, d),
              "diagnostic_k": math.ceil(n / d) if r < diagnostic_count else None}
             for n in ns for d in ds for r in range(repetitions)]
    design = {"version": VERSION, "phase": phase, "n_values": list(ns), "d_values": list(ds),
              "repetitions": repetitions, "diagnostic_count": diagnostic_count,
              "model": {"family": "fixed_size", "unique_sets": False, "coupling_seed": None},
              "witness": "exactly_k_sorted_lexicographically_smallest",
              "diagnostics": {"max_completions": 200000, "max_two_swap_evaluations": 100000},
              "statistics": {"bootstrap_repetitions": 10000, "confidence": 0.95},
              "limits": {"workers": 4, "wall_seconds": 43200, "memory_bytes": 6 * 1024**3,
                         "output_bytes": 2 * 1024**3}, "tasks": tasks}
    validate_design(design)
    return design


def validate_design(design):
    if design.get("version") != VERSION or design.get("phase") not in {"preflight", "exploration", "fixture"}:
        raise ValueError("unknown R2 version or phase")
    for name in ("n_values", "d_values"):
        values = design[name]
        if not values or len(set(values)) != len(values) or any(type(v) is not int or v < 1 for v in values):
            raise ValueError(f"invalid {name}")
    if max(design["n_values"]) > 20 or max(design["d_values"]) > min(design["n_values"]):
        raise ValueError("R2 requires d <= N <= 20")
    for name in ("repetitions", "diagnostic_count"):
        if type(design[name]) is not int or design[name] < (1 if name == "repetitions" else 0):
            raise ValueError(f"invalid {name}")
    if design["diagnostic_count"] > design["repetitions"]:
        raise ValueError("diagnostic count exceeds population")
    if design["model"] != {"family": "fixed_size", "unique_sets": False, "coupling_seed": None}:
        raise ValueError("R2 must use independent fixed-size sampling, allowing duplicate sets")
    if design["witness"] != "exactly_k_sorted_lexicographically_smallest":
        raise ValueError("unsupported witness contract")
    if design["diagnostics"] != {"max_completions": 200000, "max_two_swap_evaluations": 100000}:
        raise ValueError("diagnostic limits differ from the approved R1 limits")
    if design["statistics"] != {"bootstrap_repetitions": 10000, "confidence": 0.95}:
        raise ValueError("statistics differ from the approved R2 design")
    limits = design["limits"]
    if (type(limits["workers"]) is not int or not 1 <= limits["workers"] <= 4
            or limits["wall_seconds"] != 43200 or limits["memory_bytes"] != 6 * 1024**3
            or limits["output_bytes"] != 2 * 1024**3):
        raise ValueError("resource limits differ from the approved budget")
    expected = [(n, d, r) for n in design["n_values"] for d in design["d_values"]
                for r in range(design["repetitions"])]
    actual = [(t["n"], t["d"], t["repetition"]) for t in design["tasks"]]
    if actual != expected:
        raise ValueError("incomplete, reordered or duplicate design tasks")
    for t in design["tasks"]:
        n, d, r = t["n"], t["d"], t["repetition"]
        expected_task = {"base_graph_id": f"r2-{design['phase']}-n{n}-d{d}-r{r:04d}", "n": n, "d": d,
                         "repetition": r, "seed": seed_for(design["phase"], n, d, r),
                         "budgets": budgets(n, d),
                         "diagnostic_k": math.ceil(n / d) if r < design["diagnostic_count"] else None}
        if t != expected_task:
            raise ValueError("task seed, budget, identity or diagnostic membership differs")
    if len({t["seed"] for t in design["tasks"]}) != len(expected):
        raise ValueError("duplicate graph seeds")
    return design


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_records(output, design, partial=False):
    directory = Path(output) / "graphs"
    expected = {t["base_graph_id"] for t in design["tasks"]}
    actual = {p.stem for p in directory.glob("*.json")}
    if actual - expected or (not partial and actual != expected):
        raise ValueError("missing or unexpected graph checkpoints")
    rows = []
    for task in design["tasks"]:
        path = directory / (task["base_graph_id"] + ".json")
        if path.exists():
            row = read_json(path)
            if row.get("task") != task or row.get("status") != "complete":
                raise ValueError(f"checkpoint is incomplete or belongs to another task: {path.name}")
            if [v["k"] for v in row["values"]] != task["budgets"]:
                raise ValueError("checkpoint budgets are incomplete")
            rows.append(row)
    return rows


class RuntimeBudget:
    """Cumulative batch wall time, including recovery, validation and summaries."""
    def __init__(self, output, design, operation):
        self.output, self.design, self.operation = Path(output), design, operation
        path = self.output / "execution.jsonl"
        self.prior = sum(json.loads(line)["wall_seconds"] for line in path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
        self.prior += design.get("f2_resource_decision", {}).get("preflight_wall_seconds", 0)
        self.started = time.perf_counter()

    def check(self):
        if self.prior + time.perf_counter() - self.started >= self.design["limits"]["wall_seconds"]:
            raise RuntimeError("cumulative research wall budget exhausted; preserve samples and resume state")

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, kind, value, traceback):
        entry = {"operation": self.operation, "wall_seconds": time.perf_counter() - self.started,
                 "status": "complete" if kind is None else "interrupted"}
        with (self.output / "execution.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def computed_results(function, arguments, workers, budget):
    if workers == 1:
        for item in arguments:
            budget.check()
            yield function(*item)
        return
    iterator = iter(arguments)
    executor = ProcessPoolExecutor(max_workers=workers)
    pending = set()
    try:
        for _ in range(workers):
            item = next(iterator, None)
            if item is not None:
                pending.add(executor.submit(function, *item))
        while pending:
            budget.check()
            ready, pending = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
            for future in ready:
                yield future.result()
                budget.check()
                item = next(iterator, None)
                if item is not None:
                    pending.add(executor.submit(function, *item))
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
