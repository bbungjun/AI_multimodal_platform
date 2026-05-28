from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.models import GenerationMode, Job, JobState, utc_now
from app.services.jobs import runner


class FakeScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeBegin:
    def __init__(self, session: FakeRunnerSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeBegin:
        self.session.begin_count += 1
        return self

    async def __aexit__(self, *_args: object) -> bool:
        self.session.end_count += 1
        return False


class FakeRunnerSession:
    def __init__(self, scalar_results: list[list[object]], jobs: list[Job]) -> None:
        self.scalar_results = scalar_results
        self.jobs_by_id = {job.id: job for job in jobs}
        self.statements: list[object] = []
        self.begin_count = 0
        self.end_count = 0

    async def __aenter__(self) -> FakeRunnerSession:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    def begin(self) -> FakeBegin:
        return FakeBegin(self)

    async def scalars(self, statement: object) -> FakeScalarsResult:
        self.statements.append(statement)
        rows = self.scalar_results.pop(0) if self.scalar_results else []
        return FakeScalarsResult(rows)

    async def get(self, _model: object, job_id: object) -> Job | None:
        return self.jobs_by_id.get(job_id)


def _job(*, state: JobState = JobState.PENDING, blocked: bool = False) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=state,
        prompt="A small cabin at sunrise",
        blocked=blocked,
        attempts=0,
        parameters={},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def test_pending_jobs_statement_selects_unblocked_pending_jobs_with_row_lock():
    statement = runner._pending_jobs_statement(2)

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "jobs.state = 'pending'" in sql
    assert "jobs.blocked is false" in sql
    assert "for update skip locked" in sql
    assert "limit 2" in sql


async def test_poll_once_queues_pending_jobs_and_runs_handler():
    job = _job()
    session = FakeRunnerSession([[job]], [job])
    handled: list[object] = []

    async def handle(job_id: object) -> None:
        handled.append(job_id)

    job_runner = runner.InProcessJobRunner(
        session_factory=lambda: session,
        handler=handle,
        concurrency=1,
        poll_interval=0,
        shutdown_timeout=0.1,
    )

    picked_count = await job_runner.poll_once()
    await job_runner.wait_for_idle(timeout=1)

    assert picked_count == 1
    assert handled == [job.id]
    assert job.state == JobState.QUEUED
    assert job.state_history[-1]["detail"] == {"runner": "in-process"}
    assert session.begin_count == 1
    assert session.end_count == 1


async def test_poll_once_does_not_claim_more_jobs_when_slots_are_full():
    first_job = _job()
    second_job = _job()
    session = FakeRunnerSession([[first_job], [second_job]], [first_job, second_job])
    handler_started = asyncio.Event()
    release_handler = asyncio.Event()
    handled: list[object] = []

    async def handle(job_id: object) -> None:
        handled.append(job_id)
        handler_started.set()
        await release_handler.wait()

    job_runner = runner.InProcessJobRunner(
        session_factory=lambda: session,
        handler=handle,
        concurrency=1,
        poll_interval=0,
        shutdown_timeout=0.1,
    )

    first_picked_count = await job_runner.poll_once()
    await asyncio.wait_for(handler_started.wait(), timeout=1)
    second_picked_count = await job_runner.poll_once()

    release_handler.set()
    await job_runner.wait_for_idle(timeout=1)

    assert first_picked_count == 1
    assert second_picked_count == 0
    assert handled == [first_job.id]
    assert first_job.state == JobState.QUEUED
    assert second_job.state == JobState.PENDING
    assert len(session.statements) == 1


async def test_run_job_semaphore_caps_concurrent_handlers():
    jobs = [_job(state=JobState.QUEUED) for _ in range(3)]
    session = FakeRunnerSession([], jobs)
    active_count = 0
    max_active_count = 0

    async def handle(_job_id: object) -> None:
        nonlocal active_count, max_active_count
        active_count += 1
        max_active_count = max(max_active_count, active_count)
        try:
            await asyncio.sleep(0)
        finally:
            active_count -= 1

    job_runner = runner.InProcessJobRunner(
        session_factory=lambda: session,
        handler=handle,
        concurrency=2,
        poll_interval=0,
        shutdown_timeout=0.1,
    )

    await asyncio.gather(*(job_runner._run_job(job.id) for job in jobs))

    assert max_active_count == 2
    assert active_count == 0


async def test_handler_failure_marks_job_failed_without_leaking_exception():
    job = _job(state=JobState.QUEUED)
    session = FakeRunnerSession([], [job])

    class ProviderCrashed(RuntimeError):
        pass

    async def handle(_job_id: object) -> None:
        raise ProviderCrashed("provider unavailable")

    job_runner = runner.InProcessJobRunner(
        session_factory=lambda: session,
        handler=handle,
        concurrency=1,
        poll_interval=0,
        shutdown_timeout=0.1,
    )

    await job_runner._run_job(job.id)

    assert job.state == JobState.FAILED
    assert job.error == {
        "code": "provider_crashed",
        "message": "provider unavailable",
        "retry_count": 0,
        "last_attempt_at": job.error["last_attempt_at"],
    }
    assert job.state_history[-1]["detail"] == {"error": "provider_crashed"}


async def test_resume_polling_jobs_reschedules_jobs_with_vertex_operation():
    job = _job(state=JobState.POLLING)
    job.vertex_operation_name = "projects/demo/locations/us/operations/123"
    session = FakeRunnerSession([[job]], [job])
    handled: list[object] = []

    async def handle(job_id: object) -> None:
        handled.append(job_id)

    job_runner = runner.InProcessJobRunner(
        session_factory=lambda: session,
        handler=handle,
        concurrency=1,
        poll_interval=0,
        shutdown_timeout=0.1,
    )

    resumed_count = await job_runner.resume_polling_jobs()
    await job_runner.wait_for_idle(timeout=1)

    assert resumed_count == 1
    assert handled == [job.id]
    assert job.state == JobState.POLLING
    assert session.begin_count == 1
    assert session.end_count == 1


async def test_run_forever_sweeps_orphans_before_resuming_polling_jobs():
    class RecordingRunner(runner.InProcessJobRunner):
        def __init__(self) -> None:
            super().__init__(
                session_factory=lambda: FakeRunnerSession([], []),
                handler=lambda _job_id: asyncio.sleep(0),
                concurrency=1,
                poll_interval=0,
                shutdown_timeout=0.1,
            )
            self.calls: list[str] = []

        async def sweep_orphans(self) -> int:
            self.calls.append("sweep")
            return 0

        async def resume_polling_jobs(self) -> int:
            self.calls.append("resume")
            return 0

        async def poll_once(self) -> int:
            self.calls.append("poll")
            self._stopping = True
            return 0

    job_runner = RecordingRunner()

    await job_runner.run_forever()

    assert job_runner.calls == ["sweep", "resume", "poll"]


async def test_sweep_orphans_marks_stale_non_terminal_jobs_failed():
    job = _job(state=JobState.GENERATING)
    session = FakeRunnerSession([[job]], [job])

    swept_count = await runner._sweep_orphaned_jobs(
        lambda: session,
        older_than=timedelta(minutes=5),
    )

    assert swept_count == 1
    assert job.state == JobState.FAILED
    assert job.error == {
        "code": "orphaned_job",
        "message": "Job was left in a non-terminal state after runner restart.",
        "retry_count": 0,
        "last_attempt_at": job.error["last_attempt_at"],
    }
    assert job.state_history[-1]["detail"] == {"reason": "runner_startup_sweep"}


async def test_sweep_orphans_preserves_resumable_polling_jobs():
    job = _job(state=JobState.POLLING)
    job.vertex_operation_name = "projects/demo/locations/us/operations/123"
    session = FakeRunnerSession([[job]], [job])

    swept_count = await runner._sweep_orphaned_jobs(
        lambda: session,
        older_than=timedelta(minutes=5),
    )

    assert swept_count == 0
    assert job.state == JobState.POLLING
    assert job.error is None
    assert job.state_history == []
