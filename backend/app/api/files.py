from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import require_user
from app.api.generations import get_session
from app.auth.service import AuthenticatedUser
from app.config import get_settings
from app.ownership import OwnershipAccess
from app.services import storage


router = APIRouter(prefix="/files", tags=["files"])


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


class RangeRequestError(ValueError):
    def __init__(
        self,
        detail: str,
        *,
        status_code: int,
        include_content_range: bool = False,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.include_content_range = include_content_range
        super().__init__(detail)


@router.get("/{local_path:path}")
async def get_file(
    local_path: str,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    actor: AuthenticatedUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    raw_path = request.scope.get("raw_path")
    if raw_path is not None and raw_path != ("/files/" + local_path).encode("utf-8"):
        raise HTTPException(404, detail="content_not_found")
    asset = await OwnershipAccess(session, actor).file_asset(local_path)
    try:
        path = storage.resolve_asset_path(local_path)
        expected = get_settings().data_dir.resolve() / str(asset.job_id) / local_path.split("/")[1]
        if path != expected:
            raise storage.StoragePathError("Asset path alias refused")
        size = path.stat().st_size
    except (storage.StoragePathError, OSError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="content_not_found",
        ) from None

    media_type = guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Accept-Ranges": "bytes"}

    if range_header is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(
            _iter_file(path),
            media_type=media_type,
            headers=headers,
        )

    try:
        byte_range = _parse_range(range_header, size)
    except RangeRequestError as exc:
        range_headers = {"Accept-Ranges": "bytes"}
        if exc.include_content_range:
            range_headers["Content-Range"] = f"bytes */{size}"
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=range_headers,
        ) from exc

    headers.update(
        {
            "Content-Length": str(byte_range.length),
            "Content-Range": f"bytes {byte_range.start}-{byte_range.end}/{size}",
        }
    )
    return StreamingResponse(
        _iter_file(path, start=byte_range.start, length=byte_range.length),
        media_type=media_type,
        headers=headers,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
    )


def _parse_range(header: str, size: int) -> ByteRange:
    if size < 1:
        raise _unsatisfiable_range()

    if not header.startswith("bytes="):
        raise RangeRequestError(
            "Unsupported range unit.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    spec = header.removeprefix("bytes=").strip()
    if "," in spec:
        raise RangeRequestError(
            "Only single byte ranges are supported.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if "-" not in spec:
        raise _malformed_range()

    start_text, end_text = spec.split("-", 1)
    if not start_text and not end_text:
        raise _malformed_range()

    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length < 1:
                raise _unsatisfiable_range()
            start = max(0, size - suffix_length)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError:
        raise _malformed_range() from None

    if start < 0 or end < start or start >= size:
        raise _unsatisfiable_range()

    return ByteRange(start=start, end=min(end, size - 1))


def _malformed_range() -> RangeRequestError:
    return RangeRequestError(
        "Malformed Range header.",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def _unsatisfiable_range() -> RangeRequestError:
    return RangeRequestError(
        "Requested byte range is not satisfiable.",
        status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
        include_content_range=True,
    )


def _iter_file(
    path: Path,
    *,
    start: int = 0,
    length: int | None = None,
    chunk_size: int = 1024 * 1024,
) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as file:
        file.seek(start)
        while remaining is None or remaining > 0:
            read_size = chunk_size if remaining is None else min(chunk_size, remaining)
            data = file.read(read_size)
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data
