# Frequently Asked Questions

<!-- faq:id=problem-definition -->

## What is Maximum Coverage?

Given a finite universe of elements, a collection of candidate sets, and a
selection budget `k`, Maximum Coverage asks for at most `k` sets whose union
covers as many elements as possible. In this repository, `universe_size`,
`set_count`, and `k` describe the instance, while coverage is the number of
distinct elements in the selected union.

<!-- faq:id=why-study -->

## Why study Maximum Coverage?

Maximum Coverage is a monotone submodular optimisation problem with a familiar
greedy baseline. The project asks how controlled structural changes relate to
the gaps observed between Greedy and an exact reference on the same instance.
The question is about instance structure and algorithm behaviour, not about
replacing the classical theoretical guarantee.

<!-- faq:id=theoretical-bound -->

## Why not just use the theoretical bound?

The classical Greedy guarantee describes a worst-case relationship between the
Greedy value and the optimum for a broad class of objectives. It does not
identify which instance structures are associated with larger or smaller gaps
in a particular experiment. A theoretical guarantee and an empirical
structural analysis answer different questions.

<!-- faq:id=algorithm-roles -->

## Why so many algorithms?

Each algorithm has a distinct role:

- **Greedy** is the primary baseline and object of study.
- **Lazy Greedy** is a deterministic implementation that is intended to reduce
  marginal-gain evaluations while preserving the Greedy selection sequence
  under the repository's tie-breaking rule. This is not a general runtime
  claim.
- **Randomised Greedy** and **Multi-start Local Search** provide explicitly
  seeded stochastic alternatives for testing whether different early choices
  or additional starts change the result.
- **Local Search** tests whether neighbourhood improvements can recover from a
  poor one-pass choice.
- **Brute Force**, **Branch-and-Bound**, and **CP-SAT** are exact methods used
  as reference candidates. A run supplies a ground-truth reference only when
  it finishes with an `optimal` status; a timeout may have an incumbent but
  does not prove optimality. CP-SAT additionally requires the optional
  OR-Tools dependency.

<!-- faq:id=reference-status -->

## What counts as a valid exact reference?

Only an exact run that closes its bound and returns `optimal` can provide the
reference optimum used by optimum-relative metrics. A `feasible` result is a
completed incumbent without a proof of optimality. A `timeout` means the
configured limit was reached, and an `error` means that no valid result was
produced. See [`output_schema.md`](output_schema.md) for the artifact-level
status rules.

<!-- faq:id=instance-families -->

## Which instance families are included?

The generator registry includes `uniform`, `high_overlap`, `clustered`,
`fixed_size`, `long_tail`, `duplicate_heavy`, `dominated_heavy`,
`mixed_cluster`, and `adversarial`. They exercise different structural
stressors. Duplicate-heavy and dominated-heavy cases also test preprocessing
and exact-search behaviour; no family guarantees a Greedy failure on every
generated instance. See [`failure_mechanisms.md`](failure_mechanisms.md) for
the runnable family workflows.

<!-- faq:id=synthetic-families -->

## Why parameterised instance families instead of real-world data?

Real-world data can vary along many dimensions at once, which makes it
difficult to isolate the contribution of any one structural property.
Controlled synthetic families vary selected parameters and, where configured,
hold a common random stream fixed. This helps test candidate mechanisms and
estimate descriptive associations; it does not by itself establish causality
or real-world generalisation.

<!-- faq:id=no-results -->

## Why are there no frozen experiment results in the repository?

This repository is a code-first reproducible experiment engine. It publishes
the algorithms, generators, configurations, validators, and reporting logic,
while benchmark outputs are generated locally under `results/`. A published
quantitative statement requires a separate frozen evidence chain containing the
inputs, exact commit, environment metadata, analysis procedure, and
independent validation. The current snapshot deliberately does not carry that
research result package.

<!-- faq:id=content-boundary -->

## Why is the content boundary enforced?

The repository publishes runnable code and no quantitative research claims.
The boundary prevents a number in prose, a results table, or a stored output
corpus from being separated from the evidence needed to verify it. The
enforced rule keeps this repository a tool for producing evidence rather than a
substitute for a frozen, independently validated study.

<!-- faq:id=determinism -->

## What does determinism mean here?

With the same normalized configuration, algorithm version, and explicit seed,
completed runs reproduce the instance identities, selected set indices,
coverage values, and canonical row ordering. Wall-clock runtime, timestamps,
and environment metadata may vary by machine. A run stopped by its wall-clock
limit reports the incumbent it had reached when the limit fired; because
progress is checked against the wall clock, that incumbent and its coverage can
differ across machines and are exempt from this guarantee. Randomised
algorithms therefore require an explicit algorithm seed, while deterministic
algorithms reject one.

<!-- faq:id=reproduction -->

## How do I reproduce a workflow?

Start with [`cli.md`](cli.md) for configuration validation, benchmark
execution, resume, summarization, replay, and independent output validation.
Use [`output_schema.md`](output_schema.md) to interpret the generated CSV,
report, replay, and manifest artifacts. The README and
[`CONTRIBUTING.md`](../CONTRIBUTING.md) define the current publication scope.
