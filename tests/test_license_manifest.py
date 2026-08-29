"""Tests for the license manifest builder, written from its declarations.

The declarations under test are not this module's own idea of correctness. They
are:

* ``LICENSES/README.md`` — the manifest records each file's exact path, file
  mode, payload identity and license identifier; it is built from git's index
  rather than the working tree; only ``100644`` and ``100755`` may appear; and
  the license mapping is prose to CC BY 4.0, code and machine-readable inputs
  (including ``configs/*.json``) to MIT, with vendored font files under
  ``src/maxcover/dashboard_ui/fonts/`` to OFL-1.1.
* ``docs/history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md`` — a file carries a license
  grant only if it appears in the manifest with its exact identity.
* The builder's docstrings — identity is bound to the git object, never to the
  working-tree file, because ``.gitattributes`` normalizes line endings and
  hashing the checkout would make the manifest platform-dependent.

Three of these cases exist because the behaviour they describe was once absent:
a staged new file crashed the rebuild, a staged edit was recorded with the
previously committed bytes, and a mode-only change passed ``--check``. Each is
verified by running the builder against a real throwaway repository, never by
asserting on internals.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / ".github" / "scripts" / "build_license_manifest.py"

# A path that is neither ASCII nor a single Unicode block, so both git's path
# quoting and the manifest's UTF-8 canonicalization have to hold.
NON_ASCII_PATH = "docs/测试/笔记.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("_license_manifest_builder", BUILDER)


class ManifestTestCase(unittest.TestCase):
    """A throwaway git repository per test; the real repository is never touched."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.git("init", "-q", "-b", "main")
        # Local only, so the developer's global identity and hooks stay out of it.
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Manifest Test")
        self.git("config", "commit.gpgsign", "false")
        # The real repository normalizes line endings; reproduce that, because
        # it is the reason identity is bound to the blob rather than the file.
        self.write(".gitattributes", "* text=auto eol=lf\n")
        self.stage(".gitattributes")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", "replace")

    def write(self, relpath: str, text: str) -> None:
        target = self.root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def stage(self, *relpaths: str) -> None:
        self.git("add", "--", *relpaths)

    def commit(self, message: str = "wip") -> None:
        self.git("commit", "-qm", message)

    def build_manifest(self) -> dict:
        return json.loads(builder.build(self.root))

    def write_manifest(self) -> dict:
        """Run the builder in write mode, as a contributor regenerating it would."""

        code, _, err = self.run_cli()
        self.assertEqual(code, 0, err)
        return json.loads(
            (self.root / builder.MANIFEST_NAME).read_bytes().decode("utf-8")
        )

    def run_cli(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["--repo-root", str(self.root), *extra])
        return code, out.getvalue(), err.getvalue()

    def check(self) -> tuple[int, str, str]:
        return self.run_cli("--check")

    def entries(self, manifest: dict) -> dict[str, dict]:
        return {entry["path"]: entry for entry in manifest["files"]}


class IndexIsTheSourceTests(ManifestTestCase):
    """The builder reads one tree: git's index.

    Before the fix the path list came from the index and the payload from
    ``HEAD:``, so the two disagreed exactly when a contributor had staged
    something — which is precisely when the documented rebuild command runs.
    """

    def test_staged_new_file_does_not_crash_and_is_listed(self) -> None:
        self.write("a.py", "print(1)\n")
        self.stage("a.py")
        self.commit()

        self.write("added_later.py", "print(2)\n")
        self.stage("added_later.py")

        manifest = self.build_manifest()  # must not raise
        self.assertIn("added_later.py", self.entries(manifest))

    def test_staged_edit_is_recorded_instead_of_the_committed_bytes(self) -> None:
        self.write("a.py", "old\n")
        self.stage("a.py")
        self.commit()
        committed_digest = self.entries(self.build_manifest())["a.py"]["sha256"]

        self.write("a.py", "new content, longer\n")
        self.stage("a.py")
        staged = self.entries(self.build_manifest())["a.py"]

        self.assertNotEqual(staged["sha256"], committed_digest)
        self.assertEqual(staged["bytes"], len(b"new content, longer\n"))

    def test_unstaged_working_tree_edit_does_not_move_the_manifest(self) -> None:
        """The counterpart of the above, and what the prose now says.

        Identity is bound to the git object, so an edit that has not been staged
        is invisible here. This is the platform-independence property: a CRLF
        checkout must not produce a different manifest than a LF one.
        """

        self.write("a.py", "committed\n")
        self.stage("a.py")
        self.commit()
        before = self.build_manifest()

        (self.root / "a.py").write_bytes(b"edited in the working tree only\r\n")

        self.assertEqual(self.build_manifest(), before)

    def test_payload_is_read_with_lf_regardless_of_the_checkout(self) -> None:
        """.gitattributes normalizes to LF, so the digest is over LF bytes."""

        self.write("notes.md", "one\ntwo\n")
        self.stage("notes.md")
        self.commit()
        # Force a CRLF working-tree file; the blob stays LF.
        (self.root / "notes.md").write_bytes(b"one\r\ntwo\r\n")

        entry = self.entries(self.build_manifest())["notes.md"]
        self.assertEqual(entry["bytes"], len(b"one\ntwo\n"))


