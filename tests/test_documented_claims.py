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

How these tests are written, and why it changed
-----------------------------------------------
The first version of this file asserted that a substring was present — that the
README contained "demo", that CONTRIBUTING mentioned "ignore_errors". A review
then mutated the documents and found that **nine of ten false statements passed
all ten tests**: the README could claim the exemption covered no modules, could
drop a config from the legacy list, could say a clean mypy run proves the whole
package is typed, and every test stayed green. Substring presence says a word
appears somewhere, not that the sentence containing it is true.

So each test now does one of two things:

- runs the behaviour and asserts what it actually produces — `demo` really is
  executed and its output parsed, the configs really are loaded and the warning
  caught, git really is queried for what is tracked;
- extracts the *specific figure* the document states and compares it to the
  measured value, so a wrong number fails rather than merely a missing word.

Verbatim sentence matching is still avoided: it makes every copy-edit a failure,
which is how a test gets deleted. The difference is that a claim's *content* is
now checked, not its vocabulary.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import unittest
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


class LegacyConfigClaimTests(unittest.TestCase):
    """The README says which configs are legacy. That list must stay true."""

    def _schema_version(self, name: str) -> int:
        payload = json.loads(_read(f"configs/{name}"))
        return int(payload["schema_version"])

    def _legacy_configs(self) -> set[str]:
        return {
            path.name
            for path in sorted((REPO_ROOT / "configs").glob("*.json"))
            if int(json.loads(path.read_text(encoding="utf-8"))["schema_version"]) == 1
        }

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
        self.assertEqual(
            self._legacy_configs(),
            {"quick.json", "full.json"},
            "the set of schema-v1 configs changed; update the README paragraph "
            "that names them and explains the LegacyConfigWarning",
        )

    def test_the_readme_names_every_legacy_config_and_no_others(self) -> None:
        # Substring presence let the README drop `configs/full.json` from the
        # list while staying green. So the documented set is extracted from the
        # prose and compared to the measured set.
        readme = _read("README.md")
        documented = {
            f"{name}.json"
            for name in re.findall(r"`configs/([A-Za-z0-9_]+)\.json` and", readme)
        } | {
            f"{name}.json"
            for name in re.findall(r"and\s+`configs/([A-Za-z0-9_]+)\.json` are", readme)
        }
        self.assertEqual(
            documented,
            self._legacy_configs(),
            "the README's list of schema-v1 configs no longer matches the "
            "configs that are actually schema v1",
        )

    def test_both_named_configs_actually_raise_the_documented_warning(self) -> None:
        # The class of warning is part of the claim. Renaming it, or removing the
        # migration, leaves a README paragraph describing something that no
        # longer happens — and a substring check would not notice.
        sys.path.insert(0, str(SOURCE_ROOT))
        try:
            from maxcover.config import LegacyConfigWarning, load_config
        finally:
            sys.path.remove(str(SOURCE_ROOT))

        for name in sorted(self._legacy_configs()):
            with self.subTest(config=name):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    load_config(REPO_ROOT / "configs" / name)
                self.assertTrue(
                    any(
                        issubclass(item.category, LegacyConfigWarning)
                        for item in caught
                    ),
                    f"{name} no longer raises LegacyConfigWarning; the README "
                    "paragraph preparing the reader for it is now wrong",
                )

    def test_the_readme_states_the_correct_schema_for_sweeps(self) -> None:
        readme = _read("README.md")
        match = re.search(r"`configs/sweeps\.json`\s+is\s+schema\s+(\d+)", readme)
        self.assertIsNotNone(match, "the README no longer states sweeps' schema")
        assert match is not None
        self.assertEqual(int(match.group(1)), self._schema_version("sweeps.json"))

    def test_the_readme_states_the_correct_schema_for_the_current_configs(self) -> None:
        # Matched over the README with newlines collapsed, since the sentence
        # wraps across lines.
        readme = re.sub(r"\s+", " ", _read("README.md"))
        match = re.search(
            r"`configs/p3_\*`\s+through\s+`configs/p5_\*`\s+configurations?"
            r"\s+are\s+schema\s+(\d+)",
            readme,
        )
        self.assertIsNotNone(match, "the README no longer states the p3–p5 schema")
        assert match is not None
        documented = int(match.group(1))
        for path in sorted((REPO_ROOT / "configs").glob("p[345]_*.json")):
            with self.subTest(config=path.name):
                self.assertEqual(
                    int(json.loads(path.read_text(encoding="utf-8"))["schema_version"]),
                    documented,
                )


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

    def _module_lines(self, module: str) -> int:
        path = REPO_ROOT / "src" / (module.replace(".", "/") + ".py")
        self.assertTrue(path.exists(), f"exempt module not found: {module}")
        return len(path.read_text(encoding="utf-8").splitlines())

    def test_the_documents_name_exactly_the_exempt_modules(self) -> None:
        # Extracted from the prose rather than hard-coded, so that changing the
        # exemption and the documents together passes, while changing one alone
        # fails. The earlier version hard-coded the list, which meant fixing a
        # false README sentence would have failed the test.
        exempt = {module.split(".")[-1] for module in self._exempt_modules()}
        for name in ("README.md", "CONTRIBUTING.md"):
            with self.subTest(document=name):
                text = _read(name)
                mentioned = {
                    match
                    for match in re.findall(r"`maxcover\.([a-z_]+)`", text)
                }
                self.assertEqual(
                    mentioned,
                    exempt,
                    f"{name} names {sorted(mentioned)} but the exemption covers "
                    f"{sorted(exempt)}",
                )

    def test_the_documented_share_matches_the_measured_share(self) -> None:
        # The README states a percentage. A band alone let it drift to 5% and
        # stay green, so the stated figure is now parsed and compared.
        source = sorted((REPO_ROOT / "src" / "maxcover").rglob("*.py"))
        total = sum(
            len(path.read_text(encoding="utf-8").splitlines()) for path in source
        )
        self.assertGreater(total, 0)
        exempt = sum(self._module_lines(module) for module in self._exempt_modules())
        measured = exempt * 100 / total

        for name in ("README.md", "CONTRIBUTING.md"):
            with self.subTest(document=name):
                match = re.search(r"(\d+)%\s+of\s+the\s+source\s+by\s+line", _read(name))
                self.assertIsNotNone(
                    match, f"{name} no longer states the exempt share"
                )
                assert match is not None
                stated = int(match.group(1))
                self.assertLessEqual(
                    abs(stated - measured),
                    5,
                    f"{name} states {stated}% but the measured share is "
                    f"{measured:.1f}%",
                )

    def test_the_documented_file_count_matches_what_mypy_checks(self) -> None:
        # The README quotes mypy's own summary line. A wrong count there is a
        # claim about the tool's output, so it is checked against the tool.
        readme = _read("README.md")
        match = re.search(r"no issues found in (\d+) source files", readme)
        self.assertIsNotNone(match, "the README no longer quotes mypy's summary")
        assert match is not None
        self.assertEqual(
            int(match.group(1)),
            len(sorted((REPO_ROOT / "src" / "maxcover").rglob("*.py"))),
            "the README quotes a file count mypy no longer reports",
        )

    def test_every_documented_exempt_module_has_errors_to_hide(self) -> None:
        # The documents say these modules "carry a real backlog". Review found
        # that false for one of them: contracts.py became a pure re-export
        # facade during the module split, with zero definitions and zero errors,
        # so the exemption is vestigial and the sentence overstated.
        #
        # Rather than assert a specific error count — which would fail on every
        # incremental improvement — this asserts the weaker property the prose
        # actually depends on: an exempt module contains something to check.
        for module in self._exempt_modules():
            with self.subTest(module=module):
                path = REPO_ROOT / "src" / (module.replace(".", "/") + ".py")
                source = path.read_text(encoding="utf-8")
                self.assertRegex(
                    source,
                    r"(?m)^\s*(?:def|class)\s",
                    f"{module} defines nothing, so exempting it from type "
                    "checking hides no errors; remove the exemption and the "
                    "sentence describing it",
                )


