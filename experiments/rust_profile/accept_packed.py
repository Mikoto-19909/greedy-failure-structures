"""Compare frozen 0.2 and candidate 0.3 wheels in separate, serially sampled processes."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from maxcover.model import MaximumCoverageInstance
from profile_rust import process_peak

BASELINE = "7387f43d2133ebdbd8dfdf724c9f4e47af10eaad"


def pin_worker():
    """Use the same available logical CPU for only these owned measurement processes."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
        process, system = ctypes.c_size_t(), ctypes.c_size_t()
        handle = kernel.GetCurrentProcess()
        if not kernel.GetProcessAffinityMask(handle, ctypes.byref(process), ctypes.byref(system)):
            raise ctypes.WinError(ctypes.get_last_error())
        mask = process.value & -process.value
        if not mask or not kernel.SetProcessAffinityMask(handle, mask):
            raise ctypes.WinError(ctypes.get_last_error())
        return mask
    if hasattr(os, "sched_getaffinity"):
        cpu = min(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {cpu})
        return 1 << cpu
    raise RuntimeError("controlled acceptance requires process affinity support")


def load_adapter(mode, list_adapter):
    if mode == "stream":
        from maxcover.structure import analyze_instance
        return analyze_instance
    source = (subprocess.check_output(["git", "show", f"{BASELINE}:src/maxcover/structure.py"], cwd=ROOT)
              if mode == "baseline" else list_adapter.read_bytes())
    module = ModuleType(f"maxcover._accept_{mode}")
    sys.modules[module.__name__] = module
    exec(compile(source, f"{mode}/structure.py", "exec"), module.__dict__)
    return module.analyze_instance


