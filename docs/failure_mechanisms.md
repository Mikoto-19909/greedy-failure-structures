# Structural Stressors and Greedy Failure Mechanisms

Start with the fixed `high_overlap` versus `uniform` pilot, then use the
supplementary workflows below for specific construction and search questions.
The [completed pilot](../analysis/overlap_pilot_v1.md) did not provide sufficient
paired evidence of a difference in Greedy failure rates.
[C1](../experiments/core_rq/CLAIMS.md#c1)

## High overlap and a matched uniform control

The pilot tests whether a shared-core generating mechanism makes Greedy more
likely to miss the optimum than a uniform control. Its
[fixed configuration](../configs/core_overlap_pilot.json) matches dimensions
and theoretical expected set size, pairs cases by the configured seed batch,
and compares Greedy with a completed exhaustive reference.

```console
python run_project.py benchmark --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_reproduction --workers 1
```

Use a new output directory. The [pilot commands](cli.md#core-overlap-pilot)
include validation and offline analysis; the
[research plan](core_overlap_checkpoint_plan.zh-CN.md) defines the comparison
and stopping conditions.

**Mechanism to test.** A common core makes candidates cover many of the same
elements. Their fringes and later marginal gains determine which
combinations Greedy reaches. Equal gains follow the lower-index tie-breaking
rule. Shared seeds do not automatically align every random draw across
generators; see [`paired_seed_audit.md`](paired_seed_audit.md).

**What to inspect.** Read `pairwise_overlap_mean_jaccard` alongside
`actual_density`, `mean_set_size`, `covered_element_count`, and
`coverage_skew_gini`. Matching expected set size does not hold all those
properties fixed, so the comparison cannot attribute a difference to overlap
alone. The observed result does not establish equivalence, an overlap-strength
trend, or a result at other scales. [C1](../experiments/core_rq/CLAIMS.md#c1)

The existing parameter scan remains available for a broader descriptive
overlap question; its results are separate from the fixed pilot:

```console
python run_project.py benchmark --config configs/p6_overlap_scan.json --output results/p6_overlap_scan
```

`controlled_high_overlap` serves a different construction check. Its shared
core and disjoint, equally sized fringes make every selection of the same size
cover equally many elements. It is therefore not the pilot's treatment
generator. Details of the controls are in
[`generator_isolation.md`](generator_isolation.md).

## Adversarial Greedy traps

The certified version-2 construction places a bait set ahead of complementary
blocks. When `trap_count < block_size`, the bait initially offers more coverage
than either block but leaves elements uncovered in both. After selecting it,
Greedy cannot match the complementary blocks within the remaining budget;
constrained distractors cannot repair the loss.

At the allowed endpoint `trap_count=block_size`, the bait already covers the
universe, so this family name does not imply a failure at every parameter
setting. Version 2 supplies a known-optimum certificate in both cases. The
workflow below also retains the legacy construction for comparison.

```console
python run_project.py demo
python run_project.py benchmark --config configs/p6_trap_construction.json --output results/p6_trap_construction
```

The demo computes its values from a fixed source-defined instance. The
construction workflow compares the declared variants and certificate-backed
references. This known construction explains a possible failure mechanism;
the stochastic high-overlap hypothesis is evaluated by its own matched pilot.

## Supplementary structure and search workflows

### Duplicate-heavy structure

Exact copies increase redundancy. Once one copy is selected, another provides
no new gain while productive alternatives remain. The workflow examines
deduplication and exact-search work; use `duplicate_set_ratio` to identify the
intended structure.

```console
python run_project.py benchmark --config configs/p4_duplicate_heavy.json --output results/p4_duplicate_heavy
```

### Dominated sets

A strict subset has no larger marginal gain than its superset for the same
current coverage. This workflow studies dominance elimination and exact
search, including whether solutions still refer to the original set indices.
Inspect `dominated_set_ratio` and the subset relationships.

```console
python run_project.py benchmark --config configs/p4_dominated_heavy.json --output results/p4_dominated_heavy
```

### Long-tail coverage concentration

Concentrating coverage can produce large early gains and weaker residual
gains. Whether that produces a Greedy gap is an empirical question. The paired
scan varies concentration with fixed nominal set size; inspect the realized
`coverage_skew_gini` and the availability of exact references.

```console
python run_project.py benchmark --config configs/p4_long_tail.json --output results/p4_long_tail
```

### Clustered structure

When sets concentrate within clusters, early choices may overrepresent one
region of the universe. The scan tests that hypothesis through `clusters`,
`within_probability`, and `outside_probability`; the configuration alone
does not establish a failure on each generated instance.

```console
python run_project.py benchmark --config configs/p6_clustered_scan.json --output results/p6_clustered_scan
```

### Controlled stressor audit

For the controlled constructions, inspect target monotonicity, matched
controls, fixed dimensions and incidence, and movement of other metrics:

```console
python run_project.py audit-stressors
python run_project.py benchmark --config configs/p7_controlled_stressors.json --output results/p7_controlled_stressors
```

The audit contract is in [`generator_isolation.md`](generator_isolation.md).
The older P4/P6 configurations retain their own dimensions and parameter
semantics; do not assume their incidence is invariant across a scan.

## Interpreting outputs

The benchmark commands above include exact-reference candidates. A completed
exact run with `status=optimal`, or an independently validated construction
certificate, supplies a reference optimum. A feasible or timed-out incumbent
alone does not. Inspect the stopping metadata as well as status: `feasible`
does not itself establish completed execution.

`configs/sweeps.json` contains Greedy and Local Search without an exact
reference. It supports configuration expansion, structural metrics, and raw
coverage inspection; its outputs alone cannot establish an exact-reference
approximation ratio or Greedy failure rate.

See [`output_schema.md`](output_schema.md) for CSV, report, chart, and manifest
semantics, and [`cli.md`](cli.md) for validation and replay. Publication and
evidence-review requirements are maintained in
[`CONTRIBUTING.md`](../CONTRIBUTING.md).
