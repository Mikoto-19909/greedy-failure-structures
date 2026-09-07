"""Select docs only for a complete PR diff containing allowed plan documents."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import json


_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_HEADER = re.compile(
    rb":([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40}|[0-9a-f]{64}) "
    rb"([0-9a-f]{40}|[0-9a-f]{64}) ([A-Z])\Z"
)
_REGULAR_MODES = {b"100644", b"100755"}


def _allowed_document(path: str) -> bool:
    parts = path.split("/")
    return (path.endswith(".md") and all(part not in {"", ".", ".."} for part in parts)
            and (len(parts) == 1 or parts[0] in {"docs", "analysis"}))


def classify_diff(raw: bytes) -> str:
    """Read complete NUL-delimited --raw --no-renames output conservatively."""
    if not raw or not raw.endswith(b"\0"):
        return "full"
    fields = raw[:-1].split(b"\0")
    if len(fields) % 2:
        return "full"
    has_document = False
    for index in range(0, len(fields), 2):
        header = _HEADER.fullmatch(fields[index])
        if header is None or not fields[index + 1]:
            return "full"
        old_mode, new_mode, old_oid, new_oid, status = header.groups()
        if len(old_oid) != len(new_oid):
            return "full"
        old_missing = not old_oid.strip(b"0")
        new_missing = not new_oid.strip(b"0")
        if status == b"A":
            valid = old_mode == b"000000" and old_missing and new_mode in _REGULAR_MODES and not new_missing
        elif status == b"D":
            valid = new_mode == b"000000" and new_missing and old_mode in _REGULAR_MODES and not old_missing
        elif status == b"M":
            valid = old_mode == new_mode and old_mode in _REGULAR_MODES and not old_missing and not new_missing
        else:
            return "full"
        if not valid:
            return "full"
        try:
            path = fields[index + 1].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return "full"
        if _allowed_document(path):
            has_document = True
        else:
            return "full"
    return "docs" if has_document else "full"


def _git(repo: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "--no-pager", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    ).stdout


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None or not value.strip("0"):
        raise ValueError("missing or invalid commit SHA")
    return value


def _pr_diff(repo: Path, event: object) -> bytes:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ValueError("missing pull request")
    endpoints = []
    for endpoint in ("base", "head"):
        ref = pull_request.get(endpoint)
        if not isinstance(ref, dict):
            raise ValueError("missing pull request endpoint")
        commit = _sha(ref.get("sha"))
        verified = _git(repo, "rev-parse", "--verify", "--end-of-options", commit + "^{commit}").decode("ascii").strip()
        if verified != commit:
            raise ValueError("commit verification disagrees")
        endpoints.append(commit)
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("history is incomplete")
    common = _git(repo, "merge-base", "--all", *endpoints).decode("ascii").splitlines()
    if len(common) != 1:
        raise ValueError("common ancestor is not unique")
    ancestor = _sha(common[0])
    return _git(
        repo, "diff", "--raw", "--no-abbrev", "-z", "--no-renames",
        "--no-ext-diff", "--no-textconv", "--ignore-submodules=none",
        ancestor, endpoints[1], "--",
    )


def classify_event(event_name: str, event_path: Path | None, repo: Path) -> tuple[str, str]:
    if event_name != "pull_request":
        return "full", "event requires complete checks"
    if event_path is None:
        return "full", "pull request event is unavailable"
    try:
        event = json.loads(event_path.read_bytes())
        profile = classify_diff(_pr_diff(repo, event))
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return "full", "complete pull request diff is unavailable"
    reason = "description documents only" if profile == "docs" else "changes require complete checks"
    return profile, reason


def write_profile_output(profile: object, output_path: Path) -> str:
    """Only exact lowercase values may reach GitHub's case-insensitive consumer."""
    canonical = profile if type(profile) is str and profile in ("docs", "full") else "full"
    with output_path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"profile={canonical}\n")
    return canonical


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    profile, reason = classify_event(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        Path(event_path) if event_path else None,
        Path.cwd(),
    )
    destination = os.environ.get("GITHUB_OUTPUT")
    if not destination:
        print("CI classification output is unavailable", file=sys.stderr)
        return 1
    try:
        canonical = write_profile_output(profile, Path(destination))
    except OSError:
        print("CI classification output could not be written", file=sys.stderr)
        return 1
    print(f"CI profile: {canonical}; {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
