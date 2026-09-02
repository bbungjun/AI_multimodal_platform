from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_schema_migrations.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_schema_migrations", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_project_name_is_generated_and_strictly_validated():
    module = _load_module()

    assert module.PROJECT_PATTERN.fullmatch(module.generate_project_name())
    for invalid in ("", "multimodal", "g1-schema-", "g1-schema-UPPERCASE", "g1-schema-a/bcdefgh"):
        with pytest.raises(module.VerificationError, match="must match"):
            module.validate_project_name(invalid)


def test_compose_commands_always_bind_exact_project_and_env_file():
    module = _load_module()
    project = "g1-schema-12345678"
    env_file = REPO_ROOT / ".env.example"

    command = module.compose_command(project, env_file, "up", "-d", "db")

    assert command[:5] == ["docker", "compose", "-p", project, "--env-file"]
    assert command[5] == str(env_file.resolve())
    assert command[6:8] == ["-f", str((REPO_ROOT / "docker-compose.yml").resolve())]
    assert command[-3:] == ["up", "-d", "db"]


def test_collision_check_refuses_exact_project_and_volume():
    module = _load_module()
    project = "g1-schema-12345678"

    def project_collision(arguments):
        if arguments[:3] == ["docker", "compose", "ls"]:
            return module.CommandResult(0, json.dumps([{"Name": project}]))
        return module.CommandResult(0, "")

    with pytest.raises(module.VerificationError, match="project already exists"):
        module.refuse_collisions(project, project_collision)

    def volume_collision(arguments):
        if arguments[:3] == ["docker", "compose", "ls"]:
            return module.CommandResult(0, "[]")
        return module.CommandResult(0, f"{project}_pgdata\n")

    with pytest.raises(module.VerificationError, match="volume"):
        module.refuse_collisions(project, volume_collision)


def test_failure_still_cleans_only_the_exact_validated_project(tmp_path, monkeypatch):
    module = _load_module()
    project = "g1-schema-12345678"
    env_file = tmp_path / ".env.example"
    env_file.write_text(
        "AI_PROVIDER=mock\nPOSTGRES_USER=app\nPOSTGRES_DB=multimodal\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(arguments):
        command = list(arguments)
        calls.append(command)
        if command[:3] == ["docker", "compose", "ls"]:
            return module.CommandResult(0, "[]")
        if command[:3] == ["docker", "volume", "ls"]:
            return module.CommandResult(0, "")
        if "up" in command:
            return module.CommandResult(17, "", "sensitive output must not escape")
        return module.CommandResult(0, "")

    with pytest.raises(module.VerificationError, match="startup failed with exit code 17"):
        module.verify(env_file=env_file, project_name=project, runner=runner)

    cleanup = calls[-1]
    assert cleanup == module.compose_command(
        project, env_file, "down", "-v", "--remove-orphans"
    )
    assert all(project in command for command in calls if command[:2] == ["docker", "compose"] and "ls" not in command)


def test_env_validation_and_receipt_never_copy_sensitive_values(tmp_path, monkeypatch):
    module = _load_module()
    unsafe = tmp_path / ".env"
    unsafe.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    with pytest.raises(module.VerificationError, match=".env.example"):
        module.validate_env_file(unsafe)

    safe = tmp_path / ".env.example"
    secret = "not-for-receipt"
    safe.write_text(
        f"AI_PROVIDER=mock\nPOSTGRES_USER=app\nPOSTGRES_DB=multimodal\nPOSTGRES_PASSWORD={secret}\n",
        encoding="utf-8",
    )
    assert module.validate_env_file(safe)["POSTGRES_PASSWORD"] == secret

    evidence_dir = tmp_path / "evidence"
    monkeypatch.setattr(module, "DEFAULT_EVIDENCE_DIR", evidence_dir)
    receipt = module.write_receipt("g1-schema-12345678", cleanup=True)
    content = receipt.read_text(encoding="utf-8")
    assert secret not in content
    assert "postgresql" not in content
    assert str(tmp_path) not in content
