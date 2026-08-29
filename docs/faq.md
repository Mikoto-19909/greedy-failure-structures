# Frequently Asked Questions

## Why study Maximum Coverage?

Maximum Coverage is one of the simplest submodular optimisation problems where
greedy approximation is well-understood theoretically (the classical greedy
guarantee), but the *structural conditions* under which greedy actually performs
poorly are less well-characterised empirically. The problem is small enough to
solve exactly on moderate instances, yet rich enough to exhibit qualitatively
different failure modes under controlled structural variation.

## Why not just use the theoretical bound?

The classical greedy guarantee is a worst-case result over monotone submodular
functions. It describes a floor for greedy's value in the worst case, but says
nothing about which specific instance structures push greedy toward that floor
or keep it well above it. This project studies the empirical distribution of
greedy performance within the guarantee, not the guarantee itself.

## Why so many algorithms?

Each algorithm serves a different role in the research:

- **Greedy / Lazy Greedy** — the object of study. Lazy Greedy produces
  identical selections to standard greedy (under compatible tie-breaking) but
  reduces the number of marginal-gain evaluations through a heap-based admissible
  pruning strategy.
- **Randomised Greedy** — tests whether randomised tie-breaking can recover
  from deterministic bad early choices on specific structures.
- **Local Search / Multi-start Local Search** — tests whether neighbourhood
  search can close the OPT gap on instances where greedy's one-pass strategy
  fails.
- **Brute Force / Branch-and-Bound / CP-SAT** — exact oracles that provide
  ground-truth optimal values for comparison. They are not meant to be fast;
  they are meant to be correct.

## Why parameterised instance families instead of real-world data?

Controlled experiments require the ability to vary one structural factor while
holding others fixed. Real-world instances confound multiple factors
simultaneously, making it impossible to attribute an observed failure to any
specific structural property. The generator families expose structural
dimensions such as overlap, duplication, dominance, tail weight, clustering,
and adversarial construction, so that cause-and-effect relationships can be
established rather than merely correlated.

## Why is the content boundary enforced?

This repository publishes runnable code and no quantitative research claims.
The reason is methodological: a claim published without its full evidence chain
(frozen inputs, exact commit, environment metadata, analysis script) is not
reproducible and therefore not verifiable. Enforcing the boundary in CI ensures
that the repository remains a *tool* for producing evidence, not a substitute
for it.

## Why determinism matters

Two runs of the same configuration with the same seed must produce identical
results. This is not a convenience — it is the foundation of every equivalence
check, every hold-out validation, and every regression test in this project.
Non-determinism (from unseeded RNGs, floating-point reordering, or parallel
race conditions) would make it impossible to say whether a difference between
runs reflects a real algorithmic change or an artifact of execution order.
