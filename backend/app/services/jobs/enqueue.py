from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.config import Settings, get_settings


logger = logging.getLogger(__name__)


class ProcessJobTask(Protocol):
    def apply_async(self, args=None, kwargs=None, **options): ...


@dataclass(frozen=True)
class DispatchResult:
    job_id: UUID
    reason: str
    mode: str
    enqueued: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


async def dispatch_job(
    job_id: UUID,
    *,
    reason: str,
    settings: Settings | None = None,
    process_job_task: ProcessJobTask | None = None,
) -> DispatchResult:
    resolved_settings = settings or get_settings()
    mode = resolved_settings.job_dispatch_mode.lower()

    if mode == "polling":
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode=mode,
            enqueued=False,
        )

    if mode != "celery":
        error = f"Unsupported job dispatch mode: {resolved_settings.job_dispatch_mode}"
        logger.warning("Job %s dispatch skipped: %s", job_id, error)
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode=mode,
            enqueued=False,
            error=error,
        )

    task = process_job_task or _process_job_task()
    try:
        task.apply_async(
            args=(str(job_id),),
            kwargs={},
            queue=resolved_settings.celery_default_queue,
        )
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        logger.warning(
            "Failed to dispatch job %s via Celery for %s: %s",
            job_id,
            reason,
            error,
        )
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode=mode,
            enqueued=False,
            error=error,
        )

    return DispatchResult(
        job_id=job_id,
        reason=reason,
        mode=mode,
        enqueued=True,
    )


async def dispatch_jobs(
    job_ids: Iterable[UUID],
    *,
    reason: str,
    settings: Settings | None = None,
) -> list[DispatchResult]:
    return [
        await dispatch_job(job_id, reason=reason, settings=settings)
        for job_id in job_ids
    ]


def _process_job_task() -> ProcessJobTask:
    from app.services.jobs.tasks import process_job

    return process_job
