# Structural Stressors and Greedy Failure Mechanisms

This document separates structures that directly trap Greedy from structures
that primarily stress preprocessing or exact search. Each workflow produces
local evidence from a committed configuration; this file stores no experiment
result or quantitative research claim.

Before interpreting algorithm outcomes, run `python run_project.py
audit-stressors` and inspect the target monotonicity, dimension controls,
matched uniform controls, and non-target metric ranges. The audit contract is
documented in [`generator_isolation.md`](generator_isolation.md).

The controlled replacement workflow keeps the legacy configurations intact
and runs all six stressor scans from one configuration:

```console
python run_project.py benchmark --config configs/p7_controlled_stressors.json --output results/p7_controlled_stressors
```

The P4/P6 commands below remain reproducible mechanism and preprocessing
workflows, but their dimensions or incidence must not be assumed invariant.

## 1. Duplicate-heavy structure

**Role.** Exact copies increase candidate redundancy and make deduplication a
meaningful preprocessing question. Copies alone do not force standard Greedy to
waste a choice: after one copy is selected, another has zero marginal gain while
any productive alternative remains. This family is therefore primarily a
search- and preprocessing-stress case rather than a direct Greedy trap.

**Structural signature.** High `duplicate_set_ratio`; many candidate pairs with
identical membership.

```console
python run_project.py benchmark --config configs/p4_duplicate_heavy.json --output results/p4_duplicate_heavy
```

## 2. Dominated sets

**Role.** A dominated set is a strict subset of another available set. For the
same current coverage state, its marginal gain cannot exceed its dominator's,
so dominance alone does not create a standard Greedy failure. The family tests
whether dominance elimination reduces exact-search work without changing the
solution represented in original set indices.

**Structural signature.** High `dominated_set_ratio`; many strict subset/
superset candidate relationships.

```console
python run_project.py benchmark --config configs/p4_dominated_heavy.json --output results/p4_dominated_heavy
```

## 3. Adversarial Greedy traps

**Mechanism.** The construction places a bait set first whose initial marginal
gain is larger than either globally complementary block. Once Greedy selects the
bait, its remaining choice cannot recover the coverage obtained by selecting
the two complementary blocks. Version 2 carries a construction certificate for
its known optimum.

**Structural signature.** A high-gain bait set overlaps both complementary
blocks, with optional distractors constrained not to repair the lost coverage.

```console
python run_project.py benchmark --config configs/p6_trap_construction.json --output results/p6_trap_construction
```

For a transparent single-instance demonstration, run `python run_project.py
demo`. Its values are computed locally from the fixed source-defined instance.

## 4. Long-tail coverage concentration

**Mechanism to test.** A long-tailed element-weight construction changes how
coverage is concentrated across candidate sets. High concentration can create
large early gains followed by weak residual gains, but it does not guarantee a
Greedy failure. The paired scan measures whether changing the concentration
parameter changes exact-reference gaps while holding the common random stream
fixed.

**Structural signature.** Variation in `coverage_skew_gini` under paired
generator seeds and fixed nominal set size.

```console
python run_project.py benchmark --config configs/p4_long_tail.json --output results/p4_long_tail
```

## 5. High overlap

**Mechanism to test.** A shared core makes initial gains similar and leaves each
set's unique fringe to determine later marginal gains. Near ties increase the
importance of the repository's deterministic lower-index tie-breaking; the
selection is not random. The parameter grid tests whether measured overlap is
associated with an exact-reference gap.

**Structural signature.** High `pairwise_overlap_mean_jaccard`, interpreted
alongside actual density and exact-reference availability.

```console
python run_project.py benchmark --config configs/p6_overlap_scan.json --output results/p6_overlap_scan
```

## 6. Clustered structure

**Mechanism to test.** Sets concentrated within clusters can make early choices
overrepresent one region when the budget is small relative to the number of
clusters. This is a hypothesis evaluated by the scan, not a guarantee for every
generated instance.

**Structural signature.** The configured `clusters`, `within_probability`, and
`outside_probability` levels together with realized instance metrics.

```console
python run_project.py benchmark --config configs/p6_clustered_scan.json --output results/p6_clustered_scan
```

## Interpreting the workflows

Every P4/P6 command above and the P7 controlled command include at least one
registered exact algorithm.
Only an exact run that proves `optimal`, or an independently validated
instance certificate, supplies a reference optimum. A timeout or merely
feasible incumbent does not prove one by itself. Optimum-relative failure and
gap rows therefore report their exact-reference eligibility explicitly.

`configs/sweeps.json` is an exploratory structural sweep containing Greedy and
Local Search only. It does not include an exact reference, so its outputs alone
cannot establish an approximation ratio or an exact-reference Greedy failure
rate. It remains useful for configuration expansion, structural metrics, and
raw coverage inspection.

The benchmark runner writes typed CSV, Markdown, SVG, and manifest artifacts.
See [`output_schema.md`](output_schema.md) for their semantics and
[`cli.md`](cli.md) for validation and replay commands. Any future published
research conclusion still requires the frozen evidence chain described in
[`CONTRIBUTING.md`](../CONTRIBUTING.md).
