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


class CreditOperation(Base):
    """Immutable lifecycle command receipt, including commands with no money delta."""
    __tablename__ = "credit_operations"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "operation_key", name="pk_credit_operations"),
        ForeignKeyConstraint(["result_cycle_id", "user_id"], ["credit_cycles.id", "credit_cycles.user_id"], name="fk_credit_operations_cycle_owner", ondelete="RESTRICT"),
        ForeignKeyConstraint(["result_grant_id", "user_id"], ["credit_grants.id", "credit_grants.user_id"], name="fk_credit_operations_grant_owner", ondelete="RESTRICT"),
        CheckConstraint("operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_operations_key"),
        CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_operations_version"),
        CheckConstraint(
            "(kind = 'plan_change' AND target_plan IS NOT NULL AND target_plan IN ('free','pro','max') AND amount_microcredits IS NULL AND expires_at IS NULL AND reason_code IS NULL AND "
            "((outcome = 'upgraded' AND result_grant_id IS NOT NULL) OR (outcome IN ('scheduled','cancelled','unchanged') AND result_grant_id IS NULL))) OR "
            "(kind = 'bonus' AND target_plan IS NULL AND amount_microcredits IS NOT NULL AND amount_microcredits > 0 AND reason_code IS NOT NULL AND reason_code ~ '^[a-z0-9_]{1,64}$' AND "
            "(expires_at IS NULL OR expires_at > effective_at) AND outcome = 'granted' AND result_grant_id IS NOT NULL)",
            name="ck_credit_operations_shape"),
        Index("ix_credit_operations_user_effective", "user_id", "effective_at"),
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("credit_accounts.user_id", name="fk_credit_operations_account", ondelete="RESTRICT"), primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    kind: Mapped[str] = mapped_column(String(11), nullable=False)
    target_plan: Mapped[str | None] = mapped_column(String(4))
    amount_microcredits: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    rate_card_version: Mapped[str] = mapped_column(String(10), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_cycle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    result_grant_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)


class CreditReservation(Base):
    """Persistent accounting hold. Writers arrive in G5C2."""
    __tablename__ = "credit_reservations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_credit_reservations"),
        UniqueConstraint("id", "user_id", name="uq_credit_reservations_id_user"),
        UniqueConstraint("user_id", "reserve_operation_key", name="uq_credit_reservations_user_reserve_key"),
        CheckConstraint("reserve_operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_reservations_reserve_key"),
        CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_reservations_version"),
        CheckConstraint("reserved_microcredits > 0", name="ck_credit_reservations_amount"),
        CheckConstraint("terminal_operation_key IS NULL OR terminal_operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_reservations_terminal_key"),
        CheckConstraint("terminal_reason_code IS NULL OR terminal_reason_code ~ '^[a-z0-9_]{1,64}$'", name="ck_credit_reservations_reason"),
        CheckConstraint(
            "(status = 'held' AND terminal_operation_key IS NULL AND terminal_at IS NULL AND terminal_reason_code IS NULL AND delivery IS NULL) OR "
            "(status = 'settled' AND terminal_operation_key IS NOT NULL AND terminal_at IS NOT NULL AND terminal_at >= created_at AND terminal_reason_code IS NOT NULL AND delivery IN ('delivered','partial')) OR "
            "(status = 'released' AND terminal_operation_key IS NOT NULL AND terminal_at IS NOT NULL AND terminal_at >= created_at AND terminal_reason_code IS NOT NULL AND delivery = 'no_deliverable')",
            name="ck_credit_reservations_terminal_shape"),
        Index("uq_credit_reservations_user_terminal_key", "user_id", "terminal_operation_key", unique=True,
              postgresql_where=text("terminal_operation_key IS NOT NULL")),
        Index("ix_credit_reservations_user_status_created", "user_id", "status", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("credit_accounts.user_id", name="fk_credit_reservations_account", ondelete="RESTRICT"), nullable=False)
    reserve_operation_key: Mapped[str] = mapped_column(String(96), nullable=False)
    rate_card_version: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    reserved_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terminal_operation_key: Mapped[str | None] = mapped_column(String(96))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_reason_code: Mapped[str | None] = mapped_column(String(64))
    delivery: Mapped[str | None] = mapped_column(String(14))


