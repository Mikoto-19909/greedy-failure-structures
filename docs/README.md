# Documentation

Use this index to distinguish the current research checkpoint from runnable
examples, method checks, and broader exploratory workflows.

## Current research

The next checkpoint compares Greedy failures under `high_overlap` and a
dimension- and expected-size-matched `uniform` control. The
[execution plan in PR #23](https://github.com/Mikoto-19909/greedy-failure-structures/pull/23)
specifies the fixed pilot and its prerequisites. Its proposed
`configs/core_overlap_pilot.json` and offline analysis script await
implementation; they are not yet runnable from this checkout.

Start with [`analysis/README.md`](../analysis/README.md) for research status.
The quick/full and broader workflows below serve other purposes.

## Examples and compatibility checks

- [`README.md`](../README.md): installation and the shortest runnable workflow
- [`README.zh-CN.md`](../README.zh-CN.md): Simplified Chinese project overview
- [`cli.md`](cli.md): validation, execution, resume, summarize, replay, and
  dashboard workflows
- [`output_schema.md`](output_schema.md): generated CSV, report, replay, and
  manifest semantics
- [`reproducibility_matrix.md`](reproducibility_matrix.md): which raw result
  fields must reproduce bit-for-bit and which are exempt, plus the matrix that
  enforces it across operating systems and Python versions

The CLI and PowerShell defaults run quick; the Dashboard initially prefers
`quick.json` without a retained selection. The larger `full.json` workflow
revisits existing instance families. Both retain schema v1 for compatibility.

## Published research

- [`analysis/README.md`](../analysis/README.md): external research analysis
- [`experiments/core_rq/CLAIMS.md`](../experiments/core_rq/CLAIMS.md):
  authoritative claim-to-evidence and validation mapping

## Experiment guidance

- [`failure_mechanisms.md`](failure_mechanisms.md): structural stressors,
  direct greedy traps, and the configurations that exercise them
- [`generator_isolation.md`](generator_isolation.md): target-metric monotonicity,
  confound checks, overlap tails, cluster separation, and matched controls
- [`faq.md`](faq.md): project rationale, algorithm roles, and determinism
- [`faq.zh-CN.md`](faq.zh-CN.md): Simplified Chinese translation maintained
  section-for-section with the English FAQ
- [`lazy_greedy_test_report.md`](lazy_greedy_test_report.md): reproducible
  functional verification for Lazy Greedy
- [`paired_seed_audit.md`](paired_seed_audit.md): RNG stream consumption by
  instance family and the semantics of the paired-seed scheme

These method and functional checks remain useful even when their configuration
names contain phase prefixes. In particular, `p3_lazy_greedy.json` is used by
CI, `p7_controlled_stressors.json` by generator audits, and the pairing
configurations by paired-seed checks.

## Historical exploration and appendices

- [`p6_overlap_scan.json`](../configs/p6_overlap_scan.json): the earlier overlap
  parameter grid, which is separate from the current fixed pilot.
- [`structural_gap_cartography.json`](../configs/structural_gap_cartography.json):
  a broader matched-control scan across structures, strengths, and algorithms;
  see the [cartography command](cli.md#cartography).
- [`configs/`](../configs/): the complete configuration collection, including
  earlier structural sweeps, runtime studies, and additional algorithm comparisons.

Keep these configurations for their existing purposes. Their names and schema
versions do not make them the recommended next research experiment.

## Project policy and history

- [`PRE_PUBLIC_DEVELOPMENT_HISTORY.md`](history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md):
  pre-public milestones and the code-first boundary
- [`CANONICAL_MIGRATION_RECEIPT.json`](history/CANONICAL_MIGRATION_RECEIPT.json):
  machine-readable migration identities
- [`LICENSES/README.md`](../LICENSES/README.md): default-deny file-level license
  mapping

Generated files under `results/` are local artifacts. They are inputs to local
inspection and independent validation, not tracked documentation. Only the
minimum evidence named by the claim ledger is copied into the public evidence
directory.
