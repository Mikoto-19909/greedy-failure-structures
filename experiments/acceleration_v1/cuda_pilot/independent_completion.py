"""Independent CPU completion enumeration; no producer calculation imports.

Uses a Boolean incidence matrix and lexicographic combinations. The production
CUDA backend instead uses integer bit masks and a packed atomic maximum.
"""
import math
from pathlib import Path
import sys
from unittest.mock import patch
import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'analysis'), str(ROOT/'src')]
import validate_greedy_failure_paths as paths
from validate_r2_budget_grid import verify_graph as original_verify_graph


@njit(cache=True)
def enumerate_completions(incidence, fixed, outside, r):
    universe = incidence.shape[1]
    base = np.zeros(universe, dtype=np.uint8)
    for index in fixed:
        for element in range(universe):
            if incidence[index, element]:
                base[element] = 1
    positions = np.arange(r)
    best = -1
    optimum_count = 0
    inspected = 0
    witness = np.empty(len(fixed)+r, dtype=np.int64)
    while True:
        value = 0
        for element in range(universe):
            present = base[element]
            if not present:
                for j in range(r):
                    if incidence[outside[positions[j]], element]:
                        present = 1
                        break
            value += present
        inspected += 1
        if value > best:
            best = value
            optimum_count = 1
            for j in range(len(fixed)):
                witness[j] = fixed[j]
            for j in range(r):
                witness[len(fixed)+j] = outside[positions[j]]
            witness.sort()
        elif value == best:
            optimum_count += 1
        # Lex order of outside combinations preserves lex order after fixed union.
        j = r-1
        while j >= 0 and positions[j] == len(outside)-r+j:
            j -= 1
        if j < 0:
            break
        positions[j] += 1
        for p in range(j+1,r):
            positions[p] = positions[p-1]+1
    return best, witness, inspected, optimum_count


def best_completion(sets, k, prefix, limit):
    m = len(sets)
    if type(k) is not int or not 0 <= k <= m:
        raise ValueError('invalid completion budget')
    if any(type(i) is not int or not 0 <= i < m for i in prefix):
        raise ValueError('invalid completion index')
    fixed = sorted(prefix)
    if len(set(fixed)) != len(fixed) or len(fixed) > k:
        raise ValueError('invalid completion prefix')
    outside = [i for i in range(m) if i not in fixed]
    count = math.comb(len(outside), k-len(fixed))
    if count > limit:
        raise ValueError('completion enumeration exceeds the design budget')
    elements = sorted(set().union(*sets))
    incidence = np.asarray([[e in s for e in elements] for s in sets], dtype=np.uint8)
    # Empty universes still require a two-dimensional incidence matrix.
    incidence = incidence.reshape(m,len(elements))
    best, witness, inspected, optimum_count = enumerate_completions(
        incidence, np.asarray(fixed,dtype=np.int64),
        np.asarray(outside,dtype=np.int64), k-len(fixed))
    if inspected != count:
        raise ValueError('incomplete completion enumeration')
    return int(best), witness.tolist(), int(inspected), int(optimum_count)


def verify_graph(record, task, limits):
    with patch.object(paths,'best_completion',best_completion):
        return original_verify_graph(record,task,limits)
