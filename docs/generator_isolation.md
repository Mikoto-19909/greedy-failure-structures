# Generator Stressor Isolation Audit

The stressor audit checks realized generator structure before algorithm outcomes
are interpreted. It generates instances from the committed scan configurations,
runs no benchmark algorithm except the deterministic Greedy check required for
the adversarial bait, and prints a JSON document to standard output. The output
is local evidence and is not tracked by the repository.

## Current limitation

The canonical strict audit is expected to return a non-zero status because
gross confound-control failures remain across multiple generator families.
Adding and validating the audit detects this open problem; it does not resolve
it. Until the affected generators or scans are redesigned, the audit must not
be cited as evidence that the suite isolates one structural stressor at a time.

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

The canonical `instances.csv` schema is unchanged. Supplementary audit fields
exist only in the JSON printed by this command, so existing run identities and
benchmark artifacts remain compatible.
