"""Add immutable lifecycle command receipts; preserve all existing credit data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_credit_lifecycle_operations"
down_revision = "0004_credit_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("credit_operations",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_key", sa.String(96), nullable=False),
        sa.Column("kind", sa.String(11), nullable=False),
        sa.Column("target_plan", sa.String(4)),
        sa.Column("amount_microcredits", sa.BigInteger()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("rate_card_version", sa.String(10), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_grant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "operation_key", name="pk_credit_operations"),
        sa.ForeignKeyConstraint(["user_id"], ["credit_accounts.user_id"], name="fk_credit_operations_account", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_cycle_id", "user_id"], ["credit_cycles.id", "credit_cycles.user_id"], name="fk_credit_operations_cycle_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_grant_id", "user_id"], ["credit_grants.id", "credit_grants.user_id"], name="fk_credit_operations_grant_owner", ondelete="RESTRICT"),
        sa.CheckConstraint("operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_operations_key"),
        sa.CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_operations_version"),
        sa.CheckConstraint(
            "(kind = 'plan_change' AND target_plan IS NOT NULL AND target_plan IN ('free','pro','max') AND amount_microcredits IS NULL AND expires_at IS NULL AND reason_code IS NULL AND "
            "((outcome = 'upgraded' AND result_grant_id IS NOT NULL) OR (outcome IN ('scheduled','cancelled','unchanged') AND result_grant_id IS NULL))) OR "
            "(kind = 'bonus' AND target_plan IS NULL AND amount_microcredits IS NOT NULL AND amount_microcredits > 0 AND reason_code IS NOT NULL AND reason_code ~ '^[a-z0-9_]{1,64}$' AND "
            "(expires_at IS NULL OR expires_at > effective_at) AND outcome = 'granted' AND result_grant_id IS NOT NULL)",
            name="ck_credit_operations_shape"))
    op.create_index("ix_credit_operations_user_effective", "credit_operations", ["user_id", "effective_at"])
    op.execute("""CREATE FUNCTION credit_operation_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'credit_operation_append_only' USING ERRCODE = '23514';
        END $$""")
    op.execute("""CREATE TRIGGER credit_operation_no_row_mutation
        BEFORE UPDATE OR DELETE ON credit_operations FOR EACH ROW
        EXECUTE FUNCTION credit_operation_reject_mutation()""")
    op.execute("""CREATE TRIGGER credit_operation_no_truncate
        BEFORE TRUNCATE ON credit_operations FOR EACH STATEMENT
        EXECUTE FUNCTION credit_operation_reject_mutation()""")


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text("LOCK TABLE credit_operations IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM credit_operations)")).scalar():
        raise RuntimeError("credit_operations_requires_empty_table")
    op.drop_table("credit_operations")
    op.execute("DROP FUNCTION credit_operation_reject_mutation()")
