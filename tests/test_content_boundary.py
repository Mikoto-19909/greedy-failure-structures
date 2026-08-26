"""Adversarial tests for the content-boundary checker.

Every case here came from a review finding, not from reading the
implementation. That distinction is the point: the checker's earlier test suite
was written by its author from the same mental model that produced the code, so
it exercised the forms the patterns already handled and missed the rest — an
adversarial review then found 26 gaps in a checker whose own tests all passed.

So the rule for this file: a case is added because a *declaration* says the
input must be rejected, and it is verified by running it. The declarations live
in CONTRIBUTING.md, LICENSES/README.md, the workflow descriptions and the
checker's own docstrings.

A clean run of the checker is not evidence that the boundary holds; it is
evidence only that these cases are covered.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / ".github" / "scripts" / "check_content_boundary.py"

# Built at import time so a literal backslash never appears in a source string
# that some other tool might normalise.
BS = chr(92)
NUL = chr(0)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load("_boundary_checker", CHECKER)


class PersonalPathTests(unittest.TestCase):
    """CONTRIBUTING and the checker docstring both promise no personal paths."""

    def _findings(self, line: str) -> list[str]:
        return checker.check_sensitive("notes.md", line)

    def assertRejected(self, line: str) -> None:
        self.assertTrue(self._findings(line), f"not rejected: {line!r}")

    def assertAccepted(self, line: str) -> None:
        self.assertFalse(self._findings(line), f"wrongly rejected: {line!r}")

    def test_windows_backslash_paths_are_rejected(self) -> None:
        # This is a Windows-developed repository, so a native path pasted into a
        # document is the likeliest form of this leak.
        self.assertRejected(f"C:{BS}Users{BS}someone{BS}project")
        self.assertRejected(f"see C:{BS}Users{BS}someone{BS}AppData{BS}Local{BS}Temp")
        self.assertRejected(f"D:{BS}Users{BS}someone{BS}research")

    def test_windows_forward_slash_paths_are_rejected(self) -> None:
        self.assertRejected("C:/Users/someone/project")  # boundary-fixture

    def test_unc_and_extended_paths_are_rejected(self) -> None:
        self.assertRejected(f"{BS}{BS}WORKSTATION{BS}Users{BS}someone{BS}share")
        self.assertRejected(f"{BS}{BS}?{BS}C:{BS}Users{BS}someone")

    def test_posix_home_paths_are_rejected(self) -> None:
        self.assertRejected("/home/someone/project")  # boundary-fixture
        self.assertRejected("/Users/someone/project")  # boundary-fixture
        self.assertRejected("/mnt/c/Users/someone/project")  # boundary-fixture

    def test_generic_paths_are_accepted(self) -> None:
        self.assertAccepted("src/maxcover/model.py")
        self.assertAccepted("results/quick/raw_results.csv")
        self.assertAccepted("Use the user home directory.")
        self.assertAccepted("/usr/bin/python3")
        self.assertAccepted("/home/ is not a path on its own")


class CredentialTests(unittest.TestCase):
    """The checker claims to reject credential-shaped strings."""

    def _findings(self, line: str) -> list[str]:
        return checker.check_sensitive("notes.md", line)

    def assertRejected(self, line: str) -> None:
        self.assertTrue(self._findings(line), f"not rejected: {line!r}")

    def assertAccepted(self, line: str) -> None:
        self.assertFalse(self._findings(line), f"wrongly rejected: {line!r}")

    def test_private_key_headers_are_rejected_in_any_case(self) -> None:
        self.assertRejected("-----BEGIN RSA PRIVATE KEY-----")  # boundary-fixture
        self.assertRejected("-----begin rsa private key-----")  # boundary-fixture
        self.assertRejected("-----BEGIN OPENSSH PRIVATE KEY-----")  # boundary-fixture
        self.assertRejected("PuTTY-User-Key-File-2: ssh-rsa")  # boundary-fixture

    def test_provider_tokens_are_rejected(self) -> None:
        self.assertRejected("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab")  # boundary-fixture
        self.assertRejected("github_pat_ABCDEFGHIJKLMNOPQRSTUV_wxyz0123456789")  # boundary-fixture
        self.assertRejected("glpat-abcdefghijklmnopqrst")  # boundary-fixture
        self.assertRejected("xoxb-123456789012-123456789012-AbCdEfGhIjKlMnOpQrStUvWx")  # boundary-fixture
        self.assertRejected("sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")  # boundary-fixture
        self.assertRejected("npm_AbCdEfGhIjKlMnOpQrStUvWxYz0123456")  # boundary-fixture
        self.assertRejected("AIzaSyA1234567890abcdefghijklmnopqrstuv")  # boundary-fixture
        self.assertRejected("SG.abcdefghijklmnopqrstuv.abcdefghijklmnopqrstuvwxyz012345")  # boundary-fixture

    def test_aws_keys_are_rejected(self) -> None:
        self.assertRejected("AKIAIOSFODNN7EXAMPLE")  # boundary-fixture
        self.assertRejected("ASIA1234567890ABCDEF")  # boundary-fixture

    def test_url_embedded_credentials_are_rejected(self) -> None:
        self.assertRejected("https://user:sup3rs3cret@github.com/org/private.git")  # boundary-fixture
        self.assertRejected("postgres://admin:hunter2hunter2@db.internal:5432/prod")  # boundary-fixture

    def test_secret_assignments_are_rejected_with_or_without_quotes(self) -> None:
        self.assertRejected('password = "hunter2hunter2"')  # boundary-fixture
        self.assertRejected("password = hunter2hunter2")
        self.assertRejected("PASSWORD: hunter2hunter2")
        self.assertRejected("export SECRET=hunter2hunter2")
        self.assertRejected("api_key=hunter2hunter2")
        self.assertRejected('token = "hunter2hunter2"')  # boundary-fixture
        self.assertRejected('credential: "hunter2hunter2"')  # boundary-fixture
        self.assertRejected("AZURE_CLIENT_SECRET=Xq7aBcDeFgHiJkLmNoPqRsTuVwXyZ012345")

    def test_ordinary_lines_are_accepted(self) -> None:
        # A checker that flags these becomes noise that gets ignored.
        self.assertAccepted("password handling is out of scope")
        self.assertAccepted("Set the token in your own environment.")
        self.assertAccepted("secret = None  # not configured")
        self.assertAccepted('parser.add_argument("--api-key")')
        self.assertAccepted("https://github.com/org/public-repo.git")
        self.assertAccepted("https://docs.github.com/en/rest")


class BinaryClassificationTests(unittest.TestCase):
    """The docstring promises content decides what is text, not the filename.

    Two ways this was bypassable: a suffix list let a text file named .png go
    unscanned, and a single NUL byte made any file — including .md — skip all
    three checks while producing no finding at all.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, content: str | bytes) -> Path:
        target = self.dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        return target

    def assertScanned(self, path: Path) -> str:
        text, problem = checker.read_text_if_text(path)
        self.assertIsNone(problem, f"unexpected problem for {path.name}: {problem}")
        self.assertIsNotNone(text, f"{path.name} was treated as binary")
        return text or ""

    def test_text_content_is_scanned_whatever_the_suffix(self) -> None:
        secret = 'password = "hunter2hunter2"'  # boundary-fixture
        # A misleading suffix must not exempt a file from the credential scan.
        for name in ("logo.png", "archive.zip", "font.woff2", "notes.pdf"):
            with self.subTest(name=name):
                path = self._write(name, secret + "\n")
                text = self.assertScanned(path)
                self.assertTrue(
                    checker.check_sensitive(name, text),
                    f"credential not found in {name}",
                )

    def test_files_with_no_suffix_are_scanned(self) -> None:
        for name in ("Dockerfile", "Makefile", ".env", ".envrc"):
            with self.subTest(name=name):
                path = self._write(name, 'password = "hunter2hunter2"\n')  # boundary-fixture
                text = self.assertScanned(path)
                self.assertTrue(checker.check_sensitive(name, text))

    def test_a_nul_byte_does_not_silently_skip_a_file(self) -> None:
        # Previously this returned no text and no problem, so the file vanished
        # from the report entirely: it counted as binary and produced nothing.
        payload = b"# Notes\n" + bytes([0]) + b'\npassword = "hunter2hunter2"\n'
        path = self._write("docs/notes.md", payload)
        text, problem = checker.read_text_if_text(path)
        self.assertTrue(
            text is not None or problem is not None,
            "a NUL byte made the file disappear from the report",
        )

    def test_genuinely_binary_content_is_skipped_without_a_finding(self) -> None:
        # A real binary must not become noise: skipped, and not a finding.
        png = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + bytes(range(64))
        path = self._write("logo.png", png)
        text, problem = checker.read_text_if_text(path)
        self.assertIsNone(text)
        self.assertIsNone(problem)

    def test_invalid_utf8_is_reported_as_a_problem(self) -> None:
        path = self._write("notes.md", bytes([0xFF, 0xFE, 0x41, 0x42]))
        text, problem = checker.read_text_if_text(path)
        self.assertIsNone(text)
        self.assertIsNotNone(problem)

    def test_oversized_text_is_reported_as_a_problem(self) -> None:
        path = self._write("big.md", "x" * (checker.MAX_TEXT_BYTES + 1))
        text, problem = checker.read_text_if_text(path)
        self.assertIsNone(text)
        self.assertIsNotNone(problem)


