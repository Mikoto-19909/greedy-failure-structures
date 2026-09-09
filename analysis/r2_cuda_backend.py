"""Single-owner CUDA production. No CUDA imports or environment edits on import."""
import multiprocessing
import os
from pathlib import Path
import tempfile

POOL_LIMIT = 64 * 1024**2
FREE_RESERVE = 128 * 1024**2
_ready = False
_state = None

SOURCE = r'''
extern "C" __global__ void optima(const unsigned long long* sets,
    unsigned long long* out, unsigned int* visited, int m, int instrument) {
    __shared__ unsigned long long best[21];
    __shared__ unsigned int count;
    int tid = threadIdx.x;
    if (tid <= m) best[tid] = 0;
    if (tid == 0) count = 0;
    __syncthreads();
    unsigned int subset = blockIdx.x * blockDim.x + tid;
    if (subset < (1u << m)) {
        unsigned long long covered = 0;
        unsigned int bits = subset;
        while (bits) {
            int i = __ffs(bits) - 1;
            covered |= sets[i];
            bits &= bits - 1;
        }
        int k = __popc(subset);
        unsigned int rank = __brev(subset) >> (32 - m);
        unsigned long long score = ((unsigned long long)__popcll(covered) << m) | rank;
        atomicMax(&best[k], score);
        if (instrument) atomicAdd(&count, 1u);
    }
    __syncthreads();
    if (tid <= m) atomicMax(&out[tid], best[tid]);
    if (instrument && tid == 0) atomicAdd(visited, count);
}
'''


def initialize_worker(cache_dir):
    global _ready
    path = Path(cache_dir).resolve()
    if not str(path).isascii():
        raise ValueError('CUDA compilation requires an ASCII --cuda-cache-dir on this Windows setup')
    (path / 'tmp').mkdir(parents=True, exist_ok=True)
    (path / 'cache').mkdir(exist_ok=True)
    os.environ['CUPY_CACHE_DIR'] = str(path / 'cache')
    tempfile.tempdir = str(path / 'tmp')
    _ready = True


def _load():
    global _state
    if not _ready:
        raise RuntimeError('CUDA production must run in its isolated owner process')
    if _state is None:
        import cupy as cp
        import numpy as np
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError('no CUDA device available; install .[production-cuda] and a compatible driver')
        cp.cuda.Device(0).use()
        free, total = cp.cuda.runtime.memGetInfo()
        if free < POOL_LIMIT + FREE_RESERVE:
            raise MemoryError('insufficient CUDA free memory including context reserve')
        pool = cp.cuda.MemoryPool()
        pool.set_limit(size=POOL_LIMIT)
        kernel = cp.RawKernel(SOURCE, 'optima')
        properties = cp.cuda.runtime.getDeviceProperties(0)
        _state = cp, np, pool, kernel, properties
    return _state


def solve(sets, *, instrument=False, _test_blocks=None):
    if not 1 <= len(sets) <= 20 or any(type(v) is not int or not 0 <= v < 2**64 for v in sets):
        raise ValueError('CUDA input requires 1<=M<=20 and unsigned 64-bit masks')
    initializing = _state is None
    cp, np, pool, kernel, properties = _load()
    m = len(sets)
    blocks = ((1 << m) + 255) // 256 if _test_blocks is None else _test_blocks
    if not 1 <= blocks <= properties['maxGridSize'][0]:
        raise ValueError('invalid CUDA grid size')
    free, _ = cp.cuda.runtime.memGetInfo()
    if free < FREE_RESERVE:
        raise MemoryError('CUDA free memory below reserved headroom')
    with cp.cuda.using_allocator(pool.malloc):
        masks = cp.asarray(np.asarray(sets, dtype=np.uint64))
        out = cp.zeros(m + 1, dtype=cp.uint64)
        count = cp.zeros(1, dtype=cp.uint32)
        begin, end = cp.cuda.Event(), cp.cuda.Event()
        begin.record()
        kernel((blocks,), (256,), (masks, out, count, np.int32(m), np.int32(instrument)))
        end.record()
        scores = cp.asnumpy(out, blocking=True)
        kernel_seconds = cp.cuda.get_elapsed_time(begin, end) / 1000
        if instrument and int(cp.asnumpy(count, blocking=True)[0]) != 1 << m:
            raise ValueError('incomplete CUDA thread coverage')
    values = [int(score) >> m for score in scores]
    witnesses = [tuple(i for i in range(m) if int(score) & (1 << (m - 1 - i))) for score in scores]
    # Complete launch geometry is independently counted in explicit GPU tests.
    result = values, witnesses, 1 << m
    from r2_production_backends import check_result
    check_result(sets, result)
    name = properties['name']
    return result, {'device': name.decode() if isinstance(name, bytes) else str(name),
                    'initialization_included': initializing,
                    'kernel_seconds': kernel_seconds,
                    'owner_pid': os.getpid(), 'pool_retained_bytes': pool.total_bytes(),
                    'pool_limit_bytes': POOL_LIMIT, 'free_device_bytes': int(free),
                    'subset_count_kind': 'instrumented' if instrument else 'complete_launch_geometry'}


def computed_cuda_results(function, arguments, budget, cache_dir):
    context = multiprocessing.get_context('spawn')
    connection, child = context.Pipe()
    owner = context.Process(target=_owner_main, args=(child, str(cache_dir)))
    owner.start()
    child.close()
    completed = False
    try:
        _receive(connection, owner, budget, 'ready')
        for item in arguments:
            budget.check()
            connection.send((function, item))
            value = _receive(connection, owner, budget, 'result')
            budget.check()
            yield value
        completed = True
    finally:
        if owner.is_alive():
            if completed:
                connection.send(None)
                owner.join(timeout=5)
            if owner.is_alive():
                owner.terminate()
                owner.join(timeout=5)
            if owner.is_alive():
                owner.kill()
                owner.join(timeout=5)
        else:
            owner.join()
        connection.close()
        owner.close()


def _receive(connection, owner, budget, expected):
    while True:
        budget.check()
        if connection.poll(0.1):
            try:
                kind, value = connection.recv()
            except EOFError as error:
                raise RuntimeError('CUDA owner exited without a complete result') from error
            if kind != expected:
                raise RuntimeError(f'CUDA owner failed: {value}')
            return value
        if not owner.is_alive():
            raise RuntimeError(f'CUDA owner exited without a result (exit code {owner.exitcode})')


def _owner_main(connection, cache_dir):
    try:
        initialize_worker(cache_dir)
        connection.send(('ready', None))
        while True:
            request = connection.recv()
            if request is None:
                return
            function, arguments = request
            connection.send(('result', function(*arguments)))
    except Exception as error:
        try:
            connection.send(('error', f'{type(error).__name__}: {error}'))
        except (BrokenPipeError, OSError):
            pass
    finally:
        connection.close()
