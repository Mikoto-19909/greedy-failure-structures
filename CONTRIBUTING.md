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
and link directly to the data used. No claim ledger, file checksums, manifest,
or separate validation record is required.

## Correctness and reproducibility

Preserve algorithm correctness, deterministic tie-breaking, stable experiment
identities, and result ordering. Internal configuration, instance, and run hashes
support result joins and resume; they are not file-integrity records.

Randomized algorithms use explicit seeds. A timed-out solver's incumbent must
not be used as a proven optimum. Check selected-set feasibility and coverage,
reference status, sample pairing, and the arithmetic behind reported results.

## Verification

Use relevant existing tests while developing. Before merging a code change, run:

```console
python -m unittest discover -s tests -v
python -m mypy
```

Install the type checker with `pip install -e ".[typecheck]"`. Add a focused
regression test for a bug fix. For runner changes, exercise a fresh run and resume;
for analysis changes, check the affected calculations. The optional
`.github/scripts/validate_benchmark_output.py` checks generated benchmark
outputs against the execution configuration. Use it when detailed output
checking is useful.

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
