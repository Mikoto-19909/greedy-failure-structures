"""Adversarial tests for the commit-policy checker.

Every case here is derived from a declaration, not from the implementation.
The declarations are in CONTRIBUTING.md:

- "This repository publishes no quantitative research claims. [...] Do not add
  them to the README, to documentation, to release notes, or to commit
  messages." (the single-claim-source section, stated as enforced)
- "Do not attribute commits to an AI assistant. No `Co-Authored-By` trailer
  naming a model, and no 'generated with' line."

Both were declared and neither was enforced: the pre-existing content checker
reads tracked file content and never opens git history, so a commit stating a
failure rate in its subject and carrying an AI trailer in its body passed every
check in the repository.

The rejection cases are built as real commits in real temporary repositories
and checked through the script's command-line entry point, because that is what
CI runs. Testing the patterns alone would not catch a range-resolution bug, a
trailer that git rewrites, or an identity the log format drops — and range
handling is where this check is most likely to fail silently by reporting
success over commits it never read.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / ".github" / "scripts" / "check_commits.py"

ZERO_SHA = "0" * 40


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load("_commit_policy_checker", CHECKER)


class TemporaryRepository:
    """A real git repository, so trailers and identities are git's own output."""

    def __init__(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.path = Path(self._directory.name)
        self._git("init", "--initial-branch=main")
        self._git("config", "user.name", "Liang Dao")
        self._git("config", "user.email", "dev@example.com")
        self._git("config", "commit.gpgsign", "false")
        self._counter = 0

    def _git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.path,
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout

    def commit(
        self,
        message: str,
        author: str | None = None,
        committer: str | None = None,
    ) -> str:
        """Write a distinct file and commit it, returning the full SHA."""

        self._counter += 1
        (self.path / f"file_{self._counter}.txt").write_text(
            f"content {self._counter}\n", encoding="utf-8"
        )
        self._git("add", "--all")
        arguments = ["commit", "--no-verify", "-m", message]
        if author is not None:
            arguments += ["--author", author]
        environment_committer = committer
        if environment_committer is not None:
            name, _, rest = environment_committer.partition(" <")
            self._git("-c", f"user.name={name}", "-c",
                      f"user.email={rest.rstrip('>')}", *arguments)
        else:
            self._git(*arguments)
        return self._git("rev-parse", "HEAD").strip()

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def close(self) -> None:
        self._directory.cleanup()


def run_checker(repository: TemporaryRepository, *arguments: str) -> tuple[int, str]:
    """Invoke the checker exactly as CI does, capturing its report."""

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        status = checker.main(["--repo-root", str(repository.path), *arguments])
    return status, buffer.getvalue()


class CommitPolicyCase(unittest.TestCase):
    """Shared helpers that assert against a real commit, not a pattern."""

    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.close)
        # A base commit so that base..head ranges have something to exclude.
        self.base = self.repository.commit("chore: establish the baseline")

    def assertRejected(self, message: str, **identity: str) -> str:
        self.repository.commit(message, **identity)
        status, report = run_checker(
            self.repository, "--base", self.base, "--head", "HEAD"
        )
        self.assertEqual(status, 1, f"not rejected: {message!r}\n{report}")
        return report

    def assertAccepted(self, message: str, **identity: str) -> str:
        self.repository.commit(message, **identity)
        status, report = run_checker(
            self.repository, "--base", self.base, "--head", "HEAD"
        )
        self.assertEqual(status, 0, f"wrongly rejected: {message!r}\n{report}")
        return report