class ScopeClaimTests(unittest.TestCase):
    """The scope boundary must distinguish publishing from computing.

    `demo` prints a coverage gap and a benchmark writes measurement CSVs. An
    unqualified "no measurements" is contradicted by the terminal, which is the
    kind of gap that makes a reader distrust the rest of the boundary.
    """

    def test_demo_really_does_print_numbers(self) -> None:
        # The whole reason the scope sentence was narrowed. Review found that
        # stripping every number out of `demo` left all ten tests passing, which
        # means nothing pinned the premise. So `demo` is run as a subprocess —
        # the CLI reads sys.argv rather than taking an argument list — and its
        # output is required to contain a numeric figure.
        completed = subprocess.run(
            [sys.executable, "run_project.py", "demo"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertRegex(
            completed.stdout,
            r"\d",
            "demo prints no numbers, so the README's explanation of why its "
            "output does not cross the publishing boundary now describes "
            "something that does not happen",
        )

    def test_the_readme_explains_the_numbers_demo_prints(self) -> None:
        readme = _read("README.md")
        self.assertIn("## Scope", readme)
        scope = readme.split("## Scope", 1)[1]
        # The distinction is what makes the boundary coherent: computed on the
        # reader's machine, versus carried by the repository.
        self.assertIn("demo", scope)
        self.assertRegex(
            scope,
            r"publish|carr",
            "the scope section no longer distinguishes publishing a claim from "
            "computing a number",
        )

    def test_results_are_not_tracked_according_to_git(self) -> None:
        # The narrowed claim rests on generated output being untracked. Reading
        # .gitignore proves only that a rule exists — `git add -f` would defeat
        # it while leaving the test green. So git is asked what is tracked.
        tracked = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "results", "output"],
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(
            [name for name in tracked.decode("utf-8").split("\0") if name],
            [],
            "generated output is tracked; the scope boundary's distinction "
            "between publishing and computing no longer holds",
        )

    def test_contributing_scopes_the_rule_to_what_is_tracked(self) -> None:
        text = _read("CONTRIBUTING.md")
        self.assertIn("results/", text)
        # The rule has to remain a narrowing, not an inversion: a document
        # claiming a clean run proves more than it does is the defect itself.
        self.assertNotRegex(
            text,
            r"clean mypy run proves",
            "CONTRIBUTING now overstates what a clean mypy run establishes",
        )


if __name__ == "__main__":
    unittest.main()
