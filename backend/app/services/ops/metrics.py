from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import GenerationMode, Job, JobState, OutboxEvent, OutboxEventStatus
from app.schemas import (
    OpsDispatchResponse,
    OpsHealthResponse,
    OpsJobsResponse,
    OpsOutboxResponse,
    OpsRecentFailureResponse,
)
from app.state_machine import NON_TERMINAL_STATES


EnumT = TypeVar("EnumT")


async def collect_ops_health(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    recent_failure_limit: int = 5,
) -> OpsHealthResponse:
    resolved_settings = settings or get_settings()

    job_counts = await _enum_counts(
        session,
        job_state_counts_statement(),
        enum_values=JobState,
    )
    outbox_counts = await _enum_counts(
        session,
        outbox_status_counts_statement(),
        enum_values=OutboxEventStatus,
    )
    resumable_polling = await _single_count(
        session,
        resumable_polling_jobs_count_statement(),
    )
    blocked = await _single_count(session, blocked_jobs_count_statement())
    recent_failures = await _recent_failures(session, limit=recent_failure_limit)

    active = sum(job_counts[state] for state in NON_TERMINAL_STATES)
    return OpsHealthResponse(
        ok=True,
        db="up",
        service=resolved_settings.app_name,
        dispatch=OpsDispatchResponse(
            mode=resolved_settings.job_dispatch_mode,
            queue=resolved_settings.celery_default_queue,
            task_acks_late=resolved_settings.celery_task_acks_late,
            task_reject_on_worker_lost=(
                resolved_settings.celery_task_reject_on_worker_lost
            ),
            worker_prefetch_multiplier=(
                resolved_settings.celery_worker_prefetch_multiplier
            ),
        ),
        jobs=OpsJobsResponse(
            total=sum(job_counts.values()),
            active=active,
            blocked=blocked,
            resumable_polling=resumable_polling,
            by_state=job_counts,
        ),
        outbox=OpsOutboxResponse(
            total=sum(outbox_counts.values()),
            pending=outbox_counts[OutboxEventStatus.PENDING],
            published=outbox_counts[OutboxEventStatus.PUBLISHED],
            failed=outbox_counts[OutboxEventStatus.FAILED],
            by_status=outbox_counts,
        ),
        recent_failures=recent_failures,
    )


def job_state_counts_statement() -> Select[tuple[JobState, int]]:
    return select(Job.state, func.count(Job.id)).group_by(Job.state)


def outbox_status_counts_statement() -> Select[tuple[OutboxEventStatus, int]]:
    return select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(
        OutboxEvent.status,
    )


def resumable_polling_jobs_count_statement() -> Select[tuple[int]]:
    return (
        select(func.count(Job.id))
        .where(
            Job.mode.in_((GenerationMode.T2V, GenerationMode.I2V)),
            Job.state == JobState.POLLING,
            Job.vertex_operation_name.is_not(None),
            Job.blocked.is_(False),
        )
    )


def blocked_jobs_count_statement() -> Select[tuple[int]]:
    return select(func.count(Job.id)).where(
        Job.state.in_(NON_TERMINAL_STATES),
        Job.blocked.is_(True),
    )


def recent_failure_jobs_statement(limit: int) -> Select[tuple[Job]]:
    return (
        select(Job)
        .where(Job.state == JobState.FAILED)
        .order_by(Job.updated_at.desc())
        .limit(max(1, limit))
    )


async def _enum_counts(
    session: AsyncSession,
    statement: Select[tuple[EnumT, int]],
    *,
    enum_values: type[EnumT],
) -> dict[EnumT, int]:
    result = await session.execute(statement)
    counts = {value: 0 for value in enum_values}
    for raw_key, raw_count in result.all():
        key = raw_key if isinstance(raw_key, enum_values) else enum_values(raw_key)
        counts[key] = int(raw_count or 0)
    return counts


async def _single_count(session: AsyncSession, statement: Select[tuple[int]]) -> int:
    result = await session.execute(statement)
    return int(result.scalar_one() or 0)


async def _recent_failures(
    session: AsyncSession,
    *,
    limit: int,
) -> list[OpsRecentFailureResponse]:
    result = await session.scalars(recent_failure_jobs_statement(limit))
    return [_failure_response(job) for job in result.all()]


def _failure_response(job: Job) -> OpsRecentFailureResponse:
    error = job.error or {}
    return OpsRecentFailureResponse(
        id=job.id,
        mode=job.mode,
        model=job.model,
        code=_string_or_none(error.get("code")),
        message=_string_or_none(error.get("message")),
        retryable=_bool_or_none(error.get("retryable")),
        dead_letter=error.get("dead_letter") is True,
        updated_at=job.updated_at,
    )


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
