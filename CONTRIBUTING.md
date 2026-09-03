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

## Evidence-backed research claims

This repository may publish a small number of validated core research claims.
Full exploratory output remains untracked under `results/`. The minimum frozen
evidence for a public claim belongs in `experiments/core_rq/`, and the external
research narrative belongs in `analysis/`.

[`experiments/core_rq/CLAIMS.md`](experiments/core_rq/CLAIMS.md) is the single
claim ledger. Every quantitative research claim in tracked prose must carry a
claim ID that leads to the exact result rows or filters, analysis figure,
configuration, manifest, and independent validator command recorded as PASS.
The root README may point readers to a claim, but it must not become a second
copy of the evidence table or analysis.

Run the complete experiment and validator against the gitignored output before
copying the minimum evidence into the repository. Preserve generated evidence
filenames and bytes. A generated manifest may contain an absolute configuration
path; replace it with the repository-relative `config.json` in the complete
local output and rerun the existing validator before publishing that manifest.

The content-boundary workflow runs in `evidence_backed_claims` mode. That mode
permits quantitative prose; it does not prove that a claim matches its evidence.
The contributor and reviewer must check the `CLAIMS.md` mapping. The same
workflow continues to reject personal paths, credential-shaped strings, and
broken internal links across tracked text.

Keep quantitative research claims out of commit messages and release notes,
where the frozen evidence chain is not present. The existing commit-policy check
enforces the commit-message part of this rule. The bundled starter workflow
remains a functional check rather than evidence about algorithm performance.

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
is about 35% of the source by line, and those modules hold a real backlog of
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
