"""Behavioral checks for conservative CI routing; no Actions scheduler emulation."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/classify_ci_changes.py"
SPEC = importlib.util.spec_from_file_location("ci_routing_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
routing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(routing)


def raw_change(path: str | bytes, status: bytes = b"M", old_mode: bytes = b"100644", new_mode: bytes = b"100644") -> bytes:
    old_oid = b"0" * 40 if status == b"A" else b"a" * 40
    new_oid = b"0" * 40 if status == b"D" else b"b" * 40
    raw_path = path.encode("utf-8") if isinstance(path, str) else path
    return b":" + b" ".join((old_mode, new_mode, old_oid, new_oid, status)) + b"\0" + raw_path + b"\0"


class RawDiffTests(unittest.TestCase):
    def test_narrow_document_allowlist_and_nul_names(self) -> None:
        for path in ("docs/README.md", "docs/a_plan.zh-CN.md", "docs/带 空格_plan.zh-CN.md", "docs/a\tb\nc_plan.zh-CN.md"):
            with self.subTest(path=path):
                self.assertEqual("docs", routing.classify_diff(raw_change(path)))
                self.assertEqual("docs", routing.classify_diff(raw_change(path) + raw_change("LICENSE_MANIFEST.json")))

    def test_document_additions_deletions_and_executable_additions(self) -> None:
        for status, old_mode, new_mode in ((b"A", b"000000", b"100644"), (b"A", b"000000", b"100755"), (b"D", b"100644", b"000000")):
            with self.subTest(status=status, mode=new_mode):
                self.assertEqual("docs", routing.classify_diff(raw_change("docs/a_plan.zh-CN.md", status, old_mode, new_mode)))

    def test_other_paths_and_mixed_changes_are_full(self) -> None:
        for path in ("README.md", "CONTRIBUTING.md", "docs/reproducibility_matrix.md", "docs/sub/a_plan.zh-CN.md", "docs/../a_plan.zh-CN.md", "DOCS/a_plan.zh-CN.md", "docs/a_PLAN.zh-CN.md", "src/x.py", "tests/test_x.py", "configs/x.json", ".github/workflows/tests.yml", ".github/scripts/x.py", "analysis/x.md", "experiments/x.json"):
            with self.subTest(path=path):
                self.assertEqual("full", routing.classify_diff(raw_change(path)))
                self.assertEqual("full", routing.classify_diff(raw_change("docs/README.md") + raw_change(path)))

    def test_manifest_alone_and_no_changes_are_full(self) -> None:
        self.assertEqual("full", routing.classify_diff(raw_change("LICENSE_MANIFEST.json")))
        self.assertEqual("full", routing.classify_diff(b""))

    def test_special_modes_and_unknown_statuses_are_full(self) -> None:
        rows = [raw_change("docs/a_plan.zh-CN.md", b"M", b"100644", b"100755"), raw_change("docs/a_plan.zh-CN.md", b"M", b"100755", b"100644")]
        for mode in (b"120000", b"160000", b"100600"):
            rows.append(raw_change("docs/a_plan.zh-CN.md", b"A", b"000000", mode))
        for status in (b"T", b"U", b"R", b"C", b"X"):
            rows.append(raw_change("docs/a_plan.zh-CN.md", status))
        for raw in rows:
            with self.subTest(raw=raw):
                self.assertEqual("full", routing.classify_diff(raw))

    def test_incomplete_or_malformed_raw_output_is_full(self) -> None:
        good = raw_change("docs/a_plan.zh-CN.md")
        rows = (good[:-1], good + b"junk", b"\0", good.split(b"\0")[0] + b"\0", good.replace(b":100644", b":bad"), good.replace(b"a" * 40, b"a" * 39), raw_change(b"docs/\xff_plan.zh-CN.md"), raw_change(b""), raw_change("docs/a_plan.zh-CN.md", b"A"), raw_change("docs/a_plan.zh-CN.md", b"D"))
        for raw in rows:
            with self.subTest(raw=raw):
                self.assertEqual("full", routing.classify_diff(raw))


class OutputTests(unittest.TestCase):
    def test_final_writer_accepts_only_exact_lowercase_strings(self) -> None:
        class DocsString(str):
            pass
        with tempfile.TemporaryDirectory() as directory:
            for index, (value, expected) in enumerate((("docs", "docs"), ("full", "full"), (None, "full"), ("", "full"), ("DOCS", "full"), ("Docs", "full"), ("unknown", "full"), ("null", "full"), ("docs ", "full"), ("docs\nfull", "full"), (False, "full"), (DocsString("docs"), "full"))):
                with self.subTest(value=value):
                    path = Path(directory) / str(index)
                    self.assertEqual(expected, routing.write_profile_output(value, path))
                    self.assertEqual(f"profile={expected}\n".encode(), path.read_bytes())

    def test_main_never_bypasses_writer_for_unknown_classifier_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "output"
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(destination)}), mock.patch.object(routing, "classify_event", return_value=("DOCS", "test result")):
                self.assertEqual(0, routing.main())
            self.assertEqual(b"profile=full\n", destination.read_bytes())


@unittest.skipUnless(shutil.which("git"), "Git is required for PR diff tests")
class GitRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("-c", "init.defaultBranch=base", "init", "-q")
        self.git("config", "user.name", "CI routing fixture")
        self.git("config", "user.email", "ci-routing@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.filemode", "false")
        (self.repo / "empty-hooks").mkdir()
        self.git("config", "core.hooksPath", str(self.repo / "empty-hooks"))
        self.write("README.md", "baseline\n")
        self.write("docs/README.md", "index\n")
        self.write("docs/a_plan.zh-CN.md", "plan\n")
        self.write("src/example.py", "value = 1\n")
        self.base = self.commit("initial")

    def git(self, *args: str, input_data: bytes | None = None) -> bytes:
        return subprocess.run(["git", "-C", str(self.repo), *args], input=input_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15).stdout

    def write(self, path: str, text: str) -> None:
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message: str, *, stage: bool = True) -> str:
        if stage:
            self.git("add", "--all")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").decode().strip()

    def event(self, head: str, base: str | None = None) -> Path:
        path = self.repo / "event.json"
        path.write_text(json.dumps({"pull_request": {"base": {"sha": base or self.base}, "head": {"sha": head}}}), encoding="utf-8")
        return path

    def profile(self, head: str, base: str | None = None) -> str:
        return routing.classify_event("pull_request", self.event(head, base), self.repo)[0]

    def test_plan_index_and_companion_manifest(self) -> None:
        self.write("docs/README.md", "updated index\n")
        self.write("docs/中文 计划_plan.zh-CN.md", "new plan\n")
        self.write("LICENSE_MANIFEST.json", "{}\n")
        self.assertEqual("docs", self.profile(self.commit("documents")))

    def test_manifest_content_is_left_to_required_license_checker(self) -> None:
        self.write("docs/a_plan.zh-CN.md", "updated plan\n")
        self.write("LICENSE_MANIFEST.json", "deliberately invalid fixture\n")
        self.assertEqual("docs", self.profile(self.commit("classification is path-only")))

    def test_complete_pr_includes_earlier_code_commit(self) -> None:
        self.write("src/example.py", "value = 2\n")
        code = self.commit("source first")
        self.write("docs/a_plan.zh-CN.md", "updated plan\n")
        head = self.commit("documents last")
        last_diff = self.git("diff", "--raw", "--no-abbrev", "-z", "--no-renames", code, head, "--")
        self.assertEqual("docs", routing.classify_diff(last_diff))
        self.assertEqual("full", self.profile(head))

    def test_advanced_base_uses_common_ancestor_not_direct_base_diff(self) -> None:
        self.git("checkout", "-qb", "feature")
        self.write("docs/a_plan.zh-CN.md", "feature plan\n")
        head = self.commit("feature")
        self.git("checkout", "-qb", "advanced", self.base)
        self.write("src/example.py", "value = 3\n")
        advanced = self.commit("base advance")
        direct = self.git("diff", "--raw", "--no-abbrev", "-z", "--no-renames", advanced, head, "--")
        self.assertEqual("full", routing.classify_diff(direct))
        self.assertEqual("docs", self.profile(head, advanced))

    def test_code_renamed_into_allowlist_is_full(self) -> None:
        (self.repo / "src/example.py").replace(self.repo / "docs/renamed_plan.zh-CN.md")
        self.assertEqual("full", self.profile(self.commit("rename source")))

    def test_allowlisted_document_rename_is_docs(self) -> None:
        (self.repo / "docs/a_plan.zh-CN.md").replace(self.repo / "docs/renamed_plan.zh-CN.md")
        self.assertEqual("docs", self.profile(self.commit("rename plan")))

    def test_document_renamed_out_of_allowlist_is_full(self) -> None:
        (self.repo / "docs/a_plan.zh-CN.md").replace(self.repo / "src/plan.md")
        self.assertEqual("full", self.profile(self.commit("move plan out")))

    def test_existing_mode_change_is_full(self) -> None:
        self.git("update-index", "--chmod=+x", "docs/a_plan.zh-CN.md")
        self.assertEqual("full", self.profile(self.commit("executable plan", stage=False)))

    def test_symlink_and_gitlink_entries_are_full(self) -> None:
        blob = self.git("hash-object", "-w", "--stdin", input_data=b"README.md").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{blob},docs/link_plan.zh-CN.md")
        head = self.commit("symlink", stage=False)
        self.assertEqual("full", self.profile(head))
        self.git("reset", "--hard", self.base)
        self.git("update-index", "--add", "--cacheinfo", f"160000,{self.base},docs/submodule_plan.zh-CN.md")
        self.assertEqual("full", self.profile(self.commit("gitlink", stage=False)))

    def test_missing_objects_and_unrelated_histories_are_full(self) -> None:
        self.assertEqual("full", self.profile("1" * 40))
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        unrelated = self.git("commit-tree", tree, "-m", "unrelated root").decode().strip()
        self.assertEqual("full", self.profile(unrelated))

    def test_empty_diff_and_non_pr_events_are_full(self) -> None:
        self.assertEqual("full", self.profile(self.base))
        for name in ("push", "workflow_dispatch", "pull_request_target", "unknown", ""):
            with self.subTest(event=name):
                self.assertEqual("full", routing.classify_event(name, None, self.repo)[0])

    def test_malformed_events_and_bad_sha_values_are_full(self) -> None:
        path = self.repo / "bad-event.json"
        for event in (None, [], {}, {"pull_request": None}, {"pull_request": "text"}, {"pull_request": {"base": None, "head": {"sha": self.base}}}):
            with self.subTest(event=event):
                path.write_text(json.dumps(event), encoding="utf-8")
                self.assertEqual("full", routing.classify_event("pull_request", path, self.repo)[0])
        for value in (None, "", "0" * 40, "bad", 123, "a" * 39, "A" * 40, "--help"):
            path.write_text(json.dumps({"pull_request": {"base": {"sha": value}, "head": {"sha": self.base}}}), encoding="utf-8")
            self.assertEqual("full", routing.classify_event("pull_request", path, self.repo)[0])
        path.write_text("not JSON", encoding="utf-8")
        self.assertEqual("full", routing.classify_event("pull_request", path, self.repo)[0])
        self.assertEqual("full", routing.classify_event("pull_request", self.repo / "missing.json", self.repo)[0])

    def test_timeout_shallow_and_multiple_merge_bases_are_full(self) -> None:
        path = self.event(self.base)
        with mock.patch.object(routing, "_git", side_effect=subprocess.TimeoutExpired("git", 30)):
            self.assertEqual("full", routing.classify_event("pull_request", path, self.repo)[0])
        valid = (self.base + "\n").encode()
        with mock.patch.object(routing, "_git", side_effect=[valid, valid, b"true\n"]):
            self.assertEqual("full", routing.classify_event("pull_request", path, self.repo)[0])
        with mock.patch.object(routing, "_git", side_effect=[valid, valid, b"false\n", valid + valid]):
            self.assertEqual("full", routing.classify_event("pull_request", path, self.repo)[0])

    def test_cli_writes_docs_and_output_failures_are_real_failures(self) -> None:
        self.write("docs/a_plan.zh-CN.md", "changed\n")
        path = self.event(self.commit("docs"))
        output = self.repo / "github-output"
        env = dict(os.environ, GITHUB_EVENT_NAME="pull_request", GITHUB_EVENT_PATH=str(path), GITHUB_OUTPUT=str(output))
        process = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT)], cwd=self.repo, env=env, capture_output=True, timeout=30)
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual(b"profile=docs\n", output.read_bytes())
        for destination in (None, self.repo, self.repo / "missing-parent/output"):
            with self.subTest(output=destination):
                if destination is None:
                    env.pop("GITHUB_OUTPUT", None)
                else:
                    env["GITHUB_OUTPUT"] = str(destination)
                failed = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT)], cwd=self.repo, env=env, capture_output=True, timeout=30)
                self.assertNotEqual(0, failed.returncode)
                self.assertNotIn(b"profile=docs", failed.stdout)


if __name__ == "__main__":
    unittest.main()
