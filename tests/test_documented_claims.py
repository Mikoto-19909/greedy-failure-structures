"""Check documented commands, configuration compatibility and coverage boundaries.

Behavior checks exercise the relevant APIs; bilingual checks compare the same
facts and links. Display-only source counts and exemption percentages are not
part of the documentation contract.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


class LegacyConfigClaimTests(unittest.TestCase):
    """The CLI guide says which configs are legacy. That list must stay true."""

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
        # If either is migrated, the CLI guide paragraph explaining the warning
        # becomes wrong and the warning it prepares the reader for is gone.
        self.assertEqual(self._schema_version("quick.json"), 1)
        self.assertEqual(self._schema_version("full.json"), 1)

    def test_sweeps_is_still_schema_v2(self) -> None:
        self.assertEqual(self._schema_version("sweeps.json"), 2)

    def test_no_other_config_is_legacy_without_being_named(self) -> None:
        # The CLI guide names exactly two warning configs. A third would make the
        # documented list incomplete rather than merely stale.
        self.assertEqual(
            self._legacy_configs(),
            {"quick.json", "full.json"},
            "the set of schema-v1 configs changed; update the CLI guide paragraph "
            "that names them and explains the LegacyConfigWarning",
        )

    def test_the_guide_names_every_legacy_config_and_no_others(self) -> None:
        # Substring presence let the CLI guide drop `configs/full.json` from the
        # list while staying green. So the documented set is extracted from the
        # prose and compared to the measured set.
        guide = _read("docs/cli.md")
        documented = {
            f"{name}.json"
            for name in re.findall(r"`configs/([A-Za-z0-9_]+)\.json` and", guide)
        } | {
            f"{name}.json"
            for name in re.findall(r"and\s+`configs/([A-Za-z0-9_]+)\.json` are", guide)
        }
        self.assertEqual(
            documented,
            self._legacy_configs(),
            "the CLI guide's list of schema-v1 configs no longer matches the "
            "configs that are actually schema v1",
        )

    def test_both_named_configs_actually_raise_the_documented_warning(self) -> None:
        # The class of warning is part of the claim. Renaming it, or removing the
        # migration, leaves a CLI guide paragraph describing something that no
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
                    f"{name} no longer raises LegacyConfigWarning; the CLI guide "
                    "paragraph preparing the reader for it is now wrong",
                )

    def test_the_guide_states_the_correct_schema_for_sweeps(self) -> None:
        guide = _read("docs/cli.md")
        match = re.search(r"`configs/sweeps\.json`\s+is\s+schema\s+(\d+)", guide)
        self.assertIsNotNone(match, "the CLI guide no longer states sweeps' schema")
        assert match is not None
        self.assertEqual(int(match.group(1)), self._schema_version("sweeps.json"))

    def test_cli_states_the_correct_schema_for_current_configs(self) -> None:
        guide = re.sub(r"\s+", " ", _read("docs/cli.md"))
        match = re.search(
            r"`configs/p3_\*`\s+through\s+`configs/p(\d+)_\*`\s+"
            r"configurations?\s+are\s+schema\s+(\d+)",
            guide,
        )
        self.assertIsNotNone(match, "CLI guide must identify the retained phase schemas")
        assert match is not None
        endpoint, schema = int(match.group(1)), int(match.group(2))
        phase_schemas: dict[int, set[int]] = {}
        for path in sorted((REPO_ROOT / "configs").glob("p[0-9]*_*.json")):
            phase = re.match(r"p(\d+)_", path.name)
            assert phase is not None
            payload = json.loads(path.read_text(encoding="utf-8"))
            phase_schemas.setdefault(int(phase.group(1)), set()).add(
                int(payload["schema_version"])
            )
        self.assertEqual(max(phase_schemas), endpoint)
        for phase in range(3, endpoint + 1):
            with self.subTest(phase=phase):
                self.assertEqual(phase_schemas.get(phase), {schema})


class DocumentationNavigationClaimTests(unittest.TestCase):
    """The two README entry points must expose the same core workflow docs."""

    @staticmethod
    def _link_targets(name: str) -> set[str]:
        return set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", _read(name)))

    def test_bilingual_readmes_link_the_core_workflow_documents(self) -> None:
        expected = {
            "analysis/README.md",
            "docs/README.md",
            "docs/cli.md",
            "docs/output_schema.md",
            "docs/lazy_greedy_test_report.md",
            "experiments/core_rq/CLAIMS.md",
        }
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(document=name):
                self.assertTrue(
                    expected <= self._link_targets(name),
                    f"{name} does not link every core workflow document",
                )

    def test_cli_reference_covers_every_public_command(self) -> None:
        sys.path.insert(0, str(SOURCE_ROOT))
        try:
            from maxcover.cli import build_parser
        finally:
            sys.path.remove(str(SOURCE_ROOT))

        parser = build_parser()
        command_action = next(
            action for action in parser._actions if action.dest == "command"
        )
        implemented = set(command_action.choices)
        documented = set(
            re.findall(r"(?m)^### `([a-z-]+)`\s*$", _read("docs/cli.md"))
        )
        self.assertEqual(
            documented,
            implemented,
            "docs/cli.md command sections no longer match the CLI parser",
        )

    @staticmethod
    def _replay_document(
        algorithm: str, options: dict[str, object], directory: str
    ) -> Path:
        path = Path(directory) / "replay.json"
        path.write_text(
            json.dumps(
                {
                    "instance": {
                        "schema_version": 1,
                        "encoding": "elements",
                        "universe_size": 3,
                        "sets": [[0, 1], [1, 2]],
                        "k": 1,
                        "family": "test",
                        "seed": 11,
                        "parameters": {},
                    },
                    "replay": {"algorithm": algorithm, "options": options},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_replay_override_restriction_is_enforced(self) -> None:
        # docs/cli.md says an override is valid only when the replacement
        # algorithm accepts the recorded option contract, and that greedy
        # rejects exact-solver options rather than remapping them. Run both
        # directions instead of trusting the sentence.
        sys.path.insert(0, str(SOURCE_ROOT))
        try:
            from maxcover.benchmark import replay_instance_file
        finally:
            sys.path.remove(str(SOURCE_ROOT))

        with tempfile.TemporaryDirectory() as directory:
            timeout = self._replay_document(
                "brute_force",
                {"time_limit_seconds": 0.5, "max_set_count": 18},
                directory,
            )
            with self.assertRaises(ValueError):
                replay_instance_file(timeout, "greedy")

        with tempfile.TemporaryDirectory() as directory:
            bounded = self._replay_document(
                "branch_and_bound", {"time_limit_seconds": 5.0}, directory
            )
            solution, _ = replay_instance_file(bounded, "brute_force")
            self.assertEqual(
                solution.algorithm,
                "brute_force",
                "a replacement whose contract covers the recorded options "
                "should run, as docs/cli.md describes",
            )


class BilingualFaqClaimTests(unittest.TestCase):
    """English and Simplified Chinese FAQs must evolve as one document."""

    FAQ_FILES = ("docs/faq.md", "docs/faq.zh-CN.md")
    FAQ_SECTION_MARKER = re.compile(r"<!--\s*faq:id=([a-z0-9-]+)\s*-->")

    @staticmethod
    def _section_ids(text: str) -> list[str]:
        return re.findall(r"<!--\s*faq:id=([a-z0-9-]+)\s*-->", text)

    @classmethod
    def _section(cls, text: str, section_id: str) -> str:
        """Return one complete FAQ section bounded by its stable marker."""

        markers = list(cls.FAQ_SECTION_MARKER.finditer(text))
        for index, marker in enumerate(markers):
            if marker.group(1) != section_id:
                continue
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            return text[marker.end() : end]
        raise AssertionError(f"FAQ section marker not found: {section_id}")

    @staticmethod
    def _link_targets(text: str) -> set[str]:
        return set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))

    def test_bilingual_faqs_have_the_same_section_ids(self) -> None:
        ids = {name: self._section_ids(_read(name)) for name in self.FAQ_FILES}
        self.assertTrue(ids["docs/faq.md"], "English FAQ has no section IDs")
        for name, values in ids.items():
            self.assertEqual(
                len(values),
                len(set(values)),
                f"{name} repeats a FAQ section ID",
            )
        self.assertEqual(
            ids["docs/faq.md"],
            ids["docs/faq.zh-CN.md"],
            "English and Chinese FAQs no longer cover the same sections in order",
        )

    def test_bilingual_faqs_link_the_same_supporting_documents(self) -> None:
        expected = {"cli.md", "output_schema.md", "failure_mechanisms.md"}
        targets = {name: self._link_targets(_read(name)) for name in self.FAQ_FILES}
        self.assertEqual(
            targets["docs/faq.md"],
            targets["docs/faq.zh-CN.md"],
            "English and Chinese FAQs no longer use the same supporting links",
        )
        self.assertTrue(
            expected <= targets["docs/faq.md"],
            "the FAQs do not link all supporting documents",
        )

    def test_bilingual_faqs_state_the_reproducibility_boundary(self) -> None:
        # The determinism section pins two lists: what a run must reproduce and
        # what may vary. Phrase presence cannot catch an inversion — the section
        # could keep every phrase while moving coverage into the "may vary" list
        # — so both lists are extracted from the section and compared, and the
        # timeout exemption the section states must remain part of the claim.
        documents = {name: _read(name) for name in self.FAQ_FILES}
        sections = {
            name: re.sub(r"\s+", " ", self._section(text, "determinism"))
            for name, text in documents.items()
        }
        must_reproduce = {
            "docs/faq.md": (
                "instance identities",
                "selected set indices",
                "coverage values",
                "canonical row ordering",
            ),
            "docs/faq.zh-CN.md": (
                "实例身份",
                "选中的集合索引",
                "覆盖值",
                "规范行排序",
            ),
        }
        may_vary = {
            "docs/faq.md": ("Wall-clock runtime", "timestamps", "environment metadata"),
            "docs/faq.zh-CN.md": ("实际运行时间", "时间戳", "环境元数据"),
        }
        reproduce_patterns = {
            "docs/faq.md": r"completed runs reproduce the ([^.]*)\.",
            "docs/faq.zh-CN.md": r"已完成的运行会复现([^。]*)",
        }
        vary_patterns = {
            "docs/faq.md": r"(Wall-clock runtime[^.]*) may vary by machine",
            "docs/faq.zh-CN.md": r"(实际运行时间[^。]*)可能\s*因机器而异",
        }
        for name, section in sections.items():
            with self.subTest(document=name):
                reproduced = re.search(reproduce_patterns[name], section)
                self.assertIsNotNone(
                    reproduced, f"{name} no longer states what a run must reproduce"
                )
                assert reproduced is not None
                for item in must_reproduce[name]:
                    self.assertIn(item, reproduced.group(1))

                varied = re.search(vary_patterns[name], section)
                self.assertIsNotNone(
                    varied, f"{name} no longer states what may vary by machine"
                )
                assert varied is not None
                for item in may_vary[name]:
                    self.assertIn(item, varied.group(1))

                # The two lists must stay disjoint: an inverted boundary keeps
                # every phrase but moves it to the other side.
                for item in must_reproduce[name]:
                    self.assertNotIn(item, varied.group(1))
                for item in may_vary[name]:
                    self.assertNotIn(item, reproduced.group(1))

        exemptions = {
            "docs/faq.md": (
                r"A run stopped by its wall-clock limit reports the incumbent[^.]*"
                r"exempt from this guarantee"
            ),
            "docs/faq.zh-CN.md": (
                r"被墙钟限制中止的运行报告其在限制触发时已达成的 incumbent[^。]*"
                r"不受此保证约束"
            ),
        }
        for name, pattern in exemptions.items():
            with self.subTest(document=name):
                self.assertRegex(
                    sections[name],
                    pattern,
                    f"{name} no longer exempts timeout incumbents from the "
                    "reproducibility guarantee",
                )

    def test_bilingual_faqs_state_the_causality_boundary(self) -> None:
        documents = {name: _read(name) for name in self.FAQ_FILES}
        sections = {
            name: re.sub(r"\s+", " ", self._section(text, "synthetic-families"))
            for name, text in documents.items()
        }
        # The section's conclusion is a negative one: descriptive associations
        # do not establish causality or generalisation. The whole predicate is
        # matched so the sentence cannot be inverted while keeping its phrases.
        self.assertRegex(
            sections["docs/faq.md"],
            r"estimate descriptive associations[^.]*does not by itself establish "
            r"causality[^.]*real-world generalisation",
        )
        self.assertRegex(
            sections["docs/faq.zh-CN.md"],
            r"估计描述性关联[^。]*不能建立因果关系[^。]*真实世界的\s*泛化能力",
        )

    def test_completed_deterministic_runs_reproduce_selection_and_coverage(
        self,
    ) -> None:
        # The determinism section guarantees that completed runs reproduce
        # selection and coverage; the guarantee is exercised rather than quoted.
        sys.path.insert(0, str(SOURCE_ROOT))
        try:
            from maxcover.algorithms import ALGORITHMS
            from maxcover.contracts import AlgorithmRunOptions
            from maxcover.generators import uniform_random
        finally:
            sys.path.remove(str(SOURCE_ROOT))

        instance = uniform_random(
            universe_size=40, set_count=12, k=4, density=0.25, seed=11
        )
        first = ALGORITHMS["greedy"].run(instance, AlgorithmRunOptions())
        second = ALGORITHMS["greedy"].run(instance, AlgorithmRunOptions())
        self.assertEqual(first.selected, second.selected)
        self.assertEqual(first.coverage, second.coverage)

    def test_algorithm_seed_contract_matches_the_faq_statement(self) -> None:
        # The section says randomised algorithms require an explicit seed and
        # deterministic ones reject one; that contract is enforced by the
        # registry, so the test runs it instead of checking the words.
        sys.path.insert(0, str(SOURCE_ROOT))
        try:
            from maxcover.algorithms import ALGORITHMS
            from maxcover.contracts import AlgorithmRunOptions
            from maxcover.generators import uniform_random
        finally:
            sys.path.remove(str(SOURCE_ROOT))

        instance = uniform_random(
            universe_size=40, set_count=12, k=4, density=0.25, seed=11
        )
        with self.assertRaises(ValueError):
            ALGORITHMS["greedy"].run(instance, AlgorithmRunOptions(algorithm_seed=1))
        with self.assertRaises(RuntimeError):
            ALGORITHMS["randomized_greedy"].run(instance, AlgorithmRunOptions())


class MechanismWorkflowClaimTests(unittest.TestCase):
    """Mechanism workflows must support the exact-reference claims they make."""

    @staticmethod
    def _algorithm_names(config_name: str) -> set[str]:
        payload = json.loads(_read(config_name))
        return {
            item if isinstance(item, str) else item["name"]
            for item in payload["algorithms"]
        }

    @staticmethod
    def _exact_algorithm_names() -> set[str]:
        sys.path.insert(0, str(SOURCE_ROOT))
        try:
            from maxcover.algorithms import ALGORITHMS
        finally:
            sys.path.remove(str(SOURCE_ROOT))
        return {name for name, specification in ALGORITHMS.items() if specification.exact}

    def test_every_documented_mechanism_command_has_an_exact_algorithm(self) -> None:
        paths = set(
            re.findall(
                r"--config\s+(configs/[A-Za-z0-9_]+\.json)",
                _read("docs/failure_mechanisms.md"),
            )
        )
        self.assertTrue(paths, "the mechanism guide has no runnable configurations")
        self.assertIn("configs/core_overlap_pilot.json", paths)
        exact = self._exact_algorithm_names()
        for path in sorted(paths):
            with self.subTest(config=path):
                self.assertTrue(
                    self._algorithm_names(path) & exact,
                    f"{path} cannot support the guide's exact-reference analysis",
                )

    def test_sweeps_really_has_no_exact_reference(self) -> None:
        self.assertFalse(
            self._algorithm_names("configs/sweeps.json")
            & self._exact_algorithm_names(),
            "sweeps.json gained an exact algorithm; update the guide's limitation",
        )


class TypeCheckClaimTests(unittest.TestCase):
    """The primary coverage description must agree with the effective settings."""

    def _exempt_modules(self) -> list[str]:
        config = tomllib.loads(_read("pyproject.toml"))
        modules: list[str] = []
        for override in config["tool"]["mypy"].get("overrides", []):
            if override.get("ignore_errors"):
                value = override["module"]
                modules += [value] if isinstance(value, str) else list(value)
        return modules

    def test_mypy_enforces_the_configured_coverage_boundary(self) -> None:
        if importlib.util.find_spec("mypy") is None:
            self.skipTest("mypy is an optional development dependency")
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "maxcover"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            probe = package / "_mypy_new_module_probe.py"
            files = [probe]
            for module in self._exempt_modules():
                self.assertIn(module, {"maxcover.benchmark", "maxcover.reporting"})
                files.append(package / (module.split(".")[-1] + ".py"))
            for path in files:
                path.write_text('value: int = "not an integer"\n', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "mypy", "--config-file", str(REPO_ROOT / "pyproject.toml"),
                 "--cache-dir", str(Path(directory) / "cache"), *map(str, files)],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            errors = [line for line in result.stdout.splitlines() if ": error:" in line]
            self.assertTrue(errors, result.stdout + result.stderr)
            self.assertTrue(all(probe.name in line for line in errors), errors)

    def test_typecheck_targets_source_without_spreading_legacy_exemptions(self) -> None:
        config = tomllib.loads(_read("pyproject.toml"))["tool"]["mypy"]
        self.assertIn("src/maxcover", config["files"])
        self.assertFalse(config.get("ignore_errors", False))
        # These are the pre-split legacy exceptions. Newly extracted modules
        # must not acquire a whole-module exception or a package wildcard.
        for module in self._exempt_modules():
            with self.subTest(module=module):
                self.assertIn(module, {"maxcover.benchmark", "maxcover.reporting"})
                self.assertTrue((SOURCE_ROOT / (module.replace(".", "/") + ".py")).is_file())


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
