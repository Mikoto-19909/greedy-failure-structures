"""Compare three kernel combinations on saved inputs and bounded larger cases."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import importlib.util
import importlib.metadata
import itertools
import json
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maxcover.algorithms import greedy, lazy_greedy
from maxcover.generators import uniform_random, high_overlap, duplicate_heavy, dominated_heavy
from maxcover.model import MaximumCoverageInstance, thaw_json_value
from maxcover.structure import analyze_instance

VARIANTS = ("python", "rust_structure", "rust_all")
FIELDS = ("structure_seconds", "greedy_seconds", "lazy_greedy_seconds")
REFERENCE_COMMIT = "29895c0bca44a9b0c6874e1abce5b73da96a1a91"


def solution_record(solution):
    return {"algorithm": solution.algorithm, "selected": list(solution.selected),
            "feasible_value": solution.feasible_value, "status": solution.status.value,
            "best_bound": solution.best_bound, "nodes_or_iterations": solution.nodes_or_iterations,
            "metadata": thaw_json_value(solution.metadata)}


def small_inputs():
    for n, m, k in ((64, 32, 8), (257, 100, 20)):
        for seed in (1709, 1710, 1711):
            common = dict(universe_size=n, set_count=m, k=k, seed=seed)
            yield uniform_random(**common, density=0.15)
            yield high_overlap(**common, core_fraction=0.3, core_probability=0.95,
                               peripheral_probability=0.05)
            yield duplicate_heavy(universe_size=n, base_set_count=m // 2, k=k,
                                  set_size=n // 8, copy_factor=2, seed=seed)
            yield dominated_heavy(anchor_count=k, anchor_size=8 if n == 64 else 13,
                                  k=k, child_count=m // k - 1, seed=seed)


def instance_record(item):
    return {"universe_size": item.universe_size, "sets": list(item.sets), "k": item.k,
            "family": item.family, "seed": item.seed, "parameters": thaw_json_value(item.parameters)}


def reference_from_git(name):
    source = subprocess.check_output(
        ["git", "show", f"{REFERENCE_COMMIT}:src/maxcover/{name}.py"], cwd=ROOT).decode("utf-8")
    module = ModuleType(f"maxcover._timing_old_{name}")
    sys.modules[module.__name__] = module
    exec(compile(source, f"{REFERENCE_COMMIT}/{name}.py", "exec"), module.__dict__)
    return module, source


def reference_module(path, name):
    spec = importlib.util.spec_from_file_location(f"maxcover.{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def larger_inputs():
    for ordinal, (n, m, k, family) in enumerate(((1024, 300, 40, "dense"),
                                              (4097, 1000, 100, "dense"),
                                              (65537, 160, 40, "sparse"),
                                              (4097, 1000, 100, "duplicates"))):
        rng = random.Random(1909 + ordinal)
        if family == "sparse":
            masks = tuple(sum(1 << bit for bit in rng.sample(range(n), 12)) for _ in range(m))
        elif family == "duplicates":
            base = tuple(rng.getrandbits(n) for _ in range(m // 10))
            masks = base * 10
        else:
            masks = tuple(rng.getrandbits(n) for _ in range(m))
        yield MaximumCoverageInstance(n, masks, k, family=f"timing_{family}", seed=1909 + ordinal)


def answers(metrics, g, lazy):
    return {"structure": asdict(metrics), "greedy": solution_record(g),
            "lazy_greedy": solution_record(lazy)}


def measure(instances, variant, repeat, position):
    structure_backend = "python" if variant == "python" else "rust"
    algorithm_backend = "rust" if variant == "rust_all" else "python"
    rows, outputs = [], []
    started = time.perf_counter_ns()
    for index, instance in enumerate(instances):
        t0 = time.perf_counter_ns()
        metrics = analyze_instance(instance, backend=structure_backend)
        t1 = time.perf_counter_ns()
        g = greedy(instance, backend=algorithm_backend)
        t2 = time.perf_counter_ns()
        lazy = lazy_greedy(instance, backend=algorithm_backend)
        t3 = time.perf_counter_ns()
        outputs.append((metrics, g, lazy))
        rows.append({"repeat": repeat, "position": position, "variant": variant,
                     "instance": index, "structure_seconds": (t1 - t0) / 1e9,
                     "greedy_seconds": (t2 - t1) / 1e9, "lazy_greedy_seconds": (t3 - t2) / 1e9})
    elapsed = (time.perf_counter_ns() - started) / 1e9
    return outputs, rows, elapsed


def verify(outputs, expected):
    if len(outputs) != len(expected):
        raise ValueError("answer count mismatch")
    for index, (output, saved) in enumerate(zip(outputs, expected)):
        if answers(*output) != saved:
            raise ValueError(f"non-timing output differs at instance {index}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="Replay 24 saved inputs and answers; otherwise use the fixed corpus and Git reference")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--large", action="store_true", help="Include four fixed larger synthetic cases")
    args = parser.parse_args()
    reference_sources = {}
    if args.baseline:
        raw = json.loads((args.baseline / "inputs.json").read_text(encoding="utf-8"))
        expected = json.loads((args.baseline / "expected.json").read_text(encoding="utf-8"))
        old_algorithms = reference_module(args.baseline / "source/algorithms.py", "_timing_old_algorithms")
        old_structure = reference_module(args.baseline / "source/structure.py", "_timing_old_structure")
    else:
        old_algorithms, reference_sources["algorithms.py"] = reference_from_git("algorithms")
        old_structure, reference_sources["structure.py"] = reference_from_git("structure")
        raw = [instance_record(item) for item in small_inputs()]
        expected = [answers(old_structure.analyze_instance(item), old_algorithms.greedy(item),
                            old_algorithms.lazy_greedy(item)) for item in small_inputs()]
    if len(raw) != 24 or len(expected) != 24:
        raise ValueError("expected 24 saved inputs and answers")
    instances = [MaximumCoverageInstance(**item) for item in raw]
    verify([(old_structure.analyze_instance(item), old_algorithms.greedy(item),
             old_algorithms.lazy_greedy(item)) for item in instances], expected)
    if args.large:
        for item in larger_inputs():
            instances.append(item)
            raw.append({"universe_size": item.universe_size, "sets": item.sets, "k": item.k,
                        "family": item.family, "seed": item.seed,
                        "parameters": thaw_json_value(item.parameters)})
            expected.append(answers(old_structure.analyze_instance(item), old_algorithms.greedy(item),
                                    old_algorithms.lazy_greedy(item)))
    # Large integer masks remain exact decimal JSON integers, just like the saved baseline.
    args.output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (args.output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    save("inputs.json", raw)
    save("expected.json", expected)
    orders = list(itertools.permutations(VARIANTS)) * 2
    save("config.json", {"baseline": str(args.baseline.resolve()) if args.baseline else None,
                         "reference_commit": REFERENCE_COMMIT if not args.baseline else None, "orders": orders,
                         "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                         "warmups_per_variant": 1, "python": sys.version,
                         "platform": platform.platform(), "large": args.large,
                         "extension_version": importlib.metadata.version("maxcover-structure-native"),
                         "excluded": "generation, imports, validation, serialization, IO, process startup",
                         "scope": "structure + greedy + lazy calls; not benchmark runner or R2",
                         "reference": "saved answers; additional cases use saved pre-migration source"})
    source = args.output / "source"
    source.mkdir()
    for name in ("algorithms.py", "structure.py", "model.py", "generators.py",
                 "_generators_random.py", "_generator_common.py"):
        shutil.copy2(ROOT / "src/maxcover" / name, source / name)
    shutil.copytree(ROOT / "native/structure/src", source / "native")
    for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml"):
        shutil.copy2(ROOT / "native/structure" / name, source / name)
    shutil.copy2(__file__, source / Path(__file__).name)
    if args.baseline:
        shutil.copytree(args.baseline / "source", args.output / "reference_source")
    else:
        reference_dir = args.output / "reference_source"
        reference_dir.mkdir()
        for name, source_text in reference_sources.items():
            (reference_dir / name).write_text(source_text, encoding="utf-8")
    for variant in VARIANTS:
        outputs, _, _ = measure(instances, variant, -1, -1)
        verify(outputs, expected)
    rows, batches = [], []
    for repeat, order in enumerate(orders):
        for position, variant in enumerate(order):
            outputs, current, elapsed = measure(instances, variant, repeat, position)
            verify(outputs, expected)
            rows.extend(current)
            batches.append({"repeat": repeat, "position": position, "variant": variant,
                            "total_seconds": elapsed})
    for name, records in (("timings.csv", rows), ("batches.csv", batches)):
        with (args.output / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    summaries = []
    for index, item in enumerate(instances):
        medians = {variant: {field: statistics.median(row[field] for row in rows
                    if row["variant"] == variant and row["instance"] == index)
                    for field in FIELDS} for variant in VARIANTS}
        summaries.append({"instance": index, "n": item.universe_size, "m": item.set_count,
                          "k": item.k, "family": item.family, "median_seconds": medians})
    batch_medians = {variant: statistics.median(row["total_seconds"] for row in batches
                                               if row["variant"] == variant) for variant in VARIANTS}
    paired = {variant: [next(row["total_seconds"] for row in batches
                            if row["repeat"] == r and row["variant"] == "python") /
                       next(row["total_seconds"] for row in batches
                            if row["repeat"] == r and row["variant"] == variant)
                       for r in range(len(orders))] for variant in VARIANTS[1:]}
    summary = {"all_outputs_equal": True, "instances": summaries,
               "batch_median_seconds": batch_medians, "paired_speedups": paired,
               "median_paired_speedup": {v: statistics.median(values) for v, values in paired.items()}}
    save("summary.json", summary)
    print(json.dumps({"instances": len(instances), "batch_median_seconds": batch_medians,
                      "median_paired_speedup": summary["median_paired_speedup"]}, indent=2))


if __name__ == "__main__":
    # Exact mask serialization for the bounded 65,537-element sparse fixture.
    sys.set_int_max_str_digits(0)
    main()
