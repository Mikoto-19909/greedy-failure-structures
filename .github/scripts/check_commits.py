"""Check commits against the two commit rules CONTRIBUTING.md declares.

CONTRIBUTING.md states both of these as enforced, and neither was:

1. "This repository publishes no quantitative research claims. [...] Do not add
   them to the README, to documentation, to release notes, or to commit
   messages." The content-boundary checker reads tracked file *content* and
   never opens `git log`, so the commit-message half of that sentence had no
   enforcement at all.

2. "Do not attribute commits to an AI assistant. No `Co-Authored-By` trailer
   naming a model, and no 'generated with' line."

This script closes both over a commit range. It reads git only, makes no
network request, and writes no file.

Findings name a short SHA and the rule that failed. They never echo the
offending text. That is deliberate and is the same rule the content-boundary
checker follows: this output is readable by anyone once the repository is
public, so a check that reprints a prohibited claim would republish the claim
it exists to keep out.

Scope of the AI-attribution check
---------------------------------
Model names are matched in *attribution positions* only — trailer values, the
author and committer identity, and a "generated with" line — not in free prose.
A commit that legitimately discusses an assistant ("drop the assistant-specific
notes") is not an attribution, and matching prose would also make ordinary
words unusable: "Cursor" and "Codex" are product names, but `cursor` is also a
database and text-editing term. Restricting the match to attribution positions
is what the declaration actually says, and it keeps the check free of the
false positives that get a check disabled.

Range handling and the two GitHub event shapes
----------------------------------------------
This script does not read the `github` context or any `GITHUB_*` variable. The
range is an argument. The workflow knows the event shape and passes the range;
the script only has to be correct about the range it is given.

That split is deliberate. Event-shape knowledge in the script would be
untestable without simulating a GitHub payload, and the script would silently
check the wrong range whenever run locally. As an argument, the same invocation
is reproducible on a developer machine, and `tests/test_commit_policy.py` can
build real repositories and pass real ranges.

The one event fact the script must absorb is that `github.event.before` is
all-zeros on a branch's first push, because there is no prior commit to diff
against. An unresolvable, empty, or all-zeros base is therefore not an error:
the script falls back to the last `--fallback-depth` commits ending at the
head, which defaults to 1.

Depth 1 rather than a deep walk is the conservative choice. A new branch's
first push has no defensible lower bound — walking back N commits reaches
history that is already merged and already reviewed, so a deep default would
report findings against old commits on every new branch, which is how a check
earns a `continue-on-error` and stops meaning anything. The pull request that
follows re-checks the full `base..head` range, so nothing escapes review; the
first push is checked at its tip and the PR closes the range.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Rule 2: AI attribution.
# --------------------------------------------------------------------------

# Product and model names that identify an AI assistant rather than a person.
# Matched only in attribution positions (see the module docstring), so entries
# that are also ordinary words are safe here.
_AI_NAME = (
    r"claude|anthropic|chatgpt|gpt|openai|copilot|codex|gemini|bard|"
    r"cursor|devin|codeium|tabnine|windsurf|aider|cline|kiro|jules|"
    r"llama|mistral|deepseek|qwen|sonnet|opus|haiku|"
    r"ai\s+assistant|language\s+model|llm"
)
AI_NAME = re.compile(rf"\b(?:{_AI_NAME})\b", re.IGNORECASE)

# Domains that identify the committer as an assistant regardless of the name.
_AI_DOMAIN = (
    r"anthropic\.com|openai\.com|cursor\.(?:sh|com)|codeium\.com|"
    r"tabnine\.com|deepseek\.com"
)
AI_DOMAIN = re.compile(rf"@(?:[A-Za-z0-9-]+\.)*(?:{_AI_DOMAIN})\b", re.IGNORECASE)

# Trailer keys that assign credit. Any of them naming a model is an
# attribution. Both `Co-Authored-By` and `Co-authored-by` occur in the wild and
# git itself treats trailer keys case-insensitively, so this must too.
_ATTRIBUTION_KEY = (
    r"co-?authored-by|co-?committed-by|co-?developed-by|co-?written-by|"
    r"assisted-by|generated-by|created-by|authored-by|signed-off-by|"
    r"helped-by|reviewed-by"
)
ATTRIBUTION_TRAILER = re.compile(
    rf"^\s*(?P<key>{_ATTRIBUTION_KEY})\s*:\s*(?P<value>.*)$",
    re.IGNORECASE,
)

# The "generated with" attribution line, as a line rather than as a phrase.
# The leading class absorbs indentation and a decorative emoji, which is how
# the common form arrives: "🤖 Generated with [Claude Code](...)".
#
# Line-anchored on purpose. A commit may legitimately say that a file "is the
# live allow-list, generated by build_license_manifest.py" mid-sentence; only
# the footer form is an attribution.
GENERATED_LINE = re.compile(r"^[^\w\n]{0,8}generated\s+(?:with|by)\b", re.IGNORECASE)

# A generation claim that names an assistant is an attribution wherever it sits.
GENERATED_BY_AI = re.compile(
    rf"generated\s+(?:with|by)\b[^.\n]{{0,40}}?\b(?:{_AI_NAME})\b",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# Rule 1: quantitative research claims.
# --------------------------------------------------------------------------
#
# Implemented here rather than imported from check_content_boundary.py. The two
# checks read different inputs — tracked file content against git history — and
# coupling them would mean a pattern tuned for prose could not be adjusted for
# commit messages without moving the other check's baseline.
#
# A claim is a research *metric* stated with a number, or an outcome verb
# paired with one. Bare numbers stay legal, and that is the load-bearing half:
# commit messages in this repository count files, tests, jobs, exit codes and
# versions constantly ("The manifest lists 74 files", "timeout-minutes: 10").
# A checker that flags those is noise, gets ignored, and then gets removed.
_METRIC = (
    r"failure\s+rate|success\s+rate|recovery\s+rate|error\s+rate|hit\s+rate|"
    r"optimality\s+gap|approximation\s+ratio|runtime\s+ratio|node\s+reduction|"
    r"wall[-\s]?clock|throughput|speedups?|slowdowns?|"
    r"coverage|runtime|deficit|objective|gap"
)
_OUTCOME = (
    r"failed|succeeded|lost|loses|losing|gained|recovered|averaged|achieved|"
    r"reached|outperformed|beat|exceeded|covered|solved|explored|improved|"
    r"degraded|regressed|sped\s+up"
)
_PERCENT = r"(?:%|percent|per\s?cent)"

QUANTITATIVE = (
    # "the failure rate was 25%", "coverage of 19"
    (
        "metric stated with a value",
        re.compile(
            rf"\b(?:{_METRIC})\b[^.\n]{{0,20}}?\b(?:was|were|is|are|of)\b"
            rf"[^.\n]{{0,12}}?\d",
            re.IGNORECASE,
        ),
    ),
    # "mean gap: 0.24", "speedup = 3.2"
    (
        "metric assigned a value",
        re.compile(rf"\b(?:{_METRIC})\s*[:=]\s*\d", re.IGNORECASE),
    ),
    # "greedy covered 80%", "loses 38 percent of the optimum"
    (
        "outcome verb paired with a number",
        re.compile(
            rf"\b(?:{_OUTCOME})\b[^.\n]{{0,40}}?\b\d+(?:\.\d+)?\s*{_PERCENT}?",
            re.IGNORECASE,
        ),
    ),
    # "45% of instances", "80% of elements"
    (
        "proportion of a measured corpus",
        re.compile(
            rf"\b\d+(?:\.\d+)?\s*{_PERCENT}[^.\n]{{0,40}}?"
            r"\b(?:instances?|runs?|cases?|elements?|sets?|seeds?|trials?)\b",
            re.IGNORECASE,
        ),
    ),
    # "12.5% coverage", "3 seconds runtime"
    (
        "value attached to a metric",
        re.compile(
            rf"\b\d+(?:\.\d+)?\s*{_PERCENT}?\s+(?:\w+\s+){{0,2}}?(?:{_METRIC})\b",
            re.IGNORECASE,
        ),
    ),
)


class CommitPolicyError(RuntimeError):
    """An operational failure: git unavailable, or a revision that cannot resolve."""


def _git(root: Path, arguments: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as error:  # pragma: no cover - depends on the host
        raise CommitPolicyError("git is not available on PATH") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip().splitlines()
        raise CommitPolicyError(
            f"git {' '.join(arguments)} failed: {detail[-1] if detail else 'unknown error'}"
        ) from error
    return completed.stdout


def is_zero_sha(revision: str) -> bool:
    """True for git's all-zeros null SHA, which `push` sends for a first push."""

    return bool(revision) and set(revision) == {"0"}


