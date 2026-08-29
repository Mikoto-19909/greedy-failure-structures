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
tracked file set changes, and CI verifies it matches the tracked content
recorded in git's index.

That last distinction is deliberate and is not a synonym for the working tree.
Every path, mode and payload in this manifest is read from the index, never from
the files on disk; ``blob_bytes`` explains why. An uncommitted working-tree edit
therefore does not move the manifest, and ``--check`` does not claim it does.

Conflating the two manifests is what made the license grant lapse: the migration
archive could not cover files added after the migration, yet the license mapping
named it as the authority.

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
from typing import NamedTuple

MANIFEST_NAME = "LICENSE_MANIFEST.json"
MIGRATION_MANIFEST_NAME = "PUBLIC_SNAPSHOT_MANIFEST.json"

# Schema 2 adds ``git_mode`` to every file entry. Schema 1 bound identity to
# path, byte count and digest only, which left two mode-only substitutions
# invisible: adding the executable bit, and turning a regular file into a
# symlink whose target text equals the old contents. A manifest that claims to
# record payload identity has to record the mode that decides how the payload is
# interpreted.
SCHEMA_VERSION = 2

# Non-code content is CC BY 4.0; code and machine-readable inputs are MIT. This
# mirrors LICENSES/README.md, which is the human-readable statement of the same
# rule. Experiment configurations are MIT: they are run inputs, not prose, and
# cli.py reads one of them to run at all.
CONTENT_SUFFIXES = frozenset({".md", ".rst", ".txt"})

# Bundled third-party fonts are OFL-1.1, not MIT: the suffix rule would attach
# this repository's MIT grant and copyright line to IBM's and the Space Grotesk
# authors' work. The OFL text file carries the same identifier, the way
# CONTENT-CC-BY.txt carries CC-BY-4.0. Per-font copyright notices live in
# LICENSES/README.md next to the mapping prose.
FONT_LICENSE = "OFL-1.1"
FONT_DIR = "src/maxcover/dashboard_ui/fonts"
OFL_TEXT_PATH = "LICENSES/OFL-1.1.txt"

ATTRIBUTIONS = {
    "CC-BY-4.0": "Copyright (c) 2026 Liang Dao. Licensed under CC BY 4.0.",
    "MIT": "Copyright (c) 2026 Liang Dao. Licensed under the MIT License.",
    "OFL-1.1": (
        "Bundled font software under the SIL Open Font License 1.1 "
        "(LICENSES/OFL-1.1.txt); per-font copyright notices in LICENSES/README.md."
    ),
}

REGULAR_MODE = "100644"
EXECUTABLE_MODE = "100755"

# Which index modes may carry a license grant.
#
# Regular and executable files are both real payload: the executable bit is a
# legitimate property of a script, and refusing it would reject a valid future
# contribution for no licensing reason. Both are therefore accepted and the mode
# is recorded, so 100644 -> 100755 is an identity change that --check reports.
#
# Symlinks (120000) and gitlinks (160000) are rejected outright rather than
# merely recorded, because recording is the weaker guarantee. --check only
# proves the manifest agrees with the index; anyone who changes the index and
# regenerates gets a manifest that agrees again. A hard rejection at build time
# is an invariant instead: no manifest can ever be produced over these modes.
# That matters most for the symlink case, where the substitution preserves the
# blob exactly — a file whose contents are "../../../etc/passwd" becomes a link
# to /etc/passwd with the same digest and byte count. It is also the honest
# answer for both modes on their own terms: a symlink's blob is a pointer rather
# than the content it resolves to, and a gitlink names a commit in another
# repository whose bytes this repository does not hold. Licensing either would
# be a grant over content the manifest cannot identify.
LICENSABLE_MODES = frozenset({REGULAR_MODE, EXECUTABLE_MODE})

MODE_REJECTIONS = {
    "120000": "symlink; its blob is a link target, not licensable content",
    "160000": "gitlink; the submodule's bytes live in another repository",
}


class ManifestError(Exception):
    """An operational failure that should exit 1 with a message, not a stack."""


class IndexEntry(NamedTuple):
    """One staged path: the mode and blob git will record for it on commit."""

    path: str
    mode: str
    oid: str


def license_for(path: str) -> str:
    posix = PurePosixPath(path)
    if posix.as_posix() == OFL_TEXT_PATH:
        return FONT_LICENSE
    if (
        posix.parent.as_posix() == FONT_DIR
        and posix.suffix.casefold() == ".woff2"
    ):
        return FONT_LICENSE
    return (
        "CC-BY-4.0"
        if posix.suffix.casefold() in CONTENT_SUFFIXES
        else "MIT"
    )


