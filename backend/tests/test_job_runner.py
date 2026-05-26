from __future__ import annotations

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
