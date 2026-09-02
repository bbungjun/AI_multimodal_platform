"""Create the existing multimodal generation schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_generation_baseline"
down_revision = None
branch_labels = None
depends_on = None


generation_mode = postgresql.ENUM(
    "t2i", "t2v", "i2v", name="generation_mode", create_type=False
)
job_state = postgresql.ENUM(
    "pending",
    "enhancing",
    "queued",
    "generating",
    "polling",
    "downloading",
    "completed",
    "failed",
    "cancelled",
    name="job_state",
    create_type=False,
)
asset_kind = postgresql.ENUM(
    "image", "video", name="asset_kind", create_type=False
)
outbox_event_status = postgresql.ENUM(
    "pending", "published", "failed", name="outbox_event_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    generation_mode.create(bind, checkfirst=False)
    job_state.create(bind, checkfirst=False)
    asset_kind.create(bind, checkfirst=False)
    outbox_event_status.create(bind, checkfirst=False)

    op.create_table(
        "prompt_enhancements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("enhanced", sa.Text(), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_mode", generation_mode, nullable=False),
        sa.Column("target_model", sa.String(length=128), nullable=False),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", generation_mode, nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("state", job_state, nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("enhanced_prompt", sa.Text(), nullable=True),
        sa.Column("enhancement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retry_of_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("vertex_operation_name", sa.String(length=512), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state_history", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("vertex_charged", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["enhancement_id"],
            ["prompt_enhancements.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_job_id"],
            ["jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_job_id"],
            ["jobs.id"],
            name="fk_jobs_retry_of_job_id_jobs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_parent_job_id", "jobs", ["parent_job_id"])
    op.create_index("ix_jobs_retry_of_job_id", "jobs", ["retry_of_job_id"])
    op.create_index("ix_jobs_state", "jobs", ["state"])

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", asset_kind, nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_job_id", "assets", ["job_id"])
    op.create_foreign_key(
        "fk_jobs_source_asset_id_assets",
        "jobs",
        "assets",
        ["source_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_jobs_active_i2v_source_asset",
        "jobs",
        ["source_asset_id"],
        unique=True,
        postgresql_where=sa.text(
            "mode = 'i2v' AND source_asset_id IS NOT NULL AND "
            "state IN ('pending', 'enhancing', 'queued', 'generating', "
            "'polling', 'downloading')"
        ),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", outbox_event_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index(
        "ix_outbox_events_event_type_status",
        "outbox_events",
        ["event_type", "status"],
    )
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index(
        "ix_outbox_events_status_created_at",
        "outbox_events",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_index("uq_jobs_active_i2v_source_asset", table_name="jobs")
    op.drop_constraint(
        "fk_jobs_source_asset_id_assets", "jobs", type_="foreignkey"
    )
    op.drop_table("assets")
    op.drop_table("jobs")
    op.drop_table("prompt_enhancements")

    bind = op.get_bind()
    outbox_event_status.drop(bind, checkfirst=False)
    asset_kind.drop(bind, checkfirst=False)
    job_state.drop(bind, checkfirst=False)
    generation_mode.drop(bind, checkfirst=False)