def tracked_entries(root: Path) -> list[IndexEntry]:
    """List the index: path, mode and blob id together, from one git call.

    ``git ls-files --stage`` is the only source used here. Taking the path set
    from one git command and the payload from another (``HEAD:`` used to supply
    the payload) split the manifest across two different trees: a newly staged
    file was listed but had no HEAD blob, so a rebuild crashed, and a staged
    edit was listed with the previously committed bytes. One call, one tree.
    """

    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        capture_output=True,
        check=True,
    ).stdout

    entries: list[IndexEntry] = []
    for record in out.decode("utf-8").split("\0"):
        if not record:
            continue
        # "<mode> SP <oid> SP <stage>TAB<path>"; the path is last and unquoted
        # under -z, so a tab or a non-ASCII byte in it stays intact.
        meta, _, path = record.partition("\t")
        if not path:
            raise ManifestError(f"cannot parse git index record: {record!r}")
        fields = meta.split(" ")
        if len(fields) != 3:
            raise ManifestError(f"cannot parse git index record: {record!r}")
        mode, oid, stage = fields
        if stage != "0":
            raise ManifestError(
                f"{path}: unmerged index entry (stage {stage}); "
                "resolve the conflict before building the manifest"
            )
        entries.append(IndexEntry(path=path, mode=mode, oid=oid))

    entries.sort(key=lambda entry: entry.path)
    return entries


def blob_bytes(root: Path, oids: list[str]) -> dict[str, bytes]:
    """Read staged blobs by object id, never the working-tree files.

    These differ wherever .gitattributes normalizes line endings: a Windows
    checkout holds CRLF while the stored blob holds LF. Hashing the working
    tree would make the manifest platform-dependent, so it would pass locally
    and fail on a Linux runner. The blob is the repository's canonical content,
    so it is what the license identity must be bound to.

    Object ids come from ``git ls-files --stage``, so the lookup never puts a
    path on a git command line and non-ASCII or otherwise awkward path names
    cannot be misread.
    """

    if not oids:
        return {}

    out = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input=("\n".join(oids) + "\n").encode("ascii"),
        capture_output=True,
        check=True,
    ).stdout

    payloads: dict[str, bytes] = {}
    pos = 0
    for oid in oids:
        end = out.find(b"\n", pos)
        if end < 0:
            raise ManifestError(f"git cat-file gave no header for {oid}")
        fields = out[pos:end].decode("utf-8", "replace").split(" ")
        if len(fields) != 3 or fields[1] != "blob":
            raise ManifestError(
                f"git cat-file did not return a blob for {oid}: {' '.join(fields)}"
            )
        size = int(fields[2])
        start = end + 1
        payloads[oid] = out[start : start + size]
        pos = start + size + 1  # git appends a newline after the payload
    return payloads


def build(root: Path) -> bytes:
    """Build the manifest over every staged file except the manifest itself.

    The manifest cannot list itself: its digest would have to be computed over
    bytes that already contain that digest. Its own license is stated in
    ``manifest_license`` instead, which is the same approach the migration
    manifest takes.
    """

    tracked = [
        entry for entry in tracked_entries(root) if entry.path != MANIFEST_NAME
    ]

    rejected = [entry for entry in tracked if entry.mode not in LICENSABLE_MODES]
    if rejected:
        lines = [
            f"  {entry.path}: mode {entry.mode} — "
            + MODE_REJECTIONS.get(entry.mode, "unsupported index mode")
            for entry in rejected
        ]
        raise ManifestError(
            "these tracked paths cannot carry a license grant:\n" + "\n".join(lines)
        )

    payloads = blob_bytes(root, [entry.oid for entry in tracked])

    entries = []
    for entry in tracked:
        payload = payloads[entry.oid]
        entries.append(
            {
                "bytes": len(payload),
                "git_mode": entry.mode,
                "license": license_for(entry.path),
                "path": entry.path,
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


def _describe_change(committed: dict, current: dict) -> str:
    """Name the fields that moved, so a mode-only change is not silently 'identity'."""

    fields = sorted(set(committed) | set(current))
    changed = [
        f"{field} {committed.get(field)!r} -> {current.get(field)!r}"
        for field in fields
        if committed.get(field) != current.get(field)
    ]
    return ", ".join(changed) if changed else "entry differs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "verify the committed manifest matches the paths, modes and blobs "
            "in git's index; write nothing"
        ),
    )
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    try:
        expected = build(root)
    except ManifestError as error:
        sys.stderr.write(f"{error}\n")
        return 1
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
            f"{MANIFEST_NAME} matches the git index "
            f"({manifest['file_count']} files)\n"
        )
        return 0

    sys.stderr.write(f"{MANIFEST_NAME} does not match the git index.\n")
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
    file_entries_agree = set(committed) == set(current) and all(
        committed[path] == current[path] for path in committed
    )
    for path in sorted(set(committed) & set(current)):
        if committed[path] != current[path]:
            sys.stderr.write(
                f"  identity changed: {path}"
                f" ({_describe_change(committed[path], current[path])})\n"
            )
    # A manifest-level field can move without any file entry moving, so say so
    # rather than printing nothing and still exiting 1.
    if file_entries_agree:
        sys.stderr.write("  the manifest's own fields differ from the rules\n")
    sys.stderr.write(
        f"\nRegenerate it: python .github/scripts/build_license_manifest.py\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
