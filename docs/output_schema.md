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

## Paired algorithm analyses

The runner writes these typed files when their required variants and valid
instance-equal pairs are available:

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

`search_comparison.csv` is a compatibility comparison for paired search
variants. `stochastic_summary.csv` summarizes explicitly seeded stochastic
algorithm runs.

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

A header-only CSV or a chart with no applicable typed rows is a valid artifact.
It means the configured run did not supply the inputs required by that analysis;
it does not mean the metric equals zero.

## Status and exact-reference semantics

- `optimal` means an exact method closed its bound and may supply a reference
  optimum.
- `feasible` means a completed incumbent is available but is not a proved
  optimum.
- `timeout` means work stopped at its configured limit; an incumbent or bound
  may be present, but the timeout run itself does not prove an optimum. The
  normalized row may still carry a reference optimum from an independently
  validated instance certificate or another exact run for the same instance.
- `error` means no valid algorithm result was produced.

Failure rates, relative gaps, and other optimum-relative analyses require a
valid optimal reference for the same instance. Blank values express
ineligibility or unavailable data and must not be interpreted as zero.

## Replay artifacts

The runner writes self-contained JSON files under `failures/` for replayable
timeout or error cases. Each file includes the serialized instance, recorded
algorithm identity and options, and the result fields used for comparison. The
`replay` command can use the recorded algorithm or an explicit replacement.

## Manifest and independent validation

`manifest.json` records the experiment identity, normalized configuration hash,
Git state, Python and operating-system metadata, optional OR-Tools version,
algorithm versions and options, seeds, execution counts, analysis contracts,
and checksums for runner-owned artifacts.

A matching checksum proves that an artifact has not changed since the manifest
was written. It does not prove that the original computation was correct. Use
the independent validator to read the canonical artifacts back and recompute
their declared relationships:

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

Generated output remains local under `results/` and is not part of the
repository's published snapshot.
