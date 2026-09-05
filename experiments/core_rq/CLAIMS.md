# Core research claims

This ledger maps the published research claims to their frozen evidence.

## C1

Claim: The fixed high-overlap versus uniform pilot did not provide sufficient
paired evidence of a difference in Greedy failure rates. The observed rates were
12/30 and 10/30, respectively; their difference was 2/30, with two-sided exact
McNemar p=0.7744140625. This is a result for the prescribed generating mechanisms
and parameter setting, not evidence of equivalence or a causal effect of overlap alone.

Result: [`paired_instances.csv`](overlap_pilot_v1/paired_instances.csv), all data
rows, repetition 0 through 29. `treatment_failure` and `control_failure` give
`(n00,n10,n01,n11)=(13,7,5,5)`, hence the failure counts and paired test.
`treatment_gap` and `control_gap`, including zeros in all rows, give means
0.01545555343 and 0.007653664303 and mean paired difference 0.007801889131.

Canonical sources: [`raw_results.csv`](overlap_pilot_v1/raw_results.csv), filtered
by `algorithm_id=greedy` and `algorithm_id=exact_reference`, joined through
`instance_id` to [`instances.csv`](overlap_pilot_v1/instances.csv), then paired by
case role and repetition. [`greedy_failure_statistics.csv`](overlap_pilot_v1/greedy_failure_statistics.csv)
contains the corresponding `overlap` and `overlap_control` rows.
[`reference_status.csv`](overlap_pilot_v1/reference_status.csv) records an optimal
reference for every instance; the raw exact-reference rows all have `status=optimal`.

Structural diagnostics: all rows of `instances.csv`, grouped by `case_id`, and
the matching role-prefixed fields in `paired_instances.csv`. Means, minima,
maxima and paired mean differences use `pairwise_overlap_mean_jaccard`,
`actual_density`, `mean_set_size`, `covered_element_count`, and
`coverage_skew_gini`. The full diagnostic table is in the
[research analysis](../../analysis/overlap_pilot_v1.md#结构是否按预期变化).

Figure: [`overlap_pilot_v1.svg`](../../analysis/overlap_pilot_v1.svg), copied
without byte changes from the generated `failure_rate.svg`.
SHA-256: `dc610d05f044e4af5c130d8dff85a41f8195c66552fccd659965fd434b5c0de9`.
The analysis validation record binds this figure hash; the benchmark manifest
does not declare the separate offline analysis figure.

Configuration: [`config.json`](overlap_pilot_v1/config.json), normalized hash
`593d362a8a5bdcd8dc0366e9d1cb05238c6a07b8cc0c75419691511c53e8e17d`.

Manifest: [`manifest.json`](overlap_pilot_v1/manifest.json). Source commit
`27acae5f2ee9f478fba22af98c6694382a0a7100`, `dirty=false`.
Only `configuration.path` was normalized to `config.json` in the complete local
output before the validator and analysis were run; generated evidence bytes were
otherwise retained.

The frozen evidence uses the corrected run in `results/core_overlap_pilot_v2`
after the selection-coverage validation fix in PR #29. The first run remains
local in `results/core_overlap_pilot_v1`; its records are not pooled with the
corrected run and do not increase the sample size.

Validation: PASS —
`python .github/scripts/validate_benchmark_output.py --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v2`.
The command targets the complete local output, not this frozen subset. Separate
independent recomputation covers the paired statistics and diagnostic table;
scope, commands, results and digests are recorded in
[`validation.md`](overlap_pilot_v1/validation.md).

## Review order

1. Start with the external [research analysis](../../analysis/README.md).
2. Return here for the authoritative mapping behind each claim ID.
3. Inspect the named result rows or filters, configuration, and manifest.
4. Check the recorded validator command and PASS result.

The content-boundary workflow permits quantitative prose but does not verify
this mapping. Contributors and reviewers perform that check directly.

## Required claim entry

Add one section per public claim using this format:

```markdown
## C1

Claim: A single testable statement.

Result: [`generated-statistics.csv`](generated-statistics.csv), with the exact
rows, columns, or filters that support the statement.

Figure: [`reader-facing-figure.svg`](../../analysis/reader-facing-figure.svg),
including the generated source filename and matching manifest hash when renamed.

Configuration: [`config.json`](config.json).

Manifest: [`manifest.json`](manifest.json).

Validation: PASS — `python .github/scripts/validate_benchmark_output.py ...`
```
