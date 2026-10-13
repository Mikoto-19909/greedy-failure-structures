"""Exact linear-real adversary formula for the continuous four-request game.

The last-coordinate endpoint lemma is explained in the accompanying report.
Each query asks whether an adaptive deterministic adversary can force total
prefix excess strictly greater than a rational bound.  A satisfying model is a
lower certificate; UNSAT is an upper certificate for that first-server cell.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
import importlib
from itertools import combinations, permutations
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "results" / "online_matching_closure_20260927" / "four_exact"
z3: Any = None


def enable_solver():
    """Keep the standard-library action helpers importable without Z3."""
    global z3
    if z3 is None:
        sys.path.insert(0, str(OUT.parent / "tools"))
        try:
            z3 = importlib.import_module("z3")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Install the isolated solver with: python -m pip install --target "
                "results/online_matching_closure_20260927/tools z3-solver==5.1.0.0"
            ) from exc
    return z3


def query_tag(out: Path, base: str) -> str:
    """A replay keeps the saved result and writes a fresh timestamped query."""
    suffixes = (".smt2", ".json", "_source.py")
    if any((out / (base + suffix)).exists() for suffix in suffixes):
        return base + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return base

SERVERS = (-4, -1, 2, 8)
MATCHINGS = {n: tuple(permutations(range(4), n)) for n in range(1, 5)}


def chain(old: tuple[int, ...], new: tuple[int, ...]) -> bool:
    """Trace the newcomer to the free service; reject disconnected changes."""
    owners = {server: i for i, server in enumerate(old)}
    changed = {i for i in range(len(old)) if old[i] != new[i]}
    reached: set[int] = set()
    server = new[-1]
    while server in owners:
        i = owners[server]
        if i in reached or i not in changed:
            return False
        reached.add(i)
        server = new[i]
    return reached == changed


@lru_cache(None)
def actions(old: tuple[int, ...], used: tuple[int, ...], budget: int,
            model: str) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    result = []
    for new in MATCHINGS[len(old) + 1]:
        counts = tuple(c + int(a != b) for c, a, b in zip(used, old, new)) + (0,)
        if max(counts) <= budget and (model == "atomic" or chain(old, new)):
            result.append((new, counts))
    return tuple(result)


def minimum(values):
    iterator = iter(values)
    result = next(iterator)
    for value in iterator:
        result = z3.If(value < result, value, result)
    return result


def distances(r):
    if isinstance(r, int):
        return tuple(z3.RealVal(abs(r - s)) for s in SERVERS)
    return tuple(z3.If(r >= s, r - s, s - r) for s in SERVERS)


def cost(rows, matching):
    return z3.Sum(*(row[s] for row, s in zip(rows, matching)))


def optimum(rows, coordinates):
    # An optimum on the line pairs sorted requests with a sorted service subset.
    ordered = []
    for value in coordinates:
        ordered.append(value)
        for i in range(len(ordered) - 1, 0, -1):
            a, b = ordered[i - 1:i + 1]
            ordered[i - 1:i + 1] = [z3.If(a <= b, a, b), z3.If(a <= b, b, a)]
    sorted_rows = tuple(distances(value) for value in ordered)
    return minimum(cost(sorted_rows, matching)
                   for matching in combinations(range(4), len(rows)))


def formula(budget: int, model: str, first: int, bound: Fraction, non_strict=False):
    """Unroll all algorithm choices, keeping nature's third coordinates separate."""
    enable_solver()
    x, y = z3.Reals("x y")
    xrow, yrow = distances(x), distances(y)
    constraints = [x >= SERVERS[0], x <= SERVERS[-1],
                   y >= SERVERS[0], y <= SERVERS[-1]]
    # Nearest, ties left: lower edge open and upper edge closed.
    if first:
        constraints.append(2 * x > SERVERS[first - 1] + SERVERS[first])
    if first < 3:
        constraints.append(2 * x <= SERVERS[first] + SERVERS[first + 1])
    rows2 = (xrow, yrow)
    opt2 = optimum(rows2, (x, y))
    second = actions((first,), (0,), budget, model)
    third_variables = []
    counts = dict(second_actions=len(second), third_actions=0, terminal_actions=0)
    v = z3.RealVal(f"{bound.numerator}/{bound.denominator}")
    exceeds = (lambda value: value >= v) if non_strict else (lambda value: value > v)
    for i, (a2, used2) in enumerate(second):
        r3 = z3.Real(f"z_{i}")
        third_variables.append((r3, a2, used2))
        constraints.extend([r3 >= SERVERS[0], r3 <= SERVERS[-1]])
        rows3 = rows2 + (distances(r3),)
        opt3 = optimum(rows3, (x, y, r3))
        immediate2 = cost(rows2, a2) - opt2
        terminal_rows = [rows3 + (distances(w),) for w in SERVERS]
        terminal_opt = [optimum(rows, (x, y, r3, w))
                        for rows, w in zip(terminal_rows, SERVERS)]
        for a3, used3 in actions(a2, used2, budget, model):
            counts["third_actions"] += 1
            terminal = actions(a3, used3, budget, model)
            counts["terminal_actions"] += len(terminal)
            immediate = immediate2 + cost(rows3, a3) - opt3
            if len(terminal) == 24:
                constraints.append(exceeds(immediate))
                continue
            # Nature may choose a different final endpoint after each a3.
            bad_endpoints = []
            for rows4, opt4 in zip(terminal_rows, terminal_opt):
                # min feasible total > bound iff every feasible total > bound.
                bad_endpoints.append(z3.And(*(exceeds(immediate + cost(rows4, a4) - opt4)
                                              for a4, _ in terminal)))
            constraints.append(z3.Or(*bad_endpoints))
    return z3.And(*constraints), (x, y), third_variables, counts


