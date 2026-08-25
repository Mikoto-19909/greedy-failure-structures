# Pre-public development history

This repository begins at a single root commit. The development that preceded
it happened in a private repository whose Git history, pull requests, Actions
runs and releases were deliberately not migrated. This file records what that
period consisted of, at a level that can be checked against the private
history rather than asserted.

Every entry below was verified against the private repository before being
written here. Entries that could not be verified were removed rather than
softened.

## Milestones

**Project start — July 2026.** Development began in a private repository with
an interface-and-contract-first approach: immutable data model, algorithm and
generator registries, and typed record schemas were fixed before behaviour was
added.

**Staged capability build-out.** Work proceeded as a sequence of closed phases
covering algorithms, instance generation, execution and reproducibility,
statistics, and reporting. Each phase had its own acceptance criteria and was
closed only after its tests and documentation were complete.

**Frozen experiment corpus and private release — August 2026.** A fixed
experiment corpus was frozen and a private release was tagged, with output
identities and checksums verified by an independent validator. That release
belongs to the private repository and is not referenced by version here.

**Audited migration to this repository — August 2026.** Contents were exported
from one exact source commit under an approved, hash-pinned classification
policy, then established here as a single root commit. No Git history, branch,
tag, pull request, Actions run or release was copied.

## What this repository is, and is not

This is a **code-first** snapshot: runnable algorithms, generators, benchmark
execution, reporting and replay, together with their tests and configurations.

It deliberately contains **no quantitative research claims**. The frozen
experiment results, the technical report, the charts and the paper materials
are not part of this snapshot. Any future publication of those will be a
separate release carrying its own complete evidence chain, from typed CSV
through manifest and validator to the reported statement.

Consequently, nothing in this repository should be read as a finding about
algorithm performance. The bundled starter workflow is a functional check, not
a measurement.

## Verifying the migration

[`CANONICAL_MIGRATION_RECEIPT.json`](CANONICAL_MIGRATION_RECEIPT.json) records
the exact identities involved: the legacy source commit, the approved
migration policy digest, the public manifest and payload tree digests, and this
repository's root commit and tree.

`PUBLIC_SNAPSHOT_MANIFEST.json` in the repository root is the closed
allow-list: a file is part of this snapshot, and carries a license grant, only
if it appears there with its exact path, byte count, digest and license
identifier.
