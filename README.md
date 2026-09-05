# Maximum Coverage Study

**English** | [简体中文](README.zh-CN.md)

This project studies how Maximum Coverage instance structure relates to
Greedy's optimality gap: the coverage lost relative to an exact optimum.
It includes algorithms, instance generators and tools for reproducible experiments.

## Current research

The completed pilot compares shared-core `high_overlap` instances with a
`uniform` control matched on dimensions and expected set size, using Greedy
and an exhaustive reference. It did not provide sufficient paired evidence
of a failure-rate difference at the fixed setting. The report retains the
observed direction and the other structural differences between the generators.
See [C1](experiments/core_rq/CLAIMS.md#c1).

Read the [pilot report](analysis/overlap_pilot_v1.md), start from the
[research index](analysis/README.md), or inspect the authoritative
[claim-to-evidence mapping](experiments/core_rq/CLAIMS.md).

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

Open the printed local URL to validate configurations, start or resume runs,
inspect artifacts and replay instances. The interface supports English and Chinese
and uses the same experiment engine as the CLI. The server binds to loopback
addresses; see the [Dashboard command](docs/cli.md#dashboard) and
[security policy](SECURITY.md) for its operating boundary.

## Output and verification

Use the [output schema](docs/output_schema.md) to read CSVs, reports and manifests,
and the [reproducibility guide](docs/reproducibility_matrix.md) to distinguish
stable results from runtime and environment fields that may vary.
A checksum match establishes agreement with the recorded digest; it does not
prove the calculation is correct. The CLI guide describes the validator's scope.

Run the tests with:

```console
python -m unittest discover -s tests -v
```

[CONTRIBUTING.md](CONTRIBUTING.md#verification) maintains the complete verification
commands and actual mypy coverage, including the configured exemptions.
Windows users can also use `./project.ps1 test`, `./project.ps1 typecheck` and
`./project.ps1 quick`.

## Scope

`demo` prints locally computed coverage and a benchmark writes measurements under
`results/`. Full exploratory output stays local. Public claims are published with
minimum frozen evidence in `experiments/core_rq/` and an explanation in `analysis/`;
the claim ledger is the single evidence mapping. CI checks its declared scope,
while contributors and reviewers verify that the claims match their evidence.
The publication rules are maintained in CONTRIBUTING.

## Documentation and support

- [Documentation index](docs/README.md), [English FAQ](docs/faq.md) and [Chinese FAQ](docs/faq.zh-CN.md).
- [Structural mechanisms](docs/failure_mechanisms.md) and the [Lazy Greedy functional report](docs/lazy_greedy_test_report.md).
- [Contributing](CONTRIBUTING.md), [additional agent guidance](AGENTS.md), [support](SUPPORT.md) and [security reporting](SECURITY.md).

Code uses the MIT License; documentation and other non-code content use CC BY 4.0.
See the [file-level license mapping](LICENSES/README.md), including third-party exceptions.
