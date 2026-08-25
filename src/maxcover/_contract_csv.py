"""Private CSV parsing helpers shared by typed contract records."""

from __future__ import annotations

import math
from collections.abc import Mapping


def _validate_csv_fields(
    row: Mapping[str, str], expected_fields: tuple[str, ...]
) -> None:
    actual = set(row)
    expected = set(expected_fields)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected, key=repr)
    if missing:
        raise ValueError(f"CSV row is missing field(s): {', '.join(missing)}")
    if unknown:
        raise ValueError(f"CSV row has unknown field(s): {', '.join(map(repr, unknown))}")


def _parse_int(value: str, field: str, *, optional: bool = False) -> int | None:
    if optional and value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"CSV field {field!r} must be an integer") from error


def _parse_float(value: str, field: str, *, optional: bool = False) -> float | None:
    if optional and value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"CSV field {field!r} must be a number") from error
    if not math.isfinite(parsed):
        raise ValueError(f"CSV field {field!r} must be finite")
    return parsed


def _parse_bool(value: str, field: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"CSV field {field!r} must be 'True' or 'False'")


def _required_int(value: str, field: str) -> int:
    parsed = _parse_int(value, field)
    assert parsed is not None
    return parsed


def _required_float(value: str, field: str) -> float:
    parsed = _parse_float(value, field)
    assert parsed is not None
    return parsed
