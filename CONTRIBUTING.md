# Contributing

Thanks for looking at this project. It is research code for studying the
Maximum Coverage problem, maintained by one person, so please read the scope
notes below before opening a pull request.

## Where development happens

This public repository is the canonical home for current software development,
issues, pull requests, CI and releases. Make changes on a branch, open a pull
request here, wait for the configured required checks, and merge through the
pull request. The migration records under `docs/history/` and
`PUBLIC_SNAPSHOT_MANIFEST.json` are provenance for how the repository began;
they are not an upstream, an import channel or a synchronization mechanism.

## What this repository accepts

Bug reports and fixes, portability problems, clearer documentation, and
additional deterministic tests are all welcome.

Larger changes — a new algorithm, a new instance family, a new output schema —
need discussion first. They interact with the reproducibility contracts
described below, and a change that looks local can invalidate stored run
identities.

## Ground rules

**Determinism is a contract, not a preference.** Stable identities, fixed
tie-breaking and reproducible ordering are load-bearing. A change that makes
identical inputs produce different identities or a different result ordering is
a breaking change, even when the new behaviour looks equivalent.

**Timeouts are not optima.** A solver that ran out of time yields an incumbent,
never a reference optimum. Any code or test that treats a timed-out result as
optimal is wrong regardless of the numbers it produces.

**Randomized algorithms take an explicit seed; deterministic ones must not.**

## Single claim source

This is the rule most likely to affect a contribution, and it is enforced, not
merely requested.

**This repository publishes no quantitative research claims.** It contains no
experiment results, performance comparisons, failure rates, gap figures or
runtime measurements, and it must stay that way. Do not add them to the README,
to documentation, to release notes, or to commit messages.

"Publishes" is the operative word, because the code computes numbers by design.
`demo` prints a coverage gap and a benchmark run writes measurement CSVs under
`results/`. Both are generated on the machine that runs them, from inputs
committed here, and neither is tracked. The rule governs claims this repository
*carries* — a figure in prose, a results table, a stored corpus of outcomes —
not what its code produces when you execute it. If you are unsure which side a
change falls on, the practical test is whether `git status` would show it.

If you have measurements you believe belong here, they cannot be added as prose.
Any quantitative statement must derive from a single frozen evidence chain —
typed CSV, then manifest and checksum, then an independent validator, then the
statement — with every step reproducible by someone else. Without that chain
closed, the statement does not go in.

The rule is unconditional, which catches one honest case worth naming: quoting a
prohibited phrase as an example. If you are describing a bug — a checker that
failed to reject something, say — describe the form rather than reproducing it.
Write "a metric stated with a value" instead of the phrase itself. Two commits
predating this note quote such examples verbatim; they are known exceptions and
were left unrewritten rather than having a pushed history amended.

This is why the bundled starter workflow is described as a functional check
rather than a benchmark: it verifies that the code runs, and it is not evidence
about how well anything performs.

## Before you open a pull request

```console
python -m unittest discover -s tests -v
```

Optionally, with the type checker installed via `pip install -e ".[typecheck]"`:

```console
python -m mypy
```

A clean mypy run is narrower than it looks. `pyproject.toml` exempts
`maxcover.benchmark` and `maxcover.reporting` with `ignore_errors = true`, which
is about 40% of the source by line, and those modules hold a real backlog of
unresolved errors. So mypy passing does not mean your change is type-clean if it
lands in either — check it by temporarily removing the override for the module
you touched. Reducing that backlog is welcome as its own change; do not remove an
exemption in the same pull request as a behavioural change, since the two cannot
then be reviewed apart.

Add a regression test for a bug fix, and a seeded case for anything randomized.
Keep changes focused; unrelated reformatting makes review harder.

## Commit messages

Write in the imperative and say why, not just what. Conventional-commit
prefixes (`feat:`, `fix:`, `docs:`, `refactor:`) are used here.

Do not attribute commits to an AI assistant. No `Co-Authored-By` trailer naming
a model, and no "generated with" line. Authorship stays with the person who
submitted the work. This is checked over the commit range by
`.github/scripts/check_commits.py`.

If you are directing an AI agent to work in this repository, [`AGENTS.md`](AGENTS.md)
carries the additional constraints that apply to it — chiefly around reviewing
its own work, since the defects here have concentrated in changes where a
documented rule and its enforcing code disagreed.

## Licensing your contribution

Code contributions are under the MIT License; documentation and other non-code
content are under CC BY 4.0. See [`LICENSES/README.md`](LICENSES/README.md) for
the file-level mapping. By submitting a pull request you agree your
contribution is licensed on those terms.
