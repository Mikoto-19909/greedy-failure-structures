# License mapping

This repository uses a default-deny content rule. A file is covered only when it
appears in [`LICENSE_MANIFEST.json`](../LICENSE_MANIFEST.json), which records its
exact path, payload identity and license identifier, and which is regenerated
whenever the tracked file set changes. CI verifies it matches the working tree,
so a file added without being listed fails the build rather than shipping
unlicensed.

- Entries marked `MIT` are licensed under the root [`LICENSE`](../LICENSE).
- Entries marked `CC-BY-4.0` are licensed under
  [`CONTENT-CC-BY.txt`](CONTENT-CC-BY.txt).

The manifest licenses its own canonical bytes under the identifier in its
`manifest_license` field. It is not placed in its own file array, because its
digest would then have to be computed over bytes already containing that digest.

Files absent from `LICENSE_MANIFEST.json` are not part of this repository's
license grant, and this mapping makes no grant for them.

## The rule in prose

For orientation — the manifest is authoritative, this paragraph is not: code and
machine-readable inputs are MIT, while prose is CC BY 4.0. Experiment
configurations under `configs/` are MIT rather than CC BY, because they are run
inputs rather than documents, and the package reads one of them to run at all.

## Two manifests, two purposes

[`PUBLIC_SNAPSHOT_MANIFEST.json`](../PUBLIC_SNAPSHOT_MANIFEST.json) is a
**migration archive**, not a license authority. It records the single export that
created this repository — the legacy source commit, the approved policy digest
and the payload identities at that moment — and those values stay fixed, because
rewriting them later would destroy the provenance they exist to preserve.

`LICENSE_MANIFEST.json` is the **live allow-list** described above. Keeping them
separate is deliberate: an archive of a past export cannot cover files added
afterwards, so using it as the license authority would let the grant lapse
silently every time the repository gained a file.
