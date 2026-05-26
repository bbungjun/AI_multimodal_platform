from __future__ import annotations

import httpx

from app.config import Settings
from app.api import health as health_api
from app.main import app
from app.services.vertex import client as vertex_client
from app.services.vertex.client import VertexReadiness


async def _db_up() -> bool:
    return True


def _vertex_not_ready() -> VertexReadiness:
    return VertexReadiness(
        ready=False,
        status="vertex_credentials_missing",
        credentials="missing",
        project="unknown",
        location="us-central1",
    )


def _mock_settings() -> Settings:
    return Settings(ai_provider="mock")


def _fail_vertex_client() -> None:
    raise AssertionError("mock health must not create a Vertex client")


async def test_health_ok_tracks_db_when_vertex_is_not_ready(monkeypatch):
    monkeypatch.setattr(health_api, "check_db_connection", _db_up)
    monkeypatch.setattr(health_api, "get_vertex_readiness", _vertex_not_ready)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ready"] is False
    assert body["db"] == "up"
    assert body["vertex"]["ready"] is False


async def test_health_reports_mock_provider_without_credentials(monkeypatch):
    monkeypatch.setattr(health_api, "check_db_connection", _db_up)
    monkeypatch.setattr(vertex_client, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(vertex_client, "get_vertex_client", _fail_vertex_client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ready"] is True
    assert body["vertex"]["status"] == "mock_provider"
    assert body["vertex"]["credentials"] == "not_required"
