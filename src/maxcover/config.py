"""Typed experiment configuration loading and validation."""

from __future__ import annotations

import json
import math
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeGuard, cast

from .algorithms import ALGORITHMS
from .contracts import AlgorithmRunOptions
from .generators import GENERATORS
from .model import MaximumCoverageInstance


CONFIG_SCHEMA_VERSION = 3
LEGACY_CONFIG_SCHEMA_VERSION = 1
PREVIOUS_CONFIG_SCHEMA_VERSION = 2


class LegacyConfigWarning(FutureWarning):
    """A schema-v1 configuration was migrated to the current schema."""


class ConfigurationError(ValueError):
    """One or more path-addressed errors in an experiment configuration."""

    def __init__(self, issues: list[tuple[str, str]] | tuple[tuple[str, str], ...]):
        if not issues:
            raise ValueError("configuration errors require at least one issue")
        self.issues = tuple(issues)
        details = "\n".join(f"- {path}: {message}" for path, message in self.issues)
        super().__init__(f"invalid experiment configuration:\n{details}")


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_nonempty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class AlgorithmConfig:
    """One registered algorithm and its resolved execution options."""

    name: str
    options: AlgorithmRunOptions
    enabled: bool = True
    algorithm_id: str = ""
    algorithm_seeds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_string("algorithm name", self.name)
        if self.name not in ALGORITHMS:
            raise ValueError(f"unknown algorithm {self.name!r}")
        if not isinstance(self.options, AlgorithmRunOptions):
            raise TypeError("algorithm options must be AlgorithmRunOptions")
        if not isinstance(self.enabled, bool):
            raise TypeError("algorithm enabled must be a boolean")
        algorithm_id = self.name if not self.algorithm_id else self.algorithm_id
        _require_nonempty_string("algorithm id", algorithm_id)
        object.__setattr__(self, "algorithm_id", algorithm_id)
        object.__setattr__(self, "algorithm_seeds", tuple(self.algorithm_seeds))
        if any(not _is_integer(seed) for seed in self.algorithm_seeds):
            raise TypeError("algorithm seeds must be integers")
        if len(set(self.algorithm_seeds)) != len(self.algorithm_seeds):
            raise ValueError("algorithm seeds must be unique")
        specification = ALGORITHMS[self.name]
        if specification.uses_random_seed and not self.algorithm_seeds:
            raise ValueError(
                f"algorithm {self.name!r} requires explicit algorithm_seeds"
            )
        if not specification.uses_random_seed and self.algorithm_seeds:
            raise ValueError(
                f"deterministic algorithm {self.name!r} rejects algorithm_seeds"
            )
        specification.validate_options(self.options)


