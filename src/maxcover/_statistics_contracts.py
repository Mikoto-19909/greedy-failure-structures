"""Private non-association statistical record contracts."""

from __future__ import annotations

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


DescriptiveStatisticsRecord.__module__ = "maxcover.contracts"
ConfidenceIntervalRecord.__module__ = "maxcover.contracts"
CensoredRuntimeRecord.__module__ = "maxcover.contracts"
