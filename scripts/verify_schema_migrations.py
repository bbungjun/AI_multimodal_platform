#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import subprocess
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.example"
DEFAULT_EVIDENCE_DIR = REPO_ROOT / ".omo" / "evidence" / "schema"
PROJECT_PATTERN = re.compile(r"^schema-verify-[a-z0-9]{8,32}$")
G1_REVISION = "0001_generation_baseline"
EXPECTED_REVISION = "0006_credit_accounting_persistence"
LIFECYCLE_REVISION = "0005_credit_lifecycle_operations"
CREDIT_REVISION = "0004_credit_foundation"
OWNERSHIP_REVISION = "0003_content_ownership"
IDENTITY_REVISION = "0002_user_session_persistence"
G1_TABLES = {"alembic_version", "assets", "jobs", "outbox_events", "prompt_enhancements"}
CREDIT_TABLES = {"credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events"}
ACCOUNTING_TABLES = {"credit_reservations", "credit_reservation_items",
                     "credit_reservation_allocations", "credit_usage_records"}
EXPECTED_TABLES = G1_TABLES | {"users", "user_sessions", "credit_operations"} | CREDIT_TABLES | ACCOUNTING_TABLES
WORK_SECONDS = 300
CLEANUP_SECONDS = 90
_COMMAND_TIMEOUT = ContextVar("schema_command_timeout", default=120.0)
_COMMAND_INPUT = ContextVar("schema_command_input", default=None)
CREDIT_PROOF_PATH = REPO_ROOT / "backend" / "tests" / "credit_foundation_support.py"
ACCOUNTING_PROOF_PATH = REPO_ROOT / "backend" / "tests" / "credit_accounting_schema_support.py"
EXPECTED_ENUMS = {
    "asset_kind:image,video",
    "generation_mode:t2i,t2v,i2v",
    "job_state:pending,enhancing,queued,generating,polling,downloading,completed,failed,cancelled",
    "outbox_event_status:pending,published,failed",
    "user_origin:oauth,synthetic",
    "user_role:user,master",
    "user_status:active,suspended",
}
EXPECTED_FOREIGN_KEYS = {
    "fk_jobs_owner_user_id_users",
    "fk_prompt_enhancements_owner_user_id_users",
    "assets_job_id_fkey",
    "fk_jobs_retry_of_job_id_jobs",
    "fk_jobs_source_asset_id_assets",
    "jobs_enhancement_id_fkey",
    "jobs_parent_job_id_fkey",
    "fk_user_sessions_user_id_users",
    "fk_credit_accounts_user", "fk_credit_cycles_account", "fk_credit_grants_account",
    "fk_credit_grants_cycle_owner", "fk_credit_ledger_account", "fk_credit_ledger_grant_owner",
    "fk_credit_operations_account", "fk_credit_operations_cycle_owner", "fk_credit_operations_grant_owner",
    "fk_credit_reservations_account", "fk_credit_reservation_items_owner",
    "fk_credit_reservation_allocations_owner", "fk_credit_reservation_allocations_grant_owner",
    "fk_credit_usage_records_item_owner",
}
EXPECTED_INDEXES = {
    "ix_jobs_owner_created_at_id",
    "ix_prompt_enhancements_owner_created_at_id",
    "ix_assets_job_id",
    "ix_jobs_parent_job_id",
    "ix_jobs_retry_of_job_id",
    "ix_jobs_state",
    "ix_outbox_events_aggregate_id",
    "ix_outbox_events_event_type",
    "ix_outbox_events_event_type_status",
    "ix_outbox_events_status",
    "ix_outbox_events_status_created_at",
    "uq_jobs_active_i2v_source_asset",
    "ix_user_sessions_absolute_expires_at",
    "ix_user_sessions_active_user_id",
    "ix_credit_cycles_user_start", "uq_credit_grants_base_cycle",
    "ix_credit_grants_user_expiry", "ix_credit_ledger_user_created",
    "ix_credit_operations_user_effective",
    "uq_credit_reservations_user_terminal_key", "ix_credit_reservations_user_status_created",
    "ix_credit_reservation_items_user_reservation",
    "ix_credit_reservation_allocations_grant_reservation",
    "ix_credit_usage_records_user_recorded",
}


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str]], CommandResult]


class DeadlineRunner:
    def __init__(self, runner: Runner, seconds: float):
        self.runner = runner
        self.deadline = time.monotonic() + seconds

    def __call__(self, arguments: Sequence[str]) -> CommandResult:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise VerificationError("schema_deadline_exceeded")
        token = _COMMAND_TIMEOUT.set(min(120.0, remaining))
        try:
            result = self.runner(arguments)
        finally:
            _COMMAND_TIMEOUT.reset(token)
        if result.returncode == 124 or time.monotonic() > self.deadline:
            raise VerificationError("schema_command_timeout")
        return result


def code_revision(runner: Runner) -> str:
    revision = _run(runner, ["git", "rev-parse", "HEAD"], action="code revision").stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise VerificationError("invalid_code_revision")
    status = _run(runner, ["git", "status", "--porcelain", "--untracked-files=normal"], action="code status").stdout
    if any(line.strip() and any(not path.startswith(("docs/", ".omo/"))
                               for path in line[3:].split(" -> ")) for line in status.splitlines()):
        raise VerificationError("dirty_code_refused")
    return revision


def validate_project_name(project_name: str) -> str:
    if not PROJECT_PATTERN.fullmatch(project_name):
        raise VerificationError(
            "Project name must match schema-verify-[a-z0-9]{8,32}."
        )
    return project_name


