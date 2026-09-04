"""Add empty reservation/allocation/usage persistence; no accounting writers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_credit_accounting_persistence"
down_revision = "0005_credit_lifecycle_operations"
branch_labels = None
depends_on = None

TABLES = (
    "credit_reservations",
    "credit_reservation_items",
    "credit_reservation_allocations",
    "credit_usage_records",
)


def upgrade() -> None:
    op.create_table("credit_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reserve_operation_key", sa.String(96), nullable=False),
        sa.Column("rate_card_version", sa.String(10), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("reserved_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_operation_key", sa.String(96)),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.Column("terminal_reason_code", sa.String(64)),
        sa.Column("delivery", sa.String(14)),
        sa.PrimaryKeyConstraint("id", name="pk_credit_reservations"),
        sa.UniqueConstraint("id", "user_id", name="uq_credit_reservations_id_user"),
        sa.UniqueConstraint("user_id", "reserve_operation_key", name="uq_credit_reservations_user_reserve_key"),
        sa.ForeignKeyConstraint(["user_id"], ["credit_accounts.user_id"], name="fk_credit_reservations_account", ondelete="RESTRICT"),
        sa.CheckConstraint("reserve_operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_reservations_reserve_key"),
        sa.CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_reservations_version"),
        sa.CheckConstraint("reserved_microcredits > 0", name="ck_credit_reservations_amount"),
        sa.CheckConstraint("terminal_operation_key IS NULL OR terminal_operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_reservations_terminal_key"),
        sa.CheckConstraint("terminal_reason_code IS NULL OR terminal_reason_code ~ '^[a-z0-9_]{1,64}$'", name="ck_credit_reservations_reason"),
        sa.CheckConstraint(
            "(status = 'held' AND terminal_operation_key IS NULL AND terminal_at IS NULL AND terminal_reason_code IS NULL AND delivery IS NULL) OR "
            "(status = 'settled' AND terminal_operation_key IS NOT NULL AND terminal_at IS NOT NULL AND terminal_at >= created_at AND terminal_reason_code IS NOT NULL AND delivery IN ('delivered','partial')) OR "
            "(status = 'released' AND terminal_operation_key IS NOT NULL AND terminal_at IS NOT NULL AND terminal_at >= created_at AND terminal_reason_code IS NOT NULL AND delivery = 'no_deliverable')",
            name="ck_credit_reservations_terminal_shape"))
    op.create_index("uq_credit_reservations_user_terminal_key", "credit_reservations", ["user_id", "terminal_operation_key"], unique=True,
                    postgresql_where=sa.text("terminal_operation_key IS NOT NULL"))
    op.create_index("ix_credit_reservations_user_status_created", "credit_reservations", ["user_id", "status", "created_at", "id"])

    op.create_table("credit_reservation_items",
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meter", sa.String(32), nullable=False),
        sa.Column("maximum_units", sa.BigInteger(), nullable=False),
        sa.Column("quoted_microcredits", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("reservation_id", "meter", name="pk_credit_reservation_items"),
        sa.UniqueConstraint("reservation_id", "user_id", "meter", name="uq_credit_reservation_items_owner_meter"),
        sa.ForeignKeyConstraint(["reservation_id", "user_id"], ["credit_reservations.id", "credit_reservations.user_id"], name="fk_credit_reservation_items_owner", ondelete="RESTRICT"),
        sa.CheckConstraint("meter IN ('gemini_input_token','gemini_output_token','imagen_fast_image','imagen_standard_image','imagen_ultra_image','veo_fast_ms','veo_standard_ms')", name="ck_credit_reservation_items_meter"),
        sa.CheckConstraint("maximum_units > 0 AND quoted_microcredits > 0", name="ck_credit_reservation_items_amounts"))
    op.create_index("ix_credit_reservation_items_user_reservation", "credit_reservation_items", ["user_id", "reservation_id"])

    op.create_table("credit_reservation_allocations",
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False),
        sa.Column("reserved_microcredits", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("reservation_id", "grant_id", name="pk_credit_reservation_allocations"),
        sa.UniqueConstraint("reservation_id", "ordinal", name="uq_credit_reservation_allocations_ordinal"),
        sa.ForeignKeyConstraint(["reservation_id", "user_id"], ["credit_reservations.id", "credit_reservations.user_id"], name="fk_credit_reservation_allocations_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grant_id", "user_id"], ["credit_grants.id", "credit_grants.user_id"], name="fk_credit_reservation_allocations_grant_owner", ondelete="RESTRICT"),
        sa.CheckConstraint("ordinal >= 0", name="ck_credit_reservation_allocations_ordinal"),
        sa.CheckConstraint("reserved_microcredits > 0", name="ck_credit_reservation_allocations_amount"))
    op.create_index("ix_credit_reservation_allocations_grant_reservation", "credit_reservation_allocations", ["grant_id", "reservation_id"])

    op.create_table("credit_usage_records",
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meter", sa.String(32), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("terminal_operation_key", sa.String(96), nullable=False),
        sa.Column("rate_card_version", sa.String(10), nullable=False),
        sa.Column("actual_units", sa.BigInteger(), nullable=False),
        sa.Column("charged_microcredits", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("delivery", sa.String(14), nullable=False),
        sa.PrimaryKeyConstraint("reservation_id", "meter", name="pk_credit_usage_records"),
        sa.UniqueConstraint("user_id", "terminal_operation_key", "meter", name="uq_credit_usage_records_user_terminal_meter"),
        sa.ForeignKeyConstraint(["reservation_id", "user_id", "meter"], ["credit_reservation_items.reservation_id", "credit_reservation_items.user_id", "credit_reservation_items.meter"], name="fk_credit_usage_records_item_owner", ondelete="RESTRICT"),
        sa.CheckConstraint("terminal_operation_key ~ '^[A-Za-z0-9_-]{1,96}$'", name="ck_credit_usage_records_terminal_key"),
        sa.CheckConstraint("rate_card_version ~ '^v[1-9][0-9]{0,8}$'", name="ck_credit_usage_records_version"),
        sa.CheckConstraint("actual_units >= 0 AND charged_microcredits >= 0", name="ck_credit_usage_records_amounts"),
        sa.CheckConstraint("source IN ('provider_reported','platform_measured','mock_estimate','estimated')", name="ck_credit_usage_records_source"),
        sa.CheckConstraint("(delivery IN ('delivered','partial')) OR (delivery = 'no_deliverable' AND charged_microcredits = 0)", name="ck_credit_usage_records_delivery"))
    op.create_index("ix_credit_usage_records_user_recorded", "credit_usage_records", ["user_id", "recorded_at", "reservation_id"])

    op.execute("""CREATE FUNCTION credit_reservation_guard_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') OR OLD.status <> 'held' OR NEW.status NOT IN ('settled','released')
           OR ROW(NEW.id, NEW.user_id, NEW.reserve_operation_key, NEW.rate_card_version,
                  NEW.reserved_microcredits, NEW.created_at)
              IS DISTINCT FROM
              ROW(OLD.id, OLD.user_id, OLD.reserve_operation_key, OLD.rate_card_version,
                  OLD.reserved_microcredits, OLD.created_at) THEN
            RAISE EXCEPTION 'credit_reservation_immutable' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER credit_reservation_no_row_mutation
        BEFORE UPDATE OR DELETE ON credit_reservations FOR EACH ROW
        EXECUTE FUNCTION credit_reservation_guard_mutation()""")
    op.execute("""CREATE FUNCTION credit_accounting_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'credit_accounting_append_only' USING ERRCODE = '23514';
        END $$""")
    for table in TABLES[1:]:
        op.execute(f"""CREATE TRIGGER {table}_no_row_mutation
            BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW
            EXECUTE FUNCTION credit_accounting_reject_mutation()""")
    for table in TABLES:
        function = "credit_reservation_guard_mutation" if table == "credit_reservations" else "credit_accounting_reject_mutation"
        op.execute(f"""CREATE TRIGGER {table}_no_truncate
            BEFORE TRUNCATE ON {table} FOR EACH STATEMENT
            EXECUTE FUNCTION {function}()""")


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text(
        "LOCK TABLE credit_usage_records, credit_reservation_allocations, "
        "credit_reservation_items, credit_reservations IN ACCESS EXCLUSIVE MODE"))
    populated = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM credit_reservations "
        "UNION ALL SELECT 1 FROM credit_reservation_items "
        "UNION ALL SELECT 1 FROM credit_reservation_allocations "
        "UNION ALL SELECT 1 FROM credit_usage_records)"))
    if populated.scalar():
        raise RuntimeError("credit_accounting_requires_empty_tables")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION credit_accounting_reject_mutation()")
    op.execute("DROP FUNCTION credit_reservation_guard_mutation()")
