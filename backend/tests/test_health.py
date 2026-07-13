from __future__ import annotations

import httpx

from app.config import Settings
from app.api import health as health_api
from app.main import app
from app.services.vertex import client as vertex_client
from app.services.vertex.client import VertexReadiness


async def _db_up() -> bool:
    return True


async def _db_down() -> bool:
    return False


def _vertex_ready() -> VertexReadiness:
    return VertexReadiness(
        ready=True,
        status="ready",
        credentials="available",
        project="configured",
        location="us-central1",
    )


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


async def test_live_probe_is_process_only(monkeypatch):
    async def fail_db() -> bool:
        raise AssertionError("liveness must not check database connectivity")

    def fail_vertex_readiness() -> VertexReadiness:
        raise AssertionError("liveness must not check Vertex readiness")

    monkeypatch.setattr(health_api, "check_db_connection", fail_db)
    monkeypatch.setattr(health_api, "get_vertex_readiness", fail_vertex_readiness)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "AI Multimodal Content Platform",
    }


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
    assert body["provider_retry_max_attempts"] == 3
    assert body["vertex"]["status"] == "mock_provider"
    assert body["vertex"]["credentials"] == "not_required"


async def test_health_reports_not_ready_when_db_is_down_even_if_vertex_ready(
    monkeypatch,
):
    monkeypatch.setattr(health_api, "check_db_connection", _db_down)
    monkeypatch.setattr(health_api, "get_vertex_readiness", _vertex_ready)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["ready"] is False
    assert body["db"] == "down"
    assert body["vertex"]["ready"] is True
    assert body["vertex"]["status"] == "ready"


async def test_health_reports_not_ready_when_db_and_vertex_are_down(monkeypatch):
    monkeypatch.setattr(health_api, "check_db_connection", _db_down)
    monkeypatch.setattr(health_api, "get_vertex_readiness", _vertex_not_ready)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["ready"] is False
    assert body["db"] == "down"
    assert body["vertex"]["ready"] is False
    assert body["vertex"]["status"] == "vertex_credentials_missing"
