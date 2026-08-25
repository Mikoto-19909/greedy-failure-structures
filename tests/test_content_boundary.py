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
        self.assertRejected("C:/Users/someone/project")

    def test_unc_and_extended_paths_are_rejected(self) -> None:
        self.assertRejected(f"{BS}{BS}WORKSTATION{BS}Users{BS}someone{BS}share")
        self.assertRejected(f"{BS}{BS}?{BS}C:{BS}Users{BS}someone")

    def test_posix_home_paths_are_rejected(self) -> None:
        self.assertRejected("/home/someone/project")
        self.assertRejected("/Users/someone/project")
        self.assertRejected("/mnt/c/Users/someone/project")

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
        self.assertRejected("-----BEGIN RSA PRIVATE KEY-----")
        self.assertRejected("-----begin rsa private key-----")
        self.assertRejected("-----BEGIN OPENSSH PRIVATE KEY-----")
        self.assertRejected("PuTTY-User-Key-File-2: ssh-rsa")

    def test_provider_tokens_are_rejected(self) -> None:
        self.assertRejected("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab")
        self.assertRejected("github_pat_ABCDEFGHIJKLMNOPQRSTUV_wxyz0123456789")
        self.assertRejected("glpat-abcdefghijklmnopqrst")
        self.assertRejected("xoxb-123456789012-123456789012-AbCdEfGhIjKlMnOpQrStUvWx")
        self.assertRejected("sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")
        self.assertRejected("npm_AbCdEfGhIjKlMnOpQrStUvWxYz0123456")
        self.assertRejected("AIzaSyA1234567890abcdefghijklmnopqrstuv")
        self.assertRejected("SG.abcdefghijklmnopqrstuv.abcdefghijklmnopqrstuvwxyz012345")

    def test_aws_keys_are_rejected(self) -> None:
        self.assertRejected("AKIAIOSFODNN7EXAMPLE")
        self.assertRejected("ASIA1234567890ABCDEF")

    def test_url_embedded_credentials_are_rejected(self) -> None:
        self.assertRejected("https://user:sup3rs3cret@github.com/org/private.git")
        self.assertRejected("postgres://admin:hunter2hunter2@db.internal:5432/prod")

    def test_secret_assignments_are_rejected_with_or_without_quotes(self) -> None:
        self.assertRejected('password = "hunter2hunter2"')
        self.assertRejected("password = hunter2hunter2")
        self.assertRejected("PASSWORD: hunter2hunter2")
        self.assertRejected("export SECRET=hunter2hunter2")
        self.assertRejected("api_key=hunter2hunter2")
        self.assertRejected('token = "hunter2hunter2"')
        self.assertRejected('credential: "hunter2hunter2"')
        self.assertRejected("AZURE_CLIENT_SECRET=Xq7aBcDeFgHiJkLmNoPqRsTuVwXyZ012345")

    def test_ordinary_lines_are_accepted(self) -> None:
        # A checker that flags these becomes noise that gets ignored.
        self.assertAccepted("password handling is out of scope")
        self.assertAccepted("Set the token in your own environment.")
        self.assertAccepted("secret = None  # not configured")
        self.assertAccepted('parser.add_argument("--api-key")')
        self.assertAccepted("https://github.com/org/public-repo.git")
        self.assertAccepted("https://docs.github.com/en/rest")
