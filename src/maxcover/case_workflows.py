"""Compose failure selection and a saved-instance resolver into a bounded bundle."""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .comparison_workflows import ComparisonAnalysis, preview_comparison
from .replay_documents import greedy_replay_document


def assemble_failure_bundle(analysis: ComparisonAnalysis,
                            resolve: Callable[[str, str], dict[str, Any]], *,
                            maximum_cases: int = 100) -> dict[str, Any]:
    """Resolve every requested case or raise; never silently omit broken inputs.

    The caller holds read coordination for all resolver inputs. This workflow
    neither writes files nor runs an algorithm. Limits affect exported instances,
    not the population summaries or the full selected-record inventory.
    """
    if not isinstance(analysis, ComparisonAnalysis) or analysis.selection.outcome != "loss":
        raise ValueError("failure bundle requires a complete loss-filtered analysis")
    if type(maximum_cases) is not int or not 1 <= maximum_cases <= 200:
        raise ValueError("maximum_cases must be between 1 and 200")
    rows = analysis.selected.rows
    if any(row["algorithm_id"] != "greedy" or row["optimality_gap"] is None
           or row["optimality_gap"] <= 0 for row in rows):
        raise ValueError("failure bundle requires Greedy records with a positive saved gap")
    cases = []
    for row in rows[:maximum_cases]:
        document = resolve(row["source"], row["key"])
        replay = document["replay"]
        expected = replay["expected"]
        provenance = document["provenance"]
        if (provenance.get("instance_id") != row["instance_id"]
                or provenance.get("record_source") != row["source"] or provenance.get("record_key") != row["key"]
                or replay["algorithm"] != "greedy"
                or replay["options"] != {} or expected["coverage"] != row["coverage"]
                or expected["selected"] != sorted(row["selected"])):
            raise ValueError("resolved replay differs from selected comparison record")
        greedy_replay_document(document["instance"], coverage=expected["coverage"],
                               selected=expected["selected"], provenance=provenance)
        cases.append({"source": row["source"], "key": row["key"], "document": deepcopy(document)})
    return {"comparison": preview_comparison(analysis, include_all=True),
            "selected_cases": len(rows), "exported_cases": len(cases),
            "truncated": len(cases) < len(rows), "cases": cases}
