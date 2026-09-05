"""Private performance association record contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from ._contract_csv import (
    _parse_float,
    _required_int,
    _validate_csv_fields,
)


RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION = 1
RUNTIME_K_ASSOCIATION_SCHEMA_VERSION = 1
SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RuntimeSetCountAssociationRecord:
    """One P5.4 family-local completed-runtime versus set-count row."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "family",
        "algorithm_id",
        "algorithm",
        "predictor",
        "response",
        "repetition_unit",
        "case_count",
        "case_ids",
        "instance_count",
        "run_count",
        "completed_run_count",
        "timeout_count",
        "error_count",
        "incomplete_runtime_instance_count",
        "eligible_instance_count",
        "distinct_set_count",
        "mean_set_count",
        "mean_runtime_seconds",
        "set_count_sample_standard_deviation",
        "runtime_sample_standard_deviation_seconds",
        "pearson_correlation",
        "ols_slope_seconds_per_set",
        "ols_intercept_seconds",
        "association_status",
        "schema_version",
    )

    config_hash: str
    family: str
    algorithm_id: str
    algorithm: str
    predictor: str
    response: str
    repetition_unit: str
    case_count: int
    case_ids: tuple[str, ...]
    instance_count: int
    run_count: int
    completed_run_count: int
    timeout_count: int
    error_count: int
    incomplete_runtime_instance_count: int
    eligible_instance_count: int
    distinct_set_count: int
    mean_set_count: float | None
    mean_runtime_seconds: float | None
    set_count_sample_standard_deviation: float | None
    runtime_sample_standard_deviation_seconds: float | None
    pearson_correlation: float | None
    ols_slope_seconds_per_set: float | None
    ols_intercept_seconds: float | None
    association_status: str
    schema_version: int = RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported runtime-set-count association schema version "
                f"{self.schema_version!r}; expected "
                f"{RUNTIME_SET_COUNT_ASSOCIATION_SCHEMA_VERSION}"
            )
        for name in ("config_hash", "family", "algorithm_id", "algorithm"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.predictor != "set_count":
            raise ValueError("predictor must be 'set_count'")
        if self.response != "mean_completed_runtime_seconds":
            raise ValueError(
                "response must be 'mean_completed_runtime_seconds'"
            )
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.association_status not in {
            "no_samples",
            "insufficient_samples",
            "constant_set_count",
            "constant_runtime",
            "estimable",
        }:
            raise ValueError(
                "association_status must be no_samples, insufficient_samples, "
                "constant_set_count, constant_runtime, or estimable"
            )

        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if any(not isinstance(value, str) or not value for value in self.case_ids):
            raise ValueError("case_ids must contain non-empty strings")
        if tuple(sorted(set(self.case_ids))) != self.case_ids:
            raise ValueError("case_ids must be sorted and unique")

        count_names = (
            "case_count",
            "instance_count",
            "run_count",
            "completed_run_count",
            "timeout_count",
            "error_count",
            "incomplete_runtime_instance_count",
            "eligible_instance_count",
            "distinct_set_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.case_count <= 0 or self.case_count != len(self.case_ids):
            raise ValueError("case_count must equal the positive case_ids length")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if self.run_count < self.instance_count:
            raise ValueError("run_count cannot be smaller than instance_count")
        if (
            self.completed_run_count + self.timeout_count + self.error_count
            != self.run_count
        ):
            raise ValueError("run status counts must partition run_count")
        if (
            self.eligible_instance_count
            + self.incomplete_runtime_instance_count
            != self.instance_count
        ):
            raise ValueError(
                "eligible and incomplete instances must partition instance_count"
            )
        if self.eligible_instance_count > self.completed_run_count:
            raise ValueError(
                "eligible instances require at least one completed run"
            )
        if self.distinct_set_count > self.eligible_instance_count:
            raise ValueError(
                "distinct_set_count cannot exceed eligible_instance_count"
            )

        statistics = (
            self.mean_set_count,
            self.mean_runtime_seconds,
            self.set_count_sample_standard_deviation,
            self.runtime_sample_standard_deviation_seconds,
            self.pearson_correlation,
            self.ols_slope_seconds_per_set,
            self.ols_intercept_seconds,
        )
        if self.eligible_instance_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError("zero samples require blank association statistics")
            if self.distinct_set_count != 0:
                raise ValueError("zero samples require zero distinct set counts")
            if self.association_status != "no_samples":
                raise ValueError("zero samples require no_samples status")
            return

        mean_set_count = self.mean_set_count
        mean_runtime = self.mean_runtime_seconds
        if (
            mean_set_count is None
            or not math.isfinite(mean_set_count)
            or mean_set_count <= 0
        ):
            raise ValueError("positive samples require a positive mean set count")
        if (
            mean_runtime is None
            or not math.isfinite(mean_runtime)
            or mean_runtime < 0
        ):
            raise ValueError(
                "positive samples require a non-negative mean runtime"
            )
        if self.distinct_set_count <= 0:
            raise ValueError("positive samples require a distinct set count")

        remaining = statistics[2:]
        if self.eligible_instance_count == 1:
            if any(value is not None for value in remaining):
                raise ValueError(
                    "a singleton sample requires blank dispersion and "
                    "association fields"
                )
            if self.distinct_set_count != 1:
                raise ValueError("a singleton sample has one distinct set count")
            if self.association_status != "insufficient_samples":
                raise ValueError(
                    "a singleton sample requires insufficient_samples status"
                )
            return

        set_count_sd = self.set_count_sample_standard_deviation
        runtime_sd = self.runtime_sample_standard_deviation_seconds
        if (
            set_count_sd is None
            or not math.isfinite(set_count_sd)
            or set_count_sd < 0
        ):
            raise ValueError("set-count sample SD must be finite and non-negative")
        if runtime_sd is None or not math.isfinite(runtime_sd) or runtime_sd < 0:
            raise ValueError("runtime sample SD must be finite and non-negative")
        if set_count_sd == 0:
            if self.distinct_set_count != 1:
                raise ValueError(
                    "zero set-count variation requires one distinct set count"
                )
            if any(
                value is not None
                for value in (
                    self.pearson_correlation,
                    self.ols_slope_seconds_per_set,
                    self.ols_intercept_seconds,
                )
            ):
                raise ValueError(
                    "constant set count requires blank correlation and OLS"
                )
            if self.association_status != "constant_set_count":
                raise ValueError(
                    "zero set-count variation requires constant_set_count"
                )
            return
        if self.distinct_set_count < 2:
            raise ValueError(
                "positive set-count variation requires multiple values"
            )
        if runtime_sd == 0:
            if self.pearson_correlation is not None:
                raise ValueError("constant runtime requires blank correlation")
            if self.ols_slope_seconds_per_set != 0:
                raise ValueError("constant runtime requires zero OLS slope")
            if self.ols_intercept_seconds is None or not math.isclose(
                self.ols_intercept_seconds,
                mean_runtime,
                abs_tol=5e-10,
            ):
                raise ValueError(
                    "constant runtime requires intercept equal to mean runtime"
                )
            if self.association_status != "constant_runtime":
                raise ValueError(
                    "zero runtime variation requires constant_runtime"
                )
            return

        correlation = self.pearson_correlation
        if correlation is None or not math.isfinite(correlation):
            raise ValueError("estimable association requires finite correlation")
        if not -1 <= correlation <= 1:
            raise ValueError("pearson_correlation must be between -1 and 1")
        if (
            self.ols_slope_seconds_per_set is None
            or not math.isfinite(self.ols_slope_seconds_per_set)
        ):
            raise ValueError("estimable association requires finite OLS slope")
        if (
            self.ols_intercept_seconds is None
            or not math.isfinite(self.ols_intercept_seconds)
        ):
            raise ValueError("estimable association requires finite OLS intercept")
        if self.association_status != "estimable":
            raise ValueError("positive variation on both axes requires estimable")

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "predictor": self.predictor,
            "response": self.response,
            "repetition_unit": self.repetition_unit,
            "case_count": self.case_count,
            "case_ids": json.dumps(
                list(self.case_ids), ensure_ascii=False, separators=(",", ":")
            ),
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "completed_run_count": self.completed_run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "incomplete_runtime_instance_count": (
                self.incomplete_runtime_instance_count
            ),
            "eligible_instance_count": self.eligible_instance_count,
            "distinct_set_count": self.distinct_set_count,
            "mean_set_count": self._format_optional(self.mean_set_count),
            "mean_runtime_seconds": self._format_optional(
                self.mean_runtime_seconds
            ),
            "set_count_sample_standard_deviation": self._format_optional(
                self.set_count_sample_standard_deviation
            ),
            "runtime_sample_standard_deviation_seconds": self._format_optional(
                self.runtime_sample_standard_deviation_seconds
            ),
            "pearson_correlation": self._format_optional(
                self.pearson_correlation
            ),
            "ols_slope_seconds_per_set": self._format_optional(
                self.ols_slope_seconds_per_set
            ),
            "ols_intercept_seconds": self._format_optional(
                self.ols_intercept_seconds
            ),
            "association_status": self.association_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> RuntimeSetCountAssociationRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_case_ids = json.loads(row["case_ids"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("case_ids must encode a JSON array") from error
        if not isinstance(raw_case_ids, list):
            raise ValueError("case_ids must encode a JSON array")

        def integer(name: str) -> int:
            return _required_int(row[name], name)

        def optional_float(name: str) -> float | None:
            return _parse_float(row[name], name, optional=True)

        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            predictor=row["predictor"],
            response=row["response"],
            repetition_unit=row["repetition_unit"],
            case_count=integer("case_count"),
            case_ids=tuple(raw_case_ids),
            instance_count=integer("instance_count"),
            run_count=integer("run_count"),
            completed_run_count=integer("completed_run_count"),
            timeout_count=integer("timeout_count"),
            error_count=integer("error_count"),
            incomplete_runtime_instance_count=integer(
                "incomplete_runtime_instance_count"
            ),
            eligible_instance_count=integer("eligible_instance_count"),
            distinct_set_count=integer("distinct_set_count"),
            mean_set_count=optional_float("mean_set_count"),
            mean_runtime_seconds=optional_float("mean_runtime_seconds"),
            set_count_sample_standard_deviation=optional_float(
                "set_count_sample_standard_deviation"
            ),
            runtime_sample_standard_deviation_seconds=optional_float(
                "runtime_sample_standard_deviation_seconds"
            ),
            pearson_correlation=optional_float("pearson_correlation"),
            ols_slope_seconds_per_set=optional_float(
                "ols_slope_seconds_per_set"
            ),
            ols_intercept_seconds=optional_float("ols_intercept_seconds"),
            association_status=row["association_status"],
            schema_version=integer("schema_version"),
        )


@dataclass(frozen=True, slots=True)
class RuntimeKAssociationRecord:
    """One P5.4 family-local completed-runtime versus selection-budget row."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "family",
        "algorithm_id",
        "algorithm",
        "predictor",
        "response",
        "repetition_unit",
        "case_count",
        "case_ids",
        "instance_count",
        "run_count",
        "completed_run_count",
        "timeout_count",
        "error_count",
        "incomplete_runtime_instance_count",
        "eligible_instance_count",
        "distinct_k_count",
        "mean_k",
        "mean_runtime_seconds",
        "k_sample_standard_deviation",
        "runtime_sample_standard_deviation_seconds",
        "pearson_correlation",
        "ols_slope_seconds_per_budget_unit",
        "ols_intercept_seconds",
        "association_status",
        "schema_version",
    )

    config_hash: str
    family: str
    algorithm_id: str
    algorithm: str
    predictor: str
    response: str
    repetition_unit: str
    case_count: int
    case_ids: tuple[str, ...]
    instance_count: int
    run_count: int
    completed_run_count: int
    timeout_count: int
    error_count: int
    incomplete_runtime_instance_count: int
    eligible_instance_count: int
    distinct_k_count: int
    mean_k: float | None
    mean_runtime_seconds: float | None
    k_sample_standard_deviation: float | None
    runtime_sample_standard_deviation_seconds: float | None
    pearson_correlation: float | None
    ols_slope_seconds_per_budget_unit: float | None
    ols_intercept_seconds: float | None
    association_status: str
    schema_version: int = RUNTIME_K_ASSOCIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_K_ASSOCIATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported runtime-k association schema version "
                f"{self.schema_version!r}; expected "
                f"{RUNTIME_K_ASSOCIATION_SCHEMA_VERSION}"
            )
        if self.predictor != "k":
            raise ValueError("predictor must be 'k'")
        status = (
            "constant_set_count"
            if self.association_status == "constant_k"
            else self.association_status
        )
        RuntimeSetCountAssociationRecord(
            config_hash=self.config_hash,
            family=self.family,
            algorithm_id=self.algorithm_id,
            algorithm=self.algorithm,
            predictor="set_count",
            response=self.response,
            repetition_unit=self.repetition_unit,
            case_count=self.case_count,
            case_ids=self.case_ids,
            instance_count=self.instance_count,
            run_count=self.run_count,
            completed_run_count=self.completed_run_count,
            timeout_count=self.timeout_count,
            error_count=self.error_count,
            incomplete_runtime_instance_count=(
                self.incomplete_runtime_instance_count
            ),
            eligible_instance_count=self.eligible_instance_count,
            distinct_set_count=self.distinct_k_count,
            mean_set_count=self.mean_k,
            mean_runtime_seconds=self.mean_runtime_seconds,
            set_count_sample_standard_deviation=(
                self.k_sample_standard_deviation
            ),
            runtime_sample_standard_deviation_seconds=(
                self.runtime_sample_standard_deviation_seconds
            ),
            pearson_correlation=self.pearson_correlation,
            ols_slope_seconds_per_set=(
                self.ols_slope_seconds_per_budget_unit
            ),
            ols_intercept_seconds=self.ols_intercept_seconds,
            association_status=status,
        )
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if self.association_status not in {
            "no_samples",
            "insufficient_samples",
            "constant_k",
            "constant_runtime",
            "estimable",
        }:
            raise ValueError(
                "association_status must be no_samples, insufficient_samples, "
                "constant_k, constant_runtime, or estimable"
            )

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "predictor": self.predictor,
            "response": self.response,
            "repetition_unit": self.repetition_unit,
            "case_count": self.case_count,
            "case_ids": json.dumps(
                list(self.case_ids), ensure_ascii=False, separators=(",", ":")
            ),
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "completed_run_count": self.completed_run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "incomplete_runtime_instance_count": (
                self.incomplete_runtime_instance_count
            ),
            "eligible_instance_count": self.eligible_instance_count,
            "distinct_k_count": self.distinct_k_count,
            "mean_k": self._format_optional(self.mean_k),
            "mean_runtime_seconds": self._format_optional(
                self.mean_runtime_seconds
            ),
            "k_sample_standard_deviation": self._format_optional(
                self.k_sample_standard_deviation
            ),
            "runtime_sample_standard_deviation_seconds": self._format_optional(
                self.runtime_sample_standard_deviation_seconds
            ),
            "pearson_correlation": self._format_optional(
                self.pearson_correlation
            ),
            "ols_slope_seconds_per_budget_unit": self._format_optional(
                self.ols_slope_seconds_per_budget_unit
            ),
            "ols_intercept_seconds": self._format_optional(
                self.ols_intercept_seconds
            ),
            "association_status": self.association_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> RuntimeKAssociationRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_case_ids = json.loads(row["case_ids"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("case_ids must encode a JSON array") from error
        if not isinstance(raw_case_ids, list):
            raise ValueError("case_ids must encode a JSON array")

        def integer(name: str) -> int:
            return _required_int(row[name], name)

        def optional_float(name: str) -> float | None:
            return _parse_float(row[name], name, optional=True)

        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            predictor=row["predictor"],
            response=row["response"],
            repetition_unit=row["repetition_unit"],
            case_count=integer("case_count"),
            case_ids=tuple(raw_case_ids),
            instance_count=integer("instance_count"),
            run_count=integer("run_count"),
            completed_run_count=integer("completed_run_count"),
            timeout_count=integer("timeout_count"),
            error_count=integer("error_count"),
            incomplete_runtime_instance_count=integer(
                "incomplete_runtime_instance_count"
            ),
            eligible_instance_count=integer("eligible_instance_count"),
            distinct_k_count=integer("distinct_k_count"),
            mean_k=optional_float("mean_k"),
            mean_runtime_seconds=optional_float("mean_runtime_seconds"),
            k_sample_standard_deviation=optional_float(
                "k_sample_standard_deviation"
            ),
            runtime_sample_standard_deviation_seconds=optional_float(
                "runtime_sample_standard_deviation_seconds"
            ),
            pearson_correlation=optional_float("pearson_correlation"),
            ols_slope_seconds_per_budget_unit=optional_float(
                "ols_slope_seconds_per_budget_unit"
            ),
            ols_intercept_seconds=optional_float("ols_intercept_seconds"),
            association_status=row["association_status"],
            schema_version=integer("schema_version"),
        )


@dataclass(frozen=True, slots=True)
class SearchNodesDominatedRatioAssociationRecord:
    """One P5.4 family-local BnB search-nodes association row."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "family",
        "algorithm_id",
        "algorithm",
        "predictor",
        "response",
        "repetition_unit",
        "case_count",
        "case_ids",
        "instance_count",
        "run_count",
        "optimal_run_count",
        "timeout_count",
        "error_count",
        "eligible_instance_count",
        "distinct_dominated_ratio_count",
        "mean_dominated_set_ratio",
        "mean_search_nodes",
        "dominated_ratio_sample_standard_deviation",
        "search_nodes_sample_standard_deviation",
        "pearson_correlation",
        "ols_slope_nodes_per_ratio_unit",
        "ols_intercept_nodes",
        "association_status",
        "schema_version",
    )

    config_hash: str
    family: str
    algorithm_id: str
    algorithm: str
    predictor: str
    response: str
    repetition_unit: str
    case_count: int
    case_ids: tuple[str, ...]
    instance_count: int
    run_count: int
    optimal_run_count: int
    timeout_count: int
    error_count: int
    eligible_instance_count: int
    distinct_dominated_ratio_count: int
    mean_dominated_set_ratio: float | None
    mean_search_nodes: float | None
    dominated_ratio_sample_standard_deviation: float | None
    search_nodes_sample_standard_deviation: float | None
    pearson_correlation: float | None
    ols_slope_nodes_per_ratio_unit: float | None
    ols_intercept_nodes: float | None
    association_status: str
    schema_version: int = SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported search-nodes dominated-ratio association schema "
                f"version {self.schema_version!r}; expected "
                f"{SEARCH_NODES_DOMINATED_RATIO_ASSOCIATION_SCHEMA_VERSION}"
            )
        for name in ("config_hash", "family", "algorithm_id", "algorithm"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.algorithm not in {
            "branch_and_bound",
            "branch_and_bound_enhanced",
        }:
            raise ValueError("algorithm must be an exact Branch-and-Bound variant")
        if self.predictor != "dominated_set_ratio":
            raise ValueError("predictor must be 'dominated_set_ratio'")
        if self.response != "completed_search_nodes":
            raise ValueError("response must be 'completed_search_nodes'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.association_status not in {
            "no_samples",
            "insufficient_samples",
            "constant_dominated_ratio",
            "constant_nodes",
            "estimable",
        }:
            raise ValueError(
                "association_status must be no_samples, insufficient_samples, "
                "constant_dominated_ratio, constant_nodes, or estimable"
            )

        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        if any(not isinstance(value, str) or not value for value in self.case_ids):
            raise ValueError("case_ids must contain non-empty strings")
        if tuple(sorted(set(self.case_ids))) != self.case_ids:
            raise ValueError("case_ids must be sorted and unique")

        count_names = (
            "case_count",
            "instance_count",
            "run_count",
            "optimal_run_count",
            "timeout_count",
            "error_count",
            "eligible_instance_count",
            "distinct_dominated_ratio_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.case_count <= 0 or self.case_count != len(self.case_ids):
            raise ValueError("case_count must equal the positive case_ids length")
        if self.instance_count <= 0 or self.run_count != self.instance_count:
            raise ValueError("run_count must equal positive instance_count")
        if (
            self.optimal_run_count + self.timeout_count + self.error_count
            != self.run_count
        ):
            raise ValueError("run status counts must partition run_count")
        if self.eligible_instance_count != self.optimal_run_count:
            raise ValueError("eligible_instance_count must equal optimal_run_count")
        if self.distinct_dominated_ratio_count > self.eligible_instance_count:
            raise ValueError(
                "distinct_dominated_ratio_count cannot exceed eligible samples"
            )

        statistics = (
            self.mean_dominated_set_ratio,
            self.mean_search_nodes,
            self.dominated_ratio_sample_standard_deviation,
            self.search_nodes_sample_standard_deviation,
            self.pearson_correlation,
            self.ols_slope_nodes_per_ratio_unit,
            self.ols_intercept_nodes,
        )
        if self.eligible_instance_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError("zero samples require blank association statistics")
            if self.distinct_dominated_ratio_count != 0:
                raise ValueError("zero samples require zero distinct ratios")
            if self.association_status != "no_samples":
                raise ValueError("zero samples require no_samples status")
            return

        mean_ratio = self.mean_dominated_set_ratio
        mean_nodes = self.mean_search_nodes
        if (
            mean_ratio is None
            or not math.isfinite(mean_ratio)
            or not 0 <= mean_ratio <= 1
        ):
            raise ValueError("mean dominated-set ratio must be between 0 and 1")
        if mean_nodes is None or not math.isfinite(mean_nodes) or mean_nodes < 0:
            raise ValueError("mean search nodes must be finite and non-negative")
        if self.distinct_dominated_ratio_count <= 0:
            raise ValueError("positive samples require a distinct ratio count")

        dispersion = statistics[2:]
        if self.eligible_instance_count == 1:
            if any(value is not None for value in dispersion):
                raise ValueError(
                    "a singleton sample requires blank dispersion and "
                    "association fields"
                )
            if self.distinct_dominated_ratio_count != 1:
                raise ValueError("a singleton sample has one distinct ratio")
            if self.association_status != "insufficient_samples":
                raise ValueError(
                    "a singleton sample requires insufficient_samples status"
                )
            return

        ratio_sd = self.dominated_ratio_sample_standard_deviation
        node_sd = self.search_nodes_sample_standard_deviation
        if ratio_sd is None or not math.isfinite(ratio_sd) or ratio_sd < 0:
            raise ValueError("dominated-ratio sample SD must be non-negative")
        if node_sd is None or not math.isfinite(node_sd) or node_sd < 0:
            raise ValueError("search-node sample SD must be non-negative")
        if ratio_sd == 0:
            if self.distinct_dominated_ratio_count != 1:
                raise ValueError("zero ratio variation requires one distinct ratio")
            if any(
                value is not None
                for value in (
                    self.pearson_correlation,
                    self.ols_slope_nodes_per_ratio_unit,
                    self.ols_intercept_nodes,
                )
            ):
                raise ValueError(
                    "constant dominated ratio requires blank correlation and OLS"
                )
            if self.association_status != "constant_dominated_ratio":
                raise ValueError(
                    "zero ratio variation requires constant_dominated_ratio"
                )
            return
        if self.distinct_dominated_ratio_count < 2:
            raise ValueError("positive ratio variation requires multiple values")
        if node_sd == 0:
            if self.pearson_correlation is not None:
                raise ValueError("constant nodes require blank correlation")
            if self.ols_slope_nodes_per_ratio_unit != 0:
                raise ValueError("constant nodes require zero OLS slope")
            if self.ols_intercept_nodes is None or not math.isclose(
                self.ols_intercept_nodes, mean_nodes, abs_tol=5e-10
            ):
                raise ValueError(
                    "constant nodes require intercept equal to mean nodes"
                )
            if self.association_status != "constant_nodes":
                raise ValueError("zero node variation requires constant_nodes")
            return

        correlation = self.pearson_correlation
        if correlation is None or not math.isfinite(correlation):
            raise ValueError("estimable association requires finite correlation")
        if not -1 <= correlation <= 1:
            raise ValueError("pearson_correlation must be between -1 and 1")
        if (
            self.ols_slope_nodes_per_ratio_unit is None
            or not math.isfinite(self.ols_slope_nodes_per_ratio_unit)
        ):
            raise ValueError("estimable association requires finite OLS slope")
        if self.ols_intercept_nodes is None or not math.isfinite(
            self.ols_intercept_nodes
        ):
            raise ValueError("estimable association requires finite OLS intercept")
        if self.association_status != "estimable":
            raise ValueError("positive variation on both axes requires estimable")

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "predictor": self.predictor,
            "response": self.response,
            "repetition_unit": self.repetition_unit,
            "case_count": self.case_count,
            "case_ids": json.dumps(
                list(self.case_ids), ensure_ascii=False, separators=(",", ":")
            ),
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "optimal_run_count": self.optimal_run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "eligible_instance_count": self.eligible_instance_count,
            "distinct_dominated_ratio_count": self.distinct_dominated_ratio_count,
            "mean_dominated_set_ratio": self._format_optional(
                self.mean_dominated_set_ratio
            ),
            "mean_search_nodes": self._format_optional(self.mean_search_nodes),
            "dominated_ratio_sample_standard_deviation": self._format_optional(
                self.dominated_ratio_sample_standard_deviation
            ),
            "search_nodes_sample_standard_deviation": self._format_optional(
                self.search_nodes_sample_standard_deviation
            ),
            "pearson_correlation": self._format_optional(
                self.pearson_correlation
            ),
            "ols_slope_nodes_per_ratio_unit": self._format_optional(
                self.ols_slope_nodes_per_ratio_unit
            ),
            "ols_intercept_nodes": self._format_optional(
                self.ols_intercept_nodes
            ),
            "association_status": self.association_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> SearchNodesDominatedRatioAssociationRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_case_ids = json.loads(row["case_ids"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("case_ids must encode a JSON array") from error
        if not isinstance(raw_case_ids, list):
            raise ValueError("case_ids must encode a JSON array")

        def integer(name: str) -> int:
            return _required_int(row[name], name)

        def optional_float(name: str) -> float | None:
            return _parse_float(row[name], name, optional=True)

        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            predictor=row["predictor"],
            response=row["response"],
            repetition_unit=row["repetition_unit"],
            case_count=integer("case_count"),
            case_ids=tuple(raw_case_ids),
            instance_count=integer("instance_count"),
            run_count=integer("run_count"),
            optimal_run_count=integer("optimal_run_count"),
            timeout_count=integer("timeout_count"),
            error_count=integer("error_count"),
            eligible_instance_count=integer("eligible_instance_count"),
            distinct_dominated_ratio_count=integer(
                "distinct_dominated_ratio_count"
            ),
            mean_dominated_set_ratio=optional_float(
                "mean_dominated_set_ratio"
            ),
            mean_search_nodes=optional_float("mean_search_nodes"),
            dominated_ratio_sample_standard_deviation=optional_float(
                "dominated_ratio_sample_standard_deviation"
            ),
            search_nodes_sample_standard_deviation=optional_float(
                "search_nodes_sample_standard_deviation"
            ),
            pearson_correlation=optional_float("pearson_correlation"),
            ols_slope_nodes_per_ratio_unit=optional_float(
                "ols_slope_nodes_per_ratio_unit"
            ),
            ols_intercept_nodes=optional_float("ols_intercept_nodes"),
            association_status=row["association_status"],
            schema_version=integer("schema_version"),
        )


RuntimeSetCountAssociationRecord.__module__ = "maxcover.contracts"
RuntimeKAssociationRecord.__module__ = "maxcover.contracts"
SearchNodesDominatedRatioAssociationRecord.__module__ = "maxcover.contracts"
