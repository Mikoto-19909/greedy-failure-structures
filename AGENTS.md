# Agent guidance

Follow [CONTRIBUTING.md](CONTRIBUTING.md). Focus on the user's research task and
avoid general-purpose governance machinery, claim ledgers, manifests, checksum
gates, or tests that only enforce documentation wording.

Two scoped workflow requirements are intentional: analysis entry/helper ownership
registration tied to executable research verification, and remote Git readback
before reporting an explicitly requested evidence freeze as complete. See
[checks and evidence](docs/checks_and_evidence.zh-CN.md). These establish execution
and storage, not scientific correctness; they do not require manifests or file
checksum gates during exploratory analysis.

Before choosing a diff or applying a plan, inspect `git status --short`,
`git branch -a`, and `git worktree list`. Preserve unrelated work and verify tool
availability with the tool's version command.

Keep algorithm correctness, result identities, seeds, CSV inputs, and resume
behavior intact. Run the relevant existing tests during development and the
checks in CONTRIBUTING before merging. Report actual results and limitations.

Obtain an independent review before merging a fix for review findings or a
change that couples a documented behavior with its implementation. Have the
reviewer exercise the affected behavior, including a suitable invalid input;
no separate review ledger or hash record is required.

Keep one writer per shared file. Run long checks asynchronously when possible
and confirm their completion before relying on them. Stop when the requested
acceptance conditions are met.
