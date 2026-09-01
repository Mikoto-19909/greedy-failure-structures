# Reproducibility matrix

This matrix verifies the determinism contract declared in
[`faq.md`](faq.md) and described in [`output_schema.md`](output_schema.md)
across operating systems and Python versions. It is one declaration-plus-code
pair: the declaration is this document, and the enforcement half is
[`compare_matrix_outputs.py`](../.github/scripts/compare_matrix_outputs.py),
run by the
[`reproducibility-matrix.yml`](../.github/workflows/reproducibility-matrix.yml)
workflow. The two must be changed together.

## The declaration

The FAQ states the underlying guarantee: with the same normalized
configuration, algorithm version, and explicit seed, completed runs reproduce
the instance identities, selected set indices, coverage values, and the
canonical row ordering. Wall-clock runtime, timestamps, and environment
metadata may vary by machine. A run stopped by its wall-clock limit reports
the incumbent it had reached when the limit fired, and because progress is
checked against the wall clock, that incumbent and its coverage can differ
across machines and are exempt from the guarantee.

The matrix enforces exactly that statement over the quick benchmark config.
No quantitative claim about the results is made here; the matrix only checks
that the same experiment reproduces.

## Raw results fields

Rows of `raw_results.csv` are paired by their logical run identity:
`case_id`, `repetition`, `algorithm_id`, `algorithm_seed`, and `algorithm`.
That is the execution-plan position a run was planned for, so it is the unit
the deterministic guarantee applies to. Within a pair, every field below is
compared, subject to the stated exemption:

| field | compared | exemption |
| --- | --- | --- |
| `config_hash` | bit-exact | none |
| `case_id` | bit-exact | none |
| `instance_id` | bit-exact | none |
| `run_id` | bit-exact | none |
| `case` | bit-exact | none |
| `repetition` | bit-exact | part of the pairing key |
| `seed` | bit-exact | none |
| `family` | bit-exact | none |
| `universe_size` | bit-exact | none |
| `set_count` | bit-exact | none |
| `k` | bit-exact | none |
| `parameters` | bit-exact | none |
| `algorithm_id` | bit-exact | part of the pairing key |
| `algorithm_seed` | bit-exact | part of the pairing key |
| `algorithm` | bit-exact | part of the pairing key |
| `algorithm_options` | bit-exact | none |
| `algorithm_metadata` | bit-exact | exempt when either side is timeout |
| `status` | bit-exact | none |
| `coverage` | bit-exact | exempt when either side is timeout |
| `best_bound` | bit-exact | exempt when either side is timeout |
| `optimum` | bit-exact | none |
| `optimality_gap` | bit-exact | exempt when either side is timeout |
| `runtime_seconds` | never | wall clock, machine-specific |
| `nodes_or_iterations` | bit-exact | exempt when either side is timeout |
| `selected` | bit-exact, whole sequence | exempt when either side is timeout |
| `error_message` | bit-exact | none |

Two derived fields are not compared as independent fields: `is_exact` and
`timed_out` follow `status` by construction (the record loader rejects a row
where they disagree with it), and `schema_version` of the row is normalized
on read - a run whose records cannot be loaded under the current schema is a
hard comparison error, not a field difference.

The `status` field is compared. A run that completed inside its limit on one
platform and was stopped by the limit on another is a disagreement the matrix
reports, even though the two platforms may both be correct for their own wall
clocks; the exemption above only waives the incumbent-bearing fields of rows
whose status is `timeout` on either side of the pair.

## Canonical row order

The runner writes `raw_results.csv` rows in execution-plan order: case order,
then repetition, then algorithm order. Because the plan order is
deterministic, the row order is part of the reproducibility contract. The
compare script verifies that the sequence of logical run identities in file
order is identical in both runs; a row set that is identical as a set but was
written in a different order is reported as an inconsistent `row_order`.

## Manifest fields

The manifest records machine state alongside experiment identity, so only the
identity part is compared:

| field | compared |
| --- | --- |
| `experiment` | bit-exact |
| `configuration.config_hash` | bit-exact |
| `seeds.base_seed` | bit-exact |
| `seeds.minimum` | bit-exact |
| `seeds.maximum` | bit-exact |
| `seeds.count` | bit-exact |
| `execution.planned_instances` | bit-exact |
| `execution.planned_runs` | bit-exact |
| `algorithms` | bit-exact as a map |

Not compared: `environment`, `timing`, `git`, `configuration.path`,
`execution.workers`, `execution.resumed_runs`, `outputs`, `schema_version`,
and the analysis-contract blocks. These record the machine, the wall clock,
the checkout, the absolute path, a run bookkeeping counter, or content
checksums that legitimately differ because `runtime_seconds` differs. They
are environment- or artifact-state facts, not experiment identity.

## Matrix design

The workflow runs one quick benchmark per matrix cell (OS x Python version):

```yaml
os: [ubuntu-latest, windows-latest]
python-version: ["3.11", "3.12", "3.13"]
```

Each cell runs `python run_project.py benchmark --config
configs/quick.json --output results/quick-matrix --workers 1` on a fresh
checkout, then uploads `raw_results.csv` and `manifest.json` under an
artifact named after the cell. The compare job downloads every cell artifact
and runs the compare script once per non-baseline cell, with the baseline
cell first: `ubuntu-latest` with Python 3.12. The report text is captured and
uploaded as the `matrix-report` artifact, including when the comparison
fails. A mismatch fails the compare job, but this workflow is not wired into
branch protection - whether the check is required for merge is a repository
settings decision.

The base package has no third-party dependencies, so the cells need no `pip
install` and no dependency cache; `--workers 1` is used everywhere, including
locally.

## What the matrix can report

When a cell disagrees with the baseline, the report names the fields and an
example run. A disagreement is a finding, not a tool defect: for example, a
Python version that changes the sequence produced by a seeded generator would
surface as an inconsistent `instance_id` (and therefore an inconsistent
`run_id` and, usually, `coverage` and `selected`) at the same plan position.

The matrix does not verify the derived statistics files, the charts, or the
report. Those are re-derived from `raw_results.csv` by the independent
output validator; this matrix only asks whether the raw runs reproduce. It
also makes no wall-clock claim: `runtime_seconds` is exempt by design.

## Local reproduction and verification

Compare two local result directories:

```console
python .github/scripts/compare_matrix_outputs.py
  --result results/quick-matrix
  --result results/quick-matrix-seed
```

The first directory is the baseline. The exit status is 0 only when every
compared field is consistent with the baseline. The test suite covers the
four observed failure modes (coverage tamper, selected tamper, row-order
reversal, instance identity tamper) and the two allowed differences (runtime
variation and timeout-incumbent variation).