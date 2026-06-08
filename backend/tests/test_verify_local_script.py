from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_local.py"


def load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_local", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_verify_script_exists():
    assert SCRIPT_PATH.exists()


def test_build_default_steps_uses_mock_backend_and_env_example():
    module = load_verify_module()

    steps = module.build_steps(repo_root=Path("C:/repo"), env_file=Path(".env.example"))

    assert [step.name for step in steps] == [
        "Compose config",
        "Backend mock tests",
        "Frontend lint",
        "Frontend build",
    ]
    assert steps[0].command == [
        "docker",
        "compose",
        "--env-file",
        ".env.example",
        "config",
        "--quiet",
    ]
    assert steps[1].cwd == Path("C:/repo/backend")
    assert steps[1].command == ["python", "-m", "pytest"]
    assert steps[1].env_overrides == {"AI_PROVIDER": "mock"}
    assert steps[2].cwd == Path("C:/repo/frontend")
    assert steps[2].command == ["npm", "run", "lint"]
    assert steps[3].cwd == Path("C:/repo/frontend")
    assert steps[3].command == ["npm", "run", "build"]


def test_validate_env_file_rejects_sensitive_dotenv_name():
    module = load_verify_module()

    with pytest.raises(module.VerifyError, match="Refusing to read sensitive env file"):
        module.validate_env_file(Path(".env"))


def test_validate_no_backend_dotenv_rejects_backend_dotenv(tmp_path):
    module = load_verify_module()
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / ".env").write_text("AI_PROVIDER=vertex\n", encoding="utf-8")

    with pytest.raises(
        module.VerifyError,
        match=r"Refusing to run backend tests while backend/\.env exists",
    ):
        module.validate_no_backend_dotenv(tmp_path)


def test_run_step_passes_env_overrides(monkeypatch):
    module = load_verify_module()
    calls = []
    step = module.Step(
        name="Backend mock tests",
        command=["python", "-m", "pytest"],
        cwd=Path("C:/repo/backend"),
        env_overrides={"AI_PROVIDER": "mock"},
    )

    def fake_run(command, cwd, env, text, stdout, stderr, check):
        calls.append((command, cwd, env))
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.run_step(step)

    command, cwd, env = calls[0]
    assert command == ["python", "-m", "pytest"]
    assert cwd == Path("C:/repo/backend")
    assert env["AI_PROVIDER"] == "mock"


def test_run_step_reports_failed_step(monkeypatch):
    module = load_verify_module()
    step = module.Step(name="Frontend build", command=["npm", "run", "build"], cwd=Path("."))

    def fake_run(command, cwd, env, text, stdout, stderr, check):
        return subprocess.CompletedProcess(command, 2, stdout="build failed")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(module.VerifyError, match="Frontend build failed"):
        module.run_step(step)


def test_run_step_resolves_npm_cmd_on_windows(monkeypatch):
    module = load_verify_module()
    calls = []
    step = module.Step(
        name="Frontend lint",
        command=["npm", "run", "lint"],
        cwd=Path("C:/repo/frontend"),
    )

    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: "C:/tools/npm.cmd" if name == "npm.cmd" else None,
    )

    def fake_run(command, cwd, env, text, stdout, stderr, check):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.run_step(step)

    assert calls[0] == ["C:/tools/npm.cmd", "run", "lint"]
