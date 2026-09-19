"""Read-only research views over existing benchmark CSV and R1 trajectories.

No experiments or inferential comparisons run here. Summaries cover the complete
selected inputs; only the returned detail rows are paginated.
"""

from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from http import HTTPStatus
from pathlib import Path
from statistics import fmean
from typing import Any

from ._run_contracts import RunRecord
from .reproducibility import instance_from_payload, instance_payload


class WorkbenchError(ValueError):
    status = HTTPStatus.BAD_REQUEST


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(key) for key in ("config_hash", "case_id", "instance_id", "repetition"))


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise WorkbenchError(f"{name} must be an integer >= {minimum}")
    return value


def _r1_row(raw: dict[str, Any], source: str) -> dict[str, Any]:
    required = ("instance_id", "case_id", "population", "repetition", "sets", "k",
                "universe_size", "greedy_selected", "optimum", "prefixes", "ties")
    if any(key not in raw for key in required):
        raise WorkbenchError("paths.jsonl is missing required R1 fields")
    if not all(isinstance(raw[key], str) and raw[key] for key in ("instance_id", "case_id", "population")):
        raise WorkbenchError("R1 identity fields must be non-empty strings")
    if not isinstance(raw["prefixes"], list) or not raw["prefixes"]:
        raise WorkbenchError("R1 prefixes must be a non-empty list")
    if not isinstance(raw["sets"], list) or not raw["sets"]:
        raise WorkbenchError("R1 sets must be a non-empty list")
    coverage = _integer(raw["prefixes"][-1].get("coverage"), "coverage")
    optimum = _integer(raw["optimum"], "optimum")
    n = _integer(raw["universe_size"], "universe_size", 1)
    k = _integer(raw["k"], "k", 1)
    repetition = None if raw["population"] == "fixture" and raw["repetition"] is None else _integer(raw["repetition"], "repetition")
    if not coverage <= optimum <= n or k > len(raw["sets"]):
        raise WorkbenchError("R1 coverage, optimum or dimensions are inconsistent")
    row = {key: raw.get(key) for key in ("config_hash", "case_id", "instance_id", "seed")}
    row.update(source=source, case=raw["case_id"], repetition=repetition,
               population=raw["population"], family=raw["case_id"], universe_size=n,
               set_count=len(raw["sets"]), k=k, parameters={}, algorithm="greedy",
               algorithm_id="greedy", algorithm_options={}, coverage=coverage,
               optimum=optimum, optimality_gap=(optimum - coverage) / optimum if optimum else None,
               runtime_seconds=None, status="saved", selected=raw["greedy_selected"],
               mechanism=raw.get("mechanism"), first_failure_step=raw.get("first_failure_step"))
    row["key"] = json.dumps([raw["population"], *_identity(row)], separators=(",", ":"))
    row["seed"] = str(raw["seed"]) if raw.get("seed") is not None else None
    return row


def _benchmark_rows(path: Path, source: str) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            run = RunRecord.from_csv_row(record)
            if not run.run_id or not run.instance_id or not run.config_hash:
                raise WorkbenchError("benchmark rows require run, instance and configuration identities")
            row = {key: getattr(run, key) for key in (
                "config_hash", "case_id", "instance_id", "run_id", "case", "repetition",
                "family", "universe_size", "set_count", "k", "algorithm", "algorithm_id",
                "coverage", "optimum", "optimality_gap", "runtime_seconds", "error_message")}
            row.update(key=run.run_id, source=source, population="experiment",
                       parameters=json.loads(run.parameters), algorithm_options=json.loads(run.algorithm_options),
                       status=run.status.value, selected=list(run.selected),
                       seed=str(run.seed) if run.seed is not None else None,
                       algorithm_seed=str(run.algorithm_seed) if run.algorithm_seed is not None else None)
            rows.append(row)
    return rows


