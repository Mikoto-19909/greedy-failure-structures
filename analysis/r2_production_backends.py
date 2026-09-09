"""Optional exact R2 production backends; no verifier calculations are imported."""
from functools import lru_cache
import importlib
import warnings

BACKENDS = ('python', 'numba', 'cuda', 'auto')


class ProductionBackendUnavailable(RuntimeError):
    pass


def validate_backend(name):
    if name not in BACKENDS:
        raise ValueError(f'unknown production backend: {name!r}')


@lru_cache(maxsize=1)
def _numba_backend():
    try:
        return importlib.import_module('r2_numba_backend'), None
    except (ImportError, OSError) as error:
        return None, f'{type(error).__name__}: {error}'


def check_result(sets, result):
    best, witnesses, visited = result
    m = len(sets)
    if len(best) != m + 1 or len(witnesses) != m + 1 or type(visited) is not int or visited != 1 << m:
        raise ValueError('incomplete all-budget result')
    for k, (value, chosen) in enumerate(zip(best, witnesses)):
        if type(value) is not int or value < 0 or len(chosen) != k:
            raise ValueError('invalid coverage or witness length')
        if any(type(i) is not int or not 0 <= i < m for i in chosen):
            raise ValueError('invalid witness index')
        if tuple(sorted(set(chosen))) != tuple(chosen):
            raise ValueError('witness must contain distinct ascending indices')
        covered = 0
        for i in chosen:
            covered |= sets[i]
        if covered.bit_count() != value or (k and value < best[k - 1]):
            raise ValueError('witness coverage or monotonicity mismatch')


def solve_optima(sets, backend, python_solver):
    validate_backend(backend)
    if not isinstance(sets, (tuple, list)) or any(type(v) is not int or v < 0 for v in sets):
        raise ValueError('candidate masks must be nonnegative integers')
    event = {'requested_backend': backend, 'actual_backend': None, 'fallback_reason': None}
    if not sets:
        return ([0], [()], 1), {**event, 'actual_backend': 'degenerate'}
    supported = len(sets) <= 20 and all(v < 2**64 for v in sets)
    if backend == 'python' or (backend == 'auto' and not supported):
        event.update(actual_backend='python', fallback_reason=None if backend == 'python' else 'outside accelerated input range')
        result = python_solver(sets)
    elif not supported:
        raise ValueError('accelerated production requires M<=20 and unsigned 64-bit masks')
    elif backend == 'cuda':
        # Strict: no catch converting CUDA runtime or result errors into CPU success.
        module = importlib.import_module('r2_cuda_backend')
        result, device = module.solve(sets)
        event.update(actual_backend='cuda', **device)
    else:
        module, reason = _numba_backend()
        if module is None:
            if backend != 'auto':
                raise ProductionBackendUnavailable('Install .[production-cpu]. ' + str(reason))
            warnings.warn('Numba production unavailable; using Python. ' + str(reason), RuntimeWarning, stacklevel=2)
            result = python_solver(sets)
            event.update(actual_backend='python', fallback_reason=reason)
        else:
            # JIT compilation, computation and result errors must propagate.
            event['initialization_included'] = not bool(getattr(getattr(module, '_scores', None), 'signatures', ()))
            result = module.solve(sets)
            event['actual_backend'] = 'numba'
    check_result(sets, result)
    return result, event
