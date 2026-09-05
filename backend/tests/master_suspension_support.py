"""Actual local PostgreSQL suspension proof; only aggregate receipt is emitted."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import time
from uuid import uuid4

from app.schema_revision import CODE_REVISION as HEAD

GROUPS = ("guards", "sessions", "reactivation", "pending", "published", "pipeline", "rollback", "races")
phase = "guard"
T = datetime(2025, 1, 1, tzinfo=timezone.utc)
NOW = T + timedelta(days=1)


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"master-suspension-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.database != project.replace("-", "_") or provider != "mock" or app_env != "test"):
        raise ValueError("suspension_target_refused")


async def proof(db, factory):
    from app import generation_credit as gc
    from app.auth.service import AuthService, AuthError, new_secret, digest
    from app.master_admin import MasterCommand, MasterError, administer
    from app.models import Job, JobState, GenerationMode, Asset, AssetKind
    from app.services.jobs.outbox import add_job_dispatch_event
    from app.services.jobs import pipeline_link
    from app.services.jobs.tasks import process_job_async
    from app.state_machine import transition

    global phase
    checks, races, groups = 0, 0, {}
    pipeline_link.utc_now = lambda: NOW

    def check(value):
        nonlocal checks
        assert value, "suspension_assertion"
        checks += 1

    async def seed(role="user"):
        uid, marker = uuid4(), uuid4().hex
        await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,"
            "signed_up_at,updated_at) VALUES($1,$2,$3,true,$4,'active','oauth',$5,$5)",
            uid, marker, marker + "@example.invalid", role, T)
        return uid

    master = await seed("master")

    def command(uid, action="suspend"):
        return MasterCommand(uid, uuid4(), action, "account_policy")

    async def act(cmd, rollback=False):
        async with factory() as session, session.begin():
            result = await administer(session, actor_id=master, command=cmd, now=NOW)
            if rollback:
                await session.rollback()
            return result

    async def session_for(uid):
        secret = new_secret()
        await db.execute("INSERT INTO user_sessions(id,user_id,token_hash,created_at,last_seen_at,absolute_expires_at) "
            "VALUES($1,$2,$3,$4,$4,$5)", uuid4(), uid, digest(secret), NOW, NOW + timedelta(days=7))
        auth = AuthService(factory, None, None, clock=lambda: NOW)
        check((await auth.authenticate(secret)).id == uid)
        return auth, secret

    async def denied_auth(auth, secret):
        try:
            await auth.authenticate(secret)
        except AuthError as error:
            check(error.code == "authentication_required")
        else:
            raise AssertionError("auth_refusal_missing")

    def make(uid, *, video=False, parent=None):
        return Job(id=uuid4(), owner_user_id=uid,
            mode=GenerationMode.I2V if parent else (GenerationMode.T2V if video else GenerationMode.T2I),
            model="veo-3.0-fast-generate-001" if video else "imagen-4.0-fast-generate-001",
            state=JobState.PENDING, prompt="synthetic", parent_job_id=parent,
            blocked=parent is not None, attempts=0, state_history=[], vertex_charged=False,
            parameters={"duration_sec": 4} if video else {"number_of_images": 1}, created_at=NOW, updated_at=NOW)

    async def admit(uid, *, video=False, pipeline=False):
        parent = make(uid, video=video)
        child = make(uid, video=True, parent=parent.id) if pipeline else None
        async with factory() as session, session.begin():
            session.add(parent)
            if child:
                session.add(child)
            receipt = await gc.admit_generation(session, job=parent, pipeline_child=child, now=NOW)
            event = add_job_dispatch_event(session, parent.id, reason="proof")
        check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", receipt.reservation_id) == "held")
        return parent.id, child.id if child else None, event.id, receipt.reservation_id

    async def finish(jid, *, failed=False):
        async with factory() as session, session.begin():
            job = await session.get(Job, jid)
            if job.state == JobState.PENDING:
                transition(job, JobState.QUEUED, at=NOW)
            if job.state == JobState.QUEUED:
                transition(job, JobState.GENERATING, at=NOW)
            if not failed:
                session.add(Asset(job_id=jid, kind=AssetKind.IMAGE, local_path=jid.hex+"/proof.png",
                    mime="image/png", size_bytes=1, created_at=NOW))
                transition(job, JobState.DOWNLOADING, at=NOW)
            await gc.terminalize_generation(session, job=job, succeeded=not failed,
                reason_code="provider_failed" if failed else None, now=NOW)
            transition(job, JobState.FAILED if failed else JobState.COMPLETED, at=NOW)

    async def status(uid):
        return await db.fetchval("SELECT status FROM users WHERE id=$1", uid)

    phase = "guards"
    try:
        await act(command(master))
    except MasterError as error:
        check(error.code == "master_conflict")
    else:
        raise AssertionError("self_guard_missing")
    check(await status(master) == "active")
    check(await db.fetchval("SELECT count(*) FROM master_audit") == 0)
    check(await db.fetchval("SELECT count(*) FROM users WHERE role='master' AND status='active'") == 1)
    groups[phase] = True

    phase = "sessions"
    uid = await seed()
    credentials = [await session_for(uid) for _ in range(3)]
    cmd = command(uid)
    receipt = await act(cmd)
    check(receipt.after["revoked_sessions"] == 3)
    check(receipt.after["cancelled_jobs"] == 0)
    check(receipt.before["status"] == "active" and receipt.after["status"] == "suspended")
    check(receipt.after["plan"] is None)
    check(await db.fetchval("SELECT count(*) FROM credit_accounts WHERE user_id=$1", uid) == 0)
    for auth, secret in credentials:
        await denied_auth(auth, secret)
    check((await act(cmd)).replayed)
    check(await db.fetchval("SELECT count(*) FROM master_audit WHERE request_id=$1", cmd.request_id) == 1)
    groups[phase] = True

    phase = "reactivation"
    receipt = await act(command(uid, "reactivate"))
    check(receipt.after["status"] == "active")
    check(await status(uid) == "active")
    check(await db.fetchval("SELECT suspended_at FROM users WHERE id=$1", uid) is None)
    for auth, secret in credentials:
        await denied_auth(auth, secret)
    check(await db.fetchval("SELECT count(*) FROM user_sessions WHERE user_id=$1 AND revoked_at IS NOT NULL", uid) == 3)
    await session_for(uid)
    groups[phase] = True

    phase = "pending"
    for video in (False, True):
        owner = await seed()
        jid, _, event, reservation = await admit(owner, video=video)
        result = await act(command(owner))
        check(result.after["cancelled_jobs"] == 1)
        check(await db.fetchval("SELECT state FROM jobs WHERE id=$1", jid) == "cancelled")
        check(await db.fetchval("SELECT status FROM outbox_events WHERE id=$1", event) == "failed")
        check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "released")
        check(await db.fetchval("SELECT sum(reserved_microcredits) FROM credit_grants WHERE user_id=$1", owner) == 0)
        calls = []
        async def handler(_):
            calls.append(True)
        execution = await process_job_async(str(jid), session_factory=factory, handler=handler)
        check(not execution.executed and not calls)
        await act(command(owner, "reactivate"))
        check(await db.fetchval("SELECT state FROM jobs WHERE id=$1", jid) == "cancelled")
    groups[phase] = True

    phase = "published"
    owner = await seed()
    jid, _, event, reservation = await admit(owner)
    await db.execute("UPDATE outbox_events SET status='published',published_at=$2 WHERE id=$1", event, NOW)
    check((await act(command(owner))).after["cancelled_jobs"] == 0)
    check(await db.fetchval("SELECT state FROM jobs WHERE id=$1", jid) == "pending")
    check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "held")
    execution = await process_job_async(str(jid), session_factory=factory, handler=finish)
    check(execution.executed)
    check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "settled")
    check(await status(owner) == "suspended")
    groups[phase] = True

    phase = "pipeline"
    owner = await seed()
    parent, child, _, reservation = await admit(owner, pipeline=True)
    check((await act(command(owner))).after["cancelled_jobs"] == 2)
    check(await db.fetchval("SELECT count(*) FROM jobs WHERE id=ANY($1) AND state='cancelled'", [parent, child]) == 2)
    check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "released")
    for failed in (False, True):
        owner = await seed()
        parent, child, event, reservation = await admit(owner, pipeline=True)
        await db.execute("UPDATE outbox_events SET status='published',published_at=$2 WHERE id=$1", event, NOW)
        check((await act(command(owner))).after["cancelled_jobs"] == 0)
        check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "held")
        check(await db.fetchval("SELECT state FROM jobs WHERE id=$1", child) == "pending")
        await finish(parent, failed=failed)
        async with factory() as session:
            job = await session.get(Job, parent)
            if failed:
                result = await pipeline_link.fail_blocked_children_for_parent(session, job)
                check(result.cancelled_count == 1 and result.failed_count == 0)
            else:
                result = await pipeline_link.link_completed_parent(session, job)
                check(result.reason == "user_suspended")
        check(await db.fetchval("SELECT state FROM jobs WHERE id=$1", child) == "cancelled")
        check(await db.fetchval("SELECT count(*) FROM outbox_events WHERE aggregate_id=$1", child) == 0)
        check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == ("released" if failed else "settled"))
        check(await db.fetchval("SELECT sum(reserved_microcredits) FROM credit_grants WHERE user_id=$1", owner) == 0)
        check(await db.fetchval("SELECT sum(consumed_microcredits) FROM credit_grants WHERE user_id=$1", owner) == (0 if failed else 50_000_000))
    groups[phase] = True

    phase = "rollback"
    owner = await seed()
    auth, secret = await session_for(owner)
    jid, _, event, reservation = await admit(owner)
    await act(command(owner), rollback=True)
    check(await status(owner) == "active")
    check(await db.fetchval("SELECT state FROM jobs WHERE id=$1", jid) == "pending")
    check(await db.fetchval("SELECT status FROM outbox_events WHERE id=$1", event) == "pending")
    check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "held")
    check((await auth.authenticate(secret)).id == owner)
    groups[phase] = True

    phase = "races"
    async def wait_blocked():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if await db.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND application_name='suspension-proof' AND cardinality(pg_blocking_pids(pid))>0"):
                check(True)
                return
            await asyncio.sleep(.01)
        raise AssertionError("lock_not_observed")

    # Dispatcher publication owns its row before suspension: published work survives.
    owner = await seed()
    jid, _, event, reservation = await admit(owner)
    transaction = db.transaction()
    await transaction.start()
    await db.execute("SELECT id FROM outbox_events WHERE id=$1 FOR UPDATE", event)
    task = asyncio.create_task(act(command(owner)))
    try:
        await wait_blocked()
        await db.execute("UPDATE outbox_events SET status='published',published_at=$2 WHERE id=$1", event, NOW)
    finally:
        await transaction.commit()
    result = await task
    races += 1
    check(result.after["cancelled_jobs"] == 0)
    check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", reservation) == "held")

    # User-lock ordering: suspension precedes a new admission and authentication.
    for authenticate in (False, True):
        owner = await seed()
        auth, secret = await session_for(owner)
        transaction = db.transaction()
        await transaction.start()
        await db.execute("SELECT id FROM users WHERE id=$1 FOR UPDATE", owner)
        suspension = asyncio.create_task(act(command(owner)))
        try:
            await wait_blocked()
            other = asyncio.create_task(auth.authenticate(secret) if authenticate else admit(owner))
        finally:
            await transaction.commit()
        await suspension
        result = await asyncio.gather(other, return_exceptions=True)
        races += 1
        check(isinstance(result[0], (AuthError, gc.GenerationCreditError)))
        check(await status(owner) == "suspended")
        check(await db.fetchval("SELECT count(*) FROM jobs WHERE owner_user_id=$1", owner) == 0)

    owner = await seed()
    cmd = command(owner)
    transaction = db.transaction()
    await transaction.start()
    await db.execute("SELECT id FROM users WHERE id=$1 FOR UPDATE", owner)
    tasks = [asyncio.create_task(act(cmd)) for _ in range(8)]
    try:
        await wait_blocked()
    finally:
        await transaction.commit()
    results = await asyncio.gather(*tasks)
    races += 1
    check(sum(not result.replayed for result in results) == 1)
    check(await db.fetchval("SELECT count(*) FROM master_audit WHERE request_id=$1", cmd.request_id) == 1)
    check(await status(owner) == "suspended")
    groups[phase] = True
    return dict(groups=groups, races=races, checks=checks, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(os.environ.get("MASTER_SUSPENSION_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"application_name": "suspension-proof"}})
    try:
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        assert await db.fetchval("SELECT count(*) FROM users") == 0
        result = await proof(db, async_sessionmaker(engine, expire_on_commit=False))
        print(json.dumps(result))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("master_proof_failed:" + phase)
        sys.exit(1)
