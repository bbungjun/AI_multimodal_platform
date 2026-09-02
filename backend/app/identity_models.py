from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(StrEnum):
    USER = "user"
    MASTER = "master"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserOrigin(StrEnum):
    OAUTH = "oauth"
    SYNTHETIC = "synthetic"


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


user_role_enum = Enum(
    UserRole,
    name="user_role",
    values_callable=_enum_values,
)
user_status_enum = Enum(
    UserStatus,
    name="user_status",
    values_callable=_enum_values,
)
user_origin_enum = Enum(
    UserOrigin,
    name="user_origin",
    values_callable=_enum_values,
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
        CheckConstraint(
            "(data_origin = 'oauth' AND google_sub IS NOT NULL "
            "AND email IS NOT NULL AND email_verified IS TRUE) "
            "OR (data_origin = 'synthetic' AND google_sub IS NULL "
            "AND email_verified IS FALSE AND role = 'user')",
            name="ck_users_origin_profile",
        ),
        CheckConstraint(
            "(status = 'active' AND suspended_at IS NULL) "
            "OR (status = 'suspended' AND suspended_at IS NOT NULL "
            "AND suspended_at >= signed_up_at)",
            name="ck_users_suspension_state",
        ),
        CheckConstraint(
            "updated_at >= signed_up_at",
            name="ck_users_updated_after_signup",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    google_sub: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(200))
    profile_image_url: Mapped[str | None] = mapped_column(String(2048))
    role: Mapped[UserRole] = mapped_column(
        user_role_enum,
        nullable=False,
        default=UserRole.USER,
    )
    status: Mapped[UserStatus] = mapped_column(
        user_status_enum,
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    data_origin: Mapped[UserOrigin] = mapped_column(
        user_origin_enum,
        nullable=False,
    )
    signed_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    sessions: Mapped[list[UserSession]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        CheckConstraint(
            "octet_length(token_hash) = 32",
            name="ck_user_sessions_token_hash_length",
        ),
        CheckConstraint(
            "last_seen_at >= created_at "
            "AND last_seen_at <= absolute_expires_at",
            name="ck_user_sessions_lifecycle_order",
        ),
        CheckConstraint(
            "absolute_expires_at = created_at + INTERVAL '7 days'",
            name="ck_user_sessions_absolute_lifetime",
        ),
        CheckConstraint(
            "(revoked_at IS NULL AND revoke_reason IS NULL) "
            "OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL "
            "AND revoked_at >= created_at)",
            name="ck_user_sessions_revocation",
        ),
        CheckConstraint(
            "revoke_reason IS NULL "
            "OR revoke_reason ~ '^[a-z0-9_]{1,64}$'",
            name="ck_user_sessions_revoke_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship("User", back_populates="sessions")


Index(
    "ix_user_sessions_active_user_id",
    UserSession.user_id,
    postgresql_where=UserSession.revoked_at.is_(None),
)
Index(
    "ix_user_sessions_absolute_expires_at",
    UserSession.absolute_expires_at,
)
