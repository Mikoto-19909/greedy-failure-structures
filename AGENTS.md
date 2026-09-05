# Agent guidance

Follow [`CONTRIBUTING.md`](CONTRIBUTING.md) for the shared development,
correctness, evidence, verification, authorship and licensing requirements.
Those rules and the additional requirements below apply whether or not CI can
enforce them.

## Establish the current state

Before deciding what the recent changes are, inspect all branches and
worktrees:

```console
git branch -a
git worktree list
```

Identify the relevant work before choosing a diff or applying a plan. Verify
environment claims with the tool's version command; do not rewrite documentation
to match an unverified statement from a prior session.

`LICENSE_MANIFEST.json` is single-line JSON. Use diff statistics and compare the
relevant parsed fields instead of printing the whole file. Follow the
index-first regeneration order in CONTRIBUTING.

On Windows, reading and rewriting a file can change its line endings. Restore
an otherwise unchanged file with Git rather than rewriting its original text;
preserve existing user changes when identifying what can be restored.

## Independent review

Obtain an independent review before merging either of these changes:

- A fix for review findings.
- A change that pairs a documented rule with code that enforces it.

Use reverse verification: for each normative statement, construct an input
that the statement says must be rejected, run it, and report whether the rule
was enforced. Derive the cases from the declaration, not from the enforcing
implementation. Your own assessment or tests do not replace the independent
pass.

Assertions must check the fact behind a sentence: run the behavior, or compare
the stated value with a measurement. A wording check alone cannot establish a
documented rule.

## Execution and scope

Work toward the agreed task and its acceptance conditions. Keep changes focused,
record adjacent issues without expanding the task, and stop adding work once
the requested acceptance conditions are met. Follow existing authorization when
resolving routine implementation choices; discuss larger changes as required
by CONTRIBUTING when they are outside the agreed scope.

Before claiming a change works, complete the applicable verification in
CONTRIBUTING. Report exactly what was run, including failures, skips and omitted
local checks. Apply explicit task-specific test selection without disabling
required CI or claiming broader verification than the evidence supports. Keep
type fixes, mechanical moves and exemption removal separate as CONTRIBUTING
requires.
