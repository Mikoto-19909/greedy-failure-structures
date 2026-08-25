# License mapping

This public snapshot uses a default-deny content rule.  A payload file is
covered only when it appears in `PUBLIC_SNAPSHOT_MANIFEST.json`, which records
its exact path, payload identity, and license identifier.  The generated
manifest licenses its own canonical bytes under the identifier stored in its
`manifest_license` field; it is not placed in its own file array because that
would create a self-referential digest.

- Entries marked `MIT` are licensed under the root [`LICENSE`](../LICENSE).
- Entries marked `CC-BY-4.0` are licensed under
  [`CONTENT-CC-BY.txt`](CONTENT-CC-BY.txt).

Other files or materials absent from `PUBLIC_SNAPSHOT_MANIFEST.json` are not
part of this snapshot, and this mapping makes no license grant for them.
