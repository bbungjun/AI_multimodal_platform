"""Add credit persistence without creating accounts or issuing credit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_credit_foundation"
down_revision = "0003_content_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("credit_accounts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_anchor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan", sa.String(4), nullable=False),
        sa.Column("pending_plan", sa.String(4)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_credit_accounts"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_credit_accounts_user", ondelete="RESTRICT"),
        sa.CheckConstraint("plan IN ('free','pro','max')", name="ck_credit_accounts_plan"),
        sa.CheckConstraint("pending_plan IS NULL OR (pending_plan IN ('free','pro','max') AND pending_plan <> plan)", name="ck_credit_accounts_pending_plan"),
        sa.CheckConstraint("updated_at >= created_at AND created_at >= cycle_anchor_at", name="ck_credit_accounts_time"))
    op.create_table("credit_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_index", sa.BigInteger(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan", sa.String(4), nullable=False),
        sa.Column("allowance_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_credit_cycles"),
        sa.ForeignKeyConstraint(["user_id"], ["credit_accounts.user_id"], name="fk_credit_cycles_account", ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "cycle_index", name="uq_credit_cycles_user_index"),
        sa.UniqueConstraint("id", "user_id", name="uq_credit_cycles_id_user"),
        sa.CheckConstraint("cycle_index >= 0", name="ck_credit_cycles_index"),
        sa.CheckConstraint("extract(epoch FROM (ends_at - starts_at)) = 2592000 AND created_at >= starts_at", name="ck_credit_cycles_time"),
        sa.CheckConstraint("plan IN ('free','pro','max')", name="ck_credit_cycles_plan"),
        sa.CheckConstraint("allowance_microcredits >= 0", name="ck_credit_cycles_allowance"))
    op.create_index("ix_credit_cycles_user_start", "credit_cycles", ["user_id", "starts_at", "id"])
    op.create_table("credit_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(5), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("granted_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("reserved_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("consumed_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("expired_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_credit_grants"),
        sa.ForeignKeyConstraint(["user_id"], ["credit_accounts.user_id"], name="fk_credit_grants_account", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cycle_id", "user_id"], ["credit_cycles.id", "credit_cycles.user_id"], name="fk_credit_grants_cycle_owner", ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "user_id", name="uq_credit_grants_id_user"),
        sa.CheckConstraint("(kind = 'base' AND cycle_id IS NOT NULL AND expires_at IS NOT NULL) OR (kind = 'bonus' AND cycle_id IS NULL)", name="ck_credit_grants_kind"),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > created_at", name="ck_credit_grants_expiry"),
        sa.CheckConstraint("granted_microcredits >= 0 AND reserved_microcredits >= 0 AND consumed_microcredits >= 0 AND expired_microcredits >= 0", name="ck_credit_grants_nonnegative"),
        sa.CheckConstraint("reserved_microcredits::numeric + consumed_microcredits::numeric + expired_microcredits::numeric <= granted_microcredits", name="ck_credit_grants_balance"),
        sa.CheckConstraint("reason_code ~ '^[a-z0-9_]{1,64}$'", name="ck_credit_grants_reason"))
    op.create_index("uq_credit_grants_base_cycle", "credit_grants", ["cycle_id"], unique=True, postgresql_where=sa.text("kind = 'base'"))
    op.create_index("ix_credit_grants_user_expiry", "credit_grants", ["user_id", "expires_at", "id"])
    op.create_table("credit_ledger_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(7), nullable=False),
        sa.Column("operation_key", sa.String(128), nullable=False),
        sa.Column("rate_card_version", sa.String(10), nullable=False),
        sa.Column("granted_delta", sa.BigInteger(), nullable=False),
        sa.Column("reserved_delta", sa.BigInteger(), nullable=False),
        sa.Column("consumed_delta", sa.BigInteger(), nullable=False),
        sa.Column("expired_delta", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_credit_ledger_events"),
        sa.ForeignKeyConstraint(["user_id"], ["credit_accounts.user_id"], name="fk_credit_ledger_account", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grant_id", "user_id"], ["credit_grants.id", "credit_grants.user_id"], name="fk_credit_ledger_grant_owner", ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "operation_key", "grant_id", "kind", name="uq_credit_ledger_operation"),
        sa.CheckConstraint("operation_key ~ '^[A-Za-z0-9_-]{1,128}$'", name="ck_credit_ledger_operation_key"),
        sa.CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_ledger_version"),
        sa.CheckConstraint("reason_code ~ '^[a-z0-9_]{1,64}$'", name="ck_credit_ledger_reason"),
        sa.CheckConstraint(
            "(kind IN ('grant','adjust') AND granted_delta > 0 AND reserved_delta = 0 AND consumed_delta = 0 AND expired_delta = 0) OR "
            "(kind = 'reserve' AND granted_delta = 0 AND reserved_delta > 0 AND consumed_delta = 0 AND expired_delta = 0) OR "
            "(kind = 'settle' AND granted_delta = 0 AND reserved_delta < 0 AND consumed_delta >= 0 AND expired_delta >= 0 AND consumed_delta::numeric + expired_delta::numeric <= -reserved_delta::numeric) OR "
            "(kind = 'release' AND granted_delta = 0 AND reserved_delta < 0 AND consumed_delta = 0 AND expired_delta >= 0 AND expired_delta::numeric <= -reserved_delta::numeric) OR "
            "(kind = 'expire' AND granted_delta = 0 AND reserved_delta = 0 AND consumed_delta = 0 AND expired_delta > 0)", name="ck_credit_ledger_shape"))
    op.create_index("ix_credit_ledger_user_created", "credit_ledger_events", ["user_id", "created_at", "id"])
    op.execute("""CREATE FUNCTION credit_ledger_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'credit_ledger_append_only' USING ERRCODE = '23514';
        END $$""")
    op.execute("""CREATE TRIGGER credit_ledger_no_row_mutation
        BEFORE UPDATE OR DELETE ON credit_ledger_events
        FOR EACH ROW EXECUTE FUNCTION credit_ledger_reject_mutation()""")
    op.execute("""CREATE TRIGGER credit_ledger_no_truncate
        BEFORE TRUNCATE ON credit_ledger_events
        FOR EACH STATEMENT EXECUTE FUNCTION credit_ledger_reject_mutation()""")


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text("LOCK TABLE credit_accounts, credit_cycles, credit_grants, credit_ledger_events IN ACCESS EXCLUSIVE MODE"))
    for table in ("credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("credit_foundation_requires_empty_tables")
    for table in ("credit_ledger_events", "credit_grants", "credit_cycles", "credit_accounts"):
        op.drop_table(table)
    op.execute("DROP FUNCTION credit_ledger_reject_mutation()")
