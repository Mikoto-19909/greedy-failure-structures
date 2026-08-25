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

# Text is decided by content, not by filename. A suffix allow-list silently
# skips .env, Dockerfile, Makefile and .sh, so a credential placed in one of
# those would pass while the workflow reported that the boundary held.
BINARY_SUFFIXES = frozenset(
    {
        ".bmp", ".bz2", ".class", ".dll", ".exe", ".gif", ".gz", ".ico", ".jar",
        ".jpeg", ".jpg", ".mo", ".mp3", ".mp4", ".o", ".ods", ".odt", ".pdf",
        ".png", ".pyc", ".pyd", ".pyo", ".so", ".svgz", ".tar", ".ttf", ".webp",
        ".woff", ".woff2", ".xz", ".zip", ".zst",
    }
)
MAX_TEXT_BYTES = 4 * 1024 * 1024

# Prose is where a research claim can be asserted in words. Credential and
# personal-path checks are not limited to these: they run over all text.
PROSE_SUFFIXES = frozenset({".md", ".rst", ".txt"})

# A result claim states a research metric with a number, or pairs an outcome
# verb with one. Bare numbers stay legal: versions, seeds, sizes, worker counts
# and timeouts are ordinary content, and a checker that flags those becomes
# noise that gets ignored.
_METRIC = (
    r"failure\s+rate|optimality\s+gap|recovery\s+rate|node\s+reduction|"
    r"runtime\s+ratio|coverage|runtime|speedup|deficit|objective|gap"
)
_OUTCOME = (
    r"failed|succeeded|lost|gained|recovered|averaged|achieved|reached|"
    r"outperformed|beat|exceeded|covered|solved|explored|improved|degraded"
)
QUANTITATIVE = (
    # "the failure rate was 25%", "coverage of 19"
    re.compile(
        rf"\b(?:{_METRIC})\b[^.\n]{{0,20}}?\b(?:was|were|is|are|of)\b"
        rf"[^.\n]{{0,12}}?\d",
        re.IGNORECASE,
    ),
    # "mean gap: 0.24", "speedup = 3.2"
    re.compile(rf"\b(?:{_METRIC})\s*[:=]\s*\d", re.IGNORECASE),
    # "greedy covered 80%", "local search recovered 82"
    re.compile(
        rf"\b(?:{_OUTCOME})\b[^.\n]{{0,40}}?\b\d+(?:\.\d+)?\s*%?",
        re.IGNORECASE,
    ),
    # "45% of instances", "80% of elements"
    re.compile(
        r"\b\d+(?:\.\d+)?\s*%[^.\n]{0,40}?"
        r"\b(?:instances?|runs?|cases?|elements?|sets?)\b",
        re.IGNORECASE,
    ),
    # "12.5% coverage", "3 seconds runtime"
    re.compile(
        rf"\b\d+(?:\.\d+)?\s*%?\s+(?:\w+\s+){{0,2}}?(?:{_METRIC})\b",
        re.IGNORECASE,
    ),
)

# Credential and personal-path detection.
#
# These patterns were derived from an adversarial review that found ten missed
# credential formats in a six-pattern predecessor. Two lessons are encoded here.
#
# First, a hand-written pattern list cannot claim to detect "credential-shaped
# strings" in general. It detects the formats listed below and nothing else, and
# the documentation says so rather than implying completeness.
#
# Second, secret assignments in .env, shell and YAML files are usually unquoted,
# so requiring quotes — as the predecessor did — missed the common case in
# exactly the file types the content-based scan was added to cover.
# An environment-style key may carry a prefix, as in AZURE_CLIENT_SECRET, where
# a  before the keyword does not hold because the preceding character is an
# underscore. So the prefix is matched explicitly instead.
_SECRET_KEYWORD = (
    r"password|passwd|pwd|secret|token|credential|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|auth[_-]?token|client[_-]?secret|pat"
)
_SECRET_KEY = rf"(?:^|[^A-Za-z0-9])(?:[A-Za-z0-9]+_)*(?:{_SECRET_KEYWORD})"
# A value long enough to be a real secret, not a placeholder like None or "".
_SECRET_VALUE = r"[^\s\"'#]{8,}"