def generate_project_name() -> str:
    return validate_project_name(f"schema-verify-{secrets.token_hex(6)}")


def validate_env_file(env_file: Path) -> dict[str, str]:
    resolved = env_file.resolve()
    if resolved.name != ".env.example":
        raise VerificationError("Only a file named .env.example is accepted.")
    if not resolved.is_file():
        raise VerificationError("The selected .env.example file does not exist.")

    values: dict[str, str] = {}
    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    if values.get("AI_PROVIDER") != "mock":
        raise VerificationError("Schema verification requires AI_PROVIDER=mock.")
    for required in ("POSTGRES_USER", "POSTGRES_DB"):
        if not values.get(required):
            raise VerificationError(f"{required} must be set in .env.example.")
    return values


def compose_command(
    project_name: str,
    env_file: Path,
    *arguments: str,
) -> list[str]:
    project_name = validate_project_name(project_name)
    return [
        "docker",
        "compose",
        "-p",
        project_name,
        "--env-file",
        str(env_file.resolve()),
        "-f",
        str((REPO_ROOT / "docker-compose.yml").resolve()),
        *arguments,
    ]


def subprocess_runner(arguments: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            list(arguments),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_COMMAND_TIMEOUT.get(),
            input=_COMMAND_INPUT.get(),
            env=dict(os.environ, AI_PROVIDER="mock", GOOGLE_APPLICATION_CREDENTIALS="",
                     AUTH_GOOGLE_CLIENT_ID="", AUTH_GOOGLE_CLIENT_SECRET="", AUTH_GOOGLE_REDIRECT_URI=""),
        )
    except subprocess.TimeoutExpired:
        return CommandResult(124)
    except OSError:
        return CommandResult(127)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _run(runner: Runner, arguments: Sequence[str], *, action: str) -> CommandResult:
    result = runner(arguments)
    if result.returncode != 0:
        if action.startswith("credit "):
            phase = re.search(r"^credit_proof_failed:(guard|additive|metadata|constraints|ledger|races|downgrade|done)$", result.stdout, re.M)
            if phase:
                raise VerificationError(f"{action} failed with exit code {result.returncode}; phase={phase[1]}.")
        if action == "accounting schema proof":
            phase = re.search(r"^accounting_schema_proof_failed:(guard|metadata|constraints|downgrade|done)$", result.stdout, re.M)
            if phase:
                raise VerificationError(f"{action} failed with exit code {result.returncode}; phase={phase[1]}.")
        raise VerificationError(f"{action} failed with exit code {result.returncode}.")
    return result


def refuse_collisions(project_name: str, runner: Runner) -> None:
    validate_project_name(project_name)
    projects = _run(
        runner,
        ["docker", "compose", "ls", "--format", "json"],
        action="Compose project collision check",
    )
    try:
        payload = json.loads(projects.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise VerificationError("Compose project collision output was invalid.") from exc
    if any(item.get("Name") == project_name for item in payload if isinstance(item, dict)):
        raise VerificationError("The exact isolated Compose project already exists.")

    volumes = _run(
        runner,
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
        action="Docker volume collision check",
    )
    volume_prefix = f"{project_name}_"
    if any(line.strip().startswith(volume_prefix) for line in volumes.stdout.splitlines()):
        raise VerificationError("A volume for the exact isolated project already exists.")
    for command in (("docker", "ps", "-aq"), ("docker", "volume", "ls", "-q"), ("docker", "network", "ls", "-q")):
        result = _run(runner, [*command, "--filter", f"label=com.docker.compose.project={project_name}"], action="exact resource collision")
        if result.stdout.strip():
            raise VerificationError("Exact isolated resource collision.")


def _psql_command(
    project_name: str,
    env_file: Path,
    *,
    user: str,
    database: str,
    sql: str,
) -> list[str]:
    return compose_command(
        project_name,
        env_file,
        "exec",
        "-T",
        "db",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        database,
        "-Atc",
        sql,
    )


def _query_lines(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
    sql: str,
    action: str,
) -> set[str]:
    result = _run(
        runner,
        _psql_command(
            project_name,
            env_file,
            user=values["POSTGRES_USER"],
            database=values["POSTGRES_DB"],
            sql=sql,
        ),
        action=action,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def assert_inventory(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    tables = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
        "table inventory",
    )
    if tables != EXPECTED_TABLES:
        raise VerificationError("Application table inventory did not match the baseline.")

    enums = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT t.typname || ':' || string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) "
        "FROM pg_type t JOIN pg_enum e ON t.oid=e.enumtypid "
        "JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' "
        "GROUP BY t.typname ORDER BY t.typname",
        "enum inventory",
    )
    if enums != EXPECTED_ENUMS:
        raise VerificationError("Native enum inventory did not match the baseline.")

    foreign_keys = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
        "WHERE n.nspname='public' AND c.contype='f' ORDER BY conname",
        "foreign-key inventory",
    )
    if foreign_keys != EXPECTED_FOREIGN_KEYS:
        raise VerificationError("Foreign-key inventory did not match the baseline.")

    indexes = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT i.indexname FROM pg_indexes i WHERE i.schemaname='public' "
        "AND NOT EXISTS (SELECT 1 FROM pg_constraint c "
        "WHERE c.conname=i.indexname AND c.contype IN ('p','u')) "
        "ORDER BY i.indexname",
        "index inventory",
    )
    if indexes != EXPECTED_INDEXES:
        raise VerificationError("Index inventory did not match the baseline.")

    predicate = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
        "AND indexname='uq_jobs_active_i2v_source_asset'",
        "active-I2V predicate inventory",
    )
    predicate_text = " ".join(predicate).lower()
    for token in ("unique", "source_asset_id", "i2v", "pending", "downloading"):
        if token not in predicate_text:
            raise VerificationError("Active-I2V index predicate did not match the contract.")

    head = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT version_num FROM alembic_version",
        "Alembic head inventory",
    )
    if head != {EXPECTED_REVISION}:
        raise VerificationError("Database revision did not match the packaged head.")


