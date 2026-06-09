from __future__ import annotations

import logging
import re
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
    queue: str | None = None
    task_id: str | None = None
    error: str | None = None
    error_code: str | None = None

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
        result = DispatchResult(
            job_id=job_id,
            reason=reason,
            mode=mode,
            enqueued=False,
        )
        _log_dispatch_result(result)
        return result

    if mode != "celery":
        error = f"Unsupported job dispatch mode: {resolved_settings.job_dispatch_mode}"
        result = DispatchResult(
            job_id=job_id,
            reason=reason,
            mode=mode,
            enqueued=False,
            error=error,
            error_code="unsupported_dispatch_mode",
        )
        _log_dispatch_result(result)
        return result

    task = process_job_task or _process_job_task()
    queue = resolved_settings.celery_default_queue
    try:
        celery_result = task.apply_async(
            args=(str(job_id),),
            kwargs={},
            queue=queue,
        )
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        result = DispatchResult(
            job_id=job_id,
            reason=reason,
            mode=mode,
            enqueued=False,
            queue=queue,
            error=error,
            error_code=exception_code(exc),
        )
        _log_dispatch_result(result)
        return result

    task_id = getattr(celery_result, "id", None)
    result = DispatchResult(
        job_id=job_id,
        reason=reason,
        mode=mode,
        enqueued=True,
        queue=queue,
        task_id=str(task_id) if task_id else None,
    )
    _log_dispatch_result(result)
    return result


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


def _log_dispatch_result(result: DispatchResult) -> None:
    status = "enqueued" if result.enqueued else "skipped"
    if not result.ok:
        status = "failed"

    extra = {
        "job_id": str(result.job_id),
        "dispatch_reason": result.reason,
        "dispatch_mode": result.mode,
        "dispatch_queue": result.queue,
        "celery_task_id": result.task_id,
        "dispatch_status": status,
        "dispatch_error_code": result.error_code,
        "dispatch_error": result.error,
    }
    if result.ok:
        logger.info("Job dispatch completed.", extra=extra)
    else:
        logger.warning("Job dispatch failed.", extra=extra)


def exception_code(exc: Exception | str) -> str:
    if isinstance(exc, str):
        return _snake_case(exc)
    name = exc.__class__.__name__
    return _snake_case(name)


def _snake_case(value: str) -> str:
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    second_pass = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass)
    return re.sub(r"[^a-zA-Z0-9]+", "_", second_pass).strip("_").lower()