class WorkbenchService:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()

    def _file(self, source: str, filename: str) -> Path:
        relative = Path(source)
        if (relative.is_absolute() or not relative.parts or relative.parts[0] not in {"results", "experiments"}
                or ".." in relative.parts or source != relative.as_posix()):
            raise WorkbenchError("source must be under results/ or experiments/")
        path = self.root / relative / filename
        try:
            path.resolve().relative_to((self.root / relative.parts[0]).resolve())
        except ValueError as error:
            raise WorkbenchError("source escapes its data directory") from error
        # Refuse links at every level, including Windows junctions resolving outside root.
        for item in (path, *path.parents):
            if item == self.root:
                break
            if _linked(item):
                raise WorkbenchError("linked data paths are not supported")
        return path

    def _sources(self) -> list[str]:
        sources = []
        for name in ("results", "experiments"):
            base = self.root / name
            if not base.is_dir() or _linked(base):
                continue
            for directory, children, files in os.walk(base, followlinks=False):
                here = Path(directory)
                children[:] = sorted(child for child in children if not child.startswith(".")
                                     and not _linked(here / child))
                if "raw_results.csv" in files or "paths.jsonl" in files:
                    sources.append(here.relative_to(self.root).as_posix())
                    # A dataset owns its descendants (e.g. failure artifacts).
                    children[:] = []
        return sorted(sources)

    def _read(self, source: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            paths = self._file(source, "paths.jsonl")
            raw = []
            if paths.is_file():
                with paths.open(encoding="utf-8-sig") as handle:
                    for line in handle:
                        if line.strip():
                            value = json.loads(line)
                            if not isinstance(value, dict):
                                raise WorkbenchError("R1 records must be JSON objects")
                            raw.append(value)
                kind, rows = "r1", [_r1_row(value, source) for value in raw]
            else:
                kind, rows = "benchmark", _benchmark_rows(self._file(source, "raw_results.csv"), source)
            keys = [row["key"] for row in rows]
            if len(set(keys)) != len(keys):
                raise WorkbenchError("duplicate record identities in source")
            return kind, rows, raw
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise WorkbenchError(f"{source}: {error}") from error

    def library(self) -> dict[str, Any]:
        items = []
        for source in self._sources():
            try:
                kind, rows, _ = self._read(source)
                items.append({"source": source, "kind": kind, "records": len(rows),
                              "instances": len({_identity(row) for row in rows}),
                              "cases": sorted({row["case_id"] for row in rows}),
                              "algorithms": sorted({row["algorithm_id"] for row in rows}),
                              "populations": sorted({row["population"] for row in rows}),
                              "error": None})
            except WorkbenchError as error:
                items.append({"source": source, "error": str(error)})
        return {"sources": items}

    def compare(self, sources: list[str], *, case: str = "", algorithm: str = "",
                population: str = "research", outcome: str = "all", page: int = 0,
                page_size: int = 50) -> dict[str, Any]:
        if not 1 <= len(sources) <= 4 or len(set(sources)) != len(sources):
            raise WorkbenchError("select one to four distinct sources")
        if population not in {"research", "fixture", "all"} or outcome not in {"all", "loss", "zero", "missing"}:
            raise WorkbenchError("unknown comparison filter")
        _integer(page, "page")
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise WorkbenchError("page_size must be between 1 and 100")
        all_rows = [row for source in sources for row in self._read(source)[1]]
        rows = [row for row in all_rows
                if (not case or row["case_id"] == case)
                and (not algorithm or row["algorithm_id"] == algorithm)
                and (population == "all" or (row["population"] == "fixture" if population == "fixture"
                     else row["population"] in {"pilot", "confirmation", "experiment"}))]
        # Compute summaries before the outcome filter: selecting failures must not
        # silently change a population failure-rate denominator.
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            group = tuple(row[key] for key in ("source", "case_id", "algorithm_id", "population",
                                               "universe_size", "set_count", "k")) + (
                json.dumps(row["parameters"], sort_keys=True),
                json.dumps(row["algorithm_options"], sort_keys=True))
            groups[group].append(row)
        summaries = []
        for group_rows in groups.values():
            first = group_rows[0]
            gaps = [row["optimality_gap"] for row in group_rows if row["optimality_gap"] is not None]
            coverages = [row["coverage"] for row in group_rows if row["coverage"] is not None]
            runtimes = [row["runtime_seconds"] for row in group_rows if row["runtime_seconds"] is not None]
            summaries.append({key: first[key] for key in (
                "source", "case_id", "algorithm_id", "population", "universe_size", "set_count", "k",
                "parameters", "algorithm_options")} | {
                "records": len(group_rows), "gap_records": len(gaps),
                "missing_gap": len(group_rows) - len(gaps), "losses": sum(gap > 0 for gap in gaps),
                "loss_rate": sum(gap > 0 for gap in gaps) / len(gaps) if gaps else None,
                "mean_gap": fmean(gaps) if gaps else None, "max_gap": max(gaps) if gaps else None,
                "mean_coverage": fmean(coverages) if coverages else None,
                "mean_runtime": fmean(runtimes) if runtimes else None,
                "errors": sum(row["status"] == "error" for row in group_rows),
                "timeouts": sum(row["status"] == "timeout" for row in group_rows)})
        selected = [row for row in rows if outcome == "all"
                    or (outcome == "missing" and row["optimality_gap"] is None)
                    or (outcome == "loss" and row["optimality_gap"] is not None and row["optimality_gap"] > 0)
                    or (outcome == "zero" and row["optimality_gap"] == 0)]
        selected.sort(key=lambda row: (-(row["optimality_gap"] if row["optimality_gap"] is not None else -1),
                                       row["source"], row["key"]))
        pages = max(1, math.ceil(len(selected) / page_size))
        page = min(page, pages - 1)
        return {"sources": sources, "input_records": len(all_rows), "filtered_records": len(rows),
                "total": len(selected), "page": page, "pages": pages, "page_size": page_size,
                "cases": sorted({row["case_id"] for row in all_rows}),
                "algorithms": sorted({row["algorithm_id"] for row in all_rows}),
                "summaries": summaries, "rows": selected[page * page_size:(page + 1) * page_size]}

    def detail(self, source: str, key: str) -> dict[str, Any]:
        kind, rows, raw = self._read(source)
        index = next((i for i, row in enumerate(rows) if row["key"] == key), None)
        if index is None:
            raise WorkbenchError("record is no longer present in this source")
        row = rows[index]
        trace, trace_source, warnings = None, None, []
        if kind == "r1":
            trace, trace_source = self._trace(raw[index]), source
        else:
            # Join all identity components, never seed alone. Non-Greedy records
            # keep their own selection; the linked trace is explicitly Greedy's.
            matches = []
            for candidate in self._sources():
                if not self._file(candidate, "paths.jsonl").is_file():
                    continue
                try:
                    _, candidates, originals = self._read(candidate)
                    for item, original in zip(candidates, originals):
                        if item.get("config_hash") and _identity(item) == _identity(row):
                            matches.append((candidate, original))
                except WorkbenchError as error:
                    warnings.append(str(error))
            if matches:
                candidate, original = matches[0]
                if any(other != original for _, other in matches[1:]):
                    warnings.append("Conflicting R1 records; no trajectory was linked.")
                elif (row["universe_size"], row["set_count"], row["k"]) != (
                        original["universe_size"], len(original["sets"]), original["k"]):
                    warnings.append("R1 dimensions disagree; no trajectory was linked.")
                else:
                    trace, trace_source = self._trace(original), candidate
                    if row["algorithm"] == "greedy" and (row["coverage"] != trace["coverage"]
                            or sorted(row["selected"]) != sorted(trace["greedy_selected"])):
                        raise WorkbenchError("linked Greedy selection disagrees with benchmark record")
                    if row["optimum"] is not None and row["optimum"] != trace["optimum"]:
                        raise WorkbenchError("linked R1 optimum disagrees with benchmark record")
        return {"record": row, "trace": trace, "trace_source": trace_source, "warnings": warnings}

    @staticmethod
    def _trace(raw: dict[str, Any]) -> dict[str, Any]:
        """Check display consistency without claiming a fresh exact-solver validation."""
        try:
            instance = instance_from_payload({"schema_version": 1, "universe_size": raw["universe_size"],
                "sets": raw["sets"], "k": raw["k"], "encoding": "elements"})
            sets = [set(elements) for elements in raw["sets"]]

            def covered(selected: list[int]) -> set[int]:
                if len(set(selected)) != len(selected) or len(selected) > instance.k:
                    raise WorkbenchError("invalid selected-set list in R1 trajectory")
                for index in selected:
                    _integer(index, "selected index")
                    if index >= len(sets):
                        raise WorkbenchError("selected index outside instance")
                return set().union(*(sets[index] for index in selected))

            chosen = raw["greedy_selected"]
            prefixes = raw["prefixes"]
            if not isinstance(chosen, list) or len(chosen) != instance.k or len(prefixes) != len(chosen) + 1:
                raise WorkbenchError("R1 prefix count disagrees with Greedy choices")
            optimum = _integer(raw["optimum"], "optimum")
            if len(covered(raw["optimum_selected"])) != optimum:
                raise WorkbenchError("R1 optimum witness coverage disagrees")
            steps = []
            for step, prefix in enumerate(prefixes):
                selected = chosen[:step]
                elements = covered(selected)
                if prefix["step"] != step or prefix["prefix"] != selected or prefix["coverage"] != len(elements):
                    raise WorkbenchError("R1 prefix selection or coverage disagrees")
                completion = prefix["completion_selected"]
                bound = _integer(prefix["optimal_completion"], "optimal_completion")
                if not set(selected).issubset(completion) or len(covered(completion)) != bound or not len(elements) <= bound <= optimum:
                    raise WorkbenchError("R1 completion witness disagrees")
                gains = [len(elements_in_set - elements) if index not in selected else None
                         for index, elements_in_set in enumerate(sets)]
                candidates = [index for index, gain in enumerate(gains) if gain is not None and gain == max(g for g in gains if g is not None)] if step < len(chosen) else []
                if step < len(chosen) and (not candidates or chosen[step] != min(candidates)):
                    raise WorkbenchError("R1 choices violate deterministic Greedy")
                ties = [tie for tie in raw["ties"] if tie["step"] == step + 1] if step < len(chosen) else []
                if step < len(chosen) and sorted(tie["candidate"] for tie in ties) != candidates:
                    raise WorkbenchError("R1 tie candidates disagree")
                for tie in ties:
                    witness = tie["completion_selected"]
                    if (tie["marginal_gain"] != gains[tie["candidate"]]
                            or tie["chosen"] != (tie["candidate"] == chosen[step])
                            or not set([*selected, tie["candidate"]]).issubset(witness)
                            or len(covered(witness)) != tie["optimal_completion"]
                            or tie["preserves_optimum"] != (tie["optimal_completion"] == optimum)):
                        raise WorkbenchError("R1 tie witness disagrees")
                steps.append({**prefix, "covered_elements": sorted(elements), "gains": gains,
                              "candidates": candidates, "ties": ties,
                              "next_choice": chosen[step] if step < len(chosen) else None})
            first_failure = next((step["step"] for step in steps if step["optimal_completion"] < optimum), None)
            if first_failure != raw.get("first_failure_step"):
                raise WorkbenchError("R1 first failure step disagrees")
            swaps = {}
            for name in ("one_swap", "two_swap"):
                swap = raw.get(name)
                if swap is not None:
                    if len(covered(swap["selected"])) != swap["coverage"]:
                        raise WorkbenchError("R1 exchange witness disagrees")
                    swaps[name] = swap
            return {"instance": instance_payload(instance, encoding="elements"),
                    "sets": raw["sets"], "universe_size": instance.universe_size, "k": instance.k,
                    "greedy_selected": chosen, "coverage": len(covered(chosen)), "optimum": optimum,
                    "optimum_selected": raw["optimum_selected"], "steps": steps,
                    "first_failure_step": first_failure, "mechanism": raw.get("mechanism"), **swaps}
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
            raise WorkbenchError(f"Invalid saved R1 trajectory: {error}") from error

    def export(self, source: str, key: str) -> dict[str, Any]:
        detail = self.detail(source, key)
        trace = detail["trace"]
        if trace is None:
            raise WorkbenchError("no saved instance sets are available for replay export")
        return {"instance": trace["instance"], "replay": {"algorithm": "greedy", "options": {},
                "expected": {"coverage": trace["coverage"], "selected": sorted(trace["greedy_selected"])}},
                "provenance": {"record_source": source, "record_key": key,
                               "trajectory_source": detail["trace_source"],
                               "instance_id": detail["record"]["instance_id"],
                               "note": "Saved R1 diagnostics; display consistency checked, not a fresh optimality proof."},
                "r1_diagnostics": trace}
