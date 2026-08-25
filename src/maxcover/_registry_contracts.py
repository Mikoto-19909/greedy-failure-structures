"""Private algorithm and generator registry contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, cast

from .model import MaximumCoverageInstance, Solution, SolutionStatus


@dataclass(frozen=True, slots=True)
class AlgorithmRunOptions:
    """Execution controls understood by the algorithm registry.

    Algorithm-specific implementation details stay behind ``AlgorithmSpec``.
    The benchmark runner only needs these common execution controls.
    """

    time_limit_seconds: float | None = None
    max_set_count: int | None = None
    values: Mapping[str, object] = field(default_factory=dict)
    algorithm_seed: int | None = None

    def __post_init__(self) -> None:
        if self.time_limit_seconds is not None:
            if (
                isinstance(self.time_limit_seconds, bool)
                or not isinstance(self.time_limit_seconds, (int, float))
                or not math.isfinite(self.time_limit_seconds)
                or self.time_limit_seconds <= 0
            ):
                raise ValueError("time_limit_seconds must be finite and positive or None")
            object.__setattr__(
                self, "time_limit_seconds", float(self.time_limit_seconds)
            )
        if self.max_set_count is not None and (
            isinstance(self.max_set_count, bool)
            or not isinstance(self.max_set_count, int)
            or self.max_set_count <= 0
        ):
            raise ValueError("max_set_count must be a positive integer or None")
        if not isinstance(self.values, Mapping):
            raise TypeError("algorithm option values must be a mapping")
        copied = dict(self.values)
        try:
            json.dumps(copied, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise ValueError("algorithm option values must be finite JSON values") from error
        object.__setattr__(self, "values", MappingProxyType(copied))
        if self.algorithm_seed is not None and (
            isinstance(self.algorithm_seed, bool)
            or not isinstance(self.algorithm_seed, int)
        ):
            raise ValueError("algorithm_seed must be an integer or None")

    def get(self, name: str, default: object = None) -> object:
        if name == "time_limit_seconds":
            return self.time_limit_seconds
        if name == "max_set_count":
            return self.max_set_count
        if name == "algorithm_seed":
            return self.algorithm_seed
        return self.values.get(name, default)

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (
            AlgorithmRunOptions,
            (
                self.time_limit_seconds,
                self.max_set_count,
                dict(self.values),
                self.algorithm_seed,
            ),
        )


AlgorithmRunner = Callable[[MaximumCoverageInstance, AlgorithmRunOptions], Solution]
GeneratorFactory = Callable[..., MaximumCoverageInstance]


_REQUIRED = object()


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """Declarative contract for one algorithm-specific option."""

    expected_types: tuple[type, ...]
    type_name: str
    default: object = _REQUIRED
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: frozenset[object] = frozenset()

    @property
    def required(self) -> bool:
        return self.default is _REQUIRED

    def validate(self, algorithm: str, name: str, value: object) -> object:
        numeric = int in self.expected_types or float in self.expected_types
        if (numeric and isinstance(value, bool)) or not isinstance(
            value, self.expected_types
        ):
            raise ValueError(
                f"algorithm {algorithm!r} option {name!r} must be {self.type_name}"
            )
        comparable_value = cast(int | float, value)
        if self.minimum is not None and comparable_value < self.minimum:
            raise ValueError(
                f"algorithm {algorithm!r} option {name!r} must be >= {self.minimum}"
            )
        if self.maximum is not None and comparable_value > self.maximum:
            raise ValueError(
                f"algorithm {algorithm!r} option {name!r} must be <= {self.maximum}"
            )
        if self.choices and value not in self.choices:
            raise ValueError(
                f"algorithm {algorithm!r} option {name!r} must be one of "
                f"{sorted(self.choices, key=repr)!r}"
            )
        return value


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Declarative type contract for one generator parameter."""

    expected_types: tuple[type, ...]
    type_name: str
    default: object = _REQUIRED

    def __post_init__(self) -> None:
        if not self.expected_types:
            raise ValueError("expected_types must not be empty")
        if not self.type_name:
            raise ValueError("type_name must not be empty")

    @property
    def required(self) -> bool:
        return self.default is _REQUIRED

    def validate(self, generator: str, parameter: str, value: object) -> object:
        numeric = int in self.expected_types or float in self.expected_types
        if (numeric and isinstance(value, bool)) or not isinstance(
            value, self.expected_types
        ):
            raise ValueError(
                f"generator {generator!r} parameter {parameter!r} "
                f"must be {self.type_name}"
            )
        return value


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    """Registry entry exposing one validated generator interface."""

    name: str
    factory: GeneratorFactory
    parameters: Mapping[str, ParameterSpec]
    derived_parameters: Mapping[str, ParameterSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        overlap = set(self.parameters) & set(self.derived_parameters)
        if overlap:
            raise ValueError(
                f"generator parameters cannot also be derived: {sorted(overlap)!r}"
            )
        required_derived = sorted(
            name
            for name, specification in self.derived_parameters.items()
            if specification.required
        )
        if required_derived:
            raise ValueError(
                "generator derived parameters must have defaults for configuration "
                f"preflight: {required_derived!r}"
            )

    def generate(
        self,
        parameters: Mapping[str, object],
        seed: int,
        *,
        derived_parameters: Mapping[str, object] | None = None,
    ) -> MaximumCoverageInstance:
        if not isinstance(parameters, Mapping):
            raise ValueError(f"generator {self.name!r} parameters must be a mapping")
        if derived_parameters is None:
            derived_parameters = {}
        if not isinstance(derived_parameters, Mapping):
            raise ValueError(
                f"generator {self.name!r} derived parameters must be a mapping"
            )
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"generator {self.name!r} parameter 'seed' must be integer")

        unknown = sorted(set(parameters) - set(self.parameters), key=repr)
        if unknown:
            fields = ", ".join(repr(field) for field in unknown)
            raise ValueError(
                f"generator {self.name!r} received unknown parameter(s): {fields}"
            )

        missing = sorted(
            name
            for name, specification in self.parameters.items()
            if specification.required and name not in parameters
        )
        if missing:
            fields = ", ".join(repr(field) for field in missing)
            raise ValueError(
                f"generator {self.name!r} is missing required parameter(s): {fields}"
            )

        unknown_derived = sorted(
            set(derived_parameters) - set(self.derived_parameters), key=repr
        )
        if unknown_derived:
            fields = ", ".join(repr(field) for field in unknown_derived)
            raise ValueError(
                f"generator {self.name!r} received unknown derived parameter(s): {fields}"
            )

        resolved: dict[str, object] = {}
        for name, specification in self.parameters.items():
            value = (
                parameters[name]
                if name in parameters
                else specification.default
            )
            resolved[name] = specification.validate(self.name, name, value)

        resolved_derived: dict[str, object] = {}
        for name, specification in self.derived_parameters.items():
            value = (
                derived_parameters[name]
                if name in derived_parameters
                else specification.default
            )
            resolved_derived[name] = specification.validate(self.name, name, value)

        instance = self.factory(**resolved, **resolved_derived, seed=seed)
        if instance.family != self.name:
            raise RuntimeError(
                f"generator {self.name!r} returned family {instance.family!r}"
            )
        if instance.seed != seed:
            raise RuntimeError(
                f"generator {self.name!r} returned seed {instance.seed!r}, "
                f"expected {seed!r}"
            )
        return instance