@dataclass(frozen=True, slots=True)
class CaseConfig:
    """One named, validated generator configuration."""

    name: str
    family: str
    parameters: Mapping[str, object]
    case_id: str = ""
    seed_group: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_string("case name", self.name)
        case_id = self.name if self.case_id == "" else self.case_id
        _require_nonempty_string("case_id", case_id)
        if self.seed_group is not None:
            _require_nonempty_string("seed_group", self.seed_group)
        _require_nonempty_string("case family", self.family)
        if self.family not in GENERATORS:
            raise ValueError(f"unknown instance family {self.family!r}")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("case parameters must be a mapping")
        copied = dict(self.parameters)
        GENERATORS[self.family].generate(copied, seed=0)
        object.__setattr__(self, "parameters", MappingProxyType(copied))
        object.__setattr__(self, "case_id", case_id)

    def generate(
        self,
        seed: int,
        *,
        derived_parameters: Mapping[str, object] | None = None,
    ) -> MaximumCoverageInstance:
        """Generate this case through the same registry used for preflight."""

        return cast(
            MaximumCoverageInstance,
            GENERATORS[self.family].generate(
                self.parameters,
                seed,
                derived_parameters=derived_parameters,
            ),
        )


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """A complete experiment definition normalized to the current schema."""

    name: str
    repetitions: int
    algorithms: tuple[AlgorithmConfig, ...]
    cases: tuple[CaseConfig, ...]
    schema_version: int = CONFIG_SCHEMA_VERSION
    base_seed: int = 2026

    def __post_init__(self) -> None:
        if not _is_integer(self.schema_version):
            raise ValueError("schema_version must be an integer")
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported configuration schema version {self.schema_version!r}; "
                f"expected {CONFIG_SCHEMA_VERSION}"
            )
        _require_nonempty_string("experiment name", self.name)
        if not _is_integer(self.repetitions) or self.repetitions <= 0:
            raise ValueError("repetitions must be a positive integer")
        if self.repetitions > 10_000:
            raise ValueError("repetitions must not exceed 10000")
        if not _is_integer(self.base_seed):
            raise ValueError("base_seed must be an integer")
        object.__setattr__(self, "algorithms", tuple(self.algorithms))
        object.__setattr__(self, "cases", tuple(self.cases))
        if not self.algorithms or not all(
            isinstance(item, AlgorithmConfig) for item in self.algorithms
        ):
            raise ValueError("algorithms must contain AlgorithmConfig values")
        if not any(item.enabled for item in self.algorithms):
            raise ValueError("at least one algorithm must be enabled")
        if not self.cases or not all(
            isinstance(item, CaseConfig) for item in self.cases
        ):
            raise ValueError("cases must contain CaseConfig values")
        algorithm_ids = [item.algorithm_id for item in self.algorithms]
        if len(set(algorithm_ids)) != len(algorithm_ids):
            raise ValueError("algorithm ids must be unique")
        execution_keys = [
            (
                item.name,
                json.dumps(
                    ALGORITHMS[item.name].option_values(item.options),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                item.algorithm_seeds,
            )
            for item in self.algorithms
        ]
        if len(set(execution_keys)) != len(execution_keys):
            raise ValueError("algorithm variants must have distinct options or seeds")
        case_ids = [item.case_id for item in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case_ids must be unique")



_COMMON_ROOT_FIELDS = (
    "schema_version",
    "name",
    "base_seed",
    "repetitions",
    "algorithms",
    "cases",
)
_LEGACY_ROOT_FIELDS = (
    "exact_time_limit_seconds",
    "brute_force_set_cutoff",
)
_REQUIRED_ROOT_FIELDS = ("name", "repetitions", "algorithms", "cases")
_OPTION_FIELDS = ("time_limit_seconds", "max_set_count")


def _semantic_error_path(case_path: str, error: ValueError, parameters: set[str]) -> str:
    message = str(error)
    for parameter in parameters:
        if message.startswith(f"{parameter} must"):
            return f"{case_path}.{parameter}"
    return case_path


def _case_id_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _expanded_case_id(name: str, values: Mapping[str, object]) -> str:
    if not values:
        return name
    suffix = "__".join(
        f"{parameter}={_case_id_value(values[parameter])}"
        for parameter in sorted(values)
    )
    return f"{name}__{suffix}"


def _parse_options(
    raw: object,
    path: str,
    algorithm_name: str,
    issues: list[tuple[str, str]],
) -> AlgorithmRunOptions | None:
    if not isinstance(raw, Mapping):
        issues.append((path, "must be a JSON object"))
        return None
    values = dict(raw)
    start = len(issues)
    specification = ALGORITHMS[algorithm_name]
    supported = specification.supported_options
    declared = set(_OPTION_FIELDS) | set(specification.option_specs)
    for field in values:
        if field not in declared:
            issues.append((f"{path}.{field}", "unknown field"))
        elif field in _OPTION_FIELDS and field not in supported:
            issues.append(
                (
                    f"{path}.{field}",
                    f"is not supported by algorithm {algorithm_name!r}",
                )
            )

    defaults = ALGORITHMS[algorithm_name].options_from_config({})
    time_limit = values.get("time_limit_seconds", defaults.time_limit_seconds)
    max_set_count = values.get("max_set_count", defaults.max_set_count)
    if time_limit is not None and (
        not _is_number(time_limit)
        or not math.isfinite(time_limit)
        or time_limit <= 0
    ):
        issues.append(
            (f"{path}.time_limit_seconds", "must be null or a finite positive number")
        )
    if max_set_count is not None and (
        not _is_integer(max_set_count) or max_set_count <= 0
    ):
        issues.append(
            (f"{path}.max_set_count", "must be null or a positive integer")
        )
    extra_values: dict[str, object] = {}
    for name, option_spec in specification.option_specs.items():
        if name in values:
            try:
                extra_values[name] = option_spec.validate(
                    algorithm_name, name, values[name]
                )
            except ValueError as error:
                issues.append((f"{path}.{name}", str(error)))
        elif option_spec.required:
            issues.append((f"{path}.{name}", "missing required option"))
    if len(issues) != start:
        return None
    return AlgorithmRunOptions(
        time_limit_seconds=(None if time_limit is None else float(time_limit)),
        max_set_count=max_set_count,
        values=extra_values,
    )


def _parse_v1_algorithms(
    raw: object,
    data: Mapping[str, object],
    issues: list[tuple[str, str]],
) -> list[AlgorithmConfig]:
    time_limit = data.get("exact_time_limit_seconds", 5.0)
    cutoff = data.get("brute_force_set_cutoff", 18)
    controls_valid = True
    if (
        not _is_number(time_limit)
        or not math.isfinite(time_limit)
        or time_limit <= 0
    ):
        issues.append(
            ("$.exact_time_limit_seconds", "must be a finite positive number")
        )
        controls_valid = False
    if not _is_integer(cutoff) or cutoff <= 0:
        issues.append(("$.brute_force_set_cutoff", "must be a positive integer"))
        controls_valid = False
    if not isinstance(raw, list) or not raw:
        issues.append(("$.algorithms", "must be a non-empty array"))
        return []

    controls = {
        "exact_time_limit_seconds": time_limit,
        "brute_force_set_cutoff": cutoff,
    }
    result: list[AlgorithmConfig] = []
    seen: dict[str, int] = {}
    for index, name in enumerate(raw):
        path = f"$.algorithms[{index}]"
        if not isinstance(name, str) or not name.strip():
            issues.append((path, "must be a non-empty string"))
            continue
        if name not in ALGORITHMS:
            issues.append((path, f"unknown algorithm {name!r}"))
            continue
        if name in seen:
            issues.append((path, f"duplicates $.algorithms[{seen[name]}]"))
            continue
        seen[name] = index
        if controls_valid:
            preflight = ALGORITHMS[name].preflight_error
            if preflight is not None:
                message = preflight()
                if message is not None:
                    issues.append((path, message))
                    continue
            result.append(
                AlgorithmConfig(name, ALGORITHMS[name].options_from_config(controls))
            )
    return result


def _parse_v2_algorithms(
    raw: object,
    issues: list[tuple[str, str]],
    *,
    extended: bool = False,
) -> list[AlgorithmConfig]:
    if not isinstance(raw, list) or not raw:
        issues.append(("$.algorithms", "must be a non-empty array"))
        return []

    result: list[AlgorithmConfig] = []
    seen: dict[str, int] = {}
    for index, raw_algorithm in enumerate(raw):
        path = f"$.algorithms[{index}]"
        if not isinstance(raw_algorithm, Mapping):
            issues.append((path, "must be a JSON object"))
            continue
        algorithm = dict(raw_algorithm)
        start = len(issues)
        allowed_fields = {"name", "options", "enabled"}
        if extended:
            allowed_fields.update({"id", "algorithm_seeds"})
        for field in algorithm:
            if field not in allowed_fields:
                issues.append((f"{path}.{field}", "unknown field"))
        name = algorithm.get("name")
        if "name" not in algorithm:
            issues.append((f"{path}.name", "missing required field"))
        elif not isinstance(name, str) or not name.strip():
            issues.append((f"{path}.name", "must be a non-empty string"))
        elif name not in ALGORITHMS:
            issues.append((f"{path}.name", f"unknown algorithm {name!r}"))
        algorithm_id = algorithm.get("id", name)
        if extended and "id" in algorithm and (
            not isinstance(algorithm_id, str) or not algorithm_id.strip()
        ):
            issues.append((f"{path}.id", "must be a non-empty string"))
        identity = algorithm_id if extended else name
        if isinstance(identity, str) and identity in seen:
            issues.append(
                (
                    f"{path}.{'id' if extended else 'name'}",
                    f"duplicates $.algorithms[{seen[identity]}]",
                )
            )
        elif isinstance(identity, str):
            seen[identity] = index

        options = None
        if isinstance(name, str) and name in ALGORITHMS:
            options = _parse_options(
                algorithm.get("options", {}), f"{path}.options", name, issues
            )
        enabled = algorithm.get("enabled", True)
        if not isinstance(enabled, bool):
            issues.append((f"{path}.enabled", "must be a boolean"))
        if enabled is True and isinstance(name, str) and name in ALGORITHMS:
            preflight = ALGORITHMS[name].preflight_error
            if preflight is not None:
                message = preflight()
                if message is not None:
                    issues.append((f"{path}.name", message))
        raw_seeds = algorithm.get("algorithm_seeds", [])
        algorithm_seeds: tuple[int, ...] = ()
        if extended and "algorithm_seeds" in algorithm:
            if not isinstance(raw_seeds, list) or not raw_seeds:
                issues.append(
                    (f"{path}.algorithm_seeds", "must be a non-empty array")
                )
            elif any(not _is_integer(seed) for seed in raw_seeds):
                issues.append(
                    (f"{path}.algorithm_seeds", "must contain only integers")
                )
            elif len(set(raw_seeds)) != len(raw_seeds):
                issues.append(
                    (f"{path}.algorithm_seeds", "must contain unique integers")
                )
            else:
                algorithm_seeds = tuple(raw_seeds)
        if len(issues) == start and options is not None:
            assert isinstance(name, str)
            assert isinstance(algorithm_id, str)
            try:
                result.append(
                    AlgorithmConfig(
                        name,
                        options,
                        enabled,
                        algorithm_id,
                        algorithm_seeds,
                    )
                )
            except (TypeError, ValueError) as error:
                message = str(error)
                if "algorithm_seeds" in message or "algorithm seeds" in message:
                    error_path = f"{path}.algorithm_seeds"
                elif "algorithm id" in message:
                    error_path = f"{path}.id"
                else:
                    error_path = path
                issues.append((error_path, message))
    return result


def _parse_cases(
    raw: object,
    issues: list[tuple[str, str]],
    *,
    extended: bool = False,
) -> list[CaseConfig]:
    if not isinstance(raw, list) or not raw:
        issues.append(("$.cases", "must be a non-empty array"))
        return []

    result: list[CaseConfig] = []
    seen_names: dict[str, int] = {}
    seen_ids: dict[str, str] = {}
    for index, raw_case in enumerate(raw):
        case_path = f"$.cases[{index}]"
        if not isinstance(raw_case, Mapping):
            issues.append((case_path, "must be a JSON object"))
            continue
        case = dict(raw_case)
        start = len(issues)
        case_name = case.get("name")
        family = case.get("family")

        if "name" not in case:
            issues.append((f"{case_path}.name", "missing required field"))
        elif not isinstance(case_name, str) or not case_name.strip():
            issues.append((f"{case_path}.name", "must be a non-empty string"))
        elif case_name in seen_names:
            issues.append(
                (
                    f"{case_path}.name",
                    f"duplicates $.cases[{seen_names[case_name]}].name",
                )
            )
        else:
            seen_names[case_name] = index

        if "family" not in case:
            issues.append((f"{case_path}.family", "missing required field"))
        elif not isinstance(family, str) or not family.strip():
            issues.append((f"{case_path}.family", "must be a non-empty string"))
        elif family not in GENERATORS:
            issues.append(
                (f"{case_path}.family", f"unknown instance family {family!r}")
            )

        parameters: dict[str, object] = {}
        sweep_values: dict[str, list[object]] = {}
        if isinstance(family, str) and family in GENERATORS:
            generator = GENERATORS[family]
            allowed = set(generator.parameters)
            case_metadata_fields = {"name", "family", "sweep"}
            if extended:
                case_metadata_fields.add("seed_group")
            for field in case:
                if (
                    field not in case_metadata_fields
                    and field not in allowed
                ):
                    issues.append((f"{case_path}.{field}", "unknown field"))

            seed_group = case.get("seed_group")
            if extended and seed_group is not None and (
                not isinstance(seed_group, str) or not seed_group.strip()
            ):
                issues.append(
                    (f"{case_path}.seed_group", "must be a non-empty string")
                )

            raw_sweep = case.get("sweep")
            if "sweep" in case:
                if not isinstance(raw_sweep, Mapping) or not raw_sweep:
                    issues.append(
                        (f"{case_path}.sweep", "must be a non-empty JSON object")
                    )
                else:
                    for parameter, raw_values in raw_sweep.items():
                        parameter_path = f"{case_path}.sweep.{parameter}"
                        if parameter not in allowed:
                            issues.append((parameter_path, "unknown generator parameter"))
                            continue
                        if parameter in case:
                            issues.append(
                                (
                                    parameter_path,
                                    f"duplicates fixed field {case_path}.{parameter}",
                                )
                            )
                            continue
                        if not isinstance(raw_values, list) or not raw_values:
                            issues.append((parameter_path, "must be a non-empty array"))
                            continue
                        specification = generator.parameters[parameter]
                        valid_values: list[object] = []
                        for value_index, value in enumerate(raw_values):
                            try:
                                specification.validate(family, parameter, value)
                            except ValueError:
                                issues.append(
                                    (
                                        f"{parameter_path}[{value_index}]",
                                        f"must be {specification.type_name}",
                                    )
                                )
                            else:
                                valid_values.append(value)
                        if len(valid_values) == len(raw_values):
                            sweep_values[parameter] = valid_values

            for parameter, specification in generator.parameters.items():
                swept = (
                    isinstance(raw_sweep, Mapping) and parameter in raw_sweep
                )
                if parameter not in case:
                    if not swept and specification.required:
                        issues.append(
                            (f"{case_path}.{parameter}", "missing required field")
                        )
                    continue
                parameters[parameter] = case[parameter]
                try:
                    specification.validate(family, parameter, case[parameter])
                except ValueError:
                    issues.append(
                        (
                            f"{case_path}.{parameter}",
                            f"must be {specification.type_name}",
                        )
                    )

        if len(issues) == start:
            assert isinstance(case_name, str)
            assert isinstance(family, str)
            sweep_names = sorted(sweep_values)
            dimensions = [
                tuple(enumerate(sweep_values[parameter]))
                for parameter in sweep_names
            ]
            combinations = product(*dimensions) if dimensions else [()]
            for combination in combinations:
                selected = {
                    parameter: value
                    for parameter, (_, value) in zip(sweep_names, combination)
                }
                selected_indices = {
                    parameter: value_index
                    for parameter, (value_index, _) in zip(sweep_names, combination)
                }
                expanded_parameters = {**parameters, **selected}
                case_id = _expanded_case_id(case_name, selected)
                try:
                    expanded = CaseConfig(
                        case_name,
                        family,
                        expanded_parameters,
                        case_id,
                        cast(str | None, case.get("seed_group"))
                        if extended
                        else None,
                    )
                except ValueError as error:
                    message = str(error)
                    error_path = _semantic_error_path(
                        case_path, error, set(generator.parameters)
                    )
                    for parameter in sweep_names:
                        if message.startswith(f"{parameter} must"):
                            error_path = (
                                f"{case_path}.sweep.{parameter}"
                                f"[{selected_indices[parameter]}]"
                            )
                            break
                    issues.append((error_path, message))
                    continue
                if case_id in seen_ids:
                    issues.append(
                        (
                            f"{case_path}.sweep" if sweep_names else f"{case_path}.name",
                            f"expands to duplicate case_id {case_id!r}; "
                            f"first produced by {seen_ids[case_id]}",
                        )
                    )
                    continue
                seen_ids[case_id] = case_path
                result.append(expanded)
    return result


def parse_config(value: object) -> ExperimentConfig:
    """Parse and normalize a schema-v1 or schema-v2 configuration."""

    if not isinstance(value, Mapping):
        raise ConfigurationError([("$", "must be a JSON object")])

    data = dict(value)
    issues: list[tuple[str, str]] = []
    raw_version = data.get("schema_version", LEGACY_CONFIG_SCHEMA_VERSION)
    if not _is_integer(raw_version):
        issues.append(("$.schema_version", "must be an integer"))
        version = None
    elif raw_version not in {
        LEGACY_CONFIG_SCHEMA_VERSION,
        PREVIOUS_CONFIG_SCHEMA_VERSION,
        CONFIG_SCHEMA_VERSION,
    }:
        issues.append(
            (
                "$.schema_version",
                f"unsupported version {raw_version!r}; expected 1, 2, or 3",
            )
        )
        version = None
    else:
        version = raw_version

    known_root = set(_COMMON_ROOT_FIELDS)
    if version in {None, LEGACY_CONFIG_SCHEMA_VERSION}:
        known_root.update(_LEGACY_ROOT_FIELDS)
    for field in data:
        if field not in known_root:
            issues.append((f"$.{field}", "unknown field"))
    for field in _REQUIRED_ROOT_FIELDS:
        if field not in data:
            issues.append((f"$.{field}", "missing required field"))

    name = data.get("name")
    if "name" in data and (not isinstance(name, str) or not name.strip()):
        issues.append(("$.name", "must be a non-empty string"))
    base_seed = data.get("base_seed", 2026)
    if not _is_integer(base_seed):
        issues.append(("$.base_seed", "must be an integer"))
    repetitions = data.get("repetitions")
    if "repetitions" in data:
        if not _is_integer(repetitions) or repetitions <= 0:
            issues.append(("$.repetitions", "must be a positive integer"))
        elif repetitions > 10_000:
            issues.append(("$.repetitions", "must not exceed 10000"))

    algorithms: list[AlgorithmConfig] = []
    if "algorithms" in data:
        if version == LEGACY_CONFIG_SCHEMA_VERSION:
            algorithms = _parse_v1_algorithms(data["algorithms"], data, issues)
        elif version in {PREVIOUS_CONFIG_SCHEMA_VERSION, CONFIG_SCHEMA_VERSION}:
            algorithms = _parse_v2_algorithms(
                data["algorithms"],
                issues,
                extended=version == CONFIG_SCHEMA_VERSION,
            )
    if algorithms and not any(algorithm.enabled for algorithm in algorithms):
        issues.append(("$.algorithms", "at least one algorithm must be enabled"))
    cases: list[CaseConfig] = []
    if "cases" in data:
        cases = _parse_cases(
            data["cases"],
            issues,
            extended=version == CONFIG_SCHEMA_VERSION,
        )

    if issues:
        raise ConfigurationError(issues)

    assert version is not None
    assert isinstance(name, str)
    assert isinstance(base_seed, int)
    assert isinstance(repetitions, int)
    config = ExperimentConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        name=name,
        base_seed=base_seed,
        repetitions=repetitions,
        algorithms=tuple(algorithms),
        cases=tuple(cases),
    )
    if version == LEGACY_CONFIG_SCHEMA_VERSION:
        warnings.warn(
            "schema-v1 configuration is deprecated and was migrated to schema 3; "
            "replace string algorithm entries and top-level exact solver controls "
            "with per-algorithm options",
            LegacyConfigWarning,
            stacklevel=2,
        )
    return config


def load_config(path: Path) -> ExperimentConfig:
    """Load and fully validate one JSON configuration file."""

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value: Any = json.load(handle)
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            [
                (
                    "$",
                    f"invalid JSON at line {error.lineno}, column {error.colno}: "
                    f"{error.msg}",
                )
            ]
        ) from error
    return parse_config(value)
