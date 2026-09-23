"""Build replay documents from validated saved instances, without running solvers."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .reproducibility import instance_from_payload


def greedy_replay_document(instance: dict[str, Any], *, coverage: int,
                           selected: list[int], provenance: dict[str, Any]) -> dict[str, Any]:
    """Check witness feasibility; this is not an optimality proof.

    Study-specific provenance and reference checks remain in the source adapter.
    Selection is the canonical sorted set of indices, not a decision trajectory.
    """
    problem = instance_from_payload(instance)
    if (len(selected) != problem.k or any(type(i) is not int or not 0 <= i < problem.set_count for i in selected)
            or selected != sorted(set(selected))):
        raise ValueError("replay selection must contain k distinct sorted valid indices")
    if type(coverage) is not int or problem.coverage(tuple(selected)) != coverage:
        raise ValueError("replay coverage disagrees with selected sets")
    return deepcopy({"instance": instance,
                     "replay": {"algorithm": "greedy", "options": {},
                                "expected": {"coverage": coverage, "selected": selected}},
                     "provenance": provenance})
