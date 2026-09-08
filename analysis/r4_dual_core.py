"""Integer L5 Method 4 certificates using Method 3 on every Greedy prefix.

The crossing scan below is producer-only.  The independent verifier rebuilds
explicit residual sets and evaluates every index in the max-min recurrence.
"""
from __future__ import annotations


def _method3(singletons, cumulative, budget):
    """Compute all q values with a monotone threshold crossing.

    Before the first i with F_i >= q + s_i, min(F_i, q+s_i) is
    nondecreasing F_i; from that index onwards it is nonincreasing q+s_i.
    Therefore only the two sides of the crossing can maximize the value.
    As q grows the crossing moves right, so the whole recurrence scans at
    most M indices, besides its budget output steps.  No crossing saturates
    at F_M; equality belongs to the right side.
    """
    values = [0]
    crossing = 0
    count = len(singletons)
    for _ in range(budget):
        previous = values[-1]
        while crossing < count and cumulative[crossing] < previous + singletons[crossing]:
            crossing += 1
        if crossing == count:
            values.append(cumulative[-1])
        else:
            left = cumulative[crossing - 1] if crossing else 0
            values.append(max(left, previous + singletons[crossing]))
    return values


def certificates(masks, budgets):
    """Return independent, JSON-ready certificate records in budget order.

    ``masks`` is a nonempty sequence of nonnegative integer bitmasks, and
    ``budgets`` is a nonempty increasing list of unique integers in 1..M.
    Greedy always breaks ties by the original lower index, including after
    saturation.  Certificate sorting never changes input or path order.

    Each prefix stores ordered ``selected`` indices, residual ``order``,
    singleton sizes ``s``, cumulative union sizes ``F``, all ``q[0:k+1]``,
    and its uncapped conditional ``upper = coverage + q[k]``.  Every q uses
    the full budget k, even when the conditioning prefix is nonempty.
    """
    if not isinstance(masks, (list, tuple)) or not masks:
        raise ValueError("nonempty candidate masks required")
    if any(type(mask) is not int or mask < 0 for mask in masks):
        raise ValueError("invalid candidate masks")
    if not isinstance(budgets, list) or not budgets:
        raise ValueError("nonempty ordered unique budgets required")
    if any(type(k) is not int or not 1 <= k <= len(masks) for k in budgets):
        raise ValueError("invalid budget")
    if budgets != sorted(set(budgets)):
        raise ValueError("nonempty ordered unique budgets required")

    maximum_budget = budgets[-1]
    total_union = 0
    for mask in masks:
        total_union |= mask
    union_size = total_union.bit_count()

    # The same condition has the same residual order and q prefix at every
    # budget.  Cache only within this original graph, then copy saved lists
    # so callers can inspect or mutate a record without changing another.
    states = []
    covered = 0
    chosen = []
    available = set(range(len(masks)))
    for t in range(maximum_budget + 1):
        residuals = [mask & ~covered for mask in masks]
        sizes = [mask.bit_count() for mask in residuals]
        order = sorted(range(len(masks)), key=lambda index: (-sizes[index], index))
        singletons = [sizes[index] for index in order]
        cumulative = []
        residual_union = 0
        for index in order:
            residual_union |= residuals[index]
            cumulative.append(residual_union.bit_count())
        states.append({"t": t, "selected": chosen.copy(), "coverage": covered.bit_count(),
                       "order": order, "s": singletons, "F": cumulative,
                       "q": _method3(singletons, cumulative, maximum_budget)})
        if t < maximum_budget:
            best = max(available, key=lambda index: (sizes[index], -index))
            chosen.append(best)
            available.remove(best)
            covered |= masks[best]

    records = []
    for k in budgets:
        prefixes = []
        for state in states[:k + 1]:
            prefixes.append({"t": state["t"], "selected": state["selected"].copy(),
                             "coverage": state["coverage"], "order": state["order"].copy(),
                             "s": state["s"].copy(), "F": state["F"].copy(),
                             "q": state["q"][:k + 1],
                             "upper": state["coverage"] + state["q"][k]})
        dual_upper = min(union_size, *(prefix["upper"] for prefix in prefixes))
        records.append({"k": k, "path": chosen[:k], "greedy": states[k]["coverage"],
                        "union_size": union_size,
                        "initial_upper": min(union_size, k * states[0]["s"][0]),
                        "prefix_upper": min(union_size, *(state["coverage"] + k * state["s"][0]
                                                          for state in states[:k + 1])),
                        "dual_upper": dual_upper,
                        "minimizing_prefixes": [prefix["t"] for prefix in prefixes
                                                if prefix["upper"] == dual_upper],
                        "prefixes": prefixes})
    return records
