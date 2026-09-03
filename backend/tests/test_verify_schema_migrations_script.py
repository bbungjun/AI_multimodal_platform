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


def test_ownership_proof_program_compiles_and_is_fixed_to_owned_runtime():
    module = _load_module()
    compile(module.OWNERSHIP_PROOF_SCRIPT, "ownership-proof", "exec")
    calls = []
    def runner(command):
        calls.append(command)
        return module.CommandResult(0, "ownership_schema_proof_pass")
    module.verify_content_ownership(runner, "schema-verify-12345678", REPO_ROOT / ".env.example")
    assert len(calls) == 3
    assert calls[0][-2:] == ["downgrade", "0003_content_ownership"]
    assert calls[1][-4:] == ["migrate", "python", "-c", module.OWNERSHIP_PROOF_SCRIPT]
    assert "schema-verify-12345678" in calls[1]
    assert calls[2][-2:] == ["upgrade", "head"]
    assert '"head"' not in module.OWNERSHIP_PROOF_SCRIPT
    assert "lock timeout" in module.OWNERSHIP_PROOF_SCRIPT
    assert "await snapshot() == before" in module.OWNERSHIP_PROOF_SCRIPT


def test_ownership_proof_failure_never_exposes_raw_output():
    module = _load_module()
    def runner(command):
        if "-c" not in command:
            return module.CommandResult(0)
        return module.CommandResult(1, "private fixture", "private database error")
    with pytest.raises(module.VerificationError) as error:
        module.verify_content_ownership(runner, "schema-verify-12345678", REPO_ROOT / ".env.example")
    assert str(error.value) == "ownership schema constraints and atomic refusal failed with exit code 1."


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
    monkeypatch.setattr(module, "DEFAULT_EVIDENCE_DIR", tmp_path / "evidence")
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
        if command[:2] == ["git", "rev-parse"]:
            return module.CommandResult(0, "f" * 40)
        if command[:3] == ["docker", "compose", "ls"]:
            return module.CommandResult(0, "[]")
        if command[:3] == ["docker", "volume", "ls"]:
            return module.CommandResult(0, "")
        if "up" in command:
            return module.CommandResult(17, "", "sensitive output must not escape")
        return module.CommandResult(0, "")

    with pytest.raises(module.VerificationError, match="startup failed with exit code 17"):
        module.verify(env_file=env_file, project_name=project, runner=runner)

    cleanup = next(command for command in calls if "down" in command)
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
    receipt = module.write_receipt("schema-verify-12345678", cleanup=True, completed=True, commit="f"*40, credit_checks=90)
    content = receipt.read_text(encoding="utf-8")
    assert secret not in content
    assert "postgresql" not in content
    assert str(tmp_path) not in content
    payload = json.loads(content)
    assert payload["revision"] == "0005_credit_lifecycle_operations"
    assert payload["g1_downgrade"] == "pass"
    assert payload["identity_constraints"] == "pass"
    assert payload["reset"] == "not_requested"


@pytest.mark.parametrize("change", [dict(cleanup=False), dict(credit_checks=True), dict(credit_checks=0),
    dict(work_seconds=301), dict(cleanup_seconds=91), dict(commit="unsafe"), dict(failure_code="raw error"),
    dict(work_seconds=float("nan")), dict(cleanup_failure_code="cleanup_failed")])
def test_receipt_refuses_contradictory_success_or_unsafe_fields(tmp_path, monkeypatch, change):
    module = _load_module()
    monkeypatch.setattr(module, "DEFAULT_EVIDENCE_DIR", tmp_path)
    args = dict(cleanup=True, completed=True, commit="f"*40, credit_checks=90)
    args.update(change)
    with pytest.raises(module.VerificationError, match="invalid_schema_receipt"):
        module.write_receipt("schema-verify-12345678", **args)


def test_deadline_clamps_subprocess_and_reserves_fresh_cleanup_budget(monkeypatch):
    module = _load_module()
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    timeouts = []
    def runner(args):
        timeouts.append(module._COMMAND_TIMEOUT.get())
        return module.CommandResult(0)
    work = module.DeadlineRunner(runner, 300)
    work([])
    clock[0] = 299
    work([])
    clock[0] = 300
    with pytest.raises(module.VerificationError, match="deadline"):
        work([])
    cleanup = module.DeadlineRunner(runner, 90)
    cleanup([])
    assert timeouts == [120, 1, 90]
    assert module._COMMAND_TIMEOUT.get() == 120


def test_native_timeout_cannot_be_counted_as_expected_refusal():
    module = _load_module()
    work = module.DeadlineRunner(lambda _: module.CommandResult(124, "raw", "secret"), 300)
    with pytest.raises(module.VerificationError, match="^schema_command_timeout$"):
        work([])


def test_code_revision_refuses_dirty_code_but_allows_local_evidence():
    module = _load_module()
    def runner(status):
        return lambda args: module.CommandResult(0, "f"*40 if args[1] == "rev-parse" else status)
    assert module.code_revision(runner("?? .omo/\n M docs/current-work.md\n")) == "f"*40
    for status in (" M backend/app/credit_policy.py\n", "?? scripts/new.py\n", "R  docs/x.md -> backend/app/x.py\n"):
        with pytest.raises(module.VerificationError, match="dirty_code"):
            module.code_revision(runner(status))


