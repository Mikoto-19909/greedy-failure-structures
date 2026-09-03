"""Compare paired-seed and independent-seed treatment-minus-control differences.

This module answers one question with two benchmark directories: does sharing a
seed between a treatment case and its matched control within a repetition
reduce the spread of the treatment-minus-control difference relative to
generating the two independently?

The analysis reads the canonical raw_results.csv and instances.csv artifacts
produced by the benchmark runner and verifies the digests the benchmark
manifest records for them against the files actually read. The effective seed
that drove generation -- the coupling seed when the runner injected one,
otherwise the instance seed -- must be shared between a treatment and its
matched control at every repetition in the paired run and must be independent
in the unpaired run; when that does not hold the analysis refuses to compare.
For every family-algorithm-metric cell it builds two
difference distributions, one from the paired run and one from the unpaired
run, each holding one difference per repetition:

    difference = value(treatment) - value(control)

For the coverage metric a positive difference means the treatment covered more
elements; for the optimality-gap metric a positive difference means the
treatment is further from the reference optimum. The sample variance of the
two difference distributions is the variance comparison: a variance ratio
below one means the paired scheme has the tighter difference spread.

The convention for finding a matched control is a case-name suffix: the case
named X plus the control suffix is the control of the case named X. Every pair
must share the effective seed within each repetition in the paired run and
must not share one in the unpaired run; the module verifies both properties
and raises when they do not hold.

Run it as a module:

    python -m maxcover.paired_seed_analysis --paired-results results/pairing-v1/paired --unpaired-results results/pairing-v1/unpaired --output results/pairing-v1/analysis

Numeric results are written to the output directory (comparison.csv and
differences.csv) with analysis_manifest.json recording their input and output
digests and the verified schema and effective-coupling constraints. They are
local evidence only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import correlation, fmean, stdev, variance
from typing import ClassVar

from ._instance_contracts import InstanceRecord
from ._run_contracts import RunRecord


METRICS = ("coverage", "optimality_gap")
DEFAULT_CONTROL_SUFFIX = "_control"

# The benchmark manifest schema version written by 'benchmark.py'.
#
# Declared here rather than imported because 'benchmark.py' writes the value
# inline and exposes no constant for it; the same declaration lives in
# .github/scripts/validate_benchmark_output.py and is asserted against a real
# runner-written manifest by tests/test_output_validation.py. The pairing
# analysis accepts no other version: it reads fields the manifest provides
# only under this schema, so a future bump must fail here loudly rather than
# be interpreted under the old shape.
SUPPORTED_BENCHMARK_MANIFEST_SCHEMA_VERSION = 1


class AnalysisError(ValueError):
    """One or more inconsistencies in the paired-seed comparison inputs."""

    def __init__(self, issues: Iterable[str]) -> None:
        messages = tuple(issues)
        if not messages:
            raise ValueError("an analysis error requires at least one issue")
        self.issues = messages
        super().__init__("; ".join(messages))


@dataclass(frozen=True, slots=True)
class DifferenceSeries:
    """One difference per repetition under one scheme for one analysis cell."""

    scheme: str
    family: str
    treatment_case: str
    control_case: str
    algorithm_id: str
    algorithm: str
    metric: str
    repetitions: tuple[int, ...]
    differences: tuple[float, ...]
    treatment_values: tuple[float, ...]
    control_values: tuple[float, ...]
    treatment_seeds: tuple[int | None, ...]
    control_seeds: tuple[int | None, ...]
    missing_count: int


@dataclass(frozen=True, slots=True)
class DifferenceSummary:
    """Sample statistics of one difference distribution."""

    n: int
    mean: float | None
    sample_variance: float | None
    sample_standard_deviation: float | None
    minimum: float | None
    maximum: float | None
    treatment_control_correlation: float | None

    @classmethod
    def of(
        cls,
        differences: tuple[float, ...],
        treatment_values: tuple[float, ...],
        control_values: tuple[float, ...],
    ) -> "DifferenceSummary":
        if not differences:
            return cls(0, None, None, None, None, None, None)
        spread = stdev(differences) if len(differences) > 1 else None
        paired_correlation: float | None = None
        if len(differences) > 1:
            try:
                paired_correlation = correlation(treatment_values, control_values)
            except (ValueError, ZeroDivisionError):
                paired_correlation = None
        return cls(
            n=len(differences),
            mean=fmean(differences),
            sample_variance=None if spread is None else variance(differences),
            sample_standard_deviation=spread,
            minimum=min(differences),
            maximum=max(differences),
            treatment_control_correlation=paired_correlation,
        )


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    """One family-by-algorithm-by-metric comparison row."""

    CSV_FIELDS: ClassVar[tuple[str, ...]] = (
        "family",
        "treatment_case",
        "control_case",
        "algorithm_id",
        "algorithm",
        "metric",
        "expected_repetitions",
        "paired_count",
        "unpaired_count",
        "paired_missing_count",
        "unpaired_missing_count",
        "paired_seed_shared_count",
        "unpaired_seed_shared_count",
        "paired_mean_difference",
        "unpaired_mean_difference",
        "paired_variance_difference",
        "unpaired_variance_difference",
        "paired_standard_deviation_difference",
        "unpaired_standard_deviation_difference",
        "variance_ratio_paired_over_unpaired",
        "paired_treatment_control_correlation",
        "unpaired_treatment_control_correlation",
        "paired_minimum_difference",
        "paired_maximum_difference",
        "unpaired_minimum_difference",
        "unpaired_maximum_difference",
    )

    family: str
    treatment_case: str
    control_case: str
    algorithm_id: str
    algorithm: str
    metric: str
    expected_repetitions: int
    paired: DifferenceSummary
    unpaired: DifferenceSummary
    paired_missing_count: int
    unpaired_missing_count: int
    paired_seed_shared_count: int
    unpaired_seed_shared_count: int

    def variance_ratio(self) -> float | None:
        if (
            self.paired.sample_variance is not None
            and self.unpaired.sample_variance is not None
            and self.unpaired.sample_variance > 0
        ):
            return self.paired.sample_variance / self.unpaired.sample_variance
        return None

    def to_csv_row(self) -> dict[str, object]:
        def optional(value: float | None) -> str:
            return "" if value is None else f"{value:.10g}"

        return {
            "family": self.family,
            "treatment_case": self.treatment_case,
            "control_case": self.control_case,
            "algorithm_id": self.algorithm_id,
            "algorithm": self.algorithm,
            "metric": self.metric,
            "expected_repetitions": self.expected_repetitions,
            "paired_count": self.paired.n,
            "unpaired_count": self.unpaired.n,
            "paired_missing_count": self.paired_missing_count,
            "unpaired_missing_count": self.unpaired_missing_count,
            "paired_seed_shared_count": self.paired_seed_shared_count,
            "unpaired_seed_shared_count": self.unpaired_seed_shared_count,
            "paired_mean_difference": optional(self.paired.mean),
            "unpaired_mean_difference": optional(self.unpaired.mean),
            "paired_variance_difference": optional(self.paired.sample_variance),
            "unpaired_variance_difference": optional(self.unpaired.sample_variance),
            "paired_standard_deviation_difference": optional(
                self.paired.sample_standard_deviation
            ),
            "unpaired_standard_deviation_difference": optional(
                self.unpaired.sample_standard_deviation
            ),
            "variance_ratio_paired_over_unpaired": optional(self.variance_ratio()),
            "paired_treatment_control_correlation": optional(
                self.paired.treatment_control_correlation
            ),
            "unpaired_treatment_control_correlation": optional(
                self.unpaired.treatment_control_correlation
            ),
            "paired_minimum_difference": optional(self.paired.minimum),
            "paired_maximum_difference": optional(self.paired.maximum),
            "unpaired_minimum_difference": optional(self.unpaired.minimum),
            "unpaired_maximum_difference": optional(self.unpaired.maximum),
        }


def load_run_records(results_dir: Path) -> list[RunRecord]:
    """Read and validate one canonical raw_results.csv."""

    path = results_dir / "raw_results.csv"
    if not path.is_file():
        raise AnalysisError([f"missing raw_results.csv in {results_dir}"])
    records: list[RunRecord] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            records.append(RunRecord.from_csv_row(row))
    if not records:
        raise AnalysisError([f"empty raw_results.csv in {results_dir}"])
    return records


def load_instance_records(results_dir: Path) -> list[InstanceRecord]:
    """Read and validate the canonical instances.csv artifact."""

    path = results_dir / "instances.csv"
    if not path.is_file():
        raise AnalysisError([f"missing instances.csv in {results_dir}"])
    records: list[InstanceRecord] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                records.append(InstanceRecord.from_csv_row(row))
            except ValueError as error:
                raise AnalysisError(
                    [f"invalid instance record in {path}: {error}"]
                ) from error
    if not records:
        raise AnalysisError([f"empty instances.csv in {results_dir}"])
    return records


def _record_metric_value(row: RunRecord, metric: str) -> float | None:
    if metric == "coverage":
        return None if row.coverage is None else float(row.coverage)
    if metric == "optimality_gap":
        return None if row.optimality_gap is None else row.optimality_gap
    raise ValueError(f"unsupported metric {metric!r}")


def _unit_rows(
    records: Iterable[RunRecord],
) -> dict[tuple[str, int, str], list[RunRecord]]:
    """Group records by case, repetition, and algorithm; one run per unit."""

    units: dict[tuple[str, int, str], list[RunRecord]] = {}
    for record in records:
        units.setdefault(
            (record.case_id, record.repetition, record.algorithm_id), []
        ).append(record)
    for key, group in units.items():
        if len(group) != 1:
            case_id, repetition, algorithm_id = key
            raise AnalysisError(
                [
                    f"algorithm variant {algorithm_id!r} has {len(group)} runs for case"
                    f" {case_id!r} repetition {repetition}; seeded algorithm variants"
                    " are not supported by the paired-seed analysis"
                ]
            )
    return units


def _build_series(
    records: list[RunRecord],
    *,
    scheme: str,
    family: str,
    treatment_case: str,
    control_case: str,
    algorithm_id: str,
    algorithm: str,
    metric: str,
    expected_repetitions: int,
    require_seed_sharing: bool,
) -> DifferenceSeries:
    """Build one difference per repetition for one analysis cell."""

    units = _unit_rows(records)
    repetitions: list[int] = []
    differences: list[float] = []
    treatment_values: list[float] = []
    control_values: list[float] = []
    treatment_seeds: list[int | None] = []
    control_seeds: list[int | None] = []
    missing = 0
    for repetition in range(expected_repetitions):
        treatment_rows = units.get((treatment_case, repetition, algorithm_id))
        control_rows = units.get((control_case, repetition, algorithm_id))
        if treatment_rows is None or control_rows is None:
            missing += 1
            continue
        treatment_row = treatment_rows[0]
        control_row = control_rows[0]
        treatment_dims = (
            treatment_row.universe_size,
            treatment_row.set_count,
            treatment_row.k,
        )
        control_dims = (
            control_row.universe_size,
            control_row.set_count,
            control_row.k,
        )
        if treatment_dims != control_dims:
            raise AnalysisError(
                [
                    f"case {treatment_case!r} and its control differ in dimensions"
                    f" at repetition {repetition}: {treatment_dims} versus {control_dims}"
                ]
            )
        seeds_equal = (
            treatment_row.seed is not None and treatment_row.seed == control_row.seed
        )
        if require_seed_sharing and not seeds_equal:
            raise AnalysisError(
                [
                    f"paired scheme requires a shared seed for {treatment_case!r}"
                    f" and {control_case!r} at repetition {repetition} but the seeds"
                    f" differ ({treatment_row.seed} versus {control_row.seed})"
                ]
            )
        treatment_value = _record_metric_value(treatment_row, metric)
        control_value = _record_metric_value(control_row, metric)
        if treatment_value is None or control_value is None:
            missing += 1
            continue
        repetitions.append(repetition)
        differences.append(treatment_value - control_value)
        treatment_values.append(treatment_value)
        control_values.append(control_value)
        treatment_seeds.append(treatment_row.seed)
        control_seeds.append(control_row.seed)
    return DifferenceSeries(
        scheme=scheme,
        family=family,
        treatment_case=treatment_case,
        control_case=control_case,
        algorithm_id=algorithm_id,
        algorithm=algorithm,
        metric=metric,
        repetitions=tuple(repetitions),
        differences=tuple(differences),
        treatment_values=tuple(treatment_values),
        control_values=tuple(control_values),
        treatment_seeds=tuple(treatment_seeds),
        control_seeds=tuple(control_seeds),
        missing_count=missing,
    )


def _analysis_cells(
    paired_records: list[RunRecord],
    unpaired_records: list[RunRecord],
    *,
    control_suffix: str,
) -> list[tuple[str, str, str, str, str]]:
    """Validate the two run sets and enumerate comparison cells."""

    paired_cases = {record.case_id for record in paired_records}
    unpaired_cases = {record.case_id for record in unpaired_records}
    if paired_cases != unpaired_cases:
        raise AnalysisError(
            [
                "paired and unpaired runs must cover the same cases",
                f"  only in paired: {sorted(paired_cases - unpaired_cases)}",
                f"  only in unpaired: {sorted(unpaired_cases - paired_cases)}",
            ]
        )
    paired_algorithms = {record.algorithm_id for record in paired_records}
    unpaired_algorithms = {record.algorithm_id for record in unpaired_records}
    if paired_algorithms != unpaired_algorithms:
        raise AnalysisError(
            [
                "paired and unpaired runs must cover the same algorithms",
                f"  only in paired: {sorted(paired_algorithms - unpaired_algorithms)}",
                f"  only in unpaired: {sorted(unpaired_algorithms - paired_algorithms)}",
            ]
        )
    paired_repetitions = {record.repetition for record in paired_records}
    unpaired_repetitions = {record.repetition for record in unpaired_records}
    if paired_repetitions != unpaired_repetitions:
        raise AnalysisError(
            [
                "paired and unpaired runs must cover the same repetitions",
                f"  only in paired: {sorted(paired_repetitions - unpaired_repetitions)}",
                f"  only in unpaired: {sorted(unpaired_repetitions - paired_repetitions)}",
            ]
        )

    controls: list[str] = []
    for case in sorted(paired_cases):
        if not case.endswith(control_suffix):
            continue
        treatment = case[: -len(control_suffix)]
        if treatment not in paired_cases:
            raise AnalysisError(
                [
                    f"control case {case!r} has no matching treatment case"
                    f" {treatment!r}; the pair must share dimensions"
                ]
            )
        controls.append(case)
    if not controls:
        raise AnalysisError(
            [
                f"no control case found; cases must end with {control_suffix!r}"
            ]
        )

    names = {record.algorithm_id: record.algorithm for record in paired_records}
    cells: list[tuple[str, str, str, str, str]] = []
    for control_case in sorted(controls):
        treatment_case = control_case[: -len(control_suffix)]
        families = {
            record.family
            for record in paired_records + unpaired_records
            if record.case_id == treatment_case
        }
        if len(families) != 1:
            raise AnalysisError(
                [
                    f"treatment case {treatment_case!r} spans multiple families in"
                    f" one run set: {sorted(families)}"
                ]
            )
        family = next(iter(families))
        for algorithm_id in sorted(paired_algorithms):
            cells.append(
                (
                    family,
                    treatment_case,
                    control_case,
                    algorithm_id,
                    names[algorithm_id],
                )
            )
    return cells


def _effective_seed(record: InstanceRecord) -> int | None:
    """The seed value that actually drove instance generation.

    The runner passes the per-repetition seed as the coupling seed for the
    families that support one, so a coupling seed has generation authority over
    the instance seed; without one the instance seed itself is the effective
    value. A record with neither cannot participate in a seeded comparison.
    """

    return record.coupling_seed if record.coupling_seed is not None else record.seed


def _validate_effective_coupling(
    instances: list[InstanceRecord],
    *,
    scheme: str,
    treatment_case: str,
    control_case: str,
    repetition_count: int,
) -> None:
    """Verify that one treatment-control pair is coupled or independent.

    The raw_results.csv seed columns are the pairing under the recorded run
    identity; instances.csv records the seed that generation actually consumed,
    which for coupling-capable families is the coupling seed rather than the
    instance seed. The comparison is only valid when the two agree on the
    effective value: shared in the paired scheme, independent in the unpaired
    scheme.
    """

    by_key = {(record.case_id, record.repetition): record for record in instances}
    issues: list[str] = []
    for repetition in range(repetition_count):
        treatment = by_key.get((treatment_case, repetition))
        control = by_key.get((control_case, repetition))
        if treatment is None or control is None:
            if treatment is not None or control is not None:
                issues.append(
                    f"instances.csv records only one of {treatment_case!r} and"
                    f" {control_case!r} at repetition {repetition}"
                )
            else:
                issues.append(
                    f"instances.csv records neither {treatment_case!r} nor"
                    f" {control_case!r} at repetition {repetition}"
                )
            continue
        effective_treatment = _effective_seed(treatment)
        effective_control = _effective_seed(control)
        if effective_treatment is None or effective_control is None:
            lacking = [
                case_name
                for case_name, effective in (
                    (treatment_case, effective_treatment),
                    (control_case, effective_control),
                )
                if effective is None
            ]
            issues.append(
                f"{scheme!r} instances for"
                f" {', '.join(repr(name) for name in lacking)} carry neither a"
                f" seed nor a coupling seed at repetition {repetition}"
            )
            continue
        if scheme == "paired" and effective_treatment != effective_control:
            issues.append(
                f"paired scheme requires the same effective coupling seed for"
                f" {treatment_case!r} and {control_case!r} at repetition"
                f" {repetition}: {effective_treatment} versus"
                f" {effective_control}"
            )
        if scheme == "unpaired" and effective_treatment == effective_control:
            issues.append(
                f"unpaired scheme requires independent effective seeds for"
                f" {treatment_case!r} and {control_case!r} at repetition"
                f" {repetition}: shared value {effective_treatment}"
            )
    if issues:
        raise AnalysisError(issues)


def analyze_pairing(
    paired_records: list[RunRecord],
    unpaired_records: list[RunRecord],
    *,
    paired_instances: list[InstanceRecord],
    unpaired_instances: list[InstanceRecord],
    control_suffix: str = DEFAULT_CONTROL_SUFFIX,
) -> tuple[list[ComparisonRow], list[dict[str, object]]]:
    """Compute comparison rows and flattened seed-level difference samples."""

    if not control_suffix:
        raise AnalysisError(["control suffix must not be empty"])
    cells = _analysis_cells(
        paired_records, unpaired_records, control_suffix=control_suffix
    )
    repetition_count = 1 + max(
        record.repetition for record in paired_records + unpaired_records
    )
    pairs = sorted({(treatment, control) for _, treatment, control, _, _ in cells})
    for treatment, control in pairs:
        _validate_effective_coupling(
            paired_instances,
            scheme="paired",
            treatment_case=treatment,
            control_case=control,
            repetition_count=repetition_count,
        )
        _validate_effective_coupling(
            unpaired_instances,
            scheme="unpaired",
            treatment_case=treatment,
            control_case=control,
            repetition_count=repetition_count,
        )
    comparison: list[ComparisonRow] = []
    samples: list[dict[str, object]] = []
    for family, treatment, control, algorithm_id, algorithm in cells:
        for metric in METRICS:
            paired = _build_series(
                paired_records,
                scheme="paired",
                family=family,
                treatment_case=treatment,
                control_case=control,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                metric=metric,
                expected_repetitions=repetition_count,
                require_seed_sharing=True,
            )
            unpaired = _build_series(
                unpaired_records,
                scheme="unpaired",
                family=family,
                treatment_case=treatment,
                control_case=control,
                algorithm_id=algorithm_id,
                algorithm=algorithm,
                metric=metric,
                expected_repetitions=repetition_count,
                require_seed_sharing=False,
            )
            comparison.append(
                ComparisonRow(
                    family=family,
                    treatment_case=treatment,
                    control_case=control,
                    algorithm_id=algorithm_id,
                    algorithm=algorithm,
                    metric=metric,
                    expected_repetitions=repetition_count,
                    paired=DifferenceSummary.of(
                        paired.differences, paired.treatment_values, paired.control_values
                    ),
                    unpaired=DifferenceSummary.of(
                        unpaired.differences,
                        unpaired.treatment_values,
                        unpaired.control_values,
                    ),
                    paired_missing_count=paired.missing_count,
                    unpaired_missing_count=unpaired.missing_count,
                    paired_seed_shared_count=sum(
                        1
                        for a, b in zip(paired.treatment_seeds, paired.control_seeds)
                        if a is not None and a == b
                    ),
                    unpaired_seed_shared_count=sum(
                        1
                        for a, b in zip(
                            unpaired.treatment_seeds, unpaired.control_seeds
                        )
                        if a is not None and a == b
                    ),
                )
            )
            for index, repetition in enumerate(paired.repetitions):
                samples.append(
                    {
                        "scheme": "paired",
                        "family": family,
                        "treatment_case": treatment,
                        "control_case": control,
                        "algorithm_id": algorithm_id,
                        "algorithm": algorithm,
                        "metric": metric,
                        "repetition": repetition,
                        "treatment_value": paired.treatment_values[index],
                        "control_value": paired.control_values[index],
                        "difference": paired.differences[index],
                        "treatment_seed": paired.treatment_seeds[index],
                        "control_seed": paired.control_seeds[index],
                        "seeds_equal": (
                            paired.treatment_seeds[index] is not None
                            and paired.treatment_seeds[index]
                            == paired.control_seeds[index]
                        ),
                    }
                )
            for index, repetition in enumerate(unpaired.repetitions):
                samples.append(
                    {
                        "scheme": "unpaired",
                        "family": family,
                        "treatment_case": treatment,
                        "control_case": control,
                        "algorithm_id": algorithm_id,
                        "algorithm": algorithm,
                        "metric": metric,
                        "repetition": repetition,
                        "treatment_value": unpaired.treatment_values[index],
                        "control_value": unpaired.control_values[index],
                        "difference": unpaired.differences[index],
                        "treatment_seed": unpaired.treatment_seeds[index],
                        "control_seed": unpaired.control_seeds[index],
                        "seeds_equal": (
                            unpaired.treatment_seeds[index] is not None
                            and unpaired.treatment_seeds[index]
                            == unpaired.control_seeds[index]
                        ),
                    }
                )
    return comparison, samples


DIFFERENCE_FIELDS = (
    "scheme",
    "family",
    "treatment_case",
    "control_case",
    "algorithm_id",
    "algorithm",
    "metric",
    "repetition",
    "treatment_value",
    "control_value",
    "difference",
    "treatment_seed",
    "control_seed",
    "seeds_equal",
)


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: Iterable[Mapping[str, object]],
) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state(root: Path | None = None) -> dict[str, object]:
    if root is None:
        root = Path(__file__).resolve().parents[2]

    def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", f"safe.directory={root}", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    commit = invoke("rev-parse", "HEAD")
    status = invoke("status", "--porcelain")
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": status.returncode != 0 or bool(status.stdout.strip()),
    }


def _manifest_output_sha256(
    manifest: Mapping[str, object], filename: str, issues: list[str]
) -> str | None:
    """The checksum the benchmark manifest declares for one output file."""

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        issues.append("outputs must be an object")
        return None
    entry = outputs.get(filename)
    if not isinstance(entry, dict):
        issues.append(f"outputs.{filename} must be an object")
        return None
    digest = entry.get("sha256")
    if not (
        isinstance(digest, str)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    ):
        issues.append(
            f"outputs.{filename}.sha256 must be a lowercase SHA-256 digest"
        )
        return None
    return digest


def _input_provenance(directory: Path) -> dict[str, object]:
    raw_results = directory / "raw_results.csv"
    instances = directory / "instances.csv"
    manifest_path = directory / "manifest.json"
    provenance: dict[str, object] = {
        "raw_results_sha256": None,
        "benchmark_raw_results_sha256": None,
        "instances_sha256": None,
        "benchmark_instances_sha256": None,
        "benchmark_manifest_sha256": None,
        "benchmark_schema_version": None,
        "config_hash": None,
        "benchmark_git": None,
    }
    if not manifest_path.is_file():
        raise AnalysisError([f"benchmark manifest is missing: {manifest_path}"])
    if not raw_results.is_file():
        raise AnalysisError([f"missing raw_results.csv in {directory}"])
    if not instances.is_file():
        raise AnalysisError([f"missing instances.csv in {directory}"])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisError(
            [f"cannot read benchmark manifest {manifest_path}: {error}"]
        )
    if not isinstance(manifest, dict):
        raise AnalysisError(
            [f"benchmark manifest {manifest_path} must be an object"]
        )

    schema_version = manifest.get("schema_version")
    configuration = manifest.get("configuration")
    benchmark_git = manifest.get("git")
    config_hash = (
        configuration.get("config_hash")
        if isinstance(configuration, dict)
        else None
    )
    commit = benchmark_git.get("commit") if isinstance(benchmark_git, dict) else None
    dirty = benchmark_git.get("dirty") if isinstance(benchmark_git, dict) else None
    issues: list[str] = []
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        issues.append("schema_version must be an integer")
    elif schema_version != SUPPORTED_BENCHMARK_MANIFEST_SCHEMA_VERSION:
        issues.append(
            "schema_version must be "
            f"{SUPPORTED_BENCHMARK_MANIFEST_SCHEMA_VERSION}"
        )
    if not (
        isinstance(config_hash, str)
        and len(config_hash) == 64
        and all(character in "0123456789abcdef" for character in config_hash)
    ):
        issues.append("configuration.config_hash must be a lowercase SHA-256 digest")
    if not isinstance(benchmark_git, dict) or "commit" not in benchmark_git:
        issues.append("git.commit must be present")
    elif commit is not None and not (
        isinstance(commit, str)
        and len(commit) == 40
        and all(character in "0123456789abcdef" for character in commit)
    ):
        issues.append("git.commit must be null or a lowercase 40-character commit")
    if not isinstance(dirty, bool):
        issues.append("git.dirty must be a boolean")
    declared_raw_results = _manifest_output_sha256(
        manifest, "raw_results.csv", issues
    )
    declared_instances = _manifest_output_sha256(manifest, "instances.csv", issues)
    actual_raw_results = _sha256_file(raw_results)
    actual_instances = _sha256_file(instances)
    if declared_raw_results is not None and declared_raw_results != actual_raw_results:
        issues.append(
            "raw_results.csv does not match the benchmark manifest checksum:"
            f" manifest records {declared_raw_results}, file is"
            f" {actual_raw_results}"
        )
    if declared_instances is not None and declared_instances != actual_instances:
        issues.append(
            "instances.csv does not match the benchmark manifest checksum:"
            f" manifest records {declared_instances}, file is {actual_instances}"
        )
    if issues:
        raise AnalysisError(
            [f"benchmark manifest {manifest_path}: {issue}" for issue in issues]
        )

    assert isinstance(schema_version, int)
    assert isinstance(config_hash, str)
    assert isinstance(benchmark_git, dict)
    assert declared_raw_results is not None
    assert declared_instances is not None
    provenance["benchmark_manifest_sha256"] = _sha256_file(manifest_path)
    provenance["benchmark_schema_version"] = schema_version
    provenance["config_hash"] = config_hash
    provenance["benchmark_git"] = dict(benchmark_git)
    provenance["raw_results_sha256"] = actual_raw_results
    provenance["benchmark_raw_results_sha256"] = declared_raw_results
    provenance["instances_sha256"] = actual_instances
    provenance["benchmark_instances_sha256"] = declared_instances
    return provenance


def _write_analysis_manifest(
    output: Path,
    inputs: Mapping[str, Mapping[str, object]],
    *,
    control_suffix: str,
    comparison_count: int,
    sample_count: int,
) -> None:
    manifest = {
        "analysis": "paired_seed_variance_comparison",
        "contract": {
            "control_suffix": control_suffix,
            "difference": "treatment_value-control_value",
            "metrics": list(METRICS),
            "variance_ratio": "paired_sample_variance/unpaired_sample_variance",
            "effective_coupling": (
                "treatment and control instances share the effective seed in the"
                " paired scheme and must differ in the unpaired scheme"
            ),
            "input_binding": (
                "benchmark manifest output checksums must match the input files"
            ),
        },
        "inputs": {name: dict(value) for name, value in inputs.items()},
        "outputs": {
            "comparison.csv": {
                "rows": comparison_count,
                "sha256": _sha256_file(output / "comparison.csv"),
            },
            "differences.csv": {
                "rows": sample_count,
                "sha256": _sha256_file(output / "differences.csv"),
            },
        },
        "schema_version": 1,
        "source": {
            "git": _git_state(),
            "module": "src/maxcover/paired_seed_analysis.py",
        },
    }
    (output / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _print_summary(rows: list[ComparisonRow]) -> None:
    print(
        "family | algorithm | metric | n(p) | n(u) | mean(p) | mean(u) | "
        "stddev(p) | stddev(u) | variance ratio"
    )
    for row in rows:
        ratio = row.variance_ratio()
        print(
            " | ".join(
                [
                    row.family,
                    row.algorithm_id,
                    row.metric,
                    str(row.paired.n),
                    str(row.unpaired.n),
                    _format_optional(row.paired.mean),
                    _format_optional(row.unpaired.mean),
                    _format_optional(row.paired.sample_standard_deviation),
                    _format_optional(row.unpaired.sample_standard_deviation),
                    _format_optional(ratio),
                ]
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare paired-seed and independent-seed treatment-minus-control "
            "difference variance from two benchmark output directories."
        ),
    )
    parser.add_argument("--paired-results", type=Path, required=True, metavar="DIR")
    parser.add_argument("--unpaired-results", type=Path, required=True, metavar="DIR")
    parser.add_argument("--output", type=Path, required=True, metavar="DIR")
    parser.add_argument(
        "--control-suffix",
        default=DEFAULT_CONTROL_SUFFIX,
        metavar="SUFFIX",
        help=f"case-name suffix marking a control (default: {DEFAULT_CONTROL_SUFFIX})",
    )
    args = parser.parse_args(argv)

    input_provenance = {
        "paired": _input_provenance(args.paired_results),
        "unpaired": _input_provenance(args.unpaired_results),
    }
    paired = load_run_records(args.paired_results)
    unpaired = load_run_records(args.unpaired_results)
    paired_instances = load_instance_records(args.paired_results)
    unpaired_instances = load_instance_records(args.unpaired_results)
    comparison, samples = analyze_pairing(
        paired,
        unpaired,
        paired_instances=paired_instances,
        unpaired_instances=unpaired_instances,
        control_suffix=args.control_suffix,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    _write_csv(
        args.output / "comparison.csv",
        ComparisonRow.CSV_FIELDS,
        [row.to_csv_row() for row in comparison],
    )
    _write_csv(args.output / "differences.csv", DIFFERENCE_FIELDS, samples)
    _write_analysis_manifest(
        args.output,
        input_provenance,
        control_suffix=args.control_suffix,
        comparison_count=len(comparison),
        sample_count=len(samples),
    )
    _print_summary(comparison)
    print(f"Comparison written to {args.output / 'comparison.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
