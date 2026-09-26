"""Check the three-point minimax theorem by independent enumeration of matchings.

Coordinates use half-unit ticks: 0..12 means 0, 0.5, ..., 6.
This is a finite theorem check, not an extension of the frozen 30-sequence study.
"""
from datetime import datetime, timezone
import hashlib
from itertools import permutations
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parent
SECOND = list(permutations(range(3), 2))
FINAL = list(permutations(range(3)))


def nearest(servers, x):
    return min(range(3), key=lambda i: (abs(x-servers[i]), servers[i]))


def second_stage_rule(servers, x, y):
    """The proved rule uses only the two arrived requests."""
    p = nearest(servers, x)
    if p == 0 and y < x:
        return (1, 0)
    if p == 2 and y > x:
        return (1, 2)
    q = min((i for i in range(3) if i != p),
            key=lambda i: (abs(y-servers[i]), servers[i]))
    return (p, q)


def frozen_loss_formula(servers, x, y):
    a, b, c = servers
    positive = lambda v: max(v, 0)
    return [2*(min(x, b)-a+positive(x-max(b, y))),
            2*(positive(min(b, y)-x)+positive(x-max(b, y))),
            2*(c-max(x, b)+positive(min(b, y)-x))]


def pointwise_formula(servers, x, y, z):
    _, b, _ = servers
    positive = lambda v: max(v, 0)
    lo, hi = min(b, y, z), max(b, y, z)
    return [2*(positive(min(x, b)-lo)+positive(x-hi)),
            2*(positive(lo-x)+positive(x-hi)),
            2*(positive(hi-max(b, x))+positive(lo-x))]


def audit_prefix(servers, x, y, future):
    p = nearest(servers, x)
    costs2 = {m: abs(x-servers[m[0]])+abs(y-servers[m[1]]) for m in SECOND}
    opt2 = min(costs2.values())
    objective = {m: -1 for m in SECOND}
    frozen_losses = [0, 0, 0]
    endpoint_losses = [0, 0, 0]
    for z in future:
        # Independent oracle: all six final bijections, with lifetime counts.
        costs3 = {m: sum(abs(r-servers[s]) for r, s in zip((x, y, z), m)) for m in FINAL}
        opt3 = min(costs3.values())
        for old in SECOND:
            spent_x = int(old[0] != p)
            feasible = [value for m, value in costs3.items()
                        if spent_x+int(m[0] != old[0]) <= 1
                        and int(m[1] != old[1]) <= 1]
            objective[old] = max(objective[old], costs2[old]-opt2+min(feasible)-opt3)
        per_z = [min(value for m, value in costs3.items() if m[0] == d)-opt3 for d in range(3)]
        assert per_z == pointwise_formula(servers, x, y, z), ('pointwise', servers, x, y, z)
        frozen_losses = [max(a, b) for a, b in zip(frozen_losses, per_z)]
        if z in (servers[0], servers[2]):
            endpoint_losses = [max(a, b) for a, b in zip(endpoint_losses, per_z)]
    assert frozen_losses == endpoint_losses == frozen_loss_formula(servers, x, y)
    chosen = second_stage_rule(servers, x, y)
    value = min(objective.values())
    assert objective[chosen] == value, ('minimax', servers, x, y, chosen, objective)
    expected = costs2[chosen]-opt2 if p == 1 else 0
    assert value == expected
    return value, objective


def main():
    started_cpu, started_wall = time.process_time(), time.perf_counter()
    out = ROOT / 'output' / ('three_point_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    layouts = [(0, b, 12) for b in (2, 4, 6, 8, 10)]
    witnesses = []
    for servers in layouts:
        maximum = 0
        for x in range(13):
            for y in range(13):
                value, _ = audit_prefix(servers, x, y, range(13))
                maximum = max(maximum, value)
        bound = min(servers[1]-servers[0], servers[2]-servers[1])
        witness_x, witness_y = (servers[1]+servers[2])//2, servers[1]
        value, _ = audit_prefix(servers, witness_x, witness_y, range(13))
        assert maximum == value == bound
        witnesses.append(dict(servers=[s/2 for s in servers], x=witness_x/2, y=witness_y/2,
                              worst_excess=maximum/2))
    # Reuse the prior budget-lock example, restricted to its first three points.
    value, actions = audit_prefix((0, 3, 5), 2, 3, range(6))
    assert value == 1 and actions[(0, 1)] == 4
    result = dict(status='automatic_verification_passed_user_review_pending',
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  model='Atomic matching updates; first request nearest, ties left; lifetime budget one.',
                  objective='max_z [(C2-OPT2)+(C3(z)-OPT3(z))]',
                  grid=dict(server_layouts=5, coordinate_unit=0.5, request_coordinates=13,
                            distinct_prefixes=845, future_cases=10985,
                            stage_two_actions_per_prefix=6, final_bijections_per_future=6),
                  checks=['all_second_stage_actions', 'all_budget_feasible_final_bijections',
                          'pointwise_frozen_loss', 'worst_loss_at_endpoints',
                          'closed_form_loss', 'second_stage_minimax_rule',
                          'conditional_value', 'tight_global_bound', 'prior_budget_lock_example'],
                  worst_excess_witnesses=witnesses,
                  prior_example=dict(servers=[0, 3, 5], x=2, y=3, keep_worst_excess=1,
                                     move_first_to_zero_worst_excess=4),
                  cpu_seconds=time.process_time()-started_cpu,
                  wall_seconds=time.perf_counter()-started_wall,
                  scope='Finite grid consistency check, plus the prior example; continuous-domain validity comes from the written proof.',
                  previous_study_inputs_modified=False)
    shutil.copyfile(__file__, out/'verify_three_point.py')
    for name in ('summary.json', 'verification.json'):
        (out/name).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
