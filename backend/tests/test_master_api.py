from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.api.auth_dependencies import require_user
from app.api.generations import get_session
from app.api import master
from app.main import app
from app.master_admin import MasterError, MasterReceipt


@asynccontextmanager
async def transaction():
    yield


@pytest.fixture
def client(monkeypatch):
    session = SimpleNamespace(begin=transaction)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=UUID(int=1), role="master")
    mock = AsyncMock(return_value=MasterReceipt(UUID(int=3), "plan_change", {}, {},
                                              datetime(2025, 1, 1, tzinfo=timezone.utc), False))
    monkeypatch.setattr(master, "administer", mock)
    yield TestClient(app), mock
    app.dependency_overrides.clear()


def body(**changes):
    return dict(request_id=str(UUID(int=3)), action="plan_change", reason_code="entitlement_change",
                target_plan="pro", **changes)


def test_identity_is_dependency_only_and_success_private(client):
    http, mock = client
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=body())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert mock.call_args.kwargs["actor_id"] == UUID(int=1)
    assert mock.call_args.kwargs["command"].target_id == UUID(int=2)
    assert "source" not in mock.call_args.kwargs


@pytest.mark.parametrize("extra", [{"actor_id": str(UUID(int=9))}, {"source": "operator_cli"},
                                  {"email": "forbidden"}])
def test_unknown_fields_never_reach_module(client, extra):
    http, mock = client
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=body(**extra))
    assert response.status_code == 422
    assert response.headers["cache-control"] == "private, no-store"
    mock.assert_not_called()


def test_no_http_role_promotion(client):
    http, mock = client
    payload = body()
    payload["action"] = "promote"
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=payload)
    assert response.status_code == 422
    mock.assert_not_called()


@pytest.mark.parametrize("code,status", [("master_required", 403), ("master_target_missing", 404),
    ("master_conflict", 409), ("master_input_invalid", 422), ("master_busy", 503), ("unexpected", 503)])
def test_safe_errors_are_uncacheable(client, code, status):
    http, mock = client
    mock.side_effect = MasterError(code)
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=body())
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["detail"] == ("master_unavailable" if code == "unexpected" else code)


def test_user_denied_before_module(client):
    http, mock = client
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=UUID(int=1), role="user")
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=body())
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"
    mock.assert_not_called()


@pytest.mark.parametrize("action", ["suspend", "reactivate"])
def test_status_commands_reach_existing_authenticated_module(client, action):
    http, mock = client
    payload = body()
    payload.update(action=action, target_plan=None)
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=payload)
    assert response.status_code == 200
    assert mock.call_args.kwargs["command"].action == action


def test_real_dependency_rejects_untrusted_origin_before_authentication(client, monkeypatch):
    from app.api import auth_dependencies
    http, mock = client
    app.dependency_overrides.pop(require_user)
    authenticate = AsyncMock(return_value=SimpleNamespace(id=UUID(int=1), role="master"))
    app.dependency_overrides[auth_dependencies.get_auth_service] = lambda: SimpleNamespace(authenticate=authenticate)
    monkeypatch.setattr(auth_dependencies, "get_settings", lambda: SimpleNamespace(
        auth_frontend_origin="http://localhost:5173", cors_origins=[]))
    response = http.post(f"/api/master/users/{UUID(int=2)}/commands", json=body(),
                         headers={"Origin": "https://untrusted.invalid"})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"
    authenticate.assert_not_called()
    mock.assert_not_called()
