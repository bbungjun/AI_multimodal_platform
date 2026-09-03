from __future__ import annotations

from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.config import Settings
from app.api import files, auth_dependencies
from app.main import app
from app.services.vertex import storage


def _settings_for_data_dir(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def registered_files(monkeypatch, tmp_path):
    """Only opted-in HTTP tests register saved paths for an ordinary owner."""
    owner = SimpleNamespace(id=uuid4(), role="user")
    rows = {}
    original_save = storage.save_bytes
    def save(job_id, filename, data):
        path = original_save(job_id, filename, data)
        rows[path] = SimpleNamespace(job_id=job_id, local_path=path)
        return path
    async def execute(statement):
        path = next((v for v in statement.compile().params.values() if isinstance(v, str)), None)
        row = rows.get(path)
        return Mock(one_or_none=lambda: (row, owner.id) if row else None)
    async def session():
        yield SimpleNamespace(execute=execute)
    monkeypatch.setattr(storage, "save_bytes", save)
    monkeypatch.setattr(files, "get_settings", lambda: _settings_for_data_dir(tmp_path))
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[files.get_session] = session
    app.dependency_overrides[auth_dependencies.require_user] = lambda: owner
    try:
        yield rows
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_save_read_delete_bytes_roundtrip_in_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    job_id = uuid4()

    local_path = storage.save_bytes(job_id, "output.txt", b"hello")

    assert local_path == f"{job_id}/output.txt"
    assert storage.read_bytes(local_path) == b"hello"

    storage.delete_file(local_path, missing_ok=False)

    assert not (tmp_path / str(job_id) / "output.txt").exists()


def test_storage_rejects_unsafe_filename_and_path(monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    job_id = uuid4()

    with pytest.raises(storage.StoragePathError):
        storage.save_bytes(job_id, "../secret.txt", b"nope")

    with pytest.raises(storage.StoragePathError):
        storage.read_bytes(f"{job_id}/../secret.txt")


async def test_files_route_streams_saved_asset(registered_files, monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/files/{local_path}")

    assert response.status_code == 200
    assert response.content == b"abcdef"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "6"
    assert response.headers["content-type"].startswith("text/plain")


async def test_files_route_supports_single_byte_range(registered_files, monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "bytes=2-4"},
        )

    assert response.status_code == 206
    assert response.content == b"cde"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "3"
    assert response.headers["content-range"] == "bytes 2-4/6"


async def test_files_route_partial_video_response_includes_preview_headers(registered_files,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.mp4", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "bytes=1-3"},
        )

    assert response.status_code == 206
    assert response.content == b"bcd"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "3"
    assert response.headers["content-range"] == "bytes 1-3/6"
    assert response.headers["content-type"].startswith("video/mp4")


async def test_files_route_supports_open_ended_byte_range(registered_files, monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "bytes=3-"},
        )

    assert response.status_code == 206
    assert response.content == b"def"
    assert response.headers["content-length"] == "3"
    assert response.headers["content-range"] == "bytes 3-5/6"


async def test_files_route_supports_suffix_byte_range(registered_files, monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "bytes=-2"},
        )

    assert response.status_code == 206
    assert response.content == b"ef"
    assert response.headers["content-length"] == "2"
    assert response.headers["content-range"] == "bytes 4-5/6"


async def test_files_route_returns_416_for_unsatisfiable_byte_range(
    registered_files,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "bytes=99-100"},
        )

    assert response.status_code == 416
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == "bytes */6"
    assert response.json()["detail"] == "Requested byte range is not satisfiable."


async def test_files_route_rejects_multiple_ranges_with_400(registered_files, monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "bytes=0-1,3-4"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only single byte ranges are supported."


async def test_files_route_rejects_unsupported_range_unit_with_400(
    registered_files,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )
    local_path = storage.save_bytes(uuid4(), "output.txt", b"abcdef")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/files/{local_path}",
            headers={"Range": "items=0-1"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported range unit."


async def test_files_route_rejects_unsafe_path(registered_files, monkeypatch, tmp_path):
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/files/not-a-uuid/output.txt")

    assert response.status_code == 404
    assert response.json()["detail"] == "content_not_found"


@pytest.mark.parametrize("body,header,code,expected", [(b"",None,200,b""),(b"","bytes=0-",416,None),
    (b"abcdef","bytes=2-99",206,b"cdef"),(b"abcdef","bytes=oops",400,None)])
async def test_file_ops_empty_clipped_malformed_and_cache(registered_files,monkeypatch,tmp_path,body,header,code,expected):
    monkeypatch.setattr(storage,"get_settings",lambda:_settings_for_data_dir(tmp_path))
    path=storage.save_bytes(uuid4(),"output.bin",body)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.get("/files/"+path,headers={"Range":header} if header else None)
    assert response.status_code==code and response.headers["cache-control"]=="private, no-store"
    if expected is not None:
        assert response.content==expected
    if code==416:
        assert response.headers["content-range"]=="bytes */0"


@pytest.mark.parametrize("role",["user","master"])
@pytest.mark.parametrize("kind",["orphan","missing","alias"])
async def test_file_ops_registered_disk_consistency(registered_files,monkeypatch,tmp_path,role,kind):
    import os
    monkeypatch.setattr(storage,"get_settings",lambda:_settings_for_data_dir(tmp_path))
    actor=app.dependency_overrides[auth_dependencies.require_user]()
    actor.role=role
    path=storage.save_bytes(uuid4(),"output.txt",b"owned")
    if kind=="orphan":
        registered_files.pop(path)
    elif kind=="missing":
        storage.delete_file(path)
    else:
        other=storage.save_bytes(uuid4(),"other.txt",b"foreign")
        if os.name=="nt":
            # Windows symlink privilege varies; authoritative Linux uses a real alias.
            monkeypatch.setattr(files.storage,"resolve_asset_path",lambda value:tmp_path/other)
        else:
            (tmp_path/path).unlink()
            (tmp_path/path).symlink_to(tmp_path/other)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.get("/files/"+path,headers={"Range":"invalid"})
    assert response.status_code==404 and response.json()=={"detail":"content_not_found"}
    assert "content-range" not in response.headers