class FileModeTests(ManifestTestCase):
    """The manifest records the mode, and refuses modes it cannot license."""

    def _stage_with_mode(self, relpath: str, mode: str, content: str) -> None:
        """Put an arbitrary mode in the index without needing OS support for it.

        ``update-index --cacheinfo`` is used deliberately: on Windows
        ``core.filemode`` is false and symlinks are unavailable, so a test that
        relied on the filesystem would silently not test anything.
        """

        oid = subprocess.run(
            ["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
            input=content.encode("utf-8"),
            capture_output=True,
            check=True,
        ).stdout.decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"{mode},{oid},{relpath}")

    def test_regular_files_are_recorded_as_100644(self) -> None:
        self.write("a.py", "print(1)\n")
        self.stage("a.py")
        entry = self.entries(self.build_manifest())["a.py"]
        self.assertEqual(entry["git_mode"], "100644")

    def test_adding_the_executable_bit_fails_the_check(self) -> None:
        """A mode-only change moves identity, which schema 1 could not see."""

        self.write("script.py", "print(1)\n")
        self.stage("script.py")
        self.commit()
        before = self.write_manifest()
        self.assertEqual(self.entries(before)["script.py"]["git_mode"], "100644")

        self.git("update-index", "--chmod=+x", "script.py")

        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("script.py", err)
        self.assertIn("100755", err)

    def test_executable_files_are_licensable(self) -> None:
        self.write("script.py", "print(1)\n")
        self.stage("script.py")
        self.git("update-index", "--chmod=+x", "script.py")
        entry = self.entries(self.build_manifest())["script.py"]
        self.assertEqual(entry["git_mode"], "100755")
        self.assertEqual(entry["license"], "MIT")

    def test_symlink_mode_is_refused_even_though_the_blob_is_unchanged(self) -> None:
        """The substitution that leaves path, bytes and digest identical.

        A regular file containing ``../../../etc/passwd`` and a symlink pointing
        at it share one blob, so recording payload identity alone cannot tell
        them apart.
        """

        target_text = "../../../etc/passwd"
        self.write("payload", target_text)
        self.stage("payload")
        regular = self.entries(self.build_manifest())["payload"]

        self._stage_with_mode("payload", "120000", target_text)

        with self.assertRaises(builder.ManifestError) as caught:
            builder.build(self.root)
        message = str(caught.exception)
        self.assertIn("payload", message)
        self.assertIn("120000", message)
        # The blob really was identical, so only the mode could have caught it.
        self.assertEqual(regular["sha256"], builder.hashlib.sha256(
            target_text.encode("utf-8")
        ).hexdigest())

    def test_gitlink_mode_is_refused(self) -> None:
        # git validates the object, so a real commit id is needed; the empty
        # tree gives one without a second repository.
        empty_tree = self.git("hash-object", "-t", "tree", "-w", "--stdin").strip()
        oid = self.git("commit-tree", empty_tree, "-m", "sub").strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{oid},vendor")
        with self.assertRaises(builder.ManifestError) as caught:
            builder.build(self.root)
        self.assertIn("160000", str(caught.exception))

    def test_a_refused_mode_exits_one_with_a_message_not_a_traceback(self) -> None:
        self._stage_with_mode("link", "120000", "elsewhere")
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("link", err)


