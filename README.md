# Maximum Coverage Study

**English** | [简体中文](README.zh-CN.md)

This repository studies how Maximum Coverage instance structure relates to
Greedy's optimality gap: the loss in coverage relative to an exact optimum.
It provides Python algorithms, instance generators, and tools to run and
inspect reproducible experiments.

## Current research

The next checkpoint asks whether the shared-core `high_overlap` generator
produces more Greedy failures than a `uniform` control matched on dimensions
and expected set size. The planned comparison uses Greedy and an exhaustive
reference at one fixed parameter setting. It does not isolate overlap from
every other structural difference between the generators.

**Status: implementation prepared; formal experiment pending.** The
[fixed configuration](configs/core_overlap_pilot.json) and
[offline analysis](analysis/core_overlap_pilot.py) implement the
[execution plan](docs/core_overlap_checkpoint_plan.zh-CN.md). Use the
[pilot commands](docs/cli.md#core-overlap-pilot) after committing the preparation;
the formal run must use a clean fixed source revision.

The [research analysis](analysis/README.md) records the current research status.
Published findings, when available, link to the
[claim ledger](experiments/core_rq/CLAIMS.md) for their evidence.

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

Choose the workflow by purpose:

| Purpose | Entry point |
| --- | --- |
| Current research | The [fixed overlap pilot](docs/cli.md#core-overlap-pilot); implementation is prepared and the formal experiment is pending. |
| Examples and compatibility checks | `demo`, `quick`, and the larger legacy `full.json` workflow below. |
| Historical exploration and appendices | The [supplementary workflow index](docs/README.md#historical-exploration-and-appendices), including broader structural scans and additional algorithm comparisons. |

### Examples and compatibility checks

Show Greedy's choices on one fixed adversarial instance:

```console
python run_project.py demo
```

The values are computed locally for that source-defined example. See
[Scope](#scope) for the distinction between example output and published findings.

Run the small starter benchmark to check the installation and output workflow:

```console
python run_project.py quick
```

Omitting the CLI command also runs `quick`; the PowerShell wrapper defaults to
the same action. The Dashboard initially prefers `quick.json` when there is no
retained configuration selection. These defaults select an example workflow.

Inspect the quick execution plan without running the algorithms:

```console
python run_project.py benchmark --config configs/quick.json --dry-run
```

Run the larger legacy workflow when checking compatibility or revisiting its
mixture of instance families:

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

The name `full` describes that existing workflow, not the complete current
research study. `configs/quick.json` and
`configs/full.json` are schema v1, and the loader migrates them to schema 3 in
memory. Their `LegacyConfigWarning` is expected. These files remain available
for legacy compatibility and reproduction of the existing workflows.

Verify the completed quick run:

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

The validator checks supported artifact relationships and recorded checksums.
A checksum match establishes agreement with the recorded digest; it does not
establish that the original calculation was correct. Generated outputs remain
local under `results/`.

The [Lazy Greedy functional workflow](configs/p3_lazy_greedy.json) is also used
by CI. Its procedure is in the
[functional test report](docs/lazy_greedy_test_report.md).

### Historical exploration and appendices

Existing configurations remain available for their documented purposes.
`configs/sweeps.json` is schema 2; the `configs/p3_*` through `configs/p7_*`
configurations are schema 3. These version labels do not indicate which
experiment to run next.

For broader structural scans, see the
[cartography command](docs/cli.md#cartography). The older
[overlap parameter scan](configs/p6_overlap_scan.json) and the
[full configuration collection](configs/) support further exploration.
Neither is a substitute for the fixed pilot described above.

Phase-prefixed configurations are not all historical: `p3_lazy_greedy.json`
supports CI checks, `p7_controlled_stressors.json` supports generator audits,
and the pairing configurations support paired-seed method checks. Use the
[documentation index](docs/README.md) to find those procedures and the
[CLI reference](docs/cli.md) for complete commands.

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
`maxcover.benchmark` and `maxcover.reporting` — roughly 35% of the source by
line — so `Success: no issues found in 24 source files` means the remaining
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

## Reviewing published research

Start with the external [research analysis](analysis/README.md). The
authoritative mapping from each claim ID to its result rows, configuration,
manifest, and validation record is the
[core claim ledger](experiments/core_rq/CLAIMS.md). Neither document currently
publishes a quantitative research claim.

## Scope

This is a code-first repository that may publish a small number of validated
core research claims. Full benchmark output remains local under `results/`.
Minimum frozen evidence for a public claim belongs in `experiments/core_rq/`,
and the external research narrative belongs in `analysis/`; see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the publication rule.

The distinction matters because the code computes numbers routinely. `demo`
prints a coverage gap, and a benchmark run writes measurement CSVs to
`results/`. Those local outputs do not become public findings. A tracked
quantitative statement becomes a public claim only through the claim ledger,
frozen evidence, and recorded independent validation. CI permits that prose but
does not prove that the human-maintained mapping is correct.

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
- [`experiments/core_rq/CLAIMS.md`](experiments/core_rq/CLAIMS.md): authoritative
  mapping from public claims to frozen evidence and validation records
- [`analysis/README.md`](analysis/README.md): external research analysis entry
- `tests/`: deterministic unit and contract tests
- `run_project.py`: primary command-line entry point
- `project.ps1`: Windows convenience wrapper
- `LICENSE_MANIFEST.json`: the closed license allow-list, verified by CI
- `PUBLIC_SNAPSHOT_MANIFEST.json`: the migration archive for the one export
  that created this repository
- [`docs/README.md`](docs/README.md): documentation index and scope guide
- [`docs/cli.md`](docs/cli.md): complete command-line workflow
- [`docs/output_schema.md`](docs/output_schema.md): generated artifact semantics
- [`docs/failure_mechanisms.md`](docs/failure_mechanisms.md) and
  [`docs/faq.md`](docs/faq.md): structural guidance and project rationale
- [`docs/faq.zh-CN.md`](docs/faq.zh-CN.md): Simplified Chinese FAQ
- `docs/history/`: migration provenance and pre-public development history
- [`docs/lazy_greedy_test_report.md`](docs/lazy_greedy_test_report.md):
  lazy-greedy functional verification process

## Contributing and support

- [`CONTRIBUTING.md`](CONTRIBUTING.md): scope, ground rules, and how to submit
- [`AGENTS.md`](AGENTS.md): additional constraints for AI coding agents
- [`SECURITY.md`](SECURITY.md): what counts as a security issue, and reporting
- [`SUPPORT.md`](SUPPORT.md): what this project does and does not answer

## License

Code is licensed under the MIT License. Documentation and other non-code
content in this snapshot are licensed under Creative Commons Attribution 4.0.
See [`LICENSES/README.md`](LICENSES/README.md) for the closed file-level mapping.
