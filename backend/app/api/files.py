from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from app.services import storage


router = APIRouter(prefix="/files", tags=["files"])


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@router.get("/{local_path:path}")
async def get_file(
    local_path: str,
    range_header: str | None = Header(default=None, alias="Range"),
) -> StreamingResponse:
    try:
        path = storage.resolve_asset_path(local_path)
    except storage.StoragePathError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset file was not found.",
        ) from exc

    size = path.stat().st_size
    media_type = guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Accept-Ranges": "bytes"}

    if range_header is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(
            _iter_file(path),
            media_type=media_type,
            headers=headers,
        )

    byte_range = _parse_range(range_header, size)
    if byte_range is None:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Requested byte range is not satisfiable.",
            headers={"Content-Range": f"bytes */{size}"},
        )

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


def _parse_range(header: str, size: int) -> ByteRange | None:
    if size < 1 or not header.startswith("bytes="):
        return None

    spec = header.removeprefix("bytes=").strip()
    if "," in spec or "-" not in spec:
        return None

    start_text, end_text = spec.split("-", 1)
    if not start_text and not end_text:
        return None

    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length < 1:
                return None
            start = max(0, size - suffix_length)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError:
        return None

    if start < 0 or end < start or start >= size:
        return None

    return ByteRange(start=start, end=min(end, size - 1))


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
