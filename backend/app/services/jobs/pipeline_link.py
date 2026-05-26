from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, AssetKind, GenerationMode, Job, JobState
from app.state_machine import TERMINAL_STATES, transition


PIPELINE_SOURCE_ASSET_MISSING = "pipeline_source_asset_missing"
PIPELINE_SOURCE_ASSET_NOT_IMAGE = "pipeline_source_asset_not_image"
PIPELINE_PARENT_FAILED = "pipeline_parent_failed"


@dataclass(frozen=True)
class PipelineLinkResult:
    linked: bool
    reason: str | None = None
    child_id: UUID | None = None
    source_asset_id: UUID | None = None


async def link_completed_parent(
    session: AsyncSession,
    parent: Job,
) -> PipelineLinkResult:
    if parent.mode != GenerationMode.T2I:
        return PipelineLinkResult(linked=False, reason="parent_not_t2i")
    if parent.state != JobState.COMPLETED:
        return PipelineLinkResult(linked=False, reason="parent_not_completed")

    child = await _first_pipeline_child(session, parent.id)
    if child is None:
        return PipelineLinkResult(linked=False, reason="child_missing")
    if child.state in TERMINAL_STATES:
        return PipelineLinkResult(
            linked=False,
            reason="child_terminal",
            child_id=child.id,
        )
    if child.state != JobState.PENDING:
        return PipelineLinkResult(
            linked=False,
            reason="child_not_pending",
            child_id=child.id,
        )

    asset = await _first_parent_asset(session, parent.id)
    if asset is None:
        await _fail_child(
            session,
            child,
            code=PIPELINE_SOURCE_ASSET_MISSING,
            message="Pipeline parent completed without an image asset.",
        )
        return PipelineLinkResult(
            linked=False,
            reason="source_asset_missing",
            child_id=child.id,
        )
    if asset.kind != AssetKind.IMAGE:
        await _fail_child(
            session,
            child,
            code=PIPELINE_SOURCE_ASSET_NOT_IMAGE,
            message="Pipeline parent output asset must be an image.",
        )
        return PipelineLinkResult(
            linked=False,
            reason="source_asset_not_image",
            child_id=child.id,
        )

    child.source_asset_id = asset.id
    child.blocked = False
    await session.commit()
    return PipelineLinkResult(
        linked=True,
        child_id=child.id,
        source_asset_id=asset.id,
    )


async def fail_blocked_children_for_parent(
    session: AsyncSession,
    parent: Job,
) -> int:
    children = await _pipeline_children(session, parent.id)
    failed = 0
    for child in children:
        if not child.blocked or child.state in TERMINAL_STATES:
            continue
        child.error = {
            "code": PIPELINE_PARENT_FAILED,
            "message": "Pipeline parent generation failed.",
            "retryable": False,
            "cause": "parent_failed",
        }
        transition(
            child,
            JobState.FAILED,
            detail={"error": PIPELINE_PARENT_FAILED, "cause": "parent_failed"},
        )
        failed += 1

    if failed:
        await session.commit()
    return failed


async def _first_pipeline_child(session: AsyncSession, parent_id: UUID) -> Job | None:
    children = await _pipeline_children(session, parent_id)
    return children[0] if children else None


async def _pipeline_children(session: AsyncSession, parent_id: UUID) -> list[Job]:
    statement = (
        select(Job)
        .where(
            Job.parent_job_id == parent_id,
            Job.mode == GenerationMode.I2V,
        )
        .order_by(Job.created_at, Job.id)
    )
    result = await session.scalars(statement)
    return list(result.all())


async def _first_parent_asset(session: AsyncSession, parent_id: UUID) -> Asset | None:
    statement = (
        select(Asset)
        .where(Asset.job_id == parent_id)
        .order_by(Asset.created_at, Asset.id)
    )
    result = await session.scalars(statement)
    assets = list(result.all())
    return assets[0] if assets else None


async def _fail_child(
    session: AsyncSession,
    child: Job,
    *,
    code: str,
    message: str,
) -> None:
    child.error = {
        "code": code,
        "message": message,
        "retryable": False,
    }
    transition(child, JobState.FAILED, detail={"error": code})
    await session.commit()
