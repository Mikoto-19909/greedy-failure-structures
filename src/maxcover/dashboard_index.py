"""Disposable SQLite views of validated, local workbench source files.

CSV/JSON files remain authoritative. Every access checks their identity before
and after reading; failed parsing is never cached. SQLite failures fall back to
the same loader and are visible in ``status()``. No source file is written here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import sys
import threading
import time
from typing import Any, TypeAlias


@dataclass
class IndexedDocument:
    kind: str
    rows: list[dict[str, Any]]
    raw: list[dict[str, Any]]
    metadata: dict[str, Any]


Loader: TypeAlias = Callable[[], IndexedDocument]
Record: TypeAlias = tuple[str, dict[str, Any], dict[str, Any] | None]
Signature: TypeAlias = tuple[int, int, int, int, int, int]
Identity: TypeAlias = tuple[Any, Any, Any, Any]


class SourceChangedError(OSError):
    """A source did not remain stable for a bounded read attempt."""


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _FileBasicInfo(ctypes.Structure):
        _fields_ = [("CreationTime", ctypes.c_longlong), ("LastAccessTime", ctypes.c_longlong),
                    ("LastWriteTime", ctypes.c_longlong), ("ChangeTime", ctypes.c_longlong),
                    ("FileAttributes", wintypes.DWORD)]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _open_file = _kernel32.CreateFileW
    _open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _open_file.restype = wintypes.HANDLE
    _file_info = _kernel32.GetFileInformationByHandleEx
    _file_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _file_info.restype = wintypes.BOOL
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = [wintypes.HANDLE]
    _close_handle.restype = wintypes.BOOL

    def _windows_change_time(path: Path) -> int:
        """Read NTFS metadata change time; Windows stat ctime is creation time.

        FILE_BASIC_INFO / GetFileInformationByHandleEx definitions:
        https://learn.microsoft.com/windows/win32/api/winbase/ns-winbase-file_basic_info
        https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex
        """
        # FILE_READ_ATTRIBUTES; SHARE_READ | SHARE_WRITE | SHARE_DELETE;
        # OPEN_EXISTING; FILE_FLAG_OPEN_REPARSE_POINT. No source data is read/written.
        handle = _open_file(str(path), 0x80, 0x1 | 0x2 | 0x4, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info = _FileBasicInfo()
            if not _file_info(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):  # FileBasicInfo = 0
                raise ctypes.WinError(ctypes.get_last_error())
            if info.FileAttributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise OSError("linked source paths are not supported")
            if info.ChangeTime <= 0:
                raise OSError("Windows source change time is unavailable")
            return int(info.ChangeTime) * 100
        finally:
            _close_handle(handle)

else:
    def _windows_change_time(path: Path) -> int:
        raise OSError("Windows change-time metadata is only available on Windows")


def _linked(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    # Path.is_junction arrived in Python 3.12; the project also supports 3.11.
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0)
                                            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _shape(value: dict[str, Any]) -> str:
    return _json([(key, type(item).__name__) for key, item in sorted(value.items())])


def _object(value: str, shape: str) -> dict[str, Any]:
    def finite(text: str) -> float:
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("non-finite number in disposable index")
        return number

    decoded = json.loads(value, parse_float=finite, parse_constant=finite)
    if not isinstance(decoded, dict) or _shape(decoded) != shape:
        raise ValueError("disposable index record structure is damaged")
    return decoded


class DashboardIndex:
    """One local, rebuildable index, shared safely across dashboard processes."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.absolute()
        self.directory = self.root / "results" / ".dashboard_index"
        self.database = self.directory / "index.sqlite3"
        self._mutex = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._fallbacks = 0
        self._last_error: str | None = None

    def _check_path(self, path: Path) -> None:
        if not path.is_absolute() or ".." in path.parts:
            raise OSError("index paths must be absolute and inside the project")
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise OSError("index path escapes the project") from error
        for item in (path, *path.parents):
            if _linked(item):
                raise OSError("linked index or source paths are not supported")
            if item == self.root:
                break

    def signature(self, path: Path) -> Signature:
        """Reject missing/linked/non-file sources and return a cheap stat identity."""
        self._check_path(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise OSError("index source must be a regular file")
        changed = _windows_change_time(path) if sys.platform == "win32" else info.st_ctime_ns
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, changed

    def _check_cache_file(self, path: Path) -> None:
        self._check_path(path)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OSError("index files must be regular files without hard links")

    @contextmanager
    def _cache_lock(self) -> Iterator[None]:
        # This short OS lock also makes explicit removal of a corrupt database
        # safe against other instances. Parsing source data runs outside it.
        with self._mutex:
            self._check_path(self.directory)
            self.directory.mkdir(parents=True, exist_ok=True)
            lock_path = self.directory / "index.lock"
            self._check_cache_file(lock_path)
            for name in ("index.sqlite3", "index.sqlite3-journal", "index.sqlite3-wal", "index.sqlite3-shm"):
                self._check_cache_file(self.directory / name)
            with lock_path.open("a+b") as handle:
                lock_info = os.fstat(handle.fileno())
                if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1:
                    raise OSError("index lock must be a regular file without hard links")
                if lock_info.st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                deadline = time.monotonic() + 5
                while True:
                    try:
                        handle.seek(0)
                        if sys.platform == "win32":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise OSError("local index is busy; source data remains available")
                        time.sleep(0.01)
                for name in ("index.sqlite3", "index.sqlite3-journal", "index.sqlite3-wal", "index.sqlite3-shm"):
                    self._check_cache_file(self.directory / name)
                # Closing the descriptor releases the OS lock on both platforms.
                yield

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 2}:
                raise sqlite3.DatabaseError("unsupported disposable index schema; clear to rebuild")
            if version == 0:
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS sources (
                        path TEXT PRIMARY KEY, signature TEXT NOT NULL,
                        parser TEXT NOT NULL, kind TEXT NOT NULL, metadata TEXT NOT NULL,
                        metadata_shape TEXT NOT NULL, record_count INTEGER NOT NULL, raw_count INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS records (
                        source TEXT NOT NULL REFERENCES sources(path) ON DELETE CASCADE,
                        position INTEGER NOT NULL, key TEXT NOT NULL, identity TEXT NOT NULL,
                        row_json TEXT NOT NULL, raw_json TEXT, row_shape TEXT NOT NULL, raw_shape TEXT,
                        PRIMARY KEY(source, key)
                    );
                    CREATE INDEX IF NOT EXISTS records_identity ON records(source, identity);
                    CREATE INDEX IF NOT EXISTS records_position ON records(source, position);
                    PRAGMA user_version=2;
                """)
            yield connection
        finally:
            connection.close()

    def _cache_error(self, error: Exception) -> None:
        with self._mutex:
            self._fallbacks += 1
            self._last_error = f"{type(error).__name__}: {error}"

    def _cached(self, path: Path, version: str, signature: Signature,
                view: str, argument: Any) -> tuple[bool, Any]:
        with self._cache_lock(), self._connection() as connection:
            source = path.relative_to(self.root).as_posix()
            saved = connection.execute(
                "SELECT kind, metadata, metadata_shape, record_count, raw_count "
                "FROM sources WHERE path=? AND parser=? AND signature=?",
                (source, version, _json(signature))).fetchone()
            if saved is None:
                return False, None
            kind, encoded_metadata, metadata_shape, record_count, raw_count = saved
            if (not isinstance(kind, str) or not kind or type(record_count) is not int or record_count < 0
                    or type(raw_count) is not int or raw_count not in {0, record_count}):
                raise ValueError("disposable index source structure is damaged")
            metadata = _object(encoded_metadata, metadata_shape)
            # Count through the source index, without decoding rows or reading
            # raw trajectories. A missing row must not become a false absence.
            actual_count = connection.execute("SELECT count(*) FROM records WHERE source=?", (source,)).fetchone()[0]
            if actual_count != record_count or ("records" in metadata and metadata["records"] != record_count):
                raise ValueError("disposable index record count is damaged")
            if view == "metadata":
                return True, metadata

            def decode(record: tuple[Any, ...], *, with_raw: bool) -> Record:
                key, identity, row_json, row_shape = record[:4]
                row = _object(row_json, row_shape)
                if not row.get("key") or row["key"] != key or _json(self._identity(row)) != identity:
                    raise ValueError("disposable index record identity is damaged")
                raw = None
                if with_raw:
                    raw_json, raw_shape = record[4:]
                    if raw_count:
                        if raw_json is None or raw_shape is None:
                            raise ValueError("disposable index raw records are incomplete")
                        raw = _object(raw_json, raw_shape)
                    elif raw_json is not None or raw_shape is not None:
                        raise ValueError("disposable index raw records disagree with source metadata")
                return kind, row, raw

            if view == "read":
                columns = "key, identity, row_json, row_shape" + (", raw_json, raw_shape" if argument else "")
                records = connection.execute(
                    f"SELECT {columns} FROM records WHERE source=? ORDER BY position", (source,)).fetchall()
                decoded = [decode(record, with_raw=bool(argument)) for record in records]
                return True, IndexedDocument(kind, [item[1] for item in decoded],
                                              [item[2] for item in decoded if item[2] is not None], metadata)
            column = "key" if view == "record" else "identity"
            records = connection.execute(
                f"SELECT key, identity, row_json, row_shape, raw_json, raw_shape "
                f"FROM records WHERE source=? AND {column}=? ORDER BY position",
                (source, argument if view == "record" else _json(argument))).fetchall()
            selected = [decode(record, with_raw=True) for record in records]
            return True, (selected[0] if selected else None) if view == "record" else selected

    @staticmethod
    def _identity(row: dict[str, Any]) -> Identity:
        return row.get("config_hash"), row.get("case_id"), row.get("instance_id"), row.get("repetition")

    @staticmethod
    def _validate(document: IndexedDocument) -> None:
        if (not isinstance(document.kind, str) or not document.kind or not isinstance(document.metadata, dict)
                or any(not isinstance(row, dict) for row in [*document.rows, *document.raw])):
            raise ValueError("indexed documents require a kind and object records")
        if document.raw and len(document.raw) != len(document.rows):
            raise ValueError("indexed raw records must align with normalized rows")
        keys = [row["key"] for row in document.rows]
        if any(not isinstance(key, str) or not key for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("indexed rows require distinct non-empty string keys")

    def _save(self, path: Path, version: str, signature: Signature, document: IndexedDocument) -> None:
        source = path.relative_to(self.root).as_posix()
        # Encode outside the short database lock; large raw R1 traces need not
        # hold up another request's metadata lookup.
        records = [(source, position, row["key"], _json(self._identity(row)), _json(row),
                    _json(document.raw[position]) if document.raw else None, _shape(row),
                    _shape(document.raw[position]) if document.raw else None)
                   for position, row in enumerate(document.rows)]
        metadata = _json(document.metadata)
        with self._cache_lock(), self._connection() as connection, connection:
            connection.execute("DELETE FROM sources WHERE path=?", (source,))
            connection.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (source, _json(signature), version, document.kind, metadata,
                                _shape(document.metadata), len(document.rows), len(document.raw)))
            connection.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)", records)

    def _project(self, document: IndexedDocument, view: str, argument: Any) -> Any:
        if view == "metadata":
            return document.metadata
        if view == "read":
            return document if argument else IndexedDocument(document.kind, document.rows, [], document.metadata)
        selected: list[Record] = [
            (document.kind, row, document.raw[position] if document.raw else None)
            for position, row in enumerate(document.rows)
            if (row["key"] == argument if view == "record" else self._identity(row) == argument)]
        return (selected[0] if selected else None) if view == "record" else selected

    def _request(self, path: Path, version: str, loader: Loader, view: str,
                 argument: Any = None, *, refresh: bool = False) -> Any:
        for _ in range(2):
            before = self.signature(path)
            cache_available = True
            if not refresh:
                try:
                    found, result = self._cached(path, version, before, view, argument)
                except (sqlite3.Error, OSError, ValueError, TypeError, KeyError) as error:
                    self._cache_error(error)
                    cache_available, found = False, False
                if found:
                    if self.signature(path) != before:
                        continue
                    with self._mutex:
                        self._hits += 1
                    return result
            with self._mutex:
                self._misses += 1
            # Deliberately outside the cache exception handler: a broken source
            # must fail visibly, even if an older valid entry exists on disk.
            document = loader()
            self._validate(document)
            if self.signature(path) != before:
                continue
            if cache_available:
                try:
                    self._save(path, version, before, document)
                except (sqlite3.Error, OSError, ValueError, TypeError) as error:
                    self._cache_error(error)
            if self.signature(path) != before:
                continue
            return self._project(document, view, argument)
        raise SourceChangedError("source changed while being read; retry after its writer finishes")

    def metadata(self, path: Path, parser_version: str, loader: Loader) -> dict[str, Any]:
        result: dict[str, Any] = self._request(path, parser_version, loader, "metadata")
        return result

    def read(self, path: Path, parser_version: str, loader: Loader, *, include_raw: bool = True) -> IndexedDocument:
        result: IndexedDocument = self._request(path, parser_version, loader, "read", include_raw)
        return result

    def record(self, path: Path, parser_version: str, loader: Loader, *, key: str) -> Record | None:
        result: Record | None = self._request(path, parser_version, loader, "record", key)
        return result

    def matches(self, path: Path, parser_version: str, loader: Loader, *, identity: Identity) -> list[Record]:
        result: list[Record] = self._request(path, parser_version, loader, "matches", identity)
        return result

    def rebuild(self, path: Path, parser_version: str, loader: Loader) -> dict[str, Any]:
        result: dict[str, Any] = self._request(path, parser_version, loader, "metadata", refresh=True)
        return result

    def status(self) -> dict[str, Any]:
        sources, records, size = 0, 0, 0
        try:
            self._check_path(self.database)
            if self.database.exists():
                with self._cache_lock(), self._connection() as connection:
                    sources = connection.execute("SELECT count(*) FROM sources").fetchone()[0]
                    records = connection.execute("SELECT count(*) FROM records").fetchone()[0]
                    size = self.database.stat().st_size
        except (sqlite3.Error, OSError) as error:
            self._cache_error(error)
        with self._mutex:
            return {"cache_path": self.directory.relative_to(self.root).as_posix(),
                    "indexed_sources": sources, "indexed_records": records, "database_bytes": size,
                    "hits": self._hits, "misses": self._misses, "fallbacks": self._fallbacks,
                    "degraded": self._last_error is not None, "last_error": self._last_error}

    def clear(self) -> dict[str, Any]:
        """Remove only this derived database under the same lock as all readers."""
        with self._cache_lock():
            # All index users close their SQLite connections before releasing
            # the lock, so removal also recovers a corrupt/unsupported schema.
            for name in ("index.sqlite3", "index.sqlite3-journal", "index.sqlite3-wal", "index.sqlite3-shm"):
                (self.directory / name).unlink(missing_ok=True)
            self._last_error = None
        return self.status()
