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
from app.models import GenerationMode, Job, JobState
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
    previous_state: str | None = None
    claimed_state: str | None = None


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
        result = ProcessJobResult(
            job_id=None,
            executed=False,
            reason="invalid_job_id",
        )
        _log_process_job_result(result)
        return result

    async with session_factory() as session:
        async with session.begin():
            result = await session.scalars(_claim_job_statement(parsed_job_id))
            job = result.first()
            if job is None:
                process_result = ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="missing",
                )
                _log_process_job_result(process_result)
                return process_result
            previous_state = job.state.value
            if job.state in TERMINAL_STATES:
                process_result = ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="terminal",
                    previous_state=previous_state,
                )
                _log_process_job_result(process_result)
                return process_result
            if job.blocked:
                process_result = ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="blocked",
                    previous_state=previous_state,
                )
                _log_process_job_result(process_result)
                return process_result
            if _is_resumable_polling_job(job):
                process_result = ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=True,
                    reason="resumed_polling",
                    previous_state=previous_state,
                    claimed_state=JobState.POLLING.value,
                )
            elif job.state != JobState.PENDING:
                process_result = ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=False,
                    reason="not_pending",
                    previous_state=previous_state,
                )
                _log_process_job_result(process_result)
                return process_result
            else:
                transition(job, JobState.QUEUED, detail={"runner": "celery"})
                process_result = ProcessJobResult(
                    job_id=parsed_job_id,
                    executed=True,
                    reason="claimed",
                    previous_state=previous_state,
                    claimed_state=JobState.QUEUED.value,
                )

    await handler(parsed_job_id)
    _log_process_job_result(process_result)
    return process_result


def _claim_job_statement(job_id: UUID) -> Select[tuple[Job]]:
    return select(Job).where(Job.id == job_id).with_for_update(skip_locked=True)


def _is_resumable_polling_job(job: Job) -> bool:
    return (
        job.mode in {GenerationMode.T2V, GenerationMode.I2V}
        and job.state == JobState.POLLING
        and bool(job.vertex_operation_name)
    )


def _log_process_job_result(result: ProcessJobResult) -> None:
    extra = {
        "job_id": None if result.job_id is None else str(result.job_id),
        "task_result_reason": result.reason,
        "previous_state": result.previous_state,
        "claimed_state": result.claimed_state,
        "task_executed": result.executed,
    }
    logger.info("Celery job task completed.", extra=extra)