class FixtureExemptionTests(unittest.TestCase):
    """The exemption marker is itself a potential bypass, so it is constrained.

    A test fixture for this checker has to contain the strings the checker
    rejects. Exempting tests/ as a directory was refused: a genuine leak could
    then be parked in a test file. So the opt-out is per line and visible.

    These cases assemble their fixtures at run time from fragments, so no line
    of this file is itself a credential-shaped string. That keeps the file clean
    without needing the marker to test the marker — which would prove nothing.
    """

    def _secret(self) -> str:
        return "pass" + "word = " + '"' + "hunter2hunter2" + '"'

    def _marked(self, line: str) -> str:
        return line + "  # " + checker.FIXTURE_MARKER

    def test_an_unmarked_line_is_still_checked(self) -> None:
        self.assertTrue(checker.check_sensitive("tests/x.py", self._secret()))

    def test_a_marked_line_is_exempt(self) -> None:
        self.assertFalse(
            checker.check_sensitive("tests/x.py", self._marked(self._secret()))
        )

    def test_the_marker_exempts_only_its_own_line(self) -> None:
        text = self._marked(self._secret()) + "\n" + self._secret() + "\n"
        findings = checker.check_sensitive("tests/x.py", text)
        self.assertEqual(len(findings), 1, findings)
        self.assertIn(":2:", findings[0])

    def test_the_marker_applies_in_any_file_not_just_tests(self) -> None:
        # Deliberate: the marker is auditable wherever it appears, and scoping it
        # to a directory would recreate the exemption it replaced.
        self.assertFalse(
            checker.check_sensitive("README.md", self._marked(self._secret()))
        )


