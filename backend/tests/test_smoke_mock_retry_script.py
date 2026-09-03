from __future__ import annotations

import importlib.util
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


def test_start_compose_refuses_default_project(tmp_path):
    module = load_smoke_module()
    with pytest.raises(module.SmokeError, match="isolated_coordinator_required"):
        module.start_compose(tmp_path / ".env.example")


def test_wrapper_delegates_to_owned_runner(monkeypatch):
    import verify_ownership
    module = load_smoke_module()
    calls = []
    monkeypatch.setattr(verify_ownership, "main", lambda argv: calls.append(argv) or 0)
    assert module.main(["--cycles", "1"]) == 0
    assert calls == [["--cycles", "1"]]


def test_retry_requests_use_one_authenticated_client_without_frontend():
    import json
    from types import SimpleNamespace
    module = load_smoke_module()
    calls = []
    def transport(request):
        calls.append(request)
        path = request.full_url.removeprefix("http://127.0.0.1:8000")
        status = 200
        if path == "/api/health":
            body = {"ok": True, "ready": True, "db": "up", "vertex": {"status": "mock_provider", "credentials": "not_required"}}
        elif request.method == "DELETE":
            return b"", {}, 204
        elif path == "/api/generations":
            status, body = 201, {"id": "source"}
        else:
            retry = path.endswith("/retry")
            status = 201 if request.method == "POST" else 200
            body = {"id": "retry" if retry else "source", "retry_of_job_id": "source", "state": "failed", "attempts": 1, "assets": [], "vertex_charged": False, "error": {"code": "mock_provider_failure"}}
        return json.dumps(body).encode(), {}, status
    client = module.HttpClient("http://127.0.0.1:8000", secret="a" * 43, transport=transport)
    module.run_smoke(SimpleNamespace(timeout_sec=1, poll_interval_sec=0, keep_jobs=False), client=client)
    assert len(calls) == 7
    assert all(r.get_header("Cookie") for r in calls)
    assert all(r.get_header("Origin") for r in calls if r.method != "GET")
    assert [r.method for r in calls[-2:]] == ["DELETE", "DELETE"]
