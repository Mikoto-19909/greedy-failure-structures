"""Private performance statistical record contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from ._contract_csv import (
    _parse_float,
    _required_int,
    _validate_csv_fields,
)


HEURISTIC_EXACT_RUNTIME_RATIO_SCHEMA_VERSION = 1
BNB_NODE_REDUCTION_SCHEMA_VERSION = 1


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


HeuristicExactRuntimeRatioRecord.__module__ = "maxcover.contracts"
BranchAndBoundNodeReductionRecord.__module__ = "maxcover.contracts"