class QuantitativeClaimTests(unittest.TestCase):
    """CONTRIBUTING says the single-claim-source rule is enforced, not requested.

    Adversarial review found roughly sixteen English rephrasings, every Chinese
    formulation, table rows and statements split across lines all passing. The
    cause was a closed vocabulary of metric names and outcome verbs: anything
    said another way went through.
    """

    def _findings(self, text: str) -> list[str]:
        return checker.check_quantitative("notes.md", text, "no_quantitative_claims")

    def assertRejected(self, text: str) -> None:
        self.assertTrue(self._findings(text), f"not rejected: {text!r}")

    def assertAccepted(self, text: str) -> None:
        self.assertFalse(self._findings(text), f"wrongly rejected: {text!r}")

    def test_metric_stated_with_a_value(self) -> None:
        self.assertRejected("The failure rate was 25%.")
        self.assertRejected("The optimality gap was 10%.")
        self.assertRejected("The runtime was 3 seconds.")
        self.assertRejected("The approximation ratio is 0.63.")
        self.assertRejected("Mean approximation ratio was 0.63 across the corpus.")
        self.assertRejected("Regret was 0.38 on average.")
        self.assertRejected("Mean shortfall 0.38 (n=120)")

    def test_metric_assigned_a_value(self) -> None:
        self.assertRejected("mean gap: 0.24")
        self.assertRejected("speedup = 3.2")
        self.assertRejected("Elapsed time: 12.4 s")

    def test_outcome_paired_with_a_number(self) -> None:
        self.assertRejected("Greedy covered 80% of elements.")
        self.assertRejected("Greedy loses 38 percent of the optimum on this family.")
        self.assertRejected("Greedy reaches 62 percent of the optimum.")
        self.assertRejected("Local search recovered 82% of the gap.")
        self.assertRejected("The solver visited 41200 nodes.")

    def test_comparative_ratios(self) -> None:
        self.assertRejected("The heuristic is 3.2 times slower than branch and bound.")
        self.assertRejected("Branch and bound needs 4.5x fewer nodes.")
        self.assertRejected("Wall-clock time was 12.4 seconds for the full sweep.")

    def test_percentage_with_a_corpus_noun(self) -> None:
        self.assertRejected("45% of instances showed a deficit.")
        self.assertRejected("24 percent was the observed shortfall.")
        self.assertRejected("Twenty-five percent of instances defeat greedy.")

    def test_table_rows(self) -> None:
        self.assertRejected("| greedy | 0.62 | 41200 |")
        self.assertRejected("| algorithm | coverage | nodes |\n| greedy | 0.62 | 41200 |")

    def test_statements_split_across_lines(self) -> None:
        # Markdown renders these as one sentence, so line-at-a-time matching
        # missed them entirely.
        self.assertRejected("The failure rate\nwas 25%.")
        self.assertRejected("Greedy covered\n80% of elements.")

    def test_chinese_formulations(self) -> None:
        self.assertRejected("贪心算法的失败率为 25%。")
        self.assertRejected("覆盖率 0.62，最优间隙 0.38。")
        self.assertRejected("在 45% 的实例上贪心失败。")
        self.assertRejected("贪心比精确解慢 3.2 倍。")
        self.assertRejected("平均近似比 0.63。")

    def test_bare_numbers_stay_legal(self) -> None:
        # The comment above the patterns promises this, and a checker that
        # flags these becomes noise that gets ignored.
        self.assertAccepted("Python 3.11 or newer is required.")
        self.assertAccepted("The Python 3 runtime is supported.")
        self.assertAccepted("The runtime is 3.11 or newer.")
        self.assertAccepted("mypy 2.3.0 is pinned.")
        self.assertAccepted("Use 2 workers for the starter run.")
        self.assertAccepted("timeout_seconds: 60")
        self.assertAccepted("timeout-minutes: 10")
        self.assertAccepted("The manifest lists 74 files.")
        self.assertAccepted("base_seed 2026 controls all runs")
        self.assertAccepted("universe_size 80 with 14 sets")
        self.assertAccepted("CLI exit codes: 0 success, 1 operational error.")
        self.assertAccepted("results/ci-quick holds 48 algorithm runs")

    def test_boundary_conditions_stay_legal(self) -> None:
        # Definitional and degenerate statements are not results.
        self.assertAccepted("objective = 0 for the empty solution.")
        self.assertAccepted("gap = 0 means the bound is closed.")
        self.assertAccepted("Coverage is 1 when every element is covered.")
        self.assertAccepted(
            "The failure rate is defined as the fraction of instances "
            "where greedy is suboptimal."
        )

    def test_repository_prose_stays_legal(self) -> None:
        # Real sentences from this repository's own documents.
        self.assertAccepted(
            "Runtime observations can vary with the machine and optional solver."
        )
        self.assertAccepted(
            "The starter workflow is a functional check, not a performance claim."
        )
        self.assertAccepted(
            "no experiment results, no performance comparisons, no measurements"
        )
        self.assertAccepted("Treat timeouts as incomplete work, not proof of optimality.")

    def test_non_prose_files_are_not_claim_checked(self) -> None:
        # Section headings in reporting code would otherwise trip this.
        source = 'HEADING = "## P5.2 classical Greedy failure rate"'
        self.assertFalse(
            checker.check_quantitative("src/x.py", source, "no_quantitative_claims")
        )

    def test_a_wider_claim_mode_defers_to_its_own_workflow(self) -> None:
        self.assertFalse(
            checker.check_quantitative(
                "notes.md", "The failure rate was 25%.", "evidence_backed_claims"
            )
        )


