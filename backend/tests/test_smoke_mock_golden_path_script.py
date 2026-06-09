from __future__ import annotations

import importlib.util
import subprocess
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
    assert (
        module.join_url("http://127.0.0.1:8000/api", "assets/123")
        == "http://127.0.0.1:8000/api/assets/123"
    )


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

    monkeypatch.setattr(module, "urlopen", disconnect)
    client = module.HttpClient("http://127.0.0.1:8000")

    with pytest.raises(module.SmokeError, match="Health request disconnected"):
        client.request_bytes("GET", "/api/health", expected_status=200, step_name="Health")


def test_request_bytes_wraps_connection_reset(monkeypatch):
    module = load_smoke_module()

    def reset(*args, **kwargs):
        raise ConnectionResetError("connection reset by peer")

    monkeypatch.setattr(module, "urlopen", reset)
    client = module.HttpClient("http://127.0.0.1:8000")

    with pytest.raises(module.SmokeError, match=r"Health request.*reset"):
        client.request_bytes("GET", "/api/health", expected_status=200, step_name="Health")


def test_start_compose_includes_redis_worker_and_mock_env(monkeypatch, tmp_path):
    module = load_smoke_module()
    env_file = tmp_path / ".env.example"
    env_file.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    calls = []

    def fake_run(command, env, text, stdout, stderr, check, **_kwargs):
        calls.append((command, env))
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.start_compose(env_file)

    command, env = calls[0]
    assert command[-4:] == ["db", "redis", "backend", "worker"]
    assert env["AI_PROVIDER"] == "mock"
