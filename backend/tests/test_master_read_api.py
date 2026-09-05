from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from app.api import master
from app.api.auth_dependencies import require_user
from app.api.generations import get_session
from app.main import app
from app.master_read import MasterReadError


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=UUID(int=1), role="master")
    app.dependency_overrides[get_session] = lambda: object()
    mock = AsyncMock(return_value={"items": [], "next_cursor": None})
    monkeypatch.setattr(master, "read_master", mock)
    yield TestClient(app), mock
    app.dependency_overrides.clear()


@pytest.mark.parametrize("view", ["overview", "users", "audit"])
def test_private_actor_bound_read(client, view):
    http, mock = client
    response = http.get("/api/master/"+view)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    assert mock.call_args.kwargs["actor_id"] == UUID(int=1)
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(role="user")
    mock.reset_mock()
    assert http.get("/api/master/"+view).status_code == 403
    mock.assert_not_called()


@pytest.mark.parametrize("query", ["scope=all", "user_id=x", "limit=1&limit=2", "after=oops",
    "limit=1.2", "limit=-1", "days=30", "email=x"])
def test_bad_query_never_reaches_module(client, query):
    http, mock = client
    response = http.get("/api/master/users?"+query)
    assert response.status_code == 422 and response.headers["cache-control"] == "private, no-store"
    mock.assert_not_called()


@pytest.mark.parametrize("code,status", [("master_input_invalid", 422), ("master_required", 403),
    ("master_busy", 503), ("arbitrary", 503)])
def test_safe_errors(client, code, status):
    http, mock = client
    mock.side_effect = MasterReadError(code)
    response = http.get("/api/master/overview")
    assert response.status_code == status and response.headers["cache-control"] == "private, no-store"
    assert response.json()["detail"] != "arbitrary"
