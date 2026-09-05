# Core research analysis

The [fixed overlap pilot report](overlap_pilot_v1.md) is available with frozen
evidence and validation under [C1](../experiments/core_rq/CLAIMS.md#c1).

## Research question

Does the shared-core `high_overlap` generator produce more Greedy failures
than a `uniform` control matched on dimensions and expected set size? The
fixed pilot compared Greedy with an exhaustive reference at one fixed
parameter setting. It tests these generating mechanisms; other structural
differences can remain after matching.

## Current status

The [execution plan in PR #23](https://github.com/Mikoto-19909/greedy-failure-structures/pull/23)
records the design, prerequisites, and analysis procedure. The
[fixed configuration](../configs/core_overlap_pilot.json) and
[offline analysis](core_overlap_pilot.py) have been run on a clean fixed commit.
The pilot did not provide sufficient paired evidence of a failure-rate
difference in this setting; the report retains the observed direction and the
structural diagnostics. See [C1](../experiments/core_rq/CLAIMS.md#c1).
Use the [pilot commands](../docs/cli.md#core-overlap-pilot) to reproduce the work.
No result is inferred from the runnable quick/full examples
or the broader cartography workflow.

For installation and example commands, see the [project README](../README.md).
For method checks and supplementary studies, use the
[documentation index](../docs/README.md).

## Evidence

Validated findings link to the
[claim ledger](../experiments/core_rq/CLAIMS.md), which maps each public claim
to its result rows, configuration, figure, manifest, and validation record.
