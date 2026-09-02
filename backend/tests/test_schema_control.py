from __future__ import annotations

import importlib
import inspect
from dataclasses import FrozenInstanceError, is_dataclass
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

