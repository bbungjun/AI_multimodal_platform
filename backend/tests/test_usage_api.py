"""HTTP contract for the owner-only G9A personal usage Interface."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import Response

from app.api import auth_dependencies
from app.auth.service import AuthError
from app.main import ContentApplication, app


def test_usage_route_is_one_no_selector_get_interface():
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/usage/me")
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
    assert response.json() == {"detail": "invalid_session"}
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
