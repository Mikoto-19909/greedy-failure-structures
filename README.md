# Maximum Coverage Study

**English** | [简体中文](README.zh-CN.md)

This repository contains research-oriented Python code for deterministic
experiments with the Maximum Coverage problem.  It provides algorithm
implementations, instance generators, configuration validation, benchmark
execution, reporting, and replay utilities.

## Research highlights

**Algorithm library.** Nine algorithms spanning greedy approximation, randomised
heuristics, local search, and exact methods (brute-force, branch-and-bound,
CP-SAT). Each is a standalone function with a common interface, making paired
comparisons and drop-in substitution straightforward.

**Controlled experiment framework.** Nine parameterised instance families
(uniform random, high-overlap, clustered, fixed-size, long-tail,
duplicate-heavy, dominated-heavy, mixed-cluster, adversarial) generate instances with
explicit structural control. The benchmark pipeline enforces deterministic
seeds, independent output validation, and configuration hashing so that every
run is replayable from its recorded inputs.

**Engineering governance.** A CI suite covering algorithm contracts, generator
invariants, configuration compatibility, content-boundary enforcement, and
license verification. The content-boundary check ensures that the repository
publishes runnable code and no quantitative claims — results are produced
locally by the consumer, not asserted by the source.

## Requirements

- Python 3.11 or newer
- No third-party dependency for the base package
- OR-Tools only when the optional exact solver is needed

## Install

```console
python -m pip install -e .
```

Install the optional exact solver with:

```console
python -m pip install -e ".[oracle]"
```

## Run

Show a small deterministic example:

```console
python run_project.py demo
```

