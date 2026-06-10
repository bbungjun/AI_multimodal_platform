from __future__ import annotations

from uuid import uuid4

from app.models import GenerationMode, Job, JobState, utc_now
from app.services.jobs import tasks


class FakeScalarsResult:
    def __init__(self, rows: list[Job]) -> None:
        self.rows = rows

    def first(self) -> Job | None:
        return self.rows[0] if self.rows else None


class FakeBegin:
    def __init__(self, session: FakeTaskSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeBegin:
        self.session.events.append("begin")
        return self

    async def __aexit__(self, *_args: object) -> bool:
        self.session.events.append("end")
        return False


class FakeTaskSession:
    def __init__(self, job: Job | None) -> None:
        self.job = job
        self.events: list[str] = []
        self.statements: list[object] = []

    async def __aenter__(self) -> FakeTaskSession:
        self.events.append("session_enter")
        return self

    async def __aexit__(self, *_args: object) -> bool:
        self.events.append("session_exit")
        return False

    def begin(self) -> FakeBegin:
        return FakeBegin(self)

    async def scalars(self, statement: object) -> FakeScalarsResult:
        self.statements.append(statement)
        return FakeScalarsResult([] if self.job is None else [self.job])


def _job(
    *,
    state: JobState = JobState.PENDING,
    blocked: bool = False,
    mode: GenerationMode = GenerationMode.T2I,
    model: str = "imagen-4.0-fast-generate-001",
) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=mode,
        model=model,
        state=state,
        prompt="A small cabin at sunrise",
        blocked=blocked,
        attempts=0,
        parameters={},
        state_history=[],
        error=None,
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


async def test_process_job_resumes_polling_job_with_vertex_operation():
    job = _job(
        state=JobState.POLLING,
        mode=GenerationMode.T2V,
        model="veo-3.0-fast-generate-001",
    )
    job.vertex_operation_name = "projects/demo/locations/us/operations/veo-123"
    session = FakeTaskSession(job)
    handled: list[object] = []

    async def handle(job_id):
        session.events.append("handler")
        handled.append(job_id)

    result = await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is True
    assert result.reason == "resumed_polling"
    assert result.previous_state == "polling"
    assert result.claimed_state == "polling"
    assert job.state == JobState.POLLING
    assert job.state_history == []
    assert handled == [job.id]
    assert session.events == [
        "session_enter",
        "begin",
        "end",
        "session_exit",
        "handler",
    ]


async def test_process_job_noops_polling_image_job_even_with_operation_name():
    job = _job(state=JobState.POLLING)
    job.vertex_operation_name = "projects/demo/locations/us/operations/invalid-image-op"
    session = FakeTaskSession(job)

    async def handle(_job_id):
        raise AssertionError("non-video polling job must not reach handler")

    result = await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is False
    assert result.reason == "not_pending"
    assert result.previous_state == "polling"
    assert job.state == JobState.POLLING
    assert job.state_history == []


async def test_process_job_claims_pending_job_before_handler():
    job = _job()
    session = FakeTaskSession(job)
    handled: list[object] = []

    async def handle(job_id):
        session.events.append("handler")
        handled.append(job_id)

    result = await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is True
    assert result.reason == "claimed"
    assert result.previous_state == "pending"
    assert result.claimed_state == "queued"
    assert job.state == JobState.QUEUED
    assert job.state_history[-1]["detail"] == {"runner": "celery"}
    assert handled == [job.id]
    assert session.events == [
        "session_enter",
        "begin",
        "end",
        "session_exit",
        "handler",
    ]


async def test_process_job_noops_blocked_job_without_provider_call():
    job = _job(blocked=True)
    session = FakeTaskSession(job)

    async def handle(_job_id):
        raise AssertionError("blocked job must not reach handler")

    result = await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is False
    assert result.reason == "blocked"
    assert result.previous_state == "pending"
    assert result.claimed_state is None
    assert job.state == JobState.PENDING
    assert job.state_history == []
    assert job.attempts == 0


async def test_process_job_noops_terminal_job():
    job = _job(state=JobState.COMPLETED)
    session = FakeTaskSession(job)

    async def handle(_job_id):
        raise AssertionError("terminal job must not reach handler")

    result = await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is False
    assert result.reason == "terminal"
    assert result.previous_state == "completed"
    assert job.state == JobState.COMPLETED
    assert job.state_history == []


async def test_process_job_noops_already_queued_duplicate():
    job = _job(state=JobState.QUEUED)
    session = FakeTaskSession(job)

    async def handle(_job_id):
        raise AssertionError("duplicate queued task must not reach handler")

    result = await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is False
    assert result.reason == "not_pending"
    assert result.previous_state == "queued"
    assert job.state == JobState.QUEUED
    assert job.state_history == []


async def test_process_job_rejects_invalid_job_id_without_provider_call():
    session = FakeTaskSession(_job())

    async def handle(_job_id):
        raise AssertionError("invalid job id must not reach handler")

    result = await tasks.process_job_async(
        "not-a-uuid",
        session_factory=lambda: session,
        handler=handle,
    )

    assert result.executed is False
    assert result.reason == "invalid_job_id"
    assert result.previous_state is None
    assert result.claimed_state is None
    assert session.events == []


def test_process_job_task_closes_db_pool_after_run(monkeypatch):
    job_id = uuid4()
    calls: list[tuple[str, object]] = []

    async def fake_process_job_async(payload: str):
        calls.append(("process", payload))
        return tasks.ProcessJobResult(
            job_id=job_id,
            executed=True,
            reason="claimed",
            previous_state="pending",
            claimed_state="queued",
        )

    async def fake_close_db_connection():
        calls.append(("close_db", None))

    monkeypatch.setattr(tasks, "process_job_async", fake_process_job_async)
    monkeypatch.setattr(tasks, "close_db_connection", fake_close_db_connection)

    tasks.process_job.run(str(job_id))

    assert calls == [
        ("process", str(job_id)),
        ("close_db", None),
    ]


async def test_process_job_logs_structured_claim_result(caplog):
    job = _job()
    session = FakeTaskSession(job)
    caplog.set_level("INFO")

    async def handle(_job_id):
        return None

    await tasks.process_job_async(
        str(job.id),
        session_factory=lambda: session,
        handler=handle,
    )

    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Celery job task completed."
    )
    assert record.job_id == str(job.id)
    assert record.task_result_reason == "claimed"
    assert record.previous_state == "pending"
    assert record.claimed_state == "queued"
    assert record.task_executed is True
