# First R2 production backend acceptance

Measured implementation: `0eda797c661317a11bac54eb52e7b0c722a54b04`.
This local archive covers three nine-graph pilots and nine fresh 1,800-graph
workflows, the complete CPU check log, explicit GPU checks, independent review
(including the original budget-stop failure and its successful retest), and
actual missing-site-package checks.

Top-level plans, configurations, environments, scripts, reports and raw timing
tables are directly readable. `run_details.zip` contains every selected original
file, including those readable copies and full graph/CSV/checkpoint/command
outputs, byte-preserved and checked against the measured local files. Git may
normalize readable text line endings. Runtime compiler caches are excluded.

The recorded scripts assume their original location `results/production-v1/`
and reference the local R2 input archive. For reproduction, restore that layout
in a disposable checkout of the recorded implementation, install the recorded
CPU/CUDA environment and point the input path at the same R2 corpus (recorded
source evidence commit `4a419f338d70068fa988fa97027734cdcda0a036`). Existing
successful measurements are not overwritten. Historical review scripts may
expect pre-fix behavior; `review_fixed.py` records the fixed retest.

The primary metric is the declared no-plot CLI workflow, with fresh process
startup and cache loading included. CUDA uses one owner and serial CPU diagnosis;
CPU backends use four workers. These are execution-configuration comparisons,
not isolated hardware speed ratios. See `REPORT.zh-CN.md` for all limitations.

This archive is a local commit, not a remote publication freeze. Code/data use
the repository MIT license and prose uses CC BY 4.0, including files inside ZIPs.