class CheckDetectionTests(ManifestTestCase):
    """``--check`` is the enforcement point, so each failure mode is exercised."""

    def setUp(self) -> None:
        super().setUp()
        self.write("a.py", "print(1)\n")
        self.write("README.md", "# hi\n")
        self.stage("a.py", "README.md")
        self.commit()
        self.manifest = self.write_manifest()

    def test_a_matching_manifest_passes(self) -> None:
        code, out, err = self.check()
        self.assertEqual(code, 0, err)
        self.assertIn(str(self.manifest["file_count"]), out)

    def test_an_unlisted_committed_file_is_detected_and_named(self) -> None:
        self.write("sneaky.py", "print('unlicensed')\n")
        self.stage("sneaky.py")
        self.commit()

        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("not listed: sneaky.py", err)

    def test_a_removed_file_still_listed_is_detected(self) -> None:
        self.git("rm", "-q", "a.py")
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("listed but absent: a.py", err)

    def test_tampering_with_any_entry_field_is_detected(self) -> None:
        forgeries = {
            "bytes": 1,
            "git_mode": "100755",
            "license": "MIT",
            "path": "renamed.md",
            "sha256": "0" * 64,
        }
        for field, forged in forgeries.items():
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(self.manifest))
                entry = next(
                    e for e in manifest["files"] if e["path"] == "README.md"
                )
                self.assertNotEqual(
                    entry[field], forged, f"{field} forgery is not a change"
                )
                entry[field] = forged
                (self.root / builder.MANIFEST_NAME).write_bytes(
                    builder._canonical(manifest)
                )

                code, _, err = self.check()
                self.assertEqual(code, 1, f"{field} tamper passed --check")
                self.assertTrue(err.strip(), "failure produced no message")

    def test_tampering_with_a_manifest_level_field_is_detected(self) -> None:
        for field, forged in (
            ("manifest_license", "MIT"),
            ("file_count", 999),
            ("content_tree_sha256", "0" * 64),
            ("schema_version", 1),
        ):
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(self.manifest))
                manifest[field] = forged
                (self.root / builder.MANIFEST_NAME).write_bytes(
                    builder._canonical(manifest)
                )
                code, _, err = self.check()
                self.assertEqual(code, 1, f"{field} tamper passed --check")
                self.assertTrue(err.strip(), "failure produced no message")

    def test_a_missing_manifest_is_reported(self) -> None:
        (self.root / builder.MANIFEST_NAME).unlink()
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn(builder.MANIFEST_NAME, err)

    def test_the_manifest_never_lists_itself(self) -> None:
        self.stage(builder.MANIFEST_NAME)
        manifest = self.build_manifest()
        self.assertNotIn(builder.MANIFEST_NAME, self.entries(manifest))


