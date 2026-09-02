"""Add User and Session persistence without enabling authentication."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_user_session_persistence"
down_revision = "0001_generation_baseline"
branch_labels = None
depends_on = None


user_role = postgresql.ENUM(
    "user",
    "master",
    name="user_role",
    create_type=False,
)
user_status = postgresql.ENUM(
    "active",
    "suspended",
    name="user_status",
    create_type=False,
)
user_origin = postgresql.ENUM(
    "oauth",
    "synthetic",
    name="user_origin",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=False)
    user_status.create(bind, checkfirst=False)
    user_origin.create(bind, checkfirst=False)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("profile_image_url", sa.String(length=2048), nullable=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("status", user_status, nullable=False),
        sa.Column("data_origin", user_origin, nullable=False),
        sa.Column("signed_up_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(data_origin = 'oauth' AND google_sub IS NOT NULL "
            "AND email IS NOT NULL AND email_verified IS TRUE) "
            "OR (data_origin = 'synthetic' AND google_sub IS NULL "
            "AND email_verified IS FALSE AND role = 'user')",
            name="ck_users_origin_profile",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND suspended_at IS NULL) "
            "OR (status = 'suspended' AND suspended_at IS NOT NULL "
            "AND suspended_at >= signed_up_at)",
            name="ck_users_suspension_state",
        ),
        sa.CheckConstraint(
            "updated_at >= signed_up_at",
            name="ck_users_updated_after_signup",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32",
            name="ck_user_sessions_token_hash_length",
        ),
        sa.CheckConstraint(
            "last_seen_at >= created_at "
            "AND last_seen_at <= absolute_expires_at",
            name="ck_user_sessions_lifecycle_order",
        ),
        sa.CheckConstraint(
            "absolute_expires_at = created_at + INTERVAL '7 days'",
            name="ck_user_sessions_absolute_lifetime",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoke_reason IS NULL) "
            "OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL "
            "AND revoked_at >= created_at)",
            name="ck_user_sessions_revocation",
        ),
        sa.CheckConstraint(
            "revoke_reason IS NULL "
            "OR revoke_reason ~ '^[a-z0-9_]{1,64}$'",
            name="ck_user_sessions_revoke_reason",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index(
        "ix_user_sessions_active_user_id",
        "user_sessions",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_user_sessions_absolute_expires_at",
        "user_sessions",
        ["absolute_expires_at"],
    )


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_table("users")

    bind = op.get_bind()
    user_origin.drop(bind, checkfirst=False)
    user_status.drop(bind, checkfirst=False)
    user_role.drop(bind, checkfirst=False)
