"""Credit persistence only. Lifecycle and transaction writers are later Goals."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, PrimaryKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app import identity_models as _identity_models  # Register User FK target.


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", name="pk_credit_accounts"),
        CheckConstraint("plan IN ('free','pro','max')", name="ck_credit_accounts_plan"),
        CheckConstraint("pending_plan IS NULL OR (pending_plan IN ('free','pro','max') AND pending_plan <> plan)", name="ck_credit_accounts_pending_plan"),
        CheckConstraint("updated_at >= created_at AND created_at >= cycle_anchor_at", name="ck_credit_accounts_time"),
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", name="fk_credit_accounts_user", ondelete="RESTRICT"), primary_key=True)
    cycle_anchor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan: Mapped[str] = mapped_column(String(4), nullable=False)
    pending_plan: Mapped[str | None] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditCycle(Base):
    __tablename__ = "credit_cycles"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_credit_cycles"),
        UniqueConstraint("user_id", "cycle_index", name="uq_credit_cycles_user_index"),
        UniqueConstraint("id", "user_id", name="uq_credit_cycles_id_user"),
        CheckConstraint("cycle_index >= 0", name="ck_credit_cycles_index"),
        CheckConstraint("extract(epoch FROM (ends_at - starts_at)) = 2592000 AND created_at >= starts_at", name="ck_credit_cycles_time"),
        CheckConstraint("plan IN ('free','pro','max')", name="ck_credit_cycles_plan"),
        CheckConstraint("allowance_microcredits >= 0", name="ck_credit_cycles_allowance"),
        Index("ix_credit_cycles_user_start", "user_id", "starts_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("credit_accounts.user_id", name="fk_credit_cycles_account", ondelete="RESTRICT"), nullable=False)
    cycle_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan: Mapped[str] = mapped_column(String(4), nullable=False)
    allowance_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditGrant(Base):
    __tablename__ = "credit_grants"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_credit_grants"),
        UniqueConstraint("id", "user_id", name="uq_credit_grants_id_user"),
        ForeignKeyConstraint(["cycle_id", "user_id"], ["credit_cycles.id", "credit_cycles.user_id"], name="fk_credit_grants_cycle_owner", ondelete="RESTRICT"),
        CheckConstraint("(kind = 'base' AND cycle_id IS NOT NULL AND expires_at IS NOT NULL) OR (kind = 'bonus' AND cycle_id IS NULL)", name="ck_credit_grants_kind"),
        CheckConstraint("expires_at IS NULL OR expires_at > created_at", name="ck_credit_grants_expiry"),
        CheckConstraint("granted_microcredits >= 0 AND reserved_microcredits >= 0 AND consumed_microcredits >= 0 AND expired_microcredits >= 0", name="ck_credit_grants_nonnegative"),
        CheckConstraint("reserved_microcredits::numeric + consumed_microcredits::numeric + expired_microcredits::numeric <= granted_microcredits", name="ck_credit_grants_balance"),
        CheckConstraint("reason_code ~ '^[a-z0-9_]{1,64}$'", name="ck_credit_grants_reason"),
        Index("uq_credit_grants_base_cycle", "cycle_id", unique=True, postgresql_where=text("kind = 'base'")),
        Index("ix_credit_grants_user_expiry", "user_id", "expires_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("credit_accounts.user_id", name="fk_credit_grants_account", ondelete="RESTRICT"), nullable=False)
    cycle_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(5), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    consumed_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expired_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)

    @property
    def available_microcredits(self) -> int:
        return self.granted_microcredits - self.reserved_microcredits - self.consumed_microcredits - self.expired_microcredits


class CreditLedgerEvent(Base):
    __tablename__ = "credit_ledger_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_credit_ledger_events"),
        ForeignKeyConstraint(["grant_id", "user_id"], ["credit_grants.id", "credit_grants.user_id"], name="fk_credit_ledger_grant_owner", ondelete="RESTRICT"),
        UniqueConstraint("user_id", "operation_key", "grant_id", "kind", name="uq_credit_ledger_operation"),
        CheckConstraint("operation_key ~ '^[A-Za-z0-9_-]{1,128}$'", name="ck_credit_ledger_operation_key"),
        CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_ledger_version"),
        CheckConstraint("reason_code ~ '^[a-z0-9_]{1,64}$'", name="ck_credit_ledger_reason"),
        CheckConstraint(
            "(kind IN ('grant','adjust') AND granted_delta > 0 AND reserved_delta = 0 AND consumed_delta = 0 AND expired_delta = 0) OR "
            "(kind = 'reserve' AND granted_delta = 0 AND reserved_delta > 0 AND consumed_delta = 0 AND expired_delta = 0) OR "
            "(kind = 'settle' AND granted_delta = 0 AND reserved_delta < 0 AND consumed_delta >= 0 AND expired_delta >= 0 AND consumed_delta::numeric + expired_delta::numeric <= -reserved_delta::numeric) OR "
            "(kind = 'release' AND granted_delta = 0 AND reserved_delta < 0 AND consumed_delta = 0 AND expired_delta >= 0 AND expired_delta::numeric <= -reserved_delta::numeric) OR "
            "(kind = 'expire' AND granted_delta = 0 AND reserved_delta = 0 AND consumed_delta = 0 AND expired_delta > 0)",
            name="ck_credit_ledger_shape"),
        Index("ix_credit_ledger_user_created", "user_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("credit_accounts.user_id", name="fk_credit_ledger_account", ondelete="RESTRICT"), nullable=False)
    grant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(7), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    rate_card_version: Mapped[str] = mapped_column(String(10), nullable=False)
    granted_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    consumed_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expired_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
