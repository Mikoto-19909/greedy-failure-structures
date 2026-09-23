"""Read-only research views over existing benchmark CSV and R1 trajectories.

No experiments or inferential comparisons run here. Summaries cover the complete
selected inputs; only the returned detail rows are paginated.
"""

from __future__ import annotations

import csv
import json
import os
from collections import OrderedDict
from pathlib import Path
import threading
from typing import Any, cast

from ._run_contracts import RunRecord
from .comparison import ComparisonSelection, validate_page, validate_sources
from .comparison_workflows import ComparisonAnalysis, analyze_comparison, preview_comparison
from .dashboard_paths import WorkbenchError, data_file, linked as _linked
from .dashboard_index import DashboardIndex, IndexedDocument
from .reproducibility import instance_from_payload, instance_payload
from .replay_documents import greedy_replay_document


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
        self.index = DashboardIndex(self.root)
        self._comparisons: OrderedDict[str, str] = OrderedDict()
        self._comparison_lock = threading.RLock()

    def _source_path(self, source: str) -> Path:
        paths = self._file(source, "paths.jsonl")
        return paths if paths.is_file() else self._file(source, "raw_results.csv")

    @staticmethod
    def _parser(source: str) -> str:
        # Source spelling is part of the public record, including on Windows.
        return "workbench-v1:" + source

    def _file(self, source: str, filename: str) -> Path:
        return data_file(self.root, source, filename)

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

    def _load(self, source: str) -> IndexedDocument:
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
            metadata = {"source": source, "kind": kind, "records": len(rows),
                        "instances": len({_identity(row) for row in rows}),
                        "cases": sorted({row["case_id"] for row in rows}),
                        "algorithms": sorted({row["algorithm_id"] for row in rows}),
                        "populations": sorted({row["population"] for row in rows}), "error": None}
            return IndexedDocument(kind, rows, raw, metadata)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise WorkbenchError(f"{source}: {error}") from error

    def _read(self, source: str, *, include_raw: bool = True) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            document = self.index.read(self._source_path(source), self._parser(source),
                                       lambda: self._load(source), include_raw=include_raw)
            return document.kind, document.rows, document.raw
        except OSError as error:
            raise WorkbenchError(f"{source}: {error}") from error

    def library(self, excluded: set[str] | None = None) -> dict[str, Any]:
        items = []
        for source in self._sources():
            if excluded and any(source == path or source.startswith(path + "/") for path in excluded):
                items.append({"source": source, "error": "Benchmark 正在写入此结果；请在运行中心查看检查点进度，停止后再读取。"})
                continue
            try:
                items.append(self.index.metadata(self._source_path(source), self._parser(source), lambda: self._load(source)))
            except (WorkbenchError, OSError) as error:
                items.append({"source": source, "error": str(error)})
        return {"sources": items}

    def rebuild_index(self) -> dict[str, Any]:
        with self._comparison_lock:
            self._comparisons.clear()
        self.index.clear()
        library = self.library()
        return {"index": self.index.status(), "sources": len(library["sources"]),
                "errors": [item for item in library["sources"] if item.get("error")]}

    def _source_signatures(self, sources: list[str]) -> list[Any]:
        try:
            return [(source, self.index.signature(self._source_path(source))) for source in sources]
        except OSError as error:
            raise WorkbenchError(str(error)) from error

    def _analyze(self, sources: list[str], selection: ComparisonSelection) -> ComparisonAnalysis:
        rows = tuple(row for source in sources for row in self._read(source, include_raw=False)[1])
        return analyze_comparison(tuple(sources), rows, selection)

    def analyze(self, sources: list[str], selection: ComparisonSelection) -> ComparisonAnalysis:
        """Read a complete analysis; application callers retain write coordination."""
        try:
            validate_sources(tuple(sources))
        except ValueError as error:
            raise WorkbenchError(str(error)) from error
        signatures = self._source_signatures(sources)
        analysis = self._analyze(sources, selection)
        if self._source_signatures(sources) != signatures:
            raise WorkbenchError("source changed during comparison; refresh and retry")
        return analysis

    def compare(self, sources: list[str], *, case: str = "", algorithm: str = "",
                population: str = "research", outcome: str = "all", page: int = 0,
                page_size: int = 50, include_all: bool = False) -> dict[str, Any]:
        try:
            validate_sources(tuple(sources))
            selection = ComparisonSelection(case, algorithm, population, outcome)
            validate_page(page, page_size)
        except ValueError as error:
            raise WorkbenchError(str(error)) from error
        signatures = self._source_signatures(sources)
        cache_key = json.dumps([signatures, case, algorithm, population, outcome, page, page_size])
        if not include_all:
            with self._comparison_lock:
                cached = self._comparisons.get(cache_key)
                if cached is not None:
                    self._comparisons.move_to_end(cache_key)
            if cached is not None:
                if self._source_signatures(sources) != signatures:
                    raise WorkbenchError("source changed during comparison; refresh and retry")
                return cast(dict[str, Any], json.loads(cached))
        analysis = self._analyze(sources, selection)
        result = preview_comparison(analysis, page, page_size, include_all=include_all)
        if self._source_signatures(sources) != signatures:
            raise WorkbenchError("source changed during comparison; refresh and retry")
        if not include_all:
            payload = json.dumps(result, ensure_ascii=True, allow_nan=False)
            if len(payload) <= 1_000_000:
                with self._comparison_lock:
                    self._comparisons[cache_key] = payload
                    self._comparisons.move_to_end(cache_key)
                    while len(self._comparisons) > 32 or sum(map(len, self._comparisons.values())) > 8_000_000:
                        self._comparisons.popitem(last=False)
        return result

    def detail(self, source: str, key: str) -> dict[str, Any]:
        try:
            record = self.index.record(self._source_path(source), self._parser(source), lambda: self._load(source), key=key)
        except OSError as error:
            raise WorkbenchError(str(error)) from error
        if record is None:
            raise WorkbenchError("record is no longer present in this source")
        kind, row, original_record = record
        trace, trace_source, warnings = None, None, []
        if kind == "r1":
            if original_record is None:
                raise WorkbenchError("saved R1 record has no trajectory")
            trace, trace_source = self._trace(original_record), source
        else:
            # Join all identity components, never seed alone. Non-Greedy records
            # keep their own selection; the linked trace is explicitly Greedy's.
            matches = []
            for candidate in self._sources():
                if not self._file(candidate, "paths.jsonl").is_file():
                    continue
                try:
                    candidates = self.index.matches(self._source_path(candidate), self._parser(candidate),
                        lambda: self._load(candidate), identity=cast(tuple[Any, Any, Any, Any], _identity(row)))
                    for _, item, original in candidates:
                        if item.get("config_hash") and _identity(item) == _identity(row):
                            if original is not None:
                                matches.append((candidate, original))
                except (WorkbenchError, OSError) as error:
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
        provenance = {"record_source": source, "record_key": key,
                      "trajectory_source": detail["trace_source"],
                      "instance_id": detail["record"]["instance_id"],
                      "note": "Saved R1 diagnostics; display consistency checked, not a fresh optimality proof."}
        try:
            document = greedy_replay_document(trace["instance"], coverage=trace["coverage"],
                                              selected=sorted(trace["greedy_selected"]), provenance=provenance)
        except ValueError as error:
            raise WorkbenchError(str(error)) from error
        return {**document, "r1_diagnostics": trace}
