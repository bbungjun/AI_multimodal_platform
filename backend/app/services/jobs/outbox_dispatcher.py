from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import AsyncSessionLocal, close_db_connection, init_db_schema
from app.models import OutboxEvent, OutboxEventStatus, utc_now
from app.services.jobs.enqueue import DispatchResult, dispatch_job, exception_code
from app.services.jobs.outbox import pending_job_dispatch_events_statement


Dispatcher = Callable[..., Awaitable[DispatchResult]]
SessionFactory = Callable[[], AsyncSession]
SchemaInitializer = Callable[[], Awaitable[None]]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxEventDispatchResult:
    event_id: UUID
    job_id: UUID | None
    reason: str | None
    published: bool
    status: str
    error_code: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class OutboxBatchResult:
    selected: int
    published: int
    failed: int
    pending: int
    event_results: tuple[OutboxEventDispatchResult, ...] = ()


class InvalidOutboxPayloadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def dispatch_pending_events(
    *,
    limit: int,
    session_factory: SessionFactory = AsyncSessionLocal,
    dispatcher: Dispatcher = dispatch_job,
    max_attempts: int = 10,
) -> OutboxBatchResult:
    resolved_limit = max(1, limit)
    resolved_max_attempts = max(1, max_attempts)
    async with session_factory() as session:
        result = await session.scalars(
            pending_job_dispatch_events_statement(limit=resolved_limit)
        )
        events = list(result.all())
        event_results = [
            await _dispatch_event(
                event,
                dispatcher=dispatcher,
                max_attempts=resolved_max_attempts,
            )
            for event in events
        ]
        await session.commit()

    batch_result = OutboxBatchResult(
        selected=len(events),
        published=sum(1 for item in event_results if item.published),
        failed=sum(1 for item in event_results if item.error_code is not None),
        pending=sum(1 for event in events if event.status == OutboxEventStatus.PENDING),
        event_results=tuple(event_results),
    )
    _log_batch_result(batch_result)
    return batch_result


async def run_dispatcher_loop(
    *,
    settings: Settings | None = None,
    once: bool = False,
    session_factory: SessionFactory = AsyncSessionLocal,
    dispatcher: Dispatcher = dispatch_job,
    initialize_schema: SchemaInitializer = init_db_schema,
) -> None:
    resolved_settings = settings or get_settings()
    await initialize_schema()
    while True:
        await dispatch_pending_events(
            limit=resolved_settings.outbox_dispatcher_batch_size,
            session_factory=session_factory,
            dispatcher=dispatcher,
            max_attempts=resolved_settings.outbox_dispatcher_max_attempts,
        )
        if once:
            return
        await asyncio.sleep(resolved_settings.outbox_dispatcher_poll_interval_sec)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch pending outbox job events to the configured job queue.",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    try:
        asyncio.run(_run_main(once=args.once))
    except KeyboardInterrupt:
        logger.info("Outbox dispatcher interrupted.")
        return 130
    return 0


async def _run_main(*, once: bool) -> None:
    try:
        await run_dispatcher_loop(once=once)
    finally:
        await close_db_connection()


async def _dispatch_event(
    event: OutboxEvent,
    *,
    dispatcher: Dispatcher,
    max_attempts: int,
) -> OutboxEventDispatchResult:
    event.attempts = int(event.attempts or 0) + 1
    event.updated_at = utc_now()

    try:
        job_id, reason = _job_dispatch_payload(event)
    except InvalidOutboxPayloadError as exc:
        _mark_failed(
            event,
            code=exc.code,
            message=str(exc),
            retryable=False,
            max_attempts=max_attempts,
        )
        return _result_from_event(event, job_id=None, reason=None, error_code=exc.code)

    try:
        dispatch_result = await dispatcher(job_id, reason=reason)
    except Exception as exc:
        _record_dispatch_failure(
            event,
            code=exception_code(exc),
            message=str(exc) or exc.__class__.__name__,
            max_attempts=max_attempts,
        )
        return _result_from_event(
            event,
            job_id=job_id,
            reason=reason,
            error_code=exception_code(exc),
        )

    if dispatch_result.ok:
        event.status = OutboxEventStatus.PUBLISHED
        event.published_at = utc_now()
        event.last_error = None
        event.updated_at = event.published_at
        return _result_from_event(event, job_id=job_id, reason=reason)

    code = dispatch_result.error_code or exception_code(
        dispatch_result.error or "dispatch_failed"
    )
    _record_dispatch_failure(
        event,
        code=code,
        message=dispatch_result.error or "Dispatch failed.",
        max_attempts=max_attempts,
    )
    return _result_from_event(
        event,
        job_id=job_id,
        reason=reason,
        error_code=code,
    )


def _job_dispatch_payload(event: OutboxEvent) -> tuple[UUID, str]:
    payload = event.payload or {}
    raw_job_id = payload.get("job_id")
    try:
        job_id = UUID(str(raw_job_id))
    except (TypeError, ValueError) as exc:
        raise InvalidOutboxPayloadError(
            "invalid_payload",
            "Outbox event payload has invalid job_id.",
        ) from exc

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidOutboxPayloadError(
            "invalid_payload",
            "Outbox event payload has invalid reason.",
        )
    return job_id, reason


def _record_dispatch_failure(
    event: OutboxEvent,
    *,
    code: str,
    message: str,
    max_attempts: int,
) -> None:
    retryable = event.attempts < max_attempts
    if not retryable:
        event.status = OutboxEventStatus.FAILED
    event.last_error = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    event.updated_at = utc_now()


def _mark_failed(
    event: OutboxEvent,
    *,
    code: str,
    message: str,
    retryable: bool,
    max_attempts: int,
) -> None:
    if event.attempts >= max_attempts or not retryable:
        event.status = OutboxEventStatus.FAILED
    event.last_error = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    event.updated_at = utc_now()


def _result_from_event(
    event: OutboxEvent,
    *,
    job_id: UUID | None,
    reason: str | None,
    error_code: str | None = None,
) -> OutboxEventDispatchResult:
    error = None
    if event.last_error is not None:
        error = str(event.last_error.get("message") or "")
    return OutboxEventDispatchResult(
        event_id=event.id,
        job_id=job_id,
        reason=reason,
        published=event.status == OutboxEventStatus.PUBLISHED,
        status=event.status.value,
        error_code=error_code,
        error=error,
    )


def _log_batch_result(result: OutboxBatchResult) -> None:
    logger.info(
        "Outbox dispatch batch completed.",
        extra={
            "outbox_selected": result.selected,
            "outbox_published": result.published,
            "outbox_failed": result.failed,
            "outbox_pending": result.pending,
        },
    )


def _never_returns() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _never_returns()
