"""Three requests, lifetime recourse one: exact rational continuous minimax.

No imports from prior strategies. Run with the existing Python environment.
chain: one simple augmenting path, starting at the newcomer and ending free.
atomic: any injective final matching satisfying the lifetime move counts.
"""
from fractions import Fraction as Q
from itertools import permutations, combinations
from pathlib import Path
import json
import time


def cost(s, r, a):
    return sum(abs(x - s[j]) for x, j in zip(r, a))


def actions(old, counts, mode):
    n = len(old)
    if mode == 'atomic':
        return tuple(a for a in permutations(range(3), n + 1)
                     if all(a[i] == old[i] or counts[i] == 0 for i in range(n)))
    free = set(range(3)) - set(old)
    out = []
    eligible = [i for i in range(n) if counts[i] == 0]
    for length in range(len(eligible) + 1):
        for path in permutations(eligible, length):
            for endpoint in sorted(free):
                a = list(old) + [endpoint if not path else old[path[0]]]
                for k, i in enumerate(path):
                    a[i] = old[path[k + 1]] if k + 1 < length else endpoint
                out.append(tuple(a))
    return tuple(sorted(set(out)))


ALL = tuple(permutations(range(3)))
PAIRS = tuple(permutations(range(3), 2))


def second_actions(p, mode):
    return actions((p,), (0,), mode)


def terminal_actions(p, a, mode):
    return actions(a, (int(a[0] != p), 0), mode)


def nearest(s, x):
    return min(range(3), key=lambda j: (abs(x - s[j]), j))


def terminal_affines(s, x, ym, zm):
    """Cost of every full permutation: A*y + B*z + C in one rectangle."""
    out = {}
    for a in ALL:
        sy = Q(1 if ym > s[a[1]] else -1)
        sz = Q(1 if zm > s[a[2]] else -1)
        out[a] = (sy, sz, abs(x - s[a[0]]) - sy * s[a[1]] - sz * s[a[2]])
    return out


def line_value(line, y):
    return line[0] * y + line[1]


def substitute(f, zline):
    return (f[0] + f[1] * zline[0], f[2] + f[1] * zline[1])


def equality_lines(affines):
    """Return nonvertical equal-cost loci z = slope*y + intercept."""
    lines = set()
    verticals = set()
    for f, g in combinations(affines.values(), 2):
        a, b, c = (f[i] - g[i] for i in range(3))
        if b:
            lines.add((-a / b, -c / b))
        elif a:
            verticals.add(-c / a)
    return lines, verticals


def intersections(lines, lo, hi):
    xs = set()
    for f, g in combinations(set(lines), 2):
        if f[0] != g[0]:
            v = (g[1] - f[1]) / (f[0] - g[0])
            if lo < v < hi:
                xs.add(v)
    return xs


def second_affines(s, x, ym):
    return {a: (Q(1 if ym > s[a[1]] else -1),
                abs(x - s[a[0]]) - (1 if ym > s[a[1]] else -1) * s[a[1]])
            for a in PAIRS}


def y_slabs(s, x):
    """An exact arrangement projection, including all envelope changes."""
    critical = set(s)
    for yl, yh in zip(s, s[1:]):
        ym = (yl + yh) / 2
        c2 = second_affines(s, x, ym)
        critical |= intersections(c2.values(), yl, yh)
        for zl, zh in zip(s, s[1:]):
            aff = terminal_affines(s, x, ym, (zl + zh) / 2)
            lines, verticals = equality_lines(aff)
            lines |= {(Q(0), zl), (Q(0), zh)}
            critical |= {v for v in verticals if yl < v < yh}
            critical |= intersections(lines, yl, yh)
    return list(zip(sorted(critical), sorted(critical)[1:]))


def terminal_worst(s, x, y, feasible):
    """Exact max_z(min feasible cost - min all cost), with a witness."""
    candidates = set(s)
    for zl, zh in zip(s, s[1:]):
        zm = (zl + zh) / 2
        lines = []
        for a in ALL:
            slope = Q(1 if zm > s[a[2]] else -1)
            intercept = abs(x - s[a[0]]) + abs(y - s[a[1]]) - slope * s[a[2]]
            lines.append((slope, intercept))
        candidates |= intersections(lines, zl, zh)
    best = None
    for z in sorted(candidates):
        values = {a: cost(s, (x, y, z), a) for a in ALL}
        excess = min(values[a] for a in feasible) - min(values.values())
        if best is None or excess > best[0]:
            best = excess, z
    return best


