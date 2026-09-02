"""Compare benchmark result sets across a reproducibility matrix.

What this script enforces
-------------------------
docs/faq.md declares the determinism contract: with the same normalized
configuration, algorithm version, and explicit seed, completed runs reproduce
the instance identities, selected set indices, coverage values, and the
canonical row ordering. Wall-clock runtime, timestamps, and environment
metadata may vary by machine, and a run stopped by its wall-clock limit
reports the incumbent it had reached when the limit fired, so that incumbent
and its coverage may differ across machines and are exempt from the guarantee.

Given one baseline result directory and one or more other result directories
(each containing raw_results.csv and manifest.json), this script compares
every other directory against the baseline and reports, per field, whether the
declaration held. The declaration itself lives in
docs/reproducibility_matrix.md; this script is the enforcement half of that
declaration-plus-code pair, so the two documents must be changed together.

Rows are paired by their logical run identity (case_id, repetition,
algorithm_id, algorithm_seed, algorithm), which is the execution-plan
position a run was planned for. run_id is then compared as a field: it is the
content identity contract of a run, so a different instance at the same plan
position or a different algorithm identity shows up as an inconsistent run_id
as well as an inconsistent instance_id. The canonical row order is compared
as the sequence of logical run identities in file order, because
raw_results.csv is written in deterministic plan order.

Exit status is 1 when any compared field differs and 0 otherwise, so the
script works as an unconditional gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.contracts import RunRecord  # noqa: E402
from maxcover.model import SolutionStatus  # noqa: E402


# Wall-clock runtime is machine-specific by declaration. See docs/faq.md.
ALWAYS_EXEMPT = frozenset({"runtime_seconds"})

# Incumbent and search-progress fields of a run stopped by its wall-clock
# limit. Exempt when either side of the pair reports a timeout status.
TIMEOUT_EXEMPT = frozenset(
    {
        "algorithm_metadata",
        "coverage",
        "best_bound",
        "optimality_gap",
        "nodes_or_iterations",
        "selected",
    }
)

# Derived flags and the record schema version. RunRecord.from_csv_row
# re-derives is_exact and timed_out from status and cross-checks them, so a
# status difference is reported by the status field itself, and a schema
# mismatch is a hard error rather than a field difference.
DERIVED = frozenset({"is_exact", "timed_out", "schema_version"})

# Field report order follows the artifact column order.
REPORT_FIELDS = tuple(field for field in RunRecord.CSV_FIELDS if field not in DERIVED)

# Manifest fields that describe experiment identity and must therefore agree.
MANIFEST_COMPARED_FIELDS = (
    "experiment",
    "configuration.config_hash",
    "seeds.base_seed",
    "seeds.minimum",
    "seeds.maximum",
    "seeds.count",
    "execution.planned_instances",
    "execution.planned_runs",
    "algorithms",
)


@dataclass(frozen=True)
class FieldCheck:
    """One reported comparison result."""

    name: str
    consistent: bool
    detail: str
    example: str | None = None


def _field_value(row: RunRecord, field: str) -> object:
    return getattr(row, field)


def _display(value: object) -> str:
    if isinstance(value, tuple):
        return " ".join(str(item) for item in value)
    text = str(value)
    if len(text) <= 96:
        return text
    return text[:96] + "..."


def _load_records(path: Path) -> list[RunRecord]:
    """Read raw_results.csv into validated RunRecord instances."""
    if not path.is_file():
        raise ValueError(f"{path} does not exist")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = [RunRecord.from_csv_row(row) for row in csv.DictReader(handle)]
    except (KeyError, ValueError, csv.Error) as error:
        raise ValueError(f"{path.name} cannot be read as raw results: {error}") from error
    identifiers = [row.run_id for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{path.name} contains duplicate run_id values")
    return rows


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"{path} does not exist")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _manifest_identities(manifest: dict[str, object]) -> dict[str, object]:
    configuration = manifest.get("configuration")
    seeds = manifest.get("seeds")
    execution = manifest.get("execution")
    return {
        "experiment": manifest.get("experiment"),
        "configuration.config_hash": (
            configuration.get("config_hash") if isinstance(configuration, dict) else None
        ),
        "seeds.base_seed": seeds.get("base_seed") if isinstance(seeds, dict) else None,
        "seeds.minimum": seeds.get("minimum") if isinstance(seeds, dict) else None,
        "seeds.maximum": seeds.get("maximum") if isinstance(seeds, dict) else None,
        "seeds.count": seeds.get("count") if isinstance(seeds, dict) else None,
        "execution.planned_instances": (
            execution.get("planned_instances") if isinstance(execution, dict) else None
        ),
        "execution.planned_runs": (
            execution.get("planned_runs") if isinstance(execution, dict) else None
        ),
        "algorithms": manifest.get("algorithms"),
    }


def _logical_key(row: RunRecord) -> tuple[str, int, str, int | None, str]:
    """The execution-plan position of one run."""
    return (
        row.case_id,
        row.repetition,
        row.algorithm_id,
        row.algorithm_seed,
        row.algorithm,
    )


def _pair_rows(
    baseline: Sequence[RunRecord],
    other: Sequence[RunRecord],
) -> tuple[list[tuple[RunRecord, RunRecord]], list[str]]:
    """Pair rows on their logical run identity.

    Returns the pairs and the logical keys that could not be paired because
    they are missing on one side or duplicated on either.
    """
    baseline_by_key: dict[tuple[str, int, str, int | None, str], RunRecord] = {}
    other_by_key: dict[tuple[str, int, str, int | None, str], RunRecord] = {}
    baseline_counts = Counter(_logical_key(row) for row in baseline)
    other_counts = Counter(_logical_key(row) for row in other)
    for row in baseline:
        baseline_by_key.setdefault(_logical_key(row), row)
    for row in other:
        other_by_key.setdefault(_logical_key(row), row)
    paired: list[tuple[RunRecord, RunRecord]] = []
    ambiguous: list[str] = []
    for key in sorted(set(baseline_counts) | set(other_counts)):
        baseline_count = baseline_counts.get(key, 0)
        other_count = other_counts.get(key, 0)
        if baseline_count == 1 and other_count == 1:
            paired.append((baseline_by_key[key], other_by_key[key]))
        else:
            ambiguous.append("|".join(str(part) for part in key))
    return paired, ambiguous


def _algorithm_map_diff(left: object, right: object) -> str:
    """Describe the first difference between two algorithm identity maps."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return f"(baseline={_display(left)}, compare={_display(right)})"
    for name in sorted(set(left) | set(right)):
        if left.get(name) != right.get(name):
            return (
                f"({len(left)} baseline entries, {len(right)} compare entries; "
                f"{_display(name)} differs)"
            )
    return "(algorithm entries differ)"

