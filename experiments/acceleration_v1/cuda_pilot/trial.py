"""Bounded local CUDA experiment; no production backend changes."""
from pathlib import Path
import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'analysis')]
os.environ['CUPY_CACHE_DIR'] = str(HERE / 'cupy_cache')
# NVRTC on Windows cannot open source paths containing this account's Chinese name.
import tempfile
(HERE / 'tmp').mkdir(exist_ok=True)
tempfile.tempdir = str(HERE / 'tmp')
os.environ['CUDA_PATH'] = str(HERE / '.venv/Lib/site-packages/nvidia/cuda_runtime')
from maxcover._generators_random import fixed_size
from r2_budget_grid import all_budget_optima


def save(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def prepare():
    design = json.loads((ROOT / 'analysis/r2_f2_config.json').read_text())
    tasks = [t for t in design['tasks'] if t['repetition'] == 0]
    graphs = []
    for t in tasks:
        obj = fixed_size(universe_size=t['n'], set_count=t['n'], k=1,
                         set_size=t['d'], unique_sets=False, seed=t['seed'])
        graphs.append({'task': t, 'sets': list(obj.sets)})
    path = HERE / 'design.json'
    if path.exists():
        raise RuntimeError('Design exists; reuse it without replacing frozen inputs')
    save('design.json', {'graphs': graphs, 'repeats': 5,
        'scope': 'All budgets, including zero, of 9 existing R2 graphs; integer masks <=64 bits; m<=20',
        'order': 'Rotate python,cpu_compiled,cuda each repeat; one untimed warmup',
        'timing': 'Warm end-to-end compute from host masks to Python values and witnesses; CUDA includes allocation, H2D, kernel, sync, D2H, decode. Input generation, validation and disk I/O excluded for all backends.',
        'acceptance': 'Exact values and lexicographically smallest witnesses for every k; independent set-based verifier; report median and range, no extrapolation',
        'limits': {'max_wall_seconds': 600, 'max_m': 20, 'repeats': 5},
        'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()})
    print('Frozen', len(graphs), 'graphs', flush=True)


CUDA_SOURCE = r'''
extern "C" __global__ void optima(const unsigned long long* sets,
                                 unsigned long long* out, int m, int count) {
    __shared__ unsigned long long local_best[21];
    int tid = threadIdx.x;
    int graph = blockIdx.y;
    if (tid <= m) local_best[tid] = 0;
    __syncthreads();
    unsigned int subset = blockIdx.x * blockDim.x + tid;
    if (subset < (1u << m) && graph < count) {
        unsigned long long covered = 0;
        unsigned int bits = subset;
        while (bits) {
            int i = __ffs(bits) - 1;
            covered |= sets[graph * m + i];
            bits &= bits - 1;
        }
        int k = __popc(subset);
        // For fixed cardinality, larger reversed bits mean smaller lex witness.
        unsigned int rank = __brev(subset) >> (32 - m);
        unsigned long long score = ((unsigned long long)__popcll(covered) << m) | rank;
        atomicMax(&local_best[k], score);
    }
    __syncthreads();
    if (tid <= m) atomicMax(&out[graph * (m + 1) + tid], local_best[tid]);
}
'''


def run():
    start = time.perf_counter()
    import numpy as np
    from numba import njit
    import cupy as cp
    imports = time.perf_counter() - start
    design = json.loads((HERE / 'design.json').read_text())
    kernel = cp.RawKernel(CUDA_SOURCE, 'optima')

    @njit
    def cpu_scores(sets):
        # DP shares the union for subset without its lowest bit.
        m = len(sets)
        size = 1 << m
        unions = np.zeros(size, dtype=np.uint64)
        sizes = np.zeros(size, dtype=np.uint8)
        ranks = np.zeros(size, dtype=np.uint32)
        best = np.zeros(m + 1, dtype=np.uint64)
        for subset in range(1, size):
            rest = subset & (subset - 1)
            low = subset ^ rest
            index = 0
            while (1 << index) != low:
                index += 1
            covered = unions[rest] | sets[index]
            unions[subset] = covered
            k = sizes[rest] + 1
            sizes[subset] = k
            rank = ranks[rest] | (1 << (m - 1 - index))
            ranks[subset] = rank
            value = 0
            while covered:
                covered &= covered - np.uint64(1)
                value += 1
            score = (np.uint64(value) << np.uint64(m)) | np.uint64(rank)
            if score > best[k]:
                best[k] = score
        return best

    def checked(batch):
        if not batch or not 1 <= len(batch[0]) <= 20:
            raise ValueError('requires nonempty batch and 1<=m<=20')
        m = len(batch[0])
        if any(len(s) != m or any(type(v) is not int or not 0 <= v < 2**64 for v in s) for s in batch):
            raise ValueError('equal m and unsigned 64-bit integer masks required')
        return m

    def decode(scores, m):
        result = []
        for row in scores:
            values, witnesses = [], []
            for v in row:
                v = int(v)
                values.append(v >> m)
                witnesses.append(tuple(i for i in range(m) if v & (1 << (m-1-i))))
            result.append((values, witnesses))
        return result

    def python_backend(batch):
        checked(batch)
        return [(r[0], r[1]) for r in map(all_budget_optima, batch)]

    def cpu_backend(batch):
        m = checked(batch)
        return decode([cpu_scores(np.asarray(s, dtype=np.uint64)) for s in batch], m)

    def cuda_backend(batch):
        m = checked(batch)
        masks = cp.asarray(np.asarray(batch, dtype=np.uint64))
        out = cp.zeros((len(batch), m + 1), dtype=cp.uint64)
        kernel((((1 << m) + 255)//256, len(batch)), (256,),
               (masks, out, np.int32(m), np.int32(len(batch))))
        scores = cp.asnumpy(out)  # Blocking D2H: timing cannot omit device execution.
        return decode(scores, m)

    backends = {'python': python_backend, 'cpu_compiled': cpu_backend, 'cuda': cuda_backend}
    cold = {'imports_seconds': imports}
    for name, function in backends.items():
        t = time.perf_counter()
        function([[1, 2, 3]])
        cold[name + '_first_call_seconds'] = time.perf_counter() - t
    save('cold_start.json', cold)
    print('Cold start', cold, flush=True)

    # Independent validation uses ordinary Python sets/combinations, not packed scores.
    from validate_r2_budget_grid import reference
    fixtures = [[0], [0, 0, 0], [3, 3, 3, 3], [1, 2, 4, 8],
                [1 << 63, (1 << 64) - 1, 0, 1]]
    invalid = [[], [[]], [[-1]], [[2**64]], [[True]], [[1] * 21], [[1], [1, 2]]]
    checks = []
    for masks in fixtures + [g['sets'] for g in design['graphs']]:
        m = len(masks)
        sets = [{i for i in range(64) if v & (1 << i)} for v in masks]
        truth = [reference(sets, k) for k in range(m+1)]
        expected = ([r[0] for r in truth], [tuple(r[1]) for r in truth])
        for name, function in backends.items():
            assert function([masks])[0] == expected, (name, m, masks)
        checks.append({'m': m, 'budgets_checked': m+1, 'passed': True})
        print('Verified m=', m, flush=True)
        if time.perf_counter() - start > 600:
            raise RuntimeError('600 second wall budget exhausted')
    for name, function in backends.items():
        for batch in invalid:
            try:
                function(batch)
            except ValueError:
                pass
            else:
                raise AssertionError((name, 'invalid input accepted', batch))
    save('validation.json', {'passed': True, 'fixtures_and_graphs': checks,
        'invalid_inputs_per_backend': len(invalid), 'backends': list(backends),
        'reference': 'analysis/validate_r2_budget_grid.py:reference; ordinary Python sets and itertools.combinations'})

    rows = []
    for m in [12, 16, 20]:
        graphs = [g for g in design['graphs'] if len(g['sets']) == m]
        for batch_size in [1, 3]:
            batch = [g['sets'] for g in graphs[:batch_size]]
            expected = python_backend(batch)
            for function in backends.values():
                assert function(batch) == expected
            for repeat in range(design['repeats']):
                names = list(backends)
                names = names[repeat % 3:] + names[:repeat % 3]
                for order, name in enumerate(names):
                    t = time.perf_counter()
                    actual = backends[name](batch)
                    elapsed = time.perf_counter() - t
                    assert actual == expected
                    rows.append({'m': m, 'batch': batch_size, 'repeat': repeat,
                                 'order': order, 'backend': name, 'seconds': elapsed})
            print('Measured m=', m, 'batch=', batch_size, flush=True)
            save('timings.json', rows)
            if time.perf_counter() - start > 600:
                raise RuntimeError('600 second wall budget exhausted')
    summaries = []
    for m in [12, 16, 20]:
        for batch_size in [1, 3]:
            entry = {'m': m, 'batch': batch_size}
            for name in backends:
                values = [r['seconds'] for r in rows if (r['m'], r['batch'], r['backend']) == (m, batch_size, name)]
                entry[name] = {'median': statistics.median(values), 'min': min(values), 'max': max(values)}
            entry['cuda_speedup_vs_python'] = entry['python']['median']/entry['cuda']['median']
            entry['cuda_speedup_vs_compiled_cpu'] = entry['cpu_compiled']['median']/entry['cuda']['median']
            summaries.append(entry)
    props = cp.cuda.runtime.getDeviceProperties(0)
    save('summary.json', {'status': 'complete', 'summaries': summaries,
        'cold_start': cold, 'total_wall_seconds': time.perf_counter() - start,
        'environment': {'python': sys.version, 'platform': platform.platform(), 'cupy': cp.__version__,
                        'numpy': np.__version__, 'gpu': props['name'].decode(),
                        'driver_version': cp.cuda.runtime.driverGetVersion(),
                        'runtime_version': cp.cuda.runtime.runtimeGetVersion(),
                        'cupy_pool_peak_retained_bytes': cp.get_default_memory_pool().total_bytes()},
        'limits': 'Kernel prototype only; no whole-pipeline or CPU-process-pool speedup claim; shared laptop, five warm repetitions, fixed nine graphs.'})
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'run'])
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare()
    else:
        run()
