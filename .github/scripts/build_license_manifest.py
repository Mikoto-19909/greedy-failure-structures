"""Generate the license manifest: the closed allow-list for this repository.

Two manifests exist here and they answer different questions.

``PUBLIC_SNAPSHOT_MANIFEST.json`` is a **migration archive**. It records the one
export that created this repository: the legacy source commit, the approved
policy digest, and the payload identities at that moment. Those values describe
a past event, so they never change — rewriting them on every later commit would
destroy the provenance they exist to preserve.

``LICENSE_MANIFEST.json`` is a **live allow-list**. It states which files are
part of this repository right now and under which license, so a default-deny
license rule has something current to point at. It is regenerated whenever the
tracked file set changes, and CI verifies it matches the working tree.

Conflating the two is what made the license grant lapse: the migration archive
could not cover files added after the migration, yet the license mapping named
it as the authority.

License assignment follows the published mapping in ``LICENSES/README.md``:
prose and license texts are CC BY 4.0, everything else is MIT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

MANIFEST_NAME = "LICENSE_MANIFEST.json"
MIGRATION_MANIFEST_NAME = "PUBLIC_SNAPSHOT_MANIFEST.json"
SCHEMA_VERSION = 1

# Non-code content is CC BY 4.0; code and machine-readable inputs are MIT. This
# mirrors LICENSES/README.md, which is the human-readable statement of the same
# rule. Experiment configurations are MIT: they are run inputs, not prose, and
# cli.py reads one of them to run at all.
CONTENT_SUFFIXES = frozenset({".md", ".rst", ".txt"})

ATTRIBUTIONS = {
    "CC-BY-4.0": "Copyright (c) 2026 Liang Dao. Licensed under CC BY 4.0.",
    "MIT": "Copyright (c) 2026 Liang Dao. Licensed under the MIT License.",
}


def license_for(path: str) -> str:
    return (
        "CC-BY-4.0"
        if PurePosixPath(path).suffix.casefold() in CONTENT_SUFFIXES
        else "MIT"
    )


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return sorted(name for name in out.decode("utf-8").split("\0") if name)


def build(root: Path) -> bytes:
    """Build the manifest over every tracked file except the manifest itself.

    The manifest cannot list itself: its digest would have to be computed over
    bytes that already contain that digest. Its own license is stated in
    ``manifest_license`` instead, which is the same approach the migration
    manifest takes.
    """

    entries = []
    for name in tracked_files(root):
        if name == MANIFEST_NAME:
            continue
        payload = (root / name).read_bytes()
        entries.append(
            {
                "bytes": len(payload),
                "license": license_for(name),
                "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    used = {entry["license"] for entry in entries} | {"CC-BY-4.0"}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "closed license allow-list for the current tracked tree",
        "migration_archive": MIGRATION_MANIFEST_NAME,
        "file_count": len(entries),
        "files": entries,
        "license_attributions": {k: ATTRIBUTIONS[k] for k in sorted(used)},
        "manifest_license": "CC-BY-4.0",
        "content_tree_sha256": hashlib.sha256(
            _canonical(entries)
        ).hexdigest(),
    }
    return _canonical(manifest)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed manifest matches the tracked tree; write nothing",
    )
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    expected = build(root)
    target = root / MANIFEST_NAME

    if not args.check:
        target.write_bytes(expected)
        manifest = json.loads(expected)
        sys.stdout.write(f"wrote {MANIFEST_NAME}\n")
        sys.stdout.write(f"files      : {manifest['file_count']}\n")
        counts: dict[str, int] = {}
        for entry in manifest["files"]:
            counts[entry["license"]] = counts.get(entry["license"], 0) + 1
        for name in sorted(counts):
            sys.stdout.write(f"  {name:12}: {counts[name]}\n")
        return 0

    # Check mode: the same builder produces the expectation, so the committed
    # manifest cannot drift from the rules without the check noticing.
    if not target.is_file():
        sys.stderr.write(f"{MANIFEST_NAME} is missing\n")
        return 1
    actual = target.read_bytes()
    if actual == expected:
        manifest = json.loads(actual)
        sys.stdout.write(
            f"{MANIFEST_NAME} matches the tracked tree "
            f"({manifest['file_count']} files)\n"
        )
        return 0

    sys.stderr.write(f"{MANIFEST_NAME} does not match the tracked tree.\n")
    try:
        committed = {e["path"]: e for e in json.loads(actual)["files"]}
    except (ValueError, KeyError, TypeError):
        sys.stderr.write("  the committed manifest is not readable\n")
        return 1
    current = {e["path"]: e for e in json.loads(expected)["files"]}
    for path in sorted(set(current) - set(committed)):
        sys.stderr.write(f"  not listed: {path}\n")
    for path in sorted(set(committed) - set(current)):
        sys.stderr.write(f"  listed but absent: {path}\n")
    for path in sorted(set(committed) & set(current)):
        if committed[path] != current[path]:
            sys.stderr.write(f"  identity changed: {path}\n")
    sys.stderr.write(
        f"\nRegenerate it: python .github/scripts/build_license_manifest.py\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
