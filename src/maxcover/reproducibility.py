"""Stable identities, instance serialization, and atomic artifact helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .model import MaximumCoverageInstance, thaw_json_value

if TYPE_CHECKING:
    from .config import ExperimentConfig


INSTANCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class InstanceResourceLimits:
    """Bound resources consumed while loading a serialized instance."""

    max_input_bytes: int = 1024 * 1024
    max_universe_size: int = 512
    max_set_count: int = 128
    max_elements_per_set: int = 512
    max_bitset_chars: int = 130  # Includes the optional ``0x`` prefix.
    max_parameter_depth: int = 8

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in (
                self.max_input_bytes,
                self.max_universe_size,
                self.max_set_count,
                self.max_elements_per_set,
                self.max_bitset_chars,
                self.max_parameter_depth,
            )
        ):
            raise ValueError("instance resource limits must be positive")


DEFAULT_INSTANCE_RESOURCE_LIMITS = InstanceResourceLimits()


def _validate_parameter_depth(
    parameters: object, limits: InstanceResourceLimits
) -> None:
    """Reject nested parameter containers before recursive freezing."""

    if not isinstance(parameters, (Mapping, list, tuple)):
        return
    pending: list[tuple[object, int]] = [(parameters, 1)]
    while pending:
        current, depth = pending.pop()
        if depth > limits.max_parameter_depth:
            raise ValueError(
                "instance parameters exceed the maximum nesting depth"
            )
        if not isinstance(current, (Mapping, list, tuple)):
            continue
        children: Iterable[object] = (
            current.values() if isinstance(current, Mapping) else current
        )
        for child in children:
            if isinstance(child, (Mapping, list, tuple)):
                pending.append((child, depth + 1))


def _validate_instance_dimensions(
    raw_sets: list[object],
    universe_size: int,
    limits: InstanceResourceLimits,
) -> None:
    """Validate dimensions before any shift or large integer conversion."""

    if not 1 <= universe_size <= limits.max_universe_size:
        raise ValueError(
            "instance universe_size exceeds the supported resource limit"
        )
    if len(raw_sets) > limits.max_set_count:
        raise ValueError("instance set count exceeds the supported resource limit")


def _validate_hex_bitset(raw: str, limits: InstanceResourceLimits) -> None:
    """Validate a hexadecimal bitset length before calling ``int``."""

    if not 1 <= len(raw) <= limits.max_bitset_chars:
        raise ValueError("bitset entry exceeds the supported resource limit")
    # int(raw, 16) in the caller raises ValueError for invalid hex


def _read_json_input(path: Path, limits: InstanceResourceLimits) -> object:
    """Read at most one byte beyond the configured input limit."""

    with path.open("rb") as handle:
        raw = handle.read(limits.max_input_bytes + 1)
    if len(raw) > limits.max_input_bytes:
        raise ValueError("instance file exceeds the supported resource limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("instance file must be UTF-8") from error


def canonical_json(value: object) -> str:
    """Encode JSON deterministically for hashing and versioned artifacts."""

    return json.dumps(
        thaw_json_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def config_payload(config: ExperimentConfig) -> dict[str, object]:
    """Return the normalized, path-independent experiment definition."""

    return {
        "schema_version": config.schema_version,
        "name": config.name,
        "base_seed": config.base_seed,
        "repetitions": config.repetitions,
        "algorithms": [
            {
                "name": algorithm.name,
                "id": algorithm.algorithm_id,
                "enabled": algorithm.enabled,
                "algorithm_seeds": list(algorithm.algorithm_seeds),
                "options": {
                    "time_limit_seconds": algorithm.options.time_limit_seconds,
                    "max_set_count": algorithm.options.max_set_count,
                    **dict(algorithm.options.values),
                },
            }
            for algorithm in config.algorithms
        ],
        "cases": [
            {
                "name": case.name,
                "case_id": case.case_id,
                "family": case.family,
                "parameters": dict(case.parameters),
                **(
                    {"seed_group": case.seed_group}
                    if case.seed_group is not None
                    else {}
                ),
            }
            for case in config.cases
        ],
    }


def config_hash(config: ExperimentConfig) -> str:
    return stable_hash(config_payload(config))


def _elements_from_mask(mask: int, universe_size: int) -> list[int]:
    return [index for index in range(universe_size) if mask & (1 << index)]


def instance_payload(
    instance: MaximumCoverageInstance, *, encoding: str = "elements"
) -> dict[str, object]:
    """Serialize an instance using readable elements or compact hex bitsets."""

    if encoding == "elements":
        sets: list[object] = [
            _elements_from_mask(mask, instance.universe_size) for mask in instance.sets
        ]
    elif encoding == "bitsets":
        sets = [hex(mask) for mask in instance.sets]
    else:
        raise ValueError("instance encoding must be 'elements' or 'bitsets'")
    return {
        "schema_version": INSTANCE_SCHEMA_VERSION,
        "encoding": encoding,
        "universe_size": instance.universe_size,
        "sets": sets,
        "k": instance.k,
        "family": instance.family,
        "seed": instance.seed,
        "parameters": thaw_json_value(instance.parameters),
    }


def instance_identity_payload(instance: MaximumCoverageInstance) -> dict[str, object]:
    payload = instance_payload(instance, encoding="bitsets")
    payload.pop("encoding")
    return payload


def instance_id(instance: MaximumCoverageInstance) -> str:
    return stable_hash(instance_identity_payload(instance))


def run_id(
    instance_identifier: str,
    algorithm: str,
    options: Mapping[str, object],
    *,
    algorithm_version: int,
    algorithm_seed: int | None = None,
) -> str:
    return stable_hash(
        {
            "instance_id": instance_identifier,
            "algorithm": algorithm,
            "algorithm_version": algorithm_version,
            "algorithm_seed": algorithm_seed,
            "options": dict(options),
        }
    )


def instance_from_payload(
    value: object,
    *,
    limits: InstanceResourceLimits = DEFAULT_INSTANCE_RESOURCE_LIMITS,
) -> MaximumCoverageInstance:
    if not isinstance(value, Mapping):
        raise ValueError("instance JSON must be an object")
    data = dict(value)
    if data.get("schema_version") != INSTANCE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported instance schema version {data.get('schema_version')!r}"
        )
    encoding = data.get("encoding")
    raw_sets = data.get("sets")
    universe_size = data.get("universe_size")
    if isinstance(universe_size, bool) or not isinstance(universe_size, int):
        raise ValueError("instance universe_size must be an integer")
    if not isinstance(raw_sets, list):
        raise ValueError("instance sets must be an array")
    _validate_instance_dimensions(raw_sets, universe_size, limits)
    masks: list[int] = []
    if encoding == "bitsets":
        for raw in raw_sets:
            if not isinstance(raw, str):
                raise ValueError("bitset entries must be hexadecimal strings")
            _validate_hex_bitset(raw, limits)
            mask = int(raw, 16)
            if mask.bit_length() > universe_size:
                raise ValueError("a set contains an element outside the universe")
            masks.append(mask)
    elif encoding == "elements":
        for raw in raw_sets:
            if not isinstance(raw, list):
                raise ValueError("element-list sets must be arrays")
            if len(raw) > limits.max_elements_per_set:
                raise ValueError(
                    "set element count exceeds the supported resource limit"
                )
            mask = 0
            for element in raw:
                if isinstance(element, bool) or not isinstance(element, int):
                    raise ValueError("set elements must be integers")
                if not 0 <= element < universe_size:
                    raise ValueError("set element is outside the universe")
                mask |= 1 << element
            masks.append(mask)
    else:
        raise ValueError("instance encoding must be 'elements' or 'bitsets'")
    parameters = data.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("instance parameters must be an object")
    _validate_parameter_depth(parameters, limits)
    return MaximumCoverageInstance(
        universe_size=universe_size,
        sets=tuple(masks),
        k=cast(int, data.get("k")),
        family=data.get("family", "custom"),
        seed=data.get("seed"),
        parameters=dict(parameters),
    )


def load_instance(
    path: Path,
    *,
    limits: InstanceResourceLimits = DEFAULT_INSTANCE_RESOURCE_LIMITS,
) -> tuple[MaximumCoverageInstance, dict[str, Any]]:
    value = _read_json_input(path, limits)
    if not isinstance(value, dict):
        raise ValueError("instance file must contain a JSON object")
    payload = value.get("instance", value)
    return instance_from_payload(payload, limits=limits), value


def atomic_write_text(path: Path, content: str) -> None:
    """Replace one file atomically without exposing a partial artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