def prefix(s, x, y, p=None, mode='chain'):
    """Second-stage optimum after fixed p; includes second+third excess only."""
    s, x, y = tuple(map(Q, s)), Q(x), Q(y)
    if p is None:
        p = nearest(s, x)
    opt = min(cost(s, (x, y), a) for a in PAIRS)
    evaluated = []
    for a in second_actions(p, mode):
        worst, z = terminal_worst(s, x, y, terminal_actions(p, a, mode))
        value = cost(s, (x, y), a) - opt + worst
        evaluated.append((value, a, z))
    return min(evaluated), evaluated


def score_lines(s, x, p, mode, lo, hi):
    """Each action's robust score is max of returned affine lines on this slab."""
    ym = (lo + hi) / 2
    c2 = second_affines(s, x, ym)
    opt2 = min(c2, key=lambda a: (line_value(c2[a], ym), a))
    result = {a: set() for a in second_actions(p, mode)}
    for zl, zh in zip(s, s[1:]):
        aff = terminal_affines(s, x, ym, (zl + zh) / 2)
        lines, _ = equality_lines(aff)
        lines |= {(Q(0), zl), (Q(0), zh)}
        for zline in lines:
            zm = line_value(zline, ym)
            if not zl <= zm <= zh:
                continue
            substituted = {a: substitute(f, zline) for a, f in aff.items()}
            opt3 = min(ALL, key=lambda a: (line_value(substituted[a], ym), a))
            for a in result:
                terminal = terminal_actions(p, a, mode)
                chosen = min(terminal, key=lambda b: (line_value(substituted[b], ym), b))
                result[a].add(tuple(c2[a][i] - c2[opt2][i] +
                                    substituted[chosen][i] - substituted[opt3][i]
                                    for i in range(2)))
    return result


def first_value(s, x, p, mode='atomic'):
    """Exact max_y min_action max_z cumulative excess, including stage one."""
    s, x = tuple(map(Q, s)), Q(x)
    witnesses = []
    candidate_count = 0
    for lo, hi in y_slabs(s, x):
        by_action = score_lines(s, x, p, mode, lo, hi)
        all_lines = set().union(*by_action.values())
        candidates = {lo, hi} | intersections(all_lines, lo, hi)
        candidate_count += len(candidates)
        for y in candidates:
            value = min(max(line_value(line, y) for line in lines)
                        for lines in by_action.values())
            witnesses.append((value, y))
    worst, y = max(witnesses, key=lambda row: (row[0], -row[1]))
    exact, _ = prefix(s, x, y, p, mode)
    assert exact[0] == worst, (s, x, p, mode, y, exact, worst)
    initial = abs(x - s[p]) - min(abs(x - v) for v in s)
    return {'value': worst + initial, 'future_value': worst, 'first_excess': initial,
            'y': y, 'z': exact[2], 'second_assignment': exact[1],
            'candidate_count': candidate_count}


def free_first(s, x):
    s, x = tuple(map(Q, s)), Q(x)
    rows = [first_value(s, x, p) for p in range(3)]
    p = min(range(3), key=lambda j: (rows[j]['value'], j))
    return p, rows


def brute_actions(old, used, mode):
    """Independent permutation filter; no path generation."""
    result = []
    for new in permutations(range(3), len(old) + 1):
        moved = {i for i in range(len(old)) if new[i] != old[i]}
        if any(used[i] for i in moved):
            continue
        if mode == 'chain':
            cursor, visited = new[-1], set()
            owners = {s: i for i, s in enumerate(old)}
            while cursor in owners and owners[cursor] not in visited:
                i = owners[cursor]
                visited.add(i)
                cursor = new[i]
            if cursor in owners or visited != moved:
                continue
        result.append(new)
    return result


def brute_prefix(s, x, y, p, zs, mode):
    opt2 = min(cost(s, (x, y), a) for a in permutations(range(3), 2))
    scored = []
    for a in brute_actions((p,), (0,), mode):
        legal = brute_actions(a, (int(a[0] != p), 0), mode)
        worst = max(min(cost(s, (x, y, z), b) for b in legal) -
                    min(cost(s, (x, y, z), b) for b in permutations(range(3))) for z in zs)
        scored.append((cost(s, (x, y), a) - opt2 + worst, a))
    return min(scored)


def serial(obj):
    if isinstance(obj, Q):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): serial(v) for k, v in obj.items()}
    if isinstance(obj, (tuple, list)):
        return [serial(v) for v in obj]
    return obj