def worker(args):
    affinity = pin_worker()
    import maxcover_structure_native as native
    function = load_adapter(args.worker, args.list_adapter)
    instances = [MaximumCoverageInstance(**item) for item in json.loads(args.inputs.read_text(encoding="utf-8"))]
    hits = {"counts": 0, "counts_packed": 0}
    for name in hits:
        if hasattr(native, name):
            original = getattr(native, name)
            def observed(*values, key=name, target=original):
                hits[key] += 1
                return target(*values)
            setattr(native, name, observed)
    if args.memory_case is not None:
        before = process_peak()
        if args.tracker == "python":
            tracemalloc.start()
        result = function(instances[args.memory_case], backend="rust")
        retained, peak = tracemalloc.get_traced_memory() if args.tracker == "python" else (None, None)
        if args.tracker == "python":
            tracemalloc.stop()
        print(json.dumps({"variant": args.worker, "instance": args.memory_case, "tracker": args.tracker,
                          "affinity_mask": affinity,
                          "python_peak_bytes": peak, "python_retained_bytes": retained,
                          "process_peak_before_bytes": before, "process_peak_after_bytes": process_peak(),
                          "metrics": asdict(result), "dispatch": hits}), flush=True)
        return
    print(json.dumps({"variant": args.worker, "python": sys.version,
                      "affinity_mask": affinity,
                      "wheel_version": importlib.metadata.version("maxcover-structure-native"),
                      "native_file": native.__file__}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("stop"):
            return
        item = instances[request["instance"]]
        before = hits.copy()
        start = time.perf_counter_ns()
        for _ in range(request["calls"]):
            result = function(item, backend="rust")
        elapsed = (time.perf_counter_ns() - start) / 1e9 / request["calls"]
        print(json.dumps({"seconds": elapsed, "metrics": asdict(result),
                          "dispatch": {key: hits[key] - before[key] for key in hits}}), flush=True)


def validate_result(result, variant, calls, expected):
    if result["metrics"] != expected:
        raise ValueError(f"non-timing result changed in {variant}")
    required = {"counts": calls if variant == "baseline" else 0,
                "counts_packed": 0 if variant == "baseline" else calls}
    if result["dispatch"] != required:
        raise ValueError(f"wrong native path in {variant}: {result['dispatch']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-python", type=Path)
    parser.add_argument("--candidate-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--list-adapter", type=Path)
    parser.add_argument("--worker", choices=("baseline", "list", "stream"))
    parser.add_argument("--memory-case", type=int)
    parser.add_argument("--tracker", choices=("python", "process"), default="process")
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if not all((args.expected, args.output, args.baseline_python)):
        parser.error("expected, output and baseline-python are required")
    raw = json.loads(args.inputs.read_text(encoding="utf-8"))
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    if len(raw) != 28 or len(expected) != 28:
        raise ValueError("expected the fixed 28 input/answer records")
    args.output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (args.output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    shutil.copy2(args.inputs, args.output / "inputs.json")
    shutil.copy2(args.expected, args.output / "expected.json")
    source = args.output / "source"
    source.mkdir()
    shutil.copy2(__file__, source / Path(__file__).name)
    shutil.copy2(ROOT / "src/maxcover/structure.py", source / "candidate_structure.py")
    shutil.copy2(ROOT / "src/maxcover/model.py", source / "model.py")
    shutil.copy2(ROOT / "scripts/profile_rust.py", source / "profile_rust.py")
    (source / "baseline_structure.py").write_bytes(subprocess.check_output(
        ["git", "show", f"{BASELINE}:src/maxcover/structure.py"], cwd=ROOT))
    shutil.copytree(ROOT / "native/structure/src", source / "native")
    for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml"):
        shutil.copy2(ROOT / "native/structure" / name, source / name)
    if args.list_adapter:
        shutil.copy2(args.list_adapter, source / "packed_list_structure.py")
    variants = ["baseline", *(["list"] if args.list_adapter else []), "stream"]
    commands = {}
    for variant in variants:
        interpreter = args.baseline_python if variant == "baseline" else args.candidate_python
        commands[variant] = [str(interpreter.resolve()), str(Path(__file__).resolve()), "--worker", variant,
                             "--inputs", str((args.output / "inputs.json").resolve())]
        if args.list_adapter:
            commands[variant] += ["--list-adapter", str(args.list_adapter.resolve())]
    children, metadata = {}, {}
    rows = []
    try:
        for variant, command in commands.items():
            child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, cwd=ROOT)
            children[variant] = child
            metadata[variant] = json.loads(child.stdout.readline())
            wanted = "0.2.0" if variant == "baseline" else "0.3.0"
            if metadata[variant]["wheel_version"] != wanted:
                raise ValueError(f"wrong wheel: {metadata[variant]}")
        save("config.json", {"baseline_commit": BASELINE, "workers": metadata, "pairs": 10,
             "order": "even baseline/candidate; odd candidate/baseline; fixed case order; stages list then stream",
             "small_case_calls": 50, "scope": "public structure calls; startup/IO/warmup/verification excluded"})
        if len({item["affinity_mask"] for item in metadata.values()}) != 1:
            raise ValueError("measurement workers do not share the same logical CPU")
        def request(variant, index, calls):
            child = children[variant]
            child.stdin.write(json.dumps({"instance": index, "calls": calls}) + "\n")
            child.stdin.flush()
            line = child.stdout.readline()
            if not line:
                raise RuntimeError(f"{variant} worker failed: {child.stderr.read()}")
            result = json.loads(line)
            validate_result(result, variant, calls, expected[index]["structure"])
            return result
        for candidate in variants[1:]:
            for index, item in enumerate(raw):
                calls = 50 if len(item["sets"]) < 200 and item["universe_size"] < 2048 else 1
                for variant in ("baseline", candidate):
                    request(variant, index, 1)
                for pair in range(10):
                    order = ("baseline", candidate) if pair % 2 == 0 else (candidate, "baseline")
                    for position, variant in enumerate(order):
                        result = request(variant, index, calls)
                        rows.append({"study": candidate, "instance": index, "pair": pair, "position": position,
                                     "variant": variant, "calls": calls, "seconds": result["seconds"]})
                print(f"Compared {candidate} {index + 1}/28", flush=True)
    finally:
        for child in children.values():
            if child.poll() is None:
                try:
                    child.stdin.write('{"stop": true}\n'); child.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.terminate(); child.wait(timeout=15)
    if any(child.returncode != 0 for child in children.values()):
        raise RuntimeError("an acceptance worker exited unsuccessfully")
    import csv
    with (args.output / "timings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = []
    for candidate in variants[1:]:
        for index in range(28):
            samples = {v: [r["seconds"] for r in rows if r["study"] == candidate and r["instance"] == index
                           and r["variant"] == v] for v in ("baseline", candidate)}
            ratios = [a/b for a,b in zip(samples["baseline"], samples[candidate])]
            old, new = (statistics.median(samples[v]) for v in ("baseline", candidate))
            summary.append({"study": candidate, "instance": index, "baseline_median_seconds": old,
                            "candidate_median_seconds": new, "paired_speedup": statistics.median(ratios),
                            "faster_pairs": sum(r > 1 for r in ratios),
                            "absolute_change_seconds": new - old,
                            "regression_flag": new > old * 1.10})
    save("summary.json", summary)
    memory = []
    for index in (13, 24, 25, 26, 27):
        for variant, command in commands.items():
            for tracker in ("python", "process"):
                result = json.loads(subprocess.check_output(command + ["--memory-case", str(index), "--tracker", tracker], text=True))
                validate_result(result, variant, 1, expected[index]["structure"])
                memory.append(result)
    save("memory.json", memory)
    print("Completed isolated-wheel parity, timings and separate memory measurements")


if __name__ == "__main__":
    sys.set_int_max_str_digits(0)
    main()
