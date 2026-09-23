"""Local saved-data path policy shared by readers and snapshot storage."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path


class WorkbenchError(ValueError):
    status = HTTPStatus.BAD_REQUEST


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def data_file(root: Path, source: str, filename: str) -> Path:
    relative = Path(source)
    if (relative.is_absolute() or not relative.parts or relative.parts[0] not in {"results", "experiments"}
            or ".." in relative.parts or source != relative.as_posix()):
        raise WorkbenchError("source must be under results/ or experiments/")
    path = root / relative / filename
    try:
        path.resolve().relative_to((root / relative.parts[0]).resolve())
    except ValueError as error:
        raise WorkbenchError("source escapes its data directory") from error
    # Refuse links at every level, including Windows junctions resolving outside root.
    for item in (path, *path.parents):
        if item == root:
            break
        if linked(item):
            raise WorkbenchError("linked data paths are not supported")
    return path
