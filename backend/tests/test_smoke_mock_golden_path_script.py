from __future__ import annotations

import importlib.util
from http.client import RemoteDisconnected
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "smoke_mock_golden_path.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_mock_golden_path", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_env_file_requires_mock_provider(tmp_path):
    module = load_smoke_module()
    env_file = tmp_path / ".env.example"
    env_file.write_text(
        "\n".join(
            [
                "# local mock values",
                "AI_PROVIDER=mock",
                "POSTGRES_USER=app",
                "QUOTED='value-without-secret-read'",
            ]
        ),
        encoding="utf-8",
    )

    values = module.parse_env_file(env_file)

    assert values["AI_PROVIDER"] == "mock"
    assert values["POSTGRES_USER"] == "app"
    assert values["QUOTED"] == "value-without-secret-read"


def test_parse_env_file_rejects_sensitive_dotenv_name(tmp_path):
    module = load_smoke_module()
    env_file = tmp_path / ".env"
    env_file.write_text("AI_PROVIDER=mock\n", encoding="utf-8")

    with pytest.raises(module.SmokeError, match="Refusing to read sensitive env file"):
        module.parse_env_file(env_file)


def test_parse_env_file_rejects_non_mock_provider(tmp_path):
    module = load_smoke_module()
    env_file = tmp_path / ".env.example"
    env_file.write_text("AI_PROVIDER=vertex\n", encoding="utf-8")

    with pytest.raises(module.SmokeError, match="AI_PROVIDER=mock"):
        module.parse_env_file(env_file)


def test_join_url_handles_root_relative_paths():
    module = load_smoke_module()

    assert (
        module.join_url("http://127.0.0.1:8000/", "/files/job/image.png")
        == "http://127.0.0.1:8000/files/job/image.png"
    )
    with pytest.raises(module.SmokeError):
        module.join_url("http://127.0.0.1:8000/api", "assets/123")


def test_assert_status_reports_clear_error():
    module = load_smoke_module()

    with pytest.raises(module.SmokeError, match="Health expected HTTP 200, got 503"):
        module.assert_status("Health", 503, 200, "database down")


def test_header_lookup_is_case_insensitive():
    module = load_smoke_module()
    headers = {"content-type": "image/png", "CONTENT-LENGTH": "42"}

    assert module.header_value(headers, "Content-Type") == "image/png"
    assert module.header_value(headers, "Content-Length") == "42"
    assert module.header_value(headers, "Missing", "fallback") == "fallback"


def test_request_bytes_wraps_remote_disconnected(monkeypatch):
    module = load_smoke_module()

    def disconnect(*args, **kwargs):
        raise RemoteDisconnected("remote closed connection")

    client = module.HttpClient("http://127.0.0.1:8000", secret=None, transport=disconnect)

    with pytest.raises(module.SmokeError, match="http_transport_failed"):
        client.request_bytes("GET", "/api/health", expected_status=200, step_name="Health")


def test_request_bytes_wraps_connection_reset(monkeypatch):
    module = load_smoke_module()

    def reset(*args, **kwargs):
        raise ConnectionResetError("connection reset by peer")

    client = module.HttpClient("http://127.0.0.1:8000", secret=None, transport=reset)

    with pytest.raises(module.SmokeError, match="http_transport_failed"):
        client.request_bytes("GET", "/api/health", expected_status=200, step_name="Health")


def test_start_compose_refuses_default_runtime(tmp_path):
    module = load_smoke_module()
    with pytest.raises(module.SmokeError, match="isolated_coordinator_required"):
        module.start_compose(tmp_path / ".env.example")


def test_wrapper_delegates_to_owned_runner(monkeypatch):
    import verify_ownership
    module = load_smoke_module()
    seen = []
    monkeypatch.setattr(verify_ownership, "main", lambda argv: seen.append(argv) or 0)
    assert module.main(["--cycles", "1"]) == 0
    assert seen == [["--cycles", "1"]]


def test_golden_all_requests_use_injected_cookie_including_range_and_delete():
    import json
    from types import SimpleNamespace
    module = load_smoke_module()
    calls = []
    asset = {"id": "asset", "url": "/files/job/image.png", "mime": "image/png"}
    def transport(request):
        calls.append(request)
        path = request.full_url.removeprefix("http://127.0.0.1:8000")
        status, headers = 200, {}
        if path == "/api/health":
            body = {"ok": True, "ready": True, "db": "up", "vertex": {"status": "mock_provider", "credentials": "not_required"}}
        elif path == "/api/prompts/enhance":
            status, body = 201, {"id": "enhancement", "enhanced": "test", "components": {"provider": "mock"}}
        elif path == "/api/generations":
            status, body = 201, {"id": "job"}
        elif request.method == "DELETE":
            return b"", {}, 204
        elif path == "/api/generations/job":
            body = {"state": "completed", "assets": [asset], "vertex_charged": True, "state_history": [{"state": x} for x in ["queued", "generating", "downloading", "completed"]]}
        elif path == "/api/assets/asset":
            body = asset
        else:
            return module.PNG_SIGNATURE, {"Content-Type": "image/png", "Content-Length": "8"}, 206 if request.get_header("Range") else 200
        return json.dumps(body).encode(), headers, status
    client = module.HttpClient("http://127.0.0.1:8000", secret="a" * 43, transport=transport)
    module.run_smoke(SimpleNamespace(timeout_sec=1, poll_interval_sec=0, keep_job=False), client=client)
    assert len(calls) == 8
    assert all(r.get_header("Cookie") for r in calls)
    assert all(r.get_header("Origin") == "http://localhost:5173" for r in calls if r.method != "GET")
    assert calls[-2].get_header("Range") == "bytes=0-7"
    assert calls[-1].method == "DELETE"


def test_error_body_is_never_reported():
    module = load_smoke_module()
    with pytest.raises(module.SmokeError) as caught:
        module.assert_status("Health", 503, 200, "private-canary")
    assert "private-canary" not in str(caught.value)
