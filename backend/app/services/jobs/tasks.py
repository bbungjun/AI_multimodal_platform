from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.db import AsyncSessionLocal, close_db_connection
from app.models import Job, JobState
from app.services.jobs.handlers import handle as default_handler
from app.state_machine import TERMINAL_STATES, transition


JobHandler = Callable[[UUID], Awaitable[None]]
SessionFactory = Callable[[], AsyncSession]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessJobResult:
    job_id: UUID | None
    executed: bool
    reason: str


@celery_app.task(name="jobs.process_job", ignore_result=True)
def process_job(job_id: str) -> None:
    asyncio.run(_run_process_job_task(job_id))


async def _run_process_job_task(job_id: str) -> None:
    try:
        await process_job_async(job_id)
    finally:
        await close_db_connection()


async def process_job_async(
    job_id: str,
    *,
    session_factory: SessionFactory = AsyncSessionLocal,
    handler: JobHandler = default_handler,
) -> ProcessJobResult:
    try:
        parsed_job_id = UUID(job_id)
    except ValueError:
        logger.warning("Ignoring Celery job task with invalid UUID payload.")
        return ProcessJobResult(job_id=None, executed=False, reason="invalid_job_id")

    async with session_factory() as session:
        async with session.begin():
            result = await session.scalars(_claim_job_statement(parsed_job_id))
            job = result.first()
            if job is None:
                return ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="missing",
                )
            if job.state in TERMINAL_STATES:
                return ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="terminal",
                )
            if job.blocked:
                return ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="blocked",
                )
            if job.state != JobState.PENDING:
                return ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="not_pending",
                )

            transition(job, JobState.QUEUED, detail={"runner": "celery"})

    await handler(parsed_job_id)
    return ProcessJobResult(job_id=parsed_job_id, executed=True, reason="claimed")


def _claim_job_statement(job_id: UUID) -> Select[tuple[Job]]:
    return select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)
