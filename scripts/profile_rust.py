"""Bounded profiling of existing kernels; diagnostics never alter production dispatch."""
from __future__ import annotations

import argparse
import cProfile
import csv
import importlib.metadata
import json
from pathlib import Path
import platform
import pstats
import shutil
import statistics
import struct
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from benchmark_algorithms_rust import (ROOT, answers, instance_record, larger_inputs,
    reference_from_git, small_inputs, solution_record)
from maxcover.algorithms import greedy, lazy_greedy
from maxcover.model import MaximumCoverageInstance
from maxcover.structure import analyze_instance


def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def process_peak():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (key, ctypes.c_size_t) for key in ("peak", "working", "pool_peak", "pool",
                    "nonpaged_peak", "nonpaged", "pagefile", "peak_pagefile", "private")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.peak
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def packed_counts(buffers, n):
    import maxcover_profile_native as diagnostic
    frequencies, pairs, dominated = diagnostic.counts_packed(buffers, n)
    return frequencies, struct.iter_unpack("<QQ", pairs), dominated


def memory_worker(inputs, index, backend, tracker):
    raw = json.loads(inputs.read_text(encoding="utf-8"))
    item = MaximumCoverageInstance(**raw[index])
    import maxcover_structure_native as native
    if backend == "packed":
        __import__("maxcover_profile_native")
    before = process_peak()
    if tracker == "python":
        tracemalloc.start()
    if backend == "packed":
        with patch.object(native, "counts", new=packed_counts):
            result = analyze_instance(item, backend="rust")
    else:
        result = analyze_instance(item, backend=backend)
    retained, peak = tracemalloc.get_traced_memory() if tracker == "python" else (None, None)
    if tracker == "python":
        tracemalloc.stop()
    after = process_peak()
    return {"instance": index, "backend": backend, "tracker": tracker, "python_peak_bytes": peak,
            "python_retained_bytes": retained, "process_peak_before_bytes": before,
            "process_peak_after_bytes": after, "process_peak_increase_bytes": max(0, after - before),
            "incidence_count": result.incidence_count}


