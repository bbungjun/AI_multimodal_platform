"""HTTP contract for the owner-only G9A personal usage Interface."""
from types import SimpleNamespace
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import Response

from app.api import auth_dependencies
from app.auth.service import AuthError
from app.main import ContentApplication, app
from app.personal_usage import (
    ConcurrencyView,
    CreditBalanceView,
    CycleUsageView,
    MeterUsageView,
    PersonalUsageError,
    PersonalUsageView,
)


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


class FakeUsageSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    @asynccontextmanager
    async def begin(self):
        try:
            yield
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


def usage_view():
    meters = (
        ("gemini_input_token", "token"),
        ("gemini_output_token", "token"),
        ("imagen_fast_image", "image"),
        ("imagen_standard_image", "image"),
        ("imagen_ultra_image", "image"),
        ("veo_fast_ms", "millisecond"),
        ("veo_standard_ms", "millisecond"),
    )
    return PersonalUsageView(
        "pro", "free", "v1", CycleUsageView(0, NOW, NOW, 10, 2),
        CreditBalanceView(8, 1), ConcurrencyView(1, 3),
        tuple(MeterUsageView(meter, unit, 0, 0) for meter, unit in meters),
    )


async def request_usage(monkeypatch, *, error=None):
    from app.api import usage
    from app.api.generations import get_session

    session = FakeUsageSession()

    async def db():
        yield session

    async def read(received, *, user_id, now):
        assert received is session and user_id == UUID(int=1)
        assert now.tzinfo is not None
        if error is not None:
            raise error
        return usage_view()

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = db
    app.dependency_overrides[auth_dependencies.require_user] = lambda: SimpleNamespace(id=UUID(int=1))
    monkeypatch.setattr(usage, "read_personal_usage", read)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/usage/me")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    return response, session


def test_usage_route_is_one_no_selector_get_interface():
    from app.api import usage

    route = next(route for route in usage.router.routes if route.path == "/api/usage/me")
    assert route.methods == {"GET"}
    assert route.body_field is None
    assert route.dependant.query_params == []
    assert route.dependant.path_params == []
    assert route.dependant.header_params == []
    schema = app.openapi()["paths"]["/api/usage/me"]["get"]
    assert schema.get("parameters", []) == []


async def test_usage_unauthenticated_is_401_private_and_does_not_open_db():
    authenticate = AsyncMock(side_effect=AuthError("invalid_session"))
    app.dependency_overrides[auth_dependencies.get_auth_service] = lambda: SimpleNamespace(
        authenticate=authenticate
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/usage/me")
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_auth_service, None)
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}
    assert response.headers.get_list("cache-control") == ["private, no-store"]


@pytest.mark.parametrize("status", [200, 401, 422, 500])
async def test_usage_prefix_is_private_for_success_and_errors(status):
    instance = ContentApplication()

    @instance.get("/api/usage/probe")
    async def probe():
        if status == 500:
            raise RuntimeError("fixed_failure")
        return Response(status_code=status, headers={"Cache-Control": "public"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=instance, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/usage/probe")
    assert response.status_code == status
    assert response.headers.get_list("cache-control") == ["private, no-store"]
    assert "fixed_failure" not in response.text


async def test_usage_prefix_is_private_for_redirect_and_head_without_overmatch():
    instance = ContentApplication()

    @instance.get("/api/usage/probe")
    async def probe():
        return Response()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=instance), base_url="http://test"
    ) as client:
        redirect = await client.get("/api/usage/probe/")
        head = await client.head("/api/usage/probe")
        unrelated = await client.get("/api/usage-extra")
    assert redirect.status_code == 307
    assert redirect.headers["cache-control"] == "private, no-store"
    assert head.status_code == 405 and head.content == b""
    assert head.headers["cache-control"] == "private, no-store"
    assert "cache-control" not in unrelated.headers


def test_usage_response_schema_has_only_the_accepted_public_fields():
    from app.schemas import PersonalUsageResponse

    assert set(PersonalUsageResponse.model_fields) == {
        "plan", "pending_plan", "rate_card_version", "cycle", "credit",
        "concurrency", "usage",
    }
    forbidden = {"user_id", "email", "operation_key", "prompt", "session", "oauth"}
    nested = " ".join(str(field.annotation) for field in PersonalUsageResponse.model_fields.values())
    assert not any(name in nested.lower() for name in forbidden)


async def test_usage_success_uses_actor_only_commits_and_preserves_order(monkeypatch):
    response, session = await request_usage(monkeypatch)
    assert response.status_code == 200
    assert session.commits == 1 and session.rollbacks == 0
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert list(body) == [
        "plan", "pending_plan", "rate_card_version", "cycle", "credit",
        "concurrency", "usage",
    ]
    assert [row["meter"] for row in body["usage"]] == [
        "gemini_input_token", "gemini_output_token", "imagen_fast_image",
        "imagen_standard_image", "imagen_ultra_image", "veo_fast_ms",
        "veo_standard_ms",
    ]
    assert not ({"user_id", "email", "operation_key", "prompt"} & set(body))


@pytest.mark.parametrize(
    "internal,public",
    [("usage_busy", "usage_busy"), ("usage_unavailable", "usage_unavailable"),
     ("usage_input_invalid", "usage_unavailable")],
)
async def test_usage_failure_rolls_back_and_maps_only_safe_503(monkeypatch, internal, public):
    response, session = await request_usage(monkeypatch, error=PersonalUsageError(internal))
    assert response.status_code == 503
    assert response.json() == {"detail": public}
    assert response.headers["cache-control"] == "private, no-store"
    assert session.commits == 0 and session.rollbacks == 1


async def test_usage_unhandled_failure_rolls_back_without_detail_leak(monkeypatch):
    response, session = await request_usage(monkeypatch, error=RuntimeError("fixed_failure"))
    assert response.status_code == 500
    assert "fixed_failure" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert session.commits == 0 and session.rollbacks == 1
