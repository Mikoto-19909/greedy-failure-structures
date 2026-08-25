"""Private algorithm run and summary record contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from ._contract_csv import (
    _parse_bool,
    _parse_float,
    _parse_int,
    _required_float,
    _required_int,
    _validate_csv_fields,
)
from .model import SolutionStatus, normalize_algorithm_metadata


RECORD_SCHEMA_VERSION = 4
PREVIOUS_RECORD_SCHEMA_VERSION = 3


def _validate_schema_version(value: int) -> None:
    if value != RECORD_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported record schema version {value!r}; "
            f"expected {RECORD_SCHEMA_VERSION}"
        )



@dataclass(frozen=True, slots=True)
class RunRecord:
    """One typed algorithm-run record shared by CSV and reporting."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "instance_id",
        "run_id",
        "case",
        "repetition",
        "seed",
        "family",
        "universe_size",
        "set_count",
        "k",
        "parameters",
        "algorithm_id",
        "algorithm_seed",
        "algorithm",
        "algorithm_options",
        "algorithm_metadata",
        "status",
        "coverage",
        "best_bound",
        "optimum",
        "optimality_gap",
        "runtime_seconds",
        "is_exact",
        "timed_out",
        "nodes_or_iterations",
        "selected",
        "error_message",
        "schema_version",
    )

    case: str
    repetition: int
    seed: int | None
    family: str
    universe_size: int
    set_count: int
    k: int
    parameters: str
    algorithm: str
    algorithm_options: str
    status: SolutionStatus
    coverage: int | None
    best_bound: int | None
    optimum: int | None
    optimality_gap: float | None
    runtime_seconds: float
    nodes_or_iterations: int
    selected: tuple[int, ...]
    config_hash: str = ""
    case_id: str = ""
    instance_id: str = ""
    run_id: str = ""
    algorithm_id: str = ""
    algorithm_seed: int | None = None
    algorithm_metadata: str = ""
    error_message: str = ""
    schema_version: int = RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        if isinstance(self.status, str):
            object.__setattr__(self, "status", SolutionStatus(self.status))
        elif not isinstance(self.status, SolutionStatus):
            raise TypeError("status must be a SolutionStatus or its string value")

        for name, text_value in (
            ("case", self.case),
            ("family", self.family),
            ("algorithm", self.algorithm),
        ):
            if not text_value:
                raise ValueError(f"{name} must not be empty")
        for name, integer_value in (
            ("repetition", self.repetition),
            ("universe_size", self.universe_size),
            ("set_count", self.set_count),
            ("k", self.k),
            ("nodes_or_iterations", self.nodes_or_iterations),
        ):
            if isinstance(integer_value, bool) or not isinstance(integer_value, int):
                raise TypeError(f"{name} must be an integer")
        if self.repetition < 0:
            raise ValueError("repetition must be non-negative")
        if self.universe_size <= 0 or self.set_count <= 0:
            raise ValueError("universe_size and set_count must be positive")
        if not 1 <= self.k <= self.set_count:
            raise ValueError("k must be between 1 and set_count")
        if self.nodes_or_iterations < 0:
            raise ValueError("nodes_or_iterations must be non-negative")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise TypeError("seed must be an integer or None")
        if self.algorithm_seed is not None and (
            isinstance(self.algorithm_seed, bool)
            or not isinstance(self.algorithm_seed, int)
        ):
            raise TypeError("algorithm_seed must be an integer or None")

        try:
            parameters = json.loads(self.parameters)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("parameters must be a JSON object string") from error
        if not isinstance(parameters, dict):
            raise ValueError("parameters must encode a JSON object")
        object.__setattr__(
            self,
            "parameters",
            json.dumps(parameters, sort_keys=True, separators=(",", ":")),
        )
        try:
            algorithm_options = json.loads(self.algorithm_options)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("algorithm_options must be a JSON object string") from error
        if not isinstance(algorithm_options, dict):
            raise ValueError("algorithm_options must encode a JSON object")
        object.__setattr__(
            self,
            "algorithm_options",
            json.dumps(algorithm_options, sort_keys=True, separators=(",", ":")),
        )
        if not self.algorithm_metadata:
            metadata = normalize_algorithm_metadata(
                None,
                default_termination=(
                    "error" if self.status is SolutionStatus.ERROR else "completed"
                ),
            )
        else:
            try:
                raw_metadata = json.loads(self.algorithm_metadata)
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError(
                    "algorithm_metadata must be a JSON object string"
                ) from error
            if not isinstance(raw_metadata, dict):
                raise ValueError("algorithm_metadata must encode a JSON object")
            metadata = normalize_algorithm_metadata(
                raw_metadata,
                default_termination=(
                    "error" if self.status is SolutionStatus.ERROR else "completed"
                ),
            )
        object.__setattr__(
            self,
            "algorithm_metadata",
            json.dumps(dict(metadata), sort_keys=True, separators=(",", ":")),
        )

        object.__setattr__(self, "selected", tuple(self.selected))
        if not self.case_id:
            object.__setattr__(self, "case_id", self.case)
        if not self.algorithm_id:
            object.__setattr__(self, "algorithm_id", self.algorithm)
        for name in ("config_hash", "case_id", "instance_id", "run_id"):
            identifier_value = getattr(self, name)
            if not isinstance(identifier_value, str):
                raise TypeError(f"{name} must be a string")
        if not isinstance(self.error_message, str):
            raise TypeError("error_message must be a string")
        if any(
            isinstance(index, bool) or not isinstance(index, int) or index < 0
            for index in self.selected
        ):
            raise ValueError("selected indices must be non-negative integers")
        if len(set(self.selected)) != len(self.selected):
            raise ValueError("selected indices must be unique")

        for name, optional_integer in (
            ("coverage", self.coverage),
            ("best_bound", self.best_bound),
            ("optimum", self.optimum),
        ):
            if optional_integer is not None and (
                isinstance(optional_integer, bool)
                or not isinstance(optional_integer, int)
                or optional_integer < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")
            if optional_integer is not None and optional_integer > self.universe_size:
                raise ValueError(f"{name} cannot exceed universe_size")

        if not math.isfinite(self.runtime_seconds) or self.runtime_seconds < 0:
            raise ValueError("runtime_seconds must be finite and non-negative")
        if self.optimality_gap is not None and (
            not math.isfinite(self.optimality_gap)
            or not 0 <= self.optimality_gap <= 1
        ):
            raise ValueError("optimality_gap must be between 0 and 1 or None")

        if self.status is SolutionStatus.ERROR:
            if (
                self.selected
                or self.coverage is not None
                or self.best_bound is not None
            ):
                raise ValueError("error records cannot contain an incumbent or bound")
            if not self.error_message:
                object.__setattr__(self, "error_message", "algorithm error")
        elif self.error_message:
            raise ValueError("only error records may contain error_message")
        elif self.coverage is None:
            raise ValueError("non-error records must contain coverage")
        elif self.status is SolutionStatus.OPTIMAL:
            if self.best_bound != self.coverage:
                raise ValueError("optimal records require best_bound == coverage")
        elif self.best_bound is not None and self.best_bound <= self.coverage:
            raise ValueError("non-optimal records require best_bound > coverage")

        if self.optimality_gap is not None:
            if self.optimum is None or self.optimum <= 0 or self.coverage is None:
                raise ValueError("optimality_gap requires positive optimum and coverage")
            expected_gap = (self.optimum - self.coverage) / self.optimum
            if not math.isclose(self.optimality_gap, expected_gap, abs_tol=5e-10):
                raise ValueError("optimality_gap does not match optimum and coverage")

    @property
    def is_exact(self) -> bool:
        return self.status is SolutionStatus.OPTIMAL

    @property
    def timed_out(self) -> bool:
        return self.status is SolutionStatus.TIMEOUT

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "instance_id": self.instance_id,
            "run_id": self.run_id,
            "case": self.case,
            "repetition": self.repetition,
            "seed": "" if self.seed is None else self.seed,
            "family": self.family,
            "universe_size": self.universe_size,
            "set_count": self.set_count,
            "k": self.k,
            "parameters": self.parameters,
            "algorithm_id": self.algorithm_id,
            "algorithm_seed": (
                "" if self.algorithm_seed is None else self.algorithm_seed
            ),
            "algorithm": self.algorithm,
            "algorithm_options": self.algorithm_options,
            "algorithm_metadata": self.algorithm_metadata,
            "status": self.status.value,
            "coverage": "" if self.coverage is None else self.coverage,
            "best_bound": "" if self.best_bound is None else self.best_bound,
            "optimum": "" if self.optimum is None else self.optimum,
            "optimality_gap": (
                "" if self.optimality_gap is None else f"{self.optimality_gap:.10f}"
            ),
            "runtime_seconds": f"{self.runtime_seconds:.10f}",
            "is_exact": self.is_exact,
            "timed_out": self.timed_out,
            "nodes_or_iterations": self.nodes_or_iterations,
            "selected": " ".join(map(str, self.selected)),
            "error_message": self.error_message,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> RunRecord:
        schema_version = _parse_int(row["schema_version"], "schema_version")
        assert schema_version is not None
        values = dict(row)
        if schema_version == PREVIOUS_RECORD_SCHEMA_VERSION:
            values["algorithm_id"] = values["algorithm"]
            values["algorithm_seed"] = ""
            values["algorithm_metadata"] = ""
            values["schema_version"] = str(RECORD_SCHEMA_VERSION)
            schema_version = RECORD_SCHEMA_VERSION
        _validate_csv_fields(values, cls.CSV_FIELDS)
        row = values
        _validate_schema_version(schema_version)
        status = SolutionStatus(row["status"])
        is_exact = _parse_bool(row["is_exact"], "is_exact")
        timed_out = _parse_bool(row["timed_out"], "timed_out")
        if is_exact != (status is SolutionStatus.OPTIMAL):
            raise ValueError("CSV field 'is_exact' conflicts with status")
        if timed_out != (status is SolutionStatus.TIMEOUT):
            raise ValueError("CSV field 'timed_out' conflicts with status")
        selected_text = row["selected"].strip()
        try:
            selected = tuple(int(index) for index in selected_text.split())
        except ValueError as error:
            raise ValueError("CSV field 'selected' must contain integer indices") from error
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            instance_id=row["instance_id"],
            run_id=row["run_id"],
            case=row["case"],
            repetition=_required_int(row["repetition"], "repetition"),
            seed=_parse_int(row["seed"], "seed", optional=True),
            family=row["family"],
            universe_size=_required_int(row["universe_size"], "universe_size"),
            set_count=_required_int(row["set_count"], "set_count"),
            k=_required_int(row["k"], "k"),
            parameters=row["parameters"],
            algorithm_id=row["algorithm_id"],
            algorithm_seed=_parse_int(
                row["algorithm_seed"], "algorithm_seed", optional=True
            ),
            algorithm=row["algorithm"],
            algorithm_options=row["algorithm_options"],
            algorithm_metadata=row["algorithm_metadata"],
            status=status,
            coverage=_parse_int(row["coverage"], "coverage", optional=True),
            best_bound=_parse_int(row["best_bound"], "best_bound", optional=True),
            optimum=_parse_int(row["optimum"], "optimum", optional=True),
            optimality_gap=_parse_float(
                row["optimality_gap"], "optimality_gap", optional=True
            ),
            runtime_seconds=_required_float(row["runtime_seconds"], "runtime_seconds"),
            nodes_or_iterations=_required_int(
                row["nodes_or_iterations"], "nodes_or_iterations"
            ),
            selected=selected,
            error_message=row["error_message"],
            schema_version=schema_version,
        )