def verify_diagnostics():
    import maxcover_structure_native as native
    import maxcover_profile_native as diagnostic
    checked = 0
    for n in (1, 7, 8, 63, 64, 65, 129, 257):
        masks = (0, 1, 1 << (n - 1), (1 << n) - 1, 1)
        buffers = [m.to_bytes((n + 7) // 8, "little") for m in masks]
        prepared = diagnostic.Prepared(buffers, n)
        counts = native.counts(buffers, n)
        assert diagnostic.counts_profile(buffers, n)[0] == prepared.counts() == counts
        frequencies, packed, dominated = diagnostic.counts_packed(buffers, n)
        assert (frequencies, list(struct.iter_unpack("<QQ", packed)), dominated) == counts
        for k in (1, 3, 5):
            expected = native.lazy_greedy(buffers, n, k)
            assert diagnostic.lazy_profile(buffers, n, k)[0] == prepared.lazy(k) == expected
            checked += 1
    for buffers, n in (([], 1), ([b""], 1), ([b"\x80"], 7)):
        for function in (diagnostic.counts_profile, diagnostic.counts_packed, diagnostic.Prepared):
            try:
                function(buffers, n)
            except ValueError:
                pass
            else:
                raise ValueError("diagnostic accepted an invalid input")
    print(f"Diagnostic parity passed: {checked} boundary/budget cases and invalid-input rejection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--memory-case", type=int)
    parser.add_argument("--backend", choices=("python", "rust", "packed"))
    parser.add_argument("--memory-tracker", choices=("python", "process"), default="python")
    parser.add_argument("--confirm-packed", action="store_true", help="Paired public-adapter comparison and separate memory trackers")
    parser.add_argument("--verify-only", action="store_true", help="Short diagnostic parity check, without timing or Git reference inputs")
    args = parser.parse_args()
    if args.verify_only:
        verify_diagnostics()
        return
    if args.memory_case is not None:
        if args.inputs is None or args.backend is None:
            parser.error("memory worker needs inputs and backend")
        print(json.dumps(memory_worker(args.inputs, args.memory_case, args.backend, args.memory_tracker)))
        return
    if args.output is None or args.repeats < 2 or args.repeats % 2:
        parser.error("output and a positive even repeat count >= 2 are required")
    import maxcover_structure_native as native
    import maxcover_profile_native as diagnostic
    if args.inputs:
        raw = json.loads(args.inputs.read_text(encoding="utf-8"))
        instances = [MaximumCoverageInstance(**item) for item in raw]
    else:
        instances = [*small_inputs(), *larger_inputs()]
        raw = [instance_record(item) for item in instances]
    if len(instances) != 28:
        raise ValueError("this bounded profile requires the saved 24+4 input layout")
    old_algorithms, _ = reference_from_git("algorithms")
    old_structure, _ = reference_from_git("structure")
    expected = [answers(old_structure.analyze_instance(i), old_algorithms.greedy(i),
                        old_algorithms.lazy_greedy(i)) for i in instances]
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "inputs.json", raw)
    save(args.output / "expected.json", expected)
    source = args.output / "source"
    source.mkdir()
    shutil.copy2(__file__, source / Path(__file__).name)
    shutil.copy2(ROOT / "scripts/benchmark_algorithms_rust.py", source / "benchmark_algorithms_rust.py")
    shutil.copytree(ROOT / "experiments/rust_profile", source / "diagnostic",
                    ignore=shutil.ignore_patterns("target"))
    if args.confirm_packed:
        confirm_packed(args.output, instances, expected, args.repeats)
        return
    save(args.output / "config.json", {"python": sys.version, "platform": platform.platform(),
         "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
         "native_version": importlib.metadata.version("maxcover-structure-native"),
         "diagnostic_version": importlib.metadata.version("maxcover-profile-native"),
         "repeats": args.repeats, "cheap_operation_batch": 50, "warmups_per_operation": 1,
         "order": "fixed input order; alternate forward/reverse operation order",
         "scope": "hot function calls; native stage clocks exclude argument extraction and return boxing",
         "memory": "separate subprocesses; tracemalloc timing excluded from performance samples",
         "prepared": "diagnostic prototype only; one decode outside timed calls"})
    rows = []
    for index, item in enumerate(instances):
        width = (item.universe_size + 7) // 8
        encode = lambda: [mask.to_bytes(width, "little") for mask in item.sets]
        buffers = encode()
        reference_counts = native.counts(buffers, item.universe_size)
        reference_lazy = native.lazy_greedy(buffers, item.universe_size, item.k)
        prepared = diagnostic.Prepared(buffers, item.universe_size)
        operations = {
            "encode": encode,
            "ingest_owned": lambda: diagnostic.ingest_owned(buffers),
            "ingest_borrowed": lambda: diagnostic.ingest_borrowed(buffers),
            "native_counts": lambda: native.counts(buffers, item.universe_size),
            "profile_counts": lambda: diagnostic.counts_profile(buffers, item.universe_size),
            "prepared_counts": prepared.counts,
            "native_lazy": lambda: native.lazy_greedy(buffers, item.universe_size, item.k),
            "profile_lazy": lambda: diagnostic.lazy_profile(buffers, item.universe_size, item.k),
            "prepared_lazy": lambda: prepared.lazy(item.k),
        }
        for name, function in (("structure", analyze_instance), ("greedy", greedy), ("lazy_greedy", lazy_greedy)):
            for backend in ("python", "rust"):
                operations[f"{name}_{backend}"] = lambda f=function, b=backend: f(item, backend=b)
        def verify(name, result):
            if name in ("native_counts", "prepared_counts", "profile_counts"):
                assert (result[0] if name == "profile_counts" else result) == reference_counts, (index, name)
            elif name in ("native_lazy", "prepared_lazy", "profile_lazy"):
                assert (result[0] if name == "profile_lazy" else result) == reference_lazy, (index, name)
            elif name == "encode":
                assert result == buffers
            elif name == "ingest_owned":
                assert result == item.set_count
            elif name == "ingest_borrowed":
                assert result == item.set_count * width
            elif name.startswith("structure_"):
                from dataclasses import asdict
                assert asdict(result) == expected[index]["structure"], (index, name)
            else:
                assert solution_record(result) == expected[index][name.rsplit("_", 1)[0]], (index, name)
        for name, function in operations.items():
            verify(name, function())
        for repeat in range(args.repeats):
            names = list(operations) if repeat % 2 == 0 else list(reversed(operations))
            for position, name in enumerate(names):
                calls = 50 if name in ("encode", "ingest_owned", "ingest_borrowed") else 1
                start = time.perf_counter_ns()
                for _ in range(calls):
                    result = operations[name]()
                elapsed = (time.perf_counter_ns() - start) / calls / 1e9
                verify(name, result)
                row = {"instance": index, "repeat": repeat, "position": position, "operation": name,
                       "calls": calls, "seconds": elapsed}
                if name in ("profile_counts", "profile_lazy"):
                    keys = ("decode", "frequency", "pairs", "dominance") if name == "profile_counts" else ("decode", "queue", "selection")
                    row.update({key: value / 1e9 for key, value in zip(keys, result[1])})
                    row["boundary_and_cleanup"] = elapsed - sum(result[1]) / 1e9
                rows.append(row)
                del result
        print(f"Profiled {index + 1}/28", flush=True)
    fields = ["instance", "repeat", "position", "operation", "calls", "seconds", "decode", "frequency",
              "pairs", "dominance", "queue", "selection", "boundary_and_cleanup"]
    with (args.output / "timings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for index, item in enumerate(instances):
        medians = {}
        for name in operations:
            samples = [r for r in rows if r["instance"] == index and r["operation"] == name]
            medians[name] = {key: statistics.median(r[key] for r in samples) for key in fields[5:] if key in samples[0]}
        summary.append({"instance": index, "n": item.universe_size, "m": item.set_count,
                        "k": item.k, "family": item.family, "median_seconds": medians})
    save(args.output / "summary.json", summary)
    memory = []
    for index in (13, 24, 25, 26, 27):
        for backend in ("python", "rust"):
            for tracker in ("python", "process"):
                command = [sys.executable, str(Path(__file__).resolve()), "--inputs", str((args.output / "inputs.json").resolve()),
                           "--memory-case", str(index), "--backend", backend, "--memory-tracker", tracker]
                result = json.loads(subprocess.check_output(command, text=True))
                assert result["incidence_count"] == expected[index]["structure"]["incidence_count"]
                memory.append(result)
    save(args.output / "memory.json", memory)
    profiles = []
    for index in (25, 26):
        for backend in ("python", "rust"):
            profile = cProfile.Profile()
            profile.runcall(analyze_instance, instances[index], backend=backend)
            stats = pstats.Stats(profile)
            top = sorted(stats.stats.items(), key=lambda pair: pair[1][2], reverse=True)[:12]
            profiles.append({"instance": index, "backend": backend, "top_self_seconds": [
                {"function": str(key), "calls": value[1], "self_seconds": value[2], "cumulative_seconds": value[3]}
                for key, value in top]})
    save(args.output / "python-profile.json", profiles)
    print("Completed timing, separate-process memory and Python call profiles")


def confirm_packed(output, instances, expected, repeats):
    from dataclasses import asdict
    import maxcover_structure_native as native
    import maxcover_profile_native as diagnostic
    save(output / "config.json", {"repeats": repeats, "python": sys.version, "platform": platform.platform(),
         "native_version": importlib.metadata.version("maxcover-structure-native"),
         "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
         "change": "diagnostic packed pair transport; existing public Python assembly and fsum order unchanged",
         "timing": "alternating original/packed; patch setup excluded; one warmup per variant",
         "memory": "tracemalloc and OS process peak in separate subprocesses"})
    rows = []
    for index, item in enumerate(instances):
        buffers = [m.to_bytes((item.universe_size + 7) // 8, "little") for m in item.sets]
        reference = native.counts(buffers, item.universe_size)
        frequencies, data, dominated = diagnostic.counts_packed(buffers, item.universe_size)
        assert (frequencies, list(struct.iter_unpack("<QQ", data)), dominated) == reference
        for repeat in range(-1, repeats):
            order = ("original", "packed") if repeat % 2 == 0 else ("packed", "original")
            for position, variant in enumerate(order):
                with patch.object(native, "counts", new=packed_counts if variant == "packed" else native.counts):
                    started = time.perf_counter_ns()
                    result = analyze_instance(item, backend="rust")
                    elapsed = (time.perf_counter_ns() - started) / 1e9
                assert asdict(result) == expected[index]["structure"], (index, variant)
                if repeat >= 0:
                    rows.append({"instance": index, "repeat": repeat, "position": position,
                                 "variant": variant, "seconds": elapsed})
                del result
        print(f"Confirmed packed {index + 1}/28", flush=True)
    with (output / "timings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = []
    for index, item in enumerate(instances):
        samples = {v: [r["seconds"] for r in rows if r["instance"] == index and r["variant"] == v]
                   for v in ("original", "packed")}
        ratios = [a/b for a,b in zip(samples["original"], samples["packed"])]
        summary.append({"instance": index, "n": item.universe_size, "m": item.set_count,
                        "median_seconds": {v: statistics.median(s) for v,s in samples.items()},
                        "paired_speedup_median": statistics.median(ratios),
                        "paired_speedup_min": min(ratios), "paired_speedup_max": max(ratios)})
    save(output / "summary.json", summary)
    memory = []
    for index in (13, 24, 25, 26, 27):
        for backend in ("python", "rust", "packed"):
            for tracker in ("python", "process"):
                command = [sys.executable, str(Path(__file__).resolve()), "--inputs", str((output / "inputs.json").resolve()),
                           "--memory-case", str(index), "--backend", backend, "--memory-tracker", tracker]
                result = json.loads(subprocess.check_output(command, text=True))
                assert result["incidence_count"] == expected[index]["structure"]["incidence_count"]
                memory.append(result)
    save(output / "memory.json", memory)
    print("Completed paired packed-transport comparison and independent memory measurements")


if __name__ == "__main__":
    sys.set_int_max_str_digits(0)
    main()