def assert_g1_schema_without_identity(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    tables = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
        "G1 table inventory",
    )
    if tables != G1_TABLES:
        raise VerificationError("G1 downgrade table inventory was not preserved exactly.")

    identity_types = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname='public' AND t.typname IN "
        "('user_origin','user_role','user_status') ORDER BY t.typname",
        "G1 identity-type absence check",
    )
    if identity_types:
        raise VerificationError("G2 identity enum types remained after downgrade to G1.")

    head = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT version_num FROM alembic_version",
        "G1 revision inventory",
    )
    if head != {G1_REVISION}:
        raise VerificationError("Downgrade did not stop at the G1 revision.")


def assert_baseline_absent(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    remaining = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
        "AND tablename IN ('jobs','assets','prompt_enhancements','outbox_events') "
        "UNION ALL SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname='public' AND typname IN "
        "('generation_mode','job_state','asset_kind','outbox_event_status')",
        "downgrade absence check",
    )
    if remaining:
        raise VerificationError("Downgrade left application tables or enum types behind.")


def _execute_sql(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
    sql: str,
) -> CommandResult:
    return runner(
        _psql_command(
            project_name,
            env_file,
            user=values["POSTGRES_USER"],
            database=values["POSTGRES_DB"],
            sql=sql,
        )
    )


def _expect_constraint_rejection(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
    *,
    sql: str,
    constraint: str,
) -> None:
    result = _execute_sql(runner, project_name, env_file, values, sql)
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode == 0 or constraint not in output:
        raise VerificationError(
            f"Postgres did not reject the invalid identity row with {constraint}."
        )
    password = values.get("POSTGRES_PASSWORD", "")
    if password and password in output:
        raise VerificationError("Constraint rejection output exposed environment data.")


def verify_identity_constraints(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    signed_up = "TIMESTAMPTZ '2026-01-01 00:00:00+00'"
    oauth_user = "10000000-0000-0000-0000-000000000001"
    synthetic_user = "10000000-0000-0000-0000-000000000002"
    valid_seed = f"""
INSERT INTO users
  (id, google_sub, email, email_verified, role, status, data_origin,
   signed_up_at, updated_at)
VALUES
  ('{oauth_user}', 'subject-one', 'profile-one' || chr(64) || 'invalid.test',
   true, 'user', 'active', 'oauth', {signed_up}, {signed_up}),
  ('{synthetic_user}', NULL, NULL, false, 'user', 'active', 'synthetic',
   {signed_up}, {signed_up});
INSERT INTO user_sessions
  (id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at)
VALUES
  ('20000000-0000-0000-0000-000000000001', '{oauth_user}',
   decode(repeat('01', 32), 'hex'), {signed_up}, {signed_up},
   {signed_up} + INTERVAL '7 days');
"""
    _run(
        runner,
        _psql_command(
            project_name,
            env_file,
            user=values["POSTGRES_USER"],
            database=values["POSTGRES_DB"],
            sql=valid_seed,
        ),
        action="valid identity seed",
    )

    invalid_cases = (
        (
            "INSERT INTO users "
            "(id, google_sub, email, email_verified, role, status, data_origin, signed_up_at, updated_at) "
            "VALUES ('10000000-0000-0000-0000-000000000011', 'subject-one', "
            "'duplicate' || chr(64) || 'invalid.test', true, 'user', 'active', 'oauth', "
            f"{signed_up}, {signed_up})",
            "uq_users_google_sub",
        ),
        (
            "INSERT INTO users "
            "(id, email_verified, role, status, data_origin, signed_up_at, updated_at) "
            "VALUES ('10000000-0000-0000-0000-000000000012', false, 'user', 'active', 'oauth', "
            f"{signed_up}, {signed_up})",
            "ck_users_origin_profile",
        ),
        (
            "INSERT INTO users "
            "(id, email_verified, role, status, data_origin, signed_up_at, updated_at) "
            "VALUES ('10000000-0000-0000-0000-000000000013', false, 'master', 'active', 'synthetic', "
            f"{signed_up}, {signed_up})",
            "ck_users_origin_profile",
        ),
        (
            "INSERT INTO users "
            "(id, email_verified, role, status, data_origin, signed_up_at, updated_at) "
            "VALUES ('10000000-0000-0000-0000-000000000014', false, 'user', 'suspended', 'synthetic', "
            f"{signed_up}, {signed_up})",
            "ck_users_suspension_state",
        ),
        (
            "INSERT INTO users "
            "(id, email_verified, role, status, data_origin, signed_up_at, updated_at) "
            "VALUES ('10000000-0000-0000-0000-000000000015', false, 'user', 'active', 'synthetic', "
            f"{signed_up}, {signed_up} - INTERVAL '1 second')",
            "ck_users_updated_after_signup",
        ),
        (
            "INSERT INTO user_sessions "
            "(id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at) "
            f"VALUES ('20000000-0000-0000-0000-000000000011', '{oauth_user}', "
            f"decode(repeat('01', 32), 'hex'), {signed_up}, {signed_up}, {signed_up} + INTERVAL '7 days')",
            "uq_user_sessions_token_hash",
        ),
        (
            "INSERT INTO user_sessions "
            "(id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at) "
            f"VALUES ('20000000-0000-0000-0000-000000000012', '{oauth_user}', "
            f"decode(repeat('02', 31), 'hex'), {signed_up}, {signed_up}, {signed_up} + INTERVAL '7 days')",
            "ck_user_sessions_token_hash_length",
        ),
        (
            "INSERT INTO user_sessions "
            "(id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at) "
            f"VALUES ('20000000-0000-0000-0000-000000000013', '{oauth_user}', "
            f"decode(repeat('03', 32), 'hex'), {signed_up}, {signed_up} - INTERVAL '1 second', "
            f"{signed_up} + INTERVAL '7 days')",
            "ck_user_sessions_lifecycle_order",
        ),
        (
            "INSERT INTO user_sessions "
            "(id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at) "
            f"VALUES ('20000000-0000-0000-0000-000000000014', '{oauth_user}', "
            f"decode(repeat('04', 32), 'hex'), {signed_up}, {signed_up}, {signed_up} + INTERVAL '6 days')",
            "ck_user_sessions_absolute_lifetime",
        ),
        (
            "INSERT INTO user_sessions "
            "(id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at, revoked_at) "
            f"VALUES ('20000000-0000-0000-0000-000000000015', '{oauth_user}', "
            f"decode(repeat('05', 32), 'hex'), {signed_up}, {signed_up}, "
            f"{signed_up} + INTERVAL '7 days', {signed_up})",
            "ck_user_sessions_revocation",
        ),
        (
            "INSERT INTO user_sessions "
            "(id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at, revoked_at, revoke_reason) "
            f"VALUES ('20000000-0000-0000-0000-000000000016', '{oauth_user}', "
            f"decode(repeat('06', 32), 'hex'), {signed_up}, {signed_up}, "
            f"{signed_up} + INTERVAL '7 days', {signed_up}, 'Unsafe Reason')",
            "ck_user_sessions_revoke_reason",
        ),
    )
    for sql, constraint in invalid_cases:
        _expect_constraint_rejection(
            runner,
            project_name,
            env_file,
            values,
            sql=sql,
            constraint=constraint,
        )

    counts = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT 'user_sessions:' || count(*) FROM user_sessions UNION ALL "
        "SELECT 'users:' || count(*) FROM users",
        "identity constraint row-count check",
    )
    if counts != {"user_sessions:1", "users:2"}:
        raise VerificationError("Invalid identity rows changed persisted row counts.")
    _run(
        runner,
        _psql_command(
            project_name,
            env_file,
            user=values["POSTGRES_USER"],
            database=values["POSTGRES_DB"],
            sql="DELETE FROM users",
        ),
        action="identity constraint cleanup",
    )


