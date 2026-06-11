from __future__ import annotations

import importlib.util
import subprocess
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


def test_start_compose_includes_worker_services_and_mock_env(monkeypatch, tmp_path):
    module = load_smoke_module()
    env_file = tmp_path / ".env.example"
    env_file.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    calls = []

    def fake_run(command, env, text, encoding, errors, stdout, stderr, check):
        calls.append((command, env))
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.start_compose(env_file)

    command, env = calls[0]
    assert command[-5:] == ["db", "redis", "backend", "dispatcher", "worker"]
    assert env["AI_PROVIDER"] == "mock"
