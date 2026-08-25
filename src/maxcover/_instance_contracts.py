"""Private instance record contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar

from ._contract_csv import (
    _parse_bool,
    _parse_float,
    _parse_int,
    _required_float,
    _required_int,
    _validate_csv_fields,
)


INSTANCE_RECORD_SCHEMA_VERSION = 2
P4_3_RESEARCH_QUESTION_IDS: Mapping[str, str] = MappingProxyType(
    {
        "fixed_size": "fixed_size_set_size_variation",
        "long_tail": "long_tail_coverage_skew",
        "duplicate_heavy": "duplicate_heavy_redundancy",
        "dominated_heavy": "dominated_heavy_pruning",
        "mixed_cluster": "mixed_cluster_bridges",
    }
)
P4_3_INSTANCE_ORIGINS: Mapping[str, str] = MappingProxyType(
    {
        "fixed_size": "stochastic",
        "long_tail": "stochastic",
        "duplicate_heavy": "stochastic",
        "dominated_heavy": "constructed",
        "mixed_cluster": "stochastic",
    }
)
P4_3_COUPLED_FAMILIES = frozenset(
    {"long_tail", "duplicate_heavy", "dominated_heavy", "mixed_cluster"}
)


def _validate_instance_record_schema_version(value: int) -> None:
    if value != INSTANCE_RECORD_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported instance record schema version {value!r}; "
            f"expected {INSTANCE_RECORD_SCHEMA_VERSION}"
        )


def _record_parameter_int(
    parameters: Mapping[str, object],
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def _record_parameter_number(
    parameters: Mapping[str, object],
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and numeric > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return numeric


def _require_record_parameter_keys(
    family: str,
    parameters: Mapping[str, object],
    expected: set[str],
) -> None:
    actual = set(parameters)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(
            f"{family} parameters have missing {missing!r} or unknown {unknown!r} fields"
        )


def _validate_p4_3_record_parameters(
    record: InstanceRecord,
    parameters: Mapping[str, object],
) -> None:
    family = record.family
    if family == "fixed_size":
        expected = {"set_size", "unique_sets"}
        if "coupling_seed" in parameters:
            expected.add("coupling_seed")
        _require_record_parameter_keys(family, parameters, expected)
        set_size = _record_parameter_int(
            parameters,
            "set_size",
            minimum=1,
            maximum=record.universe_size,
        )
        unique_sets = parameters.get("unique_sets")
        if not isinstance(unique_sets, bool):
            raise ValueError("unique_sets must be a boolean")
        if unique_sets and record.set_count > math.comb(
            record.universe_size, set_size
        ):
            raise ValueError("set_count exceeds the distinct fixed-size capacity")
        if unique_sets and record.unique_set_count != record.set_count:
            raise ValueError(
                "unique_sets requires every measured candidate set to be unique"
            )
        if "coupling_seed" in parameters:
            _record_parameter_int(parameters, "coupling_seed")
            if unique_sets:
                raise ValueError(
                    "unique_sets must be false for a paired uniform control"
                )
    elif family == "long_tail":
        _require_record_parameter_keys(
            family,
            parameters,
            {"set_size", "gamma", "coupling_seed"},
        )
        set_size = _record_parameter_int(
            parameters,
            "set_size",
            minimum=1,
            maximum=record.universe_size,
        )
        _record_parameter_number(parameters, "gamma", minimum=0)
        _record_parameter_int(parameters, "coupling_seed")
    elif family == "duplicate_heavy":
        _require_record_parameter_keys(
            family,
            parameters,
            {
                "base_set_count",
                "set_size",
                "copy_factor",
                "coupling_seed",
            },
        )
        base_set_count = _record_parameter_int(
            parameters, "base_set_count", minimum=1
        )
        set_size = _record_parameter_int(
            parameters,
            "set_size",
            minimum=1,
            maximum=record.universe_size,
        )
        copy_factor = _record_parameter_int(
            parameters, "copy_factor", minimum=1
        )
        _record_parameter_int(parameters, "coupling_seed")
        if record.k > base_set_count:
            raise ValueError("k must not exceed base_set_count")
        if base_set_count > math.comb(record.universe_size, set_size):
            raise ValueError("base_set_count exceeds the distinct set capacity")
        if record.set_count != base_set_count * copy_factor:
            raise ValueError("duplicate_heavy set_count conflicts with parameters")
        if (
            record.unique_set_count != base_set_count
            or record.duplicate_set_count
            != base_set_count * (copy_factor - 1)
            or record.dominated_set_count != 0
        ):
            raise ValueError("duplicate_heavy structure conflicts with parameters")
    elif family == "dominated_heavy":
        _require_record_parameter_keys(
            family,
            parameters,
            {"anchor_count", "anchor_size", "child_count", "coupling_seed"},
        )
        anchor_count = _record_parameter_int(
            parameters, "anchor_count", minimum=1
        )
        anchor_size = _record_parameter_int(
            parameters, "anchor_size", minimum=1
        )
        child_count = _record_parameter_int(
            parameters, "child_count", minimum=0
        )
        _record_parameter_int(parameters, "coupling_seed")
        if child_count > (1 << anchor_size) - 2:
            raise ValueError("child_count exceeds the proper-subset capacity")
        if record.k > anchor_count:
            raise ValueError("k must not exceed anchor_count")
        if (
            record.universe_size != anchor_count * anchor_size
            or record.set_count != anchor_count * (child_count + 1)
        ):
            raise ValueError("dominated_heavy dimensions conflict with parameters")
        if (
            record.unique_set_count != record.set_count
            or record.duplicate_set_count != 0
            or record.dominated_set_count != anchor_count * child_count
            or record.preprocessed_set_count != anchor_count
        ):
            raise ValueError("dominated_heavy structure conflicts with parameters")
        return
    elif family == "mixed_cluster":
        _require_record_parameter_keys(
            family,
            parameters,
            {
                "clusters",
                "set_size",
                "bridge_fraction",
                "bridge_count",
                "realized_bridge_fraction",
                "coupling_seed",
            },
        )
        clusters = _record_parameter_int(
            parameters,
            "clusters",
            minimum=2,
            maximum=record.universe_size,
        )
        set_size = _record_parameter_int(
            parameters,
            "set_size",
            minimum=1,
            maximum=record.universe_size,
        )
        bridge_fraction = _record_parameter_number(
            parameters, "bridge_fraction", minimum=0, maximum=1
        )
        bridge_count = _record_parameter_int(
            parameters,
            "bridge_count",
            minimum=0,
            maximum=record.set_count,
        )
        realized_fraction = _record_parameter_number(
            parameters,
            "realized_bridge_fraction",
            minimum=0,
            maximum=1,
        )
        _record_parameter_int(parameters, "coupling_seed")
        expected_bridge_count = math.floor(
            record.set_count * bridge_fraction + 0.5
        )
        if bridge_count != expected_bridge_count or not math.isclose(
            realized_fraction,
            bridge_count / record.set_count,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError("mixed_cluster bridge fields conflict")
        if bridge_count > 0 and set_size < 2:
            raise ValueError("set_size must be at least 2 when bridges are generated")
        cluster_sizes = tuple(
            record.universe_size // clusters
            + (1 if cluster < record.universe_size % clusters else 0)
            for cluster in range(clusters)
        )
        lower_bridge_size = set_size // 2
        upper_bridge_size = set_size - lower_bridge_size
        for index in range(record.set_count):
            preferred = index % clusters
            adjacent = (preferred + 1) % clusters
            if (
                bridge_count < record.set_count
                and set_size > cluster_sizes[preferred]
            ):
                raise ValueError("set_size does not fit a specialist cluster")
            if bridge_count > 0 and (
                lower_bridge_size > cluster_sizes[preferred]
                or upper_bridge_size > cluster_sizes[adjacent]
            ):
                raise ValueError("set_size does not fit both bridge clusters")
    else:
        raise ValueError(f"unsupported P4.3 family {family!r}")

    if record.incidence_count != record.set_count * set_size:
        raise ValueError(f"{family} incidence_count conflicts with set_size")


def _validate_paired_uniform_record_parameters(
    record: InstanceRecord,
    parameters: Mapping[str, object],
) -> None:
    _require_record_parameter_keys(
        record.family,
        parameters,
        {"density", "paired_set_size", "coupling_seed"},
    )
    density = _record_parameter_number(
        parameters, "density", minimum=0, maximum=1
    )
    if density <= 0:
        raise ValueError("density must be positive")
    paired_set_size = _record_parameter_int(
        parameters,
        "paired_set_size",
        minimum=2,
        maximum=record.universe_size,
    )
    _record_parameter_int(parameters, "coupling_seed")
    expected_size = (
        record.universe_size * density
        + (1.0 - density) ** record.universe_size
    )
    if not math.isclose(
        expected_size,
        paired_set_size,
        rel_tol=1e-10,
        abs_tol=1e-10,
    ):
        raise ValueError(
            "uniform density conflicts with the paired fixed set size"
        )


@dataclass(frozen=True, slots=True)
class InstanceRecord:
    """One exact instance-level structure record shared by CSV and reporting."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "config_hash",
        "case_id",
        "repetition",
        "instance_id",
        "seed",
        "coupling_pair_id",
        "coupling_seed",
        "family",
        "generator_version",
        "research_question_id",
        "instance_origin",
        "is_adversarial",
        "universe_size",
        "set_count",
        "k",
        "parameters",
        "incidence_count",
        "covered_element_count",
        "unique_set_count",
        "actual_density",
        "mean_set_size",
        "pairwise_overlap_mean_jaccard",
        "pairwise_overlap_total_pairs",
        "pairwise_overlap_valid_pairs",
        "coverage_skew_gini",
        "duplicate_set_count",
        "duplicate_set_ratio",
        "dominated_set_count",
        "dominated_set_ratio",
        "dominated_unique_ratio",
        "preprocessed_set_count",
        "adversarial_severity",
        "realized_trap_fraction",
        "known_optimum",
        "optimum_source",
        "optimum_selected",
        "proof_kind",
        "schema_version",
    )

    config_hash: str
    case_id: str
    repetition: int
    instance_id: str
    seed: int | None
    family: str
    generator_version: int
    instance_origin: str
    is_adversarial: bool
    universe_size: int
    set_count: int
    k: int
    parameters: str
    incidence_count: int
    covered_element_count: int
    unique_set_count: int
    actual_density: float
    mean_set_size: float
    pairwise_overlap_mean_jaccard: float | None
    pairwise_overlap_total_pairs: int
    pairwise_overlap_valid_pairs: int
    coverage_skew_gini: float
    duplicate_set_count: int
    duplicate_set_ratio: float
    dominated_set_count: int
    dominated_set_ratio: float
    dominated_unique_ratio: float
    preprocessed_set_count: int
    coupling_pair_id: str | None = None
    coupling_seed: int | None = None
    research_question_id: str | None = None
    adversarial_severity: float | None = None
    realized_trap_fraction: float | None = None
    known_optimum: int | None = None
    optimum_source: str | None = None
    optimum_selected: tuple[int, ...] | None = None
    proof_kind: str | None = None
    schema_version: int = INSTANCE_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_instance_record_schema_version(self.schema_version)
        for name in ("config_hash", "case_id", "instance_id", "family"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.instance_origin not in {"stochastic", "constructed", "custom"}:
            raise ValueError("instance_origin must be stochastic, constructed, or custom")
        if not isinstance(self.is_adversarial, bool):
            raise TypeError("is_adversarial must be a boolean")
        for name in ("coupling_pair_id", "research_question_id", "optimum_source", "proof_kind"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be a non-empty string or None")

        integer_fields = (
            "repetition",
            "generator_version",
            "universe_size",
            "set_count",
            "k",
            "incidence_count",
            "covered_element_count",
            "unique_set_count",
            "pairwise_overlap_total_pairs",
            "pairwise_overlap_valid_pairs",
            "duplicate_set_count",
            "dominated_set_count",
            "preprocessed_set_count",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        for name in ("seed", "coupling_seed", "known_optimum"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise TypeError(f"{name} must be an integer or None")
        if (self.coupling_pair_id is None) != (self.coupling_seed is None):
            raise ValueError("coupling_pair_id and coupling_seed must be both present or absent")

        if self.repetition < 0 or self.generator_version <= 0:
            raise ValueError("repetition must be non-negative and generator_version positive")
        if self.universe_size <= 0 or self.set_count <= 0:
            raise ValueError("universe_size and set_count must be positive")
        if not 1 <= self.k <= self.set_count:
            raise ValueError("k must be between 1 and set_count")
        if not 0 <= self.incidence_count <= self.universe_size * self.set_count:
            raise ValueError("incidence_count is outside the instance bounds")
        if not 0 <= self.covered_element_count <= self.universe_size:
            raise ValueError("covered_element_count is outside the universe")
        if not 1 <= self.unique_set_count <= self.set_count:
            raise ValueError("unique_set_count must be between 1 and set_count")

        try:
            parameters = json.loads(self.parameters)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("parameters must be a JSON object string") from error
        if not isinstance(parameters, dict):
            raise ValueError("parameters must encode a JSON object")
        object.__setattr__(
            self, "parameters", json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        )

        ratio_fields = (
            "actual_density",
            "pairwise_overlap_mean_jaccard",
            "coverage_skew_gini",
            "duplicate_set_ratio",
            "dominated_set_ratio",
            "dominated_unique_ratio",
            "adversarial_severity",
            "realized_trap_fraction",
        )
        for name in ratio_fields:
            value = getattr(self, name)
            if value is not None and (
                not math.isfinite(value) or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be between 0 and 1 or None")
        if not math.isfinite(self.mean_set_size) or not (
            0 <= self.mean_set_size <= self.universe_size
        ):
            raise ValueError("mean_set_size is outside the instance bounds")

        expected_density = self.incidence_count / (self.universe_size * self.set_count)
        expected_mean = self.incidence_count / self.set_count
        if not math.isclose(
            self.actual_density, expected_density, rel_tol=1e-12, abs_tol=1e-15
        ):
            raise ValueError("actual_density does not match incidence_count")
        if not math.isclose(
            self.mean_set_size, expected_mean, rel_tol=1e-12, abs_tol=1e-15
        ):
            raise ValueError("mean_set_size does not match incidence_count")

        expected_pairs = self.set_count * (self.set_count - 1) // 2
        if self.pairwise_overlap_total_pairs != expected_pairs:
            raise ValueError("pairwise_overlap_total_pairs does not match set_count")
        if not 0 <= self.pairwise_overlap_valid_pairs <= expected_pairs:
            raise ValueError("pairwise_overlap_valid_pairs is outside the pair bounds")
        if (self.pairwise_overlap_mean_jaccard is None) != (
            self.pairwise_overlap_valid_pairs == 0
        ):
            raise ValueError("pairwise overlap value conflicts with valid pair count")

        if self.duplicate_set_count != self.set_count - self.unique_set_count:
            raise ValueError("duplicate_set_count conflicts with unique_set_count")
        if not 0 <= self.dominated_set_count <= self.unique_set_count - 1:
            raise ValueError("dominated_set_count is outside the unique-set bounds")
        if self.preprocessed_set_count != self.unique_set_count - self.dominated_set_count:
            raise ValueError("preprocessed_set_count conflicts with dominated_set_count")
        expected_ratios = (
            (self.duplicate_set_ratio, self.duplicate_set_count / self.set_count),
            (self.dominated_set_ratio, self.dominated_set_count / self.set_count),
            (self.dominated_unique_ratio, self.dominated_set_count / self.unique_set_count),
        )
        if any(
            not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15)
            for actual, expected in expected_ratios
        ):
            raise ValueError("duplicate or dominated ratios conflict with counts")

        if self.known_optimum is not None and not 0 <= self.known_optimum <= self.universe_size:
            raise ValueError("known_optimum is outside the universe")
        if self.optimum_selected is not None:
            selected = tuple(self.optimum_selected)
            if any(
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < self.set_count
                for index in selected
            ):
                raise ValueError("optimum_selected contains an invalid index")
            if tuple(sorted(set(selected))) != selected or len(selected) > self.k:
                raise ValueError("optimum_selected must be sorted, unique, and within budget")
            object.__setattr__(self, "optimum_selected", selected)
        certificate_values = (
            self.known_optimum,
            self.optimum_source,
            self.optimum_selected,
            self.proof_kind,
        )
        if any(value is not None for value in certificate_values) and any(
            value is None for value in certificate_values
        ):
            raise ValueError("known optimum certificate fields must be all present or all absent")
        if self.proof_kind is not None and self.proof_kind not in {
            "covers_universe",
            "disjoint_anchors",
        }:
            raise ValueError("unsupported known optimum proof kind")
        if self.proof_kind == "covers_universe" and self.known_optimum != self.universe_size:
            raise ValueError("covers_universe certificate must equal universe_size")
        if (
            self.proof_kind == "disjoint_anchors"
            and self.family != "dominated_heavy"
        ):
            raise ValueError(
                "disjoint_anchors proof requires a dominated_heavy instance"
            )

        if self.family == "adversarial" and self.generator_version == 1:
            if self.instance_origin != "constructed" or not self.is_adversarial:
                raise ValueError("legacy adversarial instances must be constructed/adversarial")
            if (
                self.adversarial_severity is not None
                or self.realized_trap_fraction is not None
            ):
                raise ValueError("legacy adversarial structure fields must remain unknown")
            if any(value is not None for value in certificate_values):
                raise ValueError("legacy adversarial certificate fields must remain unknown")
            if "construction_version" in parameters:
                raise ValueError("legacy adversarial parameters must omit construction_version")
            if self.coupling_pair_id is not None or self.coupling_seed is not None:
                raise ValueError("legacy adversarial coupling fields must remain unknown")
        elif self.family == "adversarial" and self.generator_version == 2:
            if self.instance_origin != "constructed":
                raise ValueError("version-2 adversarial instances must be constructed")
            required_parameters = (
                "block_size",
                "distractor_count",
                "construction_version",
                "trap_count",
                "coupling_seed",
            )
            if any(name not in parameters for name in required_parameters):
                raise ValueError("version-2 adversarial parameters are incomplete")
            block_size = parameters["block_size"]
            distractor_count = parameters["distractor_count"]
            construction_version = parameters["construction_version"]
            trap_count = parameters["trap_count"]
            parameter_coupling_seed = parameters["coupling_seed"]
            if (
                isinstance(construction_version, bool)
                or not isinstance(construction_version, int)
                or construction_version != 2
            ):
                raise ValueError("version-2 construction_version must be integer 2")
            if (
                isinstance(block_size, bool)
                or not isinstance(block_size, int)
                or isinstance(distractor_count, bool)
                or not isinstance(distractor_count, int)
                or isinstance(trap_count, bool)
                or not isinstance(trap_count, int)
                or isinstance(parameter_coupling_seed, bool)
                or not isinstance(parameter_coupling_seed, int)
            ):
                raise ValueError("version-2 adversarial parameters are invalid")
            if block_size < 4 or distractor_count < 0:
                raise ValueError("version-2 adversarial parameters are outside bounds")
            if not block_size // 2 + 1 <= trap_count <= block_size:
                raise ValueError("version-2 trap_count is outside the legal range")
            if (
                self.universe_size != 2 * block_size
                or self.set_count != 3 + distractor_count
                or self.k != 2
            ):
                raise ValueError("version-2 adversarial dimensions conflict with block_size")
            expected_severity = (block_size - trap_count) / (2 * block_size)
            expected_fraction = trap_count / block_size
            if self.adversarial_severity is None or not math.isclose(
                self.adversarial_severity,
                expected_severity,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("version-2 adversarial severity conflicts with parameters")
            if self.realized_trap_fraction is None or not math.isclose(
                self.realized_trap_fraction,
                expected_fraction,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("version-2 trap fraction conflicts with parameters")
            if self.is_adversarial != (expected_severity > 0):
                raise ValueError("version-2 adversarial classification conflicts with severity")
            if self.coupling_pair_id is None or self.coupling_seed is None:
                raise ValueError("version-2 adversarial coupling fields are required")
            if parameters["coupling_seed"] != self.coupling_seed:
                raise ValueError("version-2 coupling seed conflicts with parameters")
            if self.research_question_id != "adversarial_severity":
                raise ValueError("version-2 research question ID is invalid")
            if (
                self.known_optimum != self.universe_size
                or self.optimum_source != "constructed_certificate"
                or self.optimum_selected != (1, 2)
                or self.proof_kind != "covers_universe"
            ):
                raise ValueError("version-2 adversarial certificate is invalid")
        elif self.family == "adversarial":
            raise ValueError("unsupported adversarial generator version")
        elif self.family in P4_3_RESEARCH_QUESTION_IDS:
            _validate_p4_3_record_parameters(self, parameters)
            expected_origin = P4_3_INSTANCE_ORIGINS[self.family]
            expected_question = P4_3_RESEARCH_QUESTION_IDS[self.family]
            if self.generator_version != 1:
                raise ValueError("P4.3 instance families require generator version 1")
            if self.instance_origin != expected_origin:
                raise ValueError(
                    f"{self.family} instances must have {expected_origin} origin"
                )
            if self.is_adversarial:
                raise ValueError("P4.3 instance families are not adversarial")
            if (
                self.adversarial_severity is not None
                or self.realized_trap_fraction is not None
            ):
                raise ValueError("P4.3 adversarial structure fields must remain unknown")
            if self.research_question_id != expected_question:
                raise ValueError(f"{self.family} research question ID is invalid")

            if self.family in P4_3_COUPLED_FAMILIES:
                if self.coupling_pair_id is None or self.coupling_seed is None:
                    raise ValueError(f"{self.family} coupling fields are required")
                if parameters.get("coupling_seed") != self.coupling_seed:
                    raise ValueError(
                        f"{self.family} coupling seed conflicts with parameters"
                    )
            else:
                parameter_seed = parameters.get("coupling_seed")
                if parameter_seed is None:
                    if (
                        self.coupling_pair_id is not None
                        or self.coupling_seed is not None
                    ):
                        raise ValueError(
                            "unpaired fixed_size coupling fields must remain unknown"
                        )
                elif (
                    self.coupling_pair_id is None
                    or self.coupling_seed is None
                    or parameter_seed != self.coupling_seed
                ):
                    raise ValueError(
                        "fixed_size coupling seed conflicts with parameters"
                    )

            if self.family == "dominated_heavy":
                anchor_count = parameters.get("anchor_count")
                anchor_size = parameters.get("anchor_size")
                child_count = parameters.get("child_count")
                if any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in (anchor_count, anchor_size, child_count)
                ):
                    raise ValueError("dominated_heavy certificate parameters are invalid")
                assert isinstance(anchor_count, int)
                assert isinstance(anchor_size, int)
                assert isinstance(child_count, int)
                if (
                    anchor_count <= 0
                    or anchor_size <= 0
                    or child_count < 0
                    or self.k > anchor_count
                ):
                    raise ValueError("dominated_heavy certificate parameters are outside bounds")
                if (
                    self.universe_size != anchor_count * anchor_size
                    or self.set_count != anchor_count * (child_count + 1)
                ):
                    raise ValueError("dominated_heavy dimensions conflict with parameters")
                if (
                    self.known_optimum != self.k * anchor_size
                    or self.optimum_source != "constructed_certificate"
                    or self.optimum_selected != tuple(range(self.k))
                    or self.proof_kind != "disjoint_anchors"
                ):
                    raise ValueError("dominated_heavy certificate is invalid")
            elif any(value is not None for value in certificate_values):
                raise ValueError(
                    f"{self.family} known optimum certificate fields must remain unknown"
                )
        elif (
            self.family == "uniform"
            and (
                "paired_set_size" in parameters
                or self.research_question_id
                == P4_3_RESEARCH_QUESTION_IDS["fixed_size"]
            )
        ):
            _validate_paired_uniform_record_parameters(self, parameters)
            if (
                self.research_question_id
                != P4_3_RESEARCH_QUESTION_IDS["fixed_size"]
            ):
                raise ValueError(
                    "paired uniform research question ID is required"
                )
            if self.generator_version != 1:
                raise ValueError("paired uniform controls require generator version 1")
            if self.instance_origin != "stochastic" or self.is_adversarial:
                raise ValueError(
                    "paired uniform controls must be stochastic and non-adversarial"
                )
            if self.adversarial_severity is not None or self.realized_trap_fraction is not None:
                raise ValueError(
                    "paired uniform adversarial structure fields must remain unknown"
                )
            if self.coupling_pair_id is None or self.coupling_seed is None:
                raise ValueError("paired uniform coupling fields are required")
            if parameters.get("coupling_seed") != self.coupling_seed:
                raise ValueError(
                    "paired uniform coupling seed conflicts with parameters"
                )
            if any(value is not None for value in certificate_values):
                raise ValueError(
                    "paired uniform certificate fields must remain unknown"
                )
        elif self.instance_origin == "stochastic":
            if self.is_adversarial:
                raise ValueError("stochastic instances cannot be adversarial")
            if self.adversarial_severity is not None or self.realized_trap_fraction is not None:
                raise ValueError("stochastic adversarial structure fields must remain unknown")
            if self.coupling_pair_id is not None or self.coupling_seed is not None:
                raise ValueError("stochastic coupling fields must remain unknown")
            if self.research_question_id is not None:
                raise ValueError("stochastic research question ID must remain unknown")
            if any(value is not None for value in certificate_values):
                raise ValueError("stochastic certificate fields must remain unknown")

    def to_csv_row(self) -> dict[str, object]:
        optional = lambda value: "" if value is None else value
        selected = (
            ""
            if self.optimum_selected is None
            else json.dumps(list(self.optimum_selected), separators=(",", ":"))
        )
        return {
            "config_hash": self.config_hash,
            "case_id": self.case_id,
            "repetition": self.repetition,
            "instance_id": self.instance_id,
            "seed": optional(self.seed),
            "coupling_pair_id": optional(self.coupling_pair_id),
            "coupling_seed": optional(self.coupling_seed),
            "family": self.family,
            "generator_version": self.generator_version,
            "research_question_id": optional(self.research_question_id),
            "instance_origin": self.instance_origin,
            "is_adversarial": self.is_adversarial,
            "universe_size": self.universe_size,
            "set_count": self.set_count,
            "k": self.k,
            "parameters": self.parameters,
            "incidence_count": self.incidence_count,
            "covered_element_count": self.covered_element_count,
            "unique_set_count": self.unique_set_count,
            "actual_density": format(self.actual_density, ".17g"),
            "mean_set_size": format(self.mean_set_size, ".17g"),
            "pairwise_overlap_mean_jaccard": optional(
                None
                if self.pairwise_overlap_mean_jaccard is None
                else format(self.pairwise_overlap_mean_jaccard, ".17g")
            ),
            "pairwise_overlap_total_pairs": self.pairwise_overlap_total_pairs,
            "pairwise_overlap_valid_pairs": self.pairwise_overlap_valid_pairs,
            "coverage_skew_gini": format(self.coverage_skew_gini, ".17g"),
            "duplicate_set_count": self.duplicate_set_count,
            "duplicate_set_ratio": format(self.duplicate_set_ratio, ".17g"),
            "dominated_set_count": self.dominated_set_count,
            "dominated_set_ratio": format(self.dominated_set_ratio, ".17g"),
            "dominated_unique_ratio": format(self.dominated_unique_ratio, ".17g"),
            "preprocessed_set_count": self.preprocessed_set_count,
            "adversarial_severity": optional(
                None
                if self.adversarial_severity is None
                else format(self.adversarial_severity, ".17g")
            ),
            "realized_trap_fraction": optional(
                None
                if self.realized_trap_fraction is None
                else format(self.realized_trap_fraction, ".17g")
            ),
            "known_optimum": optional(self.known_optimum),
            "optimum_source": optional(self.optimum_source),
            "optimum_selected": selected,
            "proof_kind": optional(self.proof_kind),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> InstanceRecord:
        _validate_csv_fields(row, cls.CSV_FIELDS)
        schema_version = _required_int(row["schema_version"], "schema_version")
        _validate_instance_record_schema_version(schema_version)
        selected_text = row["optimum_selected"]
        selected: tuple[int, ...] | None = None
        if selected_text:
            try:
                raw_selected = json.loads(selected_text)
            except json.JSONDecodeError as error:
                raise ValueError("CSV field 'optimum_selected' must be a JSON array") from error
            if not isinstance(raw_selected, list):
                raise ValueError("CSV field 'optimum_selected' must be a JSON array")
            selected = tuple(raw_selected)
        return cls(
            config_hash=row["config_hash"],
            case_id=row["case_id"],
            repetition=_required_int(row["repetition"], "repetition"),
            instance_id=row["instance_id"],
            seed=_parse_int(row["seed"], "seed", optional=True),
            coupling_pair_id=row["coupling_pair_id"] or None,
            coupling_seed=_parse_int(row["coupling_seed"], "coupling_seed", optional=True),
            family=row["family"],
            generator_version=_required_int(row["generator_version"], "generator_version"),
            research_question_id=row["research_question_id"] or None,
            instance_origin=row["instance_origin"],
            is_adversarial=_parse_bool(row["is_adversarial"], "is_adversarial"),
            universe_size=_required_int(row["universe_size"], "universe_size"),
            set_count=_required_int(row["set_count"], "set_count"),
            k=_required_int(row["k"], "k"),
            parameters=row["parameters"],
            incidence_count=_required_int(row["incidence_count"], "incidence_count"),
            covered_element_count=_required_int(
                row["covered_element_count"], "covered_element_count"
            ),
            unique_set_count=_required_int(row["unique_set_count"], "unique_set_count"),
            actual_density=_required_float(row["actual_density"], "actual_density"),
            mean_set_size=_required_float(row["mean_set_size"], "mean_set_size"),
            pairwise_overlap_mean_jaccard=_parse_float(
                row["pairwise_overlap_mean_jaccard"],
                "pairwise_overlap_mean_jaccard",
                optional=True,
            ),
            pairwise_overlap_total_pairs=_required_int(
                row["pairwise_overlap_total_pairs"], "pairwise_overlap_total_pairs"
            ),
            pairwise_overlap_valid_pairs=_required_int(
                row["pairwise_overlap_valid_pairs"], "pairwise_overlap_valid_pairs"
            ),
            coverage_skew_gini=_required_float(
                row["coverage_skew_gini"], "coverage_skew_gini"
            ),
            duplicate_set_count=_required_int(
                row["duplicate_set_count"], "duplicate_set_count"
            ),
            duplicate_set_ratio=_required_float(
                row["duplicate_set_ratio"], "duplicate_set_ratio"
            ),
            dominated_set_count=_required_int(
                row["dominated_set_count"], "dominated_set_count"
            ),
            dominated_set_ratio=_required_float(
                row["dominated_set_ratio"], "dominated_set_ratio"
            ),
            dominated_unique_ratio=_required_float(
                row["dominated_unique_ratio"], "dominated_unique_ratio"
            ),
            preprocessed_set_count=_required_int(
                row["preprocessed_set_count"], "preprocessed_set_count"
            ),
            adversarial_severity=_parse_float(
                row["adversarial_severity"], "adversarial_severity", optional=True
            ),
            realized_trap_fraction=_parse_float(
                row["realized_trap_fraction"], "realized_trap_fraction", optional=True
            ),
            known_optimum=_parse_int(row["known_optimum"], "known_optimum", optional=True),
            optimum_source=row["optimum_source"] or None,
            optimum_selected=selected,
            proof_kind=row["proof_kind"] or None,
            schema_version=schema_version,
        )


InstanceRecord.__module__ = "maxcover.contracts"
