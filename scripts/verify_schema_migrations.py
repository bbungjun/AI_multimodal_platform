#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.example"
DEFAULT_EVIDENCE_DIR = REPO_ROOT / ".omo" / "evidence" / "issue-94"
PROJECT_PATTERN = re.compile(r"^g1-schema-[a-z0-9]{8,32}$")
EXPECTED_TABLES = {"alembic_version", "assets", "jobs", "outbox_events", "prompt_enhancements"}
EXPECTED_ENUMS = {
    "asset_kind:image,video",
    "generation_mode:t2i,t2v,i2v",
    "job_state:pending,enhancing,queued,generating,polling,downloading,completed,failed,cancelled",
    "outbox_event_status:pending,published,failed",
}
EXPECTED_FOREIGN_KEYS = {
    "assets_job_id_fkey",
    "fk_jobs_retry_of_job_id_jobs",
    "fk_jobs_source_asset_id_assets",
    "jobs_enhancement_id_fkey",
    "jobs_parent_job_id_fkey",
}
EXPECTED_INDEXES = {
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
}


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str]], CommandResult]


def validate_project_name(project_name: str) -> str:
    if not PROJECT_PATTERN.fullmatch(project_name):
        raise VerificationError(
            "Project name must match g1-schema-[a-z0-9]{8,32}."
        )
    return project_name


def generate_project_name() -> str:
    return validate_project_name(f"g1-schema-{secrets.token_hex(6)}")


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
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(124)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _run(runner: Runner, arguments: Sequence[str], *, action: str) -> CommandResult:
    result = runner(arguments)
    if result.returncode != 0:
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
    if head != {"0001_generation_baseline"}:
        raise VerificationError("Database revision did not match the packaged head.")


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


def verify_revision_refusal(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    expected_revision = "0001_generation_baseline"
    stale_revision = "0000_stale_revision"
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
INSERT INTO prompt_enhancements
  (id, original, enhanced, components, target_mode, target_model, llm_model, created_at)
VALUES
  ('00000000-0000-0000-0000-000000000001', 'seed', 'seed', '{}', 't2i', 'seed', 'seed', now());
INSERT INTO jobs
  (id, mode, model, state, prompt, enhancement_id, blocked, attempts, parameters,
   state_history, vertex_charged, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000002', 't2i', 'seed', 'pending', 'seed',
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


def _assert_reset_row_counts(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
    *,
    expected: int,
) -> None:
    rows = _query_lines(
        runner,
        project_name,
        env_file,
        values,
        "SELECT 'assets:' || count(*) FROM assets UNION ALL "
        "SELECT 'jobs:' || count(*) FROM jobs UNION ALL "
        "SELECT 'outbox_events:' || count(*) FROM outbox_events UNION ALL "
        "SELECT 'prompt_enhancements:' || count(*) FROM prompt_enhancements",
        "reset row-count check",
    )
    expected_rows = {f"{table}:{expected}" for table in ("assets", "jobs", "outbox_events", "prompt_enhancements")}
    if rows != expected_rows:
        raise VerificationError("Reset row counts did not match the expected state.")


def verify_reset(
    runner: Runner,
    project_name: str,
    env_file: Path,
    values: dict[str, str],
) -> None:
    database = values["POSTGRES_DB"]
    _seed_reset_rows(runner, project_name, env_file, values)
    _assert_reset_row_counts(
        runner, project_name, env_file, values, expected=1
    )
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
        runner, project_name, env_file, values, expected=1
    )
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


def write_receipt(project_name: str, *, cleanup: bool) -> Path:
    validate_project_name(project_name)
    DEFAULT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = DEFAULT_EVIDENCE_DIR / f"migration-{project_name}.json"
    receipt = {
        "project": project_name,
        "provider": "mock",
        "revision": "0001_generation_baseline",
        "round_trip": "pass",
        "revision_refusal": "pass",
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
    values = validate_env_file(env_file)
    project_name = validate_project_name(project_name or generate_project_name())
    refuse_collisions(project_name, runner)
    cleanup_succeeded = False
    try:
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
            (("downgrade", "base"), "Alembic downgrade"),
            (("upgrade", "head"), "Alembic re-upgrade"),
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
            if command == ("downgrade", "base"):
                assert_baseline_absent(runner, project_name, env_file, values)
            else:
                assert_inventory(runner, project_name, env_file, values)
        verify_revision_refusal(runner, project_name, env_file, values)
        if include_reset:
            verify_reset(runner, project_name, env_file, values)
    finally:
        validate_project_name(project_name)
        cleanup = runner(
            compose_command(project_name, env_file, "down", "-v", "--remove-orphans")
        )
        cleanup_succeeded = cleanup.returncode == 0

    if not cleanup_succeeded:
        raise VerificationError("Exact isolated Compose cleanup failed.")
    return write_receipt(project_name, cleanup=True)


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
