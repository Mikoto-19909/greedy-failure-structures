# Research analysis

Start with the [high-overlap pilot report](overlap_pilot_v1.md). It explains the
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
accompany the findings. R1c and R2–R4 remain proposed work.

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