@dataclass(frozen=True, slots=True)
class AlgorithmSpec:
    """Registry entry exposing one uniform algorithm interface."""

    name: str
    exact: bool
    runner: AlgorithmRunner
    version: int = 1
    supported_options: frozenset[str] = frozenset()
    time_limit_config_key: str | None = None
    default_time_limit_seconds: float | None = None
    set_count_limit_config_key: str | None = None
    default_max_set_count: int | None = None
    option_specs: Mapping[str, OptionSpec] = field(default_factory=dict)
    uses_random_seed: bool = False
    preflight_error: Callable[[], str | None] | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version <= 0
        ):
            raise ValueError("algorithm version must be a positive integer")
        known = {"time_limit_seconds", "max_set_count"}
        unknown = self.supported_options - known
        if unknown:
            raise ValueError(f"unknown supported algorithm options: {sorted(unknown)!r}")
        if (
            self.time_limit_config_key is not None
            or self.default_time_limit_seconds is not None
        ) and "time_limit_seconds" not in self.supported_options:
            raise ValueError("time-limit metadata requires time_limit_seconds support")
        if (
            self.set_count_limit_config_key is not None
            or self.default_max_set_count is not None
        ) and "max_set_count" not in self.supported_options:
            raise ValueError("set-count metadata requires max_set_count support")
        object.__setattr__(self, "option_specs", MappingProxyType(dict(self.option_specs)))

    def validate_options(self, options: AlgorithmRunOptions) -> None:
        if not isinstance(options, AlgorithmRunOptions):
            raise TypeError("options must be AlgorithmRunOptions")
        if (
            "time_limit_seconds" not in self.supported_options
            and options.time_limit_seconds is not None
        ):
            raise ValueError(f"algorithm {self.name!r} does not support time_limit_seconds")
        if (
            "max_set_count" not in self.supported_options
            and options.max_set_count is not None
        ):
            raise ValueError(f"algorithm {self.name!r} does not support max_set_count")
        if options.algorithm_seed is not None and not self.uses_random_seed:
            raise ValueError(f"algorithm {self.name!r} does not use an algorithm seed")
        unknown = sorted(set(options.values) - set(self.option_specs), key=repr)
        if unknown:
            raise ValueError(
                f"algorithm {self.name!r} received unknown option(s): {unknown!r}"
            )
        for name, specification in self.option_specs.items():
            if name in options.values:
                specification.validate(self.name, name, options.values[name])
            elif specification.required:
                raise ValueError(
                    f"algorithm {self.name!r} is missing required option {name!r}"
                )

    def option_values(self, options: AlgorithmRunOptions) -> dict[str, object]:
        """Return the canonical options actually adopted for one algorithm."""

        self.validate_options(options)
        values: dict[str, object] = {}
        if "time_limit_seconds" in self.supported_options:
            values["time_limit_seconds"] = options.time_limit_seconds
        if "max_set_count" in self.supported_options:
            values["max_set_count"] = options.max_set_count
        if options.algorithm_seed is not None:
            values["algorithm_seed"] = options.algorithm_seed
        for name, specification in self.option_specs.items():
            values[name] = (
                options.values[name]
                if name in options.values
                else specification.default
            )
        return values

    def options_from_config(self, config: Mapping[str, Any]) -> AlgorithmRunOptions:
        """Translate legacy top-level controls into the common option model."""

        time_limit = self.default_time_limit_seconds
        if self.time_limit_config_key is not None:
            time_limit = config.get(self.time_limit_config_key, time_limit)

        max_set_count = self.default_max_set_count
        if self.set_count_limit_config_key is not None:
            max_set_count = config.get(self.set_count_limit_config_key, max_set_count)

        return AlgorithmRunOptions(
            time_limit_seconds=(
                None if time_limit is None else float(time_limit)
            ),
            max_set_count=(
                None if max_set_count is None else int(max_set_count)
            ),
        )

    def is_eligible(
        self,
        instance: MaximumCoverageInstance,
        options: AlgorithmRunOptions,
    ) -> bool:
        return (
            options.max_set_count is None
            or instance.set_count <= options.max_set_count
        )

    def run(
        self,
        instance: MaximumCoverageInstance,
        options: AlgorithmRunOptions,
    ) -> Solution:
        """Run the implementation and enforce the result-side contract."""

        self.validate_options(options)
        if self.uses_random_seed and options.algorithm_seed is None:
            raise RuntimeError(f"algorithm {self.name!r} requires an algorithm seed")
        solution = self.runner(instance, options)
        if solution.algorithm != self.name:
            raise RuntimeError(
                f"algorithm {self.name!r} returned result for "
                f"{solution.algorithm!r}"
            )
        if solution.status is SolutionStatus.ERROR:
            return solution
        if len(solution.selected) > instance.k:
            raise RuntimeError(f"algorithm {self.name!r} exceeded the set budget")
        if len(set(solution.selected)) != len(solution.selected):
            raise RuntimeError(f"algorithm {self.name!r} selected a set twice")
        if solution.feasible_value != instance.coverage(solution.selected):
            raise RuntimeError(f"algorithm {self.name!r} reported invalid coverage")
        allowed_statuses = (
            {SolutionStatus.OPTIMAL, SolutionStatus.TIMEOUT}
            if self.exact
            else {SolutionStatus.FEASIBLE, SolutionStatus.TIMEOUT}
        )
        if solution.status not in allowed_statuses:
            raise RuntimeError(
                f"algorithm {self.name!r} returned status "
                f"{solution.status.value!r}, incompatible with its registry contract"
            )
        return solution

AlgorithmRunOptions.__module__ = "maxcover.contracts"
OptionSpec.__module__ = "maxcover.contracts"
ParameterSpec.__module__ = "maxcover.contracts"
GeneratorSpec.__module__ = "maxcover.contracts"
AlgorithmSpec.__module__ = "maxcover.contracts"