def _row_is_timeout(row: RunRecord) -> bool:
    return row.status is SolutionStatus.TIMEOUT


def _manifest_checks(baseline: Path, other: Path) -> list[FieldCheck]:
    baseline_manifest = _load_manifest(baseline / "manifest.json")
    other_manifest = _load_manifest(other / "manifest.json")
    baseline_identities = _manifest_identities(baseline_manifest)
    other_identities = _manifest_identities(other_manifest)
    checks: list[FieldCheck] = []
    for field in MANIFEST_COMPARED_FIELDS:
        left = baseline_identities[field]
        right = other_identities[field]
        if field == "algorithms":
            if left == right:
                size = len(left) if isinstance(left, dict) else 0
                detail = f"({size} algorithm entries)"
            else:
                detail = _algorithm_map_diff(left, right)
        else:
            detail = f"({_display(left)})" if left == right else (
                f"(baseline={_display(left)}, compare={_display(right)})"
            )
        checks.append(
            FieldCheck(name=f"manifest.{field}", consistent=left == right, detail=detail)
        )
    return checks


def _record_checks(baseline: Path, other: Path, label: str) -> list[FieldCheck]:
    baseline_rows = _load_records(baseline / "raw_results.csv")
    other_rows = _load_records(other / "raw_results.csv")
    checks: list[FieldCheck] = []
    checks.append(
        FieldCheck(
            name=f"{label}.row_count",
            consistent=len(baseline_rows) == len(other_rows),
            detail=(
                f"(baseline={len(baseline_rows)}, compare={len(other_rows)})"
                if len(baseline_rows) != len(other_rows)
                else f"({len(baseline_rows)} rows each)"
            ),
        )
    )

    paired, ambiguous = _pair_rows(baseline_rows, other_rows)
    fully_paired = not ambiguous and len(paired) == len(baseline_rows) == len(other_rows)
    if fully_paired:
        index_detail = (
            f"({len(paired)} of {len(baseline_rows)} baseline and "
            f"{len(other_rows)} compare rows paired)"
        )
    else:
        index_detail = (
            f"({len(paired)} of {len(baseline_rows)} baseline and "
            f"{len(other_rows)} compare rows paired; unpaired: "
            + ", ".join(ambiguous[:3])
            + ("..." if len(ambiguous) > 3 else "")
            + ")"
        )
    checks.append(
        FieldCheck(name=f"{label}.row_index", consistent=fully_paired, detail=index_detail)
    )

    baseline_order = [_logical_key(row) for row in baseline_rows]
    other_order = [_logical_key(row) for row in other_rows]
    first_difference: str | None = None
    if baseline_order != other_order:
        for index, (left, right) in enumerate(zip(baseline_order, other_order)):
            if left != right:
                first_difference = f"position {index}: {left} != {right}"
                break
        if first_difference is None:
            first_difference = "length differs"
    checks.append(
        FieldCheck(
            name=f"{label}.row_order",
            consistent=baseline_order == other_order,
            detail=(
                f"({len(baseline_order)} rows in the canonical plan order)"
                if baseline_order == other_order
                else f"(first difference: {first_difference})"
            ),
        )
    )

    for field in REPORT_FIELDS:
        if field in ALWAYS_EXEMPT:
            checks.append(
                FieldCheck(
                    name=f"{label}.{field}",
                    consistent=True,
                    detail="(exempt: wall-clock runtime varies by machine)",
                )
            )
            continue
        mismatched = 0
        exempt = 0
        matched = 0
        example: str | None = None
        for left, right in paired:
            if field in TIMEOUT_EXEMPT and (
                _row_is_timeout(left) or _row_is_timeout(right)
            ):
                exempt += 1
                continue
            matched += 1
            if _field_value(left, field) != _field_value(right, field):
                mismatched += 1
                if example is None:
                    example = left.run_id
        checks.append(
            FieldCheck(
                name=f"{label}.{field}",
                consistent=mismatched == 0,
                detail=(
                    f"({matched} compared, {exempt} timeout-exempt)"
                    if mismatched == 0
                    else f"({mismatched} of {matched + exempt} rows differ; "
                    f"example run_id={example})"
                ),
                example=example,
            )
        )
    return checks


