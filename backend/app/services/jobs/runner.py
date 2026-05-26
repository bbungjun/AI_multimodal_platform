from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, and_, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.models import Job, JobState
from app.state_machine import NON_TERMINAL_STATES, TERMINAL_STATES, transition
from app.services.jobs.handlers import handle as default_handler


JobHandler = Callable[[UUID], Awaitable[None]]
SessionFactory = Callable[[], AsyncSession]
logger = logging.getLogger(__name__)


class JobRunnerConfigError(ValueError):
    pass


class InProcessJobRunner:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = AsyncSessionLocal,
        handler: JobHandler = default_handler,
        concurrency: int | None = None,
        poll_interval: float = 1.0,
        shutdown_timeout: float = 30.0,
        sweep_after: timedelta = timedelta(minutes=5),
    ) -> None:
        settings = get_settings()
        resolved_concurrency = (
            settings.job_runner_concurrency if concurrency is None else concurrency
        )
        if resolved_concurrency < 1:
            raise JobRunnerConfigError("concurrency must be at least 1")
        if poll_interval < 0:
            raise JobRunnerConfigError("poll_interval must be greater than or equal to 0")
        if shutdown_timeout < 0:
            raise JobRunnerConfigError(
                "shutdown_timeout must be greater than or equal to 0"
            )

        self.session_factory = session_factory
        self.handler = handler
        self.concurrency = resolved_concurrency
        self.poll_interval = poll_interval
        self.shutdown_timeout = shutdown_timeout
        self.sweep_after = sweep_after
        self._semaphore = asyncio.Semaphore(resolved_concurrency)
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False
        self._poll_failure_key: str | None = None

    async def run_forever(self) -> None:
        try:
            await self.sweep_orphans()
            await self.resume_polling_jobs()
            while not self._stopping:
                try:
                    await self.poll_once()
                except asyncio.CancelledError:
                    self._stopping = True
                    raise
                except Exception as exc:
                    self._log_poll_failure(exc)
                    if _task_cancellation_requested():
                        raise asyncio.CancelledError
                else:
                    self._clear_poll_failure()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            self._stopping = True
            raise
        finally:
            try:
                await self.shutdown()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Job runner shutdown failed: %s", exc)

    async def poll_once(self) -> int:
        if self._stopping:
            return 0

        self._discard_finished_tasks()
        available_slots = self.concurrency - len(self._active_tasks)
        if available_slots <= 0:
            return 0

        job_ids: list[UUID] = []
        async with self.session_factory() as session:
            async with session.begin():
                jobs = await _pick_pending_jobs(session, limit=available_slots)
                for job in jobs:
                    transition(
                        job,
                        JobState.QUEUED,
                        detail={"runner": "in-process"},
                    )
                    job_ids.append(job.id)

        for job_id in job_ids:
            self._spawn_job(job_id)

        return len(job_ids)

    async def sweep_orphans(self) -> int:
        try:
            return await _sweep_orphaned_jobs(
                self.session_factory,
                older_than=self.sweep_after,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Job runner orphan sweep failed: %s", exc)
            if _task_cancellation_requested():
                raise asyncio.CancelledError
            return 0

    async def resume_polling_jobs(self) -> int:
        try:
            return await self._schedule_resumable_polling_jobs()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Job runner polling resume failed: %s", exc)
            if _task_cancellation_requested():
                raise asyncio.CancelledError
            return 0

    async def wait_for_idle(self, *, timeout: float | None = None) -> None:
        tasks = list(self._active_tasks)
        if not tasks:
            return

        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=False),
            timeout=timeout,
        )

    async def shutdown(self) -> None:
        self._stopping = True
        tasks = list(self._active_tasks)
        if not tasks:
            return

        done, pending = await asyncio.wait(tasks, timeout=self.shutdown_timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                logger.warning("Job runner task stopped with error: %s", exc)
        self._discard_finished_tasks()

    def _spawn_job(self, job_id: UUID) -> None:
        task = asyncio.create_task(
            self._run_job(job_id),
            name=f"job-runner:{job_id}",
        )
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    async def _run_job(self, job_id: UUID) -> None:
        async with self._semaphore:
            try:
                await self.handler(job_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                try:
                    await _mark_job_failed(
                        self.session_factory,
                        job_id,
                        exc,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as mark_exc:
                    logger.warning(
                        "Failed to mark job %s as failed after handler error: %s",
                        job_id,
                        mark_exc,
                    )

    def _discard_finished_tasks(self) -> None:
        self._active_tasks = {task for task in self._active_tasks if not task.done()}

    def _log_poll_failure(self, exc: Exception) -> None:
        key = f"{_exception_code(exc)}:{exc}"
        if key == self._poll_failure_key:
            return

        self._poll_failure_key = key
        logger.warning("Job runner poll failed: %s", exc)

    def _clear_poll_failure(self) -> None:
        if self._poll_failure_key is None:
            return

        self._poll_failure_key = None
        logger.info("Job runner poll recovered.")

    async def _schedule_resumable_polling_jobs(self) -> int:
        if self._stopping:
            return 0

        self._discard_finished_tasks()
        available_slots = self.concurrency - len(self._active_tasks)
        if available_slots <= 0:
            return 0

        job_ids: list[UUID] = []
        async with self.session_factory() as session:
            async with session.begin():
                jobs = await _pick_resumable_polling_jobs(
                    session,
                    limit=available_slots,
                )
                job_ids.extend(job.id for job in jobs)

        for job_id in job_ids:
            self._spawn_job(job_id)

        return len(job_ids)


async def job_runner() -> None:
    runner = InProcessJobRunner()
    await runner.run_forever()


def _pending_jobs_statement(limit: int) -> Select[tuple[Job]]:
    if limit < 1:
        raise JobRunnerConfigError("limit must be at least 1")

    return (
        select(Job)
        .where(Job.state == JobState.PENDING, Job.blocked.is_(False))
        .order_by(Job.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


async def _pick_pending_jobs(session: AsyncSession, *, limit: int) -> list[Job]:
    result = await session.scalars(_pending_jobs_statement(limit))
    return list(result.all())


def _resumable_polling_jobs_statement(limit: int) -> Select[tuple[Job]]:
    if limit < 1:
        raise JobRunnerConfigError("limit must be at least 1")

    return (
        select(Job)
        .where(
            Job.state == JobState.POLLING,
            Job.vertex_operation_name.is_not(None),
        )
        .order_by(Job.updated_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


async def _pick_resumable_polling_jobs(
    session: AsyncSession,
    *,
    limit: int,
) -> list[Job]:
    result = await session.scalars(_resumable_polling_jobs_statement(limit))
    return list(result.all())


def _orphaned_jobs_statement(stale_before: datetime) -> Select[tuple[Job]]:
    resumable_polling = and_(
        Job.state == JobState.POLLING,
        Job.vertex_operation_name.is_not(None),
    )
    return (
        select(Job)
        .where(
            Job.state.in_(NON_TERMINAL_STATES),
            Job.updated_at < stale_before,
            not_(resumable_polling),
        )
        .order_by(Job.updated_at)
        .with_for_update(skip_locked=True)
    )


async def _sweep_orphaned_jobs(
    session_factory: SessionFactory,
    *,
    older_than: timedelta,
) -> int:
    now = datetime.now(timezone.utc)
    stale_before = now - older_than
    swept = 0

    async with session_factory() as session:
        async with session.begin():
            result = await session.scalars(_orphaned_jobs_statement(stale_before))
            for job in result.all():
                if job.state in TERMINAL_STATES:
                    continue
                job.error = {
                    "code": "orphaned_job",
                    "message": "Job was left in a non-terminal state after runner restart.",
                    "retry_count": job.attempts,
                    "last_attempt_at": now.isoformat(),
                }
                transition(
                    job,
                    JobState.FAILED,
                    detail={"reason": "runner_startup_sweep"},
                    at=now,
                )
                swept += 1

    return swept


async def _mark_job_failed(
    session_factory: SessionFactory,
    job_id: UUID,
    exc: Exception,
) -> None:
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        async with session.begin():
            job = await session.get(Job, job_id)
            if job is None or job.state in TERMINAL_STATES:
                return

            error = {
                "code": _exception_code(exc),
                "message": str(exc) or exc.__class__.__name__,
                "retry_count": job.attempts,
                "last_attempt_at": now.isoformat(),
            }
            job.error = error
            transition(
                job,
                JobState.FAILED,
                detail={"error": error["code"]},
                at=now,
            )


def _exception_code(exc: Exception) -> str:
    name = exc.__class__.__name__
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()


def _task_cancellation_requested() -> bool:
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0
