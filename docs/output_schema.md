# Benchmark output guide

A completed benchmark writes canonical inputs, derived statistics, rendered
reports, and a manifest beneath the selected output directory. The record
classes and schema constants in `src/maxcover/` remain the machine-readable
source of truth; this guide explains how the files relate to one another.

## Canonical instance and run artifacts

`instances.csv` records each generated instance and the identity needed to
reproduce it. Its fields include the case and family, deterministic seeds and
coupling identities, dimensions and generator parameters, measured structural
properties, and any validated known-optimum certificate.

`raw_results.csv` records every planned algorithm run. It carries the run and
instance identities, algorithm variant and options, status, incumbent coverage,
bound and reference fields, elapsed runtime, selected set indices, metadata,
and any operational error. Checkpoints are written in this format, and resume
uses the stable run identifier as its unit.

These two files are the canonical inputs consumed by `summarize`. Derived files
must be rebuildable from them and the matching configuration without executing
an algorithm.

## General aggregates

`summary.csv` is the compatibility aggregate retained for older consumers. Its
rows summarize raw runs directly and are not the canonical source for every
analysis.

`descriptive_statistics.csv` is the canonical typed aggregate for coverage,
optimality-gap, and completed-runtime metrics. It records the repetition unit,
eligible samples, timeout and error counts, exact-reference availability, and
descriptive statistics.

`confidence_interval_statistics.csv` contains two-sided intervals for eligible
instance-level means. A row remains present when its interval is not estimable;
the status explains why and unavailable numeric fields remain blank.

`censored_runtime_statistics.csv` records timeout censoring separately from
completed runtime observations. Timeout duration is not silently treated as a
completed runtime.

## Exact-reference coverage and censoring diagnostics

`reference_status.csv` contains one row for every generated instance. It records
the effective reference status, every enabled configured exact variant's status, the
proof sources, certificate availability, and cross-validation state. A solver
excluded by its configured set-count cutoff is recorded as `not_run`; it is not
silently omitted.

`reference_coverage_statistics.csv` groups those rows by family, normalized
generator parameters, and status. Its denominator is every generated instance
in the slice, and its numerator is the instances with at least one validated
optimum proof. The status rows distinguish `optimal`, `feasible`, `timeout`,
`error`, `known_optimum_certificate`, and `not_run` outcomes.

`reference_censoring_bias_statistics.csv` compares retained instances (a proved
reference exists) with excluded instances (no proof) within the same family and
parameter slice. It reports size and measured-structure means and the excluded
mean minus the retained mean. Comparisons remain blank unless both groups have
observations; no missing value is replaced with zero.

`reference_cutoff_sensitivity_statistics.csv` preserves each enabled configured exact
variant's time and set-count cutoffs, status counts, solver-only reference
coverage, and effective coverage after independently validated certificates are
included. Configure multiple variants with different cutoffs to obtain a direct
sensitivity comparison on the same generated instances.

When brute force and Branch-and-Bound or CP-SAT both prove an optimum for the
same eligible small instance, `reference_status.csv` marks that cross-check.
Any disagreement between optimal exact sources or a known-optimum certificate
already stops normalization with an error.

## Paired algorithm analyses

The runner writes these typed files for each completed benchmark. Rows require
the corresponding variants and eligible instance-level observations or pairs;
files remain header-only when no rows apply:

- `greedy_failure_statistics.csv`: Greedy outcomes paired with valid optimal
  references
- `local_search_recovery_statistics.csv`: recovery from Greedy failures
- `local_search_remaining_gap_statistics.csv`: residual exact-reference gap
  after local search
- `heuristic_exact_runtime_ratio_statistics.csv`: completed heuristic/exact
  runtime pairs
- `bnb_node_reduction_statistics.csv`: baseline/enhanced branch-and-bound node
  comparisons
- `quality_runtime_pareto_statistics.csv`: eligible quality/runtime frontier
  classification

`search_comparison.csv` is written only when `bnb_baseline` and `bnb_enhanced`
runs share an instance. `stochastic_summary.csv` is written only when an
explicitly seeded algorithm run has a feasible coverage value. These
compatibility outputs are conditional, unlike the typed files listed above.

## Structural gap cartography artifacts

The `cartography` command adds a separate, checksummed local analysis package:

- `structural_gap_statistics.csv` reports `1 - coverage / optimum` by stressor
  family, strength, treatment/control role, algorithm, and instance seed. It
  includes the mean, median, sample standard deviation, quartiles, range, and a
  two-sided Student-t confidence interval.
- `paired_control_differences.csv` reports seed-paired
  `stressor_gap - control_gap` distributions with the same descriptive and
  interval fields. Missing exact references are counted and excluded rather
  than converted to zero.
- `precision_diagnostics.csv` estimates the seed count needed to reach the
  design's fixed confidence-interval half-width target using the observed
  paired-difference standard deviation.
- `stressor_strength_gap.svg` plots stressor strength against mean gap and its
  interval for each heuristic algorithm.
- `family_algorithm_gap.svg` is the family-by-algorithm map, using an
  equal-weight mean across the configured strength-level means.
