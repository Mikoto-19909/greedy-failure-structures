"""Independent switch replay and exact reference checks for R3 probes."""
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
from r2_design import read_json, write_json, seed_for
from validate_r2_budget_grid import reference, greedy_reference, union
from validate_greedy_failure_paths import compare


def exact_values(sets, k):
    sets = [set(s) for s in sets]
    optimum, best = reference(sets, k)
    greedy, selected = greedy_reference(sets, k)
    choices = [(len(union(sets, (0, *rest))), (0, *rest))
               for rest in combinations(range(1, len(sets)), k - 1)]
    forced, witness = min(choices, key=lambda v: (-v[0], v[1]))
    return {"greedy": greedy, "greedy_selected": selected, "optimum": optimum,
            "optimum_selected": best, "forced_optimum": forced, "forced_selected": list(witness),
            "first_loss": forced < optimum}


def local_intersections(sets):
    return sum(len(sets[0].intersection(s)) for s in sets[1:])


def replay(original, n, seed, direction, steps, k):
    sets = [set(s) for s in original]
    initial_degrees = [len(s) for s in sets]
    initial_frequencies = [sum(a in s for s in sets) for a in range(n)]
    rng = random.Random(seed)
    moves, endpoints = [], []
    legal = 0
    for attempt in range(1, max(steps) + 1):
        i, j = rng.sample(range(len(sets)), 2)
        a, b = rng.sample(range(n), 2)
        switchable = ((a in sets[i] and b not in sets[i] and b in sets[j] and a not in sets[j]) or
                      (b in sets[i] and a not in sets[i] and a in sets[j] and b not in sets[j]))
        if switchable:
            legal += 1
            proposed = [s.copy() for s in sets]
            for row in (i, j):
                proposed[row] = (sets[row] - {a, b}) | ({a, b} - sets[row])
            change = local_intersections(proposed) - local_intersections(sets)
            if (direction == 1 and change >= 0) or (direction == -1 and change <= 0):
                sets = proposed
                moves.append([attempt, i, j, a, b])
        if attempt in steps:
            compare([len(s) for s in sets], initial_degrees, "row degree sequence")
            compare([sum(a in s for s in sets) for a in range(n)], initial_frequencies, "column degree sequence")
            endpoint = {"proposals": attempt, "sets": [sorted(s) for s in sets],
                        "exposure": local_intersections(sets), "legal": legal, "accepted": len(moves),
                        "values": exact_values(sets, k)}
            endpoints.append(endpoint)
    return {"seed": seed, "direction": direction, "moves": moves, "endpoints": endpoints}


def validate_probe(output):
    output = Path(output)
    config = read_json(output / "config.json")
    expected = {"version": "r3-exposure-probe-v1", "phase": "feasibility_only", "n": 12,
                "d": 3, "k": 4, "replicas": 2, "steps": [128, 512, 2048], "wall_seconds": 3600,
                "tasks": [{"base_graph_id": f"r3-probe-r{i:04d}", "repetition": i,
                           "seed": seed_for("r3-exposure-probe-v1", 12, 3, i)} for i in range(16)]}
    compare(config, expected, "probe design")
    write_json(output / "verification.json", {"status": "incomplete"})
    files = {p.stem for p in (output / "graphs").glob("*.json")}
    compare(sorted(files), sorted(t["base_graph_id"] for t in config["tasks"]), "complete probe population")
    started = time.perf_counter()
    spent = read_json(output / "run_status.json")["wall_seconds"]
    records, timings = [], []
    for task in config["tasks"]:
        if spent + time.perf_counter() - started >= 3600:
            raise RuntimeError("combined probe budget exhausted")
        tick = time.perf_counter()
        record = read_json(output / "graphs" / (task["base_graph_id"] + ".json"))
        compare(record["task"], task, "probe task")
        instance = fixed_size(universe_size=12, set_count=12, k=4, set_size=3,
                              unique_sets=False, seed=task["seed"])
        original = [[a for a in range(12) if mask & (1 << a)] for mask in instance.sets]
        compare(record["sets"], original, "probe original input")
        compare(record["values"], exact_values(original, 4), "original optimum")
        chains = []
        for direction in (-1, 1):
            for replica in range(2):
                chain_seed = seed_for(config["version"], 12, 3, task["repetition"], f"chain-{direction}-{replica}")
                chain = replay(original, 12, chain_seed, direction, config["steps"], 4)
                chain["replica"] = replica
                chains.append(chain)
        compare(record["chains"], chains, "switch decisions, endpoints and independent optima")
        records.append(record)
        timings.append(time.perf_counter() - tick)
    structural = []
    for step in config["steps"]:
        deltas = []
        for record in records:
            sides = {}
            for direction in (-1, 1):
                endpoints = [e for c in record["chains"] if c["direction"] == direction
                             for e in c["endpoints"] if e["proposals"] == step]
                sides[direction] = sum(e["exposure"] for e in endpoints) / 2
            deltas.append(sides[1] - sides[-1])
        structural.append({"proposals": step, "graphs": len(deltas), "separated_graphs": sum(x > 0 for x in deltas),
                           "mean_exposure_difference": sum(deltas) / len(deltas),
                           "minimum_exposure_difference": min(deltas), "maximum_exposure_difference": max(deltas)})
    write_json(output / "probe_summary.json", {"structural_checkpoints": structural,
               "graph_count": len(records), "endpoint_count": len(records) * 12,
               "production_wall_seconds": spent, "verification_wall_seconds": time.perf_counter() - started,
               "max_production_seconds_per_graph": max(r["construction_seconds"] + r["evaluation_seconds"] for r in records),
               "max_verification_seconds_per_graph": max(timings)})
    write_json(output / "verification.json", {"status": "passed", "graphs": len(records), "endpoints": len(records) * 12})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate_probe(args.output)
    print("R3 feasibility inputs, switches and optima verified; no confirmation inference", flush=True)


if __name__ == "__main__":
    main()
