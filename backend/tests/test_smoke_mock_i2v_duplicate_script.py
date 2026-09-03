from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "smoke_mock_i2v_duplicate_guard.py"
)


def load_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "smoke_mock_i2v_duplicate_guard",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_i2v_duplicate_script_exists():
    assert SCRIPT_PATH.exists()


def test_assert_duplicate_i2v_responses_accepts_one_created_one_conflict():
    module = load_smoke_module()

    module.assert_duplicate_i2v_responses(
        [
            {"status": 201, "body": {"id": "created-job"}},
            {"status": 409, "body": {"detail": module.DUPLICATE_DETAIL}},
        ],
    )


def test_assert_duplicate_i2v_responses_rejects_two_created():
    module = load_smoke_module()

    with pytest.raises(module.SmokeError, match="one created I2V and one conflict"):
        module.assert_duplicate_i2v_responses(
            [
                {"status": 201, "body": {"id": "first-job"}},
                {"status": 201, "body": {"id": "second-job"}},
            ],
        )


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


def test_both_race_requests_use_same_cookie_and_origin():
    import asyncio
    import json
    from threading import Lock
    module = load_smoke_module()
    calls = []
    lock = Lock()
    def transport(request):
        with lock:
            calls.append(request)
            status = 201 if len(calls) == 1 else 409
        body = {"id": "created"} if status == 201 else {"detail": module.DUPLICATE_DETAIL}
        return json.dumps(body).encode(), {}, status
    client = module.HttpClient("http://127.0.0.1:8000", secret="a" * 43, transport=transport)
    result = asyncio.run(module.create_duplicate_i2v_requests(client, source_asset_id="asset"))
    module.assert_duplicate_i2v_responses(result)
    assert len(calls) == 2
    assert all(r.get_header("Cookie") and r.get_header("Origin") for r in calls)
    assert calls[0].get_header("Cookie") == calls[1].get_header("Cookie")


def test_duplicate_invalid_json_does_not_leak_body():
    module = load_smoke_module()
    with pytest.raises(module.SmokeError, match="invalid_json") as caught:
        module.decode_json(b"private-canary")
    assert "private-canary" not in str(caught.value)
