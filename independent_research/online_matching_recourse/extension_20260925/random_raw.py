"""Three servers: exact finite games for randomized and raw-cost objectives.

Run with the existing medical Python environment. SciPy is used only for the
small linear programs. All feasible states are independently enumerated.
"""
from datetime import datetime, timezone
from fractions import Fraction
from itertools import permutations
from pathlib import Path
import json
import time

import numpy as np
from scipy.optimize import linprog


SECOND = tuple(permutations(range(3), 2))
FINAL = tuple(permutations(range(3)))
TOL = 1e-8


def cost(servers, requests, assignment):
    return sum(abs(requests[i] - servers[s]) for i, s in enumerate(assignment))


def first(servers, x):
    return min(range(3), key=lambda i: (abs(x - servers[i]), i))


def optimum(servers, requests):
    return min(cost(servers, requests, m)
               for m in permutations(range(3), len(requests)))


def final_cost(servers, x, y, z, p, state):
    # Each old request may change at most once over the entire arrival sequence.
    used = (int(state[0] != p), 0)
    feasible = [m for m in FINAL
                if all(used[i] + int(m[i] != state[i]) <= 1 for i in range(2))]
    assert feasible
    return min(cost(servers, (x, y, z), m) for m in feasible)


def matrices(servers, x, y, points):
    p = first(servers, x)
    o2 = optimum(servers, (x, y))
    raw, excess = [], []
    for state in SECOND:
        c2 = cost(servers, (x, y), state)
        c3 = [final_cost(servers, x, y, z, p, state) for z in points]
        raw.append([c2 + v for v in c3])
        excess.append([c2 - o2 + v - optimum(servers, (x, y, z))
                       for z, v in zip(points, c3)])
    return np.asarray(raw), np.asarray(excess)


def game(matrix):
    """Exact finite reduction, solved numerically with primal/dual certificates."""
    rows, cols = matrix.shape
    result = linprog(
        [0.0] * rows + [1.0],
        A_ub=np.column_stack((matrix.T, -np.ones(cols))),
        b_ub=np.zeros(cols), A_eq=[[1.0] * rows + [0.0]], b_eq=[1.0],
        bounds=[(0.0, None)] * rows + [(None, None)], method="highs",
    )
    assert result.success, result.message
    policy = result.x[:-1]
    adversary = -result.ineqlin.marginals
    value = float(result.fun)
    residual = max(abs(sum(policy) - 1), abs(sum(adversary) - 1),
                   max(0.0, -min(policy)), max(0.0, -min(adversary)),
                   abs(max(matrix.T @ policy) - value),
                   abs(min(matrix @ adversary) - value))
    assert residual < TOL, residual
    return {"value": value, "policy": policy.tolist(),
            "adversary": adversary.tolist(), "certificate_residual": float(residual)}


def raw_formula(servers, x, y):
    a, b, c = servers
    p = first(servers, x)
    q = min((i for i in range(3) if i != p), key=lambda i: (abs(y - servers[i]), i))
    r, s = sorted((x, y))
    m0 = r - a + c - s + max(abs(r - b), abs(s - b))
    candidates = [{"state": [p, q], "c2": cost(servers, (x, y), (p, q)),
                   "max_c3": m0, "action": "defer"}]
    for d in range(3):
        if d == p:
            continue
        e, f = [servers[i] for i in range(3) if i != d]
        md = abs(x - servers[d]) + max(
            e - a + abs(y - f), abs(y - e) + c - f,
            abs(y - e) + abs(y - f))
        candidates.append({"state": [d, p], "c2": cost(servers, (x, y), (d, p)),
                           "max_c3": md, "action": f"move_to_{d}"})
    for action in candidates:
        action["max_raw"] = action["c2"] + action["max_c3"]
    # Stable ties: defer, then leftmost moved-to server.
    selected = min(candidates, key=lambda item: item["max_raw"])
    return {"candidates": candidates, "selected": selected,
            "value": selected["max_raw"]}


def excess_rule(servers, x, y):
    p = first(servers, x)
    q = min((i for i in range(3) if i != p), key=lambda i: (abs(y - servers[i]), i))
    if p == 0 and y < x or p == 2 and y > x:
        return (1, p), 0.0
    return (p, q), cost(servers, (x, y), (p, q)) - optimum(servers, (x, y))


def example(servers, x, y):
    points = sorted(set((*servers, x, y)))
    raw, excess = matrices(servers, x, y, points)
    return {"servers": servers, "x": x, "y": y, "points": points,
            "states": SECOND, "raw_matrix": raw.tolist(), "excess_matrix": excess.tolist(),
            "raw_deterministic": float(min(np.max(raw, axis=1))),
            "excess_deterministic": float(min(np.max(excess, axis=1))),
            "raw_randomized": game(raw), "excess_randomized": game(excess),
            "raw_formula": raw_formula(servers, x, y)}