def compare_pair(baseline: Path, other: Path, label: str) -> list[FieldCheck]:
    """Compare one result directory against the baseline."""
    return [
        *_manifest_checks(baseline, other),
        *_record_checks(baseline, other, label),
    ]


def print_checks(baseline: Path, other: Path, checks: Sequence[FieldCheck]) -> int:
    print(f"comparing {baseline} (baseline) with {other}")
    inconsistent = 0
    for check in checks:
        status = "consistent" if check.consistent else "inconsistent"
        print(f"  {check.name}: {status} {check.detail}".rstrip())
        if not check.consistent:
            inconsistent += 1
    print(
        "matrix comparison: "
        + ("CONSISTENT" if inconsistent == 0 else f"INCONSISTENT ({inconsistent} checks)")
    )
    return inconsistent


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare raw benchmark results across a reproducibility matrix; "
            "the first result directory is the baseline."
        )
    )
    parser.add_argument(
        "--result",
        action="append",
        type=Path,
        required=True,
        metavar="DIR",
        help="result directory containing raw_results.csv and manifest.json",
    )
    args = parser.parse_args(argv)
    results = [path.resolve() for path in args.result]
    if len(results) < 2:
        parser.error("--result must name a baseline and at least one compare directory")
    baseline, compare_dirs = results[0], results[1:]
    try:
        inconsistent = 0
        for compare_dir in compare_dirs:
            checks = compare_pair(baseline, compare_dir, "raw_results")
            inconsistent += print_checks(baseline, compare_dir, checks)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"matrix comparison failed: {error}", file=sys.stderr)
        return 1
    return 0 if inconsistent == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
