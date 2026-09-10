"""Optional independent CPU completion enumeration, with a Python fallback.

The numeric kernel uses Boolean incidence and lexicographic combinations. It
does not import a producer, its coverage helpers, or any CUDA implementation.
"""
from functools import lru_cache
import math
import warnings

BACKENDS = ('python', 'auto', 'numba')


class FastVerificationUnavailable(RuntimeError):
    """The optional dependency or its initialization cannot be used."""


def validate_backend(backend):
    if backend not in BACKENDS:
        raise ValueError(f'unknown verification backend: {backend!r}')


def _enumerate(incidence, fixed, outside, remaining):
    universe = incidence.shape[1]
    base = [False] * universe
    for index in fixed:
        for element in range(universe):
            if incidence[index, element]:
                base[element] = True
    positions = list(range(remaining))
    best = -1
    optimal_count = 0
    inspected = 0
    witness = list(fixed)
    while True:
        value = 0
        for element in range(universe):
            present = base[element]
            if not present:
                for j in range(remaining):
                    if incidence[outside[positions[j]], element]:
                        present = True
                        break
            value += present
        inspected += 1
        if value > best:
            best, optimal_count = value, 1
            witness = sorted(list(fixed) + [outside[positions[j]] for j in range(remaining)])
        elif value == best:
            optimal_count += 1
        # Adding the same fixed indices preserves the order of the outside combinations.
        j = remaining - 1
        while j >= 0 and positions[j] == len(outside) - remaining + j:
            j -= 1
        if j < 0:
            break
        positions[j] += 1
        for p in range(j + 1, remaining):
            positions[p] = positions[p - 1] + 1
    return best, witness, inspected, optimal_count


def _build_solver():
    try:
        import numpy as np
        from numba import njit
        from numba.core.errors import NumbaError
    except (ImportError, OSError) as error:
        raise FastVerificationUnavailable(str(error)) from error
    try:
        kernel = njit(cache=True)(_enumerate)
        probe = kernel(np.array([[1]], dtype=np.uint8),
                       np.array([], dtype=np.int64), np.array([0], dtype=np.int64), 1)
    except (NumbaError, OSError, RuntimeError) as error:
        raise FastVerificationUnavailable(str(error)) from error
    if probe != (1, [0], 1, 1):
        raise AssertionError('compiled completion initialization returned an incorrect result')

    def solve(sets, k, prefix, limit):
        m = len(sets)
        if type(k) is not int or not 0 <= k <= m:
            raise ValueError('invalid completion budget')
        if any(type(i) is not int or not 0 <= i < m for i in prefix):
            raise ValueError('invalid completion index')
        fixed = sorted(prefix)
        if len(set(fixed)) != len(fixed) or len(fixed) > k:
            raise ValueError('invalid completion prefix')
        outside = [i for i in range(m) if i not in fixed]
        count = math.comb(len(outside), k - len(fixed))
        if count > limit:
            raise ValueError('completion enumeration exceeds the design budget')
        if count > 2**63 - 1:
            raise ValueError('completion count exceeds the compiled integer range')
        elements = sorted(set().union(*sets))
        incidence = np.asarray([[e in s for e in elements] for s in sets], dtype=np.uint8)
        incidence = incidence.reshape(m, len(elements))
        result = kernel(incidence, np.asarray(fixed, dtype=np.int64),
                        np.asarray(outside, dtype=np.int64), k - len(fixed))
        best, witness, inspected, optimal_count = result
        if inspected != count:
            raise ValueError('incomplete completion enumeration')
        return int(best), list(witness), int(inspected), int(optimal_count)

    return solve


@lru_cache(maxsize=1)
def _optional_solver():
    # Cache initialization failures too, so each worker attempts initialization once.
    try:
        return _build_solver(), None
    except FastVerificationUnavailable as error:
        return None, str(error)


@lru_cache(maxsize=3)
def get_completion_solver(backend='python'):
    validate_backend(backend)
    from validate_greedy_failure_paths import best_completion
    if backend == 'python':
        return best_completion
    solver, reason = _optional_solver()
    if solver is not None:
        return solver
    message = ('Fast verification unavailable; install with '
               '`python -m pip install ".[fast-verification]"`. ' + str(reason))
    if backend == 'numba':
        raise FastVerificationUnavailable(message)
    warnings.warn(message + ' Using the original Python verifier.', RuntimeWarning, stacklevel=2)
    return best_completion
