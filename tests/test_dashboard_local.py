"""Archive flags are reversible sidecars and never mutate research artifacts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard_local import LocalCatalog, LocalCatalogError


@contextmanager
def directory_link(link: Path, target: Path) -> Iterator[None]:
    if os.name == "nt":
        script = "New-Item -ItemType Junction -Path $env:TEST_CATALOG_LINK -Target $env:TEST_CATALOG_TARGET | Out-Null"
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       env={**os.environ, "TEST_CATALOG_LINK": str(link), "TEST_CATALOG_TARGET": str(target)},
                       check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    try:
        yield
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


class LocalCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = LocalCatalog(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def job(self, number: int = 1, status: str = "completed") -> str:
        identifier = f"{number:032x}"
        path = self.root / "results/workbench_jobs" / identifier
        path.mkdir(parents=True, exist_ok=True)
        timestamp = "2026-09-20T00:00:00+00:00"
        record = {
            "id": identifier, "kind": "refute", "status": status,
            "params": {"kind": "refute", "n": 2, "m": 2, "k": 1,
                       "timeout_seconds": 1, "max_combinations": 10, "budget": 0,
                       "set_size": None, "max_frequency": None, "unique_sets": False,
                       "min_ratio": [1, 1]},
            "created_at": timestamp, "started_at": None if status == "queued" else timestamp,
            "finished_at": None if status in ("queued", "running") else timestamp,
            "output_dir": f"results/workbench_jobs/{identifier}/output",
            "input_snapshot": "design.json", "error": None, "retry_of": None,
            "summary": {"validated": True, "status": "budget_exhausted", "cases": [],
                        "counts": {"candidate_space": 16, "scanned": 0, "eligible": 0, "rejected": 0}}
                       if status == "completed" else None,
            "owner": "test-owner",
        }
        (path / "job.json").write_text(json.dumps(record), encoding="utf-8")
        (path / "design.json").write_bytes(b'{"frozen": true}\n')
        (path / "output").mkdir(exist_ok=True)
        (path / "output/result.json").write_bytes(b'{"output": "preserved"}\n')
        (path / "run.log").write_bytes(b"original log\r\n")
        return identifier

    def view(self, number: int = 1) -> str:
        identifier = f"{number:032x}"
        path = self.root / "results/dashboard_views" / (identifier + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "id": identifier, "title": "Saved analysis", "note": "Retain exact snapshot",
            "saved_at": "2026-09-20T00:00:00+00:00", "filters": {},
            "comparison": {"input_records": 0, "filtered_records": 0, "total": 0,
                           "rows": [], "summaries": [], "sources": ["results/original"]},
        }), encoding="utf-8")
        return identifier

    def source_bytes(self) -> dict[str, bytes]:
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for name in ("workbench_jobs", "dashboard_views")
                for path in (self.root / "results" / name).rglob("*") if path.is_file()}

    def test_archive_restore_restart_preserve_all_original_bytes(self) -> None:
        self.assertEqual(self.catalog.list("job"), {})
        self.assertFalse((self.root / "results").exists())
        job, view = self.job(), self.view()
        before = self.source_bytes()
        for kind, identifier in (("job", job), ("view", view)):
            saved = self.catalog.set_archived(kind, identifier, True)
            self.assertIs(saved["archived"], True)
            self.assertEqual(LocalCatalog(self.root).list(kind)[identifier], saved)
            restored = LocalCatalog(self.root).set_archived(kind, identifier, False)
            self.assertIs(restored["archived"], False)
            self.assertEqual(self.catalog.list(kind)[identifier], restored)
        self.assertEqual(self.source_bytes(), before)

    def test_active_jobs_rejected_and_terminal_failures_allowed(self) -> None:
        for index, status in enumerate(("queued", "running", "failed", "interrupted"), start=1):
            identifier = self.job(index, status)
            before = self.source_bytes()
            if status in ("queued", "running"):
                for archived in (True, False):
                    with self.assertRaisesRegex(LocalCatalogError, "only completed") as raised:
                        self.catalog.set_archived("job", identifier, archived)
                    self.assertEqual(raised.exception.status, 409)
            else:
                self.assertTrue(self.catalog.set_archived("job", identifier, True)["archived"])
            self.assertEqual(self.source_bytes(), before)

    def test_invalid_input_cannot_create_metadata(self) -> None:
        for kind, identifier, archived in (
            ("unknown", "a" * 32, True), ("job", "../outside", True),
            ("view", "a" * 32 + ":stream", True), ("job", "A" * 32, True),
            ("view", "a" * 32 + ".", True), ("view", "a" * 32 + " ", True),
            ("job", "a" * 32, True), ("view", "a" * 32, True),
            ("job", "a" * 32, "false"),
        ):
            with self.subTest(kind=kind, identifier=identifier, archived=archived):
                with self.assertRaises(LocalCatalogError):
                    self.catalog.set_archived(kind, identifier, archived)  # type: ignore[arg-type]
        self.assertFalse((self.root / "results/.dashboard_local").exists())

    def test_corrupt_and_removed_sources_do_not_disappear_into_archive(self) -> None:
        job, view = self.job(), self.view()
        for kind, identifier, path in (
            ("job", job, self.root / "results/workbench_jobs" / job / "job.json"),
            ("view", view, self.root / "results/dashboard_views" / (view + ".json")),
        ):
            self.catalog.set_archived(kind, identifier, True)
            original = path.read_bytes()
            for damaged in (b"{broken", b"{}", b'{"invalid": NaN}'):
                path.write_bytes(damaged)
                with self.assertRaises(LocalCatalogError):
                    self.catalog.set_archived(kind, identifier, False)
                self.assertEqual(self.catalog.list(kind), {})
                self.assertEqual(path.read_bytes(), damaged)
            path.unlink()
            self.assertEqual(self.catalog.list(kind), {})
            path.write_bytes(original)
            self.assertTrue(self.catalog.list(kind)[identifier]["archived"])

    def test_bad_annotation_does_not_hide_valid_annotations(self) -> None:
        view = self.view()
        self.catalog.set_archived("view", view, True)
        database = self.root / "results/.dashboard_local/catalog.sqlite3"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("INSERT INTO annotations VALUES ('view', '../invalid', 1, 'invalid')")
        self.assertEqual(set(self.catalog.list("view")), {view})
        self.assertTrue(self.catalog.status()["warnings"])

    def test_concurrent_threads_and_processes_do_not_lose_distinct_updates(self) -> None:
        identifiers = [self.view(number) for number in range(1, 17)]
        before = self.source_bytes()
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda identifier: LocalCatalog(self.root).set_archived("view", identifier, True), identifiers[:8]))
        code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                "from maxcover.dashboard_local import LocalCatalog; "
                "catalog=LocalCatalog(Path(sys.argv[2])); "
                "[catalog.set_archived('view', item, True) for item in sys.argv[3:]]")
        processes = [subprocess.Popen([sys.executable, "-c", code, str(ROOT / "src"), str(self.root), *identifiers[start:start + 2]],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for start in range(8, 16, 2)]
        for process in processes:
            output, error = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, (output, error))
        states = LocalCatalog(self.root).list("view")
        self.assertEqual(set(states), set(identifiers))
        self.assertTrue(all(item["archived"] for item in states.values()))
        self.assertEqual(self.source_bytes(), before)

    def test_hard_links_in_sources_database_and_journal_are_rejected(self) -> None:
        view = self.view()
        source = self.root / "results/dashboard_views" / (view + ".json")
        alias = self.root / "source-alias.json"
        os.link(source, alias)
        try:
            with self.assertRaisesRegex(LocalCatalogError, "hard-linked"):
                self.catalog.set_archived("view", view, True)
        finally:
            alias.unlink()
        self.catalog.set_archived("view", view, True)
        database = self.root / "results/.dashboard_local/catalog.sqlite3"
        before = database.read_bytes()
        os.link(database, alias)
        try:
            with self.assertRaisesRegex(LocalCatalogError, "hard-linked"):
                self.catalog.set_archived("view", view, False)
            with self.assertRaisesRegex(LocalCatalogError, "hard-linked"):
                self.catalog.list("view")
        finally:
            alias.unlink()
        journal = database.with_name(database.name + "-journal")
        os.link(source, journal)
        try:
            with self.assertRaisesRegex(LocalCatalogError, "hard-linked"):
                self.catalog.set_archived("view", view, False)
        finally:
            journal.unlink()
        self.assertEqual(database.read_bytes(), before)

    def test_linked_directory_cannot_redirect_sidecar_writes(self) -> None:
        view = self.view()
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "results/.dashboard_local"
        with directory_link(link, outside):
            with self.assertRaisesRegex(LocalCatalogError, "linked or reparse"):
                self.catalog.set_archived("view", view, True)
            self.assertEqual(list(outside.iterdir()), [])

    def test_linked_source_directory_and_project_root_are_rejected(self) -> None:
        view = self.view()
        views = self.root / "results/dashboard_views"
        outside = self.root / "outside"
        # A rename within this test's resolved temporary root creates the source
        # directory that the deliberately invalid link will target.
        self.assertTrue(views.resolve().is_relative_to(self.root.resolve()))
        self.assertTrue(outside.resolve().is_relative_to(self.root.resolve()))
        views.rename(outside)
        with directory_link(views, outside):
            with self.assertRaisesRegex(LocalCatalogError, "linked or reparse"):
                self.catalog.set_archived("view", view, True)
        with directory_link(self.root / "alias", self.root):
            with self.assertRaisesRegex(LocalCatalogError, "linked or reparse"):
                LocalCatalog(self.root / "alias").list("view")

    def test_corrupt_database_is_reported_without_overwrite(self) -> None:
        view = self.view()
        database = self.root / "results/.dashboard_local/catalog.sqlite3"
        database.parent.mkdir()
        database.write_bytes(b"damaged archive database")
        with self.assertRaisesRegex(LocalCatalogError, "Cannot read local archive"):
            self.catalog.list("view")
        with self.assertRaisesRegex(LocalCatalogError, "Cannot update local archive"):
            self.catalog.set_archived("view", view, True)
        self.assertEqual(database.read_bytes(), b"damaged archive database")


if __name__ == "__main__":
    unittest.main()
