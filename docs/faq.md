# Frequently Asked Questions

The core experiment compares Greedy with an exhaustive reference on
`high_overlap` and matched `uniform` instances. The completed
[pilot analysis](../analysis/overlap_pilot_v1.md) is the starting point for its
results and interpretation.

<!-- faq:id=problem-definition -->

## What is Maximum Coverage?

Given a finite universe, candidate sets, and a budget `k`, choose at most `k`
sets whose union covers as many elements as possible. Here, `universe_size`,
`set_count`, and `k` describe an instance; coverage counts the distinct elements
in the selected union.

<!-- faq:id=why-study -->

## What does this project study?

Maximum Coverage has a familiar Greedy baseline. The project examines how
instance structure relates to the gap between Greedy and the optimum on the
same instance. The current [fixed configuration](../configs/core_overlap_pilot.json)
compares a shared-core generating mechanism with a uniform control matched in
dimensions and theoretical expected set size.

<!-- faq:id=theoretical-bound -->

## Why not just use the theoretical bound?

The classical Greedy guarantee describes a worst-case relationship between
Greedy's value and the optimum. It does not identify which structures produce
larger gaps in a particular experiment. Empirical comparisons describe the
sampled instances and generating mechanisms; they do not replace that guarantee.

<!-- faq:id=algorithm-roles -->

## Which algorithms matter for the current experiment?

**Greedy** is the object of study. It selects the largest marginal gain and
breaks ties by the lower set index. **Brute Force** supplies the exhaustive
reference for the pilot's small instances, with no time limit configured.
Comparing their integer coverage values identifies a Greedy failure; the
relative gap measures its size.

Other workflows use **Lazy Greedy** to reduce marginal-gain evaluations while
preserving the selection rule, **Local Search** to test neighbourhood recovery,
and explicitly seeded **Randomised Greedy** or **Multi-start Local Search** to
explore alternative choices. **Branch-and-Bound** and optional **CP-SAT** provide
other exact-reference candidates. CP-SAT requires OR-Tools; it is not needed for
the core pilot. Lazy evaluation alone is not a general runtime guarantee.

<!-- faq:id=reference-status -->

## What counts as a valid exact reference?

The pilot requires a completed exhaustive run with `status=optimal` and a
selected-set coverage value consistent with the instance. Other workflows may
also use an independently validated construction certificate.

`feasible` records an incumbent without an optimality proof. It does not by
itself say that execution completed: inspect `algorithm_metadata.termination`
for the stopping reason. `timeout` records a reached time limit; `error`
records no valid algorithm result. Neither supplies a reference optimum.
The field contracts are in [`output_schema.md`](output_schema.md).

<!-- faq:id=instance-families -->

## Which instance families are included?

The core comparison uses `high_overlap` and `uniform`. Supplementary workflows
vary clusters, set size, coverage concentration, duplicates, dominance, and
adversarial traps. The `controlled_*` families provide separate structural
scans with explicit dimension and incidence controls.

An intended stressor does not establish a Greedy failure: inspect the actual
instance and its reference. Known adversarial constructions have their own
parameter conditions. See [`failure_mechanisms.md`](failure_mechanisms.md) for
mechanisms and commands, and [`generator_isolation.md`](generator_isolation.md)
for what each controlled scan holds fixed.

<!-- faq:id=synthetic-families -->

## Why parameterised families instead of real-world data?

Parameterised families make selected changes explicit. They help test candidate
mechanisms and estimate descriptive associations; this does not by itself establish
causality or real-world generalisation. Matching expected set size still leaves
other structural properties free to move.

Where configured, cases share an effective seed. Equal seed values do not
guarantee draw-by-draw alignment across generators or a reduction in variance;
the consumption rules are described in [`paired_seed_audit.md`](paired_seed_audit.md).

<!-- faq:id=no-results -->

## Where are the completed results?

The high-overlap pilot did not provide sufficient paired evidence of a
difference in Greedy failure rates. This does not establish equivalence or an
effect of overlap alone. [C1](../experiments/core_rq/CLAIMS.md#c1) connects that
statement to the frozen evidence; the
[pilot analysis](../analysis/overlap_pilot_v1.md) explains the comparison and
its limits. The [research index](../analysis/README.md) lists published work.

<!-- faq:id=content-boundary -->

## How are published claims checked?

Each claim links to its evidence through the claim ledger. The publication and
review requirements are maintained in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

<!-- faq:id=determinism -->

## What does determinism mean here?

With the same normalized configuration, generator and algorithm versions, and
explicit seeds, completed runs reproduce the instance identities, selected set
indices, coverage values, and canonical row ordering. Wall-clock runtime,
timestamps, and environment metadata may vary by machine. A run stopped by its
wall-clock limit reports the incumbent it had reached when the limit fired;
that incumbent and its coverage can differ across machines and are exempt from
this guarantee. Randomised algorithms require an explicit algorithm seed;
deterministic algorithms reject one.

<!-- faq:id=reproduction -->

## How do I reproduce a workflow?

Use the [core-pilot commands](cli.md#core-overlap-pilot) to regenerate complete
output and run the validator and offline analysis. The general
[`CLI reference`](cli.md) covers configuration checks, benchmark execution,
resume, summarize, and replay; [`output_schema.md`](output_schema.md) explains
the resulting artifacts and validation scope.
