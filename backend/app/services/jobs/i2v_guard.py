from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select

from app.models import Asset, GenerationMode, Job, JobState


ACTIVE_I2V_STATES: tuple[JobState, ...] = (
    JobState.PENDING,
    JobState.ENHANCING,
    JobState.QUEUED,
    JobState.GENERATING,
    JobState.POLLING,
    JobState.DOWNLOADING,
)

ACTIVE_I2V_DUPLICATE_MESSAGE = (
    "An active I2V generation already exists for this source asset."
)


def source_asset_for_update_statement(source_asset_id: UUID) -> Select[tuple[Asset]]:
    return select(Asset).where(Asset.id == source_asset_id).with_for_update()


def active_i2v_job_statement(source_asset_id: UUID) -> Select[tuple[Job]]:
    return (
        select(Job)
        .where(
            Job.mode == GenerationMode.I2V,
            Job.source_asset_id == source_asset_id,
            Job.state.in_(ACTIVE_I2V_STATES),
        )
        .order_by(Job.updated_at.desc())
        .limit(1)
    )
