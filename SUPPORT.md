# Support

This research project is published for inspecting and reproducing experiments.
Support is provided as maintainer time allows, without a guaranteed response
time or long-term maintenance commitment.

## Getting started on your own

Start with the [README](README.md) for installation and a short functional run.
The [CLI reference](docs/cli.md) covers the full commands, and the
[reproducibility matrix](docs/reproducibility_matrix.md) explains which outputs
should agree between runs.

Read the modules under `src/maxcover/` alongside their tests to inspect current
behavior. If documentation, code and tests disagree, check the intended rule
and algorithm definition, reproduce the behavior, and correct the mistaken
source. Passing tests alone do not decide which source is correct.

## Asking a question

Open a GitHub issue with the exact command, configuration, full error output,
Python version and the revision you ran.

Please do not use issues to report a suspected vulnerability — see
[SECURITY.md](SECURITY.md).

## Support scope

**Algorithm comparisons.** Published findings and their evidence are in the
[research analysis](analysis/README.md) and
[claim ledger](experiments/core_rq/CLAIMS.md). Evidence publication requirements
are maintained in [CONTRIBUTING.md](CONTRIBUTING.md).

**Production use.** The project studies synthetic instances. Production tuning,
hardening and suitability assessments are outside its scope.

**Larger contributions.** Discuss new algorithms, instance families or output
schemas before implementation, as described in [CONTRIBUTING.md](CONTRIBUTING.md).
