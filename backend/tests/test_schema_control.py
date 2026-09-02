from __future__ import annotations

import importlib
import inspect
from argparse import Namespace
from dataclasses import is_dataclass
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_CONTROL_PATH = REPO_ROOT / "backend" / "app" / "schema_control.py"
EXPECTED_ERROR_CODES = {
    "schema_version_table_missing",
    "schema_revision_missing",
    "schema_revision_outdated",
    "schema_multiple_heads",
    "schema_unreachable",
    "reset_target_forbidden",
    "reset_confirmation_mismatch",
    "reset_partial_failure",
}


def _schema_control():
    assert SCHEMA_CONTROL_PATH.is_file(), "G1 schema-control module is missing."
    return importlib.import_module("app.schema_control")


def test_schema_control_exposes_one_small_async_interface() -> None:
    module = _schema_control()

    for name in (
        "require_current_schema",
        "plan_local_reset",
        "execute_local_reset",
    ):
        assert inspect.iscoroutinefunction(getattr(module, name))

    assert list(inspect.signature(module.require_current_schema).parameters) == []
    assert list(inspect.signature(module.plan_local_reset).parameters) == [
        "expected_database"
    ]
    assert list(inspect.signature(module.execute_local_reset).parameters) == [
        "plan",
        "confirmation",
    ]


def test_schema_control_results_are_immutable_and_errors_are_typed() -> None:
    module = _schema_control()

    for result_type_name in ("SchemaReadiness", "ResetPlan", "ResetResult"):
        result_type = getattr(module, result_type_name)
        assert is_dataclass(result_type)
        params = getattr(result_type, "__dataclass_params__")
        assert params.frozen is True

    codes = {member.value for member in module.SchemaErrorCode}
    assert codes == EXPECTED_ERROR_CODES

    error = module.SchemaControlError(
        module.SchemaErrorCode.SCHEMA_REVISION_OUTDATED,
        current_revision="old_revision",
        expected_revision="expected_revision",
    )
    assert error.code == "schema_revision_outdated"
    assert "old_revision" in str(error)
    assert "expected_revision" in str(error)
    assert "postgresql" not in str(error)


async def test_require_current_schema_returns_the_single_current_revision(monkeypatch) -> None:
    module = _schema_control()
    monkeypatch.setattr(
        module,
        "_resolve_code_heads",
        lambda: ("0001_generation_baseline",),
    )

    async def read_database_revisions():
        return ("0001_generation_baseline",)

    monkeypatch.setattr(module, "_read_database_revisions", read_database_revisions)

    readiness = await module.require_current_schema()

    assert readiness.current_revision == "0001_generation_baseline"
    assert readiness.expected_revision == "0001_generation_baseline"


@pytest.mark.parametrize(
    ("database_revisions", "expected_code"),
    [
        (None, "schema_version_table_missing"),
        ((), "schema_revision_missing"),
        (("old_revision",), "schema_revision_outdated"),
        (("head_a", "head_b"), "schema_multiple_heads"),
    ],
)
async def test_require_current_schema_maps_revision_failures(
    monkeypatch,
    database_revisions,
    expected_code,
) -> None:
    module = _schema_control()
    monkeypatch.setattr(
        module,
        "_resolve_code_heads",
        lambda: ("0001_generation_baseline",),
    )

    async def read_database_revisions():
        return database_revisions

    monkeypatch.setattr(module, "_read_database_revisions", read_database_revisions)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.require_current_schema()

    assert exc_info.value.code == expected_code


async def test_require_current_schema_fails_closed_without_leaking_connection_error(
    monkeypatch,
) -> None:
    module = _schema_control()
    monkeypatch.setattr(
        module,
        "_resolve_code_heads",
        lambda: ("0001_generation_baseline",),
    )
    secret = "postgresql+asyncpg://app:do-not-leak@remote.example/prod"

    async def read_database_revisions():
        raise RuntimeError(secret)

    monkeypatch.setattr(module, "_read_database_revisions", read_database_revisions)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.require_current_schema()

    assert exc_info.value.code == "schema_unreachable"
    assert secret not in str(exc_info.value)


async def test_require_current_schema_rejects_multiple_code_heads(monkeypatch) -> None:
    module = _schema_control()
    monkeypatch.setattr(module, "_resolve_code_heads", lambda: ("head_a", "head_b"))

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.require_current_schema()

    assert exc_info.value.code == "schema_multiple_heads"