class LinkResolutionTests(unittest.TestCase):
    """The docstring promises every relative link resolves, in every syntax.

    Review found it promised more than it did: only `[text](target)` was parsed,
    so reference-style and HTML links were unchecked, and `C:` was skipped as a
    URL scheme, which made a Windows path in a link invisible to *both* this
    check and the personal-path check.
    """

    # A tracked-name set standing in for a repository.
    KNOWN = frozenset({"README.md", "docs/guide.md", "LICENSES/README.md"})
    DIRS = frozenset({"docs", "LICENSES"})

    def _findings(self, text: str, path: str = "README.md") -> list[str]:
        return checker.check_links(path, text, self.KNOWN, self.DIRS)

    def assertRejected(self, text: str, path: str = "README.md") -> None:
        self.assertTrue(self._findings(text, path), f"not rejected: {text!r}")

    def assertAccepted(self, text: str, path: str = "README.md") -> None:
        findings = self._findings(text, path)
        self.assertFalse(findings, f"wrongly rejected: {text!r} -> {findings}")

    def test_inline_links_are_checked(self) -> None:
        self.assertAccepted("[guide](docs/guide.md)")
        self.assertRejected("[missing](docs/absent.md)")

    def test_angle_bracket_destinations_are_checked(self) -> None:
        # `[text](<path with space>)` is valid CommonMark and the old pattern
        # stopped at the first whitespace, silently truncating the target.
        self.assertAccepted("[guide](<docs/guide.md>)")
        self.assertRejected("[missing](<docs/a file.md>)")

    def test_reference_style_definitions_are_checked(self) -> None:
        self.assertAccepted("See [the guide][g].\n\n[g]: docs/guide.md")
        self.assertRejected("See [the guide][g].\n\n[g]: docs/absent.md")

    def test_an_undefined_reference_label_is_not_reported(self) -> None:
        # Deliberately not a finding, reversing an earlier decision in this
        # file. `[text][nowhere]` renders as literal text, so it is not a broken
        # link — the same reasoning that excludes autolinks. Reporting it flagged
        # ordinary prose instead: an index expression outside backticks and a
        # citation form are indistinguishable from a mistyped label.
        self.assertAccepted("See [the guide][nowhere].")
        self.assertAccepted("Use sets[i][j] for the bitmask.")
        self.assertAccepted("See [1][2] for context.")
        self.assertAccepted("Compare data[0][1] against the reference.")

    def test_collapsed_reference_definitions_are_checked(self) -> None:
        self.assertAccepted("See [guide][].\n\n[guide]: docs/guide.md")
        self.assertRejected("See [guide][].\n\n[guide]: docs/absent.md")

    def test_reference_labels_collapse_internal_whitespace(self) -> None:
        # CommonMark folds a whitespace run inside a label, so these are one
        # label and the definition applies. Only stripping made them differ.
        self.assertAccepted("[g][a  b]\n\n[a b]: docs/guide.md")

    def test_footnote_definitions_are_not_link_definitions(self) -> None:
        # A GFM footnote's text is prose. Parsed as a destination, the prose
        # itself became a broken target.
        self.assertAccepted("Text.[^1]\n\n[^1]: See the guide for details.")

    def test_html_attribute_links_are_checked(self) -> None:
        self.assertAccepted('<a href="docs/guide.md">guide</a>')
        self.assertRejected('<a href="docs/absent.md">guide</a>')
        self.assertRejected("<img src='docs/absent.png'>")
        self.assertRejected("<a href=docs/absent.md>unquoted</a>")

    def test_image_links_are_checked(self) -> None:
        self.assertRejected("![chart](docs/absent.svg)")

    def test_a_windows_drive_path_is_not_treated_as_a_url_scheme(self) -> None:
        # Double miss: EXTERNAL matched `C:` as a scheme, so the link check
        # skipped it, and it sat inside link syntax rather than as bare text.
        drive = "C:" + BS + "Users" + BS + "someone" + BS + "notes.md"
        self.assertRejected(f"[notes]({drive})")

    def test_real_url_schemes_are_still_skipped(self) -> None:
        self.assertAccepted("[site](https://example.com/a/b)")
        self.assertAccepted("[mail](mailto:someone@example.com)")
        self.assertAccepted("[proto](ftp://example.com/x)")
        self.assertAccepted("[anchor](#section)")
        self.assertAccepted("[protocol-relative](//example.com/x)")

    def test_case_differences_are_reported_distinctly(self) -> None:
        # Path.exists() made this pass on Windows and 404 on github.com. The
        # message has to say so, or a Windows contributor cannot see the fault.
        findings = self._findings("[guide](docs/Guide.md)")
        self.assertTrue(findings)
        self.assertIn("case", findings[0])

    def test_links_to_directories_resolve(self) -> None:
        self.assertAccepted("[licences](LICENSES)")
        self.assertAccepted("[licences](LICENSES/)")

    def test_root_relative_links_resolve(self) -> None:
        self.assertAccepted("[guide](/docs/guide.md)", path="docs/guide.md")
        self.assertRejected("[missing](/docs/absent.md)", path="docs/guide.md")

    def test_relative_links_resolve_against_the_linking_file(self) -> None:
        self.assertAccepted("[readme](../README.md)", path="docs/guide.md")
        self.assertRejected("[escape](../../outside.md)", path="docs/guide.md")

    def test_anchors_and_queries_are_stripped_before_resolving(self) -> None:
        self.assertAccepted("[guide](docs/guide.md#section)")
        self.assertRejected("[missing](docs/absent.md#section)")

    def test_link_syntax_in_code_is_not_a_link(self) -> None:
        # A fenced example shows syntax; it does not link anywhere.
        self.assertAccepted("```\n[example](docs/absent.md)\n```")
        self.assertAccepted("~~~md\n[example](docs/absent.md)\n~~~")
        # An inline span does the same, and an index expression is not a
        # reference-style link.
        self.assertAccepted("Write `[text](docs/absent.md)` to link.")
        self.assertAccepted("Use `sets[i][j]` for the bitmask.")

    def test_a_fence_is_closed_only_by_its_own_marker(self) -> None:
        # A ``` inside a ~~~ block must not end it, or the rest of the file
        # would be scanned as prose while the block stays open.
        text = "~~~\n```\n[example](docs/absent.md)\n```\n~~~\n"
        self.assertAccepted(text)

    def test_non_markdown_files_are_not_link_checked(self) -> None:
        self.assertAccepted("[missing](docs/absent.md)", path="src/x.py")

    def test_reported_line_numbers_survive_code_blanking(self) -> None:
        text = "```\nfenced\n```\n\n[missing](docs/absent.md)\n"
        findings = self._findings(text)
        self.assertTrue(findings)
        self.assertIn(":5:", findings[0])

    def test_the_fixture_marker_exempts_a_link_line(self) -> None:
        marker = "  <!-- " + checker.FIXTURE_MARKER + " -->"
        self.assertAccepted("[missing](docs/absent.md)" + marker)


