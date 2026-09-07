"""Frozen F3 inputs and identities; no graph objectives or inference."""
from __future__ import annotations

import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover.model import MaximumCoverageInstance
from maxcover.reproducibility import instance_id
from r2_design import seed_for, read_json

VERSION = "r3-first-step-confirm-v1"


def tasks_for(version, count, fixture=False):
    prefix = "r3-fixture" if fixture else "r3-confirm"
    return [{"base_graph_id": f"{prefix}-r{i:04d}", "repetition": i,
             "seed": seed_for(version, 12, 3, i),
             "chains": [{"direction": side, "replica": rep,
                         "seed": seed_for(version, 12, 3, i, f"chain-{side}-{rep}")}
                        for side in (-1, 1) for rep in range(2)]} for i in range(count)]


def validate_configuration(config):
    fixture = config.get("phase") == "fixture"
    count = config.get("sample_count")
    if type(count) is not int or (not fixture and count != 3000) or (fixture and not 1 <= count <= 8):
        raise ValueError("F3 sample count differs from the frozen design")
    expected = {"version": VERSION + ("-fixture" if fixture else ""),
                "phase": "fixture" if fixture else "confirmation", "n": 12, "m": 12, "d": 3, "k": 4,
                "unique_sets": False, "coupling_seed": None, "proposals": 2048,
                "replicas_per_direction": 2, "accept_equal": True,
                "primary": "mean_base_graph_difference_in_first_step_irrecoverability", "alpha": .05,
                "interval": "two_sided_hoeffding_range_minus_one_plus_one",
                "witness": "exactly_k_sorted_lexicographically_smallest",
                "limits": {"wall_seconds": 3600, "memory_bytes": 6 * 1024**3, "output_bytes": 2 * 1024**3}}
    for key, value in expected.items():
        if type(config.get(key)) is not type(value) or config.get(key) != value:
            raise ValueError(f"F3 {key} differs from the frozen design")
    if not math.isclose(config.get("interval_half_width", -1), math.sqrt(2 * math.log(40) / count), rel_tol=1e-14):
        raise ValueError("incorrect F3 interval half width")
    if config.get("tasks") != tasks_for(expected["version"], count, fixture):
        raise ValueError("F3 task identities, graph seeds or chain seeds differ")
    seeds = [t["seed"] for t in config["tasks"]] + [c["seed"] for t in config["tasks"] for c in t["chains"]]
    if len(seeds) != len(set(seeds)):
        raise ValueError("F3 seeds must be distinct")
    return config


def identity(sets, task, config, chain=None):
    if chain is None:
        family, seed = "fixed_size", task["seed"]
        parameters = {"set_size": config["d"], "unique_sets": False}
    else:
        family, seed = "custom", chain["seed"]
        parameters = {"r3_version": config["version"], "base_graph_id": task["base_graph_id"],
                      "direction": chain["direction"], "replica": chain["replica"]}
    instance = MaximumCoverageInstance(config["n"], tuple(sum(1 << a for a in s) for s in sets),
                                       config["k"], family, seed, parameters)
    return instance_id(instance)


def load_records(output, config, partial=False):
    output = Path(output)
    expected = {t["base_graph_id"] for t in config["tasks"]}
    actual = {p.stem for p in (output / "graphs").glob("*.json")}
    if actual - expected or (not partial and actual != expected):
        raise ValueError("F3 graph checkpoints are missing or unexpected")
    records = []
    for task in config["tasks"]:
        path = output / "graphs" / (task["base_graph_id"] + ".json")
        if path.exists():
            record = read_json(path)
            if record.get("task") != task or record.get("status") != "complete":
                raise ValueError("F3 checkpoint task or completion status differs")
            membership = [{k: c[k] for k in ("direction", "replica", "seed")} for c in record["chains"]]
            if membership != task["chains"] or any(len(c["endpoints"]) != 1 or c["endpoints"][0]["proposals"] != 2048 for c in record["chains"]):
                raise ValueError("F3 checkpoint chains or proposal counts differ")
            records.append(record)
    return records
