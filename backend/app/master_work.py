"""Internal suspension work policy; uses existing state/credit terminal Interfaces."""
from uuid import UUID

from sqlalchemy import select

from app import generation_credit
from app.identity_models import User
from app.models import Job, JobState, OutboxEvent, OutboxEventStatus
from app.state_machine import transition

MAX_PENDING_SCAN = 500


class MasterWorkError(ValueError):
    def __init__(self, code="master_unavailable"):
        self.code = code
        super().__init__(code)


async def lock_owner_status(session, user_id):
    if not isinstance(user_id, UUID):
        raise MasterWorkError()
    status = await session.scalar(select(User.status).where(User.id == user_id).with_for_update())
    if status is None:
        raise MasterWorkError()
    return status


def mark_cancelled(job, now):
    job.error = {"code": "user_suspended", "message": "Account suspended before dispatch.", "retryable": False}
    transition(job, JobState.CANCELLED, detail={"error": "user_suspended"}, at=now)
    job.blocked = False


async def cancel_unpublished(session, *, user_id, now):
    """Caller holds User lock. Outbox publication completes before Job decisions."""
    events = list((await session.scalars(select(OutboxEvent).join(Job, Job.id == OutboxEvent.aggregate_id)
        .where(Job.owner_user_id == user_id, Job.state == JobState.PENDING)
        .order_by(OutboxEvent.id).limit(MAX_PENDING_SCAN + 1).with_for_update(of=OutboxEvent)
        .execution_options(populate_existing=True))).all())
    jobs = list((await session.scalars(select(Job).where(Job.owner_user_id == user_id,
        Job.state == JobState.PENDING).order_by(Job.id).limit(MAX_PENDING_SCAN + 1)
        .with_for_update(of=Job).execution_options(populate_existing=True))).all())
    if len(events) > MAX_PENDING_SCAN or len(jobs) > MAX_PENDING_SCAN:
        raise MasterWorkError("master_busy")
    published = {e.aggregate_id for e in events if e.status == OutboxEventStatus.PUBLISHED or e.published_at is not None}
    pending = {job.id: job for job in jobs}
    parent_ids = {job.parent_job_id for job in jobs if job.parent_job_id is not None}
    parents = {p.id: p for p in list((await session.scalars(select(Job).where(Job.id.in_(parent_ids))
        .execution_options(populate_existing=True))).all())} if parent_ids else {}
    cancelled = {}
    for job in jobs:
        if job.id in published:
            continue
        if job.parent_job_id is not None:
            parent = parents.get(job.parent_job_id)
            if parent is None or parent.owner_user_id != user_id:
                raise MasterWorkError()
            parent_undispatched = parent.id in pending and parent.id not in published
            if not parent_undispatched and parent.state not in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
                continue
        cancelled[job.id] = job
    for job in cancelled.values():
        mark_cancelled(job, now)
    for job in cancelled.values():
        parent = parents.get(job.parent_job_id)
        if parent is not None and (parent.id in cancelled or parent.state in {JobState.FAILED, JobState.CANCELLED}):
            continue  # The parent owns the single terminal reservation operation.
        await generation_credit.terminalize_generation(session, job=job, succeeded=False,
            reason_code="cancelled_before_delivery", now=now)
    for event in events:
        if event.aggregate_id in cancelled:
            event.status = OutboxEventStatus.FAILED
            event.last_error = {"code": "user_suspended", "retryable": False}
            event.updated_at = now
    return len(cancelled)