class FenceStateMachineTests(unittest.TestCase):
    """CommonMark 4.5 decides when a fence closes, and a mistake inverts parity.

    This class exists because a second review found the earlier fence handling
    worse than no fence handling at all. A closer mistaken for an opener flips
    the parity of the rest of the file: a real broken link becomes invisible
    while a line of actual code gets reported at a wrong line number. Since the
    workflow runs this check without `continue-on-error`, one direction blocks
    valid documentation and the other ships a broken link silently.
    """

    KNOWN = frozenset({"README.md", "docs/guide.md"})
    DIRS = frozenset({"docs"})

    def _findings(self, text: str) -> list[str]:
        return checker.check_links("README.md", text, self.KNOWN, self.DIRS)

    def assertRejected(self, text: str) -> None:
        self.assertTrue(self._findings(text), f"not rejected: {text!r}")

    def assertAccepted(self, text: str) -> None:
        findings = self._findings(text)
        self.assertFalse(findings, f"wrongly rejected: {text!r} -> {findings}")

    def test_a_closing_fence_carries_no_info_string(self) -> None:
        # ```console twice is two openers, not open-and-close. This repository's
        # own documents use exactly that style, so the desync was one editing
        # accident away from hiding a real broken link.
        text = (
            "```console\npython run_project.py demo\n"
            "```console\npython run_project.py quick\n```\n\n"
            "[broken](docs/absent.md)\n"
        )
        self.assertRejected(text)

    def test_a_closer_must_be_at_least_as_long_as_its_opener(self) -> None:
        text = "````\nx\n```\ny\n````\n\n[broken](docs/absent.md)\n"
        self.assertRejected(text)

    def test_code_inside_a_desynced_block_is_not_reported(self) -> None:
        # The other half of the same defect: real code read as prose.
        text = "```console\npython demo\n```console\npython quick\n```\n"
        self.assertAccepted(text)

    def test_a_fence_is_closed_only_by_its_own_character(self) -> None:
        self.assertAccepted("~~~\n```\n[x](docs/absent.md)\n```\n~~~\n")

    def test_an_info_string_on_an_opener_is_allowed(self) -> None:
        self.assertAccepted("```py\n[x](docs/absent.md)\n```\n")

    def test_an_unclosed_fence_runs_to_the_end(self) -> None:
        self.assertAccepted("```\n[x](docs/absent.md)\n")

    def test_indented_code_blocks_are_code(self) -> None:
        self.assertAccepted("text\n\n    [x](docs/absent.md)\n")

    def test_four_spaces_continuing_a_paragraph_are_not_code(self) -> None:
        # Without the blank line this is a lazy continuation, so the link is
        # real and must be reported.
        self.assertRejected("See the guide\n    [x](docs/absent.md)\n")

    def test_double_backtick_spans_are_code(self) -> None:
        # A span opened with two backticks may contain single ones; that is how
        # a literal backtick is written.
        self.assertAccepted("Write ``[x](docs/absent.md)`` to link.")

    def test_the_line_count_is_preserved(self) -> None:
        # Reported line numbers depend on this, across awkward inputs.
        for text in (
            "```\nx\n",
            "a\n```\nb",
            "```\r\nx\r\n```\r\n",
            "",
            "```",
            "```py\nx\n```\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    len(checker._blank_code(text)), len(text.split("\n"))
                )

    def test_a_reported_line_number_survives_a_desync_candidate(self) -> None:
        text = "```console\nx\n```\n\n```console\ny\n```\n\n[b](docs/absent.md)\n"
        findings = self._findings(text)
        self.assertTrue(findings)
        self.assertIn(":9:", findings[0])