def revision_exists(root: Path, revision: str) -> bool:
    try:
        _git(root, ["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"])
    except CommitPolicyError:
        return False
    return True


class Commit:
    __slots__ = ("sha", "author_name", "author_email", "committer_name",
                 "committer_email", "message")

    def __init__(
        self,
        sha: str,
        author_name: str,
        author_email: str,
        committer_name: str,
        committer_email: str,
        message: str,
    ) -> None:
        self.sha = sha
        self.author_name = author_name
        self.author_email = author_email
        self.committer_name = committer_name
        self.committer_email = committer_email
        self.message = message

    @property
    def short_sha(self) -> str:
        return self.sha[:8]


# NUL separates records and Unit Separator separates fields. Neither can occur
# in a commit message, so no message content can forge a record boundary.
_LOG_FORMAT = "--format=%x00%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B"


def collect_commits(root: Path, revisions: list[str]) -> list[Commit]:
    output = _git(root, ["log", _LOG_FORMAT, *revisions])
    commits = []
    for chunk in output.split("\0"):
        if not chunk.strip():
            continue
        fields = chunk.split("\x1f")
        if len(fields) < 6:
            continue
        commits.append(
            Commit(
                sha=fields[0].strip(),
                author_name=fields[1],
                author_email=fields[2],
                committer_name=fields[3],
                committer_email=fields[4],
                message=fields[5],
            )
        )
    return commits


