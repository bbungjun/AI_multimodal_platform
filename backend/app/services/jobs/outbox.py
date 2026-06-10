from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Select, select

from app.models import OutboxEvent, OutboxEventStatus


JOB_DISPATCH_REQUESTED = "job.dispatch_requested"
JOB_AGGREGATE_TYPE = "job"


def add_job_dispatch_event(
    session,
    job_id: UUID,
    *,
    reason: str,
) -> OutboxEvent:
    event = OutboxEvent(
        id=uuid4(),
        event_type=JOB_DISPATCH_REQUESTED,
        aggregate_type=JOB_AGGREGATE_TYPE,
        aggregate_id=job_id,
        payload={
            "job_id": str(job_id),
            "reason": reason,
        },
        status=OutboxEventStatus.PENDING,
        attempts=0,
    )
    session.add(event)
    return event


def pending_job_dispatch_events_statement(*, limit: int) -> Select[tuple[OutboxEvent]]:
    return (
        select(OutboxEvent)
        .where(
            OutboxEvent.event_type == JOB_DISPATCH_REQUESTED,
            OutboxEvent.status == OutboxEventStatus.PENDING,
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