def test_credit_proof_uses_fixed_source_on_stdin_and_validates_receipt():
    module = _load_module()
    def runner(args):
        assert args[-3:] == ["migrate", "python", "-"]
        assert "AI_PROVIDER=mock" in args and "APP_ENV=test" in args
        assert "CREDIT_PROOF_PROJECT=schema-verify-12345678" in args
        assert module._COMMAND_INPUT.get() == module.CREDIT_PROOF_PATH.read_text()
        return module.CommandResult(0, '{"mode":"credit","checks":90}')
    assert module.verify_credit_foundation(runner, "schema-verify-12345678", REPO_ROOT / ".env.example", {"POSTGRES_DB":"fixture"}, "credit") == 90
    assert module._COMMAND_INPUT.get() is None
    for output in ('{"mode":"credit","checks":true}', '{"mode":"credit","checks":79}',
                   '{"mode":"credit","checks":90,"raw":"secret"}', 'raw secret'):
        with pytest.raises(module.VerificationError, match="invalid_credit_proof_receipt"):
            module.verify_credit_foundation(lambda _: module.CommandResult(0, output), "schema-verify-12345678", REPO_ROOT / ".env.example", {"POSTGRES_DB":"fixture"}, "credit")


@pytest.mark.parametrize("stale", ["0003_content_ownership", "0004_credit_foundation"])
def test_stale_previous_head_is_refused_by_all_three_processes(tmp_path, stale):
    module = _load_module()
    calls = []
    def runner(args):
        calls.append(args)
        if args[-1] in ("backend", "worker", "dispatcher"):
            return module.CommandResult(1, "schema_revision_outdated")
        return module.CommandResult(0)
    module.verify_revision_refusal(runner, "schema-verify-12345678", tmp_path / ".env.example",
                                   {"POSTGRES_DB":"fixture", "POSTGRES_USER":"fixture"}, stale)
    assert stale in calls[0][-1]
    assert [args[-1] for args in calls if args[-1] in ("backend", "worker", "dispatcher")] == ["backend", "worker", "dispatcher"]
    assert sum("0005_credit_lifecycle_operations" in args[-1] for args in calls) == 1


@pytest.mark.parametrize("mutate_preview", [False, True])
def test_reset_includes_credit_rows_and_refuses_preview_mutation(monkeypatch, mutate_preview):
    module = _load_module()
    counts = {table: (3 if table in module.CREDIT_TABLES or table in ("users", "credit_operations") else 0)
              for table in module.EXPECTED_TABLES - {"alembic_version"}}
    snapshot_tag = [0]
    commands = []
    monkeypatch.setattr(module, "_reset_row_counts", lambda *a: counts.copy())
    monkeypatch.setattr(module, "_reset_data_snapshot", lambda *a: snapshot_tag[0])
    monkeypatch.setattr(module, "assert_inventory", lambda *a: None)
    def seed(*args):
        for table in counts:
            if table in {"users", "user_sessions", "jobs", "assets", "prompt_enhancements", "outbox_events"}:
                counts[table] += 1
    monkeypatch.setattr(module, "_seed_reset_rows", seed)
    def runner(args):
        commands.append(args)
        if "--execute" in args:
            counts.update({table:0 for table in counts})
        elif "reset" in args and mutate_preview:
            snapshot_tag[0] += 1
        return module.CommandResult(0, "PREVIEW:")
    if mutate_preview:
        with pytest.raises(module.VerificationError, match="preview changed data"):
            module.verify_reset(runner, "schema-verify-12345678", REPO_ROOT / ".env.example", {"POSTGRES_DB":"fixture"})
        assert len(commands) == 1 and all(counts[table] == 3 for table in module.CREDIT_TABLES)
        assert counts["credit_operations"] == 3
    else:
        module.verify_reset(runner, "schema-verify-12345678", REPO_ROOT / ".env.example", {"POSTGRES_DB":"fixture"})
        assert len(commands) == 2 and "--execute" not in commands[0] and "--execute" in commands[1]
        assert all(value == 0 for value in counts.values())


def test_first_failure_and_cleanup_failure_are_both_retained(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "DEFAULT_EVIDENCE_DIR", tmp_path / "evidence")
    def runner(args):
        if args[:2] == ["git", "rev-parse"]:
            return module.CommandResult(0, "f"*40)
        if "up" in args:
            return module.CommandResult(19, "private", "secret")
        if "down" in args:
            return module.CommandResult(23)
        return module.CommandResult(0)
    with pytest.raises(module.VerificationError, match="startup failed with exit code 19.*cleanup_failed"):
        module.verify(env_file=REPO_ROOT / ".env.example", project_name="schema-verify-12345678", runner=runner)
    receipt = json.loads(next((tmp_path / "evidence").glob("*.json")).read_text())
    assert receipt["completed"] is False and receipt["credit_constraints"] == "unverified"
    assert receipt["failure_code"] == "verification_failed" and receipt["cleanup_failure_code"] == "cleanup_failed"
    assert "private" not in json.dumps(receipt) and "secret" not in json.dumps(receipt)


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
    assert "0005_credit_lifecycle_operations" in sql_calls[-1][-1]


def test_verifier_targets_g2_head_and_schema_evidence_directory():
    module = _load_module()

    assert module.EXPECTED_REVISION == "0005_credit_lifecycle_operations"
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