- `cartography_manifest.json` binds the benchmark configuration, design, raw
  results, and every cartography artifact by SHA-256.

`validate_cartography_output.py` does not trust those hashes as proof of the
calculation. It independently rebuilds the instance-seed aggregates, paired
differences, intervals, and precision diagnostics from `raw_results.csv`, then
checks the stored values and the manifest bindings.

For algorithms with multiple `algorithm_seeds`, one instance contributes the
arithmetic mean of its complete algorithm-seed gaps. The independent unit for
distribution and interval calculations is therefore the generated instance
seed, not an individual randomized-algorithm run.

## Structural association analyses

The following files associate instance-equal response values with measured or
configured structural predictors. They retain eligibility counts and an
association status instead of substituting zero for missing or constant data:

- `gap_density_association_statistics.csv`
- `gap_overlap_association_statistics.csv`
- `gap_clustering_association_statistics.csv`
- `runtime_set_count_association_statistics.csv`
- `runtime_k_association_statistics.csv`
- `search_nodes_dominated_ratio_association_statistics.csv`

These are descriptive associations. The manifest explicitly excludes causal,
significance, and more elaborate survival or nonlinear modeling from their
contracts.

## Reports and charts

`results_summary.md` renders a local human-readable report from the typed
statistics. The SVG artifacts visualize gap, runtime, structural association,
local-search recovery, quality/runtime, search-node, and timeout views. Their
filenames are enumerated by `REPORT_FILENAMES` in
[`benchmark.py`](../src/maxcover/benchmark.py).

`reference_coverage_by_case.svg` is the cartography missingness layer. Its bars
use all generated instances and preserve the unresolved reference statuses
instead of displaying only the instances eligible for gap analysis.

A header-only CSV or a chart with no applicable typed rows is a valid artifact.
It means the configured run did not supply the inputs required by that analysis;
it does not mean the metric equals zero.

## Status and exact-reference semantics

- `optimal` means an exact method closed its bound and may supply a reference
  optimum.
- `feasible` means an incumbent is available without an optimality proof.
  Check `algorithm_metadata.termination` separately: this status can accompany
  a time or iteration limit and does not establish completed execution.
- `timeout` means work stopped at its configured limit; an incumbent or bound
  may be present, but the timeout run itself does not prove an optimum. The
  normalized row may still carry a reference optimum from an independently
  validated instance certificate or another exact run for the same instance.
- `error` means no valid algorithm result was produced.
- `known_optimum_certificate` means the generator supplied an independently
  validated feasible solution and optimum upper-bound proof.
- `not_run` is a derived reference-diagnostic status used when a configured
  exact variant is ineligible under its set-count cutoff, or when no exact
  source was configured. It is not an algorithm `SolutionStatus`.

Failure rates, relative gaps, and other optimum-relative analyses require a
valid optimal reference for the same instance. Blank values express
ineligibility or unavailable data and must not be interpreted as zero.

## Replay artifacts

The runner writes self-contained JSON files under `failures/` for replayable
timeout or error cases. Each file includes the serialized instance, recorded
algorithm identity and options, and the result fields used for comparison. The
`replay` command can use the recorded algorithm or an explicit replacement, but
the replacement receives the recorded options and must accept that option
contract; replay does not translate options between algorithms.

## Manifest and independent validation

`manifest.json` records the experiment identity, normalized configuration hash,
Git state, Python and operating-system metadata, optional OR-Tools version,
algorithm versions and options, seeds, execution counts, analysis contracts,
and checksums for runner-owned artifacts.

A matching checksum establishes agreement between the current file and the
recorded digest. The check can still pass if both are changed together; it does
not establish the file's history or the correctness of its calculation.

For a completed starter workflow, run:

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

The validator checks Manifest declarations and file digests, the configuration
and execution-plan identities, record consistency, and supported typed
statistics recomputed from `raw_results.csv` and `instances.csv`. It checks
`summary.csv` groups and run counts, the first `Headline checks` report section,
and the charts listed in its `expected_charts` mapping. The remaining report
text and the legacy `gap_by_family.svg` and `runtime_by_algorithm.svg` charts
are covered by file checksums, not content recomputation.

The validator shares statistics and rendering helpers with the producer. It
does not independently reimplement every calculation or replay every algorithm.
Selection and work-count replay covers a supported Lazy Greedy variant and a
paired Greedy variant when present. It rejects timeout and error statuses and
requires a reference optimum for every instance; it
is not a general acceptance check for all legal timeout or missing-reference
outputs. The [fault-injection matrix](fault_injection_matrix.md) records the
tested limits.

The dedicated [core overlap analysis](../analysis/core_overlap_pilot.py) checks
each pilot run's selected sets against its generated instance and declared
coverage. Its additional checks and analysis artifacts are separate from the
benchmark validator's scope.

Full exploratory output stays local under `results/`. A published claim's
minimum frozen evidence belongs in `experiments/core_rq/`, with its binding in
[`CLAIMS.md`](../experiments/core_rq/CLAIMS.md), following
[CONTRIBUTING.md](../CONTRIBUTING.md).
