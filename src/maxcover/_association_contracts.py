"""Private association statistics record contracts."""

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


GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION = 1
GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION = 1
GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GapDensityAssociationRecord:
    """One P5.4 family-local gap versus actual-density association row."""

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
        "timeout_count",
        "error_count",
        "valid_exact_reference_count",
        "zero_optimum_count",
        "no_exact_reference_count",
        "unusable_result_count",
        "eligible_instance_count",
        "distinct_density_count",
        "mean_actual_density",
        "mean_relative_gap",
        "density_sample_standard_deviation",
        "gap_sample_standard_deviation",
        "pearson_correlation",
        "ols_slope",
        "ols_intercept",
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
    timeout_count: int
    error_count: int
    valid_exact_reference_count: int
    zero_optimum_count: int
    no_exact_reference_count: int
    unusable_result_count: int
    eligible_instance_count: int
    distinct_density_count: int
    mean_actual_density: float | None
    mean_relative_gap: float | None
    density_sample_standard_deviation: float | None
    gap_sample_standard_deviation: float | None
    pearson_correlation: float | None
    ols_slope: float | None
    ols_intercept: float | None
    association_status: str
    schema_version: int = GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported gap-density association schema version "
                f"{self.schema_version!r}; "
                f"expected {GAP_DENSITY_ASSOCIATION_SCHEMA_VERSION}"
            )
        for name in ("config_hash", "family", "algorithm_id", "algorithm"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.predictor != "actual_density":
            raise ValueError("predictor must be 'actual_density'")
        if self.response != "relative_optimality_gap":
            raise ValueError("response must be 'relative_optimality_gap'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.association_status not in {
            "no_samples",
            "insufficient_samples",
            "constant_density",
            "constant_gap",
            "estimable",
        }:
            raise ValueError(
                "association_status must be no_samples, insufficient_samples, "
                "constant_density, constant_gap, or estimable"
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
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
            "zero_optimum_count",
            "no_exact_reference_count",
            "unusable_result_count",
            "eligible_instance_count",
            "distinct_density_count",
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
        if self.timeout_count + self.error_count > self.run_count:
            raise ValueError("timeout_count plus error_count cannot exceed run_count")
        if (
            self.valid_exact_reference_count + self.no_exact_reference_count
            != self.instance_count
        ):
            raise ValueError(
                "reference counts must partition instance_count"
            )
        if (
            self.zero_optimum_count
            + self.unusable_result_count
            + self.eligible_instance_count
            != self.valid_exact_reference_count
        ):
            raise ValueError(
                "zero, unusable, and eligible counts must partition valid "
                "exact references"
            )
        if self.distinct_density_count > self.eligible_instance_count:
            raise ValueError(
                "distinct_density_count cannot exceed eligible_instance_count"
            )

        statistics = (
            self.mean_actual_density,
            self.mean_relative_gap,
            self.density_sample_standard_deviation,
            self.gap_sample_standard_deviation,
            self.pearson_correlation,
            self.ols_slope,
            self.ols_intercept,
        )
        if self.eligible_instance_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError("zero samples require blank association statistics")
            if self.distinct_density_count != 0:
                raise ValueError("zero samples require zero distinct densities")
            if self.association_status != "no_samples":
                raise ValueError("zero samples require no_samples status")
            return

        mean_density = self.mean_actual_density
        mean_gap = self.mean_relative_gap
        if mean_density is None or not math.isfinite(mean_density):
            raise ValueError("positive samples require a finite mean density")
        if mean_gap is None or not math.isfinite(mean_gap):
            raise ValueError("positive samples require a finite mean gap")
        if not 0 <= mean_density <= 1:
            raise ValueError("mean_actual_density must be between 0 and 1")
        if not 0 <= mean_gap <= 1:
            raise ValueError("mean_relative_gap must be between 0 and 1")
        if self.distinct_density_count <= 0:
            raise ValueError("positive samples require a distinct density")

        remaining = statistics[2:]
        if self.eligible_instance_count == 1:
            if any(value is not None for value in remaining):
                raise ValueError(
                    "a singleton sample requires blank dispersion and "
                    "association fields"
                )
            if self.distinct_density_count != 1:
                raise ValueError("a singleton sample has one distinct density")
            if self.association_status != "insufficient_samples":
                raise ValueError(
                    "a singleton sample requires insufficient_samples status"
                )
            return

        density_sd = self.density_sample_standard_deviation
        gap_sd = self.gap_sample_standard_deviation
        if density_sd is None or not math.isfinite(density_sd) or density_sd < 0:
            raise ValueError("density sample SD must be finite and non-negative")
        if gap_sd is None or not math.isfinite(gap_sd) or gap_sd < 0:
            raise ValueError("gap sample SD must be finite and non-negative")

        if density_sd == 0:
            if self.distinct_density_count != 1:
                raise ValueError(
                    "zero density variation requires one distinct density"
                )
            if any(
                value is not None
                for value in (
                    self.pearson_correlation,
                    self.ols_slope,
                    self.ols_intercept,
                )
            ):
                raise ValueError(
                    "constant density requires blank correlation and OLS fields"
                )
            if self.association_status != "constant_density":
                raise ValueError(
                    "zero density variation requires constant_density status"
                )
            return

        if self.distinct_density_count < 2:
            raise ValueError(
                "positive density variation requires multiple distinct densities"
            )
        if gap_sd == 0:
            if self.pearson_correlation is not None:
                raise ValueError("constant gap requires blank correlation")
            if self.ols_slope != 0:
                raise ValueError("constant gap requires zero OLS slope")
            if self.ols_intercept is None or not math.isclose(
                self.ols_intercept,
                mean_gap,
                abs_tol=5e-10,
            ):
                raise ValueError(
                    "constant gap requires OLS intercept equal to mean gap"
                )
            if self.association_status != "constant_gap":
                raise ValueError(
                    "zero gap variation requires constant_gap status"
                )
            return

        correlation = self.pearson_correlation
        slope = self.ols_slope
        intercept = self.ols_intercept
        if correlation is None or not math.isfinite(correlation):
            raise ValueError("estimable association requires finite correlation")
        if not -1 <= correlation <= 1:
            raise ValueError("pearson_correlation must be between -1 and 1")
        if slope is None or not math.isfinite(slope):
            raise ValueError("estimable association requires finite OLS slope")
        if intercept is None or not math.isfinite(intercept):
            raise ValueError("estimable association requires finite OLS intercept")
        if self.association_status != "estimable":
            raise ValueError(
                "positive variation on both axes requires estimable status"
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
                list(self.case_ids),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "valid_exact_reference_count": (
                self.valid_exact_reference_count
            ),
            "zero_optimum_count": self.zero_optimum_count,
            "no_exact_reference_count": self.no_exact_reference_count,
            "unusable_result_count": self.unusable_result_count,
            "eligible_instance_count": self.eligible_instance_count,
            "distinct_density_count": self.distinct_density_count,
            "mean_actual_density": self._format_optional(
                self.mean_actual_density
            ),
            "mean_relative_gap": self._format_optional(
                self.mean_relative_gap
            ),
            "density_sample_standard_deviation": self._format_optional(
                self.density_sample_standard_deviation
            ),
            "gap_sample_standard_deviation": self._format_optional(
                self.gap_sample_standard_deviation
            ),
            "pearson_correlation": self._format_optional(
                self.pearson_correlation
            ),
            "ols_slope": self._format_optional(self.ols_slope),
            "ols_intercept": self._format_optional(self.ols_intercept),
            "association_status": self.association_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> GapDensityAssociationRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_case_ids = json.loads(row["case_ids"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("case_ids must encode a JSON array") from error
        if not isinstance(raw_case_ids, list):
            raise ValueError("case_ids must encode a JSON array")
        return cls(
            config_hash=row["config_hash"],
            family=row["family"],
            algorithm_id=row["algorithm_id"],
            algorithm=row["algorithm"],
            predictor=row["predictor"],
            response=row["response"],
            repetition_unit=row["repetition_unit"],
            case_count=_required_int(row["case_count"], "case_count"),
            case_ids=tuple(raw_case_ids),
            instance_count=_required_int(
                row["instance_count"], "instance_count"
            ),
            run_count=_required_int(row["run_count"], "run_count"),
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
            unusable_result_count=_required_int(
                row["unusable_result_count"], "unusable_result_count"
            ),
            eligible_instance_count=_required_int(
                row["eligible_instance_count"], "eligible_instance_count"
            ),
            distinct_density_count=_required_int(
                row["distinct_density_count"], "distinct_density_count"
            ),
            mean_actual_density=_parse_float(
                row["mean_actual_density"],
                "mean_actual_density",
                optional=True,
            ),
            mean_relative_gap=_parse_float(
                row["mean_relative_gap"],
                "mean_relative_gap",
                optional=True,
            ),
            density_sample_standard_deviation=_parse_float(
                row["density_sample_standard_deviation"],
                "density_sample_standard_deviation",
                optional=True,
            ),
            gap_sample_standard_deviation=_parse_float(
                row["gap_sample_standard_deviation"],
                "gap_sample_standard_deviation",
                optional=True,
            ),
            pearson_correlation=_parse_float(
                row["pearson_correlation"],
                "pearson_correlation",
                optional=True,
            ),
            ols_slope=_parse_float(
                row["ols_slope"], "ols_slope", optional=True
            ),
            ols_intercept=_parse_float(
                row["ols_intercept"], "ols_intercept", optional=True
            ),
            association_status=row["association_status"],
            schema_version=_required_int(
                row["schema_version"], "schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class GapOverlapAssociationRecord:
    """One P5.4 family-local gap versus measured-overlap association row."""

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
        "timeout_count",
        "error_count",
        "valid_exact_reference_count",
        "zero_optimum_count",
        "no_exact_reference_count",
        "unusable_result_count",
        "missing_overlap_predictor_count",
        "eligible_instance_count",
        "distinct_overlap_count",
        "mean_pairwise_overlap_jaccard",
        "mean_relative_gap",
        "overlap_sample_standard_deviation",
        "gap_sample_standard_deviation",
        "pearson_correlation",
        "ols_slope",
        "ols_intercept",
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
    timeout_count: int
    error_count: int
    valid_exact_reference_count: int
    zero_optimum_count: int
    no_exact_reference_count: int
    unusable_result_count: int
    missing_overlap_predictor_count: int
    eligible_instance_count: int
    distinct_overlap_count: int
    mean_pairwise_overlap_jaccard: float | None
    mean_relative_gap: float | None
    overlap_sample_standard_deviation: float | None
    gap_sample_standard_deviation: float | None
    pearson_correlation: float | None
    ols_slope: float | None
    ols_intercept: float | None
    association_status: str
    schema_version: int = GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported gap-overlap association schema version "
                f"{self.schema_version!r}; expected "
                f"{GAP_OVERLAP_ASSOCIATION_SCHEMA_VERSION}"
            )
        for name in ("config_hash", "family", "algorithm_id", "algorithm"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.predictor != "pairwise_overlap_mean_jaccard":
            raise ValueError(
                "predictor must be 'pairwise_overlap_mean_jaccard'"
            )
        if self.response != "relative_optimality_gap":
            raise ValueError("response must be 'relative_optimality_gap'")
        if self.repetition_unit != "instance_seed":
            raise ValueError("repetition_unit must be 'instance_seed'")
        if self.association_status not in {
            "no_samples",
            "insufficient_samples",
            "constant_overlap",
            "constant_gap",
            "estimable",
        }:
            raise ValueError(
                "association_status must be no_samples, insufficient_samples, "
                "constant_overlap, constant_gap, or estimable"
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
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
            "zero_optimum_count",
            "no_exact_reference_count",
            "unusable_result_count",
            "missing_overlap_predictor_count",
            "eligible_instance_count",
            "distinct_overlap_count",
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
        if self.timeout_count + self.error_count > self.run_count:
            raise ValueError("timeout_count plus error_count cannot exceed run_count")
        if (
            self.valid_exact_reference_count + self.no_exact_reference_count
            != self.instance_count
        ):
            raise ValueError("reference counts must partition instance_count")
        if (
            self.zero_optimum_count
            + self.unusable_result_count
            + self.missing_overlap_predictor_count
            + self.eligible_instance_count
            != self.valid_exact_reference_count
        ):
            raise ValueError(
                "zero, unusable, missing-overlap, and eligible counts must "
                "partition valid exact references"
            )
        if self.distinct_overlap_count > self.eligible_instance_count:
            raise ValueError(
                "distinct_overlap_count cannot exceed eligible_instance_count"
            )

        statistics = (
            self.mean_pairwise_overlap_jaccard,
            self.mean_relative_gap,
            self.overlap_sample_standard_deviation,
            self.gap_sample_standard_deviation,
            self.pearson_correlation,
            self.ols_slope,
            self.ols_intercept,
        )
        if self.eligible_instance_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError("zero samples require blank association statistics")
            if self.distinct_overlap_count != 0:
                raise ValueError("zero samples require zero distinct overlaps")
            if self.association_status != "no_samples":
                raise ValueError("zero samples require no_samples status")
            return

        mean_overlap = self.mean_pairwise_overlap_jaccard
        mean_gap = self.mean_relative_gap
        if mean_overlap is None or not math.isfinite(mean_overlap):
            raise ValueError("positive samples require a finite mean overlap")
        if mean_gap is None or not math.isfinite(mean_gap):
            raise ValueError("positive samples require a finite mean gap")
        if not 0 <= mean_overlap <= 1:
            raise ValueError("mean pairwise overlap must be between 0 and 1")
        if not 0 <= mean_gap <= 1:
            raise ValueError("mean_relative_gap must be between 0 and 1")
        if self.distinct_overlap_count <= 0:
            raise ValueError("positive samples require a distinct overlap")

        remaining = statistics[2:]
        if self.eligible_instance_count == 1:
            if any(value is not None for value in remaining):
                raise ValueError(
                    "a singleton sample requires blank dispersion and "
                    "association fields"
                )
            if self.distinct_overlap_count != 1:
                raise ValueError("a singleton sample has one distinct overlap")
            if self.association_status != "insufficient_samples":
                raise ValueError(
                    "a singleton sample requires insufficient_samples status"
                )
            return

        overlap_sd = self.overlap_sample_standard_deviation
        gap_sd = self.gap_sample_standard_deviation
        if overlap_sd is None or not math.isfinite(overlap_sd) or overlap_sd < 0:
            raise ValueError("overlap sample SD must be finite and non-negative")
        if gap_sd is None or not math.isfinite(gap_sd) or gap_sd < 0:
            raise ValueError("gap sample SD must be finite and non-negative")

        if overlap_sd == 0:
            if self.distinct_overlap_count != 1:
                raise ValueError(
                    "zero overlap variation requires one distinct overlap"
                )
            if any(
                value is not None
                for value in (
                    self.pearson_correlation,
                    self.ols_slope,
                    self.ols_intercept,
                )
            ):
                raise ValueError(
                    "constant overlap requires blank correlation and OLS fields"
                )
            if self.association_status != "constant_overlap":
                raise ValueError(
                    "zero overlap variation requires constant_overlap status"
                )
            return

        if self.distinct_overlap_count < 2:
            raise ValueError(
                "positive overlap variation requires multiple distinct overlaps"
            )
        if gap_sd == 0:
            if self.pearson_correlation is not None:
                raise ValueError("constant gap requires blank correlation")
            if self.ols_slope != 0:
                raise ValueError("constant gap requires zero OLS slope")
            if self.ols_intercept is None or not math.isclose(
                self.ols_intercept,
                mean_gap,
                abs_tol=5e-10,
            ):
                raise ValueError(
                    "constant gap requires OLS intercept equal to mean gap"
                )
            if self.association_status != "constant_gap":
                raise ValueError(
                    "zero gap variation requires constant_gap status"
                )
            return

        correlation = self.pearson_correlation
        slope = self.ols_slope
        intercept = self.ols_intercept
        if correlation is None or not math.isfinite(correlation):
            raise ValueError("estimable association requires finite correlation")
        if not -1 <= correlation <= 1:
            raise ValueError("pearson_correlation must be between -1 and 1")
        if slope is None or not math.isfinite(slope):
            raise ValueError("estimable association requires finite OLS slope")
        if intercept is None or not math.isfinite(intercept):
            raise ValueError("estimable association requires finite OLS intercept")
        if self.association_status != "estimable":
            raise ValueError(
                "positive variation on both axes requires estimable status"
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
                list(self.case_ids),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "valid_exact_reference_count": self.valid_exact_reference_count,
            "zero_optimum_count": self.zero_optimum_count,
            "no_exact_reference_count": self.no_exact_reference_count,
            "unusable_result_count": self.unusable_result_count,
            "missing_overlap_predictor_count": (
                self.missing_overlap_predictor_count
            ),
            "eligible_instance_count": self.eligible_instance_count,
            "distinct_overlap_count": self.distinct_overlap_count,
            "mean_pairwise_overlap_jaccard": self._format_optional(
                self.mean_pairwise_overlap_jaccard
            ),
            "mean_relative_gap": self._format_optional(self.mean_relative_gap),
            "overlap_sample_standard_deviation": self._format_optional(
                self.overlap_sample_standard_deviation
            ),
            "gap_sample_standard_deviation": self._format_optional(
                self.gap_sample_standard_deviation
            ),
            "pearson_correlation": self._format_optional(
                self.pearson_correlation
            ),
            "ols_slope": self._format_optional(self.ols_slope),
            "ols_intercept": self._format_optional(self.ols_intercept),
            "association_status": self.association_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> GapOverlapAssociationRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_case_ids = json.loads(row["case_ids"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("case_ids must encode a JSON array") from error
        if not isinstance(raw_case_ids, list):
            raise ValueError("case_ids must encode a JSON array")
        def optional_float(name: str) -> float | None:
            return _parse_float(row[name], name, optional=True)

        def integer(name: str) -> int:
            return _required_int(row[name], name)

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
            timeout_count=integer("timeout_count"),
            error_count=integer("error_count"),
            valid_exact_reference_count=integer(
                "valid_exact_reference_count"
            ),
            zero_optimum_count=integer("zero_optimum_count"),
            no_exact_reference_count=integer("no_exact_reference_count"),
            unusable_result_count=integer("unusable_result_count"),
            missing_overlap_predictor_count=integer(
                "missing_overlap_predictor_count"
            ),
            eligible_instance_count=integer("eligible_instance_count"),
            distinct_overlap_count=integer("distinct_overlap_count"),
            mean_pairwise_overlap_jaccard=optional_float(
                "mean_pairwise_overlap_jaccard"
            ),
            mean_relative_gap=optional_float("mean_relative_gap"),
            overlap_sample_standard_deviation=optional_float(
                "overlap_sample_standard_deviation"
            ),
            gap_sample_standard_deviation=optional_float(
                "gap_sample_standard_deviation"
            ),
            pearson_correlation=optional_float("pearson_correlation"),
            ols_slope=optional_float("ols_slope"),
            ols_intercept=optional_float("ols_intercept"),
            association_status=row["association_status"],
            schema_version=integer("schema_version"),
        )


@dataclass(frozen=True, slots=True)
class GapClusteringAssociationRecord:
    """One P5.4 paired mixed-cluster level-mean association row."""

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
        "clustering_levels",
        "instance_count",
        "run_count",
        "independent_block_count",
        "clustering_level_count",
        "distinct_clustering_level_count",
        "eligible_block_count",
        "incomplete_block_count",
        "timeout_count",
        "error_count",
        "valid_exact_reference_count",
        "zero_optimum_count",
        "no_exact_reference_count",
        "unusable_result_count",
        "usable_gap_instance_count",
        "eligible_instance_count",
        "mean_realized_bridge_fraction",
        "mean_level_relative_gap",
        "bridge_fraction_sample_standard_deviation",
        "gap_level_mean_sample_standard_deviation",
        "pearson_correlation",
        "ols_slope",
        "ols_intercept",
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
    clustering_levels: tuple[float, ...]
    instance_count: int
    run_count: int
    independent_block_count: int
    clustering_level_count: int
    distinct_clustering_level_count: int
    eligible_block_count: int
    incomplete_block_count: int
    timeout_count: int
    error_count: int
    valid_exact_reference_count: int
    zero_optimum_count: int
    no_exact_reference_count: int
    unusable_result_count: int
    usable_gap_instance_count: int
    eligible_instance_count: int
    mean_realized_bridge_fraction: float | None
    mean_level_relative_gap: float | None
    bridge_fraction_sample_standard_deviation: float | None
    gap_level_mean_sample_standard_deviation: float | None
    pearson_correlation: float | None
    ols_slope: float | None
    ols_intercept: float | None
    association_status: str
    schema_version: int = GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported gap-clustering association schema version "
                f"{self.schema_version!r}; expected "
                f"{GAP_CLUSTERING_ASSOCIATION_SCHEMA_VERSION}"
            )
        for name in ("config_hash", "family", "algorithm_id", "algorithm"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.family != "mixed_cluster":
            raise ValueError("family must be 'mixed_cluster'")
        if self.predictor != "realized_bridge_fraction":
            raise ValueError("predictor must be 'realized_bridge_fraction'")
        if self.response != "level_mean_relative_optimality_gap":
            raise ValueError(
                "response must be 'level_mean_relative_optimality_gap'"
            )
        if self.repetition_unit != "coupling_seed_block":
            raise ValueError("repetition_unit must be 'coupling_seed_block'")
        if self.association_status not in {
            "no_complete_blocks",
            "insufficient_levels",
            "constant_clustering",
            "constant_gap",
            "estimable",
        }:
            raise ValueError(
                "association_status must be no_complete_blocks, "
                "insufficient_levels, constant_clustering, constant_gap, "
                "or estimable"
            )

        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        object.__setattr__(
            self,
            "clustering_levels",
            tuple(float(value) for value in self.clustering_levels),
        )
        if any(not isinstance(value, str) or not value for value in self.case_ids):
            raise ValueError("case_ids must contain non-empty strings")
        if tuple(sorted(set(self.case_ids))) != self.case_ids:
            raise ValueError("case_ids must be sorted and unique")
        if len(self.clustering_levels) != len(self.case_ids):
            raise ValueError("clustering_levels must align with case_ids")
        if any(
            not math.isfinite(value) or not 0 <= value <= 1
            for value in self.clustering_levels
        ):
            raise ValueError("clustering levels must be finite values in [0, 1]")

        count_names = (
            "case_count",
            "instance_count",
            "run_count",
            "independent_block_count",
            "clustering_level_count",
            "distinct_clustering_level_count",
            "eligible_block_count",
            "incomplete_block_count",
            "timeout_count",
            "error_count",
            "valid_exact_reference_count",
            "zero_optimum_count",
            "no_exact_reference_count",
            "unusable_result_count",
            "usable_gap_instance_count",
            "eligible_instance_count",
        )
        for name in count_names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.case_count <= 0 or self.case_count != len(self.case_ids):
            raise ValueError("case_count must equal the positive case_ids length")
        if self.clustering_level_count != self.case_count:
            raise ValueError("clustering_level_count must equal case_count")
        if self.distinct_clustering_level_count != len(
            set(self.clustering_levels)
        ):
            raise ValueError(
                "distinct_clustering_level_count conflicts with level values"
            )
        if self.independent_block_count <= 0:
            raise ValueError("independent_block_count must be positive")
        if (
            self.instance_count
            != self.independent_block_count * self.clustering_level_count
        ):
            raise ValueError(
                "instance_count must equal blocks times clustering levels"
            )
        if self.run_count < self.instance_count:
            raise ValueError("run_count cannot be smaller than instance_count")
        if self.timeout_count + self.error_count > self.run_count:
            raise ValueError("timeout_count plus error_count cannot exceed run_count")
        if (
            self.valid_exact_reference_count + self.no_exact_reference_count
            != self.instance_count
        ):
            raise ValueError("reference counts must partition instance_count")
        if (
            self.zero_optimum_count
            + self.unusable_result_count
            + self.usable_gap_instance_count
            != self.valid_exact_reference_count
        ):
            raise ValueError(
                "zero, unusable, and usable-gap counts must partition valid "
                "exact references"
            )
        if (
            self.eligible_block_count + self.incomplete_block_count
            != self.independent_block_count
        ):
            raise ValueError("eligible and incomplete blocks must partition blocks")
        if (
            self.eligible_instance_count
            != self.eligible_block_count * self.clustering_level_count
        ):
            raise ValueError(
                "eligible_instance_count must equal eligible blocks times levels"
            )
        if self.eligible_instance_count > self.usable_gap_instance_count:
            raise ValueError(
                "eligible instances cannot exceed usable-gap instances"
            )

        statistics = (
            self.mean_realized_bridge_fraction,
            self.mean_level_relative_gap,
            self.bridge_fraction_sample_standard_deviation,
            self.gap_level_mean_sample_standard_deviation,
            self.pearson_correlation,
            self.ols_slope,
            self.ols_intercept,
        )
        if self.eligible_block_count == 0:
            if any(value is not None for value in statistics):
                raise ValueError(
                    "no complete blocks require blank association statistics"
                )
            if self.association_status != "no_complete_blocks":
                raise ValueError(
                    "zero eligible blocks require no_complete_blocks status"
                )
            return

        mean_predictor = self.mean_realized_bridge_fraction
        mean_gap = self.mean_level_relative_gap
        if mean_predictor is None or not math.isfinite(mean_predictor):
            raise ValueError("complete blocks require a finite predictor mean")
        if mean_gap is None or not math.isfinite(mean_gap):
            raise ValueError("complete blocks require a finite level-gap mean")
        if not 0 <= mean_predictor <= 1 or not 0 <= mean_gap <= 1:
            raise ValueError("association means must be between 0 and 1")

        remaining = statistics[2:]
        if self.clustering_level_count == 1:
            if any(value is not None for value in remaining):
                raise ValueError(
                    "one clustering level requires blank dispersion and "
                    "association fields"
                )
            if self.association_status != "insufficient_levels":
                raise ValueError(
                    "one clustering level requires insufficient_levels status"
                )
            return

        predictor_sd = self.bridge_fraction_sample_standard_deviation
        gap_sd = self.gap_level_mean_sample_standard_deviation
        if (
            predictor_sd is None
            or not math.isfinite(predictor_sd)
            or predictor_sd < 0
        ):
            raise ValueError("bridge-fraction sample SD must be non-negative")
        if gap_sd is None or not math.isfinite(gap_sd) or gap_sd < 0:
            raise ValueError("gap-level-mean sample SD must be non-negative")
        if predictor_sd == 0:
            if any(
                value is not None
                for value in (
                    self.pearson_correlation,
                    self.ols_slope,
                    self.ols_intercept,
                )
            ):
                raise ValueError(
                    "constant clustering requires blank correlation and OLS"
                )
            if self.association_status != "constant_clustering":
                raise ValueError(
                    "zero predictor variation requires constant_clustering"
                )
            return
        if gap_sd == 0:
            if self.pearson_correlation is not None:
                raise ValueError("constant gap requires blank correlation")
            if self.ols_slope != 0:
                raise ValueError("constant gap requires zero OLS slope")
            if self.ols_intercept is None or not math.isclose(
                self.ols_intercept,
                mean_gap,
                abs_tol=5e-10,
            ):
                raise ValueError(
                    "constant gap requires intercept equal to mean level gap"
                )
            if self.association_status != "constant_gap":
                raise ValueError("zero gap variation requires constant_gap")
            return

        correlation = self.pearson_correlation
        if correlation is None or not math.isfinite(correlation):
            raise ValueError("estimable association requires finite correlation")
        if not -1 <= correlation <= 1:
            raise ValueError("pearson_correlation must be between -1 and 1")
        if self.ols_slope is None or not math.isfinite(self.ols_slope):
            raise ValueError("estimable association requires finite OLS slope")
        if self.ols_intercept is None or not math.isfinite(self.ols_intercept):
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
            "clustering_levels": json.dumps(
                [f"{value:.10f}" for value in self.clustering_levels],
                separators=(",", ":"),
            ),
            "instance_count": self.instance_count,
            "run_count": self.run_count,
            "independent_block_count": self.independent_block_count,
            "clustering_level_count": self.clustering_level_count,
            "distinct_clustering_level_count": (
                self.distinct_clustering_level_count
            ),
            "eligible_block_count": self.eligible_block_count,
            "incomplete_block_count": self.incomplete_block_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "valid_exact_reference_count": self.valid_exact_reference_count,
            "zero_optimum_count": self.zero_optimum_count,
            "no_exact_reference_count": self.no_exact_reference_count,
            "unusable_result_count": self.unusable_result_count,
            "usable_gap_instance_count": self.usable_gap_instance_count,
            "eligible_instance_count": self.eligible_instance_count,
            "mean_realized_bridge_fraction": self._format_optional(
                self.mean_realized_bridge_fraction
            ),
            "mean_level_relative_gap": self._format_optional(
                self.mean_level_relative_gap
            ),
            "bridge_fraction_sample_standard_deviation": self._format_optional(
                self.bridge_fraction_sample_standard_deviation
            ),
            "gap_level_mean_sample_standard_deviation": self._format_optional(
                self.gap_level_mean_sample_standard_deviation
            ),
            "pearson_correlation": self._format_optional(
                self.pearson_correlation
            ),
            "ols_slope": self._format_optional(self.ols_slope),
            "ols_intercept": self._format_optional(self.ols_intercept),
            "association_status": self.association_status,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(
        cls, row: Mapping[str, str]
    ) -> GapClusteringAssociationRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        try:
            raw_case_ids = json.loads(row["case_ids"])
            raw_levels = json.loads(row["clustering_levels"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                "case_ids and clustering_levels must encode JSON arrays"
            ) from error
        if not isinstance(raw_case_ids, list) or not isinstance(raw_levels, list):
            raise ValueError(
                "case_ids and clustering_levels must encode JSON arrays"
            )

        def integer(name: str) -> int:
            return _required_int(row[name], name)

        def optional_float(name: str) -> float | None:
            return _parse_float(row[name], name, optional=True)

        try:
            levels = tuple(float(value) for value in raw_levels)
        except (TypeError, ValueError) as error:
            raise ValueError("clustering_levels must contain numbers") from error
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
            clustering_levels=levels,
            instance_count=integer("instance_count"),
            run_count=integer("run_count"),
            independent_block_count=integer("independent_block_count"),
            clustering_level_count=integer("clustering_level_count"),
            distinct_clustering_level_count=integer(
                "distinct_clustering_level_count"
            ),
            eligible_block_count=integer("eligible_block_count"),
            incomplete_block_count=integer("incomplete_block_count"),
            timeout_count=integer("timeout_count"),
            error_count=integer("error_count"),
            valid_exact_reference_count=integer(
                "valid_exact_reference_count"
            ),
            zero_optimum_count=integer("zero_optimum_count"),
            no_exact_reference_count=integer("no_exact_reference_count"),
            unusable_result_count=integer("unusable_result_count"),
            usable_gap_instance_count=integer("usable_gap_instance_count"),
            eligible_instance_count=integer("eligible_instance_count"),
            mean_realized_bridge_fraction=optional_float(
                "mean_realized_bridge_fraction"
            ),
            mean_level_relative_gap=optional_float("mean_level_relative_gap"),
            bridge_fraction_sample_standard_deviation=optional_float(
                "bridge_fraction_sample_standard_deviation"
            ),
            gap_level_mean_sample_standard_deviation=optional_float(
                "gap_level_mean_sample_standard_deviation"
            ),
            pearson_correlation=optional_float("pearson_correlation"),
            ols_slope=optional_float("ols_slope"),
            ols_intercept=optional_float("ols_intercept"),
            association_status=row["association_status"],
            schema_version=integer("schema_version"),
        )


GapDensityAssociationRecord.__module__ = "maxcover.contracts"
GapOverlapAssociationRecord.__module__ = "maxcover.contracts"
GapClusteringAssociationRecord.__module__ = "maxcover.contracts"
