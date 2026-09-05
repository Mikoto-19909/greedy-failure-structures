"""Private solution quality record contracts."""

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


GREEDY_FAILURE_SCHEMA_VERSION = 1
LOCAL_SEARCH_RECOVERY_SCHEMA_VERSION = 1
LOCAL_SEARCH_REMAINING_GAP_SCHEMA_VERSION = 1
QUALITY_RUNTIME_PARETO_SCHEMA_VERSION = 1


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


GreedyFailureRecord.__module__ = "maxcover.contracts"
LocalSearchRecoveryRecord.__module__ = "maxcover.contracts"
LocalSearchRemainingGapRecord.__module__ = "maxcover.contracts"
QualityRuntimeParetoRecord.__module__ = "maxcover.contracts"
