# Documentation

This repository is a code-first reproducible experiment engine. It publishes
runnable code, tests, configurations, and documentation, but it does not carry
frozen experiment results or quantitative research claims. See
[`CONTRIBUTING.md`](../CONTRIBUTING.md) for the enforced content boundary.

## Getting started

- [`README.md`](../README.md): installation and the shortest runnable workflow
- [`README.zh-CN.md`](../README.zh-CN.md): Simplified Chinese project overview
- [`cli.md`](cli.md): validation, execution, resume, summarize, replay, and
  dashboard workflows
- [`output_schema.md`](output_schema.md): generated CSV, report, replay, and
  manifest semantics

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

## Project policy and history

- [`PRE_PUBLIC_DEVELOPMENT_HISTORY.md`](history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md):
  pre-public milestones and the code-first boundary
- [`CANONICAL_MIGRATION_RECEIPT.json`](history/CANONICAL_MIGRATION_RECEIPT.json):
  machine-readable migration identities
- [`LICENSES/README.md`](../LICENSES/README.md): default-deny file-level license
  mapping

Generated files under `results/` are local artifacts. They are inputs to local
inspection and independent validation, not tracked documentation.
