"""Check this repository against its published content boundary.

Three things are verified over every tracked text file:

1. no quantitative research claim, under the active claim mode;
2. no personal path or credential-shaped string;
3. every relative Markdown link resolves.

Findings name a file and a line and describe the rule that failed. They never
echo the matched text, and the report never enumerates paths that are not
already public — this output is readable by anyone once the repository is
public, so it must not become an inventory of anything private.

The claim mode is an argument, not a constant: a future release that carries
evidence-backed results will run this with a wider mode rather than bypassing
the check.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

CLAIM_MODES = ("no_quantitative_claims", "evidence_backed_claims")

TEXT_SUFFIXES = frozenset(
    {".cff", ".cfg", ".json", ".md", ".ps1", ".py", ".toml", ".txt", ".yml", ".yaml"}
)
PROSE_SUFFIXES = frozenset({".md", ".txt"})

# A number joined to a coverage, gap, failure, speed or instance-count word is
# a result claim. Bare numbers are not: version strings, seeds, sizes and
# parameters are ordinary content.
# A result claim pairs an outcome word with a number, or a percentage with a
# corpus-size noun. Bare numbers stay legal: versions, seeds, sizes, worker
# counts and parameters are ordinary content, and a checker that flags those
# becomes noise that gets ignored.
QUANTITATIVE = (
    re.compile(
        r"\b(?:failed|succeeded|lost|gained|recovered|averaged|achieved|reached|"
        r"outperformed|beat|exceeded)\b[^.\n]{0,40}?\b\d+(?:\.\d+)?\s*%?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+(?:\.\d+)?\s*%[^.\n]{0,40}?\b(?:instances?|runs?|cases?)\b",
        re.IGNORECASE,
    ),
)

SENSITIVE = (
    ("personal path", re.compile(r"[A-Za-z]:[\/]Users[\/][^\/\s\"']+", re.IGNORECASE)),
    ("home path", re.compile(r"/(?:home|Users)/[^/\s\"']+/")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token", re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}")),
    ("aws key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("password assignment", re.compile(
        r"\b(?:password|passwd|secret|api[_-]?key)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']",
        re.IGNORECASE)),
)

MD_LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")
EXTERNAL = re.compile(r"\A(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def check_quantitative(path: str, text: str, claim_mode: str) -> list[str]:
    """Reject result claims in prose, unless the active mode authorizes them."""

    if claim_mode != "no_quantitative_claims":
        # A wider mode still needs its claims bound to a frozen evidence chain,
        # but that verification belongs to its own workflow, not to this check.
        return []
    if PurePosixPath(path).suffix.casefold() not in PROSE_SUFFIXES:
        return []
    findings = []
    for index, line in enumerate(text.splitlines(), start=1):
        for pattern in QUANTITATIVE:
            if pattern.search(line):
                findings.append(
                    f"{path}:{index}: reads as a quantitative result claim; "
                    "this repository publishes none"
                )
                break
    return findings


def check_sensitive(path: str, text: str) -> list[str]:
    findings = []
    for index, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SENSITIVE:
            if pattern.search(line):
                findings.append(f"{path}:{index}: {label} must not be published")
    return findings


def check_links(root: Path, path: str, text: str, known: set[str]) -> list[str]:
    if PurePosixPath(path).suffix.casefold() != ".md":
        return []
    findings = []
    for index, line in enumerate(text.splitlines(), start=1):
        for match in MD_LINK.finditer(line):
            target = match.group(1)
            if EXTERNAL.match(target):
                continue
            cleaned = target.split("#", 1)[0].split("?", 1)[0]
            if not cleaned:
                continue
            parts: list[str] = []
            escaped = False
            for part in (PurePosixPath(path).parent / cleaned).parts:
                if part == "..":
                    if not parts:
                        escaped = True
                        break
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            if escaped:
                findings.append(f"{path}:{index}: link escapes the repository")
                continue
            candidate = "/".join(parts)
            if candidate and candidate not in known and not (root / candidate).exists():
                findings.append(f"{path}:{index}: internal link does not resolve")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim-mode", required=True, choices=CLAIM_MODES)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    names = tracked_files(root)
    known = set(names)

    findings: list[str] = []
    scanned = 0
    for name in names:
        if PurePosixPath(name).suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(f"{name}: tracked text file is not readable UTF-8")
            continue
        scanned += 1
        findings += check_quantitative(name, text, args.claim_mode)
        findings += check_sensitive(name, text)
        findings += check_links(root, name, text, known)

    sys.stdout.write(f"claim mode    : {args.claim_mode}\n")
    sys.stdout.write(f"tracked files : {len(names)}\n")
    sys.stdout.write(f"text scanned  : {scanned}\n")
    sys.stdout.write(f"findings      : {len(findings)}\n")
    if findings:
        sys.stdout.write("\n")
        for item in findings:
            sys.stdout.write(f"  {item}\n")
        return 1
    sys.stdout.write("\nThe published content boundary holds.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
