from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
MIGRATIONS_ROOT = BACKEND_ROOT / "migrations"
VERSIONS_ROOT = MIGRATIONS_ROOT / "versions"
BASELINE_REVISION = VERSIONS_ROOT / "0001_generation_baseline.py"
IDENTITY_REVISION = VERSIONS_ROOT / "0002_user_session_persistence.py"
OWNERSHIP_REVISION = VERSIONS_ROOT / "0003_content_ownership.py"
CREDIT_REVISION = VERSIONS_ROOT / "0004_credit_foundation.py"
LIFECYCLE_REVISION = VERSIONS_ROOT / "0005_credit_lifecycle_operations.py"
ACCOUNTING_REVISION = VERSIONS_ROOT / "0006_credit_accounting_persistence.py"


def _text(path: Path) -> str:
    assert path.is_file(), f"Required G1 artifact is missing: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_alembic_runtime_dependency_and_required_files_exist() -> None:
    pyproject = _text(BACKEND_ROOT / "pyproject.toml")

    assert '"alembic>=1.14,<2.0"' in pyproject
    assert ALEMBIC_INI.is_file()
    assert (MIGRATIONS_ROOT / "env.py").is_file()
    assert (MIGRATIONS_ROOT / "script.py.mako").is_file()
    assert BASELINE_REVISION.is_file()


def test_exactly_six_ordered_revisions_are_packaged() -> None:
    revisions = sorted(VERSIONS_ROOT.glob("*.py")) if VERSIONS_ROOT.exists() else []

    assert revisions == [BASELINE_REVISION, IDENTITY_REVISION, OWNERSHIP_REVISION,
                         CREDIT_REVISION, LIFECYCLE_REVISION, ACCOUNTING_REVISION]
    baseline = _text(BASELINE_REVISION)
    identity = _text(IDENTITY_REVISION)
    assert 'revision = "0001_generation_baseline"' in baseline
    assert "down_revision = None" in baseline
    assert 'revision = "0002_user_session_persistence"' in identity
    assert 'down_revision = "0001_generation_baseline"' in identity
    ownership = _text(OWNERSHIP_REVISION)
    assert 'revision = "0003_content_ownership"' in ownership
    assert 'down_revision = "0002_user_session_persistence"' in ownership
    credit = _text(CREDIT_REVISION)
    assert 'revision = "0004_credit_foundation"' in credit
    assert 'down_revision = "0003_content_ownership"' in credit
    lifecycle = _text(LIFECYCLE_REVISION)
    assert 'revision = "0005_credit_lifecycle_operations"' in lifecycle
    assert 'down_revision = "0004_credit_foundation"' in lifecycle
    accounting = _text(ACCOUNTING_REVISION)
    assert 'revision = "0006_credit_accounting_persistence"' in accounting
    assert 'down_revision = "0005_credit_lifecycle_operations"' in accounting
    for table in ("credit_reservations", "credit_reservation_items",
                  "credit_reservation_allocations", "credit_usage_records"):
        assert f'"{table}"' in accounting
    for forbidden in ("DELETE FROM", "TRUNCATE TABLE", "DROP SCHEMA", "create_all", "stamp("):
        assert forbidden not in accounting

    dockerfile = _text(BACKEND_ROOT / "Dockerfile")
    assert "COPY alembic.ini" in dockerfile
    assert "COPY migrations" in dockerfile


def test_identity_revision_is_additive_and_credential_free() -> None:
    revision = _text(IDENTITY_REVISION)

    for table_name in ("users", "user_sessions"):
        assert f'"{table_name}"' in revision
    for enum_name in ("user_role", "user_status", "user_origin"):
        assert f'"{enum_name}"' in revision
    for generation_table in ("jobs", "assets", "prompt_enhancements", "outbox_events"):
        assert f'alter_table(\n        "{generation_table}"' not in revision
    for forbidden in (
        "password",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization_code",
        "raw_session",
    ):
        assert forbidden not in revision.lower()


def test_baseline_is_current_generation_schema_only() -> None:
    revision = _text(BASELINE_REVISION)

    for table_name in ("jobs", "assets", "prompt_enhancements", "outbox_events"):
        assert f'"{table_name}"' in revision
    for enum_name in (
        "generation_mode",
        "job_state",
        "asset_kind",
        "outbox_event_status",
    ):
        assert f'"{enum_name}"' in revision
    assert "fk_jobs_retry_of_job_id_jobs" in revision
    assert "ix_jobs_retry_of_job_id" in revision
    assert "uq_jobs_active_i2v_source_asset" in revision

    forbidden_future_schema = (
        "users",
        "sessions",
        "credit_accounts",
        "credit_reservations",
        "usage_events",
        "audit_events",
    )
    assert all(name not in revision for name in forbidden_future_schema)
    assert "stamp" not in revision.lower()


def test_alembic_configuration_uses_application_settings_without_committed_url() -> None:
    ini = _text(ALEMBIC_INI)
    env = _text(MIGRATIONS_ROOT / "env.py")

    assert "sqlalchemy.url" not in ini
    assert "get_settings" in env
    assert "database_url" in env
    assert "compare_type=True" in env
    assert "Base.metadata" in env
