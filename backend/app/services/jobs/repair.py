from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import GenerationMode, Job, JobState
from app.services.jobs.enqueue import DispatchResult, dispatch_job, exception_code


Dispatcher = Callable[[UUID], Awaitable[DispatchResult]]
SessionFactory = Callable[[], AsyncSession]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepairResult:
    selected: int
    dispatched: int
    failed: int
    dispatch_results: tuple[DispatchResult, ...] = ()


async def reenqueue_pending_jobs(
    *,
    limit: int = 100,
    reason: str = "repair_pending",
    session_factory: SessionFactory = AsyncSessionLocal,
    dispatcher: Callable[..., Awaitable[DispatchResult]] = dispatch_job,
) -> RepairResult:
    return await _reenqueue_jobs(
        statement=_pending_unblocked_jobs_statement(limit=limit),
        reason=reason,
        session_factory=session_factory,
        dispatcher=dispatcher,
    )


async def reenqueue_resumable_polling_jobs(
    *,
    limit: int = 100,
    reason: str = "resume_polling",
    session_factory: SessionFactory = AsyncSessionLocal,
    dispatcher: Callable[..., Awaitable[DispatchResult]] = dispatch_job,
) -> RepairResult:
    return await _reenqueue_jobs(
        statement=_resumable_polling_jobs_statement(limit=limit),
        reason=reason,
        session_factory=session_factory,
        dispatcher=dispatcher,
    )


async def _reenqueue_jobs(
    *,
    statement: Select[tuple[Job]],
    reason: str,
    session_factory: SessionFactory,
    dispatcher: Callable[..., Awaitable[DispatchResult]],
) -> RepairResult:
    async with session_factory() as session:
        result = await session.scalars(statement)
        jobs = list(result.all())

    dispatched = 0
    failed = 0
    dispatch_results: list[DispatchResult] = []
    for job in jobs:
        try:
            dispatch_result = await dispatcher(job.id, reason=reason)
        except Exception as exc:
            dispatch_result = DispatchResult(
                job_id=job.id,
                reason=reason,
                mode="unknown",
                enqueued=False,
                error=str(exc) or exc.__class__.__name__,
                error_code=exception_code(exc),
            )
            logger.warning(
                "Repair dispatch failed for pending job %s: %s",
                job.id,
                dispatch_result.error,
            )
            failed += 1
            dispatch_results.append(dispatch_result)
            continue

        if dispatch_result.error and dispatch_result.error_code is None:
            dispatch_result = DispatchResult(
                job_id=dispatch_result.job_id,
                reason=dispatch_result.reason,
                mode=dispatch_result.mode,
                enqueued=dispatch_result.enqueued,
                queue=dispatch_result.queue,
                task_id=dispatch_result.task_id,
                error=dispatch_result.error,
                error_code=exception_code(dispatch_result.error),
            )

        dispatch_results.append(dispatch_result)
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
        dispatch_results=tuple(dispatch_results),
    )


def _pending_unblocked_jobs_statement(*, limit: int) -> Select[tuple[Job]]:
    return (
        select(Job)
        .where(Job.state == JobState.PENDING, Job.blocked.is_(False))
        .order_by(Job.created_at)
        .limit(limit)
    )


def _resumable_polling_jobs_statement(*, limit: int) -> Select[tuple[Job]]:
    return (
        select(Job)
        .where(
            Job.mode.in_((GenerationMode.T2V, GenerationMode.I2V)),
            Job.state == JobState.POLLING,
            Job.vertex_operation_name.is_not(None),
            Job.blocked.is_(False),
        )
        .order_by(Job.updated_at)
        .limit(limit)
    )