@dataclass(frozen=True, slots=True)
class SummaryRecord:
    """One typed aggregate record shared by CSV and reporting."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "case",
        "family",
        "algorithm_id",
        "algorithm",
        "runs",
        "mean_coverage",
        "mean_optimality_gap",
        "max_optimality_gap",
        "mean_runtime_seconds",
        "timeouts",
        "schema_version",
    )

    case: str
    family: str
    algorithm: str
    runs: int
    mean_coverage: float | None
    mean_optimality_gap: float | None
    max_optimality_gap: float | None
    mean_runtime_seconds: float
    timeouts: int
    algorithm_id: str = ""
    schema_version: int = RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        for name, text_value in (
            ("case", self.case),
            ("family", self.family),
            ("algorithm", self.algorithm),
        ):
            if not text_value:
                raise ValueError(f"{name} must not be empty")
        if not self.algorithm_id:
            object.__setattr__(self, "algorithm_id", self.algorithm)
        if isinstance(self.runs, bool) or not isinstance(self.runs, int) or self.runs <= 0:
            raise ValueError("runs must be a positive integer")
        if (
            isinstance(self.timeouts, bool)
            or not isinstance(self.timeouts, int)
            or not 0 <= self.timeouts <= self.runs
        ):
            raise ValueError("timeouts must be between 0 and runs")
        for name, nonnegative_value in (
            ("mean_coverage", self.mean_coverage),
            ("mean_runtime_seconds", self.mean_runtime_seconds),
        ):
            if nonnegative_value is not None and (
                not math.isfinite(nonnegative_value) or nonnegative_value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        for name, gap_value in (
            ("mean_optimality_gap", self.mean_optimality_gap),
            ("max_optimality_gap", self.max_optimality_gap),
        ):
            if gap_value is not None and (
                not math.isfinite(gap_value) or not 0 <= gap_value <= 1
            ):
                raise ValueError(f"{name} must be between 0 and 1 or None")
        if (self.mean_optimality_gap is None) != (self.max_optimality_gap is None):
            raise ValueError("mean and max optimality gaps must both be present or absent")
        if (
            self.mean_optimality_gap is not None
            and self.max_optimality_gap is not None
            and self.mean_optimality_gap > self.max_optimality_gap
            and not math.isclose(
                self.mean_optimality_gap, self.max_optimality_gap
            )
        ):
            raise ValueError("mean optimality gap cannot exceed max optimality gap")

    def to_csv_row(self) -> dict[str, object]:
        return {
            "case": self.case,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "runs": self.runs,
            "mean_coverage": (
                "" if self.mean_coverage is None else f"{self.mean_coverage:.4f}"
            ),
            "mean_optimality_gap": (
                ""
                if self.mean_optimality_gap is None
                else f"{self.mean_optimality_gap:.8f}"
            ),
            "max_optimality_gap": (
                ""
                if self.max_optimality_gap is None
                else f"{self.max_optimality_gap:.8f}"
            ),
            "mean_runtime_seconds": f"{self.mean_runtime_seconds:.10f}",
            "timeouts": self.timeouts,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> SummaryRecord:
        values = dict(row)
        schema_version = _required_int(values["schema_version"], "schema_version")
        if schema_version == PREVIOUS_RECORD_SCHEMA_VERSION:
            values["algorithm_id"] = values["algorithm"]
            values["schema_version"] = str(RECORD_SCHEMA_VERSION)
            schema_version = RECORD_SCHEMA_VERSION
        _validate_csv_fields(values, cls.CSV_FIELDS)
        _validate_schema_version(schema_version)
        row = values
        return cls(
            case=row["case"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            runs=_required_int(row["runs"], "runs"),
            mean_coverage=_parse_float(
                row["mean_coverage"], "mean_coverage", optional=True
            ),
            mean_optimality_gap=_parse_float(
                row["mean_optimality_gap"], "mean_optimality_gap", optional=True
            ),
            max_optimality_gap=_parse_float(
                row["max_optimality_gap"], "max_optimality_gap", optional=True
            ),
            mean_runtime_seconds=_required_float(
                row["mean_runtime_seconds"], "mean_runtime_seconds"
            ),
            timeouts=_required_int(row["timeouts"], "timeouts"),
            schema_version=schema_version,
        )


RunRecord.__module__ = "maxcover.contracts"
SummaryRecord.__module__ = "maxcover.contracts"
