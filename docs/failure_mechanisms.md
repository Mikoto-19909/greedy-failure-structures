# Greedy Failure Mechanisms

This document describes the structural conditions under which greedy algorithms
for Maximum Coverage tend to perform poorly. Each mechanism is illustrated by a
generator family included in this repository; concrete numbers are produced
locally by the commands shown, not stored in this file.

## 1. Duplicate-heavy structure

**Mechanism.** When many candidate sets are near-copies of each other, greedy's
first-mover advantage is amplified: it selects one copy early and then wastes
subsequent picks on sets that add almost nothing. The OPT, by contrast, can
choose a diverse set of non-overlapping copies that collectively cover more
elements.

**Structural signature.** High `duplicate_set_ratio`; many pairs of sets with
Jaccard similarity near 1.

```console
python run_project.py benchmark \
  --config configs/p4_duplicate_heavy.json \
  --output results/p4_duplicate_heavy
```

## 2. Dominated sets

**Mechanism.** A dominated set is one whose elements are a strict subset of
another set's elements. Greedy is attracted to dominated sets when they appear
early in the ordering (or have a temporarily high marginal gain due to prior
selections), wasting a budget slot on a set that contributes nothing the
dominator wouldn't already cover.

**Structural signature.** High `dominated_set_ratio`; large gap between the
dominator's coverage and the dominated set's coverage.

```console
python run_project.py benchmark \
  --config configs/p4_dominated_heavy.json \
  --output results/p4_dominated_heavy
```

## 3. Adversarial greedy traps

**Mechanism.** The generator constructs instances where a small "bait" set
offers a high initial marginal gain, drawing greedy into a local optimum.
Subsequent picks cannot recover the coverage lost by not choosing the
globally optimal first set. This is the purest form of greedy failure: a
single early decision that cannot be undone.

**Structural signature.** Small block of high-gain sets with overlapping
coverage, surrounded by many low-gain "distractor" sets.

```console
python run_project.py demo
```

The default demo uses the `adversarial_greedy_trap` generator with
`block_size=12, distractor_count=4, seed=7`.

## 4. Long-tail set sizes

**Mechanism.** When most sets are small and a few are very large, greedy tends
to pick the large sets early (high absolute gain) and then struggles to cover
the remaining elements with the many small sets that individually add little.
The OPT may instead pick a carefully chosen combination of small sets that
collectively outperform the single large set.

**Structural signature.** High variance in `set_size`; low
`mean_set_size` relative to `universe_size`.

```console
python run_project.py benchmark \
  --config configs/p4_long_tail.json \
  --output results/p4_long_tail
```

## 5. High overlap

**Mechanism.** When all candidate sets share a large common core, greedy's
marginal-gain calculation is dominated by the identical core coverage, making
it nearly indifferent between sets. The resulting selections are effectively
random among the overlapping sets, and the per-set unique coverage — which is
what actually matters — is not prioritised.

**Structural signature.** High `pairwise_overlap_mean_jaccard`; low
`coverage_skew_gini` (coverage is evenly distributed, not concentrated).

```console
python run_project.py benchmark \
  --config configs/sweeps.json \
  --output results/sweeps
```

## 6. Clustered structure

**Mechanism.** When the universe is partitioned into clusters and sets are
concentrated within clusters, greedy may exhaust one cluster's coverage before
moving to the next. If the budget `k` is small relative to the number of
clusters, greedy misses entire clusters while the OPT spreads picks across
them.

**Structural signature.** Low `actual_density` relative to cluster count; high
coverage concentration within a few clusters.

```console
python run_project.py benchmark \
  --config configs/sweeps.json \
  --output results/sweeps
```

## Using these mechanisms

The generator families in `src/maxcover/generators.py` expose one or more of
these mechanisms. The controlled experiment framework (see
`configs/`) lets you sweep structural parameters while holding other factors
fixed, producing the evidence needed to establish which mechanisms are
responsible for observed greedy failures.

To reproduce the structural analysis:

```console
python run_project.py benchmark --config configs/sweeps.json --output results/sweeps
```

The output CSVs in `results/sweeps/` contain per-instance structural metrics
and per-algorithm coverage values. The analysis scripts (not included in this
repository — see the content boundary in `CONTRIBUTING.md`) read those CSVs to
compute failure rates, approximation ratios, and structural correlations.
