"""Add empty append-only Master audit; no data rewrite."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_master_audit"
down_revision = "0006_credit_accounting_persistence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("master_audit",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("payload_fingerprint", sa.String(64), nullable=False),
        sa.Column("before_value", postgresql.JSONB(), nullable=False),
        sa.Column("after_value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("request_id", name="pk_master_audit"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_master_audit_actor", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"], name="fk_master_audit_target", ondelete="RESTRICT"),
        sa.CheckConstraint("action IN ('promote','plan_change','bonus_grant','suspend','reactivate')", name="ck_master_audit_action"),
        sa.CheckConstraint("(source = 'operator_cli' AND action = 'promote' AND actor_id = target_id) OR (source = 'browser' AND action <> 'promote')", name="ck_master_audit_source"),
        sa.CheckConstraint("reason_code IN ('operator_bootstrap','entitlement_change','support_adjustment','service_recovery','account_policy','account_reactivated')", name="ck_master_audit_reason"),
        sa.CheckConstraint("payload_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_master_audit_fingerprint"),
        sa.CheckConstraint("jsonb_typeof(before_value) = 'object' AND before_value - ARRAY['role','status','plan','pending_plan','bonus_microcredits','revoked_sessions','cancelled_jobs']::text[] = '{}'::jsonb", name="ck_master_audit_before_value"),
        sa.CheckConstraint("jsonb_typeof(after_value) = 'object' AND after_value - ARRAY['role','status','plan','pending_plan','bonus_microcredits','revoked_sessions','cancelled_jobs']::text[] = '{}'::jsonb", name="ck_master_audit_after_value"),
    )
    op.create_index("ix_master_audit_target_created", "master_audit", ["target_id", "created_at", "request_id"])
    op.create_index("ix_master_audit_created", "master_audit", ["created_at", "request_id"])
    op.execute("""
        CREATE FUNCTION master_audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'master_audit_append_only' USING ERRCODE = '23514';
        END $$;
    """)
    op.execute("CREATE TRIGGER master_audit_no_mutation BEFORE UPDATE OR DELETE ON master_audit "
               "FOR EACH ROW EXECUTE FUNCTION master_audit_append_only()")
    op.execute("CREATE TRIGGER master_audit_no_truncate BEFORE TRUNCATE ON master_audit "
               "FOR EACH STATEMENT EXECUTE FUNCTION master_audit_append_only()")


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text("LOCK TABLE master_audit IN ACCESS EXCLUSIVE MODE"))
    connection.execute(sa.text("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM master_audit) THEN
                RAISE EXCEPTION 'master_audit_requires_empty_table';
            END IF;
        END $$;
    """))
    op.drop_table("master_audit")
    op.execute("DROP FUNCTION master_audit_append_only()")
