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
