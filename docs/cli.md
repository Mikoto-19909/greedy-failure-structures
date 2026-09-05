# Command-line workflow

The command line is the canonical interface for validating configurations,
running experiments, rebuilding reports, and replaying serialized cases. Run
all commands from the repository root after installing the package:

```console
python -m pip install -e .
```

Install the optional CP-SAT oracle only when a configuration enables it:

```console
python -m pip install -e ".[oracle]"
```

## Choose a workflow

| Purpose | Configuration or starting point |
| --- | --- |
| Current research | The [fixed overlap pilot plan](https://github.com/Mikoto-19909/greedy-failure-structures/pull/23). It compares `high_overlap` with a dimension- and expected-size-matched `uniform` control using Greedy and an exhaustive reference. |
| Examples and compatibility checks | `demo`, `quick`, and the larger legacy `configs/full.json` workflow. |
| Historical exploration and appendices | Earlier exploratory configurations and broader scans such as `configs/structural_gap_cartography.json`, selected for their documented purpose. |

The [pilot configuration](../configs/core_overlap_pilot.json) and
[offline analysis script](../analysis/core_overlap_pilot.py) are implemented.
The formal experiment is complete; see the [report](../analysis/overlap_pilot_v1.md)
and [C1](../experiments/core_rq/CLAIMS.md#c1). Use the
[dedicated commands](#core-overlap-pilot) to reproduce the fixed design.

Omitting the CLI command runs `quick`. The PowerShell wrapper also defaults to
quick, and the Dashboard initially prefers `quick.json` without a retained
selection. These remain example defaults. `full.json` is a larger legacy
multi-family benchmark, not the complete current research study:

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

The quick and full configurations retain schema v1 and emit an expected
`LegacyConfigWarning`. Other older configurations can still support active
checks: `p3_lazy_greedy.json` is used by CI, `p7_controlled_stressors.json` by
generator audits, and the pairing configurations by paired-seed method checks.
See the [workflow index](README.md) for those roles.

## Core overlap pilot

The published evidence uses clean commit `27acae5f2ee9f478fba22af98c6694382a0a7100`,
after [preparation PR #28](https://github.com/Mikoto-19909/greedy-failure-structures/pull/28)
and the [selection validation fix](https://github.com/Mikoto-19909/greedy-failure-structures/pull/29).
Reproduce it from that revision and a new output directory; keep
the prescribed seed batch even if the result is inconclusive or reversed.
Matplotlib is an optional offline plotting dependency:

```console
python -m pip install matplotlib
python run_project.py benchmark --config configs/core_overlap_pilot.json --dry-run
python run_project.py benchmark --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v2 --workers 1
python .github/scripts/validate_benchmark_output.py --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v2
python analysis/core_overlap_pilot.py --config configs/core_overlap_pilot.json --results results/core_overlap_pilot_v2 --output results/core_overlap_pilot_v2/analysis
```

The analysis also invokes the complete-output validator before its own input
checks. It writes `paired_instances.csv`, `report.md`, `failure_rate.svg`, and
`validation.md`. Its table, statistics, and Matplotlib figure need separate
review before publishing evidence; the benchmark validator does not cover them.
The full design and acceptance rules remain in the
[checkpoint plan](core_overlap_checkpoint_plan.zh-CN.md).

## Commands

### `quick`

Run the small starter workflow and write local artifacts to `results/quick`:

```console
python run_project.py quick
```

Omitting the command has the same effect. The bundled `quick.json` is a legacy
schema-v1 configuration, so its `LegacyConfigWarning` is expected.

### `demo`

Print one fixed adversarial construction and its locally computed solutions:

```console
python run_project.py demo
```

The output demonstrates behavior on that one source-defined instance. It is not
a result about an experiment corpus.

### `audit-stressors`

Audit whether the committed generator sweeps change their intended structural
target while exposing dimension and incidence confounders:

```console
python run_project.py audit-stressors
```

The default command audits `configs/p7_controlled_stressors.json`. It prints
JSON and does not run the benchmark algorithms. Repeat `--config PATH` to
select legacy or custom configurations, and add `--strict` when failed gross
isolation checks should produce a non-zero status. See
[`generator_isolation.md`](generator_isolation.md) for metric and control
semantics.

### `validate-config`

Validate JSON shape, expand sweeps, and preflight algorithms without running
them or creating an output directory:

```console
python run_project.py validate-config --config configs/p6_uniform_scale.json
```

### `benchmark`

Inspect the expanded plan without writing output:

```console
python run_project.py benchmark --config configs/p6_uniform_scale.json --dry-run
```

Execute it with independent algorithm runs distributed across workers:

```console
python run_project.py benchmark --config configs/p6_uniform_scale.json --output results/p6_uniform_scale --workers 2
```

Compatible rows already present in `raw_results.csv` are resumed by default.
The configuration hash and deterministic run identifiers must match the current
plan. `--force` removes runner-owned artifacts in that result directory and
reruns every planned identifier; unrelated files are left in place.

### `cartography`

This is a broad supplementary scan across structures, strengths, and algorithms.
Use the pilot plan above for the current single-point research checkpoint.

Run the six documented stressor families at multiple strength levels against
dimension-matched uniform controls:

```console
python run_project.py cartography --config configs/structural_gap_cartography.json --design designs/structural_gap_cartography.json --output results/structural_gap_cartography --workers 4
```

`seed_group` is an optional schema-3 case field. Cases in the same group use
the same generated-instance seed at each repetition; cases without it retain
the historical case-index seed schedule. The design validator requires each
declared stressor/control pair to share a non-empty group and equal universe,
candidate-count, and budget dimensions. The analysis checks the observed seeds
again before computing a paired difference.

Randomized algorithm seeds are nested within an instance seed. Their gaps are
averaged within an instance before the across-instance distribution and paired
intervals are computed, so algorithm-seed repetitions are not counted as
independent instances. Use `precision_diagnostics.csv` to decide whether the
configured repetition count meets the design's confidence-interval half-width
target. The cartography runner checkpoints each batch of 100 newly completed
runs and writes the complete canonical CSV at the end; after interruption it
resumes from the last completed batch. Ordinary benchmark calls retain the
default per-run checkpoint interval. With `--force`, stale cartography-owned
CSV, SVG, summary, and manifest files are removed before benchmark execution;
unrelated files in the output directory are preserved.

After a completed run, independently recompute the cartography statistics from
the canonical benchmark rows:

```console
python .github/scripts/validate_cartography_output.py --config configs/structural_gap_cartography.json --design designs/structural_gap_cartography.json --output results/structural_gap_cartography
```

Run the benchmark output validator first; the cartography validator treats its
validated `raw_results.csv` as the canonical input and separately checks the
cartography CSV values, layout, and manifest checksums.

### `resume`

Resume an interrupted compatible checkpoint explicitly:

```console
python run_project.py resume --config configs/p6_uniform_scale.json --output results/p6_uniform_scale --workers 2
```

This command skips completed run identifiers. Passing `--force` instead starts
the configured plan again under the same output directory.

### `summarize`

Validate a complete canonical checkpoint and rebuild its typed CSV, Markdown,
SVG, and manifest artifacts without running any algorithm:

```console
python run_project.py summarize --config configs/p6_uniform_scale.json --output results/p6_uniform_scale
```

The command rejects missing planned rows, unexpected identifiers, incompatible
instances, and malformed canonical CSV input.

### `replay`

Replay a serialized case using its recorded algorithm:

```console
python run_project.py replay --instance results/p6_uniform_scale/failures/<run-id>.json
```

Use `--algorithm NAME` to request a replacement algorithm. The replacement
receives the options recorded in the replay file, so the override is valid only
when that algorithm accepts the recorded option contract. For example, a
time-limited exact-solver artifact cannot be replayed with `greedy`, because
Greedy rejects exact-solver options; the command does not remap options for the
replacement. When the file contains a recorded result, a coverage or selection
mismatch produces a nonzero exit status. Replay artifacts are self-contained
and do not regenerate their instances from a generator.

### `dashboard`

Start the local browser frontend:

```console
python run_project.py dashboard
```

Use `--host` and `--port` to change the loopback address or port. Non-loopback
bindings are rejected. The dashboard reads `configs/`, writes under `results/`,
and calls the same validation, benchmark, report, and replay functions as the
CLI. It provides no accounts, remote queue, or hosted execution.
Its initial quick selection is an example workflow; choose other existing
configurations according to the purpose described above.

## Output validation

After a completed run, verify the artifacts independently of their own manifest
checksum:

```console
python .github/scripts/validate_benchmark_output.py --config configs/p6_uniform_scale.json --output results/p6_uniform_scale
```

See [`output_schema.md`](output_schema.md) for the artifact roles and status
semantics. A timeout carries an incumbent when one exists, but the timeout run
itself does not prove a reference optimum. An independently validated instance
certificate or another exact run for the same instance may still supply that
reference for normalized analysis.
