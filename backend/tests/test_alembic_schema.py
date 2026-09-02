from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
MIGRATIONS_ROOT = BACKEND_ROOT / "migrations"
VERSIONS_ROOT = MIGRATIONS_ROOT / "versions"
BASELINE_REVISION = VERSIONS_ROOT / "0001_generation_baseline.py"


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


def test_exactly_one_generation_baseline_revision_is_packaged() -> None:
    revisions = sorted(VERSIONS_ROOT.glob("*.py")) if VERSIONS_ROOT.exists() else []

    assert revisions == [BASELINE_REVISION]
    revision = _text(BASELINE_REVISION)
    assert 'revision = "0001_generation_baseline"' in revision
    assert "down_revision = None" in revision

    dockerfile = _text(BACKEND_ROOT / "Dockerfile")
    assert "COPY alembic.ini" in dockerfile
    assert "COPY migrations" in dockerfile


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