class NestedLinkSyntaxTests(unittest.TestCase):
    """Link text may contain brackets, so a character class cannot parse it.

    The badge pattern `[![alt](img)](target)` is the most common link shape in a
    public README, and a pattern stopping at the first `]` saw neither of its
    two links.
    """

    KNOWN = frozenset({"README.md", "docs/guide.md", "docs/a file.md"})
    DIRS = frozenset({"docs"})

    def _findings(self, text: str) -> list[str]:
        return checker.check_links("README.md", text, self.KNOWN, self.DIRS)

    def assertRejected(self, text: str) -> None:
        self.assertTrue(self._findings(text), f"not rejected: {text!r}")

    def assertAccepted(self, text: str) -> None:
        findings = self._findings(text)
        self.assertFalse(findings, f"wrongly rejected: {text!r} -> {findings}")

    def test_a_badge_links_are_both_checked(self) -> None:
        self.assertRejected("[![alt](docs/guide.md)](docs/absent.md)")
        self.assertRejected("[![alt](docs/absent.svg)](docs/guide.md)")
        self.assertAccepted("[![alt](docs/guide.md)](docs/guide.md)")

    def test_brackets_inside_link_text_are_allowed(self) -> None:
        self.assertRejected("[see [this] now](docs/absent.md)")
        self.assertAccepted("[see [this] now](docs/guide.md)")

    def test_escaped_brackets_are_literal_text(self) -> None:
        self.assertAccepted(BS + "[not a link" + BS + "](docs/absent.md)")

    def test_a_link_split_across_lines_is_checked(self) -> None:
        # Markdown renders consecutive lines as one sentence, so this is a real
        # link that line-at-a-time matching missed.
        self.assertRejected("See [the guide](\ndocs/absent.md).")
        self.assertAccepted("See [the guide](\ndocs/guide.md).")

    def test_a_title_is_not_part_of_the_destination(self) -> None:
        self.assertRejected('[x](docs/absent.md "title")')
        self.assertAccepted('[x](docs/guide.md "title")')

    def test_percent_encoding_is_decoded_before_resolving(self) -> None:
        # The standard way to link a tracked filename containing a space.
        self.assertAccepted("[x](docs/a%20file.md)")
        self.assertRejected("[x](docs/absent%20file.md)")

    def test_multiple_links_on_one_line(self) -> None:
        findings = self._findings("[a](docs/absent.md) and [b](docs/other.md)")
        self.assertEqual(len(findings), 2, findings)


