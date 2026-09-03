from __future__ import annotations

import importlib
from pathlib import Path

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql


REPO_ROOT = Path(__file__).resolve().parents[2]
IDENTITY_MODELS_PATH = REPO_ROOT / "backend" / "app" / "identity_models.py"


def _identity_models():
    assert IDENTITY_MODELS_PATH.is_file(), "G2 identity persistence module is missing."
    return importlib.import_module("app.identity_models")


def _constraint_sql(table) -> dict[str, str]:
    dialect = postgresql.dialect()
    return {
        constraint.name: str(constraint.sqltext.compile(dialect=dialect)).lower()
        for constraint in table.constraints
        if getattr(constraint, "sqltext", None) is not None
    }


def test_identity_enums_are_exact_and_use_native_postgres_names() -> None:
    module = _identity_models()

    assert [item.value for item in module.UserRole] == ["user", "master"]
    assert [item.value for item in module.UserStatus] == ["active", "suspended"]
    assert [item.value for item in module.UserOrigin] == ["oauth", "synthetic"]
    assert module.user_role_enum.name == "user_role"
    assert module.user_status_enum.name == "user_status"
    assert module.user_origin_enum.name == "user_origin"


def test_user_mapping_has_profile_not_credential_identity_contract() -> None:
    module = _identity_models()
    table = module.User.__table__

    assert table.name == "users"
    assert set(table.columns) == {
        table.c.id,
        table.c.google_sub,
        table.c.email,
        table.c.email_verified,
        table.c.display_name,
        table.c.profile_image_url,
        table.c.role,
        table.c.status,
        table.c.data_origin,
        table.c.signed_up_at,
        table.c.suspended_at,
        table.c.updated_at,
    }
    assert table.c.google_sub.type.length == 255
    assert table.c.google_sub.nullable is True
    assert table.c.email.type.length == 320
    assert table.c.email.nullable is True
    assert table.c.role.default.arg == module.UserRole.USER
    assert table.c.status.default.arg == module.UserStatus.ACTIVE
    assert table.c.data_origin.default is None

    unique_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_users_google_sub" in unique_names
    assert all("email" not in (name or "") for name in unique_names)

    forbidden_columns = {
        "password",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization_code",
        "session_token",
    }
    assert forbidden_columns.isdisjoint(table.columns.keys())


def test_user_checks_lock_origin_status_and_timestamp_invariants() -> None:
    module = _identity_models()
    checks = _constraint_sql(module.User.__table__)

    assert set(checks) == {
        "ck_users_origin_profile",
        "ck_users_suspension_state",
        "ck_users_updated_after_signup",
    }
    assert all(token in checks["ck_users_origin_profile"] for token in (
        "google_sub",
        "email_verified",
        "oauth",
        "synthetic",
        "role",
        "user",
    ))
    assert "suspended_at" in checks["ck_users_suspension_state"]
    assert "signed_up_at" in checks["ck_users_updated_after_signup"]


def test_user_session_mapping_stores_only_a_digest_and_bounded_lifecycle() -> None:
    module = _identity_models()
    table = module.UserSession.__table__

    assert table.name == "user_sessions"
    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "token_hash",
        "created_at",
        "last_seen_at",
        "absolute_expires_at",
        "revoked_at",
        "revoke_reason",
    }
    assert table.c.token_hash.nullable is False
    assert table.c.revoke_reason.type.length == 64
    assert "token" not in {name for name in table.columns.keys() if name != "token_hash"}

    unique_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_user_sessions_token_hash" in unique_names
    checks = _constraint_sql(table)
    assert set(checks) == {
        "ck_user_sessions_token_hash_length",
        "ck_user_sessions_lifecycle_order",
        "ck_user_sessions_absolute_lifetime",
        "ck_user_sessions_revocation",
        "ck_user_sessions_revoke_reason",
    }
    assert "octet_length" in checks["ck_user_sessions_token_hash_length"]
    assert "7 days" in checks["ck_user_sessions_absolute_lifetime"]
    assert "last_seen_at" in checks["ck_user_sessions_lifecycle_order"]
    assert "revoked_at" in checks["ck_user_sessions_revocation"]


def test_user_session_relationship_and_indexes_match_query_paths() -> None:
    module = _identity_models()
    table = module.UserSession.__table__
    foreign_key = next(iter(table.c.user_id.foreign_keys))

    assert str(foreign_key.column) == "users.id"
    assert foreign_key.ondelete == "CASCADE"
    assert foreign_key.constraint.name == "fk_user_sessions_user_id_users"
    relationship = module.User.__mapper__.relationships["sessions"]
    assert relationship.mapper.class_ is module.UserSession
    assert "delete-orphan" in relationship.cascade

    indexes = {index.name: index for index in table.indexes}
    assert set(indexes) == {
        "ix_user_sessions_absolute_expires_at",
        "ix_user_sessions_active_user_id",
    }
    active_where = str(
        indexes["ix_user_sessions_active_user_id"]
        .dialect_options["postgresql"]["where"]
        .compile(dialect=postgresql.dialect())
    ).lower()
    assert "revoked_at is null" in active_where
    assert "now(" not in active_where


def test_generation_metadata_is_unchanged_when_identity_models_are_registered() -> None:
    _identity_models()
    from app.models import Asset, Job, OutboxEvent, PromptEnhancement

    assert set(Job.__table__.columns.keys()) == {
        "id", "owner_user_id", "mode", "model", "state", "prompt", "enhanced_prompt",
        "enhancement_id", "parent_job_id", "retry_of_job_id", "source_asset_id",
        "blocked", "vertex_operation_name", "attempts", "parameters",
        "state_history", "error", "vertex_charged", "created_at", "updated_at",
    }
    assert set(Asset.__table__.columns.keys()) == {
        "id", "job_id", "kind", "local_path", "mime", "size_bytes", "width",
        "height", "duration_sec", "created_at",
    }
    assert set(PromptEnhancement.__table__.columns.keys()) == {
        "id", "owner_user_id", "original", "enhanced", "components", "target_mode",
        "target_model", "llm_model", "latency_ms", "tokens_in", "tokens_out",
        "created_at",
    }
    assert set(OutboxEvent.__table__.columns.keys()) == {
        "id", "event_type", "aggregate_type", "aggregate_id", "payload", "status",
        "attempts", "last_error", "published_at", "created_at", "updated_at",
    }