def resolve_revisions(
    root: Path,
    base: str | None,
    head: str,
    fallback_depth: int,
) -> tuple[list[str], str]:
    """Turn a base/head pair into `git log` arguments, and say what was used.

    An unusable base is a supported input, not an error: see the module
    docstring on `github.event.before`.
    """

    if not revision_exists(root, head):
        raise CommitPolicyError(f"head revision does not resolve: {head}")

    if base and not is_zero_sha(base) and revision_exists(root, base):
        return [f"{base}..{head}"], f"{base[:8]}..{head[:8]}"

    if base and is_zero_sha(base):
        reason = "base is the null SHA (first push of a branch)"
    elif base:
        reason = "base does not resolve in this checkout"
    else:
        reason = "no base given"
    return (
        [f"--max-count={fallback_depth}", head],
        f"{head[:8]} and {fallback_depth} commit(s) back ({reason})",
    )


def check_ai_attribution(commit: Commit) -> list[str]:
    """Reject AI attribution in trailers, identity fields and generation lines."""

    findings = []
    for line in commit.message.splitlines():
        trailer = ATTRIBUTION_TRAILER.match(line)
        if trailer is not None:
            value = trailer.group("value")
            if AI_NAME.search(value) or AI_DOMAIN.search(value):
                # Lowercased so that the same trailer written in two casings
                # is one finding rather than two. The key is named because it
                # tells the contributor which line to remove; the value is not,
                # because reproducing it would republish the attribution.
                key = trailer.group("key").casefold()
                findings.append(
                    f"'{key}' trailer attributes the commit to an AI assistant; "
                    "authorship stays with the person who submitted the work"
                )
                continue
        if GENERATED_LINE.match(line) or GENERATED_BY_AI.search(line):
            findings.append(
                "carries a 'generated with' attribution line; "
                "CONTRIBUTING.md prohibits it"
            )

    for role, name, email in (
        ("author", commit.author_name, commit.author_email),
        ("committer", commit.committer_name, commit.committer_email),
    ):
        identity = f"{name} <{email}>"
        if AI_NAME.search(name) or AI_DOMAIN.search(identity):
            findings.append(
                f"{role} identity names an AI assistant; "
                "commits must be attributed to a person"
            )

    # One finding per rule per commit. A commit repeating the same trailer
    # should not inflate the count.
    return sorted(set(findings))


def check_quantitative(commit: Commit) -> list[str]:
    """Reject research metrics stated with numbers in the commit message."""

    findings = []
    for line in commit.message.splitlines():
        for label, pattern in QUANTITATIVE:
            if pattern.search(line):
                findings.append(
                    f"message reads as a quantitative research claim "
                    f"({label}); this repository publishes none"
                )
                break
    return sorted(set(findings))


def check_commit(commit: Commit) -> list[str]:
    return check_ai_attribution(commit) + check_quantitative(commit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check commit messages and authorship against CONTRIBUTING.md.",
    )
    parser.add_argument(
        "--base",
        default=None,
        help=(
            "Exclusive lower bound. Accepts an empty value or git's all-zeros "
            "null SHA, both of which fall back to --fallback-depth."
        ),
    )
    parser.add_argument("--head", default="HEAD", help="Inclusive upper bound.")
    parser.add_argument(
        "--range",
        dest="commit_range",
        default=None,
        help="A git range such as main..HEAD, as an alternative to --base/--head.",
    )
    parser.add_argument(
        "--fallback-depth",
        type=int,
        default=1,
        help="Commits to check from the head when no usable base is given (default: 1).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository to inspect (default: the repository holding this script).",
    )
    args = parser.parse_args(argv)

    if args.commit_range and args.base:
        parser.error("--range and --base are mutually exclusive")
    if args.fallback_depth < 1:
        parser.error("--fallback-depth must be at least 1")

    root = args.repo_root.resolve()

    try:
        if args.commit_range:
            revisions, described = [args.commit_range], args.commit_range
        else:
            revisions, described = resolve_revisions(
                root, args.base, args.head, args.fallback_depth
            )
        commits = collect_commits(root, revisions)
    except CommitPolicyError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1

    findings = []
    for commit in commits:
        for problem in check_commit(commit):
            findings.append(f"{commit.short_sha}: {problem}")

    sys.stdout.write(f"range checked  : {described}\n")
    sys.stdout.write(f"commits checked: {len(commits)}\n")
    sys.stdout.write(f"findings       : {len(findings)}\n")

    if findings:
        sys.stdout.write("\n")
        for item in findings:
            sys.stdout.write(f"  {item}\n")
        sys.stdout.write(
            "\nThe offending text is deliberately not reproduced here. "
            "Use 'git log -1 <sha>' locally, and amend or rebase to correct it.\n"
        )
        return 1
    sys.stdout.write("\nEvery commit in range satisfies the commit rules.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