class MarkdownScopeTests(unittest.TestCase):
    """Link checking applies to what GitHub renders as Markdown, and says so."""

    KNOWN = frozenset({"README.md"})
    DIRS = frozenset()

    def _findings(self, path: str) -> list[str]:
        return checker.check_links(path, "[x](docs/absent.md)", self.KNOWN, self.DIRS)

    def test_markdown_suffixes_are_checked(self) -> None:
        for name in ("notes.md", "notes.markdown", "notes.MD"):
            with self.subTest(name=name):
                self.assertTrue(self._findings(name), name)

    def test_non_markdown_prose_is_not_link_checked(self) -> None:
        # `.rst` and `.txt` are claim-scanned, but a [x](y) in them is literal
        # text, so reporting its target would name a path no reader can click.
        for name in ("notes.txt", "notes.rst", "src/x.py"):
            with self.subTest(name=name):
                self.assertFalse(self._findings(name), name)


class CaseDifferenceTests(unittest.TestCase):
    """The wrong-case message asserts a specific platform behaviour, so it has
    to be right about which failure occurred."""

    KNOWN = frozenset({"docs/guide.md", "docs/strasse.md"})
    DIRS = frozenset({"docs", "LICENSES"})

    def _findings(self, target: str) -> list[str]:
        return checker.check_links(
            "README.md", f"[x]({target})", self.KNOWN, self.DIRS
        )

    def test_a_case_difference_says_so(self) -> None:
        findings = self._findings("docs/Guide.md")
        self.assertTrue(findings)
        self.assertIn("case", findings[0])

    def test_a_directory_case_difference_says_so(self) -> None:
        findings = self._findings("licenses")
        self.assertTrue(findings)
        self.assertIn("case", findings[0])

    def test_a_distinct_name_is_not_called_a_case_difference(self) -> None:
        # casefold() maps the sharp s to "ss", so this genuinely different
        # filename was reported as a mere case difference, with a message
        # claiming it resolves on Windows when it resolves nowhere.
        findings = self._findings("docs/stra" + chr(223) + ".md")
        self.assertTrue(findings)
        self.assertNotIn("case", findings[0])
        self.assertIn("does not resolve", findings[0])


