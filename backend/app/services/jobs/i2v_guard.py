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
ACTIVE_I2V_UNIQUE_INDEX_NAME = "uq_jobs_active_i2v_source_asset"
ACTIVE_I2V_STATE_SQL = ", ".join(f"'{state.value}'" for state in ACTIVE_I2V_STATES)

ACTIVE_I2V_DUPLICATE_SCAN_SQL = f"""
SELECT source_asset_id, COUNT(*) AS active_count
FROM jobs
WHERE mode = 'i2v'
  AND source_asset_id IS NOT NULL
  AND state IN ({ACTIVE_I2V_STATE_SQL})
GROUP BY source_asset_id
HAVING COUNT(*) > 1
LIMIT 1
"""

ACTIVE_I2V_UNIQUE_INDEX_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {ACTIVE_I2V_UNIQUE_INDEX_NAME}
ON jobs (source_asset_id)
WHERE mode = 'i2v'
  AND source_asset_id IS NOT NULL
  AND state IN ({ACTIVE_I2V_STATE_SQL})
"""


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


def is_active_i2v_unique_violation(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    text = str(exc)
    return (
        constraint_name == ACTIVE_I2V_UNIQUE_INDEX_NAME
        or ACTIVE_I2V_UNIQUE_INDEX_NAME in text
        or (orig is not None and ACTIVE_I2V_UNIQUE_INDEX_NAME in str(orig))
    )
