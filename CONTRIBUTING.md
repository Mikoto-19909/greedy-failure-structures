# Contributing

This project studies how Maximum Coverage instance structure affects Greedy's
optimality gap. Keep changes focused on the research question or requested fix.
Discuss new algorithms, instance families, or result schemas before implementing
them when they are outside the agreed task.

## Research workflow

Keep experiment configurations and explicit random seeds. Write exploratory
results under the gitignored `results/` directory. Save useful configurations,
raw data, analysis scripts, and figures with the research report when publishing
a result. Reports should describe the method, sample, findings, and limitations,
and link directly to the data used. At result freezing, publish the explicitly
selected evidence to a protected codex/evidence/* branch and record the verified
remote commit. Unfrozen exploration remains local and is not automatically backed up.
No claim ledger, file checksums, manifest, or separate validation ledger is required.

## Document structure

Use a short outline suited to the document's purpose so readers can find the
question, facts, and next action. These are writing defaults: use the document's
language, combine short sections, and omit sections that add no useful content.
These outlines introduce no regex or text-matching checks for headings, wording,
or section order.

- **Research report:** question and main finding; method and data (configuration,
  sample, seed, comparison baseline, and metric); results with tables or figures;
  interpretation and limitations; commands and data links for reproduction.
- **Plan:** objective and current state; scope; proposed steps; how completion
  will be checked; unresolved questions, if any.
- **Usage guide:** purpose and prerequisites; runnable commands or steps;
  expected output and how to read it; common problems when relevant.

Keep the README short and link to these documents. When changing a command,
result field, or research conclusion, update its explanation in the same change
and check the affected example or calculation. Prefer generating numerical
tables and figures from the analysis script. Review hand-written interpretations
and links against their sources; passing code tests does not establish that all
prose is correct.

The benchmark report generator provides a default layout. The output validator
checks CSV identities, numerical consistency, and selected charts; it does not
compare Markdown paragraphs or enforce report headings. Rebuilding a generated
report overwrites edits to it, so keep durable research prose under `analysis/`.

## Correctness and reproducibility

Preserve algorithm correctness, deterministic tie-breaking, stable experiment
identities, and result ordering. Internal configuration, instance, and run hashes
support result joins and resume; they are not file-integrity records.

Randomized algorithms use explicit seeds. A timed-out solver's incumbent must
not be used as a proven optimum. Check selected-set feasibility and coverage,
reference status, sample pairing, and the arithmetic behind reported results.

## Verification

Use relevant existing tests while developing. The daily check runs core tests,
required research verification and mypy:

```console
python scripts/check.py
```

R2/R3 reference configurations live in their published snapshots rather than the
source tree. When research tests are selected, the check entry restores missing
local copies from the original merged commit, without network access or overwriting existing files; `--list`
does not restore files. Use a complete clone with that history. Before direct
unittest discovery or research commands in a fresh clone, restore the missing
configs explicitly (do not overwrite an existing local config):

```console
git restore --source=cef5b92954571423b10a0c3b56947a4b26400d3c --worktree -- analysis/r2_f2_config.json analysis/r3_confirmation_config.json
```

Install check dependencies with `pip install -e ".[typecheck]" scipy==1.18.1 numpy==2.3.5`.
Before merging changes to the check system, run `python scripts/check.py --profile full`
and obtain an independent review with valid and invalid inputs. All new tests default
to core; required research verification must execute, never silently skip.
See [checks and evidence](docs/checks_and_evidence.zh-CN.md) for profiles, CI routing,
independent definition review and evidence freezing. Add a focused
regression test for a bug fix. For runner changes, exercise a fresh run and resume;
for analysis changes, check the affected calculations. The optional
`.github/scripts/validate_benchmark_output.py` recomputes results from the
configuration and CSVs without a manifest. It is available when detailed output
checking is useful, rather than a prerequisite for exploratory analysis.

Report actual failures, skips, and unavailable checks. Do not replace behavior
tests with tests that merely search documentation for particular wording.

## Collaboration and licensing

Use a focused branch and pull request for publication. Do not push directly to
the default branch. Preserve unrelated local work. Keep authorship with the
contributor and use clear commit messages explaining the change.

Code and machine-readable inputs use the MIT License; prose uses CC BY 4.0.
Bundled fonts retain their own licenses. See [LICENSES/README.md](LICENSES/README.md).
The one-time migration records in `docs/history/` and
`PUBLIC_SNAPSHOT_MANIFEST.json` are historical records and need no regeneration.
