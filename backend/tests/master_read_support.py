"""Fixed disposable PostgreSQL snapshot proof; output contains counts only."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from uuid import uuid4

from app.schema_revision import CODE_REVISION as HEAD

GROUPS = ("guards", "users", "cycles", "credits", "jobs", "audit", "privacy", "snapshot")
phase = "guard"
T = datetime(2025, 1, 1, tzinfo=timezone.utc)
NOW = T + timedelta(days=1)


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"master-read-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.database != project.replace("-", "_") or provider != "mock" or app_env != "test"):
        raise ValueError("master_proof_target_refused")


async def proof(db, factory):
    from sqlalchemy import text
    from app.master_read import read_master, MasterReadError, MODELS, METER_UNITS
    from app.master_admin import administer, MasterCommand
    from app.credit_lifecycle import ensure_cycle, change_plan, grant_bonus
    from app.credit_accounting import reserve, settle, release, ReservationRequest, UsageEstimate, UsageReport, UsageLine

    global phase
    checks, races, groups = 0, 0, {}

    def check(value):
        nonlocal checks
        assert value, "master_read_assertion"
        checks += 1

    async def seed(role="user", origin="synthetic"):
        uid, marker = uuid4(), uuid4().hex
        await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,"
            "signed_up_at,updated_at) VALUES($1,$2,$3,$4,$5,'active',$6,$7,$7)", uid,
            marker if origin == "oauth" else None, marker+"@example.invalid" if origin == "oauth" else None,
            origin == "oauth", role, origin, T)
        return uid

    master = await seed("master", "oauth")
    users = [await seed() for _ in range(7)]

    async def read(view="users", actor=None, now=NOW, **params):
        async with factory() as session:
            return await read_master(session, actor_id=master if actor is None else actor,
                view=view, now=now, **params)

    async def account(uid, plan="free"):
        async with factory() as session, session.begin():
            await ensure_cycle(session, user_id=uid, now=NOW)
            if plan != "free":
                await change_plan(session, user_id=uid, target_plan=plan, operation_key="plan_"+uuid4().hex, now=NOW)

    async def reserve_one(uid, meter="imagen_fast_image", units=1):
        async with factory() as session, session.begin():
            return await reserve(session, request=ReservationRequest(uid, "reserve_"+uuid4().hex,
                (UsageEstimate(meter, units),)), now=NOW)

    async def terminal(uid, receipt, meter="imagen_fast_image", units=1, delivered=True):
        async with factory() as session, session.begin():
            if delivered:
                await settle(session, user_id=uid, reservation_id=receipt.reservation_id,
                    usage=UsageReport((UsageLine(meter, units, "mock_estimate"),)), delivery="delivered",
                    operation_key="settle_"+uuid4().hex, now=NOW)
            else:
                await release(session, user_id=uid, reservation_id=receipt.reservation_id,
                    operation_key="release_"+uuid4().hex, usage=UsageReport(()), reason_code="provider_failed", now=NOW)

    async def item(uid, now=NOW):
        return next(r for r in (await read(now=now))["items"] if r["id"] == uid)

    phase = "guards"
    for actor in [users[0], uuid4()]:
        try:
            await read(actor=actor)
        except MasterReadError as error:
            check(error.code == "master_required")
        else:
            raise AssertionError("guard_missing")
    for kwargs in [dict(days=0), dict(days=91), dict(limit=51), dict(origin="remote"), dict(status="removed")]:
        try:
            await read(**kwargs)
        except MasterReadError as error:
            check(error.code == "master_input_invalid")
        else:
            raise AssertionError("input_guard_missing")
    groups[phase] = True

    phase = "users"
    before = await db.fetchval("SELECT count(*) FROM credit_accounts")
    page, seen = await read(limit=2), []
    while True:
        check(len(page["items"]) <= 2)
        seen += [r["id"] for r in page["items"]]
        if page["next_cursor"] is None:
            break
        page = await read(limit=2, after=page["next_cursor"])
    check(seen == sorted([master, *users]))
    check(len(set(seen)) == 8)
    check(await db.fetchval("SELECT count(*) FROM credit_accounts") == before)
    check(len((await read(origin="oauth"))["items"]) == 1)
    check(len((await read(origin="synthetic"))["items"]) == 7)
    check((await item(master))["plan"] == "max")
    check((await read(status="suspended"))["items"] == [])
    empty = await read("overview", origin="oauth")
    check(empty["success_rate"] is None and empty["terminal_count"] == 0)
    for meter in empty["usage"]:
        check(meter["observed_units"] == "0" and meter["charged_microcredits"] == "0")
    groups[phase] = True

    phase = "cycles"
    await account(users[0], "pro")
    async with factory() as session, session.begin():
        await change_plan(session, user_id=users[0], target_plan="free", operation_key="downgrade", now=NOW)
        await grant_bonus(session, user_id=users[0], amount_microcredits=101,
            operation_key="bonus", expires_at=None, reason_code="support_adjustment", now=NOW)
    old = await item(users[0])
    check(old["plan"] == "pro" and old["pending_plan"] == "free")
    check(old["balance_materialized"])
    before = await db.fetchval("SELECT count(*) FROM credit_cycles")
    new = await item(users[0], T+timedelta(days=30))
    check(new["plan"] == "free" and new["pending_plan"] is None)
    check(new["available_microcredits"] == "1000000101")
    check(new["cycle_starts_at"] == T+timedelta(days=30))
    check(new["renews_at"] == T+timedelta(days=60))
    check(not new["balance_materialized"])
    check(await db.fetchval("SELECT count(*) FROM credit_cycles") == before)
    for uid, plan in zip(users[1:4], ("free", "pro", "max")):
        await account(uid, plan)
        check((await item(uid))["plan"] == plan)
    groups[phase] = True

    phase = "credits"
    uid = users[3]
    for meter, _ in METER_UNITS:
        receipt = await reserve_one(uid, meter)
        await terminal(uid, receipt, meter)
    held = await reserve_one(uid)
    released = await reserve_one(uid)
    await terminal(uid, released, delivered=False)
    overview = await read("overview")
    check(len(overview["usage"]) == 7)
    for r in overview["usage"]:
        check(r["observed_units"] == "1")
        check(int(r["charged_microcredits"]) > 0)
    max_credit = next(r for r in overview["credits"] if r["plan"] == "max")
    check(max_credit["held_microcredits"] == "50000000")
    check(max_credit["released_microcredits"] == "50000000")
    check(int(max_credit["reserved_microcredits"]) == int(max_credit["held_microcredits"])
        + int(max_credit["charged_microcredits"]) + int(max_credit["released_microcredits"]))
    check((await item(uid))["held_microcredits"] == "50000000")
    check(sum(int(r["charged_microcredits"]) for r in overview["daily"])
        == int(max_credit["charged_microcredits"]))
    check(overview["plan_attribution"] == "current_persisted_account_plan")
    groups[phase] = True

    phase = "jobs"
    model = sorted(MODELS)[0]
    for state, seconds in [("completed", 10), ("completed", 20), ("failed", 30), ("cancelled", 40)]:
        await db.execute("INSERT INTO jobs(id,owner_user_id,mode,model,state,prompt,parameters,"
            "attempts,blocked,state_history,vertex_charged,created_at,updated_at,error) VALUES($1,$2,'t2i',$3,$4,'private',"
            "'{}',0,false,'[]',false,$5,$6,$7::jsonb)", uuid4(), uid, model, state, NOW-timedelta(seconds=60),
            NOW-timedelta(seconds=60-seconds), json.dumps({"code":"private_error", "message":"private"}))
    overview = await read("overview")
    check(overview["terminal_count"] == 3)
    check(overview["success_rate"] == 2/3)
    completed = next(r for r in overview["jobs"] if r["state"] == "completed")
    check(completed["p95_seconds"] == 19.5)
    check(overview["errors"] == [dict(code="other", count=1)])
    check(overview["recent_failures"][0]["code"] == "other")
    check(overview["recent_failures"][0]["model"] == model)
    check(overview["duration_definition"] == "queue_inclusive_updated_minus_created")
    check((await read("overview", origin="oauth"))["terminal_count"] == 0)
    groups[phase] = True

    phase = "audit"
    async def command():
        async with factory() as session, session.begin():
            return await administer(session, actor_id=master, command=MasterCommand(users[1], uuid4(),
                "bonus_grant", "support_adjustment", amount_microcredits=17), now=NOW)
    receipts = [await command() for _ in range(3)]
    first = await read("audit", limit=2)
    second = await read("audit", limit=2, after=first["next_cursor"])
    audit = first["items"]+second["items"]
    check(len(audit) == 3 and len({r["request_id"] for r in audit}) == 3)
    check(second["next_cursor"] is None)
    for r in audit:
        check(r["after"]["bonus_microcredits"] == "17")
        check(r["actor_id"] == master and r["target_id"] == users[1])
        check(r["reason_code"] == "support_adjustment")
    check({r["request_id"] for r in audit} == {r.request_id for r in receipts})
    groups[phase] = True

    phase = "privacy"
    for view in ("users", "overview", "audit"):
        payload = await read(view)
        serialized = json.dumps(payload, default=str)
        for forbidden in ("@example", "private_error", "private\"", "google_sub", "email", "payload_fingerprint"):
            check(forbidden not in serialized)
    async with factory() as session:
        async with session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            try:
                await session.execute(text("UPDATE users SET updated_at=updated_at"))
            except Exception as error:
                check(getattr(getattr(error, "orig", None), "sqlstate", None) == "25006")
            else:
                raise AssertionError("read_only_missing")
    groups[phase] = True

    phase = "snapshot"
    # Gate after the actor SELECT has acquired the MVCC snapshot, not with sleeps.
    async def interleave(writer):
        nonlocal races
        reached, resume = asyncio.Event(), asyncio.Event()
        async with factory() as raw:
            class Gate:
                def __getattr__(self, key):
                    return getattr(raw, key)
                async def execute(self, statement, *args, **kwargs):
                    result = await raw.execute(statement, *args, **kwargs)
                    if "SELECT id FROM users" in str(statement):
                        reached.set()
                        await asyncio.wait_for(resume.wait(), 5)
                    return result
            before = await read()
            task = asyncio.create_task(read_master(Gate(), actor_id=master, view="users", now=NOW))
            await asyncio.wait_for(reached.wait(), 5)
            try:
                await writer()
            finally:
                resume.set()
            during = await asyncio.wait_for(task, 5)
            after = await read()
            check(during == before)
            check(after != before)
            races += 1

    saved = []
    async def make_hold():
        saved.append(await reserve_one(users[2]))
    await interleave(make_hold)
    await interleave(lambda: terminal(users[2], saved[0]))
    await interleave(command)
    check(races == 3)
    groups[phase] = True
    check(set(groups) == set(GROUPS))
    return dict(groups=groups, races=races, checks=checks, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(os.environ.get("MASTER_READ_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        assert await db.fetchval("SELECT count(*) FROM users") == 0
        print(json.dumps(await proof(db, async_sessionmaker(engine, expire_on_commit=False))))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("master_proof_failed:"+phase)
        sys.exit(1)
