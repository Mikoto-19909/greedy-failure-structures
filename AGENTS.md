# AGENTS.md

Guidance for AI coding agents working in this repository. A human contributor
should read [`CONTRIBUTING.md`](CONTRIBUTING.md) first; this file adds the
constraints that exist because an agent fails differently from a person.

Everything here is enforced by CI where enforcement is possible. Where it is
not, it is a rule you are expected to follow rather than a suggestion.

## Development home

This is the public canonical development repository. Current software work,
issues, pull requests, CI and releases belong here. Work on a branch, open a
pull request, wait for the configured required checks, and merge through that
pull request; direct pushes to the default branch are rejected.

`PUBLIC_SNAPSHOT_MANIFEST.json` and `docs/history/` preserve the one-time
migration provenance. They are historical records, not instructions to import
from, publish from or synchronize with another repository. Do not add a second
development path or a recurring cross-repository publication workflow.

## Authorship

Do not attribute a commit to an AI assistant. No `Co-Authored-By` trailer naming
a model, no "generated with" line, and no model name in the author or committer
identity. Authorship stays with the person who submitted the work.

This is checked by `.github/scripts/check_commits.py`, which reads trailers,
identity fields and generation lines over a commit range. The check exists
because the rule was stated in prose for some time before anything verified it,
and a documented rule with no enforcement is a rule that drifts.

## The content boundary

This repository publishes runnable code and no quantitative research claims.
`.github/scripts/check_content_boundary.py` enforces that over every tracked
file, along with two other rules: no personal path or credential-shaped string,
and every relative link resolving to a tracked path.

Three things about this check are load-bearing:

- **A clean run is not evidence that the boundary holds.** It means the boundary
  holds *or* the checker is blind to what you added. Those are different, and the
  second has happened repeatedly.
- **It rejects some things it should not, and the list of exclusions is part of
  the design.** If it flags a sentence that is legitimate, widen the exclusion
  with a comment naming the real sentence that motivated it. Do not disable a
  pattern, and do not reach for the fixture marker to silence a finding in
  ordinary content.
- **The fixture marker is not a general opt-out.** It exists so that this
  checker's own tests can contain the strings it rejects. It applies per line and
  is visible in review of that line. A directory-wide exemption was refused
  because a genuine leak could then be parked in a test file.

If your change needs to quote a prohibited phrase as an example — describing a
defect in the checker, say — describe the form instead of reproducing it.
`CONTRIBUTING.md` explains this and names the two commits that predate the rule.

## Determinism

Stable identities, fixed tie-breaking and reproducible ordering are contracts.
A change that makes identical inputs produce different identities or a different
result ordering is a breaking change even when the new behaviour looks
equivalent. Configuration hashes are computed over the normalized configuration,
so reformatting a config file is not a cosmetic change.

Randomized algorithms take an explicit seed; deterministic ones must not. A
solver that ran out of time yields an incumbent, never a reference optimum.

## Orientation

Before deciding what "the recent changes" are, enumerate the work:

```console
git branch -a
git worktree list
```

Development here has run on several branches and in a separate worktree at the
same time. A review that reads only the checked-out branch can be a complete,
confident review of the wrong commits, and nothing in the diff will say so. Two
commands settle it.

`LICENSE_MANIFEST.json` is a single-line JSON document, so a diff of it prints
the whole file twice and `head` cannot trim one line. Read it with `--stat` and
compare the specific fields that matter.

## Verification before you claim something works

Run the suite and the checks, and report what they actually said:

```console
python -m unittest discover -s tests -v
python .github/scripts/check_content_boundary.py --claim-mode no_quantitative_claims
python .github/scripts/build_license_manifest.py --check
python -m mypy
```

Two ordering facts will otherwise waste your time. `build_license_manifest.py`
reads the git *index*, so stage your changes first, then regenerate, then stage
the manifest. And reading a file and writing it back through a script can change
its line endings on a Windows checkout, which makes an unchanged file look
modified — restore such a file with git rather than by rewriting the original
text.

A clean mypy run is narrower than it looks; `CONTRIBUTING.md` says which modules
are exempt and what that means for a change landing in one of them.

A statement about the environment is not an environment fact. A plan or a
handover note saying a tool is missing is a claim from another session, and
editing a document to agree with it is a change you will have to make twice if
the claim is stale. Run the version command first; it costs one call.

## Reviewing your own work

This is the section most specific to agents, and it exists because of a
measured pattern rather than a principle.

Defects in this repository have concentrated almost entirely in one class:
**the documented rule and the code meant to enforce it disagree.** Not logic
errors — specification-versus-implementation gaps. On more than one occasion a
comment contradicted the code directly beneath it. On more than one occasion a
fix for a review finding introduced a fresh instance of the same class it was
fixing, because the fix was designed from the same mental model as the defect.

Two consequences follow, and neither is a judgement call:

1. **After fixing review findings, get an independent pass before merging.** Your
   own assessment that a fix is correct is not sufficient evidence, and the
   fix-introduces-the-same-defect pattern is exactly what an independent reader
   catches and you do not.

2. **Any change that pairs a documented rule with enforcing code needs that pass
   too.** This is where the gaps concentrate.

Conduct such a review by **reverse verification**: take each normative statement
in the document, construct an input the statement says must be rejected, *run
it*, and report whether the rule was actually enforced. Deriving test cases by
reading the implementation and asking what the code does is the failure mode
that let these through — the cases have to come from the declaration.

Two related traps:

- **Tests you designed yourself cannot probe your own blind spots.** Every case
  you invent falls inside the model that produced the code. A suite passing tells
  you the cases it contains are covered, nothing more.
- **A test that asserts a word appears in a document does not test the
  document's claim.** Prose containing the right vocabulary can still state the
  opposite of the truth. Assert the fact the sentence depends on: run the
  behaviour, or extract the stated figure and compare it to a measured one.

## Scope discipline

Larger changes — a new algorithm, a new instance family, a new output schema —
need discussion before implementation. They interact with the reproducibility
contracts, and a change that looks local can invalidate stored run identities.

Keep a change focused. Do not reformat unrelated code, and do not remove a type
exemption in the same commit as a behavioural change; the two cannot be reviewed
apart.