This builds one fixed instance defined in the source and prints what each
algorithm returns on it, coverage gap included. Those numbers are computed on
your machine from that hard-coded instance. They demonstrate that greedy can be
trapped; they are not a measurement of any corpus, and nothing in this
repository reports them as a result. See [Scope](#scope).

Run the starter workflow:

```console
python run_project.py quick
```

Validate a configuration without executing a benchmark:

```console
python run_project.py benchmark --config configs/sweeps.json --dry-run
```

The deterministic lazy-greedy variant has a paired functional workflow in
[`configs/p3_lazy_greedy.json`](configs/p3_lazy_greedy.json). Its complete
verification procedure is documented in
[`docs/lazy_greedy_test_report.md`](docs/lazy_greedy_test_report.md); that
report records compatibility checks only and is not a performance claim.

Run a configured benchmark and write local outputs:

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

Both commands above emit a `LegacyConfigWarning`: `configs/quick.json` and
`configs/full.json` are schema v1, and the loader migrates them to schema 3 in
memory on every run. The warning is expected. Those two files stay at v1
deliberately — `config_hash` is computed over the normalized configuration, so
rewriting them would change the hash and orphan the run identities already
recorded against it, which `CONTRIBUTING.md` classes as a breaking change.
`configs/sweeps.json` is schema 2; the `configs/p3_*` through `configs/p5_*`
configurations are schema 3 and warn about nothing.

Generated files under `results/` are local artifacts and are not part of the
repository snapshot.

Verify a completed run without relying on its own checksum:

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

`manifest.json` carries a checksum, and verifying it proves the files were not
altered after they were written. It cannot prove they were written correctly — a
run that computed a statistic wrongly produces output whose checksum matches
perfectly. This reads the artifacts back and recomputes what they claim from the
configuration alone, exiting non-zero on any disagreement. CI runs it after every
starter workflow.

## Test

```console
python -m unittest discover -s tests -v
```

Optionally, run the type checker:

```console
python -m pip install -e ".[typecheck]"
python -m mypy
```

Read its output narrowly. `pyproject.toml` sets `ignore_errors = true` for
`maxcover.benchmark` and `maxcover.reporting` — roughly 40% of the source by
line — so `Success: no issues found in 20 source files` means the remaining
modules are clean, not that the package is. Those two modules carry a real
backlog of unresolved type errors; the exemption keeps the check enforceable
everywhere else instead of leaving it permanently red. Reducing that backlog is
a welcome contribution, and the exemption list is the place to check what is not
yet covered.

On Windows, the convenience wrapper provides equivalent commands:

```powershell
./project.ps1 test
./project.ps1 typecheck
./project.ps1 quick
```

To use the local experiment dashboard:

```console
python run_project.py dashboard
```

Then open the printed local URL in a browser. The dashboard can validate a
configuration, start or resume a benchmark under `results/`, inspect generated
CSV/report artifacts, and replay serialized failure instances. It is a local
frontend over the same engine used by the CLI; it does not provide accounts,
remote execution, or a hosted service. Use another loopback address with
`--host`, and `--port` on the `dashboard` command when the default binding
needs to change; non-loopback bindings are rejected because state-changing
requests are intentionally local-only.
The browser UI includes a Chinese/English language toggle for the full control
surface and its dynamic run, result, and replay states.

## Reproducibility notes

- Use committed configuration files and explicit seeds.
- Keep fresh and resumed executions separate when diagnosing a run.
- Treat timeouts as incomplete work, not as proof of optimality.
- Runtime observations can vary with the machine and optional solver.
- The starter workflow is a functional check, not a performance claim.

## Scope

This is a code-first snapshot. It publishes runnable code, its tests and its
configurations, and it publishes **no quantitative research claims**: no
experiment results, no performance comparisons, no measurements. That is a
deliberate boundary, not an omission — see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the rule and
[`docs/history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md`](docs/history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md)
for what preceded this repository.

The boundary is about what this repository *publishes*, and the distinction is
worth stating because the code does compute numbers. `demo` prints a coverage
gap, and a benchmark run writes CSVs full of measurements to `results/`. Neither
crosses the boundary: both are produced on your machine when you run them, from
inputs committed here, and neither is checked in or asserted as a finding. What
the boundary excludes is a claim carried *by this repository* — a figure in the
README, a results table in the documentation, a stored corpus of outcomes.
Anything of that kind requires the frozen evidence chain
[`CONTRIBUTING.md`](CONTRIBUTING.md) describes, and CI enforces the rule over
every tracked file rather than trusting the convention.

## Dashboard

The repository includes an interactive experiment dashboard as a second
frontend to the existing experiment engine. A local user can configure and
validate experiments, start or resume benchmark runs, inspect locally generated
outputs, compare algorithm behaviour, and replay serialized failure cases
without reimplementing the underlying research logic.

The command-line interface remains fully supported. The dashboard is not a
hosted multi-user platform: it is a local frontend over the same configuration,
benchmark, reporting, validation, and replay functions used by the CLI.
Database-backed accounts, remote job queues, and hosted execution are outside
its scope.

## Project layout

- `src/maxcover/`: algorithms, generators, benchmark execution, and reporting
- `src/maxcover/dashboard.py` and `src/maxcover/dashboard_ui/`: local dashboard
  service and browser frontend
- `configs/`: reproducible experiment configurations
- `tests/`: deterministic unit and contract tests
- `run_project.py`: primary command-line entry point
- `project.ps1`: Windows convenience wrapper
- `LICENSE_MANIFEST.json`: the closed license allow-list, verified by CI
- `PUBLIC_SNAPSHOT_MANIFEST.json`: the migration archive for the one export
  that created this repository
- `docs/history/`: migration provenance and pre-public development history
- `docs/lazy_greedy_test_report.md`: lazy-greedy functional verification process

## Contributing and support

- [`CONTRIBUTING.md`](CONTRIBUTING.md): scope, ground rules, and how to submit
- [`AGENTS.md`](AGENTS.md): additional constraints for AI coding agents
- [`SECURITY.md`](SECURITY.md): what counts as a security issue, and reporting
- [`SUPPORT.md`](SUPPORT.md): what this project does and does not answer

## License

Code is licensed under the MIT License.  Documentation and other non-code
content in this snapshot are licensed under Creative Commons Attribution 4.0.
See [`LICENSES/README.md`](LICENSES/README.md) for the closed file-level mapping.
