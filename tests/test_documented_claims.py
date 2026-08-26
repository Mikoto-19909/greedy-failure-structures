"""Tests that the documentation's narrowed claims still match the code.

Batch 7 of the adversarial review found three places where a document claimed
more than the implementation delivered:

- the README said this repository publishes "no measurements" while `demo`
  prints a coverage gap to the terminal;
- it recommended two commands that both emit a deprecation warning, without
  saying so;
- it called mypy a "typed baseline" while 40% of the source is exempt from the
  check by line.

Each was fixed by narrowing the claim rather than by changing behaviour, since
migrating the configs would change `config_hash` and clearing the type backlog
is separate work. A narrowed claim drifts as easily as a wide one, so each is
pinned here against the thing it describes.

These tests read the documents and the configuration. They deliberately do not
re-check the wording with a pattern: asserting that a sentence exists verbatim
makes every copy-edit a test failure, which is how a test gets deleted. They
assert the *facts* the sentences depend on, so the test fails when the code and
the document diverge, not when the prose is rephrased.
"""

from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


class LegacyConfigClaimTests(unittest.TestCase):
    """The README says which configs are legacy. That list must stay true."""

    def _schema_version(self, name: str) -> int:
        payload = json.loads(_read(f"configs/{name}"))
        return int(payload["schema_version"])

    def test_the_two_named_legacy_configs_are_still_schema_v1(self) -> None:
        # If either is migrated, the README paragraph explaining the warning
        # becomes wrong and the warning it prepares the reader for is gone.
        self.assertEqual(self._schema_version("quick.json"), 1)
        self.assertEqual(self._schema_version("full.json"), 1)

    def test_sweeps_is_still_schema_v2(self) -> None:
        self.assertEqual(self._schema_version("sweeps.json"), 2)

    def test_no_other_config_is_legacy_without_being_named(self) -> None:
        # The README names exactly two warning configs. A third would make the
        # documented list incomplete rather than merely stale.
        named = {"quick.json", "full.json"}
        legacy = {
            path.name
            for path in sorted((REPO_ROOT / "configs").glob("*.json"))
            if int(json.loads(path.read_text(encoding="utf-8"))["schema_version"]) == 1
        }
        self.assertEqual(
            legacy,
            named,
            "the set of schema-v1 configs changed; update the README paragraph "
            "that names them and explains the LegacyConfigWarning",
        )

    def test_the_readme_still_warns_the_reader(self) -> None:
        readme = _read("README.md")
        self.assertIn("LegacyConfigWarning", readme)
        self.assertIn("configs/quick.json", readme)


class TypeCheckClaimTests(unittest.TestCase):
    """The README quantifies the mypy exemption. The number must stay honest."""

    def _exempt_modules(self) -> list[str]:
        config = tomllib.loads(_read("pyproject.toml"))
        modules: list[str] = []
        for override in config["tool"]["mypy"].get("overrides", []):
            if override.get("ignore_errors"):
                value = override["module"]
                modules += [value] if isinstance(value, str) else list(value)
        return modules

    def test_the_documented_modules_are_the_exempt_ones(self) -> None:
        self.assertEqual(
            sorted(self._exempt_modules()),
            ["maxcover.benchmark", "maxcover.contracts", "maxcover.reporting"],
            "the mypy exemption list changed; README.md and CONTRIBUTING.md "
            "both name these three modules",
        )

    def test_the_exempt_share_is_still_about_forty_percent(self) -> None:
        # Both documents say "about 40% of the source by line". A drift past a
        # few points makes the figure misleading in one direction or the other.
        source = sorted((REPO_ROOT / "src" / "maxcover").rglob("*.py"))
        total = sum(
            len(path.read_text(encoding="utf-8").splitlines()) for path in source
        )
        self.assertGreater(total, 0)
        exempt = 0
        for module in self._exempt_modules():
            path = REPO_ROOT / "src" / (module.replace(".", "/") + ".py")
            self.assertTrue(path.exists(), f"exempt module not found: {module}")
            exempt += len(path.read_text(encoding="utf-8").splitlines())
        share = exempt * 100 / total
        self.assertTrue(
            30 <= share <= 50,
            f"exempt share is now {share:.0f}% of source lines; both README.md "
            "and CONTRIBUTING.md state about 40%",
        )

    def test_both_documents_qualify_the_clean_mypy_run(self) -> None:
        # The defect was an unqualified claim, so the qualification is the fix
        # and has to survive edits to either file.
        for name in ("README.md", "CONTRIBUTING.md"):
            with self.subTest(document=name):
                text = _read(name)
                self.assertIn("ignore_errors", text)


class ScopeClaimTests(unittest.TestCase):
    """The scope boundary must distinguish publishing from computing.

    `demo` prints a coverage gap and a benchmark writes measurement CSVs. An
    unqualified "no measurements" is contradicted by the terminal, which is the
    kind of gap that makes a reader distrust the rest of the boundary.
    """

    def test_the_readme_scope_section_acknowledges_computed_numbers(self) -> None:
        readme = _read("README.md")
        self.assertIn("## Scope", readme)
        scope = readme.split("## Scope", 1)[1]
        self.assertIn("demo", scope)

    def test_contributing_scopes_the_rule_to_what_is_tracked(self) -> None:
        text = _read("CONTRIBUTING.md")
        self.assertIn("results/", text)

    def test_results_are_not_tracked(self) -> None:
        # The narrowed claim rests on generated output being untracked. If
        # `results/` were ever committed, the distinction would collapse.
        ignore = _read(".gitignore")
        self.assertIn("results/", ignore)


if __name__ == "__main__":
    unittest.main()