class AiAttributionTests(CommitPolicyCase):
    """CONTRIBUTING.md: no Co-Authored-By naming a model, no 'generated with'."""

    def test_co_authored_by_claude_is_rejected(self) -> None:
        report = self.assertRejected(
            "fix: correct the boundary check\n\n"
            "Co-Authored-By: Claude <noreply@anthropic.com>"
        )
        self.assertIn("AI assistant", report)

    def test_trailer_key_casing_variants_are_rejected(self) -> None:
        for key in ("Co-authored-by", "co-authored-by", "CO-AUTHORED-BY",
                    "Co-Authored-By", "Coauthored-by"):
            with self.subTest(key=key):
                repository = TemporaryRepository()
                self.addCleanup(repository.close)
                base = repository.commit("chore: baseline")
                repository.commit(
                    f"fix: adjust the check\n\n{key}: Claude <noreply@anthropic.com>"
                )
                status, report = run_checker(
                    repository, "--base", base, "--head", "HEAD"
                )
                self.assertEqual(status, 1, f"{key} not rejected\n{report}")

    def test_other_model_names_in_trailers_are_rejected(self) -> None:
        for name, email in (
            ("GPT-4", "assistant@openai.com"),
            ("GitHub Copilot", "copilot@example.com"),
            ("Codex", "codex@example.com"),
            ("Gemini", "gemini@example.com"),
            ("Cursor", "agent@cursor.sh"),
            ("Devin", "devin@example.com"),
        ):
            with self.subTest(name=name):
                repository = TemporaryRepository()
                self.addCleanup(repository.close)
                base = repository.commit("chore: baseline")
                repository.commit(
                    f"fix: adjust the check\n\nCo-Authored-By: {name} <{email}>"
                )
                status, report = run_checker(
                    repository, "--base", base, "--head", "HEAD"
                )
                self.assertEqual(status, 1, f"{name} not rejected\n{report}")

    def test_generated_with_line_is_rejected(self) -> None:
        report = self.assertRejected(
            "fix: correct the boundary check\n\n"
            "\N{ROBOT FACE} Generated with [Claude Code](https://claude.com/claude-code)"
        )
        self.assertIn("generated with", report)

    def test_generated_by_line_is_rejected(self) -> None:
        self.assertRejected("fix: correct the check\n\nGenerated by an AI assistant")

    def test_author_identity_naming_an_ai_is_rejected(self) -> None:
        report = self.assertRejected(
            "fix: correct the boundary check",
            author="Claude <noreply@anthropic.com>",
        )
        self.assertIn("author identity", report)

    def test_committer_identity_naming_an_ai_is_rejected(self) -> None:
        report = self.assertRejected(
            "fix: correct the boundary check",
            committer="Cursor Agent <agent@cursor.sh>",
        )
        self.assertIn("committer identity", report)

    def test_ai_domain_alone_is_rejected_even_with_a_human_name(self) -> None:
        self.assertRejected(
            "fix: correct the boundary check",
            author="A Helper <bot@anthropic.com>",
        )

    def test_human_co_author_trailer_is_accepted(self) -> None:
        self.assertAccepted(
            "fix: correct the boundary check\n\n"
            "Co-Authored-By: Jane Roe <jane.roe@example.com>"
        )

    def test_prose_discussing_an_assistant_is_not_an_attribution(self) -> None:
        """The declaration prohibits attribution, not the subject matter."""

        self.assertAccepted(
            "docs: drop the assistant-specific notes from the guide\n\n"
            "The generated allow-list is produced by build_license_manifest.py."
        )


class QuantitativeClaimTests(CommitPolicyCase):
    """CONTRIBUTING.md prohibits quantitative claims in commit messages."""

    def test_failure_rate_claim_is_rejected(self) -> None:
        self.assertRejected("docs: note that greedy failure rate was 25%")

    def test_speedup_assignment_is_rejected(self) -> None:
        self.assertRejected("perf: record that speedup = 3.2")

    def test_optimality_gap_claim_is_rejected(self) -> None:
        self.assertRejected("docs: The optimality gap was 10%")

    def test_percentage_of_elements_is_rejected(self) -> None:
        self.assertRejected("docs: greedy covered 80% of elements")

    def test_spelled_out_percent_loss_is_rejected(self) -> None:
        self.assertRejected("docs: Greedy loses 38 percent of the optimum")

    def test_claim_in_the_body_is_rejected(self) -> None:
        """The subject is not the only place a claim can hide."""

        self.assertRejected(
            "docs: describe the instance families\n\n"
            "Adds the two adversarial families.\n\n"
            "The optimality gap was 10% across the sweep."
        )

    def test_legitimate_messages_are_not_flagged(self) -> None:
        """Real wording from this repository's own history must stay legal."""

        legitimate = (
            "fix: bind license identities to committed blobs, not the work tree",
            "178 tests and mypy pass after the changes.",
            "Verified by injection rather than trusted on a clean run",
            "The manifest lists 74 files.",
            "timeout-minutes: 10",
            "Python 3.11 or newer is required.",
            "CLI exit codes: 0 success, 1 operational error, 2 usage error.",
            "11 job 全部 success",
        )
        for line in legitimate:
            with self.subTest(line=line):
                repository = TemporaryRepository()
                self.addCleanup(repository.close)
                base = repository.commit("chore: baseline")
                repository.commit(f"chore: record the state\n\n{line}")
                status, report = run_checker(
                    repository, "--base", base, "--head", "HEAD"
                )
                self.assertEqual(status, 0, f"wrongly rejected: {line!r}\n{report}")

    def test_a_normal_repository_style_commit_passes(self) -> None:
        self.assertAccepted(
            "fix: separate the license allow-list from the migration archive\n\n"
            "Three findings from review, all confirmed by reproducing them.\n\n"
            "PUBLIC_SNAPSHOT_MANIFEST.json stays frozen as the migration\n"
            "archive. LICENSE_MANIFEST.json is the live allow-list, verified in\n"
            "CI with --check, which fails and names the offending path when the\n"
            "tree and the manifest disagree.\n\n"
            "The manifest lists 74 files. 178 tests and mypy pass.\n\n"
            "Co-Authored-By: Jane Roe <jane.roe@example.com>"
        )


