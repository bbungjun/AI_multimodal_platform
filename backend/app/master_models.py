"""Append-only operator evidence; never an arbitrary JSON log sink."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MasterAudit(Base):
    __tablename__ = "master_audit"
    __table_args__ = (
        CheckConstraint("action IN ('promote','plan_change','bonus_grant','suspend','reactivate')", name="ck_master_audit_action"),
        CheckConstraint("(source = 'operator_cli' AND action = 'promote' AND actor_id = target_id) OR (source = 'browser' AND action <> 'promote')", name="ck_master_audit_source"),
        CheckConstraint("reason_code IN ('operator_bootstrap','entitlement_change','support_adjustment','service_recovery','account_policy','account_reactivated')", name="ck_master_audit_reason"),
        CheckConstraint("payload_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_master_audit_fingerprint"),
        CheckConstraint("jsonb_typeof(before_value) = 'object' AND before_value - ARRAY['role','status','plan','pending_plan','bonus_microcredits','revoked_sessions','cancelled_jobs']::text[] = '{}'::jsonb", name="ck_master_audit_before_value"),
        CheckConstraint("jsonb_typeof(after_value) = 'object' AND after_value - ARRAY['role','status','plan','pending_plan','bonus_microcredits','revoked_sessions','cancelled_jobs']::text[] = '{}'::jsonb", name="ck_master_audit_after_value"),
        Index("ix_master_audit_target_created", "target_id", "created_at", "request_id"),
        Index("ix_master_audit_created", "created_at", "request_id"),
    )
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey(
        "users.id", name="fk_master_audit_actor", ondelete="RESTRICT"), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey(
        "users.id", name="fk_master_audit_target", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    before_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
