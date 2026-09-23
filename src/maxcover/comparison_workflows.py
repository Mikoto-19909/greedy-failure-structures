"""Explicit composition of saved-record analysis, preview and snapshot creation.

These workflows take already parsed in-memory records; file-backed callers own
read coordination and source-change checks. No solver, HTTP or file IO runs here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .comparison import (ComparisonSelection, Row, SelectedRows, paginate,
                         select_outcomes, select_population, summarize_population,
                         validate_sources)


@dataclass(frozen=True)
class ComparisonAnalysis:
    sources: tuple[str, ...]
    selection: ComparisonSelection
    input_records: int
    filtered_records: int
    cases: tuple[str, ...]
    algorithms: tuple[str, ...]
    summaries: tuple[Row, ...]
    selected: SelectedRows


def analyze_comparison(sources: tuple[str, ...], rows: tuple[Row, ...],
                       selection: ComparisonSelection) -> ComparisonAnalysis:
    validate_sources(sources)
    population = select_population(rows, selection)
    # These are sibling branches. Outcome filtering must not change denominators.
    summaries = summarize_population(population)
    selected = select_outcomes(population, selection.outcome)
    return ComparisonAnalysis(sources, selection, len(rows), len(population.rows),
                              tuple(sorted({row["case_id"] for row in rows})),
                              tuple(sorted({row["algorithm_id"] for row in rows})),
                              tuple(summaries), selected)


def preview_comparison(analysis: ComparisonAnalysis, page: int = 0, page_size: int = 50,
                       *, include_all: bool = False) -> dict[str, Any]:
    """Adapt to the existing response; include_all preserves legacy metadata."""
    window = paginate(analysis.selected, page, page_size)
    return deepcopy({"sources": list(analysis.sources), "input_records": analysis.input_records,
                     "filtered_records": analysis.filtered_records, "total": window.total,
                     "page": window.page, "pages": window.pages, "page_size": window.page_size,
                     "cases": list(analysis.cases), "algorithms": list(analysis.algorithms),
                     "summaries": list(analysis.summaries),
                     "rows": list(analysis.selected.rows if include_all else window.rows)})


def assemble_snapshot(analysis: ComparisonAnalysis, *, identifier: str, saved_at: str,
                      title: str, note: str = "") -> dict[str, Any]:
    """Consume full analysis, never a page; caller provides clock and identity."""
    if not isinstance(analysis, ComparisonAnalysis):
        raise TypeError("snapshot requires complete comparison analysis")
    return {"id": identifier, "title": title.strip(), "note": note, "saved_at": saved_at,
            "filters": analysis.selection.as_dict(),
            "comparison": preview_comparison(analysis, include_all=True)}
