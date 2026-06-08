from __future__ import annotations

import importlib.util
import subprocess
from http.client import RemoteDisconnected
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "smoke_mock_retry_flow.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_mock_retry_flow", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_retry_script_exists():
    assert SCRIPT_PATH.exists()


def test_assert_failed_source_job_contract():
    module = load_smoke_module()

    source = {
        "id": "source-job",
        "state": "failed",
        "assets": [],
        "vertex_charged": False,
        "error": {"code": "mock_provider_failure", "message": "forced"},
    }

    module.assert_failed_source_job(source)


def test_assert_failed_source_job_rejects_assets():
    module = load_smoke_module()

    source = {
        "id": "source-job",
        "state": "failed",
        "assets": [{"id": "unexpected"}],
        "vertex_charged": False,
        "error": {"code": "mock_provider_failure"},
    }

    with pytest.raises(module.SmokeError, match="expected no assets"):
        module.assert_failed_source_job(source)


def test_assert_retry_job_contract_allows_pending_retry():
    module = load_smoke_module()

    retry = {
        "id": "retry-job",
        "state": "pending",
        "retry_of_job_id": "source-job",
        "assets": [],
        "vertex_charged": False,
        "attempts": 0,
        "error": None,
    }

    module.assert_retry_job(retry, source_id="source-job")


def test_assert_retry_job_contract_allows_failed_retry_after_runner():
    module = load_smoke_module()

    retry = {
        "id": "retry-job",
        "state": "failed",
        "retry_of_job_id": "source-job",
        "assets": [],
        "vertex_charged": False,
        "attempts": 1,
        "error": {"code": "mock_provider_failure"},
    }

    module.assert_retry_job(retry, source_id="source-job")


def test_assert_retry_job_rejects_source_id_reuse():
    module = load_smoke_module()

    retry = {
        "id": "source-job",
        "state": "pending",
        "retry_of_job_id": "source-job",
        "assets": [],
        "attempts": 0,
        "error": None,
    }

    with pytest.raises(module.SmokeError, match="new job id"):
        module.assert_retry_job(retry, source_id="source-job")


def test_assert_retry_job_rejects_vertex_charged_true():
    module = load_smoke_module()

    retry = {
        "id": "retry-job",
        "state": "failed",
        "retry_of_job_id": "source-job",
        "assets": [],
        "vertex_charged": True,
        "attempts": 1,
        "error": {"code": "mock_provider_failure"},
    }

    with pytest.raises(module.SmokeError, match="vertex_charged false"):
        module.assert_retry_job(retry, source_id="source-job")


def test_cleanup_jobs_reports_retry_contract_error_and_deletes_both_jobs(monkeypatch):
    module = load_smoke_module()
    deleted_paths = []

    class FakeClient:
        def request_bytes(
            self,
            method,
            path,
            *,
            expected_status,
            step_name,
            payload=None,
            headers=None,
        ):
            deleted_paths.append((method, path, expected_status, step_name))
            return b"", {}, expected_status

    def fake_poll_generation_terminal(client, *, job_id, deadline, interval_sec):
        assert job_id == "retry-job"
        return {
            "id": "retry-job",
            "state": "failed",
            "retry_of_job_id": "source-job",
            "assets": [],
            "vertex_charged": True,
            "attempts": 1,
            "error": {"code": "mock_provider_failure"},
        }

    monkeypatch.setattr(module, "poll_generation_terminal", fake_poll_generation_terminal)

    error = module.cleanup_jobs(
        FakeClient(),
        retry_id="retry-job",
        source_id="source-job",
        deadline=0,
        interval_sec=0,
    )

    assert isinstance(error, module.SmokeError)
    assert "vertex_charged false" in str(error)
    assert deleted_paths == [
        ("DELETE", "/api/generations/retry-job", 204, "Cleanup retry"),
        ("DELETE", "/api/generations/source-job", 204, "Cleanup source"),
    ]


def test_start_compose_includes_frontend_and_mock_env(monkeypatch, tmp_path):
    module = load_smoke_module()
    env_file = tmp_path / ".env.example"
    env_file.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    calls = []

    def fake_run(command, env, text, stdout, stderr, check):
        calls.append((command, env))
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.start_compose(env_file)

    command, env = calls[0]
    assert command[-3:] == ["db", "backend", "frontend"]
    assert env["AI_PROVIDER"] == "mock"


def test_wait_for_frontend_wraps_remote_disconnect(monkeypatch):
    module = load_smoke_module()

    def disconnect(*args, **kwargs):
        raise RemoteDisconnected("remote closed connection")

    monkeypatch.setattr(module, "urlopen", disconnect)

    with pytest.raises(module.SmokeError, match="Timed out waiting for frontend"):
        module.wait_for_frontend("http://127.0.0.1:5173", deadline=0, interval_sec=0)