class SecretPlaceholderTests(unittest.TestCase):
    """A bare secret assignment ends at whitespace, not at the line end.

    Found while probing whether code blanking had leaked into the credential
    check. It had not — but anchoring the bare-assignment pattern to the line end
    meant anything following the value hid it, which is the common shape in prose
    and in a documented example. Neither earlier review found this.

    Widening it required an exclusion for the placeholder forms documentation
    uses to show how to supply a secret without containing one.
    """

    def _findings(self, line: str) -> list[str]:
        return checker.check_sensitive("notes.md", line)

    def assertRejected(self, line: str) -> None:
        self.assertTrue(self._findings(line), f"not rejected: {line!r}")

    def assertAccepted(self, line: str) -> None:
        self.assertFalse(self._findings(line), f"wrongly rejected: {line!r}")

    def _secret(self) -> str:
        return "hunter2" + "hunter2"

    def test_a_value_followed_by_prose_is_still_a_secret(self) -> None:
        self.assertRejected("Set password = " + self._secret() + " here.")
        self.assertRejected("export SECRET=" + self._secret() + "  # staging")

    def test_a_value_inside_a_code_span_is_still_a_secret(self) -> None:
        self.assertRejected("Set `password = " + self._secret() + "` here.")

    def test_a_value_inside_a_fence_is_still_a_secret(self) -> None:
        # Only link checking ignores code. A leaked credential in a fenced
        # example is still published.
        self.assertRejected("```\npassword = " + self._secret() + "\n```")

    def test_documented_placeholders_are_accepted(self) -> None:
        # Flagging these blocks correct documentation, and a check that blocks
        # correct documentation gets disabled.
        for value in (
            "<your-password>",
            "${GITHUB_TOKEN}",
            "$API_KEY",
            "%USERPASS%",
            "{{ secrets.GITHUB_TOKEN }}",
            "os.environ['API_KEY']",
            "REDACTED",
            "CHANGEME",
            "xxxxxxxxxx",
        ):
            with self.subTest(value=value):
                self.assertAccepted(f"password = {value}")

    def test_a_placeholder_prefix_does_not_launder_a_real_value(self) -> None:
        # The exclusion requires the whole value to be the placeholder.
        self.assertRejected("password = <tag>" + self._secret())
