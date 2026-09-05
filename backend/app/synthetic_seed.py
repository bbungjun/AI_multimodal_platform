"""Deterministic content-free history, restricted to disposable mock targets."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text

from app.credit_accounting import (CreditAccountingError, ReservationRequest, UsageEstimate,
    UsageLine, UsageReport, reserve, settle, release)
from app.credit_lifecycle import change_plan, ensure_cycle, grant_bonus
from app.identity_models import User
from app.models import Job, JobState
from app.state_machine import transition

VERSION = "g10e-v1"
NAMESPACE = uuid5(NAMESPACE_URL, "creativeops/synthetic/g10e-v1")
LOCK_KEY = 74100501


class SeedError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureUser:
    id: UUID
    index: int
    plan: str
    signed_up_at: datetime
    cohort: str


@dataclass(frozen=True)
class FixtureJob:
    id: UUID
    index: int
    created_at: datetime
    model: str
    meter: str
    units: int
    outcome: str


def instant(value):
    if not isinstance(value, datetime) or value.utcoffset() is None or not 2001 <= value.year <= 2099:
        raise SeedError("seed_time_invalid")
    return value.astimezone(timezone.utc)


def fixture_users(as_of):
    as_of = instant(as_of)
    return tuple(FixtureUser(uuid5(NAMESPACE, f"user-{i}"), i,
        "free" if i < 84 else "pro" if i < 114 else "max",
        as_of-timedelta(days=100+i % 17),
        "dormant" if i % 10 == 0 else "suspended" if i % 10 == 1 else "active") for i in range(120))


def fixture_jobs(user, as_of):
    as_of = instant(as_of)
    result = []
    for i in range(25):
        video = i % 5 == 4
        variant = ("fast" if user.plan == "free" else "standard" if user.plan == "pro" else "ultra")
        if video:
            variant = "standard" if user.plan == "max" else "fast"
        model = ({"fast": "veo-3.0-fast-generate-001", "standard": "veo-3.0-generate-001"} if video else {
            "fast": "imagen-4.0-fast-generate-001", "standard": "imagen-4.0-generate-001",
            "ultra": "imagen-4.0-ultra-generate-001"})[variant]
        result.append(FixtureJob(uuid5(NAMESPACE, f"job-{user.index}-{i}"), i,
            as_of-timedelta(days=89)+timedelta(seconds=i*(44 if user.cohort == "dormant" else 88)*86400//24),
            model, f"veo_{variant}_ms" if video else f"imagen_{variant}_image", 4000 if video else 1,
            "failed" if i % 7 == 6 else "cancelled" if i % 11 == 10 else "completed"))
    return tuple(result)


def report(replayed):
    return dict(users=120, jobs=3000, plans=dict(free=84, pro=30, max=6),
        cohorts=dict(active=96, dormant=12, suspended=12), replayed=replayed,
        denial_observations=dict(plan=1, quota=1, concurrency=1))


async def _existing(session, users, jobs, marker):
    ids = [u.id for u in users]
    found = list((await session.execute(select(User.id, User.data_origin, User.google_sub,
        User.email, User.email_verified, User.role).where(User.id.in_(ids)))).all())
    existing_jobs = list((await session.execute(select(Job.id, Job.owner_user_id, Job.parameters)
        .where(Job.id.in_(jobs)))).all())
    if not found and not existing_jobs:
        return False
    if len(found) != 120 or len(existing_jobs) != 3000:
        raise SeedError("seed_namespace_conflict")
    if any(r.data_origin != "synthetic" or r.google_sub is not None or r.email is not None
           or r.email_verified or r.role != "user" for r in found):
        raise SeedError("seed_namespace_conflict")
    if any(r.owner_user_id != jobs[r.id] or not isinstance(r.parameters, dict)
           or r.parameters.get("synthetic_fixture") != marker for r in existing_jobs):
        raise SeedError("seed_namespace_conflict")
    return True


async def _denials(session, user_id, as_of):
    probe = await session.begin_nested()
    try:
        for key, meter, units, expected in (
            ("plan", "imagen_ultra_image", 1, "credit_plan_refused"),
            ("quota", "imagen_fast_image", 1000, "monthly_credit_exhausted")):
            try:
                await reserve(session, request=ReservationRequest(user_id, "seed_probe_"+key,
                    (UsageEstimate(meter, units),)), now=as_of)
            except CreditAccountingError as error:
                if error.code != expected:
                    raise SeedError("seed_probe_failed") from None
            else:
                raise SeedError("seed_probe_failed")
        await reserve(session, request=ReservationRequest(user_id, "seed_probe_hold",
            (UsageEstimate("gemini_input_token", 1),)), now=as_of)
        try:
            await reserve(session, request=ReservationRequest(user_id, "seed_probe_concurrency",
                (UsageEstimate("gemini_input_token", 1),)), now=as_of)
        except CreditAccountingError as error:
            if error.code != "user_concurrency_limit":
                raise SeedError("seed_probe_failed") from None
        else:
            raise SeedError("seed_probe_failed")
    finally:
        await probe.rollback()


async def seed_fixture(session, *, as_of):
    """Caller commits or rolls back. Never selects a target from runtime defaults."""
    as_of = instant(as_of)
    if not session.in_transaction():
        raise SeedError("seed_transaction_required")
    users = fixture_users(as_of)
    jobs = {job.id: user.id for user in users for job in fixture_jobs(user, as_of)}
    marker = dict(version=VERSION, as_of=as_of.isoformat())
    async with session.begin_nested():
        await session.execute(text("SET LOCAL lock_timeout='5s'"))
        await session.execute(text("SET LOCAL statement_timeout='5s'"))
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        if await _existing(session, users, jobs, marker):
            return report(True)
        for user in users:
            row = User(id=user.id, google_sub=None, email=None, email_verified=False, role="user",
                status="active", data_origin="synthetic", signed_up_at=user.signed_up_at,
                updated_at=user.signed_up_at, suspended_at=None)
            session.add(row)
            await session.flush()
            entries = fixture_jobs(user, as_of)
            await ensure_cycle(session, user_id=user.id, now=entries[0].created_at)
            if user.plan != "free":
                await change_plan(session, user_id=user.id, target_plan=user.plan,
                    operation_key="seed_plan_v1", now=entries[0].created_at)
            if user.plan == "free" and user.cohort == "dormant":
                await grant_bonus(session, user_id=user.id, amount_microcredits=1_000_000_000,
                    expires_at=None, reason_code="synthetic_fixture", operation_key="seed_bonus_v1",
                    now=entries[0].created_at)
            for entry in entries:
                key = f"seed_v1_{entry.index}"
                usage = (UsageEstimate("gemini_input_token", 10), UsageEstimate("gemini_output_token", 5),
                         UsageEstimate(entry.meter, entry.units))
                receipt = await reserve(session, request=ReservationRequest(user.id, key, usage), now=entry.created_at)
                observed = UsageReport(tuple(UsageLine(v.meter, v.maximum_units, "mock_estimate") for v in usage))
                end = entry.created_at+timedelta(seconds=5+entry.index)
                job = Job(id=entry.id, owner_user_id=user.id, mode="t2v" if entry.meter.startswith("veo") else "t2i",
                    model=entry.model, state=JobState.PENDING, prompt="Synthetic operation fixture",
                    parameters={"synthetic_fixture": marker}, state_history=[], blocked=False,
                    attempts=0, vertex_charged=False, created_at=entry.created_at, updated_at=entry.created_at)
                if entry.outcome == "completed":
                    for state, offset in ((JobState.QUEUED, 1), (JobState.GENERATING, 2), (JobState.DOWNLOADING, 3)):
                        transition(job, state, at=entry.created_at+timedelta(seconds=offset))
                    transition(job, JobState.COMPLETED, at=end)
                    await settle(session, user_id=user.id, reservation_id=receipt.reservation_id,
                        usage=observed, delivery="delivered", operation_key=key+"_terminal", now=end)
                else:
                    code = "provider_failed" if entry.outcome == "failed" else "cancelled_before_delivery"
                    transition(job, JobState.FAILED if entry.outcome == "failed" else JobState.CANCELLED, at=end)
                    job.error = {"code": code, "retryable": False}
                    await release(session, user_id=user.id, reservation_id=receipt.reservation_id,
                        usage=observed, reason_code=code, operation_key=key+"_terminal", now=end)
                session.add(job)
            if user.cohort == "suspended":
                row.status, row.suspended_at, row.updated_at = "suspended", as_of, as_of
            await session.flush()
        await _denials(session, users[2].id, as_of)
        return report(False)
