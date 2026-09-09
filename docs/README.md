# Documentation

Use this index to distinguish the current research checkpoint from runnable
examples, method checks, and broader exploratory workflows.

## Current research

Open the [interactive research showcase](greedy_failure_showcase.html) in a browser
to try coverage cards, trace the first loss of optimal reachability, and preview
one- or two-card exchanges. The self-contained Chinese page works offline and
explains the R1c comparison using archived examples and a set-inclusion diagram.

The original pilot checkpoint compares Greedy failures under `high_overlap` and a
dimension- and expected-size-matched `uniform` control. The
[execution plan in PR #23](https://github.com/Mikoto-19909/greedy-failure-structures/pull/23)
specifies the fixed pilot and its prerequisites. The
[configuration](../configs/core_overlap_pilot.json) and
[offline analysis](../analysis/core_overlap_pilot.py) have been run on a clean
fixed source revision. Read the [pilot report](../analysis/overlap_pilot_v1.md)
and [pilot configuration and data](../experiments/core_rq/overlap_pilot_v1/), or use the
[pilot commands](cli.md#core-overlap-pilot) to reproduce it.

Start with [`analysis/README.md`](../analysis/README.md) for research status.
The quick/full and broader workflows below serve other purposes.

The [next research plan](greedy_failure_research_plan.zh-CN.md) connects six
papers to studies of greedy decision paths, swap recovery, random instance
regimes, structural controls, and quality certificates. Its R1a/R1b stage is
complete: the [prefix and exchange report](../analysis/r1_prefix_exchange_report.md)
reanalyzes all 60 pilot instances and six separate functional examples. The
[R1c design](../analysis/r1c_confirmation_design.md) fixes the new sample,
primary interval and stopping rules. The [R1c confirmation report](../analysis/r1c_confirmation_report.md)
completes all 3,000 new seed pairs: its interval-width target is met, while the
primary difference interval includes zero. The [new-sample adapter](../analysis/r1c_confirmation_usage.md)
and independent validator have checked all 6,000 instances. R2 exploration is complete;
R3 has completed its feasibility probe and independent confirmation. R4's prefix and
L5 DUAL implementations, full fixed-corpus comparison and published evidence are complete;
see the [final R4 report](../analysis/r4_final_research_report.zh-CN.md). Larger-instance work remains unexecuted.
The existing optional acceleration results are organized into
[CPU verification PR #56](https://github.com/Mikoto-19909/greedy-failure-structures/pull/56) and
[CPU/CUDA production PR #57](https://github.com/Mikoto-19909/greedy-failure-structures/pull/57) for separate review and delivery. The
[workflow speed report](../analysis/gate_speed_comparison_report.md) separately
measures experiment commands and local delivery steps after the gate removal.

## Examples and compatibility checks

- [`README.md`](../README.md): installation and the shortest runnable workflow
- [`README.zh-CN.md`](../README.zh-CN.md): Simplified Chinese project overview
- [`cli.md`](cli.md): validation, execution, resume, summarize, replay, and
  dashboard workflows ([中文](cli.zh-CN.md))
- [`output_schema.md`](output_schema.md): generated CSV, report, replay, and
  result identity and resume semantics ([中文](output_schema.zh-CN.md))
- [`reproducibility_matrix.md`](reproducibility_matrix.md): which raw result
  fields must reproduce bit-for-bit and which are exempt, plus the matrix that
  enforces it across operating systems and Python versions

The CLI and PowerShell defaults run quick; the Dashboard initially prefers
`quick.json` without a retained selection. The larger `full.json` workflow
revisits existing instance families. Both retain schema v1 for compatibility.

## Published research

- [`analysis/README.md`](../analysis/README.md): external research analysis
- [pilot configuration and data](../experiments/core_rq/overlap_pilot_v1/):
  experiment configuration and raw data
- [R1 trajectories and summaries](../experiments/r1_prefix_exchange_v1/):
  exploratory prefix and exchange analysis, with independent recomputation
- [R1c confirmation data](../experiments/r1c_confirmation_v1/): the fixed new
  sample, raw runs, complete trajectories, statistics, execution context and figure

## Experiment guidance

- [`greedy_failure_research_plan.zh-CN.md`](greedy_failure_research_plan.zh-CN.md):
  literature-grounded next steps, staged experiments, and verification criteria
  (Simplified Chinese; R1, R2, R3 and the first R4 calibration completed, larger-instance work pending)
- [`r2_r3_integrated_plan.zh-CN.md`](r2_r3_integrated_plan.zh-CN.md):
  R1 prerequisites, R2 preparation and exploration with an F2 design freeze,
  and conditional R3 feasibility probes leading to F3 and independent confirmation;
  the current batch has completed R2 and R3 feasibility/F3/confirmation
- [R2 exploration report](../analysis/r2_exploration_report.zh-CN.md): complete grid,
  mechanism observations and independent validation; selected evidence is published and linked by immutable commit
- [R3 confirmation design](../analysis/r3_confirmation_design.zh-CN.md): the selected
  local-exposure protocols, independent sampling and prospective inference
- [R3 confirmation report](../analysis/r3_confirmation_report.zh-CN.md): completed
  protocol comparison with 3,000 independent source graphs and 12,000 verified endpoints
- [R4 preparation plan](r4_preparation_plan.zh-CN.md): integer prefix bounds, retrospective
  calibration on the fixed R2 corpus and conditional larger-instance work
- [R4 remaining-work plan](r4_remaining_work_plan.zh-CN.md): baseline closeout, selection
  and small-instance comparison of one tighter bound, followed by a conditional scale-up decision
- [R4 F4 design](../analysis/r4_f4_design.zh-CN.md): completed 18-graph independent preflight,
  fixed 1,800-graph calibration design and measured resource decision
- [R4 calibration report](../analysis/r4_calibration_report.zh-CN.md): complete independent
  verification of 13,000 budget records; one tighter bound, unchanged optimality certification,
  and measured costs separated from exhaustive-reference computation
- [R4 usage](../analysis/r4_usage.zh-CN.md): source association, production, independent
  verification, recovery and saved-data summaries
- [`core_overlap_checkpoint_plan.zh-CN.md`](core_overlap_checkpoint_plan.zh-CN.md):
  fixed single-point comparison of Greedy failures under high overlap and a
  matched uniform control (Simplified Chinese; completed pilot and original design)
- [`failure_mechanisms.md`](failure_mechanisms.md): structural stressors,
  direct greedy traps, and the configurations that exercise them
  ([中文](failure_mechanisms.zh-CN.md))
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

## Implementation plans

The fixed core experiment, documentation cleanup, benchmark B0–B4, reporting,
output validation, generators, record-type splits, and CI routing are complete.
The plans below preserve that implementation history and its original checks.
They are not the current contribution requirements: manifest generation, source
digest ledgers, and the old/new artifact comparison tool have since been removed.
Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for new work and verification.
Benchmark B5 was assessed and cancelled after B4; the documented demo-script
cleanup remains conditional.

- [`benchmark_modularization_plan.md`](benchmark_modularization_plan.md): B0
  historical compatibility baseline and staged runner extraction
- [`reporting_split_plan.zh-CN.md`](reporting_split_plan.zh-CN.md): report module
  boundaries and the original compatibility checks
- [`output_validation_split_plan.zh-CN.md`](output_validation_split_plan.zh-CN.md):
  validator function extraction with preserved rejection behavior and required prechecks
- [`generators_split_plan.zh-CN.md`](generators_split_plan.zh-CN.md): generator
  family modules with stable random draws, ordered instances, and coupling
- [`contracts_split_plan.zh-CN.md`](contracts_split_plan.zh-CN.md): statistical
  record groups with preserved CSV, public exports, and pickle compatibility

## Project policy and history

- [`glossary.md`](glossary.md): the terminology table that Simplified Chinese
  documentation follows, including terms kept in English
- [`documentation_simplification_plan.zh-CN.md`](documentation_simplification_plan.zh-CN.md):
  Simplified Chinese plan for documentation corrections and cleanup, including
  related comments, tests, and completion criteria
- [`PRE_PUBLIC_DEVELOPMENT_HISTORY.md`](history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md):
  pre-public milestones and the code-first boundary
- [`CANONICAL_MIGRATION_RECEIPT.json`](history/CANONICAL_MIGRATION_RECEIPT.json):
  machine-readable migration identities
- [`LICENSES/README.md`](../LICENSES/README.md): content-category license
  mapping
- [`ci_routing_plan.zh-CN.md`](ci_routing_plan.zh-CN.md): implemented CI routing
  for plan-only pull requests, with required checks, fallback behavior, actual
  Actions runs, and measured operational timings

Generated files under `results/` are local artifacts. They are inputs to local
inspection and independent validation, not tracked documentation. Reports link directly to the configurations and data saved in
`experiments/`.
