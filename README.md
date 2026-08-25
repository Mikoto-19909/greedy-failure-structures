# Maximum Coverage Study

This repository contains research-oriented Python code for deterministic
experiments with the Maximum Coverage problem.  It provides algorithm
implementations, instance generators, configuration validation, benchmark
execution, reporting, and replay utilities.

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

Run the starter workflow:

```console
python run_project.py quick
```

Validate a configuration without executing a benchmark:

```console
python run_project.py benchmark --config configs/sweeps.json --dry-run
```

Run a configured benchmark and write local outputs:

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

Generated files under `results/` are local artifacts and are not part of the
repository snapshot.

## Test

```console
python -m unittest discover -s tests -v
```

Optionally, check the typed baseline:

```console
python -m pip install -e ".[typecheck]"
python -m mypy
```

On Windows, the convenience wrapper provides equivalent commands:

```powershell
./project.ps1 test
./project.ps1 typecheck
./project.ps1 quick
```

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

## Project layout

- `src/maxcover/`: algorithms, generators, benchmark execution, and reporting
- `configs/`: reproducible experiment configurations
- `tests/`: deterministic unit and contract tests
- `run_project.py`: primary command-line entry point
- `project.ps1`: Windows convenience wrapper
- `PUBLIC_SNAPSHOT_MANIFEST.json`: the closed allow-list defining this snapshot
- `docs/history/`: migration provenance and pre-public development history

## Contributing and support

- [`CONTRIBUTING.md`](CONTRIBUTING.md): scope, ground rules, and how to submit
- [`SECURITY.md`](SECURITY.md): what counts as a security issue, and reporting
- [`SUPPORT.md`](SUPPORT.md): what this project does and does not answer

## License

Code is licensed under the MIT License.  Documentation and other non-code
content in this snapshot are licensed under Creative Commons Attribution 4.0.
See [`LICENSES/README.md`](LICENSES/README.md) for the closed file-level mapping.
