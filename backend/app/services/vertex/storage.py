from __future__ import annotations

import os
import re
import stat
from pathlib import Path, PurePosixPath
from uuid import UUID

from app.config import get_settings


class StoragePathError(ValueError):
    pass


_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def save_bytes(job_id: UUID | str, filename: str, data: bytes) -> str:
    job_uuid = _coerce_job_id(job_id)
    safe_filename = _validate_filename(filename)
    root = _storage_root()
    job_dir = root / str(job_uuid)

    try:
        job_dir.mkdir(mode=0o755, exist_ok=True)
        job_dir_resolved = job_dir.resolve(strict=True)
        _ensure_inside_root(job_dir_resolved, root)
    except OSError as exc:
        raise StoragePathError("Could not prepare asset directory") from exc

    target = job_dir / safe_filename
    _ensure_inside_root(target.resolve(strict=False), root)

    dir_fd: int | None = None
    file_fd: int | None = None
    try:
        dir_fd = os.open(job_dir, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        file_fd = os.open(
            safe_filename,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW,
            0o644,
            dir_fd=dir_fd,
        )
        with os.fdopen(file_fd, "wb") as output:
            file_fd = None
            output.write(data)
    except OSError as exc:
        raise StoragePathError("Could not write asset safely") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if dir_fd is not None:
            os.close(dir_fd)

    return f"{job_uuid}/{safe_filename}"


def read_bytes(local_path: str) -> bytes:
    return resolve_asset_path(local_path).read_bytes()


def delete_file(local_path: str, *, missing_ok: bool = True) -> None:
    job_id, filename = _parse_local_path(local_path)
    root = _storage_root()
    job_dir = root / job_id

    try:
        job_dir_resolved = job_dir.resolve(strict=True)
        _ensure_inside_root(job_dir_resolved, root)
    except FileNotFoundError:
        if missing_ok:
            return
        raise StoragePathError("Asset path does not exist") from None
    except OSError as exc:
        raise StoragePathError("Could not inspect asset directory") from exc

    dir_fd: int | None = None
    try:
        dir_fd = os.open(job_dir, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        try:
            file_stat = os.stat(filename, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return
            raise StoragePathError("Asset path does not exist") from None

        if not stat.S_ISREG(file_stat.st_mode):
            raise StoragePathError("Asset path is not a regular file")

        os.unlink(filename, dir_fd=dir_fd)
    except StoragePathError:
        raise
    except OSError as exc:
        raise StoragePathError("Could not delete asset safely") from exc
    finally:
        if dir_fd is not None:
            os.close(dir_fd)

    try:
        job_dir.rmdir()
    except OSError:
        pass


def resolve_asset_path(local_path: str) -> Path:
    path = _safe_path(local_path, must_exist=True)
    if not path.is_file():
        raise StoragePathError("Asset path is not a file")
    return path


def _safe_path(local_path: str, *, must_exist: bool = False) -> Path:
    job_id, filename = _parse_local_path(local_path)
    root = _storage_root()
    candidate = root / job_id / filename
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise StoragePathError("Asset path does not exist") from exc

    return _ensure_inside_root(resolved, root)


def _parse_local_path(local_path: str) -> tuple[str, str]:
    if not local_path or "\\" in local_path:
        raise StoragePathError("Asset path must be a relative POSIX path")

    path = PurePosixPath(local_path)
    if path.is_absolute():
        raise StoragePathError("Asset path must be relative")

    parts = path.parts
    if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
        raise StoragePathError("Asset path must be '<job_uuid>/<filename>'")

    job_id, filename = parts
    job_uuid = _coerce_job_id(job_id)
    safe_filename = _validate_filename(filename)
    return str(job_uuid), safe_filename


def _storage_root() -> Path:
    root = get_settings().data_dir
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    return root.resolve(strict=True)


def _coerce_job_id(job_id: UUID | str) -> UUID:
    try:
        return job_id if isinstance(job_id, UUID) else UUID(str(job_id))
    except ValueError as exc:
        raise StoragePathError("Job id must be a UUID") from exc


def _validate_filename(filename: str) -> str:
    if not filename or filename in {".", ".."}:
        raise StoragePathError("Filename is required")
    if "/" in filename or "\\" in filename:
        raise StoragePathError("Filename must not contain path separators")
    if not _SAFE_FILENAME.fullmatch(filename):
        raise StoragePathError("Filename contains unsupported characters")
    return filename


def _ensure_inside_root(path: Path, root: Path) -> Path:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise StoragePathError("Asset path escapes DATA_DIR") from exc
    return path
