from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx

from app.api import assets
from app.main import app
from app.models import Asset, AssetKind, utc_now


class FakeAssetSession:
    def __init__(self, asset: Asset | None) -> None:
        self.asset = asset
        self.get_calls: list[tuple[object, object]] = []

    async def get(self, model: object, entity_id: object) -> object | None:
        self.get_calls.append((model, entity_id))
        if model is Asset and self.asset is not None and self.asset.id == entity_id:
            return self.asset
        return None


async def _get_asset(path: str, session: FakeAssetSession):
    async def override_session() -> AsyncIterator[FakeAssetSession]:
        yield session

    app.dependency_overrides[assets.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.pop(assets.get_session, None)


def _image_asset() -> Asset:
    now = utc_now()
    job_id = uuid4()
    return Asset(
        id=uuid4(),
        job_id=job_id,
        kind=AssetKind.IMAGE,
        local_path=f"{job_id}/output.png",
        mime="image/png",
        size_bytes=123,
        width=640,
        height=360,
        created_at=now,
    )


async def test_get_asset_returns_asset_dto_with_file_url():
    asset = _image_asset()
    session = FakeAssetSession(asset)

    response = await _get_asset(f"/api/assets/{asset.id}", session)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": str(asset.id),
        "job_id": str(asset.job_id),
        "kind": "image",
        "local_path": asset.local_path,
        "mime": "image/png",
        "size_bytes": 123,
        "width": 640,
        "height": 360,
        "duration_sec": None,
        "created_at": asset.created_at.isoformat().replace("+00:00", "Z"),
        "url": f"/files/{asset.local_path}",
    }
    assert session.get_calls == [(Asset, asset.id)]


async def test_get_asset_returns_404_for_missing_asset():
    missing_asset_id = uuid4()
    session = FakeAssetSession(None)

    response = await _get_asset(f"/api/assets/{missing_asset_id}", session)

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset was not found."
    assert session.get_calls == [(Asset, missing_asset_id)]
