"""Finite, degree-preserving exposure probes; no confirmation-run command."""
from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from maxcover._generators_random import fixed_size
from maxcover.algorithms import brute_force, greedy
from maxcover.model import MaximumCoverageInstance
from r2_design import seed_for, read_json, write_json

VERSION = "r3-exposure-probe-v1"


def probe_config():
    return {"version": VERSION, "phase": "feasibility_only", "n": 12, "d": 3, "k": 4,
            "replicas": 2, "steps": [128, 512, 2048], "wall_seconds": 3600,
            "tasks": [{"base_graph_id": f"r3-probe-r{i:04d}", "repetition": i,
                       "seed": seed_for(VERSION, 12, 3, i)} for i in range(16)]}


def exposure(sets, frequencies):
    return sum(frequencies[a] - 1 for a in sets[0])


def construct(original, n, seed, direction, steps):
    if direction not in (-1, 1) or steps != sorted(set(steps)) or not steps or steps[0] < 1:
        raise ValueError("invalid exposure direction or proposal checkpoints")
    sets = [set(s) for s in original]
    frequencies = [sum(a in s for s in sets) for a in range(n)]
    rng = random.Random(seed)
    accepted, endpoints = [], []
    legal = 0
    for proposal in range(1, steps[-1] + 1):
        i, j = rng.sample(range(len(sets)), 2)
        a, b = rng.sample(range(n), 2)
        bits = (a in sets[i], b in sets[i], a in sets[j], b in sets[j])
        if bits in ((True, False, False, True), (False, True, True, False)):
            legal += 1
            before = exposure(sets, frequencies)
            sets[i].symmetric_difference_update((a, b))
            sets[j].symmetric_difference_update((a, b))
            if direction * (exposure(sets, frequencies) - before) >= 0:
                accepted.append([proposal, i, j, a, b])
            else:
                sets[i].symmetric_difference_update((a, b))
                sets[j].symmetric_difference_update((a, b))
        if proposal in steps:
            endpoints.append({"proposals": proposal, "sets": [sorted(s) for s in sets],
                              "exposure": exposure(sets, frequencies), "legal": legal, "accepted": len(accepted)})
    return {"seed": seed, "direction": direction, "moves": accepted, "endpoints": endpoints}


def evaluate(sets, n, k):
    masks = tuple(sum(1 << a for a in s) for s in sets)
    instance = MaximumCoverageInstance(n, masks, k)
    best = brute_force(instance, time_limit_seconds=None)
    greedy_result = greedy(instance)
    forced, witness = -1, None
    for rest in combinations(range(1, len(sets)), k - 1):
        indices = (0, *rest)
        value = instance.coverage(indices)
        if value > forced:
            forced, witness = value, list(indices)
    return {"greedy": greedy_result.coverage, "greedy_selected": list(greedy_result.selected),
            "optimum": best.coverage, "optimum_selected": list(best.selected),
            "forced_optimum": forced, "forced_selected": witness, "first_loss": forced < best.coverage}


def run_probe(config, output):
    if config != probe_config():
        raise ValueError("only the declared feasibility probe is authorized by this entry")
    output = Path(output)
    if output.exists():
        raise ValueError("probe output already exists")
    started = time.perf_counter()
    write_json(output / "config.json", config)
    for task in config["tasks"]:
        if time.perf_counter() - started >= config["wall_seconds"]:
            raise RuntimeError("probe time budget exhausted")
        instance = fixed_size(universe_size=config["n"], set_count=config["n"], k=config["k"],
                              set_size=config["d"], unique_sets=False, seed=task["seed"])
        original = [[a for a in range(config["n"]) if mask & (1 << a)] for mask in instance.sets]
        graph_started = time.perf_counter()
        chains = []
        for direction in (-1, 1):
            for replica in range(config["replicas"]):
                chain = construct(original, config["n"], seed_for(VERSION, config["n"], config["d"],
                                  task["repetition"], f"chain-{direction}-{replica}"), direction, config["steps"])
                chain["replica"] = replica
                chains.append(chain)
        constructed = time.perf_counter()
        # Outcomes are evaluated only after every chain has been constructed.
        base_values = evaluate(original, config["n"], config["k"])
        for chain in chains:
            for endpoint in chain["endpoints"]:
                endpoint["values"] = evaluate(endpoint["sets"], config["n"], config["k"])
        record = {"task": task, "sets": original, "values": base_values, "chains": chains,
                  "construction_seconds": constructed - graph_started,
                  "evaluation_seconds": time.perf_counter() - constructed}
        write_json(output / "graphs" / (task["base_graph_id"] + ".json"), record)
    write_json(output / "run_status.json", {"complete": True, "graphs": len(config["tasks"]),
                                            "wall_seconds": time.perf_counter() - started})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_probe(probe_config(), args.output)


if __name__ == "__main__":
    main()
