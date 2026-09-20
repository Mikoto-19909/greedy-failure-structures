"""Reversible local archive flags; source jobs and saved views stay untouched."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any

from .dashboard_exports import ComparisonExports
from .dashboard_jobs import _read, _validate_record
from .dashboard_workbench import WorkbenchError

_ID = re.compile(r"[0-9a-f]{32}\Z")
_KINDS = ("job", "view")
_TERMINAL = ("completed", "failed", "interrupted")


class LocalCatalogError(WorkbenchError):
    """Invalid source object or unavailable local archive metadata."""


class _ActiveJobError(LocalCatalogError):
    status = HTTPStatus.CONFLICT


class LocalCatalog:
    """Keep archive state in a small SQLite sidecar, shared safely by processes.

    ``list`` returns annotations only for objects that are still readable and
    eligible. Missing or damaged source objects therefore remain visible through
    their original list/error routes rather than disappearing into the archive.
    A list of a new workspace does not create a database.
    """

    def __init__(self, project_root: Path) -> None:
        # Keep the lexical path until link checks have run; resolve() would hide
        # a junction or symlink at the project root itself.
        self.root = Path(os.path.abspath(project_root))
        self._warnings: list[str] = []

    def _path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        for item in (self.root, *[self.root.joinpath(*parts[:i]) for i in range(1, len(parts) + 1)]):
            try:
                info = item.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise LocalCatalogError("linked or reparse local data paths are not supported")
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise LocalCatalogError("local data paths must be ordinary files or directories")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise LocalCatalogError("hard-linked local data files are not supported")
        return path

    def _database(self, *, create: bool) -> Path:
        for count in (1, 2):
            path = self._path(*("results", ".dashboard_local")[:count])
            if create:
                path.mkdir(exist_ok=True)
                self._path(*("results", ".dashboard_local")[:count])
        path = self._path("results", ".dashboard_local", "catalog.sqlite3")
        for suffix in ("-journal", "-wal", "-shm"):
            self._path("results", ".dashboard_local", "catalog.sqlite3" + suffix)
        return path

    @staticmethod
    def _identity(kind: str, identifier: str | None = None) -> None:
        if kind not in _KINDS:
            raise LocalCatalogError("local archive kind must be job or view")
        if identifier is not None and (not isinstance(identifier, str) or not _ID.fullmatch(identifier)):
            raise LocalCatalogError("invalid local archive id")

    def _validate_source(self, kind: str, identifier: str) -> None:
        try:
            if kind == "job":
                path = self._path("results", "workbench_jobs", identifier, "job.json")
                job = _read(path)
                _validate_record(job, identifier)
                if job["status"] not in _TERMINAL:
                    raise _ActiveJobError("only completed, failed or interrupted jobs can be archived")
            else:
                self._path("results", "dashboard_views", identifier + ".json")
                ComparisonExports(self.root)._read(identifier)
        except LocalCatalogError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise LocalCatalogError(f"Cannot archive {kind} {identifier}: {error}") from error

    def status(self) -> dict[str, list[str]]:
        """Diagnostics from the most recent listing; original errors stay visible."""
        return {"warnings": list(self._warnings)}

    def list(self, kind: str) -> dict[str, dict[str, Any]]:
        self._identity(kind)
        self._warnings = []
        try:
            path = self._database(create=False)
            if not path.exists():
                return {}
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)) as connection:
                rows = connection.execute(
                    "SELECT identifier, archived, updated_at FROM annotations WHERE kind = ?", (kind,)
                ).fetchall()
            result = {}
            for identifier, archived, updated_at in rows:
                try:
                    self._identity(kind, identifier)
                    if archived not in (0, 1) or not isinstance(updated_at, str):
                        raise LocalCatalogError("invalid local archive annotation")
                    self._validate_source(kind, identifier)
                except LocalCatalogError as error:
                    self._warnings.append(str(error))
                    continue
                result[identifier] = {"archived": bool(archived), "updated_at": updated_at}
            return result
        except (OSError, sqlite3.Error) as error:
            raise LocalCatalogError(f"Cannot read local archive: {error}") from error

    def set_archived(self, kind: str, identifier: str, archived: bool) -> dict[str, Any]:
        self._identity(kind, identifier)
        if type(archived) is not bool:
            raise LocalCatalogError("archived must be a boolean")
        # Validate before creating any metadata for invalid requests, and again
        # after obtaining the write transaction. Terminal jobs are never reused:
        # existing retries receive a new id and directory.
        self._validate_source(kind, identifier)
        try:
            path = self._database(create=True)
            with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("""CREATE TABLE IF NOT EXISTS annotations (
                    kind TEXT NOT NULL CHECK (kind IN ('job', 'view')),
                    identifier TEXT NOT NULL,
                    archived INTEGER NOT NULL CHECK (archived IN (0, 1)),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (kind, identifier))""")
                self._validate_source(kind, identifier)
                updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
                connection.execute("""INSERT INTO annotations VALUES (?, ?, ?, ?)
                    ON CONFLICT(kind, identifier) DO UPDATE SET
                    archived = excluded.archived, updated_at = excluded.updated_at""",
                    (kind, identifier, int(archived), updated_at))
            return {"archived": archived, "updated_at": updated_at}
        except (OSError, sqlite3.Error) as error:
            raise LocalCatalogError(f"Cannot update local archive: {error}") from error
