"""Optional backends for the bounded local R2 pipeline adapter."""
import ast
from pathlib import Path
import numpy as np
from numba import njit
from trial import CUDA_SOURCE, all_budget_optima

# Reuse exactly the CPU implementation measured in v1, without running its harness.
source = Path(__file__).with_name('trial.py').read_text(encoding='utf-8')
tree = ast.parse(source)
cpu_node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'cpu_scores')
namespace = {'np': np}
exec(compile(ast.Module(body=[ast.FunctionDef(name=cpu_node.name, args=cpu_node.args,
    body=cpu_node.body, decorator_list=[], returns=None, type_comment=None,
    lineno=cpu_node.lineno, col_offset=0)], type_ignores=[]), '<cpu-v1>', 'exec'), namespace)
CPU_SCORES = njit(namespace['cpu_scores'])


def decode(scores, m):
    result = []
    for row in scores:
        values, witnesses = [], []
        for score in row:
            score = int(score)
            values.append(score >> m)
            witnesses.append(tuple(i for i in range(m) if score & (1 << (m-1-i))))
        result.append((values, witnesses, 1 << m))
    return result


class Backend:
    def __init__(self, mode, disabled=False):
        if mode not in {'compiled', 'hybrid'}:
            raise ValueError('unknown backend')
        self.mode = mode
        self.disabled = disabled
        self.events = []
        self.cp = None
        self.kernel = None

    def cpu(self, batch):
        return decode([CPU_SCORES(np.asarray(s, dtype=np.uint64)) for s in batch], len(batch[0]))

    def gpu(self, batch):
        if self.disabled:
            raise ImportError('CUDA deliberately unavailable in fallback test')
        if self.cp is None:
            import cupy
            self.cp = cupy
            self.kernel = cupy.RawKernel(CUDA_SOURCE, 'optima')
        cp = self.cp
        m = len(batch[0])
        masks = cp.asarray(np.asarray(batch, dtype=np.uint64))
        out = cp.zeros((len(batch), m+1), dtype=cp.uint64)
        self.kernel((((1 << m)+255)//256, len(batch)), (256,),
                    (masks, out, np.int32(m), np.int32(len(batch))))
        return decode(cp.asnumpy(out), m)

    def __call__(self, batch):
        if not batch or not 1 <= len(batch[0]) <= 20:
            raise ValueError('batch requires 1<=m<=20')
        m = len(batch[0])
        if any(len(s) != m or any(type(v) is not int or v < 0 for v in s) for s in batch):
            raise ValueError('equal m and nonnegative integer masks required')
        if any(v >= 2**64 for s in batch for v in s):
            result = [all_budget_optima(s) for s in batch]
            selected, reason = 'python', 'mask exceeds 64 bits'
        elif self.mode == 'hybrid' and m >= 20:
            try:
                result = self.gpu(batch)
                selected, reason = 'cuda', None
            except Exception as error:
                # Fallback only for unavailable CUDA/runtime/compiler/allocation.
                allowed = isinstance(error, (ImportError, OSError))
                if self.cp is not None:
                    allowed |= isinstance(error, (self.cp.cuda.runtime.CUDARuntimeError,
                        self.cp.cuda.memory.OutOfMemoryError, self.cp.cuda.compiler.CompileException))
                if not allowed:
                    raise
                result = self.cpu(batch)
                selected, reason = 'compiled', f'{type(error).__name__}: {error}'
        else:
            result = self.cpu(batch)
            selected, reason = 'compiled', None
        self.events.append({'m': m, 'count': len(batch), 'selected': selected, 'fallback': reason})
        return result