def test_runtime_processes_check_schema_without_mutating_it() -> None:
    runtime_paths = (
        REPO_ROOT / "backend" / "app" / "db.py",
        REPO_ROOT / "backend" / "app" / "main.py",
        REPO_ROOT / "backend" / "app" / "worker.py",
        REPO_ROOT
        / "backend"
        / "app"
        / "services"
        / "jobs"
        / "outbox_dispatcher.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in runtime_paths)

    assert "create_all" not in source
    assert "ALTER TABLE" not in source
    assert "CREATE INDEX" not in source
    assert "init_db_schema" not in source
    assert source.count("require_current_schema") >= 6


def test_reset_contract_is_preview_first_and_requires_every_guard() -> None:
    module = _schema_control()
    source = SCHEMA_CONTROL_PATH.read_text(encoding="utf-8")

    assert "APP_ENV" in source or "app_env" in source
    for host in ("db", "localhost", "127.0.0.1"):
        assert host in source
    assert "RESET:" in source
    assert "--execute" in source
    assert "--expected-database" in source
    assert "--confirm" in source
    assert "DROP SCHEMA public" in source
    assert "CREATE SCHEMA public" in source

    assert "DROP DATABASE" not in source
    assert "docker volume" not in source.lower()
    assert "redis" not in source.lower()
    assert "gcloud" not in source.lower()


def test_schema_control_cli_help_is_available_without_database_access(capsys) -> None:
    module = _schema_control()

    with pytest.raises(SystemExit) as exc_info:
        module.main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "check" in output
    assert "reset" in output
    assert "--expected-database" not in output


async def test_reset_preview_returns_only_redacted_exact_local_target(
    monkeypatch,
) -> None:
    module = _schema_control()
    secret = "do-not-leak"
    settings = module.Settings(
        _env_file=None,
        app_env="local",
        database_url=f"postgresql+asyncpg://app:{secret}@db:5432/multimodal",
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        module,
        "_resolve_code_heads",
        lambda: ("0001_generation_baseline",),
    )

    async def current_snapshot():
        return module._ResetSnapshot(
            "multimodal",
            "0001_generation_baseline",
            (("jobs", 2), ("assets", 1)),
        )

    monkeypatch.setattr(module, "_current_reset_snapshot", current_snapshot)

    plan = await module.plan_local_reset("multimodal")

    assert plan.app_env == "local"
    assert plan.dialect == "postgresql"
    assert plan.host == "db"
    assert plan.database == "multimodal"
    assert plan.row_counts == (("jobs", 2), ("assets", 1))
    assert secret not in repr(plan)
    assert "postgresql+asyncpg" not in repr(plan)


@pytest.mark.parametrize(
    ("app_env", "database_url", "expected_database"),
    [
        (
            "production",
            "postgresql+asyncpg://app:secret@db:5432/multimodal",
            "multimodal",
        ),
        (
            "local",
            "postgresql+asyncpg://app:secret@remote.example:5432/multimodal",
            "multimodal",
        ),
        (
            "local",
            "postgresql+asyncpg://app:secret@db:5432/multimodal",
            "another_database",
        ),
    ],
)
async def test_reset_preview_refuses_environment_host_and_expected_database(
    monkeypatch,
    app_env,
    database_url,
    expected_database,
) -> None:
    module = _schema_control()
    settings = module.Settings(
        _env_file=None,
        app_env=app_env,
        database_url=database_url,
    )
    snapshot_calls = 0

    async def current_snapshot():
        nonlocal snapshot_calls
        snapshot_calls += 1
        raise AssertionError("forbidden target must fail before connecting")

    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(module, "_current_reset_snapshot", current_snapshot)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.plan_local_reset(expected_database)

    assert exc_info.value.code == "reset_target_forbidden"
    assert snapshot_calls == 0
    assert "secret" not in str(exc_info.value)


async def test_reset_preview_refuses_live_database_name_mismatch(monkeypatch) -> None:
    module = _schema_control()
    settings = module.Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://app:secret@localhost:5432/multimodal",
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        module,
        "_resolve_code_heads",
        lambda: ("0001_generation_baseline",),
    )

    async def current_snapshot():
        return module._ResetSnapshot("different", "unversioned", ())

    monkeypatch.setattr(module, "_current_reset_snapshot", current_snapshot)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.plan_local_reset("multimodal")

    assert exc_info.value.code == "reset_target_forbidden"


