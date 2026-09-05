# Documentation

This repository is a code-first reproducible experiment engine. It publishes
runnable code, tests, configurations, and documentation, and it may carry a
small number of validated core research claims. See
[`CONTRIBUTING.md`](../CONTRIBUTING.md) for the publication boundary.

## Getting started

- [`README.md`](../README.md): installation and the shortest runnable workflow
- [`README.zh-CN.md`](../README.zh-CN.md): Simplified Chinese project overview
- [`cli.md`](cli.md): validation, execution, resume, summarize, replay, and
  dashboard workflows
- [`output_schema.md`](output_schema.md): generated CSV, report, replay, and
  manifest semantics
- [`reproducibility_matrix.md`](reproducibility_matrix.md): which raw result
  fields must reproduce bit-for-bit and which are exempt, plus the matrix that
  enforces it across operating systems and Python versions

## Published research

- [`analysis/README.md`](../analysis/README.md): external research analysis
- [`experiments/core_rq/CLAIMS.md`](../experiments/core_rq/CLAIMS.md):
  authoritative claim-to-evidence and validation mapping

## Experiment guidance

- [`core_overlap_checkpoint_plan.zh-CN.md`](core_overlap_checkpoint_plan.zh-CN.md):
  planned single-point comparison of Greedy failures under high overlap and a
  matched uniform control (Simplified Chinese; experiment not yet executed)
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

## Project policy and history

- [`documentation_simplification_plan.zh-CN.md`](documentation_simplification_plan.zh-CN.md):
  Simplified Chinese plan for documentation corrections and cleanup, including
  related comments, tests, and completion criteria
- [`PRE_PUBLIC_DEVELOPMENT_HISTORY.md`](history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md):
  pre-public milestones and the code-first boundary
- [`CANONICAL_MIGRATION_RECEIPT.json`](history/CANONICAL_MIGRATION_RECEIPT.json):
  machine-readable migration identities
- [`LICENSES/README.md`](../LICENSES/README.md): default-deny file-level license
  mapping
- [`ci_routing_plan.zh-CN.md`](ci_routing_plan.zh-CN.md): proposed CI routing
  for plan-only pull requests, including required checks, fallback behavior,
  and implementation acceptance checks; not yet implemented

Generated files under `results/` are local artifacts. They are inputs to local
inspection and independent validation, not tracked documentation. Only the
minimum evidence named by the claim ledger is copied into the public evidence
directory.
