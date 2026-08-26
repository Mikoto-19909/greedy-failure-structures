"""Tests that the package version is stated once, consistently.

The version appears in two places — `pyproject.toml` and `maxcover.__version__`
— and nothing kept them equal. That matters beyond tidiness: the release process
treats a disagreement between the package version and the tag as a stop
condition, and a drift here would only surface at that point, after a tag had
already been considered.

These tests do not assert a particular version number. Pinning the value would
make every release edit this file, which is how a test starts being updated
mechanically instead of read. They assert the two sources agree and that the
value is a well-formed release version.
"""

from __future__ import annotations

import re
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# A release version, not an arbitrary string: three dot-separated numbers, with
# an optional pre-release suffix.
VERSION = re.compile(r"\A\d+\.\d+\.\d+(?:[-.]?(?:a|b|rc|alpha|beta|dev)\d*)?\Z")


class VersionConsistencyTests(unittest.TestCase):
    def _packaging_version(self) -> str:
        payload = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        return str(payload["project"]["version"])

    def _runtime_version(self) -> str:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        try:
            import maxcover

            return str(maxcover.__version__)
        finally:
            sys.path.remove(str(REPO_ROOT / "src"))

    def test_the_packaging_and_runtime_versions_agree(self) -> None:
        packaging = self._packaging_version()
        runtime = self._runtime_version()
        self.assertEqual(
            packaging,
            runtime,
            "pyproject.toml and maxcover.__version__ disagree; a release would "
            "then ship a package whose reported version is not its own",
        )

    def test_the_version_is_a_well_formed_release_version(self) -> None:
        version = self._packaging_version()
        self.assertRegex(version, VERSION)

    def test_the_version_is_not_a_placeholder(self) -> None:
        # 0.0.0 and 1.0.0-by-default are the two values that arrive without
        # anyone deciding them.
        self.assertNotEqual(self._packaging_version(), "0.0.0")


if __name__ == "__main__":
    unittest.main()
