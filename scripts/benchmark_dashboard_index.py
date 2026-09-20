"""Measure local dashboard reads on a fixed artificial corpus, never run solvers.

The fixture copies ten typed rows from commit 05571c5 into 100 sources of 1,000
rows. Its identities and seeds are artificial: it is NOT research evidence.
All generated files stay under ignored output/verification/index-scale/.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover._run_contracts import RunRecord
from maxcover.dashboard_exports import ComparisonExports
from maxcover.dashboard_workbench import WorkbenchService

BASELINE = "05571c5"
TEMPLATE = "tests/fixtures/benchmark_compatibility/raw_results.csv"
SOURCES = 100
ROWS_PER_SOURCE = 1000
HOT_REPEATS = 3


def git_text(spec: str) -> str:
    return subprocess.check_output(["git", "show", spec], cwd=ROOT).decode("utf-8-sig")


def baseline_service() -> type:
    module = types.ModuleType("maxcover._dashboard_workbench_scale_baseline")
    module.__package__ = "maxcover"
    exec(compile(git_text(f"{BASELINE}:src/maxcover/dashboard_workbench.py"),
                 f"{BASELINE}:dashboard_workbench.py", "exec"), module.__dict__)
    return module.WorkbenchService


def make_fixture(root: Path) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(git_text(f"{BASELINE}:{TEMPLATE}")))
    templates = list(reader)[:10]
    assert len(templates) == 10 and reader.fieldnames
    for source_number in range(SOURCES):
        target = root / f"results/artificial-{source_number:03d}/raw_results.csv"
        target.parent.mkdir(parents=True, exist_ok=False)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=reader.fieldnames)
            writer.writeheader()
            for number in range(ROWS_PER_SOURCE):
                row = dict(templates[number % 10])
                cycle = number // 10
                row.update(config_hash=f"artificial-config-{source_number:03d}",
                           run_id=f"artificial-run-{source_number:03d}-{number:04d}",
                           instance_id=f"artificial-instance-{source_number:03d}-{cycle:03d}",
                           repetition=str(cycle), seed=str(2**63 + source_number * 1000 + cycle))
                if number % 20 == 19:
                    row.update(optimum="", optimality_gap="")
                RunRecord.from_csv_row(row)
                writer.writerow(row)
    return {
        "kind": "artificial_read_fixture_not_research_evidence",
        "template": f"{BASELINE}:{TEMPLATE}", "template_rows": "first ten, repeated in original order",
        "sources": SOURCES, "rows_per_source": ROWS_PER_SOURCE,
        "rows": SOURCES * ROWS_PER_SOURCE,
        "identities": "source-specific config; unique run; shared instance/repetition per ten-row cycle",
        "seeds": "2**63 + source_number*1000 + cycle; artificial, not generation seeds",
        "missing_reference": "zero-based row number % 20 == 19: clear optimum and optimality_gap",
        "expected_per_source": {"loss": 100, "zero": 850, "missing": 50},
        "typed_validation": "all generated rows accepted by RunRecord.from_csv_row",
        "csv_bytes": sum(path.stat().st_size for path in root.rglob("raw_results.csv")),
    }


def measure(action: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    started = time.perf_counter()
    first = action()
    cold = time.perf_counter() - started
    hot = []
    for _ in range(HOT_REPEATS):
        started = time.perf_counter()
        result = action()
        hot.append(time.perf_counter() - started)
        assert result == first, "repeated reads changed their result"
    return first, {"first_seconds": cold, "hot_seconds": hot,
                   "hot_median_seconds": statistics.median(hot)}


def equal(expected: Any, actual: Any, label: str) -> None:
    if expected != actual:
        raise AssertionError(f"baseline/current mismatch: {label}")


def verify_exports(service: Any, sources: list[str], expected: dict[str, Any]) -> bytes:
    exports = ComparisonExports(service.root)
    exports.workbench = service
    view = exports.save({"title": "Artificial index read check", "sources": sources})
    payload, _, _ = exports.artifact(view["id"], "json")
    equal(expected, json.loads(payload)["comparison"], "complete JSON export")
    content, _, _ = exports.artifact(view["id"], "csv")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    equal(len(expected["rows"]), len(rows), "CSV exported row count")
    equal([row["key"] for row in expected["rows"]], [row["run_id"] for row in rows],
          "CSV exported identities and order")
    equal([row["seed"] for row in expected["rows"]], [row["seed"] for row in rows],
          "CSV exact large-integer seeds")
    return content


def compare_fixture(root: Path, old_class: type) -> dict[str, Any]:
    previous, current = old_class(root), WorkbenchService(root)
    report: dict[str, Any] = {"timings": {}, "parity": []}
    for name, service in (("baseline", previous), ("current", current)):
        print(f"{name}: library over 100 sources / 100000 artificial rows", flush=True)
        library, report["timings"][name + "_library"] = measure(service.library)
        assert len(library["sources"]) == SOURCES
        assert sum(item["records"] for item in library["sources"]) == SOURCES * ROWS_PER_SOURCE
        if name == "baseline":
            old_library = library
        else:
            equal(old_library, library, "complete library")
    report["parity"].append("complete library: all fields, 100 sources and 100000 records")
    selected = [f"results/artificial-{number:03d}" for number in (0, 1, 98, 99)]
    print("four-source comparison and all-row export", flush=True)
    full_before, report["timings"]["baseline_compare_all"] = measure(
        lambda: previous.compare(selected, include_all=True))
    full_after, report["timings"]["current_compare_all"] = measure(
        lambda: current.compare(selected, include_all=True))
    equal(full_before, full_after, "complete comparison including summaries and row order")
    equal(4000, full_after["total"], "complete comparison count")
    summaries = full_after["summaries"]
    equal(400, sum(item["losses"] for item in summaries), "known loss count")
    equal(200, sum(item["missing_gap"] for item in summaries), "known missing count")
    report["parity"].append("complete comparison: all 4000 rows, summaries and ordering identical")
    queries: list[dict[str, Any]] = [{"page": page, "page_size": 100} for page in (0, 20, 39, 999)]
    queries.extend({"outcome": outcome} for outcome in ("loss", "zero", "missing"))
    queries.extend({"algorithm": name} for name in ("greedy", "randomized_greedy", "absent"))
    queries.extend([{"case": full_after["cases"][0]}, {"case": "absent"},
                    {"population": "fixture"}, {"population": "all"}])
    for query in queries:
        before = previous.compare(selected, **query)
        after = current.compare(selected, **query)
        equal(before, after, f"query {query}")
        if query.get("page") == 20:
            equal(full_before["rows"][2000:2100], after["rows"], "records after row 2000")
    report["queries"] = queries
    report["parity"].append(f"all fields matched for {len(queries)} frozen filter/page queries")
    _, report["timings"]["baseline_page_20"] = measure(
        lambda: previous.compare(selected, page=20, page_size=100))
    _, report["timings"]["current_page_20"] = measure(
        lambda: current.compare(selected, page=20, page_size=100))
    equal(verify_exports(previous, selected, full_before),
          verify_exports(current, selected, full_after), "complete CSV export bytes")
    report["parity"].append("CSV bytes and JSON comparison identical; all 4000 records and seeds exported")
    restarted = WorkbenchService(root)
    restarted_library, report["timings"]["current_new_service_library"] = measure(restarted.library)
    equal(old_library, restarted_library, "new service persisted-cache library")
    report["parity"].append("new service instance retained identical library")
    return report


def compare_r1(root: Path, old_class: type) -> dict[str, Any]:
    source = "experiments/r1c_confirmation_v1"
    original = ROOT / source / "paths.jsonl"
    if not original.is_file():
        return {"available": False, "source": str(original)}
    target = root / source / "paths.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(original, target)
    report: dict[str, Any] = {"available": True, "bytes": target.stat().st_size,
                              "source": str(original), "timings": {}}
    previous, current = old_class(root), WorkbenchService(root)
    for name, service in (("baseline", previous), ("current", current)):
        print(f"{name}: reading saved R1c copy", flush=True)
        result, report["timings"][name + "_compare_all"] = measure(
            lambda: service.compare([source], include_all=True))
        if name == "baseline":
            expected = result
        else:
            equal(expected, result, "all saved R1c rows, summaries and order")
    report["records"] = expected["input_records"]
    for number in (0, len(expected["rows"]) - 1):
        key = expected["rows"][number]["key"]
        equal(previous.detail(source, key), current.detail(source, key), "R1c detail")
        equal(previous.export(source, key), current.export(source, key), "R1c instance export")
    report["parity"] = "complete comparison plus first/last sorted instance details and replay payloads identical"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-r1", action="store_true", help="also read a copy of saved R1c; run no solvers")
    parser.add_argument("--prepare-only", action="store_true", help="construct the fixture and time only the frozen baseline")
    parser.add_argument("--reuse-run", type=Path, help="read an existing prepared fixture without rewriting its inputs")
    args = parser.parse_args()
    output = ROOT / "output/verification/index-scale"
    output.mkdir(parents=True, exist_ok=True)
    if args.reuse_run:
        run = args.reuse_run.resolve()
        if not run.is_relative_to(output.resolve()) or not run.is_dir() or args.prepare_only:
            parser.error("--reuse-run requires an existing run under output/verification/index-scale, without --prepare-only")
    else:
        run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    report_path = run / ("prepared.json" if args.prepare_only else "report.json")
    if report_path.exists():
        report_path = run / ("report-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".json")
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", BASELINE], cwd=ROOT, text=True).strip(),
        "current_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "current_worktree_status": subprocess.check_output(
            ["git", "status", "--short"], cwd=ROOT, text=True).splitlines(),
        "python": sys.version, "platform": platform.platform(), "hot_repeats": HOT_REPEATS,
        "timing_scope": "first library read includes index construction if no cache exists; three repeats reuse service/cache. "
                        "Compare runs follow library warmup. OS filesystem caches are NOT cleared.",
        "cache_files_before": [str(path.relative_to(run)) for path in run.rglob("*") if path.is_file()
                               and path.suffix in {".db", ".sqlite", ".sqlite3"}],
        "limits": ["Artificial repeated records measure I/O/application behavior, not new research evidence.",
                   "No timing target or statistical performance guarantee; local wall time only.",
                   "Comparisons keep the existing maximum of four selected sources.",
                   "The frozen baseline Workbench module uses the current unchanged record/parser dependencies.",
                   "New-service timing tests cache reuse in-process, not a separate-process restart."],
    }
    print(f"Output: {run}", flush=True)
    try:
        report["fixture"] = (json.loads((run / "prepared.json").read_text(encoding="utf-8"))["fixture"]
                             if args.reuse_run else make_fixture(run / "artificial"))
        old_class = baseline_service()
        if args.prepare_only:
            previous = old_class(run / "artificial")
            print("prepared: frozen baseline library / comparison", flush=True)
            _, library_timing = measure(previous.library)
            _, comparison_timing = measure(lambda: previous.compare(
                [f"results/artificial-{number:03d}" for number in (0, 1, 98, 99)], include_all=True))
            report.update(status="prepared", timings={"library": library_timing, "comparison": comparison_timing})
            return 0
        report["artificial"] = compare_fixture(run / "artificial", old_class)
        if args.include_r1:
            report["r1_saved_copy"] = compare_r1(run / "r1", old_class)
        report["database_files"] = [{"path": str(path.relative_to(run)), "bytes": path.stat().st_size}
                                    for path in run.rglob("*") if path.is_file()
                                    and (path.suffix in {".db", ".sqlite", ".sqlite3"}
                                         or path.name.endswith(("-wal", "-shm")))]
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report: {report_path}", flush=True)
    print(json.dumps({"status": report["status"], "timings": report["artificial"]["timings"],
                      "database_files": report["database_files"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
