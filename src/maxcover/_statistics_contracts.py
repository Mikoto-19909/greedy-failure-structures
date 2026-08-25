"""Private non-association statistical record contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from ._contract_csv import (
    _parse_float,
    _required_float,
    _required_int,
    _validate_csv_fields,
)


DESCRIPTIVE_STATISTICS_SCHEMA_VERSION = 1
CONFIDENCE_INTERVAL_SCHEMA_VERSION = 1
CENSORED_RUNTIME_SCHEMA_VERSION = 1
AUTOMATIC_CONCLUSION_CONTRACT_SCHEMA_VERSION = 1
AUTOMATIC_CONCLUSION_MINIMUM_SAMPLE_COUNT = 10
GREEDY_FAILURE_SCHEMA_VERSION = 1
LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION = 1
LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION = 1
HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION = 1
BNB_NODE_REDUCTION_SCHEMA_VERSION = 1
QUALITY_RUNTIME_PARETO_SCHEMA_VERSION = 1

DESCRIPTIVE_STATISTICS_METRICS = frozenset(
    {"coverage", "optimality_gap", "runtime_seconds"}
)

@dataclass(frozen=True, slots=True)
class DescriptiveStatisticsRecord:
    """One P5 descriptive-statistics row for a metric and algorithm variant."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "algorithm_id",
        "algorithm",
        "metric",
        "repetition_unit",
        "instance_count",
        "sample_count",
        "run_count",
        "timeout_count",
        "timeout_rate",
        "error_count",
        "error_rate",
        "valid_exact_reference_count",
        "exact_reference_rate",
        "mean",
        "median",
        "standard_deviation",
        "minimum",
        "p25",
        "p75",
        "p95",
        "maximum",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    metric: str
    repetition_unit: str
    instance_count: int
    sample_count: int
    run_count: int
    timeout_count: int
    timeout_rate: float
    error_count: int
    error_rate: float
    valid_exact_reference_count: int
    exact_reference_rate: float
    mean: float | None
    median: float | None
    standard_deviation: float | None
    minimum: float | None
    p25: float | None
    p75: float | None
    p95: float | None
    maximum: float | None
    schema_version: int = DESCRIPTIVE_STATISTICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESCRIPTIVE_STATISTICS_SCHEMA_VERSION:
            raise ValueError(
                "unsupported descriptive-statistics schema version "
                f"{self.schema_version!r}; "
                f"expected {DESCRIPTIVE_STATISTICS_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.metric not in DESCRIPTIVE_STATISTICS_METRICS:
            raise ValueError(
                f"metric must be one of {sorted(DESCRIPTIVE_STATISTICS_METRICS)!r}"
            )
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")

        for name in (
            "instance_count",
            "sample_count",
            "run_count",
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0 or self.run_count <= 0:
            raise ValueError("instance_count and run_count must be positive")
        if self.run_count < self.instance_count:
            raise ValueError("run_count cannot be smaller than instance_count")
        if self.sample_count > self.instance_count:
            raise ValueError("sample_count cannot exceed instance_count")
        if self.valid_exact_reference_count > self.instance_count:
            raise ValueError(
                "valid_exact_reference_count cannot exceed instance_count"
            )
        if (
            self.metric == "optimality_gap"
            and self.sample_count > self.valid_exact_reference_count
        ):
            raise ValueError(
                "optimality_gap sample_count cannot exceed "
                "valid_exact_reference_count"
            )
        if self.timeout_count + self.error_count > self.run_count:
            raise ValueError("timeout_count plus error_count cannot exceed run_count")

        for name, count in (
            ("timeout_rate", self.timeout_count),
            ("error_rate", self.error_count),
        ):
            rate = getattr(self, name)
            if not math.isfinite(rate) or not 0 <= rate <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")
            if not math.isclose(rate, count / self.run_count, abs_tol=5e-10):
                raise ValueError(f"{name} does not match its count and run_count")
        if (
            not math.isfinite(self.exact_reference_rate)
            or not 0 <= self.exact_reference_rate <= 1
        ):
            raise ValueError(
                "exact_reference_rate must be finite and between 0 and 1"
            )
        if not math.isclose(
            self.exact_reference_rate,
            self.valid_exact_reference_count / self.instance_count,
            abs_tol=5e-10,
        ):
            raise ValueError(
                "exact_reference_rate does not match its count and instance_count"
            )

        statistic_names = (
            "mean",
            "median",
            "standard_deviation",
            "minimum",
            "p25",
            "p75",
            "p95",
            "maximum",
        )
        if self.sample_count == 0:
            if any(getattr(self, name) is not None for name in statistic_names):
                raise ValueError("empty metric samples require blank statistics")
            return

        required = (
            "mean",
            "median",
            "minimum",
            "p25",
            "p75",
            "p95",
            "maximum",
        )
        if any(getattr(self, name) is None for name in required):
            raise ValueError("non-empty metric samples require all location statistics")
        if self.sample_count == 1:
            if self.standard_deviation is not None:
                raise ValueError(
                    "a singleton sample has no sample standard deviation"
                )
            singleton_values = tuple(getattr(self, name) for name in required)
            assert all(value is not None for value in singleton_values)
            if not all(
                value == singleton_values[0]
                for value in singleton_values[1:]
            ):
                raise ValueError(
                    "a singleton sample requires identical location statistics"
                )
        elif self.standard_deviation is None:
            raise ValueError(
                "two or more samples require a sample standard deviation"
            )

        present = [
            value
            for value in (getattr(self, name) for name in statistic_names)
            if value is not None
        ]
        if any(not math.isfinite(value) for value in present):
            raise ValueError("statistics must be finite when present")
        if self.standard_deviation is not None and self.standard_deviation < 0:
            raise ValueError("standard_deviation must be non-negative")
        assert self.minimum is not None
        assert self.p25 is not None
        assert self.median is not None
        assert self.p75 is not None
        assert self.p95 is not None
        assert self.maximum is not None
        assert self.mean is not None
        ordered = (
            self.minimum,
            self.p25,
            self.median,
            self.p75,
            self.p95,
            self.maximum,
        )
        if any(left > right for left, right in zip(ordered, ordered[1:])):
            raise ValueError("quantile statistics must be monotonically ordered")
        if (
            self.mean < self.minimum
            and not math.isclose(self.mean, self.minimum)
        ) or (
            self.mean > self.maximum
            and not math.isclose(self.mean, self.maximum)
        ):
            raise ValueError("mean must be between minimum and maximum")
        if self.metric in {"coverage", "runtime_seconds"} and self.minimum < 0:
            raise ValueError(f"{self.metric} statistics must be non-negative")
        if self.metric == "optimality_gap" and (
            self.minimum < 0 or self.maximum > 1
        ):
            raise ValueError("optimality_gap statistics must be between 0 and 1")

    def to_csv_row(self) -> dict[str, object]:
        def optional(value: float | None) -> str:
            return "" if value is None else f"{value:.10f}"

        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "metric": self.metric,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "sample_count": self.sample_count,
            "run_count": self.run_count,
            "timeout_count": self.timeout_count,
            "timeout_rate": f"{self.timeout_rate:.10f}",
            "error_count": self.error_count,
            "error_rate": f"{self.error_rate:.10f}",
            "valid_exact_reference_count": self.valid_exact_reference_count,
            "exact_reference_rate": f"{self.exact_reference_rate:.10f}",
            "mean": optional(self.mean),
            "median": optional(self.median),
            "standard_deviation": optional(self.standard_deviation),
            "minimum": optional(self.minimum),
            "p25": optional(self.p25),
            "p75": optional(self.p75),
            "p95": optional(self.p95),
            "maximum": optional(self.maximum),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> DescriptiveStatisticsRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        schema_version = _required_int(row["schema_version"], "schema_version")
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            metric=row["metric"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            sample_count=_required_int(row["sample_count"], "sample_count"),
            run_count=_required_int(row["run_count"], "run_count"),
            timeout_count=_required_int(row["timeout_count"], "timeout_count"),
            timeout_rate=_required_float(row["timeout_rate"], "timeout_rate"),
            error_count=_required_int(row["error_count"], "error_count"),
            error_rate=_required_float(row["error_rate"], "error_rate"),
            valid_exact_reference_count=_required_int(
                row["valid_exact_reference_count"],
                "valid_exact_reference_count",
            ),
            exact_reference_rate=_required_float(
                row["exact_reference_rate"], "exact_reference_rate"
            ),
            mean=_parse_float(row["mean"], "mean", optional=True),
            median=_parse_float(row["median"], "median", optional=True),
            standard_deviation=_parse_float(
                row["standard_deviation"],
                "standard_deviation",
                optional=True,
            ),
            minimum=_parse_float(row["minimum"], "minimum", optional=True),
            p25=_parse_float(row["p25"], "p25", optional=True),
            p75=_parse_float(row["p75"], "p75", optional=True),
            p95=_parse_float(row["p95"], "p95", optional=True),
            maximum=_parse_float(row["maximum"], "maximum", optional=True),
            schema_version=schema_version,
        )


@dataclass(frozen=True, slots=True)
class ConfidenceIntervalRecord:
    """One P5.3 two-sided confidence interval for an instance-level mean."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "algorithm_id",
        "algorithm",
        "metric",
        "estimand",
        "confidence_level",
        "method",
        "repetition_unit",
        "instance_count",
        "sample_count",
        "run_count",
        "timeout_count",
        "error_count",
        "valid_exact_reference_count",
        "degrees_of_freedom",
        "mean",
        "standard_error",
        "critical_value",
        "lower_bound",
        "upper_bound",
        "interval_status",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    metric: str
    estimand: str
    confidence_level: float
    method: str
    repetition_unit: str
    instance_count: int
    sample_count: int
    run_count: int
    timeout_count: int
    error_count: int
    valid_exact_reference_count: int
    degrees_of_freedom: int
    mean: float | None
    standard_error: float | None
    critical_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    interval_status: str
    schema_version: int = CONFIDENCE_INTERVAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONFIDENCE_INTERVAL_SCHEMA_VERSION:
            raise ValueError(
                "unsupported confidence-interval schema version "
                f"{self.schema_version!r}; "
                f"expected {CONFIDENCE_INTERVAL_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.metric not in DESCRIPTIVE_STATISTICS_METRICS:
            raise ValueError(
                f"metric must be one of {sorted(DESCRIPTIVE_STATISTICS_METRICS)!r}"
            )
        if self.estimand != "instance_mean":
            raise ValueError("estimand must be 'instance_mean'")
        if (
            not math.isfinite(self.confidence_level)
            or not math.isclose(self.confidence_level, 0.95, abs_tol=5e-10)
        ):
            raise ValueError("confidence_level must be 0.95")
        if self.method != "student_t_two_sided":
            raise ValueError("method must be 'student_t_two_sided'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.interval_status not in {
            "no_samples",
            "insufficient_samples",
            "estimable",
        }:
            raise ValueError(
                "interval_status must be no_samples, insufficient_samples, "
                "or estimable"
            )

        for name in (
            "instance_count",
            "sample_count",
            "run_count",
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
            "degrees_of_freedom",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0 or self.run_count <= 0:
            raise ValueError("instance_count and run_count must be positive")
        if self.run_count < self.instance_count:
            raise ValueError("run_count cannot be smaller than instance_count")
        if self.sample_count > self.instance_count:
            raise ValueError("sample_count cannot exceed instance_count")
        if self.timeout_count + self.error_count > self.run_count:
            raise ValueError("timeout_count plus error_count cannot exceed run_count")
        if self.valid_exact_reference_count > self.instance_count:
            raise ValueError(
                "valid_exact_reference_count cannot exceed instance_count"
            )
        if (
            self.metric == "optimality_gap"
            and self.sample_count > self.valid_exact_reference_count
        ):
            raise ValueError(
                "optimality_gap sample_count cannot exceed "
                "valid_exact_reference_count"
            )
        expected_degrees = max(self.sample_count - 1, 0)
        if self.degrees_of_freedom != expected_degrees:
            raise ValueError(
                "degrees_of_freedom must equal max(sample_count - 1, 0)"
            )

        interval_values = (
            self.standard_error,
            self.critical_value,
            self.lower_bound,
            self.upper_bound,
        )
        if self.sample_count == 0:
            if self.mean is not None or any(
                value is not None for value in interval_values
            ):
                raise ValueError(
                    "zero samples require blank mean and interval fields"
                )
            if self.interval_status != "no_samples":
                raise ValueError(
                    "zero samples require no_samples interval status"
                )
            return

        if self.mean is None or not math.isfinite(self.mean):
            raise ValueError("positive samples require a finite mean")
        if self.metric in {"coverage", "runtime_seconds"} and self.mean < 0:
            raise ValueError(f"{self.metric} mean must be non-negative")
        if self.metric == "optimality_gap" and not 0 <= self.mean <= 1:
            raise ValueError("optimality_gap mean must be between 0 and 1")

        if self.sample_count == 1:
            if any(value is not None for value in interval_values):
                raise ValueError(
                    "a singleton sample cannot define a confidence interval"
                )
            if self.interval_status != "insufficient_samples":
                raise ValueError(
                    "a singleton sample requires insufficient_samples status"
                )
            return

        if any(value is None for value in interval_values):
            raise ValueError(
                "two or more samples require all confidence-interval fields"
            )
        standard_error = self.standard_error
        critical_value = self.critical_value
        lower_bound = self.lower_bound
        upper_bound = self.upper_bound
        assert standard_error is not None
        assert critical_value is not None
        assert lower_bound is not None
        assert upper_bound is not None
        if not math.isfinite(standard_error) or standard_error < 0:
            raise ValueError("standard_error must be finite and non-negative")
        if not math.isfinite(critical_value) or critical_value <= 0:
            raise ValueError("critical_value must be finite and positive")
        if not math.isfinite(lower_bound) or not math.isfinite(upper_bound):
            raise ValueError("confidence bounds must be finite")
        if lower_bound > self.mean or upper_bound < self.mean:
            raise ValueError("confidence interval must contain its mean")
        if lower_bound > upper_bound:
            raise ValueError("lower_bound cannot exceed upper_bound")
        expected_margin = standard_error * critical_value
        if not math.isclose(
            self.mean - lower_bound,
            expected_margin,
            abs_tol=2e-9,
        ) or not math.isclose(
            upper_bound - self.mean,
            expected_margin,
            abs_tol=2e-9,
        ):
            raise ValueError(
                "confidence bounds must equal mean plus or minus "
                "critical_value times standard_error"
            )
        if self.interval_status != "estimable":
            raise ValueError(
                "two or more samples require estimable interval status"
            )

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "metric": self.metric,
            "estimand": self.estimand,
            "confidence_level": f"{self.confidence_level:.10f}",
            "method": self.method,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "sample_count": self.sample_count,
            "run_count": self.run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "valid_exact_reference_count": (
                self.valid_exact_reference_count
            ),
            "degrees_of_freedom": self.degrees_of_freedom,
            "mean": self._format_optional(self.mean),
            "standard_error": self._format_optional(self.standard_error),
            "critical_value": self._format_optional(self.critical_value),
            "lower_bound": self._format_optional(self.lower_bound),
            "upper_bound": self._format_optional(self.upper_bound),
            "interval_status": self.interval_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> ConfidenceIntervalRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            metric=row["metric"],
            estimand=row["estimand"],
            confidence_level=_required_float(
                row["confidence_level"], "confidence_level"
            ),
            method=row["method"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            sample_count=_required_int(row["sample_count"], "sample_count"),
            run_count=_required_int(row["run_count"], "run_count"),
            timeout_count=_required_int(row["timeout_count"], "timeout_count"),
            error_count=_required_int(row["error_count"], "error_count"),
            valid_exact_reference_count=_required_int(
                row["valid_exact_reference_count"],
                "valid_exact_reference_count",
            ),
            degrees_of_freedom=_required_int(
                row["degrees_of_freedom"], "degrees_of_freedom"
            ),
            mean=_parse_float(row["mean"], "mean", optional=True),
            standard_error=_parse_float(
                row["standard_error"], "standard_error", optional=True
            ),
            critical_value=_parse_float(
                row["critical_value"], "critical_value", optional=True
            ),
            lower_bound=_parse_float(
                row["lower_bound"], "lower_bound", optional=True
            ),
            upper_bound=_parse_float(
                row["upper_bound"], "upper_bound", optional=True
            ),
            interval_status=row["interval_status"],
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class CensoredRuntimeRecord:
    """One P5.3 right-censored runtime summary for an algorithm variant."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "algorithm_id",
        "algorithm",
        "repetition_unit",
        "instance_count",
        "run_count",
        "completed_run_count",
        "right_censored_run_count",
        "error_run_count",
        "completed_instance_count",
        "right_censored_instance_count",
        "error_affected_instance_count",
        "fully_right_censored_instance_count",
        "censoring_sample_count",
        "censoring_rate",
        "mean_censor_time_seconds",
        "median_censor_time_seconds",
        "minimum_censor_time_seconds",
        "maximum_censor_time_seconds",
        "censoring_status",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    repetition_unit: str
    instance_count: int
    run_count: int
    completed_run_count: int
    right_censored_run_count: int
    error_run_count: int
    completed_instance_count: int
    right_censored_instance_count: int
    error_affected_instance_count: int
    fully_right_censored_instance_count: int
    censoring_sample_count: int
    censoring_rate: float
    mean_censor_time_seconds: float | None
    median_censor_time_seconds: float | None
    minimum_censor_time_seconds: float | None
    maximum_censor_time_seconds: float | None
    censoring_status: str
    schema_version: int = CENSORED_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CENSORED_RUNTIME_SCHEMA_VERSION:
            raise ValueError(
                "unsupported censored-runtime schema version "
                f"{self.schema_version!r}; "
                f"expected {CENSORED_RUNTIME_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.censoring_status not in {
            "no_runtime_observations",
            "no_censoring",
            "right_censoring_present",
            "all_runtime_observations_right_censored",
        }:
            raise ValueError("unsupported censoring_status")

        count_names = (
            "instance_count",
            "run_count",
            "completed_run_count",
            "right_censored_run_count",
            "error_run_count",
            "completed_instance_count",
            "right_censored_instance_count",
            "error_affected_instance_count",
            "fully_right_censored_instance_count",
            "censoring_sample_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0 or self.run_count <= 0:
            raise ValueError("instance_count and run_count must be positive")
        if self.run_count < self.instance_count:
            raise ValueError("run_count cannot be smaller than instance_count")
        if (
            self.completed_run_count
            + self.right_censored_run_count
            + self.error_run_count
            != self.run_count
        ):
            raise ValueError("runtime status counts must partition run_count")
        for name in (
            "completed_instance_count",
            "right_censored_instance_count",
            "error_affected_instance_count",
            "fully_right_censored_instance_count",
        ):
            if getattr(self, name) > self.instance_count:
                raise ValueError(f"{name} cannot exceed instance_count")
        if self.completed_instance_count > self.completed_run_count:
            raise ValueError(
                "completed_instance_count cannot exceed completed_run_count"
            )
        if (self.completed_instance_count == 0) != (
            self.completed_run_count == 0
        ):
            raise ValueError(
                "completed instance and run counts must be zero together"
            )
        if (
            self.right_censored_instance_count
            > self.right_censored_run_count
        ):
            raise ValueError(
                "right_censored_instance_count cannot exceed "
                "right_censored_run_count"
            )
        if (self.right_censored_instance_count == 0) != (
            self.right_censored_run_count == 0
        ):
            raise ValueError(
                "right-censored instance and run counts must be zero together"
            )
        if self.error_affected_instance_count > self.error_run_count:
            raise ValueError(
                "error_affected_instance_count cannot exceed error_run_count"
            )
        if (self.error_affected_instance_count == 0) != (
            self.error_run_count == 0
        ):
            raise ValueError(
                "error-affected instance and run counts must be zero together"
            )
        if (
            self.fully_right_censored_instance_count
            > self.right_censored_instance_count
        ):
            raise ValueError(
                "fully right-censored instances require right censoring"
            )
        if (
            self.fully_right_censored_instance_count
            + self.completed_instance_count
            > self.instance_count
        ):
            raise ValueError(
                "fully right-censored and completed instance sets are disjoint"
            )
        if self.censoring_sample_count != self.right_censored_instance_count:
            raise ValueError(
                "censoring_sample_count must equal "
                "right_censored_instance_count"
            )
        if (
            not math.isfinite(self.censoring_rate)
            or not 0 <= self.censoring_rate <= 1
            or not math.isclose(
                self.censoring_rate,
                self.right_censored_instance_count / self.instance_count,
                abs_tol=5e-10,
            )
        ):
            raise ValueError(
                "censoring_rate must match right-censored instances"
            )

        statistics = (
            self.mean_censor_time_seconds,
            self.median_censor_time_seconds,
            self.minimum_censor_time_seconds,
            self.maximum_censor_time_seconds,
        )
        if self.censoring_sample_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError(
                    "zero censoring samples require blank time statistics"
                )
            expected_status = (
                "no_runtime_observations"
                if self.completed_run_count == 0
                else "no_censoring"
            )
            if self.censoring_status != expected_status:
                raise ValueError(
                    "zero censoring samples have an inconsistent status"
                )
            return

        if any(value is None for value in statistics):
            raise ValueError(
                "positive censoring samples require all time statistics"
            )
        assert self.mean_censor_time_seconds is not None
        assert self.median_censor_time_seconds is not None
        assert self.minimum_censor_time_seconds is not None
        assert self.maximum_censor_time_seconds is not None
        if any(
            not math.isfinite(value) or value < 0
            for value in statistics
            if value is not None
        ):
            raise ValueError(
                "censor-time statistics must be finite and non-negative"
            )
        if (
            self.minimum_censor_time_seconds
            > self.median_censor_time_seconds
            or self.median_censor_time_seconds
            > self.maximum_censor_time_seconds
            or self.mean_censor_time_seconds
            < self.minimum_censor_time_seconds
            or self.mean_censor_time_seconds
            > self.maximum_censor_time_seconds
        ):
            raise ValueError("censor-time statistics are inconsistently ordered")
        expected_status = (
            "all_runtime_observations_right_censored"
            if self.completed_run_count == 0
            else "right_censoring_present"
        )
        if self.censoring_status != expected_status:
            raise ValueError(
                "positive censoring samples have an inconsistent status"
            )

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "completed_run_count": self.completed_run_count,
            "right_censored_run_count": self.right_censored_run_count,
            "error_run_count": self.error_run_count,
            "completed_instance_count": self.completed_instance_count,
            "right_censored_instance_count": (
                self.right_censored_instance_count
            ),
            "error_affected_instance_count": (
                self.error_affected_instance_count
            ),
            "fully_right_censored_instance_count": (
                self.fully_right_censored_instance_count
            ),
            "censoring_sample_count": self.censoring_sample_count,
            "censoring_rate": f"{self.censoring_rate:.10f}",
            "mean_censor_time_seconds": self._format_optional(
                self.mean_censor_time_seconds
            ),
            "median_censor_time_seconds": self._format_optional(
                self.median_censor_time_seconds
            ),
            "minimum_censor_time_seconds": self._format_optional(
                self.minimum_censor_time_seconds
            ),
            "maximum_censor_time_seconds": self._format_optional(
                self.maximum_censor_time_seconds
            ),
            "censoring_status": self.censoring_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> CensoredRuntimeRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            run_count=_required_int(row["run_count"], "run_count"),
            completed_run_count=_required_int(
                row["completed_run_count"], "completed_run_count"
            ),
            right_censored_run_count=_required_int(
                row["right_censored_run_count"],
                "right_censored_run_count",
            ),
            error_run_count=_required_int(
                row["error_run_count"], "error_run_count"
            ),
            completed_instance_count=_required_int(
                row["completed_instance_count"],
                "completed_instance_count",
            ),
            right_censored_instance_count=_required_int(
                row["right_censored_instance_count"],
                "right_censored_instance_count",
            ),
            error_affected_instance_count=_required_int(
                row["error_affected_instance_count"],
                "error_affected_instance_count",
            ),
            fully_right_censored_instance_count=_required_int(
                row["fully_right_censored_instance_count"],
                "fully_right_censored_instance_count",
            ),
            censoring_sample_count=_required_int(
                row["censoring_sample_count"], "censoring_sample_count"
            ),
            censoring_rate=_required_float(
                row["censoring_rate"], "censoring_rate"
            ),
            mean_censor_time_seconds=_parse_float(
                row["mean_censor_time_seconds"],
                "mean_censor_time_seconds",
                optional=True,
            ),
            median_censor_time_seconds=_parse_float(
                row["median_censor_time_seconds"],
                "median_censor_time_seconds",
                optional=True,
            ),
            minimum_censor_time_seconds=_parse_float(
                row["minimum_censor_time_seconds"],
                "minimum_censor_time_seconds",
                optional=True,
            ),
            maximum_censor_time_seconds=_parse_float(
                row["maximum_censor_time_seconds"],
                "maximum_censor_time_seconds",
                optional=True,
            ),
            censoring_status=row["censoring_status"],
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class GreedyFailureRecord:
    """One P5.2 Greedy failure-rate row for a case and algorithm variant."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "algorithm_id",
        "algorithm",
        "repetition_unit",
        "instance_count",
        "run_count",
        "completed_count",
        "timeout_count",
        "timeout_rate",
        "error_count",
        "error_rate",
        "valid_exact_reference_count",
        "exact_reference_rate",
        "no_exact_reference_count",
        "eligible_pair_count",
        "eligible_pair_rate",
        "failure_count",
        "optimal_tie_count",
        "failure_rate",
        "optimal_tie_rate",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    repetition_unit: str
    instance_count: int
    run_count: int
    completed_count: int
    timeout_count: int
    timeout_rate: float
    error_count: int
    error_rate: float
    valid_exact_reference_count: int
    exact_reference_rate: float
    no_exact_reference_count: int
    eligible_pair_count: int
    eligible_pair_rate: float
    failure_count: int
    optimal_tie_count: int
    failure_rate: float | None
    optimal_tie_rate: float | None
    schema_version: int = GREEDY_FAILURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GREEDY_FAILURE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported Greedy-failure schema version "
                f"{self.schema_version!r}; "
                f"expected {GREEDY_FAILURE_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.algorithm != "greedy":
            raise ValueError("algorithm must be 'greedy'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")

        count_names = (
            "instance_count",
            "run_count",
            "completed_count",
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
            "no_exact_reference_count",
            "eligible_pair_count",
            "failure_count",
            "optimal_tie_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if self.run_count != self.instance_count:
            raise ValueError(
                "run_count must equal instance_count for deterministic Greedy"
            )
        if (
            self.completed_count + self.timeout_count + self.error_count
            != self.run_count
        ):
            raise ValueError(
                "completed_count, timeout_count, and error_count must partition "
                "run_count"
            )
        if (
            self.valid_exact_reference_count + self.no_exact_reference_count
            != self.instance_count
        ):
            raise ValueError(
                "valid_exact_reference_count and no_exact_reference_count must "
                "partition instance_count"
            )
        if self.eligible_pair_count > self.completed_count:
            raise ValueError("eligible_pair_count cannot exceed completed_count")
        if self.eligible_pair_count > self.valid_exact_reference_count:
            raise ValueError(
                "eligible_pair_count cannot exceed valid_exact_reference_count"
            )
        minimum_eligible = (
            self.completed_count
            + self.valid_exact_reference_count
            - self.instance_count
        )
        if self.eligible_pair_count < minimum_eligible:
            raise ValueError(
                "eligible_pair_count is smaller than the required intersection "
                "of completed and exact-reference instances"
            )
        if self.failure_count + self.optimal_tie_count != self.eligible_pair_count:
            raise ValueError(
                "failure_count and optimal_tie_count must partition "
                "eligible_pair_count"
            )

        for name, count, denominator in (
            ("timeout_rate", self.timeout_count, self.run_count),
            ("error_rate", self.error_count, self.run_count),
            (
                "exact_reference_rate",
                self.valid_exact_reference_count,
                self.instance_count,
            ),
            (
                "eligible_pair_rate",
                self.eligible_pair_count,
                self.instance_count,
            ),
        ):
            rate = getattr(self, name)
            if not math.isfinite(rate) or not 0 <= rate <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")
            if not math.isclose(rate, count / denominator, abs_tol=5e-10):
                raise ValueError(
                    f"{name} does not match its count and denominator"
                )

        if self.eligible_pair_count == 0:
            if self.failure_rate is not None or self.optimal_tie_rate is not None:
                raise ValueError(
                    "failure_rate and optimal_tie_rate must be blank when "
                    "eligible_pair_count is zero"
                )
            return
        if self.failure_rate is None or self.optimal_tie_rate is None:
            raise ValueError(
                "failure_rate and optimal_tie_rate are required when "
                "eligible_pair_count is positive"
            )
        for name, count in (
            ("failure_rate", self.failure_count),
            ("optimal_tie_rate", self.optimal_tie_count),
        ):
            rate = getattr(self, name)
            assert rate is not None
            if not math.isfinite(rate) or not 0 <= rate <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")
            if not math.isclose(
                rate,
                count / self.eligible_pair_count,
                abs_tol=5e-10,
            ):
                raise ValueError(
                    f"{name} does not match its count and eligible_pair_count"
                )

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "completed_count": self.completed_count,
            "timeout_count": self.timeout_count,
            "timeout_rate": f"{self.timeout_rate:.10f}",
            "error_count": self.error_count,
            "error_rate": f"{self.error_rate:.10f}",
            "valid_exact_reference_count": self.valid_exact_reference_count,
            "exact_reference_rate": f"{self.exact_reference_rate:.10f}",
            "no_exact_reference_count": self.no_exact_reference_count,
            "eligible_pair_count": self.eligible_pair_count,
            "eligible_pair_rate": f"{self.eligible_pair_rate:.10f}",
            "failure_count": self.failure_count,
            "optimal_tie_count": self.optimal_tie_count,
            "failure_rate": (
                "" if self.failure_rate is None else f"{self.failure_rate:.10f}"
            ),
            "optimal_tie_rate": (
                ""
                if self.optimal_tie_rate is None
                else f"{self.optimal_tie_rate:.10f}"
            ),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> GreedyFailureRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        schema_version = _required_int(row["schema_version"], "schema_version")
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            run_count=_required_int(row["run_count"], "run_count"),
            completed_count=_required_int(
                row["completed_count"], "completed_count"
            ),
            timeout_count=_required_int(row["timeout_count"], "timeout_count"),
            timeout_rate=_required_float(row["timeout_rate"], "timeout_rate"),
            error_count=_required_int(row["error_count"], "error_count"),
            error_rate=_required_float(row["error_rate"], "error_rate"),
            valid_exact_reference_count=_required_int(
                row["valid_exact_reference_count"],
                "valid_exact_reference_count",
            ),
            exact_reference_rate=_required_float(
                row["exact_reference_rate"], "exact_reference_rate"
            ),
            no_exact_reference_count=_required_int(
                row["no_exact_reference_count"],
                "no_exact_reference_count",
            ),
            eligible_pair_count=_required_int(
                row["eligible_pair_count"], "eligible_pair_count"
            ),
            eligible_pair_rate=_required_float(
                row["eligible_pair_rate"], "eligible_pair_rate"
            ),
            failure_count=_required_int(row["failure_count"], "failure_count"),
            optimal_tie_count=_required_int(
                row["optimal_tie_count"], "optimal_tie_count"
            ),
            failure_rate=_parse_float(
                row["failure_rate"], "failure_rate", optional=True
            ),
            optimal_tie_rate=_parse_float(
                row["optimal_tie_rate"], "optimal_tie_rate", optional=True
            ),
            schema_version=schema_version,
        )


@dataclass(frozen=True, slots=True)
class LocalSearchRecoveryRecord:
    """One P5.2 Local Search recovery row for a paired algorithm variant."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "greedy_algorithm_id",
        "local_search_algorithm_id",
        "algorithm",
        "repetition_unit",
        "instance_count",
        "greedy_completed_count",
        "greedy_timeout_count",
        "greedy_error_count",
        "local_search_completed_count",
        "local_search_timeout_count",
        "local_search_error_count",
        "valid_exact_reference_count",
        "greedy_failure_count",
        "eligible_pair_count",
        "eligible_pair_rate",
        "mean_gap_recovery_rate",
        "full_recovery_count",
        "full_recovery_rate",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    greedy_algorithm_id: str
    local_search_algorithm_id: str
    algorithm: str
    repetition_unit: str
    instance_count: int
    greedy_completed_count: int
    greedy_timeout_count: int
    greedy_error_count: int
    local_search_completed_count: int
    local_search_timeout_count: int
    local_search_error_count: int
    valid_exact_reference_count: int
    greedy_failure_count: int
    eligible_pair_count: int
    eligible_pair_rate: float | None
    mean_gap_recovery_rate: float | None
    full_recovery_count: int
    full_recovery_rate: float | None
    schema_version: int = LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported Local Search recovery schema version "
                f"{self.schema_version!r}; "
                f"expected {LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "greedy_algorithm_id",
            "local_search_algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.algorithm != "local_search":
            raise ValueError("algorithm must be 'local_search'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")

        count_names = (
            "instance_count",
            "greedy_completed_count",
            "greedy_timeout_count",
            "greedy_error_count",
            "local_search_completed_count",
            "local_search_timeout_count",
            "local_search_error_count",
            "valid_exact_reference_count",
            "greedy_failure_count",
            "eligible_pair_count",
            "full_recovery_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if (
            self.greedy_completed_count
            + self.greedy_timeout_count
            + self.greedy_error_count
            != self.instance_count
        ):
            raise ValueError("Greedy status counts must partition instance_count")
        if (
            self.local_search_completed_count
            + self.local_search_timeout_count
            + self.local_search_error_count
            != self.instance_count
        ):
            raise ValueError(
                "Local Search status counts must partition instance_count"
            )
        if self.valid_exact_reference_count > self.instance_count:
            raise ValueError(
                "valid_exact_reference_count cannot exceed instance_count"
            )
        if self.greedy_failure_count > self.greedy_completed_count:
            raise ValueError(
                "greedy_failure_count cannot exceed greedy_completed_count"
            )
        if self.greedy_failure_count > self.valid_exact_reference_count:
            raise ValueError(
                "greedy_failure_count cannot exceed valid_exact_reference_count"
            )
        if self.eligible_pair_count > self.greedy_failure_count:
            raise ValueError(
                "eligible_pair_count cannot exceed greedy_failure_count"
            )
        if self.eligible_pair_count > self.local_search_completed_count:
            raise ValueError(
                "eligible_pair_count cannot exceed local_search_completed_count"
            )
        minimum_eligible = (
            self.greedy_failure_count
            + self.local_search_completed_count
            - self.instance_count
        )
        if self.eligible_pair_count < minimum_eligible:
            raise ValueError(
                "eligible_pair_count is smaller than the required intersection "
                "of Greedy failures and completed Local Search instances"
            )
        if self.full_recovery_count > self.eligible_pair_count:
            raise ValueError(
                "full_recovery_count cannot exceed eligible_pair_count"
            )

        if self.greedy_failure_count == 0:
            if self.eligible_pair_count != 0 or self.eligible_pair_rate is not None:
                raise ValueError(
                    "eligible pair fields must be zero/blank when there are no "
                    "Greedy failures"
                )
        else:
            if self.eligible_pair_rate is None:
                raise ValueError(
                    "eligible_pair_rate is required when Greedy failures exist"
                )
            self._validate_rate(
                "eligible_pair_rate",
                self.eligible_pair_rate,
                self.eligible_pair_count / self.greedy_failure_count,
            )

        if self.eligible_pair_count == 0:
            if (
                self.mean_gap_recovery_rate is not None
                or self.full_recovery_rate is not None
                or self.full_recovery_count != 0
            ):
                raise ValueError(
                    "recovery rates and full_recovery_count must be blank/zero "
                    "when eligible_pair_count is zero"
                )
            return
        if (
            self.mean_gap_recovery_rate is None
            or self.full_recovery_rate is None
        ):
            raise ValueError(
                "recovery rates are required when eligible_pair_count is positive"
            )
        self._validate_rate(
            "mean_gap_recovery_rate",
            self.mean_gap_recovery_rate,
        )
        self._validate_rate(
            "full_recovery_rate",
            self.full_recovery_rate,
            self.full_recovery_count / self.eligible_pair_count,
        )

    @staticmethod
    def _validate_rate(
        name: str, value: float, expected: float | None = None
    ) -> None:
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be finite and between 0 and 1")
        if expected is not None and not math.isclose(
            value, expected, abs_tol=5e-10
        ):
            raise ValueError(f"{name} does not match its count and denominator")

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "greedy_algorithm_id": self.greedy_algorithm_id,
            "local_search_algorithm_id": self.local_search_algorithm_id,
            "algorithm": self.algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "greedy_completed_count": self.greedy_completed_count,
            "greedy_timeout_count": self.greedy_timeout_count,
            "greedy_error_count": self.greedy_error_count,
            "local_search_completed_count": self.local_search_completed_count,
            "local_search_timeout_count": self.local_search_timeout_count,
            "local_search_error_count": self.local_search_error_count,
            "valid_exact_reference_count": self.valid_exact_reference_count,
            "greedy_failure_count": self.greedy_failure_count,
            "eligible_pair_count": self.eligible_pair_count,
            "eligible_pair_rate": (
                ""
                if self.eligible_pair_rate is None
                else f"{self.eligible_pair_rate:.10f}"
            ),
            "mean_gap_recovery_rate": (
                ""
                if self.mean_gap_recovery_rate is None
                else f"{self.mean_gap_recovery_rate:.10f}"
            ),
            "full_recovery_count": self.full_recovery_count,
            "full_recovery_rate": (
                ""
                if self.full_recovery_rate is None
                else f"{self.full_recovery_rate:.10f}"
            ),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> LocalSearchRecoveryRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            greedy_algorithm_id=row["greedy_algorithm_id"],
            local_search_algorithm_id=row["local_search_algorithm_id"],
            algorithm=row["algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            greedy_completed_count=_required_int(
                row["greedy_completed_count"], "greedy_completed_count"
            ),
            greedy_timeout_count=_required_int(
                row["greedy_timeout_count"], "greedy_timeout_count"
            ),
            greedy_error_count=_required_int(
                row["greedy_error_count"], "greedy_error_count"
            ),
            local_search_completed_count=_required_int(
                row["local_search_completed_count"],
                "local_search_completed_count",
            ),
            local_search_timeout_count=_required_int(
                row["local_search_timeout_count"],
                "local_search_timeout_count",
            ),
            local_search_error_count=_required_int(
                row["local_search_error_count"], "local_search_error_count"
            ),
            valid_exact_reference_count=_required_int(
                row["valid_exact_reference_count"],
                "valid_exact_reference_count",
            ),
            greedy_failure_count=_required_int(
                row["greedy_failure_count"], "greedy_failure_count"
            ),
            eligible_pair_count=_required_int(
                row["eligible_pair_count"], "eligible_pair_count"
            ),
            eligible_pair_rate=_parse_float(
                row["eligible_pair_rate"], "eligible_pair_rate", optional=True
            ),
            mean_gap_recovery_rate=_parse_float(
                row["mean_gap_recovery_rate"],
                "mean_gap_recovery_rate",
                optional=True,
            ),
            full_recovery_count=_required_int(
                row["full_recovery_count"], "full_recovery_count"
            ),
            full_recovery_rate=_parse_float(
                row["full_recovery_rate"], "full_recovery_rate", optional=True
            ),
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class LocalSearchRemainingGapRecord:
    """One P5.2 post-recovery gap row for a paired algorithm variant."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "greedy_algorithm_id",
        "local_search_algorithm_id",
        "algorithm",
        "repetition_unit",
        "instance_count",
        "valid_exact_reference_count",
        "greedy_failure_count",
        "eligible_pair_count",
        "mean_remaining_relative_gap",
        "maximum_remaining_relative_gap",
        "zero_remaining_gap_count",
        "zero_remaining_gap_rate",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    greedy_algorithm_id: str
    local_search_algorithm_id: str
    algorithm: str
    repetition_unit: str
    instance_count: int
    valid_exact_reference_count: int
    greedy_failure_count: int
    eligible_pair_count: int
    mean_remaining_relative_gap: float | None
    maximum_remaining_relative_gap: float | None
    zero_remaining_gap_count: int
    zero_remaining_gap_rate: float | None
    schema_version: int = LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION:
            raise ValueError(
                "unsupported Local Search remaining-gap schema version "
                f"{self.schema_version!r}; "
                f"expected {LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "greedy_algorithm_id",
            "local_search_algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.algorithm != "local_search":
            raise ValueError("algorithm must be 'local_search'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")

        for name in (
            "instance_count",
            "valid_exact_reference_count",
            "greedy_failure_count",
            "eligible_pair_count",
            "zero_remaining_gap_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if self.valid_exact_reference_count > self.instance_count:
            raise ValueError(
                "valid_exact_reference_count cannot exceed instance_count"
            )
        if self.greedy_failure_count > self.valid_exact_reference_count:
            raise ValueError(
                "greedy_failure_count cannot exceed valid_exact_reference_count"
            )
        if self.eligible_pair_count > self.greedy_failure_count:
            raise ValueError(
                "eligible_pair_count cannot exceed greedy_failure_count"
            )
        if self.zero_remaining_gap_count > self.eligible_pair_count:
            raise ValueError(
                "zero_remaining_gap_count cannot exceed eligible_pair_count"
            )

        if self.eligible_pair_count == 0:
            if (
                self.mean_remaining_relative_gap is not None
                or self.maximum_remaining_relative_gap is not None
                or self.zero_remaining_gap_count != 0
                or self.zero_remaining_gap_rate is not None
            ):
                raise ValueError(
                    "remaining-gap statistics must be blank/zero when "
                    "eligible_pair_count is zero"
                )
            return
        if (
            self.mean_remaining_relative_gap is None
            or self.maximum_remaining_relative_gap is None
            or self.zero_remaining_gap_rate is None
        ):
            raise ValueError(
                "remaining-gap statistics are required when eligible_pair_count "
                "is positive"
            )
        for name in (
            "mean_remaining_relative_gap",
            "maximum_remaining_relative_gap",
            "zero_remaining_gap_rate",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")
        if self.mean_remaining_relative_gap > self.maximum_remaining_relative_gap:
            raise ValueError(
                "mean_remaining_relative_gap cannot exceed "
                "maximum_remaining_relative_gap"
            )
        expected_zero_rate = (
            self.zero_remaining_gap_count / self.eligible_pair_count
        )
        if not math.isclose(
            self.zero_remaining_gap_rate,
            expected_zero_rate,
            abs_tol=5e-10,
        ):
            raise ValueError(
                "zero_remaining_gap_rate does not match its count and denominator"
            )
        all_zero = self.zero_remaining_gap_count == self.eligible_pair_count
        observed_all_zero = math.isclose(
            self.maximum_remaining_relative_gap, 0.0, abs_tol=5e-10
        )
        if all_zero != observed_all_zero:
            raise ValueError(
                "zero_remaining_gap_count conflicts with the maximum remaining gap"
            )

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "greedy_algorithm_id": self.greedy_algorithm_id,
            "local_search_algorithm_id": self.local_search_algorithm_id,
            "algorithm": self.algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "valid_exact_reference_count": self.valid_exact_reference_count,
            "greedy_failure_count": self.greedy_failure_count,
            "eligible_pair_count": self.eligible_pair_count,
            "mean_remaining_relative_gap": (
                ""
                if self.mean_remaining_relative_gap is None
                else f"{self.mean_remaining_relative_gap:.10f}"
            ),
            "maximum_remaining_relative_gap": (
                ""
                if self.maximum_remaining_relative_gap is None
                else f"{self.maximum_remaining_relative_gap:.10f}"
            ),
            "zero_remaining_gap_count": self.zero_remaining_gap_count,
            "zero_remaining_gap_rate": (
                ""
                if self.zero_remaining_gap_rate is None
                else f"{self.zero_remaining_gap_rate:.10f}"
            ),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> LocalSearchRemainingGapRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            greedy_algorithm_id=row["greedy_algorithm_id"],
            local_search_algorithm_id=row["local_search_algorithm_id"],
            algorithm=row["algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            valid_exact_reference_count=_required_int(
                row["valid_exact_reference_count"],
                "valid_exact_reference_count",
            ),
            greedy_failure_count=_required_int(
                row["greedy_failure_count"], "greedy_failure_count"
            ),
            eligible_pair_count=_required_int(
                row["eligible_pair_count"], "eligible_pair_count"
            ),
            mean_remaining_relative_gap=_parse_float(
                row["mean_remaining_relative_gap"],
                "mean_remaining_relative_gap",
                optional=True,
            ),
            maximum_remaining_relative_gap=_parse_float(
                row["maximum_remaining_relative_gap"],
                "maximum_remaining_relative_gap",
                optional=True,
            ),
            zero_remaining_gap_count=_required_int(
                row["zero_remaining_gap_count"], "zero_remaining_gap_count"
            ),
            zero_remaining_gap_rate=_parse_float(
                row["zero_remaining_gap_rate"],
                "zero_remaining_gap_rate",
                optional=True,
            ),
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class HeuristicExactRuntimeRatioRecord:
    """One P5.2 runtime-ratio row for a heuristic/exact variant pair."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "heuristic_algorithm_id",
        "heuristic_algorithm",
        "exact_algorithm_id",
        "exact_algorithm",
        "repetition_unit",
        "instance_count",
        "heuristic_run_count",
        "heuristic_completed_run_count",
        "heuristic_timeout_count",
        "heuristic_error_count",
        "exact_run_count",
        "exact_completed_run_count",
        "exact_timeout_count",
        "exact_error_count",
        "eligible_pair_count",
        "zero_exact_runtime_count",
        "mean_runtime_ratio",
        "median_runtime_ratio",
        "minimum_runtime_ratio",
        "maximum_runtime_ratio",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    heuristic_algorithm_id: str
    heuristic_algorithm: str
    exact_algorithm_id: str
    exact_algorithm: str
    repetition_unit: str
    instance_count: int
    heuristic_run_count: int
    heuristic_completed_run_count: int
    heuristic_timeout_count: int
    heuristic_error_count: int
    exact_run_count: int
    exact_completed_run_count: int
    exact_timeout_count: int
    exact_error_count: int
    eligible_pair_count: int
    zero_exact_runtime_count: int
    mean_runtime_ratio: float | None
    median_runtime_ratio: float | None
    minimum_runtime_ratio: float | None
    maximum_runtime_ratio: float | None
    schema_version: int = HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION:
            raise ValueError(
                "unsupported heuristic/exact runtime-ratio schema version "
                f"{self.schema_version!r}; "
                f"expected {HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "heuristic_algorithm_id",
            "heuristic_algorithm",
            "exact_algorithm_id",
            "exact_algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.heuristic_algorithm_id == self.exact_algorithm_id:
            raise ValueError("heuristic and exact algorithm IDs must differ")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")

        count_names = (
            "instance_count",
            "heuristic_run_count",
            "heuristic_completed_run_count",
            "heuristic_timeout_count",
            "heuristic_error_count",
            "exact_run_count",
            "exact_completed_run_count",
            "exact_timeout_count",
            "exact_error_count",
            "eligible_pair_count",
            "zero_exact_runtime_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if self.heuristic_run_count < self.instance_count:
            raise ValueError(
                "heuristic_run_count cannot be smaller than instance_count"
            )
        if self.exact_run_count != self.instance_count:
            raise ValueError(
                "deterministic exact variants require one run per instance"
            )
        if (
            self.heuristic_completed_run_count
            + self.heuristic_timeout_count
            + self.heuristic_error_count
            != self.heuristic_run_count
        ):
            raise ValueError(
                "heuristic status counts must partition heuristic_run_count"
            )
        if (
            self.exact_completed_run_count
            + self.exact_timeout_count
            + self.exact_error_count
            != self.exact_run_count
        ):
            raise ValueError("exact status counts must partition exact_run_count")
        if self.eligible_pair_count > self.instance_count:
            raise ValueError(
                "eligible_pair_count cannot exceed instance_count"
            )
        if self.eligible_pair_count > self.exact_completed_run_count:
            raise ValueError(
                "eligible_pair_count cannot exceed exact_completed_run_count"
            )
        if self.zero_exact_runtime_count > self.exact_completed_run_count:
            raise ValueError(
                "zero_exact_runtime_count cannot exceed exact completed runs"
            )

        statistics = (
            self.mean_runtime_ratio,
            self.median_runtime_ratio,
            self.minimum_runtime_ratio,
            self.maximum_runtime_ratio,
        )
        if self.eligible_pair_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError(
                    "runtime-ratio statistics must be blank when "
                    "eligible_pair_count is zero"
                )
            return
        if any(value is None for value in statistics):
            raise ValueError(
                "runtime-ratio statistics are required when "
                "eligible_pair_count is positive"
            )
        mean = self.mean_runtime_ratio
        middle = self.median_runtime_ratio
        minimum = self.minimum_runtime_ratio
        maximum = self.maximum_runtime_ratio
        assert mean is not None
        assert middle is not None
        assert minimum is not None
        assert maximum is not None
        for name, value in (
            ("mean_runtime_ratio", mean),
            ("median_runtime_ratio", middle),
            ("minimum_runtime_ratio", minimum),
            ("maximum_runtime_ratio", maximum),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if minimum > middle or middle > maximum:
            raise ValueError(
                "runtime-ratio minimum, median, and maximum are inconsistent"
            )
        if mean < minimum - 5e-10 or mean > maximum + 5e-10:
            raise ValueError(
                "mean_runtime_ratio must be between minimum and maximum"
            )
        if self.eligible_pair_count == 1 and not (
            math.isclose(mean, middle, abs_tol=5e-10)
            and math.isclose(mean, minimum, abs_tol=5e-10)
            and math.isclose(mean, maximum, abs_tol=5e-10)
        ):
            raise ValueError(
                "singleton runtime-ratio statistics must all be equal"
            )

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "heuristic_algorithm_id": self.heuristic_algorithm_id,
            "heuristic_algorithm": self.heuristic_algorithm,
            "exact_algorithm_id": self.exact_algorithm_id,
            "exact_algorithm": self.exact_algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "heuristic_run_count": self.heuristic_run_count,
            "heuristic_completed_run_count": (
                self.heuristic_completed_run_count
            ),
            "heuristic_timeout_count": self.heuristic_timeout_count,
            "heuristic_error_count": self.heuristic_error_count,
            "exact_run_count": self.exact_run_count,
            "exact_completed_run_count": self.exact_completed_run_count,
            "exact_timeout_count": self.exact_timeout_count,
            "exact_error_count": self.exact_error_count,
            "eligible_pair_count": self.eligible_pair_count,
            "zero_exact_runtime_count": self.zero_exact_runtime_count,
            "mean_runtime_ratio": self._format_optional(
                self.mean_runtime_ratio
            ),
            "median_runtime_ratio": self._format_optional(
                self.median_runtime_ratio
            ),
            "minimum_runtime_ratio": self._format_optional(
                self.minimum_runtime_ratio
            ),
            "maximum_runtime_ratio": self._format_optional(
                self.maximum_runtime_ratio
            ),
            "schema_version": self.schema_version,
        }

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> HeuristicExactRuntimeRatioRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            heuristic_algorithm_id=row["heuristic_algorithm_id"],
            heuristic_algorithm=row["heuristic_algorithm"],
            exact_algorithm_id=row["exact_algorithm_id"],
            exact_algorithm=row["exact_algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            heuristic_run_count=_required_int(
                row["heuristic_run_count"], "heuristic_run_count"
            ),
            heuristic_completed_run_count=_required_int(
                row["heuristic_completed_run_count"],
                "heuristic_completed_run_count",
            ),
            heuristic_timeout_count=_required_int(
                row["heuristic_timeout_count"], "heuristic_timeout_count"
            ),
            heuristic_error_count=_required_int(
                row["heuristic_error_count"], "heuristic_error_count"
            ),
            exact_run_count=_required_int(
                row["exact_run_count"], "exact_run_count"
            ),
            exact_completed_run_count=_required_int(
                row["exact_completed_run_count"], "exact_completed_run_count"
            ),
            exact_timeout_count=_required_int(
                row["exact_timeout_count"], "exact_timeout_count"
            ),
            exact_error_count=_required_int(
                row["exact_error_count"], "exact_error_count"
            ),
            eligible_pair_count=_required_int(
                row["eligible_pair_count"], "eligible_pair_count"
            ),
            zero_exact_runtime_count=_required_int(
                row["zero_exact_runtime_count"], "zero_exact_runtime_count"
            ),
            mean_runtime_ratio=_parse_float(
                row["mean_runtime_ratio"], "mean_runtime_ratio", optional=True
            ),
            median_runtime_ratio=_parse_float(
                row["median_runtime_ratio"],
                "median_runtime_ratio",
                optional=True,
            ),
            minimum_runtime_ratio=_parse_float(
                row["minimum_runtime_ratio"],
                "minimum_runtime_ratio",
                optional=True,
            ),
            maximum_runtime_ratio=_parse_float(
                row["maximum_runtime_ratio"],
                "maximum_runtime_ratio",
                optional=True,
            ),
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class BranchAndBoundNodeReductionRecord:
    """One P5.2 node-reduction row for a baseline/enhanced BnB pair."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "baseline_algorithm_id",
        "baseline_algorithm",
        "enhanced_algorithm_id",
        "enhanced_algorithm",
        "repetition_unit",
        "instance_count",
        "baseline_run_count",
        "baseline_optimal_count",
        "baseline_timeout_count",
        "baseline_error_count",
        "enhanced_run_count",
        "enhanced_optimal_count",
        "enhanced_timeout_count",
        "enhanced_error_count",
        "eligible_pair_count",
        "zero_baseline_nodes_count",
        "total_baseline_nodes",
        "total_enhanced_nodes",
        "mean_node_reduction",
        "median_node_reduction",
        "minimum_node_reduction",
        "maximum_node_reduction",
        "aggregate_node_reduction",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    baseline_algorithm_id: str
    baseline_algorithm: str
    enhanced_algorithm_id: str
    enhanced_algorithm: str
    repetition_unit: str
    instance_count: int
    baseline_run_count: int
    baseline_optimal_count: int
    baseline_timeout_count: int
    baseline_error_count: int
    enhanced_run_count: int
    enhanced_optimal_count: int
    enhanced_timeout_count: int
    enhanced_error_count: int
    eligible_pair_count: int
    zero_baseline_nodes_count: int
    total_baseline_nodes: int
    total_enhanced_nodes: int
    mean_node_reduction: float | None
    median_node_reduction: float | None
    minimum_node_reduction: float | None
    maximum_node_reduction: float | None
    aggregate_node_reduction: float | None
    schema_version: int = BNB_NODE_REDUCTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BNB_NODE_REDUCTION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported Branch-and-Bound node-reduction schema version "
                f"{self.schema_version!r}; "
                f"expected {BNB_NODE_REDUCTION_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "baseline_algorithm_id",
            "baseline_algorithm",
            "enhanced_algorithm_id",
            "enhanced_algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.baseline_algorithm != "branch_and_bound":
            raise ValueError(
                "baseline_algorithm must be 'branch_and_bound'"
            )
        if self.enhanced_algorithm != "branch_and_bound_enhanced":
            raise ValueError(
                "enhanced_algorithm must be 'branch_and_bound_enhanced'"
            )
        if self.baseline_algorithm_id == self.enhanced_algorithm_id:
            raise ValueError("baseline and enhanced algorithm IDs must differ")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")

        count_names = (
            "instance_count",
            "baseline_run_count",
            "baseline_optimal_count",
            "baseline_timeout_count",
            "baseline_error_count",
            "enhanced_run_count",
            "enhanced_optimal_count",
            "enhanced_timeout_count",
            "enhanced_error_count",
            "eligible_pair_count",
            "zero_baseline_nodes_count",
            "total_baseline_nodes",
            "total_enhanced_nodes",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if self.baseline_run_count != self.instance_count:
            raise ValueError(
                "baseline variants require one run per instance"
            )
        if self.enhanced_run_count != self.instance_count:
            raise ValueError(
                "enhanced variants require one run per instance"
            )
        if (
            self.baseline_optimal_count
            + self.baseline_timeout_count
            + self.baseline_error_count
            != self.baseline_run_count
        ):
            raise ValueError(
                "baseline status counts must partition baseline_run_count"
            )
        if (
            self.enhanced_optimal_count
            + self.enhanced_timeout_count
            + self.enhanced_error_count
            != self.enhanced_run_count
        ):
            raise ValueError(
                "enhanced status counts must partition enhanced_run_count"
            )
        if self.eligible_pair_count > min(
            self.baseline_optimal_count,
            self.enhanced_optimal_count,
        ):
            raise ValueError(
                "eligible_pair_count cannot exceed either optimal count"
            )
        if self.zero_baseline_nodes_count > self.baseline_optimal_count:
            raise ValueError(
                "zero_baseline_nodes_count cannot exceed baseline_optimal_count"
            )
        if (
            self.eligible_pair_count + self.zero_baseline_nodes_count
            > self.baseline_optimal_count
        ):
            raise ValueError(
                "eligible and zero-node baseline pairs cannot exceed "
                "baseline_optimal_count"
            )
        minimum_eligible = max(
            0,
            self.baseline_optimal_count
            + self.enhanced_optimal_count
            - self.instance_count
            - self.zero_baseline_nodes_count,
        )
        if self.eligible_pair_count < minimum_eligible:
            raise ValueError(
                "eligible_pair_count is too small for the paired optimal "
                "status counts"
            )

        statistics = (
            self.mean_node_reduction,
            self.median_node_reduction,
            self.minimum_node_reduction,
            self.maximum_node_reduction,
            self.aggregate_node_reduction,
        )
        if self.eligible_pair_count == 0:
            if self.total_baseline_nodes or self.total_enhanced_nodes:
                raise ValueError(
                    "node totals must be zero when eligible_pair_count is zero"
                )
            if any(value is not None for value in statistics):
                raise ValueError(
                    "node-reduction statistics must be blank when "
                    "eligible_pair_count is zero"
                )
            return
        if self.total_baseline_nodes <= 0:
            raise ValueError(
                "eligible pairs require a positive total_baseline_nodes"
            )
        if any(value is None for value in statistics):
            raise ValueError(
                "node-reduction statistics are required when "
                "eligible_pair_count is positive"
            )
        mean = self.mean_node_reduction
        middle = self.median_node_reduction
        minimum = self.minimum_node_reduction
        maximum = self.maximum_node_reduction
        aggregate = self.aggregate_node_reduction
        assert mean is not None
        assert middle is not None
        assert minimum is not None
        assert maximum is not None
        assert aggregate is not None
        for name, value in (
            ("mean_node_reduction", mean),
            ("median_node_reduction", middle),
            ("minimum_node_reduction", minimum),
            ("maximum_node_reduction", maximum),
            ("aggregate_node_reduction", aggregate),
        ):
            if not math.isfinite(value) or value > 1:
                raise ValueError(f"{name} must be finite and no greater than 1")
        if minimum > middle or middle > maximum:
            raise ValueError(
                "node-reduction minimum, median, and maximum are inconsistent"
            )
        if mean < minimum - 5e-10 or mean > maximum + 5e-10:
            raise ValueError(
                "mean_node_reduction must be between minimum and maximum"
            )
        expected_aggregate = (
            self.total_baseline_nodes - self.total_enhanced_nodes
        ) / self.total_baseline_nodes
        if not math.isclose(aggregate, expected_aggregate, abs_tol=5e-10):
            raise ValueError(
                "aggregate_node_reduction does not match the node totals"
            )
        if self.eligible_pair_count == 1 and not (
            math.isclose(mean, middle, abs_tol=5e-10)
            and math.isclose(mean, minimum, abs_tol=5e-10)
            and math.isclose(mean, maximum, abs_tol=5e-10)
            and math.isclose(mean, aggregate, abs_tol=5e-10)
        ):
            raise ValueError(
                "singleton node-reduction statistics must all be equal"
            )

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "baseline_algorithm_id": self.baseline_algorithm_id,
            "baseline_algorithm": self.baseline_algorithm,
            "enhanced_algorithm_id": self.enhanced_algorithm_id,
            "enhanced_algorithm": self.enhanced_algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "baseline_run_count": self.baseline_run_count,
            "baseline_optimal_count": self.baseline_optimal_count,
            "baseline_timeout_count": self.baseline_timeout_count,
            "baseline_error_count": self.baseline_error_count,
            "enhanced_run_count": self.enhanced_run_count,
            "enhanced_optimal_count": self.enhanced_optimal_count,
            "enhanced_timeout_count": self.enhanced_timeout_count,
            "enhanced_error_count": self.enhanced_error_count,
            "eligible_pair_count": self.eligible_pair_count,
            "zero_baseline_nodes_count": self.zero_baseline_nodes_count,
            "total_baseline_nodes": self.total_baseline_nodes,
            "total_enhanced_nodes": self.total_enhanced_nodes,
            "mean_node_reduction": self._format_optional(
                self.mean_node_reduction
            ),
            "median_node_reduction": self._format_optional(
                self.median_node_reduction
            ),
            "minimum_node_reduction": self._format_optional(
                self.minimum_node_reduction
            ),
            "maximum_node_reduction": self._format_optional(
                self.maximum_node_reduction
            ),
            "aggregate_node_reduction": self._format_optional(
                self.aggregate_node_reduction
            ),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> BranchAndBoundNodeReductionRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            baseline_algorithm_id=row["baseline_algorithm_id"],
            baseline_algorithm=row["baseline_algorithm"],
            enhanced_algorithm_id=row["enhanced_algorithm_id"],
            enhanced_algorithm=row["enhanced_algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            baseline_run_count=_required_int(
                row["baseline_run_count"], "baseline_run_count"
            ),
            baseline_optimal_count=_required_int(
                row["baseline_optimal_count"], "baseline_optimal_count"
            ),
            baseline_timeout_count=_required_int(
                row["baseline_timeout_count"], "baseline_timeout_count"
            ),
            baseline_error_count=_required_int(
                row["baseline_error_count"], "baseline_error_count"
            ),
            enhanced_run_count=_required_int(
                row["enhanced_run_count"], "enhanced_run_count"
            ),
            enhanced_optimal_count=_required_int(
                row["enhanced_optimal_count"], "enhanced_optimal_count"
            ),
            enhanced_timeout_count=_required_int(
                row["enhanced_timeout_count"], "enhanced_timeout_count"
            ),
            enhanced_error_count=_required_int(
                row["enhanced_error_count"], "enhanced_error_count"
            ),
            eligible_pair_count=_required_int(
                row["eligible_pair_count"], "eligible_pair_count"
            ),
            zero_baseline_nodes_count=_required_int(
                row["zero_baseline_nodes_count"],
                "zero_baseline_nodes_count",
            ),
            total_baseline_nodes=_required_int(
                row["total_baseline_nodes"], "total_baseline_nodes"
            ),
            total_enhanced_nodes=_required_int(
                row["total_enhanced_nodes"], "total_enhanced_nodes"
            ),
            mean_node_reduction=_parse_float(
                row["mean_node_reduction"],
                "mean_node_reduction",
                optional=True,
            ),
            median_node_reduction=_parse_float(
                row["median_node_reduction"],
                "median_node_reduction",
                optional=True,
            ),
            minimum_node_reduction=_parse_float(
                row["minimum_node_reduction"],
                "minimum_node_reduction",
                optional=True,
            ),
            maximum_node_reduction=_parse_float(
                row["maximum_node_reduction"],
                "maximum_node_reduction",
                optional=True,
            ),
            aggregate_node_reduction=_parse_float(
                row["aggregate_node_reduction"],
                "aggregate_node_reduction",
                optional=True,
            ),
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class QualityRuntimeParetoRecord:
    """One P5.2 quality-runtime Pareto row for an algorithm variant."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "family",
        "algorithm_id",
        "algorithm",
        "repetition_unit",
        "instance_count",
        "run_count",
        "completed_run_count",
        "timeout_count",
        "error_count",
        "valid_exact_reference_count",
        "zero_optimum_count",
        "no_exact_reference_count",
        "eligible_instance_count",
        "mean_relative_gap",
        "mean_runtime_seconds",
        "pareto_status",
        "dominated_by_algorithm_ids",
        "schema_version",
    )

    config_hash: str
    case_id: str
    family: str
    algorithm_id: str
    algorithm: str
    repetition_unit: str
    instance_count: int
    run_count: int
    completed_run_count: int
    timeout_count: int
    error_count: int
    valid_exact_reference_count: int
    zero_optimum_count: int
    no_exact_reference_count: int
    eligible_instance_count: int
    mean_relative_gap: float | None
    mean_runtime_seconds: float | None
    pareto_status: str
    dominated_by_algorithm_ids: tuple[str, ...] = ()
    schema_version: int = QUALITY_RUNTIME_PARETO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != QUALITY_RUNTIME_PARETO_SCHEMA_VERSION:
            raise ValueError(
                "unsupported quality-runtime Pareto schema version "
                f"{self.schema_version!r}; "
                f"expected {QUALITY_RUNTIME_PARETO_SCHEMA_VERSION}"
            )
        for name in (
            "config_hash",
            "case_id",
            "family",
            "algorithm_id",
            "algorithm",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.pareto_status not in {
            "frontier",
            "dominated",
            "not_evaluable",
        }:
            raise ValueError(
                "pareto_status must be frontier, dominated, or not_evaluable"
            )

        count_names = (
            "instance_count",
            "run_count",
            "completed_run_count",
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
            "zero_optimum_count",
            "no_exact_reference_count",
            "eligible_instance_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.instance_count <= 0:
            raise ValueError("instance_count must be positive")
        if self.run_count < self.instance_count:
            raise ValueError("run_count cannot be smaller than instance_count")
        if (
            self.completed_run_count
            + self.timeout_count
            + self.error_count
            != self.run_count
        ):
            raise ValueError("status counts must partition run_count")
        if (
            self.valid_exact_reference_count
            + self.no_exact_reference_count
            != self.instance_count
        ):
            raise ValueError(
                "reference counts must partition instance_count"
            )
        if self.zero_optimum_count > self.valid_exact_reference_count:
            raise ValueError(
                "zero_optimum_count cannot exceed valid references"
            )
        if self.eligible_instance_count > (
            self.valid_exact_reference_count - self.zero_optimum_count
        ):
            raise ValueError(
                "eligible instances require a positive exact reference"
            )
        if self.eligible_instance_count > self.completed_run_count:
            raise ValueError(
                "eligible instances require at least one completed run"
            )

        object.__setattr__(
            self,
            "dominated_by_algorithm_ids",
            tuple(self.dominated_by_algorithm_ids),
        )
        dominators = self.dominated_by_algorithm_ids
        if any(not isinstance(value, str) or not value for value in dominators):
            raise ValueError(
                "dominated_by_algorithm_ids must contain non-empty strings"
            )
        if tuple(sorted(set(dominators))) != dominators:
            raise ValueError(
                "dominated_by_algorithm_ids must be sorted and unique"
            )
        if self.algorithm_id in dominators:
            raise ValueError("a Pareto point cannot dominate itself")

        statistics = (self.mean_relative_gap, self.mean_runtime_seconds)
        if self.eligible_instance_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError(
                    "Pareto coordinates must be blank with no eligible instances"
                )
            if self.pareto_status != "not_evaluable":
                raise ValueError(
                    "zero eligible instances require not_evaluable status"
                )
            if dominators:
                raise ValueError(
                    "not_evaluable points cannot list dominators"
                )
            return
        if any(value is None for value in statistics):
            raise ValueError(
                "Pareto coordinates require positive eligible instances"
            )
        gap = self.mean_relative_gap
        runtime = self.mean_runtime_seconds
        assert gap is not None
        assert runtime is not None
        if not math.isfinite(gap) or not 0 <= gap <= 1:
            raise ValueError("mean_relative_gap must be between 0 and 1")
        if not math.isfinite(runtime) or runtime < 0:
            raise ValueError(
                "mean_runtime_seconds must be finite and non-negative"
            )
        if self.pareto_status == "frontier" and dominators:
            raise ValueError("frontier points cannot list dominators")
        if self.pareto_status == "dominated" and not dominators:
            raise ValueError("dominated points must list at least one dominator")
        if self.pareto_status == "not_evaluable":
            raise ValueError(
                "positive eligible instances require an evaluated Pareto status"
            )

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "" if value is None else f"{value:.10f}"

    def to_csv_row(self) -> dict[str, object]:
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "family": self.family,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "repetition_unit": self.repetition_unit,
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "completed_run_count": self.completed_run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "valid_exact_reference_count": (
                self.valid_exact_reference_count
            ),
            "zero_optimum_count": self.zero_optimum_count,
            "no_exact_reference_count": self.no_exact_reference_count,
            "eligible_instance_count": self.eligible_instance_count,
            "mean_relative_gap": self._format_optional(
                self.mean_relative_gap
            ),
            "mean_runtime_seconds": self._format_optional(
                self.mean_runtime_seconds
            ),
            "pareto_status": self.pareto_status,
            "dominated_by_algorithm_ids": json.dumps(
                list(self.dominated_by_algorithm_ids),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> QualityRuntimeParetoRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_dominators = json.loads(row["dominated_by_algorithm_ids"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                "dominated_by_algorithm_ids must encode a JSON array"
            ) from error
        if not isinstance(raw_dominators, list):
            raise ValueError(
                "dominated_by_algorithm_ids must encode a JSON array"
            )
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            repetition_unit=row["repetition_unit"],
            instance_count=_required_int(row["instance_count"], "instance_count"),
            run_count=_required_int(row["run_count"], "run_count"),
            completed_run_count=_required_int(
                row["completed_run_count"], "completed_run_count"
            ),
            timeout_count=_required_int(
                row["timeout_count"], "timeout_count"
            ),
            error_count=_required_int(row["error_count"], "error_count"),
            valid_exact_reference_count=_required_int(
                row["valid_exact_reference_count"],
                "valid_exact_reference_count",
            ),
            zero_optimum_count=_required_int(
                row["zero_optimum_count"], "zero_optimum_count"
            ),
            no_exact_reference_count=_required_int(
                row["no_exact_reference_count"],
                "no_exact_reference_count",
            ),
            eligible_instance_count=_required_int(
                row["eligible_instance_count"], "eligible_instance_count"
            ),
            mean_relative_gap=_parse_float(
                row["mean_relative_gap"],
                "mean_relative_gap",
                optional=True,
            ),
            mean_runtime_seconds=_parse_float(
                row["mean_runtime_seconds"],
                "mean_runtime_seconds",
                optional=True,
            ),
            pareto_status=row["pareto_status"],
            dominated_by_algorithm_ids=tuple(raw_dominators),
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


DescriptiveStatisticsRecord.__module__ = "maxcover.contracts"
ConfidenceIntervalRecord.__module__ = "maxcover.contracts"
CensoredRuntimeRecord.__module__ = "maxcover.contracts"
GreedyFailureRecord.__module__ = "maxcover.contracts"
LocalSearchRecoveryRecord.__module__ = "maxcover.contracts"
LocalSearchRemainingGapRecord.__module__ = "maxcover.contracts"
HeuristicExactRuntimeRatioRecord.__module__ = "maxcover.contracts"
BranchAndBoundNodeReductionRecord.__module__ = "maxcover.contracts"
QualityRuntimeParetoRecord.__module__ = "maxcover.contracts"
