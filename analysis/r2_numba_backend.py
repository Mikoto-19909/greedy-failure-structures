"""Compiled production DP; imported only when explicitly selecting a CPU accelerator."""
import numpy as np
from numba import njit


@njit(cache=True)
def _scores(sets):
    m = len(sets)
    size = 1 << m
    unions = np.zeros(size, dtype=np.uint64)
    cardinalities = np.zeros(size, dtype=np.uint8)
    ranks = np.zeros(size, dtype=np.uint32)
    best = np.zeros(m + 1, dtype=np.uint64)
    visited = 1
    for subset in range(1, size):
        rest = subset & (subset - 1)
        low = subset ^ rest
        index = 0
        while (1 << index) != low:
            index += 1
        covered = unions[rest] | sets[index]
        unions[subset] = covered
        k = cardinalities[rest] + 1
        cardinalities[subset] = k
        rank = ranks[rest] | (1 << (m - 1 - index))
        ranks[subset] = rank
        value = 0
        while covered:
            covered &= covered - np.uint64(1)
            value += 1
        score = (np.uint64(value) << np.uint64(m)) | np.uint64(rank)
        if score > best[k]:
            best[k] = score
        visited += 1
    return best, visited


def solve(sets):
    scores, visited = _scores(np.asarray(sets, dtype=np.uint64))
    m = len(sets)
    values = [int(score) >> m for score in scores]
    witnesses = [tuple(i for i in range(m) if int(score) & (1 << (m - 1 - i))) for score in scores]
    return values, witnesses, int(visited)
