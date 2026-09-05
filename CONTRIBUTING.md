# Contributing

This project studies the Maximum Coverage problem. Contributions may address
bugs, portability, documentation and deterministic tests.

## Development and scope

This public repository is the canonical home for development, issues, pull
requests, CI and releases. Work on a branch, open a pull request here, wait for
the configured required checks, and merge through that pull request. Do not push
directly to the default branch. After merging, delete the merged branches and
verify that no stale branches remain.

Keep each pull request focused on one responsibility. Do not cherry-pick
unrelated governance or configuration changes into a feature pull request or
reformat unrelated code. When formatting hooks change files, stash or fix those
changes before retrying the push; do not bypass the hooks.

Discuss a new algorithm, instance family or output schema before implementing
it: these changes can affect stored run identities and reproducibility.

`docs/history/` and `PUBLIC_SNAPSHOT_MANIFEST.json` record the one-time
migration. Keep them unchanged when current policy changes. They are not an
import, upstream publication or synchronization channel; do not add a second
development path or recurring cross-repository publication workflow.

## Correctness and reproducibility

Stable identities, fixed tie-breaking and reproducible ordering are contracts.
If identical inputs acquire different identities or result ordering, the change
is breaking even when the results look equivalent. Configuration hashes use the
normalized configuration; check changes against that representation and the
derived identities rather than treating configuration edits as cosmetic.

Randomized algorithms require an explicit seed; deterministic algorithms must
not take one. A timed-out solver supplies an incumbent, never a reference
optimum. Code and tests must preserve that distinction.

Add a regression test for a bug fix and a seeded case for randomized behavior.
Test the behavior or fact a rule asserts. The presence of a word in a document
does not establish that its claim is true, and passing tests establish only the
cases they cover. When documentation, code and tests disagree, check the
intended rule and algorithm definition before correcting the mistaken source.

## Evidence-backed research claims

The repository may publish a small number of validated core research claims.
Full exploratory output stays untracked under `results/`. Minimum frozen
evidence belongs in `experiments/core_rq/`; the external research narrative
belongs in `analysis/`.

[`experiments/core_rq/CLAIMS.md`](experiments/core_rq/CLAIMS.md) is the single
claim ledger. Every quantitative research claim in tracked prose must cite its
claim ID. The entry must identify exact result rows or filters, an analysis
figure, configuration, manifest and an independent validator command recorded
as PASS. Do not create a parallel claim list or duplicate the evidence table
and analysis in the README; link to them.

Run the complete experiment and validator against the gitignored output before
copying minimum evidence into the repository. Preserve generated filenames and
bytes. If a generated manifest contains an absolute configuration path, replace
that path with the repository-relative `config.json` in the complete local
output and rerun the existing validator before publishing the manifest.

The content-boundary check runs in `evidence_backed_claims` mode. It permits
quantitative prose and rejects personal paths, credential-shaped strings and
broken relative links across tracked files. It does not verify the
claim-to-evidence mapping: contributors and reviewers must check that mapping
in `CLAIMS.md`. A passing content-boundary check is not evidence that a claim
matches its source artifacts.

The fixture marker is a per-line test-fixture exemption that bypasses every
content check on that line. Do not use it in ordinary content. If a legitimate
tracked file needs an exclusion, make the narrowest justified exclusion and
preserve coverage for the rejected form.

Keep quantitative research claims out of commit messages and release notes.
The commit-policy check enforces the commit-message rule. The bundled starter
workflow is a functional check, not evidence of algorithm performance.

## Verification

Before merge, verify the final change with the required checks and report their
actual results:

```console
python -m unittest discover -s tests -v
python .github/scripts/check_content_boundary.py --claim-mode evidence_backed_claims
python .github/scripts/build_license_manifest.py --check
python -m mypy
```

Use relevant tests during development. When the task authorizes targeted local
testing, state which local checks were omitted and use the required checks on
the current pull request revision for the remaining coverage. Do not disable
required CI checks to avoid repeating local checks or present omitted checks
as passed.

`build_license_manifest.py` reads the Git index. Stage the intended file changes,
run `python .github/scripts/build_license_manifest.py`, and stage
`LICENSE_MANIFEST.json` before running its `--check` command. Check the staged
diff for whitespace errors before committing, then run the commit-policy check
over the resulting commit range.

Install the type checker with `pip install -e ".[typecheck]"`. The configured
mypy check covers `src/maxcover`; the per-module `ignore_errors` overrides in
[`pyproject.toml`](pyproject.toml) identify the legacy modules whose errors are
excluded. A clean configured run does not establish that a change in an exempt
module is free of type errors. Check an affected module with its override temporarily
removed. New modules are checked by default; do not expand exemptions to hide
problems introduced by a move. Keep necessary type fixes separate from a
mechanical move, and remove an exemption in a separate pull request from a
behavioral change.

If a tool is unavailable, report the missing check and use available CI coverage;
do not substitute an earlier revision's result. Agents must also follow the
independent review requirements in [`AGENTS.md`](AGENTS.md).

## Commit messages and authorship

Use imperative conventional-commit messages (`feat:`, `fix:`, `docs:`,
`refactor:`) that explain why the change is needed.

Authorship stays with the contributor. Do not add an AI assistant or model to a
`Co-Authored-By` trailer, a "generated with" line, or the author or committer
identity. `.github/scripts/check_commits.py` checks these fields over the commit
range.

## Licensing

Code contributions use the MIT License. Documentation and other non-code
content use CC BY 4.0; see [`LICENSES/README.md`](LICENSES/README.md) for the
file-level mapping. By submitting a pull request, you agree to license your
contribution on those terms.
