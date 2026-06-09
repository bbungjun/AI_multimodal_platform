from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import Job, JobState
from app.services.jobs.enqueue import DispatchResult, dispatch_job


Dispatcher = Callable[[UUID], Awaitable[DispatchResult]]
SessionFactory = Callable[[], AsyncSession]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepairResult:
    selected: int
    dispatched: int
    failed: int


async def reenqueue_pending_jobs(
    *,
    limit: int = 100,
    reason: str = "repair_pending",
    session_factory: SessionFactory = AsyncSessionLocal,
    dispatcher: Callable[..., Awaitable[DispatchResult]] = dispatch_job,
) -> RepairResult:
    async with session_factory() as session:
        result = await session.scalars(_pending_unblocked_jobs_statement(limit=limit))
        jobs = list(result.all())

    dispatched = 0
    failed = 0
    for job in jobs:
        try:
            dispatch_result = await dispatcher(job.id, reason=reason)
        except Exception as exc:
            logger.warning("Repair dispatch failed for pending job %s: %s", job.id, exc)
            failed += 1
            continue

        if dispatch_result.ok:
            dispatched += 1
        else:
            logger.warning(
                "Repair dispatch reported failure for pending job %s: %s",
                job.id,
                dispatch_result.error,
            )
            failed += 1

    return RepairResult(
        selected=len(jobs),
        dispatched=dispatched,
        failed=failed,
    )


def _pending_unblocked_jobs_statement(*, limit: int) -> Select[tuple[Job]]:
    return (
        select(Job)
        .where(Job.state == JobState.PENDING, Job.blocked.is_(False))
        .order_by(Job.created_at)
        .limit(limit)
    )
