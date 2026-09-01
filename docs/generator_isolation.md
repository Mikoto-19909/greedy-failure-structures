# Generator Stressor Isolation Audit

The stressor audit checks realized generator structure before algorithm outcomes
are interpreted. It generates instances from the committed scan configurations,
runs no benchmark algorithm except the deterministic Greedy check required for
the adversarial bait, and prints a JSON document to standard output. The output
is local evidence and is not tracked by the repository.

## Current scope

The default audit uses `configs/p7_controlled_stressors.json`. Its controlled
families hold universe size, candidate-set count, budget, and total incidence
exactly fixed across intensity levels. The earlier P4/P6 scans remain available
with their original identities and known gross confound-control failures; they
are not silently reinterpreted as controlled experiments.

With the committed controlled configuration unchanged, the default `--strict`
invocation is expected to succeed as a functional contract.

Passing the controlled gross checks does not prove that every non-target
structural statistic is constant. Some target constructions mechanically move
coverage concentration, union size, or overlap tails. Those movements remain
in the report and must be accepted explicitly, controlled in the analysis, or
used to narrow the paper's claim.

Run the canonical audit with:

```console
python run_project.py audit-stressors
```

Repeat `--config PATH` to audit a different set of configurations. Add
`--strict` when a non-zero process status is required for any requested scan
whose gross isolation checks fail or that is skipped. A scan of cluster count
is descriptive: more clusters do not by themselves mean stronger
within-cluster separation, so that parameter has no declared monotonic
direction. A descriptive scan does not by itself make strict mode fail.

## Target metrics

The registered audit targets are:

- `duplicate_heavy`: `duplicate_set_ratio` over `copy_factor`;
- `dominated_heavy`: `dominated_set_ratio` over `child_count`;
- `high_overlap`: mean pairwise Jaccard overlap over `core_fraction` or
  `core_probability`;
- `long_tail`: element-frequency Gini over `gamma`;
- `clustered`: within-cluster minus between-cluster mean Jaccard overlap over
  `within_probability` or `outside_probability`;
- versioned `adversarial`: constructed severity over `trap_count`, together
  with Greedy choosing index zero first and successful optimum-certificate
  validation.

The controlled counterparts are:

- `controlled_duplicate`: balanced copies over `copy_factor` at fixed total
  set count and fixed set size;
- `controlled_dominated`: neutral disjoint pairs converted to strict-subset
  pairs over `dominated_pair_count`, with constant pair incidence;
- `controlled_high_overlap`: a shared core over `shared_core_size`, with an
  exact fixed cardinality for every set;
- `controlled_clustered`: per-cluster shared cores over `within_core_size`,
  with disjoint cluster cores and set-specific fringes;
- `controlled_adversarial`: a certified bait over `trap_count`, with a
  compensating dominated padding set that keeps total incidence constant.

For the `clustered` generator, a set's cluster label is its index modulo the
declared cluster count. That is the same assignment used by the generator.
Pairwise overlap quantiles use deterministic linear interpolation over the
sorted realized Jaccard values. The audit also records the share of incidence
carried by the most frequently covered tenth of the universe.

## Confound checks and controls

Each scan reports whether universe size, candidate-set count, and budget are
exactly invariant across levels. It reports the relative range of level-mean
incidence and compares it with the declared tolerance. The gross `assessment`
uses target monotonicity, those dimension checks, incidence stability, and the
adversarial checks when applicable.

Every treatment observation receives a generated `uniform` control with the
same realized universe size, candidate-set count, and budget. Its density
parameter is matched to the treatment's realized density. Because the control
is Bernoulli-generated, its realized incidence need not equal the treatment's;
the audit reports the remaining relative difference rather than hiding it.

The report also carries level means and ranges for every measured non-target
metric, including Jaccard quantiles, frequency concentration, duplicates, and
dominance. Both unique-set and duplicate-set ratios are emitted explicitly.
These diagnostics are deliberately not collapsed into one universal
leakage threshold: some target structures mechanically change more than one
summary statistic. A paper-level isolation claim should name which non-target
movements are accepted, controlled in a model, or grounds for redesigning the
scan.

The controlled families use new registry names instead of changing legacy
factory semantics. The canonical `instances.csv` schema is unchanged, and
existing run identities and benchmark artifacts remain compatible.
