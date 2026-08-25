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

# No suffix list decides what gets scanned. An allow-list skipped .env,
# Dockerfile and .sh; replacing it with a deny-list was the same mistake in
# reverse, since either can be defeated by choosing a filename. Binary is now
# judged from content in read_text_if_text.
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
# a word boundary before the keyword does not hold because the preceding
# character is an underscore. So the prefix is matched explicitly instead.
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


# A test fixture for this checker must contain the exact strings the checker
# rejects, so scanning them would make the boundary permanently fail. Blanket
# directory exemptions were rejected: exempting tests/ wholesale would open a
# real bypass, since a genuine leak could then be parked in a test file.
#
# Instead each line opts out explicitly and visibly. The marker has to be on the
# same line as the fixture, so an exemption is always adjacent to what it
# exempts and shows up in review of that line.
FIXTURE_MARKER = "boundary-fixture"


def _is_exempt(line: str) -> bool:
    """True when this line declares itself a fixture for this checker."""

    return FIXTURE_MARKER in line


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def read_text_if_text(path: Path) -> tuple[str | None, str | None]:
    """Return decoded text, or a reason it could not be scanned.

    Content decides, never the filename. A suffix list — whether it named the
    files to scan or the files to skip — could always be defeated by choosing a
    name, which is the opposite of what this check is for. So every tracked file
    is read and classified by what is in it.

    Three outcomes, and the difference between the last two matters:

    - ``(text, None)`` — scan it.
    - ``(None, None)`` — genuinely binary; skipped and counted, no finding. A
      real PNG must not become noise.
    - ``(None, reason)`` — a finding. Something was tracked that could not be
      examined, so the boundary is unverified for it rather than clean.

    A NUL byte previously produced the second outcome, which let any file,
    including a Markdown one, disappear from the report entirely. Now a NUL byte
    only means binary when the rest of the content agrees; a file that is
    otherwise valid UTF-8 text is reported instead of silently dropped.
    """

    try:
        payload = path.read_bytes()
    except OSError as error:
        return None, f"cannot be read ({error.strerror})"
    if not payload:
        return "", None
    if len(payload) > MAX_TEXT_BYTES:
        return None, "exceeds the text size limit and was not scanned"

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        # Not UTF-8. If it looks like a known binary format, skip it quietly;
        # otherwise say so, because an unreadable tracked file is unverified.
        if _looks_binary(payload):
            return None, None
        return None, "is not valid UTF-8 and could not be scanned"

    if "\0" not in text:
        return text, None

    # Valid UTF-8 containing NUL. A real binary can decode as UTF-8 by accident,
    # so decide by how much of it is unprintable rather than by the NUL alone.
    if _looks_binary(payload):
        return None, None
    return None, "contains NUL bytes in otherwise textual content"


def _looks_binary(payload: bytes) -> bool:
    """Judge binary by the share of bytes that no text format would carry.

    Deliberately not a suffix check. Control characters outside tab, newline and
    carriage return are the signal; a text file holding a stray NUL stays text,
    while a compiled object or image crosses the threshold immediately.
    """

    sample = payload[:8192]
    if not sample:
        return False
    textual = bytes(range(32, 127)) + bytes([9, 10, 13, 27])
    unprintable = sum(1 for byte in sample if byte not in textual and byte < 128)
    return unprintable / len(sample) > 0.05


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
        if _is_exempt(line):
            continue
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
        if _is_exempt(line):
            continue
        for label, pattern in SENSITIVE:
            if pattern.search(line):
                findings.append(f"{path}:{index}: {label} must not be published")
    return findings


def check_links(root: Path, path: str, text: str, known: set[str]) -> list[str]:
    if PurePosixPath(path).suffix.casefold() != ".md":
        return []
    findings = []
    for index, line in enumerate(text.splitlines(), start=1):
        if _is_exempt(line):
            continue
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
