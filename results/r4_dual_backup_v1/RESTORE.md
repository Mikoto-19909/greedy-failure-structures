# R4 DUAL backup and restoration

This snapshot preserves the completed study at source commit
`f144418eb09bb61d9b9b28f866f8c91ededbe7ad`. The computation is fixed to
`d31cf2e62efb57fe939ce38cfe35a671314477d0`; the design was committed in `0bf8a58`.
The two Git bundles contain complete history with no external prerequisites.
They contain only the requested source branch and the fixed baseline evidence
branch, not other active worktree branches, environments or credentials.

The original report's local-only statements describe the study before this
backup. Remote backup completion requires the publisher's verified commit and
tree readback; a local snapshot or successful ZIP extraction alone is not that
confirmation. Existing validation results are preserved, not re-executed or
relabeled as new scientific validation during byte-preserving backup.

## Restore into a new directory

Run these PowerShell commands from the root of the downloaded/cloned evidence
snapshot. Choose a new destination; do not use an existing working repository.

```powershell
$evidenceRoot = (Get-Location).Path
$restoreRoot = Join-Path (Split-Path $evidenceRoot -Parent) 'r4-dual-restored'
git clone --branch codex/r4-l5-dual "$evidenceRoot/results/r4_dual_backup_v1/dual-source.bundle" "$restoreRoot"
New-Item -ItemType Directory -Force -Path "$restoreRoot/results"
git clone --branch codex/evidence/r4-calibration-v1 "$evidenceRoot/results/r4_dual_backup_v1/r4-baseline-evidence.bundle" "$restoreRoot/results/frozen-r4-calibration-v1"
$dataPaths = @(
  'r4_dual_comparison_v1', 'r4_dual_comparison_v1_commands',
  'r4_dual_preflight_v1', 'r4_dual_full_check.log',
  'r4_dual_comparison_numbers.json', 'r4_dual_execution_source.zip',
  'r4_dual_measure_commands.py', 'r4_dual_session_close.json'
)
foreach ($relative in $dataPaths) {
  Copy-Item -LiteralPath (Join-Path "$evidenceRoot/results" $relative) -Destination "$restoreRoot/results" -Recurse
}
Copy-Item -LiteralPath "$evidenceRoot/analysis/r4_next_question_and_l5_feasibility.zh-CN.md" -Destination "$restoreRoot/analysis"
Set-Location -LiteralPath $restoreRoot
git rev-parse HEAD
git -C results/frozen-r4-calibration-v1 rev-parse HEAD
```

Expected source HEAD is `f144418eb09bb61d9b9b28f866f8c91ededbe7ad`; expected
baseline HEAD is `1a8b1899d927cba202cf7931fe992ecd2b5a1807`.
The latter Git object is needed by `SourceAccess`; plain JSON or a source ZIP
does not replace this Git repository. The method handoff document was untracked
in the source working tree and is backed up unchanged as a separate file.

Use Python 3.12 (the original run used 3.12.14). Dependencies for the full test
suite are documented in CONTRIBUTING.md; virtual environments are not backed up.
The restored original study is already complete: 1,800 graphs, 13,000 budgets,
97,200 prefix conditions and 65 summary cells. No production resume is needed.
For an intentional fresh verification of the restored copy:

```powershell
python analysis/validate_r4_dual.py --source results/frozen-r4-calibration-v1 --output results/r4_dual_comparison_v1
python analysis/validate_r4_dual.py --output results/r4_dual_comparison_v1 --summaries-only
```

Those commands recheck current restored data and append resource accounting;
they do not reproduce the historical execution timings. The immutable backup
retains the original verification reports and logs.

## Included data and intentional exclusions

All formal graph checkpoints, CSVs, verification/resource records, command logs,
the independent numeric audit, preflight inputs/certificates/failure history,
source archive, full check log and reviewed method notes are included.
The preflight's 1,800 four-byte synthetic directory-probe files are omitted;
their generation parameters and all 20 measured timings remain in the resource
report. Existing zero-byte operation locks may remain as ordinary inert files;
there is no active-operation marker or unfinished production batch.

This backup does not merge or publish the development branch itself. Its full
history is recoverable from `dual-source.bundle`. Other worktrees and unrelated
results are excluded.