class RangeResolutionTests(unittest.TestCase):
    """The range is where a check fails silently by reading nothing."""

    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.close)

    def test_null_base_sha_from_a_first_push_does_not_crash(self) -> None:
        """`github.event.before` is all zeros on a branch's first push."""

        self.repository.commit("chore: establish the baseline")
        self.repository.commit(
            "fix: correct the check\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        status, report = run_checker(
            self.repository, "--base", ZERO_SHA, "--head", "HEAD"
        )
        self.assertEqual(status, 1, report)
        self.assertIn("null SHA", report)
        self.assertIn("commits checked: 1", report)

    def test_null_base_sha_on_a_clean_tip_succeeds(self) -> None:
        self.repository.commit("chore: establish the baseline")
        status, report = run_checker(
            self.repository, "--base", ZERO_SHA, "--head", "HEAD"
        )
        self.assertEqual(status, 0, report)

    def test_empty_base_falls_back_to_the_head(self) -> None:
        """workflow_dispatch supplies neither base nor head context value."""

        self.repository.commit("chore: establish the baseline")
        status, report = run_checker(self.repository, "--base", "", "--head", "HEAD")
        self.assertEqual(status, 0, report)
        self.assertIn("commits checked: 1", report)

    def test_unresolvable_base_falls_back_rather_than_erroring(self) -> None:
        """A force-pushed or pruned base is no longer in the checkout."""

        self.repository.commit("chore: establish the baseline")
        status, report = run_checker(
            self.repository, "--base", "d" * 40, "--head", "HEAD"
        )
        self.assertEqual(status, 0, report)
        self.assertIn("does not resolve", report)

    def test_the_range_covers_every_commit_not_only_the_tip(self) -> None:
        """A violation mid-range must not be hidden by a clean tip."""

        base = self.repository.commit("chore: establish the baseline")
        self.repository.commit(
            "fix: adjust the check\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        self.repository.commit("docs: describe the adjustment")
        status, report = run_checker(
            self.repository, "--base", base, "--head", "HEAD"
        )
        self.assertEqual(status, 1, report)
        self.assertIn("commits checked: 2", report)

    def test_the_base_commit_itself_is_excluded(self) -> None:
        """base..head is exclusive: already-reviewed history is not re-flagged."""

        base = self.repository.commit(
            "fix: baseline\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        self.repository.commit("docs: describe the change")
        status, report = run_checker(
            self.repository, "--base", base, "--head", "HEAD"
        )
        self.assertEqual(status, 0, report)
        self.assertIn("commits checked: 1", report)

    def test_range_argument_is_supported(self) -> None:
        base = self.repository.commit("chore: establish the baseline")
        self.repository.commit(
            "fix: adjust\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        status, report = run_checker(self.repository, "--range", f"{base}..HEAD")
        self.assertEqual(status, 1, report)

    def test_fallback_depth_can_widen_the_first_push_window(self) -> None:
        self.repository.commit("chore: establish the baseline")
        self.repository.commit(
            "fix: adjust\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        self.repository.commit("docs: describe the change")
        shallow, _ = run_checker(
            self.repository, "--base", ZERO_SHA, "--head", "HEAD"
        )
        deep, report = run_checker(
            self.repository, "--base", ZERO_SHA, "--head", "HEAD",
            "--fallback-depth", "3",
        )
        self.assertEqual(shallow, 0, "the clean tip should pass on its own")
        self.assertEqual(deep, 1, report)

    def test_an_unresolvable_head_is_an_operational_error(self) -> None:
        self.repository.commit("chore: establish the baseline")
        status, _ = run_checker(self.repository, "--head", "e" * 40)
        self.assertEqual(status, 1)


class ReportHygieneTests(CommitPolicyCase):
    """The report must not republish what it rejects."""

    def test_the_report_does_not_echo_the_offending_message(self) -> None:
        report = self.assertRejected("docs: note that greedy failure rate was 25%")
        self.assertNotIn("25%", report)
        self.assertNotIn("failure rate was", report)

    def test_the_report_does_not_echo_the_offending_trailer(self) -> None:
        report = self.assertRejected(
            "fix: adjust the check\n\n"
            "Co-Authored-By: Claude <noreply@anthropic.com>"
        )
        self.assertNotIn("noreply@anthropic.com", report)
        self.assertNotIn("Claude", report)

    def test_findings_name_a_short_sha(self) -> None:
        head = self.repository.commit(
            "fix: adjust\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        status, report = run_checker(
            self.repository, "--base", self.base, "--head", "HEAD"
        )
        self.assertEqual(status, 1, report)
        self.assertIn(head[:8], report)

    def test_a_repeated_trailer_yields_one_finding(self) -> None:
        self.repository.commit(
            "fix: adjust\n\n"
            "Co-Authored-By: Claude <noreply@anthropic.com>\n"
            "Co-authored-by: Claude <noreply@anthropic.com>"
        )
        status, report = run_checker(
            self.repository, "--base", self.base, "--head", "HEAD"
        )
        self.assertEqual(status, 1, report)
        self.assertEqual(report.count("trailer attributes"), 1, report)


class WorkflowContractTests(unittest.TestCase):
    """The workflow must keep the repository's CI safety conventions."""

    def setUp(self) -> None:
        self.workflow = (
            REPO_ROOT / ".github" / "workflows" / "commit-policy.yml"
        ).read_text(encoding="utf-8")

    def test_actions_are_pinned_to_a_full_sha(self) -> None:
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", self.workflow
        )
        self.assertIn(
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            self.workflow,
        )

    def test_credentials_are_not_persisted(self) -> None:
        self.assertIn("persist-credentials: false", self.workflow)

    def test_history_is_deep_enough_to_see_every_commit(self) -> None:
        """The default fetch-depth of 1 would hide all but the tip."""

        self.assertIn("fetch-depth: 0", self.workflow)

    def test_permissions_are_read_only(self) -> None:
        self.assertIn("permissions:", self.workflow)
        self.assertIn("contents: read", self.workflow)

    def test_failures_are_not_swallowed(self) -> None:
        self.assertNotIn("continue-on-error", self.workflow)
        self.assertNotIn("|| true", self.workflow)

    def test_the_job_is_bounded_and_cancellable(self) -> None:
        self.assertIn("timeout-minutes:", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)

    def test_utf8_environment_matches_the_other_workflows(self) -> None:
        self.assertIn('PYTHONUTF8: "1"', self.workflow)
        self.assertIn('PYTHONDONTWRITEBYTECODE: "1"', self.workflow)


if __name__ == "__main__":
    unittest.main()


class KnownExceptionTests(unittest.TestCase):
    """The exception list is itself a bypass risk, so its scope is pinned.

    It exists for commits predating this check that quote prohibited phrases
    while describing a defect in the checker. Matching by pattern was refused:
    telling a quotation from an assertion is not decidable from the text, so a
    pattern-based exemption would be general-purpose.
    """

    def test_exceptions_are_listed_by_sha_not_by_pattern(self) -> None:
        for entry in checker.KNOWN_EXCEPTIONS:
            self.assertRegex(entry, r"\A[0-9a-f]{7,40}\Z", entry)

    def test_a_listed_commit_is_exempt_from_the_claim_rule(self) -> None:
        commit = checker.Commit(
            sha=sorted(checker.KNOWN_EXCEPTIONS)[0] + "0" * 8,
            message="docs: the failure rate was 25 percent",
            author_name="Someone",
            author_email="someone@example.com",
            committer_name="Someone",
            committer_email="someone@example.com",
        )
        self.assertEqual(checker.check_quantitative(commit), [])

    def test_an_unlisted_commit_is_not_exempt(self) -> None:
        commit = checker.Commit(
            sha="f" * 40,
            message="docs: the failure rate was 25 percent",
            author_name="Someone",
            author_email="someone@example.com",
            committer_name="Someone",
            committer_email="someone@example.com",
        )
        self.assertTrue(checker.check_quantitative(commit))

    def test_a_listed_commit_is_still_checked_for_ai_attribution(self) -> None:
        # The attribution rule has no exceptions; the owner asked for it to be
        # enforced strictly, and an exemption here would silently weaken it.
        commit = checker.Commit(
            sha=sorted(checker.KNOWN_EXCEPTIONS)[0] + "0" * 8,
            message="docs: something\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
            author_name="Someone",
            author_email="someone@example.com",
            committer_name="Someone",
            committer_email="someone@example.com",
        )
        self.assertTrue(checker.check_ai_attribution(commit))
