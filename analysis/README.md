# Research analysis

The [R2 exploration report](r2_exploration_report.zh-CN.md) completes the fixed-size
budget grid: 1,800 source graphs, 13,000 budget records and independent verification.
The [F2 design](r2_exploration_design.zh-CN.md) and [usage guide](r2_usage.zh-CN.md)
describe the frozen inputs and reproducible commands. Selected evidence is published on protected evidence branches and linked by immutable commit from each report.
The [R3 confirmation report](r3_confirmation_report.zh-CN.md) completes the
[frozen design](r3_confirmation_design.zh-CN.md): 3,000 new source graphs and 12,000
independently verified endpoints establish the specified protocol contrast.
See the [execution guide](r3_confirmation_usage.zh-CN.md) for recovery and verification commands.

The [R3 fixed-degree counterexample tool](../docs/r3_counterexamples.zh-CN.md)
finds exploratory pairs for E0 and first-step irrecoverability while preserving
indexed row and column degrees. It saves exact O/O1 witnesses and replayable
switches; it does not run or replace the R3 confirmation protocol.

For hands-on counterexample experiments, start with the
[experiment walkthrough](../docs/counterexample_experiments.zh-CN.md).
`counterexamples.ps1` offers short commands for mining, creating a conjecture,
searching it, and independently checking the result before displaying it.

The [bounded conjecture refuter](conjectures_usage.zh-CN.md) searches explicit
structural premises for a violation of a Greedy coverage-ratio claim. It checks
the exact witness independently and distinguishes domain exhaustion from an
unfinished search.

The [counterexample miner and reducer](counterexamples_usage.zh-CN.md) selects
Greedy failures from saved R1/R1c instances or instance JSON and produces smaller,
independently checked replay cases. These selected cases support explanation and
testing, not population failure-rate estimates.

Start with the [R1c confirmation report](r1c_confirmation_report.md). Its fixed
3,000 new seed pairs meet the interval-width target but do not establish the
direction of the conditional tie-avoidability difference. The
[configuration, raw inputs, trajectories and summaries](../experiments/r1c_confirmation_v1/)
support the report and figure.

The [high-overlap pilot report](overlap_pilot_v1.md) explains the original
fixed comparison, observed failure rates, structural diagnostics, and limitations.
The [configuration and data](../experiments/core_rq/overlap_pilot_v1/) accompany
the report; [core_overlap_pilot.py](core_overlap_pilot.py) computes the paired
analysis and figure directly from the configuration and CSV inputs.

The [R1 prefix and exchange report](r1_prefix_exchange_report.md) completes the
exploratory follow-up on the same 60 instances, with six separate functional
examples. It locates the first loss of optimal reachability and compares one-swap
with up-to-two-swap recovery. The [design](r1_prefix_exchange_design.md),
[analysis](greedy_failure_paths.py), [independent recomputation](validate_greedy_failure_paths.py),
and [saved trajectories and summaries](../experiments/r1_prefix_exchange_v1/)
accompany the findings. The [R1c new-sample design](r1c_confirmation_design.md)
fixes 3,000 new seed pairs and a single primary contrast in tie-avoidable failure
proportions. The [analysis and validation commands](r1c_confirmation_usage.md)
are implemented and independently checked on the complete formal batch as well
as the preflight and functional examples. R1c, R2 and R3 confirmation are complete; R4 remains future work.

The [workflow speed comparison](gate_speed_comparison_report.md) measures the
same experiment commands and local research-delivery steps before and after
removing the gates. Its [paired timings and workflow steps](../experiments/gate_speed_comparison_v1/)
support a scoped performance observation, not a model reasoning-speed claim.

For new research, keep the configuration, seeds, raw results, and analysis
script. Link reports directly to their data. The
[contribution guide](../CONTRIBUTING.md#research-workflow) describes this workflow.
Use its [research report outline](../CONTRIBUTING.md#document-structure) to cover
the question, method, results, interpretation, and reproduction steps. Adapt the
headings and length to the study.