SENSITIVE = (
    # Windows drive paths, both separators. The backslash form is the likeliest
    # leak in a Windows-developed repository and was the one originally missed.
    (
        "personal path",
        re.compile(
            r"[A-Za-z]:[\\/]Users[\\/](?![Pp]ublic[\\/])[^\\/\s\"']+",
            re.IGNORECASE,
        ),
    ),
    # UNC and extended-length prefixes: a double-backslash host share whose
    # first component under it is the users directory, and the \\?\ form.
    # Written descriptively rather than as a literal example, since a literal
    # would match this file's own pattern.
    (
        "personal path",
        re.compile(r"\\\\[^\\\s\"']+\\Users\\[^\\/\s\"']+", re.IGNORECASE),
    ),
    # POSIX home directories, including the WSL mount of a Windows drive.
    (
        "personal path",
        re.compile(r"(?:/mnt/[a-z])?/(?:home|Users)/[^/\s\"']+"),
    ),
    # Private key material in any case, plus the PuTTY key format.
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)),
    ("private key", re.compile(r"\bPuTTY-User-Key-File-\d+\s*:", re.IGNORECASE)),
    # Provider tokens with distinctive prefixes.
    ("token", re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}")),
    ("token", re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}")),
    ("token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{16,}")),
    ("token", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}")),
    ("token", re.compile(r"\bnpm_[A-Za-z0-9]{30,}")),
    ("token", re.compile(r"\bAIza[A-Za-z0-9_-]{30,}")),
    ("token", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}")),
    # AWS long-term (AKIA) and temporary (ASIA) access key IDs.
    ("aws key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    # Credentials embedded in a URL's userinfo component.
    (
        "url credential",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@\"']+:[^\s:/@\"']+@", re.IGNORECASE),
    ),
    # Secret assignments, quoted or bare.
    (
        "secret assignment",
        re.compile(
            rf"{_SECRET_KEY}\s*[:=]\s*[\"']{_SECRET_VALUE}[\"']",
            re.IGNORECASE,
        ),
    ),
    (
        "secret assignment",
        re.compile(
            rf"{_SECRET_KEY}\s*[:=]\s*{_SECRET_VALUE}\s*$",
            re.IGNORECASE,
        ),
    ),
)

MD_LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")
EXTERNAL = re.compile(r"\A(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def read_text_if_text(path: Path) -> tuple[str | None, str | None]:
    """Return decoded text, or a reason it is not text to scan.

    Content decides, not the filename: a NUL byte or a UTF-8 decoding failure
    means binary. Only unambiguously binary suffixes are skipped without
    reading, so .env, Dockerfile, Makefile and .sh are all scanned.
    """

    if path.suffix.casefold() in BINARY_SUFFIXES:
        return None, None
    try:
        payload = path.read_bytes()
    except OSError as error:
        return None, f"cannot be read ({error.strerror})"
    if len(payload) > MAX_TEXT_BYTES:
        return None, "exceeds the text size limit and was not scanned"
    if b"\0" in payload:
        return None, None
    try:
        return payload.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "is not valid UTF-8 and could not be scanned"


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
    skipped_binary = 0
    for name in names:
        text, problem = read_text_if_text(root / name)
        if problem is not None:
            findings.append(f"{name}: {problem}")
            continue
        if text is None:
            skipped_binary += 1
            continue
        scanned += 1
        findings += check_quantitative(name, text, args.claim_mode)
        findings += check_sensitive(name, text)
        findings += check_links(root, name, text, known)

    sys.stdout.write(f"claim mode    : {args.claim_mode}\n")
    sys.stdout.write(f"tracked files : {len(names)}\n")
    sys.stdout.write(f"text scanned  : {scanned}\n")
    sys.stdout.write(f"binary skipped: {skipped_binary}\n")
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
