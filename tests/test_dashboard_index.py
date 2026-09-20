"""Stable-source caching, restart reuse, concurrency and disposable recovery."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.dashboard_index import DashboardIndex, IndexedDocument, SourceChangedError


class DashboardIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "experiments" / "r1" / "paths.jsonl"
        self.source.parent.mkdir(parents=True)
        self.index = DashboardIndex(self.root)
        self.calls = 0
        self.write_source()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_source(self, value: int = 1, *, raw: bool = True) -> None:
        rows = [{"key": f"row-{i}", "config_hash": "config", "case_id": "case",
                 "instance_id": "instance", "repetition": i, "coverage": value + i,
                 "source": "experiments/r1", "status": "saved",
                 "seed": str(2 ** 100 + i)} for i in range(3)]
        originals = [{"sets": [[1, 2], [2, 3]], "value": value + i} for i in range(3)] if raw else []
        self.source.write_text(json.dumps({"kind": "r1" if raw else "benchmark", "rows": rows,
                                          "raw": originals, "metadata": {"records": 3, "value": value}}),
                               encoding="utf-8")

    def loader(self) -> IndexedDocument:
        self.calls += 1
        return IndexedDocument(**json.loads(self.source.read_text(encoding="utf-8")))

    def test_reuses_metadata_rows_and_single_records_after_restart(self) -> None:
        original = self.source.read_bytes()
        signature = self.index.signature(self.source)
        expected = self.loader()
        self.assertEqual(self.index.read(self.source, "v1", self.loader), expected)
        self.assertEqual(self.calls, 2)
        restarted = DashboardIndex(self.root)
        no_loader = lambda: self.fail("unchanged source should use the saved index")
        self.assertEqual(restarted.metadata(self.source, "v1", no_loader), expected.metadata)
        self.assertEqual(restarted.read(self.source, "v1", no_loader), expected)
        self.assertEqual(restarted.record(self.source, "v1", no_loader, key="row-1"),
                         ("r1", expected.rows[1], expected.raw[1]))
        self.assertIsNone(restarted.record(self.source, "v1", no_loader, key="unknown"))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.index.signature(self.source), signature)
        self.assertEqual(restarted.status()["indexed_records"], 3)
        self.assertEqual(restarted.status()["hits"], 4)

    def test_metadata_and_normalized_reads_do_not_decode_raw_traces(self) -> None:
        self.index.read(self.source, "v1", self.loader)
        with closing(sqlite3.connect(self.index.database)) as connection, connection:
            # Invalid raw JSON makes accidental decoding observable; metadata
            # and normalized-only views should not even select that column.
            connection.execute("UPDATE records SET raw_json='not json'")
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["records"], 3)
        document = self.index.read(self.source, "v1", self.loader, include_raw=False)
        self.assertEqual(len(document.rows), 3)
        self.assertEqual(document.raw, [])
        self.assertEqual(self.calls, 1)
        # A request for the damaged column degrades explicitly to the source.
        self.assertEqual(self.index.record(self.source, "v1", self.loader, key="row-0")[2]["value"], 1)
        self.assertTrue(self.index.status()["degraded"])

    def test_identity_lookup_preserves_zero_none_and_all_identity_fields(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        expected = [("r1", self.loader().rows[0], self.loader().raw[0])]
        self.assertEqual(self.index.matches(self.source, "v1", self.loader,
                                           identity=("config", "case", "instance", 0)), expected)
        for identity in (("other", "case", "instance", 0), ("config", "case", "instance", None),
                         ("config", "other", "instance", 0), ("config", "case", "other", 0)):
            self.assertEqual(self.index.matches(self.source, "v1", self.loader, identity=identity), [])

    def test_changed_source_and_parser_version_invalidate_cache(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        self.write_source(200)
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["value"], 200)
        self.assertEqual(self.calls, 2)
        self.index.metadata(self.source, "v2", self.loader)
        self.assertEqual(self.calls, 3)
        self.index.rebuild(self.source, "v2", self.loader)
        self.assertEqual(self.calls, 4)

    def test_atomic_replacement_with_same_length_and_mtime_invalidates_cache(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        original_stat = self.source.stat()
        replacement = self.source.with_suffix(".new")
        replacement.write_text(self.source.read_text(encoding="utf-8").replace('"value": 1', '"value": 9'),
                               encoding="utf-8")
        self.assertEqual(replacement.stat().st_size, original_stat.st_size)
        os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        replacement.replace(self.source)
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["value"], 9)
        self.assertEqual(self.calls, 2)

    def test_missing_and_invalid_sources_never_return_saved_data(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            self.index.metadata(self.source, "v1", self.loader)
        self.source.write_text("not json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.index.metadata(self.source, "v1", self.loader)
        self.write_source(7)
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["value"], 7)

    def test_source_changed_during_loading_retries_once_then_rejects(self) -> None:
        def change_once() -> IndexedDocument:
            document = self.loader()
            if self.calls == 1:
                self.write_source(12)
            return document

        self.assertEqual(self.index.metadata(self.source, "v1", change_once)["value"], 12)
        self.assertEqual(self.calls, 2)
        self.index.clear()

        def keep_changing() -> IndexedDocument:
            document = self.loader()
            self.write_source(document.metadata["value"] + 1)
            return document

        with self.assertRaises(SourceChangedError):
            self.index.read(self.source, "v1", keep_changing)
        self.assertEqual(self.calls, 4)
        self.assertEqual(self.index.status()["indexed_sources"], 0)

    def test_source_changed_during_cached_lookup_is_not_returned(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        cached = self.index._cached
        changed = False

        def change_after_lookup(*args: object) -> object:
            nonlocal changed
            result = cached(*args)
            if not changed:
                changed = True
                self.write_source(99)
            return result

        with patch.object(self.index, "_cached", side_effect=change_after_lookup):
            self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["value"], 99)
        self.assertEqual(self.calls, 2)

    def test_corrupt_database_falls_back_visibly_and_clear_recovers(self) -> None:
        source = self.source.read_bytes()
        self.index.metadata(self.source, "v1", self.loader)
        self.index.database.write_bytes(b"not a sqlite database")
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["value"], 1)
        status = self.index.status()
        self.assertTrue(status["degraded"])
        self.assertIn("DatabaseError", status["last_error"])
        self.assertGreaterEqual(status["fallbacks"], 1)
        self.assertEqual(self.calls, 2)
        cleared = self.index.clear()
        self.assertFalse(cleared["degraded"])
        self.assertEqual(cleared["indexed_sources"], 0)
        self.index.rebuild(self.source, "v1", self.loader)
        self.assertEqual(self.index.status()["indexed_sources"], 1)
        self.assertEqual(self.source.read_bytes(), source)

    def test_storage_failure_falls_back_without_masking_source_failure(self) -> None:
        with patch.object(self.index, "_save", side_effect=OSError("disk unavailable")):
            self.assertEqual(self.index.read(self.source, "v1", self.loader).metadata["value"], 1)
        self.assertIn("disk unavailable", self.index.status()["last_error"])
        self.source.write_text("broken", encoding="utf-8")
        with patch.object(self.index, "_cached", side_effect=OSError("disk unavailable")):
            with self.assertRaises(json.JSONDecodeError):
                self.index.read(self.source, "v1", self.loader)

    def test_threads_share_complete_atomic_documents(self) -> None:
        expected = self.loader()
        original = self.source.read_bytes()

        def read(index: int) -> IndexedDocument:
            local = DashboardIndex(self.root) if index % 2 else self.index
            return local.read(self.source, "v1", self.loader)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(read, range(24)))
        self.assertEqual(results, [expected] * 24)
        self.assertEqual(self.index.status()["indexed_sources"], 1)
        self.assertEqual(self.index.status()["indexed_records"], 3)
        self.assertEqual(self.source.read_bytes(), original)

    def test_processes_share_cache_and_restart_without_parsing_again(self) -> None:
        script = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from maxcover.dashboard_index import DashboardIndex, IndexedDocument
root, source = Path(sys.argv[2]), Path(sys.argv[3])
index = DashboardIndex(root)
def loader():
    return IndexedDocument(**json.loads(source.read_text(encoding='utf-8')))
for _ in range(4):
    assert index.metadata(source, 'v1', loader)['records'] == 3
assert index.status()['indexed_records'] == 3
"""
        processes = [subprocess.Popen([sys.executable, "-c", script, str(ROOT / "src"), str(self.root), str(self.source)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(self.index.metadata(self.source, "v1", lambda: self.fail("restart parsed source"))["records"], 3)
        self.assertEqual(self.calls, 0)

    def test_linked_source_or_cache_is_rejected_without_touching_target(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        original = self.source.read_bytes()
        from maxcover import dashboard_index
        real_linked = dashboard_index._linked
        with patch.object(dashboard_index, "_linked", side_effect=lambda path: path == self.source or real_linked(path)):
            with self.assertRaisesRegex(OSError, "linked"):
                self.index.metadata(self.source, "v1", self.loader)
        with patch.object(dashboard_index, "_linked", side_effect=lambda path: path == self.index.directory or real_linked(path)):
            self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["records"], 3)
            with self.assertRaisesRegex(OSError, "linked"):
                self.index.clear()
        self.assertEqual(self.source.read_bytes(), original)

    def test_invalid_document_is_never_persisted(self) -> None:
        document = self.loader()
        document.rows.append(document.rows[0])
        document.raw.append(document.raw[0])
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.index.read(self.source, "v1", lambda: document)
        self.assertEqual(self.index.status()["indexed_sources"], 0)

    def test_replacing_source_directory_with_actual_link_rejects_warm_cache(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        directory = self.source.parent
        moved = directory.with_name("moved")
        directory.rename(moved)
        try:
            if sys.platform == "win32":
                result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(directory), str(moved)],
                                        capture_output=True, text=True, errors="replace", check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                directory.symlink_to(moved, target_is_directory=True)
            with self.assertRaisesRegex(OSError, "linked"):
                self.index.metadata(self.source, "v1", self.loader)
            self.assertEqual(self.calls, 1)
        finally:
            if directory.exists():
                if sys.platform == "win32":
                    directory.rmdir()
                else:
                    directory.unlink()
            moved.rename(directory)

    def test_cache_hard_links_never_modify_originals_and_clear_refuses_them(self) -> None:
        self.index.directory.mkdir(parents=True)
        for name in ("index.lock", "index.sqlite3", "index.sqlite3-journal", "index.sqlite3-wal", "index.sqlite3-shm"):
            with self.subTest(name=name):
                victim = self.root / ("original-" + name)
                if name == "index.sqlite3":
                    with closing(sqlite3.connect(victim)) as connection, connection:
                        connection.execute("CREATE TABLE original (value TEXT)")
                        connection.execute("INSERT INTO original VALUES ('research data')")
                else:
                    victim.write_bytes(b"" if name == "index.lock" else b"original research data")
                original = victim.read_bytes()
                cache_file = self.index.directory / name
                cache_file.unlink(missing_ok=True)
                os.link(victim, cache_file)
                self.assertEqual(self.index.read(self.source, "v1", self.loader).metadata["records"], 3)
                self.assertTrue(self.index.status()["degraded"])
                with self.assertRaisesRegex(OSError, "hard links"):
                    self.index.clear()
                self.assertTrue(cache_file.exists())
                self.assertEqual(victim.read_bytes(), original)
                cache_file.unlink()
                self.index.clear()

    def test_damaged_cached_row_structures_fall_back_to_complete_source(self) -> None:
        expected = self.loader()
        original = expected.rows[0]
        damaged = ["null", "{}", "[]"]
        damaged.extend(json.dumps({key: value for key, value in original.items() if key != missing})
                       for missing in ("key", "coverage", "status", "source", "config_hash"))
        damaged.extend(json.dumps(dict(original, coverage=value)) for value in ("wrong type", float("nan"), float("inf")))
        for row_json in damaged:
            with self.subTest(row_json=row_json):
                self.index.clear()
                self.index.read(self.source, "v1", self.loader)
                with closing(sqlite3.connect(self.index.database)) as connection, connection:
                    connection.execute("UPDATE records SET row_json=? WHERE position=0", (row_json,))
                before = self.calls
                self.assertEqual(self.index.read(self.source, "v1", self.loader), expected)
                self.assertEqual(self.calls, before + 1)
                self.assertTrue(self.index.status()["degraded"])

    def test_missing_cached_record_cannot_be_reported_as_absent(self) -> None:
        expected = self.loader()
        self.index.read(self.source, "v1", self.loader)
        with closing(sqlite3.connect(self.index.database)) as connection, connection:
            connection.execute("DELETE FROM records WHERE position=0")
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader), expected.metadata)
        self.assertEqual(self.index.read(self.source, "v1", self.loader), expected)
        self.assertEqual(self.index.record(self.source, "v1", self.loader, key="row-0"),
                         ("r1", expected.rows[0], expected.raw[0]))
        self.assertEqual(self.index.matches(self.source, "v1", self.loader, identity=("config", "case", "instance", 0)),
                         [("r1", expected.rows[0], expected.raw[0])])
        self.assertTrue(self.index.status()["degraded"])

    def test_damaged_metadata_and_raw_structure_fall_back(self) -> None:
        expected = self.loader()
        for sql in ("UPDATE sources SET metadata='[]'", "UPDATE sources SET metadata='{}'",
                    "UPDATE sources SET metadata='null'", "UPDATE records SET raw_json='null'",
                    "UPDATE records SET raw_json=NULL", "UPDATE records SET raw_json='{}'"):
            with self.subTest(sql=sql):
                self.index.clear()
                self.index.read(self.source, "v1", self.loader)
                with closing(sqlite3.connect(self.index.database)) as connection, connection:
                    connection.execute(sql)
                self.assertEqual(self.index.read(self.source, "v1", self.loader), expected)
                self.assertTrue(self.index.status()["degraded"])

    def test_cache_encoding_failure_does_not_add_a_source_parser_restriction(self) -> None:
        document = self.loader()
        document.raw[0]["unused_extension"] = float("nan")
        self.assertIs(self.index.read(self.source, "v1", lambda: document), document)
        self.assertTrue(self.index.status()["degraded"])
        self.assertIn("ValueError", self.index.status()["last_error"])
        self.assertEqual(self.index.status()["indexed_sources"], 0)

    def test_same_inode_and_size_rewrite_with_restored_mtime_invalidates_cache(self) -> None:
        self.index.metadata(self.source, "v1", self.loader)
        original = self.source.stat()
        signature = self.index.signature(self.source)
        replacement = self.source.read_bytes().replace(b'"value": 1', b'"value": 9')
        self.source.write_bytes(replacement)
        os.utime(self.source, ns=(original.st_atime_ns, original.st_mtime_ns))
        changed = self.source.stat()
        self.assertEqual(changed.st_ino, original.st_ino)
        self.assertEqual(changed.st_size, original.st_size)
        self.assertEqual(changed.st_mtime_ns, original.st_mtime_ns)
        self.assertNotEqual(self.index.signature(self.source), signature)
        self.assertEqual(self.index.metadata(self.source, "v1", self.loader)["value"], 9)
        self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
