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

The command prints JSON and does not run the benchmark algorithms. Repeat
`--config PATH` to select configurations, and add `--strict` when failed gross
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
