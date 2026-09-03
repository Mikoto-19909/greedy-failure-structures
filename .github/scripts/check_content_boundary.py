"""Check this repository against its published content boundary.

Three things are verified over every tracked text file:

1. quantitative research claims according to the active claim mode;
2. no personal path or credential-shaped string;
3. in every file GitHub renders as Markdown, every relative link resolves to
   a tracked path — inline, reference-style and HTML syntax alike.

Findings name a file and a line and describe the rule that failed. They never
echo the matched text, and the report never enumerates paths that are not
already public — this output is readable by anyone once the repository is
public, so it must not become an inventory of anything private.

The claim mode is an argument, not a constant. The active evidence-backed mode
permits quantitative prose while repository policy and review bind each claim
to its frozen evidence; the sensitive-content and link checks remain active.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

CLAIM_MODES = ("no_quantitative_claims", "evidence_backed_claims")

# No suffix list decides what gets scanned. An allow-list skipped .env,
# Dockerfile and .sh; replacing it with a deny-list was the same mistake in
# reverse, since either can be defeated by choosing a filename. Binary is now
# judged from content in read_text_if_text.
MAX_TEXT_BYTES = 4 * 1024 * 1024

# Prose is where a research claim can be asserted in words. Credential and
# personal-path checks are not limited to these: they run over all text.
PROSE_SUFFIXES = frozenset({".md", ".rst", ".txt"})

# Suffixes GitHub renders as Markdown. Link checking applies to these only: a
# `[x](y)` in a .txt file is literal text, so reporting its target would name a
# path no reader can click. The claim and credential checks are wider.
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown", ".mdown", ".mkdn"})

# A result claim states a research metric with a number, pairs an outcome verb
# with one, or expresses a ratio. Bare numbers stay legal: versions, seeds,
# sizes, worker counts, file counts and timeouts are ordinary content, and a
# checker that flags those becomes noise that gets ignored.
#
# The predecessor used a closed vocabulary and matched one line at a time. An
# adversarial review got roughly sixteen English rephrasings, every Chinese
# formulation, table rows and split sentences past it. Three things changed:
# the vocabulary widened, Chinese forms are matched directly rather than assumed
# absent, and matching runs over the joined paragraph because Markdown renders
# consecutive lines as one sentence.
_METRIC = (
    r"failure\s+rate|optimality\s+gap|approximation\s+ratio|recovery\s+rate|"
    r"node\s+reduction|runtime\s+ratio|wall[-\s]*clock(?:\s+time)?|elapsed\s+time|"
    r"coverage|runtime|speedup|regret|shortfall|deficit|objective|gap"
)
_OUTCOME = (
    r"failed|succeeded|lost|loses|gained|recovered|averaged|achieved|reached|"
    r"reaches|outperformed|beat|exceeded|covered|covers|solved|explored|visited|"
    r"improved|degraded"
)

# Exclusions run before the patterns. Each covers a construction that names a
# metric beside a number without asserting a measurement, and each exists
# because the pattern set flagged a real sentence from this repository.
#
# A definition says what a term means, not what was observed.
_DEFINITIONAL = re.compile(
    r"\bis\s+defined\s+as\b|\bmeans\b|\bwhen\s+every\b|\bfor\s+the\s+empty\b|"
    r"\bis\s+the\s+fraction\b",
    re.IGNORECASE,
)
# 0 and 1 are boundary conditions of the definition. "gap = 0" states that the
# bound is closed; no corpus produced it.
_DEGENERATE = re.compile(rf"\b(?:{_METRIC})\s*[:=]\s*[01](?!\d|\.\d)", re.IGNORECASE)
# Dependency prose. "runtime" is both a metric name and the word for an
# interpreter, which is why "the Python 3 runtime is supported" read as a claim.
_VERSIONISH = re.compile(
    r"\b(?:python|mypy|pytest|ortools|version)\b[^.\n]{0,20}?\d|"
    r"\b\d+\.\d+(?:\.\d+)?\s+or\s+newer\b|"
    r"\bis\s+pinned\b",
    re.IGNORECASE,
)

QUANTITATIVE = (
    ("metric stated with a value", re.compile(
        rf"\b(?:{_METRIC})\b[^.\n]{{0,24}}?\b(?:was|were|is|are|of)\b"
        rf"[^.\n]{{0,14}}?\d", re.IGNORECASE)),
    ("metric assigned a value", re.compile(
        rf"\b(?:{_METRIC})\s*[:=]\s*\d", re.IGNORECASE)),
    ("metric followed by a value", re.compile(
        rf"\b(?:{_METRIC})\s+\d+(?:\.\d+)?\b", re.IGNORECASE)),
    ("outcome paired with a number", re.compile(
        rf"\b(?:{_OUTCOME})\b[^.\n]{{0,40}}?\b\d+(?:\.\d+)?\s*%?", re.IGNORECASE)),
    ("percentage with a corpus noun", re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:%|percent)[^.\n]{0,40}?"
        r"\b(?:instances?|runs?|cases?|elements?|sets?|optimum)\b", re.IGNORECASE)),
    ("spelled-out percentage of a corpus", re.compile(
        r"\b(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
        r"[-\s]?(?:one|two|three|four|five|six|seven|eight|nine)?\s*percent\b",
        re.IGNORECASE)),
    # Up to four intervening words, not two: "24 percent was the observed
    # shortfall" puts three between the value and the metric. Widening this far
    # was checked against the repository's own prose — test counts, file counts,
    # seeds and exit codes stay legal.
    ("value followed by a metric", re.compile(
        rf"\b\d+(?:\.\d+)?\s*%?\s+(?:\w+\s+){{0,4}}?(?:{_METRIC})\b", re.IGNORECASE)),
    ("comparative ratio", re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:x|times)\s+(?:\w+\s+){0,2}?"
        r"(?:slower|faster|fewer|more|better|worse)\b", re.IGNORECASE)),
    ("table row of numbers", re.compile(r"^\s*\|[^|\n]*\|\s*\d+(?:\.\d+)?\s*\|")),
    # Chinese forms. Their absence was assumed rather than checked, while the
    # project's own working language is Chinese.
    ("Chinese metric with a value", re.compile(
        r"(?:失败率|覆盖率|间隙|近似比|加速比|运行时间|耗时|节点数)[^。\n]{0,8}?\d")),
    ("Chinese percentage of a corpus", re.compile(
        r"\d+(?:\.\d+)?\s*%\s*的?\s*(?:实例|运行|案例|元素)")),
    ("Chinese comparative ratio", re.compile(r"\d+(?:\.\d+)?\s*倍")),
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
# Documentation has to show how to supply a secret without containing one. These
# forms are how it is done, and flagging them blocks correct documentation:
# an angle-bracket or brace placeholder, a shell or CI variable reference, and a
# lookup in code. Each requires the *whole* value to be the placeholder, so a
# placeholder followed by a real value is still reported — the exclusion cannot
# be used as a prefix that launders a secret. Written as a description rather
# than as an example, since an example would trip this file's own check.
_SECRET_PLACEHOLDER = re.compile(
    r"\A(?:"
    r"<[^>]*>"                                  # <your-password>
    r"|\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*"    # ${VAR}, $VAR
    r"|%[A-Za-z_][A-Za-z0-9_]*%"                # %VAR% on Windows
    r"|\{\{[^}]*\}\}|\{[A-Za-z_][A-Za-z0-9_]*\}"  # {{ secrets.X }}, {name}
    r"|(?:os\.environ|os\.getenv|getenv|process\.env)\b.*"
    r"|(?:REDACTED|CHANGEME|CHANGE_ME|PLACEHOLDER|EXAMPLE|TODO|xxx+|\.{3,})"
    r")\Z",
    re.IGNORECASE,
)

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
    # Secret assignments, quoted or bare. Both capture the value as `value` so
    # a placeholder can be recognised and excluded; see _SECRET_PLACEHOLDER.
    (
        "secret assignment",
        re.compile(
            rf"{_SECRET_KEY}\s*[:=]\s*[\"'](?P<value>{_SECRET_VALUE})[\"']",
            re.IGNORECASE,
        ),
    ),
    # A bare assignment ends at whitespace, not at the line end. Anchoring it to
    # the line end missed the value whenever anything followed it — a trailing
    # comment, a closing backtick, or a sentence continuing past it — which is
    # the common shape in prose and in a documented example. The value class
    # already excludes whitespace, so the run itself is the bound.
    (
        "secret assignment",
        re.compile(
            rf"{_SECRET_KEY}\s*[:=]\s*(?P<value>{_SECRET_VALUE})(?=\s|$|`)",
            re.IGNORECASE,
        ),
    ),
)

# Link syntaxes that GitHub actually resolves.
#
# The predecessor recognised exactly one, `[text](target)`. Reference-style
# links and HTML attributes went unchecked, so a broken target written either of
# those ways passed a check whose docstring promises that every relative link
# resolves.
#
# Link text may itself contain brackets — `[![alt](img)](target)` is the badge
# pattern every public README uses, and `[see [this]](target)` is legal. So the
# text is matched by scanning balanced brackets rather than by a character class
# that stops at the first `]`, which is what made both invisible.
#
# Autolinks are deliberately absent rather than overlooked. A CommonMark
# autolink carries a scheme, as in <https://example.com>, so it is always
# external; a bare relative path in angle brackets is not a link at all and
# renders as literal text. Checking it would report a target no reader can
# click, which is how a check earns a `continue-on-error`.

# A destination, once the opening paren is found: `<...>`, or a bare run ending
# at whitespace or the closing paren. A bare destination may be followed by a
# title, as in `[x](path "title")`, which is not part of the target.
LINK_DESTINATION = re.compile(r"\s*(?:<([^>]*)>|([^)\s]+))")
MD_REFERENCE_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(?:<([^>]*)>|(\S+))")
# A GFM footnote definition, `[^1]: text`, is not a link definition. Its text is
# prose, so parsing it as a destination reported the prose as a broken target.
FOOTNOTE_DEF = re.compile(r"^\s{0,3}\[\^")
HTML_ATTRIBUTE_LINK = re.compile(
    r"<(?:a|img|source|video|audio|iframe)\b[^>]*?"
    r"\b(?:href|src)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.IGNORECASE,
)

# The shortcut form — a bare `[label]` with its definition elsewhere — is not
# matched. Every bracketed phrase in prose would become a candidate target. The
# collapsed form `[label][]` is matched, because the empty second bracket makes
# the intent explicit.

# Two or more characters before the colon. RFC 3986 permits a single-letter
# scheme, but in a link destination a lone letter before a colon is a Windows
# drive, and a drive path was therefore skipped here as an external URL.
EXTERNAL = re.compile(r"\A(?:[a-z][a-z0-9+.-]+:|//|#)", re.IGNORECASE)

# Fenced code shows link syntax as an example rather than linking anywhere.
#
# CommonMark 4.5 governs when a fence closes, and getting it wrong is worse than
# not handling fences at all: a closer that is mistaken for an opener flips the
# parity of everything after it, so a real broken link becomes invisible while a
# line of actual code gets reported. Two rules were missing.
#
# First, a closing fence carries no info string. `` ```console `` twice in a
# file is an opener followed by another opener, not an open-and-close, and this
# repository's own documents use exactly that style.
#
# Second, a closer must be at least as long as its opener, so a three-backtick
# line inside a four-backtick block is content.
FENCE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})(.*)$")
# An inline code span does the same within a line: `sets[i][j]` is not a
# reference-style link. The delimiter may be a run of any length, and a span
# opened with two backticks can contain single ones — that is how a literal
# backtick is written — so the closing run must match the opening run's length.
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)*?\1", re.DOTALL)
# An indented code block is code on GitHub too. Four spaces, outside a fence,
# and not a lazy continuation of a paragraph — so only after a blank line.
INDENTED_CODE = re.compile(r"^(?: {4}|\t)")
# A bracket escaped with a backslash is literal text, not link syntax.
ESCAPED_BRACKET = re.compile(r"\\[\[\]]")


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
    """Reject result claims in prose, unless the active mode authorizes them.

    Matching runs over each paragraph with its newlines collapsed, because
    Markdown renders consecutive lines as one sentence and a claim split across
    two lines would otherwise pass. The reported line is the paragraph's first,
    since a joined match has no single line of its own.
    """

    if claim_mode != "no_quantitative_claims":
        # Evidence binding is the human-reviewed CLAIMS.md contract. This check
        # still scans the same tracked files for sensitive content and links.
        return []
    if PurePosixPath(path).suffix.casefold() not in PROSE_SUFFIXES:
        return []

    findings = []
    line_number = 1
    for paragraph in re.split(r"\n\s*\n", text):
        lines = paragraph.split("\n")
        # Fixture markers and exclusions are judged per line so that one
        # exempt line does not carry its whole paragraph.
        checkable = [line for line in lines if not _is_exempt(line)]
        if checkable:
            joined = re.sub(r"\s*\n\s*", " ", "\n".join(checkable))
            if not _claim_excluded(joined):
                for label, pattern in QUANTITATIVE:
                    if pattern.search(joined) or any(
                        pattern.search(line) for line in checkable
                    ):
                        findings.append(
                            f"{path}:{line_number}: reads as a quantitative result "
                            f"claim ({label}); the selected claim mode permits none"
                        )
                        break
        line_number += len(lines) + 1
    return findings


def _claim_excluded(segment: str) -> bool:
    """True when a metric sits beside a number without asserting a measurement."""

    return bool(
        _DEFINITIONAL.search(segment)
        or _DEGENERATE.search(segment)
        or _VERSIONISH.search(segment)
    )


def check_sensitive(path: str, text: str) -> list[str]:
    findings = []
    for index, line in enumerate(text.splitlines(), start=1):
        if _is_exempt(line):
            continue
        for label, pattern in SENSITIVE:
            match = pattern.search(line)
            if match is None:
                continue
            # A pattern that captures a value lets a documented placeholder
            # through. Only the assignment patterns do; everything else — a key
            # header, a provider token — has no placeholder form.
            if "value" in (pattern.groupindex or {}):
                value = match.group("value")
                if value and _SECRET_PLACEHOLDER.match(value):
                    continue
            findings.append(f"{path}:{index}: {label} must not be published")
    return findings


def _blank_code(text: str) -> list[str]:
    """Return the lines with code content blanked, keeping the line count intact.

    Link syntax inside code is an example, not a link. Three code forms are
    recognised: fenced blocks, indented blocks, and inline spans.

    The line *count* is preserved so a reported line number still matches the
    file. Line length is not: a code line becomes empty. Nothing may depend on
    the column of a blanked line — `check_links` reads the original line when it
    needs the real text, which is what the fixture-marker check does.

    Fence handling follows CommonMark 4.5, because a mistake here is worse than
    ignoring fences entirely. A closer mistaken for an opener flips the parity of
    the rest of the file, hiding real broken links and reporting real code.
    """

    lines = text.split("\n")
    result = []
    fence: tuple[str, int] | None = None
    previous_blank = True
    for line in lines:
        match = FENCE.match(line)
        if fence is None:
            if match is not None:
                # An opener may carry an info string; its length is the minimum
                # a closer must match.
                fence = (match.group(2)[0], len(match.group(2)))
                result.append("")
                previous_blank = False
                continue
            # An indented code block only starts after a blank line; otherwise
            # four spaces are a lazy continuation of the paragraph above.
            if previous_blank and INDENTED_CODE.match(line):
                result.append("")
                continue
            previous_blank = not line.strip()
            result.append(CODE_SPAN.sub(lambda hit: " " * len(hit.group(0)), line))
        else:
            character, length = fence
            closes = (
                match is not None
                and match.group(2)[0] == character
                and len(match.group(2)) >= length
                # A closing fence carries no info string. Without this, a second
                # ```console line reads as a closer and inverts everything after.
                and not match.group(3).strip()
            )
            if closes:
                fence = None
                previous_blank = False
            result.append("")
    return result


def _inline_targets(line: str) -> list[str]:
    """Find `[text](destination)` targets, allowing brackets inside the text.

    A character class cannot do this. `[![alt](img)](target)` is the badge
    pattern, and its text contains a complete image link; a class that stops at
    the first `]` sees neither link. So brackets are counted.

    An escaped bracket is literal text and does not open or close a link. The
    scan runs left to right and finds nested links too, since it continues from
    inside the text rather than skipping past the whole construct.
    """

    targets = []
    for index, character in enumerate(line):
        if character != "[":
            continue
        if index and line[index - 1] == "\\":
            continue
        depth = 0
        position = index
        while position < len(line):
            here = line[position]
            if here in "[]" and position and line[position - 1] == "\\":
                position += 1
                continue
            if here == "[":
                depth += 1
            elif here == "]":
                depth -= 1
                if depth == 0:
                    break
            position += 1
        else:
            continue
        # `position` is now the `]` closing this link's text.
        if position + 1 >= len(line) or line[position + 1] != "(":
            continue
        match = LINK_DESTINATION.match(line, position + 2)
        if match is not None:
            targets.append(match.group(1) if match.group(1) is not None else match.group(2))
    return targets


def _resolve(path: str, target: str) -> tuple[str | None, bool]:
    """Resolve a link target against the linking file. Returns (path, escaped)."""

    cleaned = target.split("#", 1)[0].split("?", 1)[0].strip()
    # A destination is percent-encoded, so `%20` is how a tracked filename
    # containing a space is written. Compare the decoded form against the
    # tracked names, or every such link reads as unresolvable.
    cleaned = unquote(cleaned)
    if not cleaned:
        return None, False
    # A leading slash in a Markdown link is repository-root-relative on GitHub.
    base = PurePosixPath("") if cleaned.startswith("/") else PurePosixPath(path).parent
    parts: list[str] = []
    for part in (base / cleaned.lstrip("/")).parts:
        if part == "..":
            if not parts:
                return None, True
            parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts), False


def check_links(
    path: str, text: str, known: frozenset[str], known_dirs: frozenset[str]
) -> list[str]:
    """Verify that every relative link resolves to a tracked path.

    Applies to files GitHub renders as Markdown. `.rst` and `.txt` are prose for
    the claim check but their link syntax is not Markdown's, so a `[x](y)` in
    them is literal text; checking it would report targets no reader can click.

    Four things this does not do, each for a reason:

    - It never touches the filesystem. `Path.exists()` is case-insensitive on
      Windows and case-sensitive on the Linux runner, so a link whose case was
      wrong passed locally and 404s on github.com. The tracked-name set is the
      same on both platforms, which makes the verdict platform-independent — and
      a wrong-case link is reported as such rather than as missing, since that is
      the failure a contributor on Windows cannot otherwise see.
    - It does not resolve anchors. GitHub's heading-slug rules are not worth
      reimplementing, and a wrong anchor degrades to landing at the top of a page
      that does exist.
    - It does not follow a reference definition's own target twice. A definition
      is checked where it is defined; a use is checked only against the set of
      definitions.
    - It does not report an undefined reference label. `[text][nowhere]` renders
      as literal text, so it is not a broken link — the same reasoning that
      excludes autolinks. Reporting it flagged ordinary prose instead: an index
      expression like sets[i][j] outside backticks, and citation forms, are
      indistinguishable from a mistyped label without knowing the author's
      intent. A check that flags those is noise, and noise is what gets a gate
      disabled.
    """

    if PurePosixPath(path).suffix.casefold() not in MARKDOWN_SUFFIXES:
        return []

    lines = _blank_code(text)
    raw = text.split("\n")

    # Built once. Rebuilding these inside the per-target loop made the cost
    # quadratic in tracked files, on the path taken when something is already
    # wrong. Lower-cased, not case-folded: casefold maps ß to ss, so a link to a
    # genuinely different filename was reported as a mere case difference, with
    # a message claiming it works on Windows when it works nowhere.
    lowered_names = {name.lower(): name for name in known}
    lowered_dirs = {name.lower() for name in known_dirs}

    definitions: set[str] = set()
    for line in lines:
        if FOOTNOTE_DEF.match(line):
            continue
        match = MD_REFERENCE_DEF.match(line)
        if match is not None:
            definitions.add(_normalize_label(match.group(1)))

    findings = []
    for index, line in enumerate(lines, start=1):
        if _is_exempt(raw[index - 1]):
            continue

        targets = list(_inline_targets(line))
        for match in HTML_ATTRIBUTE_LINK.finditer(line):
            targets.append(match.group(1) or match.group(2) or match.group(3))
        # A footnote definition's text is prose, not a destination.
        if not FOOTNOTE_DEF.match(line):
            definition = MD_REFERENCE_DEF.match(line)
            if definition is not None:
                targets.append(
                    definition.group(2)
                    if definition.group(2) is not None
                    else definition.group(3)
                )

        for target in targets:
            if not target or EXTERNAL.match(target):
                continue
            candidate, escaped = _resolve(path, target)
            if escaped:
                findings.append(f"{path}:{index}: link escapes the repository")
                continue
            if not candidate or candidate in known or candidate in known_dirs:
                continue
            lowered = candidate.lower()
            if lowered in lowered_names or lowered in lowered_dirs:
                findings.append(
                    f"{path}:{index}: internal link differs in case from the "
                    "tracked path; it resolves on Windows and 404s on github.com"
                )
            else:
                findings.append(f"{path}:{index}: internal link does not resolve")

    # A link may be split across lines, since Markdown renders consecutive lines
    # as one sentence. Matched over the joined paragraph as well, the same way
    # check_quantitative does, and reported at the paragraph's first line because
    # a joined match has no line of its own. Only targets not already seen
    # line-by-line are reported, so an ordinary link is not counted twice.
    #
    # Not deduplicated. Two different broken links on one line produce the same
    # message text, and collapsing them would report one fault where there are
    # two — the joined pass already excludes what the line pass saw, which is
    # where a genuine double-report would come from.
    findings += _check_joined_links(
        path, lines, raw, known, known_dirs, lowered_names, lowered_dirs
    )
    return findings


def _normalize_label(label: str) -> str:
    """Fold a reference label the way CommonMark does: trim, collapse, casefold.

    Internal whitespace runs collapse to a single space, so `[a  b]` and `[a b]`
    are the same label. Only stripping made them different.
    """

    return re.sub(r"\s+", " ", label.strip()).casefold()


def _check_joined_links(
    path: str,
    lines: list[str],
    raw: list[str],
    known: frozenset[str],
    known_dirs: frozenset[str],
    lowered_names: dict[str, str],
    lowered_dirs: set[str],
) -> list[str]:
    """Report links whose syntax spans a line break within one paragraph."""

    seen: set[str] = set()
    for line in lines:
        seen.update(_inline_targets(line))

    findings = []
    number = 1
    for paragraph in re.split(r"\n\s*\n", "\n".join(lines)):
        block = paragraph.split("\n")
        checkable = [
            item
            for offset, item in enumerate(block)
            if number + offset <= len(raw) and not _is_exempt(raw[number + offset - 1])
        ]
        joined = re.sub(r"\s*\n\s*", " ", "\n".join(checkable))
        for target in _inline_targets(joined):
            if target in seen or not target or EXTERNAL.match(target):
                continue
            candidate, escaped = _resolve(path, target)
            if escaped:
                findings.append(f"{path}:{number}: link escapes the repository")
                continue
            if not candidate or candidate in known or candidate in known_dirs:
                continue
            lowered = candidate.lower()
            if lowered in lowered_names or lowered in lowered_dirs:
                findings.append(
                    f"{path}:{number}: internal link differs in case from the "
                    "tracked path; it resolves on Windows and 404s on github.com"
                )
            else:
                findings.append(f"{path}:{number}: internal link does not resolve")
        number += len(block) + 1
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim-mode", required=True, choices=CLAIM_MODES)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    names = tracked_files(root)
    known = frozenset(names)
    # Git tracks no directory, but a link to one resolves on github.com. Every
    # parent of every tracked file is therefore a legal target.
    known_dirs = frozenset(
        str(parent)
        for name in names
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    )

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
        findings += check_links(name, text, known, known_dirs)

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
