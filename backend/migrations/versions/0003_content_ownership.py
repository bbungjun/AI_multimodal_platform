"""Persist explicit content ownership on an empty generation schema only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_content_ownership"
down_revision = "0002_user_session_persistence"
branch_labels = None
depends_on = None


def _require_empty_generation_tables() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text(
        "LOCK TABLE jobs, assets, prompt_enhancements, outbox_events IN ACCESS EXCLUSIVE MODE"
    ))
    for table in ("jobs", "assets", "prompt_enhancements", "outbox_events"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("content_ownership_requires_empty_generation_tables")


def upgrade() -> None:
    _require_empty_generation_tables()
    for table in ("jobs", "prompt_enhancements"):
        op.add_column(table, sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False))
        op.create_foreign_key(f"fk_{table}_owner_user_id_users", table, "users",
                              ["owner_user_id"], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_owner_created_at_id", table,
                        ["owner_user_id", "created_at", "id"])
    op.create_unique_constraint("uq_assets_local_path", "assets", ["local_path"])


def downgrade() -> None:
    _require_empty_generation_tables()
    op.drop_constraint("uq_assets_local_path", "assets", type_="unique")
    for table in ("prompt_enhancements", "jobs"):
        op.drop_index(f"ix_{table}_owner_created_at_id", table_name=table)
        op.drop_constraint(f"fk_{table}_owner_user_id_users", table, type_="foreignkey")
        op.drop_column(table, "owner_user_id")