def run_query(budget, model, first, bound, timeout, non_strict=False):
    enable_solver()
    start = time.process_time()
    OUT.mkdir(parents=True, exist_ok=True)
    relation = "ge" if non_strict else "gt"
    tag = query_tag(OUT, f"b{budget}_{model}_p{first}_{relation}{str(bound).replace('/', '_')}_sorted")
    (OUT / f"{tag}_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    statement, xy, thirds, counts = formula(budget, model, first, bound, non_strict)
    solver = z3.SolverFor("QF_LRA")
    solver.set(timeout=timeout * 1000, threads=1)
    solver.add(statement)
    (OUT / f"{tag}.smt2").write_text(solver.to_smt2(), encoding="utf-8")
    result = solver.check()
    record = dict(budget=budget, model=model, first_server_index=first,
                  bound=str(bound), relation=relation,
                  question="can_force_bound_or_more" if non_strict else "can_force_strictly_greater",
                  status=str(result), counts=counts,
                  cpu_seconds=time.process_time() - start,
                  z3_version=z3.get_version_string(), timeout_seconds=timeout)
    if result == z3.sat:
        witness = solver.model()
        record["witness"] = dict(x=str(witness.eval(xy[0])), y=str(witness.eval(xy[1])),
                                  third=[dict(second_assignment=a2, used=used,
                                              coordinate=str(witness.eval(r3)))
                                         for r3, a2, used in thirds])
    elif result == z3.unknown:
        record["reason_unknown"] = solver.reason_unknown()
    (OUT / f"{tag}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, choices=(1, 2), required=True)
    parser.add_argument("--model", choices=("atomic", "chain"), required=True)
    parser.add_argument("--first", type=int, choices=range(4), required=True)
    parser.add_argument("--bound", type=Fraction, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--non-strict", action="store_true")
    args = parser.parse_args()
    run_query(args.budget, args.model, args.first, args.bound, args.timeout, args.non_strict)


if __name__ == "__main__":
    main()