def verify_revision_refusal(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
    stale_revision: str = "0000_stale_revision",
) -> None:
    expected_revision = EXPECTED_REVISION
    if stale_revision not in ("0000_stale_revision", OWNERSHIP_REVISION, CREDIT_REVISION, LIFECYCLE_REVISION):
        raise VerificationError("invalid_stale_revision")
    update_revision = (
        "UPDATE alembic_version SET version_num="
        f"'{stale_revision}'"
    )
    restore_revision = (
        "UPDATE alembic_version SET version_num="
        f"'{expected_revision}'"
    )
    _run(
        runner,
        _psql_command(
            project_name,
            env_file,
            user=values["POSTGRES_USER"],
            database=values["POSTGRES_DB"],
            sql=update_revision,
        ),
        action="stale revision setup",
    )

    try:
        for service in ("backend", "worker", "dispatcher"):
            result = runner(
                compose_command(
                    project_name,
                    env_file,
                    "run",
                    "--rm",
                    "--no-deps",
                    service,
                )
            )
            output = f"{result.stdout}\n{result.stderr}"
            if result.returncode == 0 or "schema_revision_outdated" not in output:
                raise VerificationError(
                    f"{service} did not fail closed on a stale schema revision."
                )
            password = values.get("POSTGRES_PASSWORD", "")
            if password and password in output:
                raise VerificationError(
                    f"{service} stale-revision output exposed environment data."
                )
    finally:
        _run(
            runner,
            _psql_command(
                project_name,
                env_file,
                user=values["POSTGRES_USER"],
                database=values["POSTGRES_DB"],
                sql=restore_revision,
            ),
            action="schema revision recovery",
        )

    for service in ("backend", "worker", "dispatcher"):
        _run(
            runner,
            compose_command(
                project_name,
                env_file,
                "run",
                "--rm",
                "--no-deps",
                service,
                "python",
                "-m",
                "app.schema_control",
                "check",
            ),
            action=f"{service} schema recovery check",
        )


def reset_command(
    project_name: str,
    env_file: Path,
    *,
    database: str,
    execute: bool,
) -> list[str]:
    arguments = [
        "run",
        "--rm",
        "--no-deps",
        "-e",
        "APP_ENV=test",
        "migrate",
        "python",
        "-m",
        "app.schema_control",
        "reset",
        "--expected-database",
        database,
    ]
    if execute:
        arguments.extend(("--execute", "--confirm", f"RESET:{database}"))
    return compose_command(project_name, env_file, *arguments)


