"""R4 source association and batch I/O; no bound or optimum calculations."""
from __future__ import annotations

from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_id
from maxcover._generators_random import fixed_size
from r2_design import read_json, write_json, validate_design
from r2_design import RuntimeBudget as _RuntimeBudget

VERSION = "r4-prefix-bound-v1"
SOURCE_COMMIT = "4a419f338d70068fa988fa97027734cdcda0a036"
LIMITS = {"workers": 1, "wall_seconds": 3600, "memory_bytes": 6 * 1024**3,
          "output_bytes": 2 * 1024**3}
STATISTICS = {"unit": "original_graph_with_paired_budgets", "inference": "fixed_corpus_descriptive",
              "summaries": ["mean", "median", "p90_nearest_rank"], "zero_denominator": None}


class RuntimeBudget(_RuntimeBudget):
    def __init__(self, output, design, operation):
        super().__init__(output, design, operation)
        preflight = design.get("resource_decision", {}).get("preflight_wall_seconds", 0)
        if not isinstance(preflight, (int, float)) or not math.isfinite(preflight) or preflight < 0:
            raise ValueError("invalid preflight consumed time")
        self.prior += preflight


def configuration(phase, source_design):
    source_design = validate_design(source_design)
    if phase not in {"preflight", "calibration", "fixture"}:
        raise ValueError("unknown R4 phase")
    expected_phase = {"preflight": "preflight", "calibration": "exploration", "fixture": "fixture"}[phase]
    if source_design["phase"] != expected_phase:
        raise ValueError("R4 phase conflicts with source")
    if phase != "fixture":
        repetitions = 8 if phase == "preflight" else 200
        if (source_design["n_values"], source_design["d_values"], source_design["repetitions"]) != ([12, 16, 20], [2, 3, 4], repetitions):
            raise ValueError("R4 requires the complete planned R2 source design")
    tasks = [t for t in source_design["tasks"] if phase != "preflight" or t["repetition"] < 2]
    return {"version": VERSION, "phase": phase, "source_commit": SOURCE_COMMIT,
            "source_design": source_design, "tasks": tasks, "limits": dict(LIMITS),
            "bound": "min(union_size, coverage(prefix_t)+k*max_gain(prefix_t), t=0..k)",
            "witness": "lowest_index_gain_witness;exactly_k_sorted_lexicographic_optimum",
            "statistics": dict(STATISTICS)}


def validate_configuration(config):
    expected = configuration(config["phase"], config["source_design"])
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(f"R4 configuration differs: {key}")
    return config


def instance(elements, task, k):
    if type(k) is not int or not 1 <= k <= len(elements):
        raise ValueError("invalid budget")
    n = task["n"]
    if type(n) is not int or n < 1 or len(elements) != n:
        raise ValueError("invalid R2 dimensions")
    for s in elements:
        if (not isinstance(s, list) or any(type(a) is not int or not 0 <= a < n for a in s)
                or s != sorted(set(s)) or len(s) != task["d"]):
            raise ValueError("invalid source candidate elements or size")
    return MaximumCoverageInstance(n, tuple(sum(1 << a for a in s) for s in elements), k,
                                   "fixed_size", task["seed"],
                                   {"set_size": task["d"], "unique_sets": False})


def source_record(source, task):
    row = read_json(Path(source) / "graphs" / (task["base_graph_id"] + ".json"))
    if row["task"] != task or row["status"] != "complete":
        raise ValueError("source identity or completion differs")
    values = row["values"]
    if [v["k"] for v in values] != task["budgets"]:
        raise ValueError("source budgets are incomplete")
    # Reproduce the fixed source seed only to check association. Never save a
    # replacement input, and do not trust a self-consistent edited instance_id.
    canonical = fixed_size(universe_size=task["n"], set_count=task["n"], k=1,
                           set_size=task["d"], unique_sets=False, seed=task["seed"])
    if instance(row["sets"], task, 1).sets != canonical.sets:
        raise ValueError("source sets differ from the frozen R2 seed")
    for v in values:
        item = instance(row["sets"], task, v["k"])
        if v["instance_id"] != instance_id(item) or v["reference_status"] != "optimal":
            raise ValueError("source instance identity or exact reference status differs")
    return {"task": task, "sets": row["sets"], "values": values}


def check_source(source, config):
    if read_json(Path(source) / "config.json") != config["source_design"]:
        raise ValueError("source design association differs")


def load_records(output, config, partial=False):
    paths = {p.stem: p for p in (Path(output) / "graphs").glob("*.json")}
    expected = {t["base_graph_id"] for t in config["tasks"]}
    if set(paths) - expected or (not partial and set(paths) != expected):
        raise ValueError("missing or unexpected R4 graph checkpoints")
    records = []
    for task in config["tasks"]:
        if task["base_graph_id"] not in paths:
            continue
        row = read_json(paths[task["base_graph_id"]])
        if row["task"] != task or row["status"] != "complete":
            raise ValueError("R4 checkpoint association or completion differs")
        records.append(row)
    return records


def output_size(output):
    return sum(p.stat().st_size for p in Path(output).rglob("*") if p.is_file())


def check_resources(output, config, peak_memory):
    if peak_memory > config["limits"]["memory_bytes"]:
        raise RuntimeError("R4 memory budget exhausted; preserve checkpoints")
    if output_size(output) > config["limits"]["output_bytes"]:
        raise RuntimeError("R4 output budget exhausted; preserve checkpoints")