class NonAsciiPathTests(ManifestTestCase):
    """Non-ASCII paths were verified not to be a bypass; keep it that way.

    The builder now looks blobs up by object id rather than by putting the path
    on a git command line, so this guards the property the change could have
    broken.
    """

    def test_a_non_ascii_path_is_listed_with_the_right_identity(self) -> None:
        body = "内容\n"
        self.write(NON_ASCII_PATH, body)
        self.stage(NON_ASCII_PATH)

        entry = self.entries(self.build_manifest())[NON_ASCII_PATH]
        self.assertEqual(entry["bytes"], len(body.encode("utf-8")))
        self.assertEqual(
            entry["sha256"],
            builder.hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(entry["license"], "CC-BY-4.0")

    def test_a_non_ascii_path_round_trips_through_check(self) -> None:
        self.write(NON_ASCII_PATH, "内容\n")
        self.stage(NON_ASCII_PATH)
        self.commit()
        self.write_manifest()

        code, _, err = self.check()
        self.assertEqual(code, 0, err)

    def test_an_unlisted_non_ascii_file_is_still_caught(self) -> None:
        self.write("a.py", "print(1)\n")
        self.stage("a.py")
        self.commit()
        self.write_manifest()

        self.write(NON_ASCII_PATH, "内容\n")
        self.stage(NON_ASCII_PATH)
        self.commit()

        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn(NON_ASCII_PATH, err)

    def test_quotepath_does_not_hide_a_non_ascii_path(self) -> None:
        """git's default path quoting must not reach the manifest."""

        self.git("config", "core.quotepath", "true")
        self.write(NON_ASCII_PATH, "内容\n")
        self.stage(NON_ASCII_PATH)
        paths = set(self.entries(self.build_manifest()))
        self.assertIn(NON_ASCII_PATH, paths)
        self.assertFalse(
            [p for p in paths if chr(92) in p], f"escaped path leaked: {paths}"
        )


class LicenseMappingTests(unittest.TestCase):
    """The mapping must match the prose in LICENSES/README.md, not the reverse.

    The prose says: code and machine-readable inputs are MIT, prose is CC BY
    4.0, ``configs/`` is MIT specifically because those files are run inputs
    rather than documents, and font files directly in
    ``src/maxcover/dashboard_ui/fonts/`` are OFL-1.1 because they are vendored
    third-party font software rather than MIT-licensed contributions.
    """

    def assertLicense(self, path: str, expected: str) -> None:
        self.assertEqual(builder.license_for(path), expected, path)

    def test_configs_json_is_mit_because_it_is_a_run_input(self) -> None:
        for path in ("configs/full.json", "configs/quick.json", "configs/sweeps.json"):
            self.assertLicense(path, "MIT")

    def test_bundled_fonts_are_ofl(self) -> None:
        for path in (
            "src/maxcover/dashboard_ui/fonts/ibm-plex-mono-latin-400-normal.woff2",
            "src/maxcover/dashboard_ui/fonts/ibm-plex-mono-latin-600-normal.woff2",
            "src/maxcover/dashboard_ui/fonts/space-grotesk-latin-600-normal.woff2",
            "src/maxcover/dashboard_ui/fonts/space-grotesk-latin-700-normal.woff2",
        ):
            self.assertLicense(path, "OFL-1.1")

    def test_the_ofl_text_carries_the_same_identifier(self) -> None:
        self.assertLicense("LICENSES/OFL-1.1.txt", "OFL-1.1")

    def test_a_woff2_outside_the_font_dir_stays_mit(self) -> None:
        """The OFL rule is scoped to the vendored font directory, not the suffix."""

        self.assertLicense("assets/logo.woff2", "MIT")

    def test_a_woff2_in_a_font_subdirectory_stays_mit(self) -> None:
        """The directory rule matches direct children, not the whole subtree."""

        self.assertLicense(
            "src/maxcover/dashboard_ui/fonts/sub/outline.woff2", "MIT"
        )

    def test_a_prose_file_inside_the_font_dir_is_cc_by(self) -> None:
        """The directory rule does not capture non-font files inside it."""

        self.assertLicense("src/maxcover/dashboard_ui/fonts/NOTICE.md", "CC-BY-4.0")

    def test_the_font_suffix_test_is_case_insensitive(self) -> None:
        """A .WOFF2 spelling must not fall through to MIT on a case-blind path."""

        self.assertLicense(
            "src/maxcover/dashboard_ui/fonts/space-grotesk-latin-600-normal.WOFF2",
            "OFL-1.1",
        )

    def test_prose_suffixes_are_cc_by(self) -> None:
        for path in (
            "README.md",
            "docs/guides/QUICKSTART_zh.md",
            "docs/index.rst",
            "LICENSES/CONTENT-CC-BY.txt",
            NON_ASCII_PATH,
        ):
            self.assertLicense(path, "CC-BY-4.0")

    def test_suffixless_files_are_mit(self) -> None:
        for path in ("LICENSE", "Makefile", "project.ps1"):
            self.assertLicense(path, "MIT")

    def test_code_and_data_suffixes_are_mit(self) -> None:
        for path in (
            "src/maxcover/cli.py",
            ".gitattributes",
            "pyproject.toml",
            ".github/workflows/ci.yml",
            "results/raw_results.csv",
        ):
            self.assertLicense(path, "MIT")

    def test_the_suffix_test_is_case_insensitive(self) -> None:
        """Otherwise NOTES.MD would silently fall to MIT on a case-blind path."""

        self.assertLicense("NOTES.MD", "CC-BY-4.0")
        self.assertLicense("NOTES.Txt", "CC-BY-4.0")

    def test_every_license_used_has_an_attribution(self) -> None:
        for path in (
            "a.py",
            "a.md",
            "LICENSE",
            "src/maxcover/dashboard_ui/fonts/ibm-plex-mono-latin-400-normal.woff2",
            "LICENSES/OFL-1.1.txt",
        ):
            self.assertIn(builder.license_for(path), builder.ATTRIBUTIONS)


class RealRepositoryTests(unittest.TestCase):
    """The committed manifest must satisfy the checker it ships with."""

    def test_the_committed_manifest_only_holds_licensable_modes(self) -> None:
        entries = builder.tracked_entries(REPO_ROOT)
        offenders = [e for e in entries if e.mode not in builder.LICENSABLE_MODES]
        self.assertEqual(offenders, [], f"non-licensable modes tracked: {offenders}")


if __name__ == "__main__":
    unittest.main()
