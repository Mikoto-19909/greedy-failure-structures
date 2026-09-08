# Acceleration experiment archive

Local archival commit for the CPU/CUDA work of 2026-09-08. This is not a remote
evidence freeze and does not change the original R2 research data or protocol.

## Contents

- `cuda_pilot/`: initial CUDA/compiled-CPU kernel comparison, nine-graph pipeline
  integration, profiling, independent-verifier prototype and their checks.
- `batch_scaling/`: 36 verification-command measurements over 90/360/1,800 graphs.
- `e2e_ab/`: six fresh full R2 workflows with Python versus Numba verification.
- `verification_acceptance/`: full local test log, nine-graph CLI acceptance,
  actual missing-dependency fallback checks and independent agent review files.

Each stage retains top-level scripts, plans, environments, summaries, raw timing
tables and reports as ordinary files, subject to the repository's normal text
line-ending policy. That stage's `run_details.zip` contains every selected file
in its original byte representation, including those readable copies and all
graph JSON, verification reports, command logs and checkpoint journals. Paths
inside each ZIP match the original stage layout. Extract into a separate writable
directory to recover that layout. Every archived member was compared byte-for-byte
with its local source after ZIP readback. No file-hash ledger is required.

Virtual environments, bytecode/JIT caches and compiler temporary directories
are runtime byproducts and are not part of this archive. Original local output
directories are retained.

## Reproduction and historical paths

The scripts are the exact measured snapshots, not new public commands. Some
contain original absolute paths and assume their original location under
`results/`. Do not run them directly inside this archive. For reproduction,
restore the corresponding measured layout in a disposable checkout, use the
recorded code commit and pinned environment, and point source paths at a local
copy of the recorded R2 archive. The original layout mappings are:

- `cuda_pilot/` -> `results/cuda_trial_v1/` (in the original R4 checkout).
- `batch_scaling/` -> `results/batch-scaling-v1/`.
- `e2e_ab/` -> `results/e2e-ab-v1/`.
- `verification_acceptance/` -> `results/fast-verification/`.

The last three used the fast-verification worktree. Per-stage plans/reports name
the measured revision, command boundary, source archive and excluded startup or
comparison costs. Historical reports and scripts may refer to the original
`runs/...` paths; these are preserved inside the corresponding ZIP.

Code/data use the repository MIT license; prose and original research figures
use CC BY 4.0, following `LICENSES/README.md`. The same categories apply inside ZIPs.
