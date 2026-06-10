from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.models import OutboxEvent, OutboxEventStatus
from app.services.jobs import outbox


class FakeOutboxSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)


def test_add_job_dispatch_event_stores_minimal_payload_only():
    session = FakeOutboxSession()
    job_id = uuid4()

    event = outbox.add_job_dispatch_event(
        session,
        job_id,
        reason="generation_created",
    )

    assert session.added == [event]
    assert isinstance(event, OutboxEvent)
    assert event.status == OutboxEventStatus.PENDING
    assert event.event_type == outbox.JOB_DISPATCH_REQUESTED
    assert event.aggregate_type == "job"
    assert event.aggregate_id == job_id
    assert event.payload == {
        "job_id": str(job_id),
        "reason": "generation_created",
    }
    payload_repr = repr(event.payload)
    assert "prompt" not in payload_repr
    assert "parameters" not in payload_repr
    assert "source_asset_id" not in payload_repr


def test_pending_job_dispatch_events_statement_locks_oldest_pending_events():
    statement = outbox.pending_job_dispatch_events_statement(limit=25)

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "from outbox_events" in sql
    assert "outbox_events.event_type = 'job.dispatch_requested'" in sql
    assert "outbox_events.status = 'pending'" in sql
    assert "order by outbox_events.created_at, outbox_events.id" in sql
    assert "limit 25" in sql
    assert "for update skip locked" in sql