def main():
    started = time.process_time()
    checks = {"prefixes": 0, "lp_solved": 0, "affine_interior_points": 0,
              "raw_random_strict_improvements": 0, "raw_vs_excess_different_states": 0}
    max_residual = 0.0
    largest_gain = {"gain": 0.0}
    records = []
    for b in range(1, 6):
        servers = (0.0, float(b), 6.0)
        for ix in range(13):
            for iy in range(13):
                x, y = ix / 2, iy / 2
                points = sorted(set((*servers, x, y)))
                raw, excess = matrices(servers, x, y, points)
                raw_game, excess_game = game(raw), game(excess)
                max_residual = max(max_residual, raw_game["certificate_residual"],
                                   excess_game["certificate_residual"])
                rd = float(min(np.max(raw, axis=1)))
                ed = float(min(np.max(excess, axis=1)))
                formula = raw_formula(servers, x, y)
                rule_state, rule_value = excess_rule(servers, x, y)
                assert abs(rd - formula["value"]) < TOL
                assert abs(ed - rule_value) < TOL
                assert abs(ed - excess_game["value"]) < TOL
                for action in formula["candidates"]:
                    row = SECOND.index(tuple(action["state"]))
                    assert abs(max(raw[row]) - action["max_raw"]) < TOL
                # Verify interpolation by fresh budget-feasible enumeration.
                for left, right in zip(points, points[1:]):
                    for weight in (1 / 3, 1 / 2, 2 / 3):
                        z = left + weight * (right - left)
                        ri, ei = matrices(servers, x, y, [z])
                        j = points.index(left)
                        assert np.max(abs(ri[:, 0] - ((1-weight)*raw[:, j]+weight*raw[:, j+1]))) < TOL
                        assert np.max(abs(ei[:, 0] - ((1-weight)*excess[:, j]+weight*excess[:, j+1]))) < TOL
                        checks["affine_interior_points"] += 1
                gain = rd - raw_game["value"]
                checks["raw_random_strict_improvements"] += int(gain > TOL)
                checks["raw_vs_excess_different_states"] += int(
                    tuple(formula["selected"]["state"]) != rule_state)
                if gain > largest_gain["gain"] + TOL:
                    largest_gain = {"gain": gain, "servers": servers, "x": x, "y": y}
                records.append({"servers": servers, "x": x, "y": y,
                                "excess_deterministic": ed, "excess_randomized": excess_game["value"],
                                "raw_deterministic": rd, "raw_randomized": raw_game["value"],
                                "raw_policy": raw_game["policy"],
                                "raw_adversary": raw_game["adversary"], "points": points})
                checks["prefixes"] += 1
                checks["lp_solved"] += 2
    witness = example((0, 10, 50), 6, 10)
    assert witness["raw_deterministic"] == 62
    assert abs(witness["raw_randomized"]["value"] - 60) < TOL
    assert witness["excess_deterministic"] == 8
    # Exact rational certificate for the reduced two-action raw game.
    reduced = ((58, 64), (62, 56))
    policy, adversary = (Fraction(1, 2), Fraction(1, 2)), (Fraction(2, 3), Fraction(1, 3))
    assert all(sum(policy[i] * reduced[i][j] for i in range(2)) == 60 for j in range(2))
    assert all(sum(adversary[j] * reduced[i][j] for j in range(2)) == 60 for i in range(2))
    result = {"model": {"first": "nearest_ties_left", "update": "atomic_batch",
                        "budget": "one_per_request_lifetime", "future": "continuous_in_server_hull",
                        "random_adversary": "chooses_z_without_observing_sampled_state",
                        "raw_objective": "C2+C3; C1 is a constant", "seed": None,
                        "same_cost_rule": "defer_then_leftmost_moved_to_server",
                        "LP_note": "finite reduction exact; SciPy numerical primal-dual residual checked"},
              "checks": checks, "max_lp_certificate_residual": max_residual,
              "largest_raw_random_gain_on_grid": largest_gain,
              "exact_rational_witness": {"policy": ["1/2", "1/2"],
                                          "adversary_at_0_and_6": ["2/3", "1/3"], "value": 60},
              "witness": witness, "records": records, "cpu_seconds": time.process_time() - started,
              "all_checks_passed": True}
    out = Path(__file__).parent / "output" / ("random_raw_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    out.mkdir(parents=True)
    (out / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "checks": checks,
                      "max_lp_certificate_residual": max_residual,
                      "largest_raw_random_gain": largest_gain,
                      "cpu_seconds": result["cpu_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
