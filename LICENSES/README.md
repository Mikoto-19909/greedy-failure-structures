# License mapping

This repository uses a default-deny content rule. A file is covered only when it
appears in [`LICENSE_MANIFEST.json`](../LICENSE_MANIFEST.json), which records its
exact path, file mode, payload identity and license identifier, and which is
regenerated whenever the tracked file set changes. CI verifies it matches the
tracked content recorded in git's index, so a file added without being listed
fails the build rather than shipping unlicensed.

The manifest is built from the index, not from the files on disk. That is
deliberate: `.gitattributes` normalizes line endings, so a Windows checkout holds
CRLF where the stored blob holds LF, and hashing the working tree would make the
recorded identities depend on the platform that generated them. The consequence
is worth stating plainly — an uncommitted working-tree edit does not change the
manifest and is not something `--check` detects; what it detects is any
difference between the manifest and what git has staged.

Only regular files (`100644`) and executable files (`100755`) can appear.
Symlinks and submodule gitlinks are refused at build time rather than recorded,
because their blob is a pointer rather than the content it names, so a license
grant over them would cover bytes the manifest cannot identify.

- Entries marked `MIT` are licensed under the root [`LICENSE`](../LICENSE).
- Entries marked `CC-BY-4.0` are licensed under
  [`CONTENT-CC-BY.txt`](CONTENT-CC-BY.txt).
- Entries marked `OFL-1.1` are licensed under
  [`OFL-1.1.txt`](OFL-1.1.txt).

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
Font files directly in `src/maxcover/dashboard_ui/fonts/` are OFL-1.1: they
are vendored third-party font software, not MIT-licensed contributions of
this repository, and the suffix rule would attach the wrong grant and
copyright line to them. The rule is scoped to that directory, not to the
`.woff2` suffix; a font file anywhere else stays MIT under the suffix rule.

The bundled fonts are:

- **IBM Plex Mono** (Regular 400, SemiBold 600), Copyright 2017 IBM Corp.
  All rights reserved., with Reserved Font Name "Plex".
- **Space Grotesk** (SemiBold 600, Bold 700), Copyright 2020 The Space
  Grotesk Project Authors (https://github.com/floriankarsten/space-grotesk).

Both are distributed under the SIL Open Font License 1.1
([`OFL-1.1.txt`](OFL-1.1.txt)), whose text carries the same identifier, the
way `CONTENT-CC-BY.txt` carries CC BY 4.0.

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