def _reset_plan(module):
    return module.ResetPlan(
        app_env="test",
        dialect="postgresql",
        host="db",
        port=5432,
        database="multimodal",
        current_revision="0001_generation_baseline",
        target_revision="0001_generation_baseline",
        row_counts=(("jobs", 2), ("assets", 1)),
    )


async def test_reset_execution_requires_exact_confirmation_before_mutation(
    monkeypatch,
) -> None:
    module = _schema_control()
    plan = _reset_plan(module)
    mutation_calls = 0

    async def reset_public_schema():
        nonlocal mutation_calls
        mutation_calls += 1

    monkeypatch.setattr(module, "_reset_public_schema", reset_public_schema)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.execute_local_reset(plan, confirmation="RESET:another_database")

    assert exc_info.value.code == "reset_confirmation_mismatch"
    assert mutation_calls == 0


async def test_reset_execution_revalidates_target_and_returns_current_head(
    monkeypatch,
) -> None:
    module = _schema_control()
    plan = _reset_plan(module)
    calls: list[str] = []

    async def fresh_plan(_expected_database):
        calls.append("revalidate")
        return plan

    async def reset_public_schema():
        calls.append("reset")

    def upgrade_to_head():
        calls.append("upgrade")

    async def require_current_schema():
        calls.append("check")
        return module.SchemaReadiness(
            "0001_generation_baseline", "0001_generation_baseline"
        )

    monkeypatch.setattr(module, "plan_local_reset", fresh_plan)
    monkeypatch.setattr(module, "_reset_public_schema", reset_public_schema)
    monkeypatch.setattr(module, "_upgrade_to_head", upgrade_to_head)
    monkeypatch.setattr(module, "require_current_schema", require_current_schema)

    result = await module.execute_local_reset(
        plan,
        confirmation="RESET:multimodal",
    )

    assert calls == ["revalidate", "reset", "upgrade", "check"]
    assert result.current_revision == "0001_generation_baseline"
    assert result.deleted_rows == 3


async def test_reset_upgrade_failure_reports_partial_reset_and_recovery(
    monkeypatch,
) -> None:
    module = _schema_control()
    plan = _reset_plan(module)

    async def fresh_plan(_expected_database):
        return plan

    async def reset_public_schema():
        return None

    def failed_upgrade():
        raise RuntimeError("database URL must not leak")

    monkeypatch.setattr(module, "plan_local_reset", fresh_plan)
    monkeypatch.setattr(module, "_reset_public_schema", reset_public_schema)
    monkeypatch.setattr(module, "_upgrade_to_head", failed_upgrade)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.execute_local_reset(plan, confirmation="RESET:multimodal")

    assert exc_info.value.code == "reset_partial_failure"
    assert exc_info.value.recovery_command == "python -m alembic upgrade head"
    assert "database URL" not in str(exc_info.value)


async def test_reset_ddl_failure_is_typed_and_does_not_leak_raw_error(
    monkeypatch,
) -> None:
    module = _schema_control()
    plan = _reset_plan(module)

    async def fresh_plan(_expected_database):
        return plan

    async def failed_reset():
        raise RuntimeError("postgresql://app:do-not-leak@db/multimodal")

    monkeypatch.setattr(module, "plan_local_reset", fresh_plan)
    monkeypatch.setattr(module, "_reset_public_schema", failed_reset)

    with pytest.raises(module.SchemaControlError) as exc_info:
        await module.execute_local_reset(plan, confirmation="RESET:multimodal")

    assert exc_info.value.code == "reset_partial_failure"
    assert exc_info.value.recovery_command == "python -m alembic upgrade head"
    assert "do-not-leak" not in str(exc_info.value)


async def test_reset_cli_without_execute_is_preview_only(monkeypatch, capsys) -> None:
    module = _schema_control()
    plan = _reset_plan(module)
    execute_calls = 0

    async def preview(_expected_database):
        return plan

    async def execute(*_args, **_kwargs):
        nonlocal execute_calls
        execute_calls += 1
        raise AssertionError("preview must not execute reset")

    monkeypatch.setattr(module, "plan_local_reset", preview)
    monkeypatch.setattr(module, "execute_local_reset", execute)

    result = await module._run_command(
        Namespace(
            command="reset",
            expected_database="multimodal",
            execute=False,
            confirm=None,
        )
    )

    assert result == 0
    assert execute_calls == 0
    assert "PREVIEW" in capsys.readouterr().out