def verify():
    started = time.process_time()
    count = 0
    differences = []
    # These are mathematical checks, not an enlarged benchmark dataset.
    for middle in (1, 2, 3, 4, 5):
        s = tuple(map(Q, (0, middle, 6)))
        grid = tuple(Q(i, 2) for i in range(13))
        for x in grid:
            p = nearest(s, x)
            for y in grid:
                chain, _ = prefix(s, x, y, p, 'chain')
                atomic, _ = prefix(s, x, y, p, 'atomic')
                for mode, result in [('chain', chain), ('atomic', atomic)]:
                    brute = brute_prefix(s, x, y, p, grid, mode)
                    # Terminal difference extrema are checked here against the grid;
                    # rational off-grid cases are verified separately below.
                    assert result[:2] == brute, (s, x, y, mode, result, brute)
                    count += 1
                if chain[0] > atomic[0]:
                    differences.append({'servers': s, 'x': x, 'y': y,
                                        'chain': chain, 'atomic': atomic})
    first_results = []
    for s, xs in [((0, 3, 6), [Q(i, 2) for i in range(13)] + [Q(7, 4), Q(17, 4)]),
                  ((0, 1, 6), [Q(3, 4), Q(7, 3), Q(7, 2)]),
                  ((0, 3, 5), [Q(2), Q(5, 2), Q(4)]),
                  ((Q(-2, 3), Q(5, 7), Q(17, 6)), [Q(1, 3), Q(9, 7)])]:
        s = tuple(map(Q, s))
        for x in xs:
            best, rows = free_first(s, x)
            # Independent nested game on a validation grid plus all exact witnesses.
            ys = {s[0] + (s[2] - s[0]) * Q(i, 24) for i in range(25)}
            ys |= {row['y'] for row in rows}
            for p, row in enumerate(rows):
                zs = ys | {row['z']}
                got = max(brute_prefix(s, x, y, p, zs, 'atomic')[0] for y in ys)
                assert got == row['future_value'], (s, x, p, got, row)
                # Direct prefix evaluator also tests interior points in every exact slab.
                for lo, hi in y_slabs(s, x):
                    y = (2 * lo + hi) / 3
                    lines = score_lines(s, x, p, 'atomic', lo, hi)
                    predicted = min(max(line_value(f, y) for f in fs) for fs in lines.values())
                    assert prefix(s, x, y, p, 'atomic')[0][0] == predicted
            first_results.append({'servers': s, 'x': x, 'nearest': nearest(s, x),
                                  'optimal_first': best, 'choices': rows})
    s, x, y = tuple(map(Q, (0, 2, 6))), Q(5, 4), Q(2)
    chain_example = {'servers': s, 'x': x, 'y': y,
                     'chain': prefix(s, x, y, mode='chain'),
                     'atomic': prefix(s, x, y, mode='atomic')}
    assert chain_example['chain'][0][0] == Q(5, 2)
    assert chain_example['chain'][0][1] == (0, 1)
    assert chain_example['atomic'][0][0] == Q(3, 2)
    assert chain_example['atomic'][0][1] == (1, 0)
    rational_checks = 0
    for s in [tuple(map(Q, (0, 2, 6))), (Q(-2, 3), Q(5, 7), Q(17, 6))]:
        for x in (s[0] + (s[2] - s[0]) * Q(2, 7),
                  s[0] + (s[2] - s[0]) * Q(5, 11)):
            for y in (s[0] + (s[2] - s[0]) * Q(1, 3),
                      s[0] + (s[2] - s[0]) * Q(7, 13)):
                for p in range(3):
                    for mode in ('chain', 'atomic'):
                        exact, rows = prefix(s, x, y, p, mode)
                        # All actual per-action worst witnesses are included.
                        # The permutation checker independently tests feasibility.
                        zs = set(s) | {r[2] for r in rows}
                        assert brute_prefix(s, x, y, p, zs, mode) == exact[:2]
                        rational_checks += 1
    return {'input_domain': 'three ordered rational servers, three requests in [a,c], lifetime budget one',
            'continuous_method': 'exact Fraction arrangement and envelope enumeration; proof in report',
            'prefix_checks': count, 'grid_layouts': 5, 'grid_points': 13,
            'first_games': len(first_results), 'chain_atomic_differences': differences[:8],
            'chain_atomic_difference_count': len(differences),
            'strict_timing_reversal_example': chain_example,
            'off_grid_rational_prefix_checks': rational_checks,
            'first_results': first_results, 'cpu_seconds': time.process_time() - started,
            'all_checks_passed': True}


if __name__ == '__main__':
    output = Path(__file__).parent / 'output' / ('chain_first_' + time.strftime('%Y%m%dT%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    result = verify()
    (output / 'verification.json').write_text(json.dumps(serial(result), ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
    print(json.dumps(serial({k: v for k, v in result.items() if k not in
                            ('first_results', 'chain_atomic_differences', 'strict_timing_reversal_example')}), ensure_ascii=False))
