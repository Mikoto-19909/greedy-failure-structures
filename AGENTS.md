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

Report blocking findings or a justified pass as soon as the review checks
finish. Complete required review records before delivery; report formatting
must not hold up unrelated work.

## Execution and scope

Work through the authorized task and its acceptance conditions. Keep changes
focused, record adjacent issues without expanding the task, and stop adding work once
the requested acceptance conditions are met. Follow existing authorization when
resolving routine implementation choices; discuss larger changes as required
by CONTRIBUTING when they are outside the agreed scope.

Before claiming a change works, complete the applicable verification in
CONTRIBUTING. Report exactly what was run, including failures, skips and omitted
local checks. Apply explicit task-specific test selection without disabling
required CI or claiming broader verification than the evidence supports. Keep
type fixes, mechanical moves and exemption removal separate as CONTRIBUTING
requires.

## Long-running task efficiency

- At the start, briefly identify the necessary checks and the risk each covers.
  Add a check or verification tool only for an uncovered risk. Reuse existing
  tools instead of building duplicate ledgers or general verification frameworks.
- Freeze or reuse one old baseline for each compatibility boundary before
  changing it. Do not regenerate old expectations from the candidate to accept
  unexplained differences.
- Reuse successful evidence only when the relevant code, dependencies,
  configuration, inputs and environment have not changed in ways that could
  affect the result. An unchanged individual file alone does not establish reuse.
- Use focused local checks during development and consolidate final verification
  for each batch. Re-run checks for relevant changes, failures or unresolved
  risks. Keep required CI on the current PR revision; report local omissions and
  their actual coverage without repeating checks that prove the same fact.
- Use the smallest agreed set of live remote validation scenarios. Cover
  suitable boundaries with local counterexamples instead of continually adding
  remote probe revisions. Combine related documentation, manifest and PR
  description updates when their evidence is available to reduce small pushes.
- When subagent use is authorized, delegate only independent work. Keep one
  writer for shared files and one observer for each CI run. Reuse their results
  rather than having several agents repeat the same monitoring or review.
- Run long jobs asynchronously when supported. A session identifier is not a
  completion result: confirm the outcome and exit status before dependent work.
  Distinguish network and tool failures from test failures, and resume existing
  jobs instead of launching duplicates.
- Reuse valid authorization within its stated destination and scope. If an
  approval rejection requires additional authorization, explain the concrete
  missing destination or action in one request and continue unaffected work.
  Do not repeat unchanged requests or route around the rejection.
