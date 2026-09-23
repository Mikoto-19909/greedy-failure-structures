"""Pure comparison components over normalized saved records.

Rows retain the existing dashboard fields. Stage containers distinguish the
statistical population from outcome-selected records; components never mutate
their inputs. File parsing and scientific reference validation belong upstream.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from statistics import fmean
from typing import Any

Row = dict[str, Any]


@dataclass(frozen=True)
class ComparisonSelection:
    case: str = ""
    algorithm: str = ""
    population: str = "research"
    outcome: str = "all"

    def __post_init__(self) -> None:
        if self.population not in {"research", "fixture", "all"} or self.outcome not in {"all", "loss", "zero", "missing"}:
            raise ValueError("unknown comparison filter")

    def as_dict(self) -> dict[str, str]:
        return {"case": self.case, "algorithm": self.algorithm,
                "population": self.population, "outcome": self.outcome}


@dataclass(frozen=True)
class PopulationRows:
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class SelectedRows:
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class RecordPage:
    rows: tuple[Row, ...]
    total: int
    page: int
    pages: int
    page_size: int


def validate_sources(sources: tuple[str, ...]) -> None:
    if not 1 <= len(sources) <= 4 or len(set(sources)) != len(sources):
        raise ValueError("select one to four distinct sources")


def validate_page(page: int, page_size: int) -> None:
    if type(page) is not int or page < 0:
        raise ValueError("page must be an integer >= 0")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")


def select_population(rows: tuple[Row, ...], selection: ComparisonSelection) -> PopulationRows:
    return PopulationRows(tuple(row for row in rows
        if (not selection.case or row["case_id"] == selection.case)
        and (not selection.algorithm or row["algorithm_id"] == selection.algorithm)
        and (selection.population == "all" or (row["population"] == "fixture" if selection.population == "fixture"
             else row["population"] in {"pilot", "confirmation", "experiment"}))))


def summarize_population(population: PopulationRows) -> list[Row]:
    if not isinstance(population, PopulationRows):
        raise TypeError("summary requires population rows, not outcome-selected rows")
    groups: dict[tuple[Any, ...], list[Row]] = defaultdict(list)
    for row in population.rows:
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
    return summaries


def select_outcomes(population: PopulationRows, outcome: str) -> SelectedRows:
    if outcome not in {"all", "missing", "loss", "zero"}:
        raise ValueError("unknown comparison filter")
    selected = [row for row in population.rows if outcome == "all"
                or (outcome == "missing" and row["optimality_gap"] is None)
                or (outcome == "loss" and row["optimality_gap"] is not None and row["optimality_gap"] > 0)
                or (outcome == "zero" and row["optimality_gap"] == 0)]
    selected.sort(key=lambda row: (-(row["optimality_gap"] if row["optimality_gap"] is not None else -1),
                                   row["source"], row["key"]))
    return SelectedRows(tuple(selected))


def paginate(selected: SelectedRows, page: int = 0, page_size: int = 50) -> RecordPage:
    validate_page(page, page_size)
    pages = max(1, math.ceil(len(selected.rows) / page_size))
    page = min(page, pages - 1)
    return RecordPage(selected.rows[page * page_size:(page + 1) * page_size],
                      len(selected.rows), page, pages, page_size)
