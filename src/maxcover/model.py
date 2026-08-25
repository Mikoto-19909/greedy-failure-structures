"""Immutable problem and result models."""

from __future__ import annotations

import math
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class FrozenMapping(Mapping[str, Any]):
    """A small, recursively immutable and pickle-safe JSON mapping."""

    __slots__ = ("_items",)
    _items: tuple[tuple[str, Any], ...]

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        raw = {} if values is None else values
        if not isinstance(raw, Mapping):
            raise TypeError("parameters must be a mapping")
        items: list[tuple[str, Any]] = []
        for key, value in raw.items():
            if not isinstance(key, str):
                raise TypeError("parameter keys must be strings")
            items.append((key, _freeze_json_value(value)))
        object.__setattr__(self, "_items", tuple(items))

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __getitem__(self, key: str) -> Any:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __reduce__(self) -> tuple[object, tuple[dict[str, Any]]]:
        return FrozenMapping, (dict(self._items),)

    def __repr__(self) -> str:
        return f"FrozenMapping({dict(self._items)!r})"


def _freeze_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parameter numbers must be finite")
        return value
    if isinstance(value, Mapping):
        return FrozenMapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    raise TypeError("parameter values must be finite JSON values")


def thaw_json_value(value: Any) -> Any:
    """Return mutable JSON containers for serialization without exposing internals."""

    if isinstance(value, Mapping):
        return {key: thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class MaximumCoverageInstance:
    """A Maximum Coverage instance encoded with Python integer bitsets."""

    universe_size: int
    sets: tuple[int, ...]
    k: int
    family: str = "custom"
    seed: int | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sets", tuple(self.sets))
        object.__setattr__(self, "parameters", FrozenMapping(self.parameters))
        if self.universe_size <= 0:
            raise ValueError("universe_size must be positive")
        if not self.sets:
            raise ValueError("at least one candidate set is required")
        if not 1 <= self.k <= len(self.sets):
            raise ValueError("k must be between 1 and the number of sets")
        limit = (1 << self.universe_size) - 1
        if any(mask < 0 or mask & ~limit for mask in self.sets):
            raise ValueError("a set contains an element outside the universe")

    @property
    def set_count(self) -> int:
        return len(self.sets)

    def coverage_mask(self, selected: tuple[int, ...]) -> int:
        mask = 0
        for index in selected:
            if not 0 <= index < self.set_count:
                raise IndexError(f"set index {index} is out of range")
            mask |= self.sets[index]
        return mask

    def coverage(self, selected: tuple[int, ...]) -> int:
        return self.coverage_mask(selected).bit_count()


class SolutionStatus(str, Enum):
    """Outcome of one algorithm run.

    ``TIMEOUT`` still carries the best feasible incumbent found before the
    deadline.  Only ``OPTIMAL`` certifies that incumbent as an optimum.
    """

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    TIMEOUT = "timeout"
    ERROR = "error"


METADATA_SCHEMA_VERSION = 1
_TERMINATIONS = {"completed", "time_limit", "iteration_limit", "error"}


def normalize_algorithm_metadata(
    value: Mapping[str, Any] | None,
    *,
    default_termination: str = "completed",
) -> Mapping[str, Any]:
    """Validate and normalize the shared per-run metadata envelope."""

    raw = dict(value or {})
    if not raw:
        raw = {
            "schema_version": METADATA_SCHEMA_VERSION,
            "termination": default_termination,
            "search": {},
            "trajectory": [],
        }
    if set(raw) != {"schema_version", "termination", "search", "trajectory"}:
        raise ValueError(
            "metadata must contain schema_version, termination, search, and trajectory"
        )
    if raw["schema_version"] != METADATA_SCHEMA_VERSION:
        raise ValueError("unsupported algorithm metadata schema version")
    if raw["termination"] not in _TERMINATIONS:
        raise ValueError("unsupported algorithm termination value")
    if not isinstance(raw["search"], Mapping):
        raise ValueError("metadata search must be an object")
    if not isinstance(raw["trajectory"], (list, tuple)):
        raise ValueError("metadata trajectory must be an array")
    try:
        copied = json.loads(
            json.dumps(raw, allow_nan=False, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError) as error:
        raise ValueError("metadata must contain only finite JSON values") from error
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class Solution:
    """An algorithm result with explicit incumbent and bound semantics.

    ``feasible_value`` is the coverage of ``selected`` for every non-error
    result.  ``best_bound`` is an upper bound on the optimum when one is known.
    An optimal result has a closed gap, so its bound must equal its feasible
    value.  The legacy ``coverage``, ``is_exact`` and ``timed_out`` names remain
    available as derived, read-only properties.
    """

    algorithm: str
    selected: tuple[int, ...]
    feasible_value: int | None
    runtime_seconds: float
    status: SolutionStatus
    best_bound: int | None = None
    nodes_or_iterations: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            object.__setattr__(self, "status", SolutionStatus(self.status))
        elif not isinstance(self.status, SolutionStatus):
            raise TypeError("status must be a SolutionStatus or its string value")
        object.__setattr__(
            self,
            "metadata",
            normalize_algorithm_metadata(
                self.metadata,
                default_termination=(
                    "error" if self.status is SolutionStatus.ERROR else "completed"
                ),
            ),
        )

        if not self.algorithm:
            raise ValueError("algorithm must not be empty")
        if not math.isfinite(self.runtime_seconds) or self.runtime_seconds < 0:
            raise ValueError("runtime_seconds must be finite and non-negative")
        if (
            isinstance(self.nodes_or_iterations, bool)
            or not isinstance(self.nodes_or_iterations, int)
            or self.nodes_or_iterations < 0
        ):
            raise ValueError("nodes_or_iterations must be a non-negative integer")
        if any(
            isinstance(index, bool) or not isinstance(index, int) or index < 0
            for index in self.selected
        ):
            raise ValueError("selected indices must be non-negative integers")
        if len(set(self.selected)) != len(self.selected):
            raise ValueError("selected indices must be unique")

        for name, value in (
            ("feasible_value", self.feasible_value),
            ("best_bound", self.best_bound),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")

        if self.status is SolutionStatus.ERROR:
            if (
                self.selected
                or self.feasible_value is not None
                or self.best_bound is not None
            ):
                raise ValueError("error results cannot contain an incumbent or bound")
            return

        if self.feasible_value is None:
            raise ValueError("non-error results must contain a feasible incumbent value")

        if self.status is SolutionStatus.OPTIMAL:
            if self.best_bound != self.feasible_value:
                raise ValueError(
                    "optimal results require best_bound == feasible_value"
                )
        elif self.best_bound is not None and self.best_bound <= self.feasible_value:
            raise ValueError(
                "non-optimal results require best_bound > feasible_value when present"
            )

    @property
    def optimal_value(self) -> int | None:
        """Return the certified optimum, never a merely feasible incumbent."""

        if self.status is SolutionStatus.OPTIMAL:
            return self.feasible_value
        return None

    @property
    def coverage(self) -> int | None:
        """Backward-compatible alias for the feasible incumbent value."""

        return self.feasible_value

    @property
    def is_exact(self) -> bool:
        """Backward-compatible exactness flag derived from ``status``."""

        return self.status is SolutionStatus.OPTIMAL

    @property
    def timed_out(self) -> bool:
        """Backward-compatible timeout flag derived from ``status``."""

        return self.status is SolutionStatus.TIMEOUT

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (
            Solution,
            (
                self.algorithm,
                self.selected,
                self.feasible_value,
                self.runtime_seconds,
                self.status,
                self.best_bound,
                self.nodes_or_iterations,
                dict(self.metadata),
            ),
        )