class CreditReservationItem(Base):
    __tablename__ = "credit_reservation_items"
    __table_args__ = (
        PrimaryKeyConstraint("reservation_id", "meter", name="pk_credit_reservation_items"),
        UniqueConstraint("reservation_id", "user_id", "meter", name="uq_credit_reservation_items_owner_meter"),
        ForeignKeyConstraint(["reservation_id", "user_id"], ["credit_reservations.id", "credit_reservations.user_id"], name="fk_credit_reservation_items_owner", ondelete="RESTRICT"),
        CheckConstraint("meter IN ('gemini_input_token','gemini_output_token','imagen_fast_image','imagen_standard_image','imagen_ultra_image','veo_fast_ms','veo_standard_ms')", name="ck_credit_reservation_items_meter"),
        CheckConstraint("maximum_units > 0 AND quoted_microcredits > 0", name="ck_credit_reservation_items_amounts"),
        Index("ix_credit_reservation_items_user_reservation", "user_id", "reservation_id"),
    )
    reservation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    meter: Mapped[str] = mapped_column(String(32), primary_key=True)
    maximum_units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quoted_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CreditReservationAllocation(Base):
    __tablename__ = "credit_reservation_allocations"
    __table_args__ = (
        PrimaryKeyConstraint("reservation_id", "grant_id", name="pk_credit_reservation_allocations"),
        UniqueConstraint("reservation_id", "ordinal", name="uq_credit_reservation_allocations_ordinal"),
        ForeignKeyConstraint(["reservation_id", "user_id"], ["credit_reservations.id", "credit_reservations.user_id"], name="fk_credit_reservation_allocations_owner", ondelete="RESTRICT"),
        ForeignKeyConstraint(["grant_id", "user_id"], ["credit_grants.id", "credit_grants.user_id"], name="fk_credit_reservation_allocations_grant_owner", ondelete="RESTRICT"),
        CheckConstraint("ordinal >= 0", name="ck_credit_reservation_allocations_ordinal"),
        CheckConstraint("reserved_microcredits > 0", name="ck_credit_reservation_allocations_amount"),
        Index("ix_credit_reservation_allocations_grant_reservation", "grant_id", "reservation_id"),
    )
    reservation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    grant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CreditUsageRecord(Base):
    __tablename__ = "credit_usage_records"
    __table_args__ = (
        PrimaryKeyConstraint("reservation_id", "meter", name="pk_credit_usage_records"),
        UniqueConstraint("user_id", "terminal_operation_key", "meter", name="uq_credit_usage_records_user_terminal_meter"),
        ForeignKeyConstraint(["reservation_id", "user_id", "meter"], ["credit_reservation_items.reservation_id", "credit_reservation_items.user_id", "credit_reservation_items.meter"], name="fk_credit_usage_records_item_owner", ondelete="RESTRICT"),
        CheckConstraint("terminal_operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_usage_records_terminal_key"),
        CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_usage_records_version"),
        CheckConstraint("actual_units >= 0 AND charged_microcredits >= 0", name="ck_credit_usage_records_amounts"),
        CheckConstraint("source IN ('provider_reported','platform_measured','mock_estimate','estimated')", name="ck_credit_usage_records_source"),
        CheckConstraint("(delivery IN ('delivered','partial')) OR (delivery = 'no_deliverable' AND charged_microcredits = 0)", name="ck_credit_usage_records_delivery"),
        Index("ix_credit_usage_records_user_recorded", "user_id", "recorded_at", "reservation_id"),
    )
    reservation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    meter: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    terminal_operation_key: Mapped[str] = mapped_column(String(96), nullable=False)
    rate_card_version: Mapped[str] = mapped_column(String(10), nullable=False)
    actual_units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    charged_microcredits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery: Mapped[str] = mapped_column(String(14), nullable=False)


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