def _seed_reset_rows(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    sql = """
INSERT INTO users
  (id, google_sub, email, email_verified, role, status, data_origin,
   signed_up_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000005', 'reset-subject',
   'reset-profile' || chr(64) || 'invalid.test', true,
   'user', 'active', 'oauth', now(), now());
INSERT INTO user_sessions
  (id, user_id, token_hash, created_at, last_seen_at, absolute_expires_at)
VALUES
  ('00000000-0000-0000-0000-000000000006',
   '00000000-0000-0000-0000-000000000005', decode(repeat('07', 32), 'hex'),
   TIMESTAMPTZ '2026-01-01 00:00:00+00', TIMESTAMPTZ '2026-01-01 00:00:00+00',
   TIMESTAMPTZ '2026-01-08 00:00:00+00');
INSERT INTO prompt_enhancements
  (id, owner_user_id, original, enhanced, components, target_mode, target_model, llm_model, created_at)
VALUES
  ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000005',
   'seed', 'seed', '{}', 't2i', 'seed', 'seed', now());
INSERT INTO jobs
  (id, owner_user_id, mode, model, state, prompt, enhancement_id, blocked, attempts, parameters,
   state_history, vertex_charged, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000005',
   't2i', 'seed', 'pending', 'seed',
   '00000000-0000-0000-0000-000000000001', false, 0, '{}', '[]', false, now(), now());
INSERT INTO assets
  (id, job_id, kind, local_path, mime, size_bytes, created_at)
VALUES
  ('00000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000002', 'image', 'seed.png', 'image/png', 1, now());
INSERT INTO outbox_events
  (id, event_type, aggregate_type, aggregate_id, payload, status, attempts, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000004', 'seed', 'job',
   '00000000-0000-0000-0000-000000000002', '{}', 'pending', 0, now(), now());
"""
    _run(
        runner,
        _psql_command(
            project_name,
            env_file,
            user=values["POSTGRES_USER"],
            database=values["POSTGRES_DB"],
            sql=sql,
        ),
        action="reset seed",
    )


def _reset_row_counts(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> dict[str, int]:
    tables = sorted(EXPECTED_TABLES - {"alembic_version"})
    rows = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        " UNION ALL ".join(f"SELECT '{table}:' || count(*) FROM {table}" for table in tables),
        "reset row-count check",
    )
    if len(rows) != len(tables) or any(not re.fullmatch(r"[a-z_]+:[0-9]+", row) for row in rows):
        raise VerificationError("Invalid reset row-count response.")
    result = {row.split(":")[0]: int(row.split(":")[1]) for row in rows}
    if set(result) != set(tables):
        raise VerificationError("Unexpected reset tables.")
    return result


def _assert_reset_row_counts(runner, project_name, env_file, values, *, expected):
    rows = _reset_row_counts(runner, project_name, env_file, values)
    expected_rows = ({table: expected for table in rows} if type(expected) is int else expected)
    if rows != expected_rows:
        raise VerificationError("Reset row counts did not match the expected state.")


def _reset_data_snapshot(runner, project_name, env_file, values):
    # Kept only in memory for preview nonmutation; never output as evidence.
    return {table: _query_lines(runner, project_name, env_file, values,
            f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1", "reset preview snapshot")
            for table in sorted(EXPECTED_TABLES - {"alembic_version"})}


def verify_reset(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    database = values["POSTGRES_DB"]
    before = _reset_row_counts(runner, project_name, env_file, values)
    _seed_reset_rows(runner, project_name, env_file, values)
    # The fixed seed adds only the six legacy application rows, not accounting history.
    seeded_tables = {"users", "user_sessions", "jobs", "assets", "prompt_enhancements", "outbox_events"}
    expected = {table: count + (table in seeded_tables) for table, count in before.items()}
    _assert_reset_row_counts(
        runner, project_name, env_file, values, expected=expected
    )
    snapshot = _reset_data_snapshot(runner, project_name, env_file, values)
    preview = _run(
        runner,
        reset_command(
            project_name,
            env_file,
            database=database,
            execute=False,
        ),
        action="reset preview",
    )
    if "PREVIEW:" not in preview.stdout:
        raise VerificationError("Reset preview did not report preview mode.")
    _assert_reset_row_counts(
        runner, project_name, env_file, values, expected=expected
    )
    if _reset_data_snapshot(runner, project_name, env_file, values) != snapshot:
        raise VerificationError("Reset preview changed data.")
    _run(
        runner,
        reset_command(
            project_name,
            env_file,
            database=database,
            execute=True,
        ),
        action="guarded reset execution",
    )
    assert_inventory(runner, project_name, env_file, values)
    _assert_reset_row_counts(
        runner, project_name, env_file, values, expected=0
    )


# Fixed program executed only inside this verifier's newly owned migrate container.
# No user-supplied SQL/DSN, no row/exception output; comparisons stay in memory.
OWNERSHIP_PROOF_SCRIPT = r'''
import asyncio, os, sys
import asyncpg

OWNER = "20000000-0000-0000-0000-000000000001"
JOB = "20000000-0000-0000-0000-000000000002"
TABLES = ("jobs", "assets", "prompt_enhancements", "outbox_events")

async def main():
    connection = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:"))
    async def migrate(direction, target, reject=False):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", direction, target,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        output, error = await asyncio.wait_for(process.communicate(), 30)
        if reject:
            assert process.returncode != 0
            assert b"content_ownership_requires_empty_generation_tables" in output + error
        else:
            assert process.returncode == 0
    async def identity():
        return [await connection.fetch(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id")
                for table in ("users", "user_sessions")]
    async def snapshot():
        rows = [await connection.fetch(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id")
                for table in TABLES]
        columns = await connection.fetch("SELECT table_name,column_name,data_type,is_nullable,column_default "
                                         "FROM information_schema.columns WHERE table_schema='public' "
                                         "ORDER BY table_name,ordinal_position")
        constraints = await connection.fetch("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint "
                                             "WHERE connamespace='public'::regnamespace ORDER BY conname")
        indexes = await connection.fetch("SELECT indexname,indexdef FROM pg_indexes "
                                         "WHERE schemaname='public' ORDER BY indexname")
        return rows, columns, constraints, indexes, await connection.fetchval("SELECT version_num FROM alembic_version"), await identity()
    async def clear():
        for table in ("outbox_events", "assets", "jobs", "prompt_enhancements"):
            await connection.execute(f"DELETE FROM {table}")
    def fixture(table, owned=True):
        owner_column = ", owner_user_id" if owned else ""
        owner_value = f", '{OWNER}'" if owned else ""
        job = f"""INSERT INTO jobs (id,mode,model,state,prompt,blocked,attempts,parameters,
                   state_history,vertex_charged,created_at,updated_at{owner_column})
                   VALUES ('{JOB}','t2i','mock','failed','fixture',false,0,'{{}}','[]',false,now(),now(){owner_value});"""
        if table == "jobs":
            return job
        if table == "assets":
            return job + f"""INSERT INTO assets(id,job_id,kind,local_path,mime,size_bytes,created_at)
                VALUES ('20000000-0000-0000-0000-000000000003','{JOB}','image','ownership-fixture.png','image/png',1,now());"""
        if table == "prompt_enhancements":
            return f"""INSERT INTO prompt_enhancements(id,original,enhanced,components,target_mode,
                target_model,llm_model,created_at{owner_column}) VALUES
                ('20000000-0000-0000-0000-000000000004','fixture','fixture','{{}}','t2i','mock','mock',now(){owner_value});"""
        assert table == "outbox_events"
        return f"""INSERT INTO outbox_events(id,event_type,aggregate_type,aggregate_id,payload,status,
            attempts,created_at,updated_at) VALUES
            ('20000000-0000-0000-0000-000000000005','fixture','job','{JOB}','{{}}','pending',0,now(),now());"""
    async def rejects(sql, error_type):
        before = await snapshot()
        transaction = connection.transaction()
        await transaction.start()
        try:
            try:
                await connection.execute(sql)
            except error_type:
                pass
            else:
                raise AssertionError("expected_constraint_rejection")
        finally:
            await transaction.rollback()
        assert await snapshot() == before
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0003_content_ownership"
        assert all([await connection.fetchval(f"SELECT count(*) FROM {t}") == 0 for t in TABLES])
        await connection.execute(f"""INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at)
            VALUES ('{OWNER}',false,'user','active','synthetic',now(),now());
            INSERT INTO user_sessions(id,user_id,token_hash,created_at,last_seen_at,absolute_expires_at)
            VALUES ('20000000-0000-0000-0000-000000000006','{OWNER}',decode(repeat('ab',32),'hex'),
                    now(),now(),now()+interval '7 days');""")
        identities = await identity()
        for table in ("jobs", "prompt_enhancements"):
            metadata = await connection.fetchrow("SELECT data_type,is_nullable,column_default FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=$1 AND column_name='owner_user_id'", table)
            assert tuple(metadata) == ("uuid","NO",None)
            await rejects(fixture(table, False), asyncpg.NotNullViolationError)
            await rejects(fixture(table).replace(OWNER, "20000000-0000-0000-0000-000000000099"),
                          asyncpg.ForeignKeyViolationError)
            await connection.execute(fixture(table))
            await rejects(f"DELETE FROM users WHERE id='{OWNER}'", asyncpg.ForeignKeyViolationError)
            await clear()
        await connection.execute(fixture("assets"))
        await rejects(f"""INSERT INTO assets(id,job_id,kind,local_path,mime,size_bytes,created_at)
            VALUES ('20000000-0000-0000-0000-000000000007','{JOB}','image','ownership-fixture.png','image/png',1,now());""",
            asyncpg.UniqueViolationError)
        assert await connection.fetchval(f"SELECT bool_and(j.owner_user_id='{OWNER}'::uuid) FROM assets a JOIN jobs j ON j.id=a.job_id")
        await clear()
        for owned, direction, target in ((True,"downgrade","0002_user_session_persistence"),
                                          (False,"upgrade","0003_content_ownership")):
            if not owned:
                await migrate("downgrade","0002_user_session_persistence")
                assert await identity() == identities
            for table in TABLES:
                await connection.execute(fixture(table, owned))
                before = await snapshot()
                await migrate(direction,target,reject=True)
                assert await snapshot() == before
                await clear()
            if not owned:
                await migrate("upgrade","0003_content_ownership")
                assert await identity() == identities
        # Hold a conflicting lock until the migration's bounded lock_timeout refuses.
        transaction = connection.transaction()
        await transaction.start()
        await connection.execute("LOCK TABLE jobs IN ROW EXCLUSIVE MODE")
        process = await asyncio.create_subprocess_exec(sys.executable,"-m","alembic","downgrade",
            "0002_user_session_persistence",stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            output,error = await asyncio.wait_for(process.communicate(),20)
            assert process.returncode != 0 and b"lock timeout" in output+error
        finally:
            await transaction.rollback()
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0003_content_ownership"
        assert await identity() == identities
        await connection.execute(f"DELETE FROM users WHERE id='{OWNER}'")
    finally:
        await connection.close()

try:
    asyncio.run(main())
except Exception:
    print("ownership_schema_proof_failed")
    sys.exit(1)
print("ownership_schema_proof_pass")
'''


def verify_content_ownership(runner, project_name, env_file):
    _run(runner, compose_command(project_name, env_file, "run", "--rm", "--no-deps",
                                "migrate", "python", "-m", "alembic", "downgrade", OWNERSHIP_REVISION),
         action="pin legacy ownership revision")
    _run(runner, compose_command(project_name, env_file, "run", "--rm", "--no-deps",
                                 "migrate", "python", "-c", OWNERSHIP_PROOF_SCRIPT),
         action="ownership schema constraints and atomic refusal")
    _run(runner, compose_command(project_name, env_file, "run", "--rm", "--no-deps",
                                "migrate", "python", "-m", "alembic", "upgrade", "head"),
         action="restore credit head")


def verify_credit_foundation(runner, project_name, env_file, values, mode):
    if mode not in ("additive", "credit"):
        raise VerificationError("invalid_credit_proof_mode")
    source = CREDIT_PROOF_PATH.read_text(encoding="utf-8")
    token = _COMMAND_INPUT.set(source)
    try:
        result = _run(runner, compose_command(project_name, env_file, "run", "--rm", "--no-deps", "-T",
            "-e", "AI_PROVIDER=mock", "-e", "APP_ENV=test",
            "-e", f"CREDIT_PROOF_PROJECT={project_name}", "-e", f"CREDIT_PROOF_MODE={mode}",
            "-e", f"CREDIT_PROOF_DATABASE={values['POSTGRES_DB']}", "migrate", "python", "-"),
            action=f"credit {mode} proof")
    finally:
        _COMMAND_INPUT.reset(token)
    try:
        payload = json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        raise VerificationError("invalid_credit_proof_receipt") from None
    if (not isinstance(payload, dict) or set(payload) != {"mode", "checks"} or payload["mode"] != mode
            or type(payload["checks"]) is not int or payload["checks"] < (90 if mode == "credit" else 1)):
        raise VerificationError("invalid_credit_proof_receipt")
    return payload["checks"]


def verify_credit_accounting_schema(runner, project_name, env_file, values):
    source = ACCOUNTING_PROOF_PATH.read_text(encoding="utf-8")
    token = _COMMAND_INPUT.set(source)
    try:
        result = _run(runner, compose_command(
            project_name, env_file, "run", "--rm", "--no-deps", "-T",
            "-e", "AI_PROVIDER=mock", "-e", "APP_ENV=test",
            "-e", f"ACCOUNTING_SCHEMA_PROJECT={project_name}",
            "-e", f"ACCOUNTING_SCHEMA_DATABASE={values['POSTGRES_DB']}",
            "migrate", "python", "-"), action="accounting schema proof")
    finally:
        _COMMAND_INPUT.reset(token)
    try:
        payload = json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        raise VerificationError("invalid_accounting_schema_receipt") from None
    if (not isinstance(payload, dict)
            or set(payload) != {"groups", "checks", "downgrade_cases"}
            or payload["groups"] != 4 or type(payload["checks"]) is not int
            or payload["checks"] < 40 or payload["downgrade_cases"] != 4):
        raise VerificationError("invalid_accounting_schema_receipt")
    return payload["checks"], payload["downgrade_cases"]


def write_receipt(project_name: str, *, cleanup: bool, completed: bool, commit: str,
                  include_reset=False, credit_checks=0, accounting_checks=0,
                  accounting_downgrade_cases=0, work_seconds=0.0, cleanup_seconds=0.0,
                  failure_code="none", cleanup_failure_code="none") -> Path:
    validate_project_name(project_name)
    if (type(cleanup) is not bool or type(completed) is not bool or type(include_reset) is not bool
            or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or type(credit_checks) is not int or credit_checks < 0
            or type(accounting_checks) is not int or accounting_checks < 0
            or type(accounting_downgrade_cases) is not int or accounting_downgrade_cases < 0
            or failure_code not in ("none", "timeout", "verification_failed")
            or cleanup_failure_code not in ("none", "cleanup_failed")
            or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                   for value in (work_seconds, cleanup_seconds))
            or (completed and (not cleanup or failure_code != "none" or cleanup_failure_code != "none"
                               or credit_checks < 90 or accounting_checks < 40
                               or accounting_downgrade_cases != 4
                               or work_seconds > WORK_SECONDS or cleanup_seconds > CLEANUP_SECONDS))):
        raise VerificationError("invalid_schema_receipt")
    DEFAULT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = DEFAULT_EVIDENCE_DIR / f"migration-{project_name}.json"
    status = "pass" if completed else "unverified"
    receipt = {
        "project": project_name,
        "provider": "mock",
        "commit": commit,
        "revision": EXPECTED_REVISION if completed else "unverified",
        "expected_revision": EXPECTED_REVISION,
        "completed": completed,
        "round_trip": status,
        "g1_downgrade": status,
        "identity_constraints": status,
        "ownership_constraints": status,
        "nonempty_refusals": 8 if completed else 0,
        "lock_refusal": status,
        "identity_preservation": status,
        "revision_refusal": status,
        "additive_preservation": status,
        "metadata_parity": status,
        "credit_constraints": status,
        "credit_checks": credit_checks,
        "credit_uniqueness_races": 3 if completed else 0,
        "credit_downgrade_refusal": status,
        "credit_append_only": status,
        "operation_additive_round_trip": status,
        "operation_populated_lock_refusal": status,
        "stale_credit_revision": status,
        "accounting_constraints": status,
        "accounting_checks": accounting_checks,
        "accounting_downgrade_cases": accounting_downgrade_cases,
        "accounting_mutation_guards": status,
        "stale_lifecycle_revision": status,
        "reset": status if include_reset else "not_requested",
        "work_seconds": round(work_seconds, 3),
        "cleanup_seconds": round(cleanup_seconds, 3),
        "failure_code": failure_code,
        "cleanup_failure_code": cleanup_failure_code,
        "cleanup": "pass" if cleanup else "fail",
    }
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


def verify(
    *,
    env_file: Path = DEFAULT_ENV_FILE,
    project_name: str | None = None,
    runner: Runner = subprocess_runner,
    include_reset: bool = False,
) -> Path:
    started = time.monotonic()
    original_runner = runner
    runner = DeadlineRunner(runner, WORK_SECONDS)
    values = validate_env_file(env_file)
    project_name = validate_project_name(project_name or generate_project_name())
    commit = code_revision(runner)
    refuse_collisions(project_name, runner)
    cleanup_succeeded = False
    failure = None
    cleanup_failure = None
    credit_checks = 0
    accounting_checks = 0
    accounting_downgrade_cases = 0
    print(f"phase=start project={project_name}", flush=True)
    try:
        _run(runner, compose_command(project_name, env_file, "build", "migrate", "backend", "worker", "dispatcher"),
             action="current source image build")
        _run(
            runner,
            compose_command(
                project_name,
                env_file,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "90",
                "db",
            ),
            action="isolated Postgres startup",
        )
        for command, action in (
            (("upgrade", "head"), "Alembic upgrade"),
            (("downgrade", G1_REVISION), "Alembic downgrade to G1"),
            (("upgrade", "head"), "Alembic re-upgrade from G1"),
            (("downgrade", "base"), "Alembic full-chain downgrade"),
            (("upgrade", "head"), "Alembic full-chain re-upgrade"),
        ):
            _run(
                runner,
                compose_command(
                    project_name,
                    env_file,
                    "run",
                    "--rm",
                    "--no-deps",
                    "migrate",
                    "python",
                    "-m",
                    "alembic",
                    *command,
                ),
                action=action,
            )
            if command == ("downgrade", G1_REVISION):
                assert_g1_schema_without_identity(
                    runner, project_name, env_file, values
                )
            elif command == ("downgrade", "base"):
                assert_baseline_absent(runner, project_name, env_file, values)
            else:
                assert_inventory(runner, project_name, env_file, values)
        verify_identity_constraints(runner, project_name, env_file, values)
        verify_content_ownership(runner, project_name, env_file)
        print("phase=credit_additive", flush=True)
        verify_credit_foundation(runner, project_name, env_file, values, "additive")
        print("phase=credit_constraints", flush=True)
        credit_checks = verify_credit_foundation(runner, project_name, env_file, values, "credit")
        assert_inventory(runner, project_name, env_file, values)
        print("phase=accounting_schema", flush=True)
        accounting_checks, accounting_downgrade_cases = verify_credit_accounting_schema(
            runner, project_name, env_file, values)
        assert_inventory(runner, project_name, env_file, values)
        print("phase=revision_refusal", flush=True)
        verify_revision_refusal(runner, project_name, env_file, values)
        verify_revision_refusal(runner, project_name, env_file, values, OWNERSHIP_REVISION)
        verify_revision_refusal(runner, project_name, env_file, values, CREDIT_REVISION)
        verify_revision_refusal(runner, project_name, env_file, values, LIFECYCLE_REVISION)
        if include_reset:
            verify_reset(runner, project_name, env_file, values)
        if code_revision(runner) != commit:
            raise VerificationError("code_changed_during_proof")
    except VerificationError as error:
        failure = error
    except Exception:
        failure = VerificationError("unexpected_schema_failure")
    finally:
        work_seconds = time.monotonic() - started
        validate_project_name(project_name)
        cleanup_started = time.monotonic()
        cleanup_runner = DeadlineRunner(original_runner, CLEANUP_SECONDS)
        print("phase=cleanup", flush=True)
        try:
            _run(cleanup_runner, compose_command(project_name, env_file, "down", "-v", "--remove-orphans"), action="exact cleanup")
            for command in (("docker", "ps", "-aq"), ("docker", "volume", "ls", "-q"), ("docker", "network", "ls", "-q")):
                result = _run(cleanup_runner, [*command, "--filter", f"label=com.docker.compose.project={project_name}"], action="cleanup inventory")
                if result.stdout.strip():
                    raise VerificationError("cleanup_incomplete")
            cleanup_succeeded = True
        except Exception:
            cleanup_failure = "cleanup_failed"
        cleanup_seconds = time.monotonic() - cleanup_started
    if work_seconds > WORK_SECONDS and failure is None:
        failure = VerificationError("schema_deadline_exceeded")
    path = write_receipt(project_name, cleanup=cleanup_succeeded, completed=failure is None and cleanup_failure is None,
        commit=commit, include_reset=include_reset, credit_checks=credit_checks,
        accounting_checks=accounting_checks, accounting_downgrade_cases=accounting_downgrade_cases,
        work_seconds=work_seconds,
        cleanup_seconds=cleanup_seconds, failure_code=("none" if failure is None else
        "timeout" if any(token in str(failure) for token in ("timeout", "deadline")) else "verification_failed"),
        cleanup_failure_code=cleanup_failure or "none")
    if failure or cleanup_failure:
        raise VerificationError((str(failure) if failure else "") + ("; cleanup_failed" if cleanup_failure else ""))
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the G1 schema in isolated Postgres.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--project-name")
    parser.add_argument("--include-reset", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = verify(
            env_file=args.env_file,
            project_name=args.project_name,
            include_reset=args.include_reset,
        )
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: isolated schema round trip; receipt={receipt.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
