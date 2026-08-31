"""Typed contracts for exact-reference coverage and censoring diagnostics."""

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


REFERENCE_STATUS_SCHEMA_VERSION = 1
REFERENCE_COVERAGE_SCHEMA_VERSION = 1
REFERENCE_CENSORING_BIAS_SCHEMA_VERSION = 1
REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION = 1

REFERENCE_STATUSES = (
    "known_optimum_certificate",
    "optimal",
    "feasible",
    "timeout",
    "error",
    "not_run",
)


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _canonical_object(value: str, field: str) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field} must be a JSON object string") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must encode a JSON object")
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def _tuple_from_json(value: str, field: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"CSV field {field!r} must contain a JSON array") from error
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) or not item for item in parsed
    ):
        raise ValueError(
            f"CSV field {field!r} must contain non-empty string values"
        )
    return tuple(parsed)


@dataclass(frozen=True, slots=True)
class ReferenceStatusRecord:
    """One generated instance's effective reference status and source detail."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "instance_id",
        "repetition",
        "family",
        "parameters",
        "reference_status",
        "exact_solver_statuses",
        "reference_source_ids",
        "proof_source_count",
        "has_known_optimum_certificate",
        "provably_optimal",
        "optimum",
        "cross_validation_status",
        "small_instance_cross_validated",
        "schema_version",
    )

    config_hash: str
    case_id: str
    instance_id: str
    repetition: int
    family: str
    parameters: str
    reference_status: str
    exact_solver_statuses: str
    reference_source_ids: tuple[str, ...]
    proof_source_count: int
    has_known_optimum_certificate: bool
    provably_optimal: bool
    optimum: int | None
    cross_validation_status: str
    small_instance_cross_validated: bool
    schema_version: int = REFERENCE_STATUS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REFERENCE_STATUS_SCHEMA_VERSION:
            raise ValueError("unsupported reference-status schema version")
        for name in ("config_hash", "case_id", "instance_id", "family"):
            _required_text(getattr(self, name), name)
        if self.repetition < 0:
            raise ValueError("repetition must be non-negative")
        object.__setattr__(self, "parameters", _canonical_object(self.parameters, "parameters"))
        statuses_text = _canonical_object(
            self.exact_solver_statuses, "exact_solver_statuses"
        )
        statuses = json.loads(statuses_text)
        if any(value not in REFERENCE_STATUSES[1:] for value in statuses.values()):
            raise ValueError("exact_solver_statuses contains an unsupported status")
        object.__setattr__(self, "exact_solver_statuses", statuses_text)
        object.__setattr__(self, "reference_source_ids", tuple(self.reference_source_ids))
        if any(not isinstance(value, str) or not value for value in self.reference_source_ids):
            raise ValueError("reference_source_ids must contain non-empty strings")
        if len(set(self.reference_source_ids)) != len(self.reference_source_ids):
            raise ValueError("reference_source_ids must be unique")
        if self.reference_status not in REFERENCE_STATUSES:
            raise ValueError("unsupported reference_status")
        if self.cross_validation_status not in {
            "not_available",
            "single_source",
            "agreement",
        }:
            raise ValueError("unsupported cross_validation_status")
        if self.proof_source_count != len(self.reference_source_ids):
            raise ValueError("proof_source_count must match reference_source_ids")
        if self.proof_source_count < 0:
            raise ValueError("proof_source_count must be non-negative")
        expected_cross_validation = (
            "not_available"
            if self.proof_source_count == 0
            else "single_source"
            if self.proof_source_count == 1
            else "agreement"
        )
        if self.cross_validation_status != expected_cross_validation:
            raise ValueError("cross_validation_status conflicts with proof sources")
        if self.provably_optimal != (self.proof_source_count > 0):
            raise ValueError("provably_optimal conflicts with proof sources")
        if self.provably_optimal != (self.optimum is not None):
            raise ValueError("provably_optimal conflicts with optimum")
        if self.optimum is not None and self.optimum < 0:
            raise ValueError("optimum must be non-negative or None")
        if self.has_known_optimum_certificate != (
            "known_optimum_certificate" in self.reference_source_ids
        ):
            raise ValueError("certificate flag conflicts with reference sources")
        if self.reference_status == "known_optimum_certificate" and not self.has_known_optimum_certificate:
            raise ValueError("certificate status requires a certificate source")
        if self.reference_status == "optimal" and not self.provably_optimal:
            raise ValueError("optimal status requires a proved reference")
        if self.reference_status not in {"known_optimum_certificate", "optimal"} and self.provably_optimal:
            raise ValueError("unproved status cannot carry a proved reference")
        if self.small_instance_cross_validated and self.proof_source_count < 2:
            raise ValueError("small-instance cross-validation requires two proof sources")

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "instance_id": self.instance_id,
            "repetition": self.repetition,
            "family": self.family,
            "parameters": self.parameters,
            "reference_status": self.reference_status,
            "exact_solver_statuses": self.exact_solver_statuses,
            "reference_source_ids": json.dumps(
                self.reference_source_ids, separators=(",", ":")
            ),
            "proof_source_count": self.proof_source_count,
            "has_known_optimum_certificate": self.has_known_optimum_certificate,
            "provably_optimal": self.provably_optimal,
            "optimum": "" if self.optimum is None else self.optimum,
            "cross_validation_status": self.cross_validation_status,
            "small_instance_cross_validated": self.small_instance_cross_validated,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> ReferenceStatusRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            instance_id=row["instance_id"],
            repetition=_required_int(row["repetition"], "repetition"),
            family=row["family"],
            parameters=row["parameters"],
            reference_status=row["reference_status"],
            exact_solver_statuses=row["exact_solver_statuses"],
            reference_source_ids=_tuple_from_json(
                row["reference_source_ids"], "reference_source_ids"
            ),
            proof_source_count=_required_int(
                row["proof_source_count"], "proof_source_count"
            ),
            has_known_optimum_certificate=_parse_bool(
                row["has_known_optimum_certificate"],
                "has_known_optimum_certificate",
            ),
            provably_optimal=_parse_bool(row["provably_optimal"], "provably_optimal"),
            optimum=_parse_int(row["optimum"], "optimum", optional=True),
            cross_validation_status=row["cross_validation_status"],
            small_instance_cross_validated=_parse_bool(
                row["small_instance_cross_validated"],
                "small_instance_cross_validated",
            ),
            schema_version=_required_int(row["schema_version"], "schema_version"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceCoverageRecord:
    """One family/parameter/status slice of exact-reference coverage."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "family",
        "parameters",
        "case_count",
        "case_ids",
        "status",
        "generated_instance_count",
        "status_instance_count",
        "status_rate",
        "provably_optimal_instance_count",
        "reference_coverage",
        "certificate_reference_count",
        "solver_reference_count",
        "cross_validated_instance_count",
        "schema_version",
    )

    config_hash: str
    family: str
    parameters: str
    case_count: int
    case_ids: tuple[str, ...]
    status: str
    generated_instance_count: int
    status_instance_count: int
    status_rate: float
    provably_optimal_instance_count: int
    reference_coverage: float
    certificate_reference_count: int
    solver_reference_count: int
    cross_validated_instance_count: int
    schema_version: int = REFERENCE_COVERAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REFERENCE_COVERAGE_SCHEMA_VERSION:
            raise ValueError("unsupported reference-coverage schema version")
        _required_text(self.config_hash, "config_hash")
        _required_text(self.family, "family")
        object.__setattr__(self, "parameters", _canonical_object(self.parameters, "parameters"))
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if self.status not in REFERENCE_STATUSES:
            raise ValueError("unsupported coverage status")
        if self.case_count != len(self.case_ids) or self.case_count <= 0:
            raise ValueError("case_count must match non-empty case_ids")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("case_ids must be unique")
        counts = (
            self.status_instance_count,
            self.provably_optimal_instance_count,
            self.certificate_reference_count,
            self.solver_reference_count,
            self.cross_validated_instance_count,
        )
        if self.generated_instance_count <= 0 or any(
            value < 0 or value > self.generated_instance_count for value in counts
        ):
            raise ValueError("reference coverage counts are outside the denominator")
        for name, value in (
            ("status_rate", self.status_rate),
            ("reference_coverage", self.reference_coverage),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between zero and one")
        if not math.isclose(
            self.status_rate,
            self.status_instance_count / self.generated_instance_count,
            abs_tol=5e-10,
        ):
            raise ValueError("status_rate does not match its count")
        if not math.isclose(
            self.reference_coverage,
            self.provably_optimal_instance_count / self.generated_instance_count,
            abs_tol=5e-10,
        ):
            raise ValueError("reference_coverage does not match its count")

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "family": self.family,
            "parameters": self.parameters,
            "case_count": self.case_count,
            "case_ids": json.dumps(self.case_ids, separators=(",", ":")),
            "status": self.status,
            "generated_instance_count": self.generated_instance_count,
            "status_instance_count": self.status_instance_count,
            "status_rate": f"{self.status_rate:.10f}",
            "provably_optimal_instance_count": self.provably_optimal_instance_count,
            "reference_coverage": f"{self.reference_coverage:.10f}",
            "certificate_reference_count": self.certificate_reference_count,
            "solver_reference_count": self.solver_reference_count,
            "cross_validated_instance_count": self.cross_validated_instance_count,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> ReferenceCoverageRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            parameters=row["parameters"],
            case_count=_required_int(row["case_count"], "case_count"),
            case_ids=_tuple_from_json(row["case_ids"], "case_ids"),
            status=row["status"],
            generated_instance_count=_required_int(
                row["generated_instance_count"], "generated_instance_count"
            ),
            status_instance_count=_required_int(
                row["status_instance_count"], "status_instance_count"
            ),
            status_rate=_required_float(row["status_rate"], "status_rate"),
            provably_optimal_instance_count=_required_int(
                row["provably_optimal_instance_count"],
                "provably_optimal_instance_count",
            ),
            reference_coverage=_required_float(
                row["reference_coverage"], "reference_coverage"
            ),
            certificate_reference_count=_required_int(
                row["certificate_reference_count"], "certificate_reference_count"
            ),
            solver_reference_count=_required_int(
                row["solver_reference_count"], "solver_reference_count"
            ),
            cross_validated_instance_count=_required_int(
                row["cross_validated_instance_count"],
                "cross_validated_instance_count",
            ),
            schema_version=_required_int(row["schema_version"], "schema_version"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceCensoringBiasRecord:
    """Retained-versus-excluded means for one size or structure metric."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "family",
        "parameters",
        "case_count",
        "case_ids",
        "metric",
        "retained_instance_count",
        "excluded_instance_count",
        "retained_observation_count",
        "excluded_observation_count",
        "retained_mean",
        "excluded_mean",
        "excluded_minus_retained",
        "comparison_status",
        "schema_version",
    )

    config_hash: str
    family: str
    parameters: str
    case_count: int
    case_ids: tuple[str, ...]
    metric: str
    retained_instance_count: int
    excluded_instance_count: int
    retained_observation_count: int
    excluded_observation_count: int
    retained_mean: float | None
    excluded_mean: float | None
    excluded_minus_retained: float | None
    comparison_status: str
    schema_version: int = REFERENCE_CENSORING_BIAS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REFERENCE_CENSORING_BIAS_SCHEMA_VERSION:
            raise ValueError("unsupported reference-censoring-bias schema version")
        _required_text(self.config_hash, "config_hash")
        _required_text(self.family, "family")
        _required_text(self.metric, "metric")
        object.__setattr__(self, "parameters", _canonical_object(self.parameters, "parameters"))
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if self.case_count != len(self.case_ids) or self.case_count <= 0:
            raise ValueError("case_count must match non-empty case_ids")
        for name in (
            "retained_instance_count",
            "excluded_instance_count",
            "retained_observation_count",
            "excluded_observation_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.retained_observation_count > self.retained_instance_count:
            raise ValueError("retained observations exceed retained instances")
        if self.excluded_observation_count > self.excluded_instance_count:
            raise ValueError("excluded observations exceed excluded instances")
        expected_status = (
            "estimable"
            if self.retained_observation_count and self.excluded_observation_count
            else "missing_group"
        )
        if self.comparison_status != expected_status:
            raise ValueError("comparison_status conflicts with observations")
        for name in ("retained_mean", "excluded_mean", "excluded_minus_retained"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite or None")
        if expected_status == "estimable":
            if self.retained_mean is None or self.excluded_mean is None:
                raise ValueError("estimable comparisons require both means")
            expected_difference = self.excluded_mean - self.retained_mean
            if self.excluded_minus_retained is None or not math.isclose(
                self.excluded_minus_retained, expected_difference, abs_tol=5e-10
            ):
                raise ValueError("excluded_minus_retained does not match means")
        elif self.excluded_minus_retained is not None:
            raise ValueError("missing-group comparisons require a blank difference")

    def to_csv_row(self) -> dict[str, object]:
        optional = lambda value: "" if value is None else f"{value:.10f}"
        return {
            "config_hash": self.config_hash,
            "family": self.family,
            "parameters": self.parameters,
            "case_count": self.case_count,
            "case_ids": json.dumps(self.case_ids, separators=(",", ":")),
            "metric": self.metric,
            "retained_instance_count": self.retained_instance_count,
            "excluded_instance_count": self.excluded_instance_count,
            "retained_observation_count": self.retained_observation_count,
            "excluded_observation_count": self.excluded_observation_count,
            "retained_mean": optional(self.retained_mean),
            "excluded_mean": optional(self.excluded_mean),
            "excluded_minus_retained": optional(self.excluded_minus_retained),
            "comparison_status": self.comparison_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> ReferenceCensoringBiasRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            parameters=row["parameters"],
            case_count=_required_int(row["case_count"], "case_count"),
            case_ids=_tuple_from_json(row["case_ids"], "case_ids"),
            metric=row["metric"],
            retained_instance_count=_required_int(
                row["retained_instance_count"], "retained_instance_count"
            ),
            excluded_instance_count=_required_int(
                row["excluded_instance_count"], "excluded_instance_count"
            ),
            retained_observation_count=_required_int(
                row["retained_observation_count"], "retained_observation_count"
            ),
            excluded_observation_count=_required_int(
                row["excluded_observation_count"], "excluded_observation_count"
            ),
            retained_mean=_parse_float(row["retained_mean"], "retained_mean", optional=True),
            excluded_mean=_parse_float(row["excluded_mean"], "excluded_mean", optional=True),
            excluded_minus_retained=_parse_float(
                row["excluded_minus_retained"],
                "excluded_minus_retained",
                optional=True,
            ),
            comparison_status=row["comparison_status"],
            schema_version=_required_int(row["schema_version"], "schema_version"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceCutoffSensitivityRecord:
    """Coverage and status counts for one configured exact-solver cutoff."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "family",
        "parameters",
        "case_count",
        "case_ids",
        "algorithm_id",
        "algorithm",
        "time_limit_seconds",
        "max_set_count",
        "generated_instance_count",
        "eligible_instance_count",
        "optimal_count",
        "feasible_count",
        "timeout_count",
        "error_count",
        "not_run_count",
        "certificate_count",
        "solver_reference_coverage",
        "effective_reference_coverage",
        "schema_version",
    )

    config_hash: str
    family: str
    parameters: str
    case_count: int
    case_ids: tuple[str, ...]
    algorithm_id: str
    algorithm: str
    time_limit_seconds: float | None
    max_set_count: int | None
    generated_instance_count: int
    eligible_instance_count: int
    optimal_count: int
    feasible_count: int
    timeout_count: int
    error_count: int
    not_run_count: int
    certificate_count: int
    solver_reference_coverage: float
    effective_reference_coverage: float
    schema_version: int = REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REFERENCE_CUTOFF_SENSITIVITY_SCHEMA_VERSION:
            raise ValueError("unsupported reference-cutoff schema version")
        for name in ("config_hash", "family", "algorithm_id", "algorithm"):
            _required_text(getattr(self, name), name)
        object.__setattr__(self, "parameters", _canonical_object(self.parameters, "parameters"))
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if self.case_count != len(self.case_ids) or self.case_count <= 0:
            raise ValueError("case_count must match non-empty case_ids")
        if self.time_limit_seconds is not None and (
            not math.isfinite(self.time_limit_seconds) or self.time_limit_seconds <= 0
        ):
            raise ValueError("time_limit_seconds must be finite and positive or None")
        if self.max_set_count is not None and self.max_set_count <= 0:
            raise ValueError("max_set_count must be positive or None")
        counts = (
            self.eligible_instance_count,
            self.optimal_count,
            self.feasible_count,
            self.timeout_count,
            self.error_count,
            self.not_run_count,
            self.certificate_count,
        )
        if self.generated_instance_count <= 0 or any(
            value < 0 or value > self.generated_instance_count for value in counts
        ):
            raise ValueError("cutoff counts are outside the generated denominator")
        if self.eligible_instance_count + self.not_run_count != self.generated_instance_count:
            raise ValueError("eligible and not-run counts must partition generated instances")
        if (
            self.optimal_count
            + self.feasible_count
            + self.timeout_count
            + self.error_count
            != self.eligible_instance_count
        ):
            raise ValueError("solver status counts must partition eligible instances")
        for name, value in (
            ("solver_reference_coverage", self.solver_reference_coverage),
            ("effective_reference_coverage", self.effective_reference_coverage),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between zero and one")
        if not math.isclose(
            self.solver_reference_coverage,
            self.optimal_count / self.generated_instance_count,
            abs_tol=5e-10,
        ):
            raise ValueError("solver_reference_coverage does not match optimal_count")
        if self.effective_reference_coverage < self.solver_reference_coverage:
            raise ValueError("certificate coverage cannot reduce solver coverage")

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "family": self.family,
            "parameters": self.parameters,
            "case_count": self.case_count,
            "case_ids": json.dumps(self.case_ids, separators=(",", ":")),
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "time_limit_seconds": (
                "" if self.time_limit_seconds is None else f"{self.time_limit_seconds:.10f}"
            ),
            "max_set_count": "" if self.max_set_count is None else self.max_set_count,
            "generated_instance_count": self.generated_instance_count,
            "eligible_instance_count": self.eligible_instance_count,
            "optimal_count": self.optimal_count,
            "feasible_count": self.feasible_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "not_run_count": self.not_run_count,
            "certificate_count": self.certificate_count,
            "solver_reference_coverage": f"{self.solver_reference_coverage:.10f}",
            "effective_reference_coverage": f"{self.effective_reference_coverage:.10f}",
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> ReferenceCutoffSensitivityRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            parameters=row["parameters"],
            case_count=_required_int(row["case_count"], "case_count"),
            case_ids=_tuple_from_json(row["case_ids"], "case_ids"),
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            time_limit_seconds=_parse_float(
                row["time_limit_seconds"], "time_limit_seconds", optional=True
            ),
            max_set_count=_parse_int(
                row["max_set_count"], "max_set_count", optional=True
            ),
            generated_instance_count=_required_int(
                row["generated_instance_count"], "generated_instance_count"
            ),
            eligible_instance_count=_required_int(
                row["eligible_instance_count"], "eligible_instance_count"
            ),
            optimal_count=_required_int(row["optimal_count"], "optimal_count"),
            feasible_count=_required_int(row["feasible_count"], "feasible_count"),
            timeout_count=_required_int(row["timeout_count"], "timeout_count"),
            error_count=_required_int(row["error_count"], "error_count"),
            not_run_count=_required_int(row["not_run_count"], "not_run_count"),
            certificate_count=_required_int(
                row["certificate_count"], "certificate_count"
            ),
            solver_reference_coverage=_required_float(
                row["solver_reference_coverage"], "solver_reference_coverage"
            ),
            effective_reference_coverage=_required_float(
                row["effective_reference_coverage"], "effective_reference_coverage"
            ),
            schema_version=_required_int(row["schema_version"], "schema_version"),
        )


ReferenceStatusRecord.__module__ = "maxcover.contracts"
ReferenceCoverageRecord.__module__ = "maxcover.contracts"
ReferenceCensoringBiasRecord.__module__ = "maxcover.contracts"
ReferenceCutoffSensitivityRecord.__module__ = "maxcover.contracts"
