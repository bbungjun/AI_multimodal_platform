from __future__ import annotations

from uuid import uuid4

from app.models import OutboxEvent, OutboxEventStatus, utc_now
from app.config import Settings
from app.services.jobs.enqueue import DispatchResult
from app.services.jobs import outbox_dispatcher
from app.services.jobs.outbox import JOB_AGGREGATE_TYPE, JOB_DISPATCH_REQUESTED


class FakeScalarsResult:
    def __init__(self, rows: list[OutboxEvent]) -> None:
        self.rows = rows

    def all(self) -> list[OutboxEvent]:
        return self.rows


class FakeOutboxDispatchSession:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events
        self.statements: list[object] = []
        self.commit_count = 0

    async def __aenter__(self) -> FakeOutboxDispatchSession:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def scalars(self, statement: object) -> FakeScalarsResult:
        self.statements.append(statement)
        return FakeScalarsResult(self.events)

    async def commit(self) -> None:
        self.commit_count += 1


def _event(
    *,
    payload: dict[str, object] | None = None,
    status: OutboxEventStatus = OutboxEventStatus.PENDING,
    attempts: int = 0,
) -> OutboxEvent:
    job_id = uuid4()
    return OutboxEvent(
        id=uuid4(),
        event_type=JOB_DISPATCH_REQUESTED,
        aggregate_type=JOB_AGGREGATE_TYPE,
        aggregate_id=job_id,
        payload=payload
        if payload is not None
        else {"job_id": str(job_id), "reason": "generation_created"},
        status=status,
        attempts=attempts,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


async def test_dispatcher_publishes_event_and_marks_published():
    event = _event()
    session = FakeOutboxDispatchSession([event])
    dispatch_calls: list[tuple[object, str]] = []

    async def dispatch_job(job_id, *, reason):
        dispatch_calls.append((job_id, reason))
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode="celery",
            enqueued=True,
            queue="generation",
            task_id="task-123",
        )

    result = await outbox_dispatcher.dispatch_pending_events(
        limit=10,
        session_factory=lambda: session,
        dispatcher=dispatch_job,
        max_attempts=3,
    )

    assert result.selected == 1
    assert result.published == 1
    assert result.failed == 0
    assert result.pending == 0
    assert dispatch_calls == [(event.aggregate_id, "generation_created")]
    assert event.status == OutboxEventStatus.PUBLISHED
    assert event.attempts == 1
    assert event.published_at is not None
    assert event.last_error is None
    assert session.commit_count == 1
    sent_repr = repr(dispatch_calls)
    assert "prompt" not in sent_repr
    assert "parameters" not in sent_repr


async def test_dispatcher_keeps_event_pending_before_max_attempts_on_dispatch_failure():
    event = _event(attempts=1)
    session = FakeOutboxDispatchSession([event])

    async def dispatch_job(job_id, *, reason):
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode="celery",
            enqueued=False,
            error="broker unavailable",
            error_code="runtime_error",
        )

    result = await outbox_dispatcher.dispatch_pending_events(
        limit=10,
        session_factory=lambda: session,
        dispatcher=dispatch_job,
        max_attempts=3,
    )

    assert result.selected == 1
    assert result.published == 0
    assert result.failed == 1
    assert result.pending == 1
    assert event.status == OutboxEventStatus.PENDING
    assert event.attempts == 2
    assert event.published_at is None
    assert event.last_error == {
        "code": "runtime_error",
        "message": "broker unavailable",
        "retryable": True,
    }


async def test_dispatcher_marks_event_failed_at_max_attempts():
    event = _event(attempts=2)
    session = FakeOutboxDispatchSession([event])

    async def dispatch_job(job_id, *, reason):
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode="celery",
            enqueued=False,
            error="broker unavailable",
            error_code="runtime_error",
        )

    result = await outbox_dispatcher.dispatch_pending_events(
        limit=10,
        session_factory=lambda: session,
        dispatcher=dispatch_job,
        max_attempts=3,
    )

    assert result.selected == 1
    assert result.published == 0
    assert result.failed == 1
    assert result.pending == 0
    assert event.status == OutboxEventStatus.FAILED
    assert event.attempts == 3
    assert event.last_error == {
        "code": "runtime_error",
        "message": "broker unavailable",
        "retryable": False,
    }


async def test_dispatcher_rejects_invalid_payload_without_dispatching():
    event = _event(payload={"job_id": "not-a-uuid", "reason": "generation_created"})
    session = FakeOutboxDispatchSession([event])
    dispatch_calls: list[tuple[object, str]] = []

    async def dispatch_job(job_id, *, reason):
        dispatch_calls.append((job_id, reason))
        raise AssertionError("invalid outbox payload must not dispatch")

    result = await outbox_dispatcher.dispatch_pending_events(
        limit=10,
        session_factory=lambda: session,
        dispatcher=dispatch_job,
        max_attempts=3,
    )

    assert result.selected == 1
    assert result.published == 0
    assert result.failed == 1
    assert result.pending == 0
    assert dispatch_calls == []
    assert event.status == OutboxEventStatus.FAILED
    assert event.attempts == 1
    assert event.last_error == {
        "code": "invalid_payload",
        "message": "Outbox event payload has invalid job_id.",
        "retryable": False,
    }


async def test_dispatcher_loop_initializes_schema_before_first_batch():
    events: list[str] = []
    session = FakeOutboxDispatchSession([])

    async def initialize_schema() -> None:
        events.append("init_schema")

    async def dispatch_job(*_args, **_kwargs):
        events.append("dispatch_job")
        raise AssertionError("empty outbox batch must not dispatch jobs")

    await outbox_dispatcher.run_dispatcher_loop(
        settings=Settings(
            _env_file=None,
            outbox_dispatcher_batch_size=10,
            outbox_dispatcher_poll_interval_sec=0,
            outbox_dispatcher_max_attempts=3,
        ),
        once=True,
        session_factory=lambda: session,
        dispatcher=dispatch_job,
        initialize_schema=initialize_schema,
    )

    assert events == ["init_schema"]
    assert session.commit_count == 1
