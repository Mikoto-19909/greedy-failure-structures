"""Measure L5 DUAL on 18 seeded inputs independent of the formal corpus."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "analysis")]
from r2_design import make_design, read_json, write_json
from r2_budget_grid import run as prepare_sources
from r4_dual import run, analyze
from r4_dual_io import configuration, SourceAccess, load_records, output_size, RuntimeBudget
from validate_r4_dual import validate_batch, verify_summaries, verify_record, same
from validate_r2_budget_grid import memory_usage


def directory_scale_probe(output):
    """Measure metadata scan cost at the full graph count without corpus data."""
    started = time.perf_counter()
    directory = Path(output) / "directory_scale_probe"
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(1800):
        path = directory / f"{index:04d}.json"
        if not path.exists():
            path.write_text("{}\n", encoding="utf-8")
    if len(list(directory.glob("*.json"))) != 1800:
        raise ValueError("independent directory probe population differs")
    samples = []
    for _ in range(20):
        before = time.perf_counter()
        output_size(directory)
        samples.append(time.perf_counter() - before)
    # Final runtime performs only initial/final scans in four operations;
    # growing checkpoint bytes are accounted incrementally during production.
    return {"files": 1800, "scan_seconds": samples, "max_scan_seconds": max(samples),
            "full_pipeline_scan_count_bound": 8,
            "conservative_allowance_seconds": 2 * 8 * max(samples),
            "wall_seconds": time.perf_counter() - started,
            "note": "Synthetic tiny JSON files only. No formal graph or DUAL data. Allowance is a conservative design margin, not another observed pipeline cost."}


def preflight(output, *, source_repository=None, resume=False):
    output = Path(output)
    if output.exists() and not resume:
        raise ValueError("preflight output exists; use --resume to preserve its fixed inputs")
    design = make_design("preflight", repetitions=2, diagnostic_count=0)
    config = configuration("preflight", design)
    formal = read_json(ROOT / "analysis/r2_f2_config.json")
    if {task["seed"] for task in design["tasks"]} & {task["seed"] for task in formal["tasks"]}:
        raise ValueError("preflight and formal seed domains overlap")
    source, certificates_output = output / "source", output / "dual"
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "incomplete", "started_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "interpreter": sys.executable, "platform": platform.platform(),
              "input_graphs": 18, "budget_records": sum(len(task["budgets"]) for task in design["tasks"]),
              "independent_of_formal_seeds": True, "config": config}
    report_path = output / "resource_preflight.json"
    started = time.perf_counter()
    measurement_path = output / "pipeline_measurement.json"
    owns_output = False
    try:
        with RuntimeBudget(output, config, "dual_resource_preflight") as resource_budget:
            owns_output = True
            write_json(report_path, report)
            if resume and measurement_path.exists():
                measurement = read_json(measurement_path)
                same(measurement["config"], config, "saved preflight measurement configuration")
                produced, verified, analyzed, derived = [read_json(certificates_output / filename) for filename in
                    ("run_status.json", "verification.json", "analysis_status.json", "summary_verification.json")]
                # Complete a failed report/transport step without reproducing the
                # already saved inputs, certificates or exhaustive references.
                # A stale passed flag cannot authorize modified saved data.
                recovery_started = time.perf_counter()
                recovery_graphs, recovery_budgets = 0, 0
                with SourceAccess(source, config) as inputs:
                    for record in load_records(certificates_output, config):
                        verify_record(record, inputs.record(record["task"]), config)
                        recovery_graphs += 1
                        recovery_budgets += len(record["values"])
                if recovery_graphs != 18 or recovery_budgets != report["budget_records"]:
                    raise ValueError("preflight recovery has incomplete graph or budget population")
                derived = verify_summaries(certificates_output)
                report["recovery_check_seconds"] = time.perf_counter() - recovery_started
                source_wall, pipeline_wall = measurement["source_preparation_wall_seconds"], measurement["pipeline_wall_seconds"]
                stages = measurement["stages"]
            else:
                before = time.perf_counter()
                prepare_sources(design, source, workers=1, resume=resume and source.exists())
                source_wall = time.perf_counter() - before
                resource_budget.check()
                pipeline_started = time.perf_counter()
                before = time.perf_counter()
                produced = run(config, source, certificates_output,
                               resume=resume and (certificates_output / "config.json").exists())
                production_wall = time.perf_counter() - before
                before = time.perf_counter()
                verified = validate_batch(certificates_output, source)
                verification_wall = time.perf_counter() - before
                before = time.perf_counter()
                analyzed = analyze(certificates_output, source)
                analysis_wall = time.perf_counter() - before
                before = time.perf_counter()
                derived = verify_summaries(certificates_output)
                derived_wall = time.perf_counter() - before
                pipeline_wall = time.perf_counter() - pipeline_started
                stages = {"production_wall_seconds": production_wall, "verification_wall_seconds": verification_wall,
                          "analysis_wall_seconds": analysis_wall, "derived_verification_wall_seconds": derived_wall}
                measurement = {"config": config, "source_preparation_wall_seconds": source_wall,
                               "pipeline_wall_seconds": pipeline_wall, "stages": stages,
                               "peak_python_process_memory_bytes": memory_usage(),
                               "pipeline_wall_measurement": "direct perf_counter wall measurement",
                               "initial_invocation_was_resume": resume}
                write_json(measurement_path, measurement)
            if (not produced["complete"] or verified["status"] != "passed" or derived["status"] != "passed"
                    or verified["graph_count"] != 18 or analyzed["budget_rows"] != report["budget_records"]):
                raise ValueError("preflight population or independent verification is incomplete")
            resource_budget.check()

            records = list(load_records(certificates_output, config))
            components = dict(produced["timing"])
            for name in ("certificate_seconds", "reference_seconds", "source_read_seconds", "checkpoint_read_seconds"):
                components["independent_" + name] = sum(row[name] for row in verified["graphs"].values())
            components["independent_source_setup_seconds"] = verified["source_setup_seconds"]
            components.update({"analysis_" + key: value for key, value in analyzed["timing"].items()})
            cells = []
            for n in design["n_values"]:
                for d in design["d_values"]:
                    cell = [row for row in records if (row["task"]["n"], row["task"]["d"]) == (n, d)]
                    costs = []
                    for row in cell:
                        checked = verified["graphs"][row["task"]["base_graph_id"]]
                        # Analyze performs a fresh certificate/source check before rebuilding.
                        costs.append(sum(row["timing"][name] for name in
                                         ("greedy_seconds", "production_seconds", "source_read_seconds"))
                                     + 2 * sum(checked[name] for name in
                                               ("certificate_seconds", "reference_seconds", "source_read_seconds", "checkpoint_read_seconds")))
                    cells.append({"n": n, "d": d, "graphs": len(cell), "max_graph_component_seconds": max(costs)})

            transport_setup = []
            if source_repository is not None:
                formal_config = configuration("comparison", formal)
                for _ in range(3):
                    before = time.perf_counter()
                    # Only immutable configuration objects: no formal graph or DUAL calculation.
                    with SourceAccess(source_repository, formal_config):
                        pass
                    transport_setup.append(time.perf_counter() - before)
            git_revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
            directory_probe = directory_scale_probe(output)
            dual_bytes = output_size(certificates_output)
            peak = max(memory_usage(), measurement["peak_python_process_memory_bytes"])
            gross_projection = 100 * pipeline_wall
            worst_cell_projection = 200 * sum(cell["max_graph_component_seconds"] for cell in cells)
            decision = {
                "conservative_wall_seconds": 2 * max(gross_projection, worst_cell_projection) + 600
                    + directory_probe["conservative_allowance_seconds"],
                "conservative_peak_memory_bytes": max(2 * peak, 512 * 1024**2),
                "conservative_output_bytes": 2 * 100 * dual_bytes,
                "safety_factor": 2, "fixed_allowance_seconds": 600,
                "pipeline_projection_seconds": gross_projection,
                "worst_cell_component_projection_seconds": worst_cell_projection,
                "reference_enumeration_in_projection": True,
                "memory_floor_bytes": 512 * 1024**2,
                "directory_scan_allowance_seconds": directory_probe["conservative_allowance_seconds"],
            }
            report.update(
                status="passed", code_revision=git_revision,
                code_state="current worktree; final committed revision is fixed in the formal design",
                source_preparation_wall_seconds=source_wall,
                source_preparation_note="Fresh independent input generation and exhaustive reference production; excluded from formal pipeline projection.",
                pipeline_wall_seconds=pipeline_wall,
                stages=stages, pipeline_wall_measurement=measurement["pipeline_wall_measurement"],
                components=components, cells=cells, immutable_config_transport_setup_seconds=transport_setup,
                directory_scale_probe=directory_probe,
                peak_python_process_memory_bytes=peak, dual_output_bytes=dual_bytes,
                source_output_bytes=output_size(source), total_output_bytes_before_report=output_size(output),
                resource_decision=decision,
                timing_note="Stage walls are components of pipeline wall; any recovered conservative bound is labeled separately. Components are never added again. Analysis source/certificate checks are real additional work. Preflight exact-reference enumeration is retained in the conservative projection although formal references are reused.",
                transport_note="Preflight graph access uses local files. Optional fixed Git configuration reads test transport setup only. The fixed 600 s allowance also covers source transport and report overhead; formal graph access must be measured in the actual run.",
                memory_note="Peak is the Python process lifetime including source preparation. The short Git configuration-read subprocess is excluded; the estimate reserves at least 512 MiB for formal summaries and source transport.",
            )
            resource_budget.check()
    except BaseException:
        report["status"] = "incomplete"
        raise
    finally:
        report["full_wall_seconds"] = time.perf_counter() - started
        history = output / "execution.jsonl"
        if history.exists():
            import json
            operations = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
            report["all_attempts_measured_wall_seconds"] = sum(entry["wall_seconds"] for entry in operations)
            report["operation_attempts"] = operations
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        if owns_output:
            write_json(report_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-repository", type=Path, default=ROOT / "results/frozen-r4-calibration-v1",
                        help="immutable-source Git configuration transport check")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = preflight(args.output, source_repository=args.source_repository, resume=args.resume)
        print({key: report[key] for key in ("status", "input_graphs", "budget_records", "full_wall_seconds",
                                           "pipeline_wall_seconds", "peak_python_process_memory_bytes", "dual_output_bytes", "resource_decision")})
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
