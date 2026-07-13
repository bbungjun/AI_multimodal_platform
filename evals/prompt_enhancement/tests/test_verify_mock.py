from __future__ import annotations

import subprocess
import sys

import pytest

import verify_mock


def test_require_mock_provider_accepts_only_explicit_mock():
    verify_mock.require_mock_provider({"AI_PROVIDER": "mock"})

    with pytest.raises(verify_mock.VerificationError, match="AI_PROVIDER=mock"):
        verify_mock.require_mock_provider({})


def test_require_mock_provider_does_not_echo_environment_value():
    secret_value = "vertex-secret-value-must-not-be-printed"

    with pytest.raises(verify_mock.VerificationError) as exc_info:
        verify_mock.require_mock_provider({"AI_PROVIDER": secret_value})

    assert secret_value not in str(exc_info.value)


def test_run_tests_uses_current_python_and_package_directory(monkeypatch):
    calls = []

    def fake_run(command, *, cwd, env, check):
        calls.append((command, cwd, env, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verify_mock.subprocess, "run", fake_run)

    assert verify_mock.run_tests({"AI_PROVIDER": "mock"}) == 0
    command, cwd, env, check = calls[0]
    assert command == [sys.executable, "-m", "pytest"]
    assert cwd == verify_mock.PACKAGE_ROOT
    assert env["AI_PROVIDER"] == "mock"
    assert check is False


def test_main_rejects_env_file_argument_without_reading_it(capsys):
    assert verify_mock.main(["--env-file", ".env"]) == 2

    captured = capsys.readouterr()
    assert "accepts no arguments" in captured.err
    assert "AI_PROVIDER" not in captured.err
