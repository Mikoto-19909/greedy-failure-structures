# Maximum Coverage Study and Research Dashboard

**English** | [简体中文](README.zh-CN.md)

This project studies how Maximum Coverage instance structure relates to
Greedy's optimality gap: the coverage lost relative to an exact optimum.
It includes algorithms, instance generators and tools for reproducible experiments.
The local Dashboard also hosts independent research cases. Online matching with
bounded recourse is the first such case, with its own metrics and verification.

Try the [interactive counterexample toy](examples/greedy-playground/index.html)
(Chinese UI): choose sets, challenge Greedy, replay its decisions, and edit a small
instance. Open the downloaded HTML in a browser; no installation is needed.

## Current research

The completed pilot compares shared-core `high_overlap` instances with a
`uniform` control matched on dimensions and expected set size, using Greedy
and an exhaustive reference. It did not provide sufficient paired evidence
of a failure-rate difference at the fixed setting. The report retains the
observed direction and the other structural differences between the generators.
See [pilot data](experiments/core_rq/overlap_pilot_v1/).

Read the [pilot report](analysis/overlap_pilot_v1.md), start from the
[research index](analysis/README.md), or inspect the
[pilot data](experiments/core_rq/overlap_pilot_v1/).

The [R1 follow-up](analysis/r1_prefix_exchange_report.md) reanalyzes these same
instances to locate Greedy's first loss of optimal reachability and measure
recovery by one- and two-set exchanges. It is exploratory and adds no new samples.

## Quick start

The base package requires Python 3.11 or newer and no third-party runtime dependency.
From the repository root:

```console
python -m pip install -e .
python run_project.py quick
```

`quick` checks the installation and example output workflow. Its
`LegacyConfigWarning` is expected because the retained configuration uses an
older schema. The [CLI guide](docs/cli.md) explains configuration compatibility,
all commands, optional OR-Tools installation and output validation.

Omitting the CLI command and using the PowerShell wrapper without arguments both
run quick. The Dashboard also initially prefers `quick.json` when no selection
has been retained. These defaults select an example workflow.

## Choose a workflow

| Purpose | Entry point |
| --- | --- |
| Current research | [Fixed pilot commands](docs/cli.md#core-overlap-pilot), [report](analysis/overlap_pilot_v1.md) and [original design](docs/core_overlap_checkpoint_plan.zh-CN.md). |
| Examples and compatibility | `python run_project.py demo`, `quick`, and the larger legacy `full.json` workflow in the CLI guide. The name `full` does not designate the complete current research study. |
| Method checks and broader exploration | The [documentation index](docs/README.md) distinguishes pairing checks, generator audits, functional checks and wider structural scans. |

The pilot's offline figure uses Matplotlib. Other optional algorithms and
configurations remain available for their documented purposes; a phase prefix
alone does not make a configuration historical.

## Local dashboard

```console
python run_project.py dashboard
```

Open the printed local URL to choose a study. **Maximum Coverage** opens the
existing experiment tools at `/maximum-coverage`; **Online Matching with Recourse**
opens imported reports, assignment replay and fixed-input reproduction at `/online-matching`.
The shared study switcher returns to the home page or opens another study.
Opening a page starts no computation. `/index.html` remains an alias for Maximum Coverage.
The home page and Maximum Coverage interface support English and Chinese.
Maximum Coverage uses the same experiment engine as the CLI. The server binds to loopback
addresses; see the [Dashboard command](docs/cli.md#dashboard) and
[security policy](SECURITY.md) for its operating boundary.

New study cards and the switcher share one [topic list](src/maxcover/dashboard_ui/topics.json).
See [adding an entry](docs/cli.md#adding-a-research-entry) for the small presentation contract.

## Output and verification

Use the [output schema](docs/output_schema.md) to read CSVs and reports,
and the [reproducibility guide](docs/reproducibility_matrix.md) to distinguish
stable results from runtime and environment fields that may vary.
The optional validator recomputes results from the configuration and CSVs.

Run the tests with:

```console
python scripts/check.py --profile full --tests-only
```

[CONTRIBUTING.md](CONTRIBUTING.md#verification) maintains the complete verification
commands, direct unittest prerequisites, and actual mypy coverage.
Windows users can also use `./project.ps1 test`, `./project.ps1 typecheck` and
`./project.ps1 quick`.

## Scope

`demo` prints locally computed coverage and a benchmark writes measurements under
`results/`. Full exploratory output stays local. Research reports in `analysis/` link directly to configurations and data in
`experiments/core_rq/`. Keep enough information to rerun and understand a result;
no claim ledger or file-integrity manifest is required.
The publication rules are maintained in CONTRIBUTING.

## Documentation and support

The [independent research directory](independent_research/README.md) includes
the imported online-matching study. Open **Online Matching with Recourse** from the Dashboard
to read its reports, replay assignments and reproduce its fixed comparisons.

- [Documentation index](docs/README.md), [English FAQ](docs/faq.md) and [Chinese FAQ](docs/faq.zh-CN.md).
- [Structural mechanisms](docs/failure_mechanisms.md) and the [Lazy Greedy functional report](docs/lazy_greedy_test_report.md).
- [Contributing](CONTRIBUTING.md), [additional agent guidance](AGENTS.md), [support](SUPPORT.md) and [security reporting](SECURITY.md).

Code uses the MIT License; documentation and other non-code content use CC BY 4.0.
See the [file-level license mapping](LICENSES/README.md), including third-party exceptions.
