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
    assert module.generate_project_name().startswith("schema-verify-")
    for invalid in ("", "multimodal", "g1-schema-12345678", "schema-verify-UPPERCASE", "schema-verify-a/bcdefgh"):
        with pytest.raises(module.VerificationError, match="must match"):
            module.validate_project_name(invalid)


def test_compose_commands_always_bind_exact_project_and_env_file():
    module = _load_module()
    project = "schema-verify-12345678"
    env_file = REPO_ROOT / ".env.example"

    command = module.compose_command(project, env_file, "up", "-d", "db")

    assert command[:5] == ["docker", "compose", "-p", project, "--env-file"]
    assert command[5] == str(env_file.resolve())
    assert command[6:8] == ["-f", str((REPO_ROOT / "docker-compose.yml").resolve())]
    assert command[-3:] == ["up", "-d", "db"]


def test_collision_check_refuses_exact_project_and_volume():
    module = _load_module()
    project = "schema-verify-12345678"

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
    project = "schema-verify-12345678"
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
    receipt = module.write_receipt("schema-verify-12345678", cleanup=True)
    content = receipt.read_text(encoding="utf-8")
    assert secret not in content
    assert "postgresql" not in content
    assert str(tmp_path) not in content
    payload = json.loads(content)
    assert payload["revision"] == "0002_user_session_persistence"
    assert payload["g1_downgrade"] == "pass"
    assert payload["identity_constraints"] == "pass"


def test_reset_commands_are_preview_first_and_exact_target_only(tmp_path):
    module = _load_module()
    project = "schema-verify-12345678"
    env_file = tmp_path / ".env.example"

    preview = module.reset_command(
        project,
        env_file,
        database="multimodal",
        execute=False,
    )
    execute = module.reset_command(
        project,
        env_file,
        database="multimodal",
        execute=True,
    )

    assert preview[-2:] == ["--expected-database", "multimodal"]
    assert "--execute" not in preview
    assert "--confirm" not in preview
    assert execute[-3:] == ["--execute", "--confirm", "RESET:multimodal"]
    assert "APP_ENV=test" in preview
    assert project in preview


def test_revision_refusal_checks_each_runtime_and_restores_head(tmp_path):
    module = _load_module()
    project = "schema-verify-12345678"
    env_file = tmp_path / ".env.example"
    values = {
        "POSTGRES_USER": "app",
        "POSTGRES_DB": "multimodal",
    }
    calls: list[list[str]] = []

    def runner(arguments):
        command = list(arguments)
        calls.append(command)
        if command[-3:] == ["-m", "app.schema_control", "check"]:
            return module.CommandResult(0, "PASS: schema current")
        if "run" in command and any(service in command for service in ("backend", "worker", "dispatcher")):
            return module.CommandResult(1, "", "schema_revision_outdated")
        return module.CommandResult(0, "")

    module.verify_revision_refusal(runner, project, env_file, values)

    runtime_calls = [
        command
        for command in calls
        if "run" in command and command[-3:] != ["-m", "app.schema_control", "check"]
    ]
    assert [command[-1] for command in runtime_calls] == [
        "backend",
        "worker",
        "dispatcher",
    ]
    sql_calls = [command for command in calls if "UPDATE alembic_version" in command[-1]]
    assert "0000_stale_revision" in sql_calls[0][-1]
    assert "0002_user_session_persistence" in sql_calls[-1][-1]


def test_verifier_targets_g2_head_and_schema_evidence_directory():
    module = _load_module()

    assert module.EXPECTED_REVISION == "0002_user_session_persistence"
    assert {"users", "user_sessions"}.issubset(module.EXPECTED_TABLES)
    assert module.DEFAULT_EVIDENCE_DIR.parts[-2:] == ("evidence", "schema")


def test_identity_constraint_matrix_requires_every_expected_postgres_rejection(tmp_path):
    module = _load_module()
    project = "schema-verify-12345678"
    env_file = tmp_path / ".env.example"
    values = {
        "POSTGRES_USER": "app",
        "POSTGRES_DB": "multimodal",
        "POSTGRES_PASSWORD": "secret-not-for-output",
    }
    rejected: set[str] = set()
    constraint_by_marker = {
        "000000000011', '10000000": "uq_user_sessions_token_hash",
        "000000000012', '10000000": "ck_user_sessions_token_hash_length",
        "000000000013', '10000000": "ck_user_sessions_lifecycle_order",
        "000000000014', '10000000": "ck_user_sessions_absolute_lifetime",
        "000000000015', '10000000": "ck_user_sessions_revocation",
        "000000000016": "ck_user_sessions_revoke_reason",
        "000000000011": "uq_users_google_sub",
        "000000000012": "ck_users_origin_profile",
        "000000000013": "ck_users_origin_profile",
        "000000000014": "ck_users_suspension_state",
        "000000000015', false": "ck_users_updated_after_signup",
    }

    def runner(arguments):
        sql = list(arguments)[-1]
        if "SELECT 'user_sessions:'" in sql:
            return module.CommandResult(0, "user_sessions:1\nusers:2\n")
        for marker, constraint in constraint_by_marker.items():
            if marker in sql:
                rejected.add(constraint)
                return module.CommandResult(1, "", constraint)
        return module.CommandResult(0, "")

    module.verify_identity_constraints(runner, project, env_file, values)

    assert rejected == {
        "uq_users_google_sub",
        "ck_users_origin_profile",
        "ck_users_suspension_state",
        "ck_users_updated_after_signup",
        "uq_user_sessions_token_hash",
        "ck_user_sessions_token_hash_length",
        "ck_user_sessions_lifecycle_order",
        "ck_user_sessions_absolute_lifetime",
        "ck_user_sessions_revocation",
        "ck_user_sessions_revoke_reason",
    }
