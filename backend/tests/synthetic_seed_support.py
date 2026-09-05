"""Owned, full-size synthetic fixture proof. Never output row data or SQL."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from types import SimpleNamespace
from uuid import uuid4

from app.schema_revision import CODE_REVISION as HEAD

GROUPS = ("guards", "dryrun", "seed", "distribution", "accounting", "replay", "denials", "readmodel")
ASOF = datetime(2026, 9, 5, tzinfo=timezone.utc)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"master-seed-verify-[a-f0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.database != project.replace("-", "_") or provider != "mock" or app_env != "test"):
        raise ValueError("seed_proof_target_refused")


async def proof(db, factory, database):
    from sqlalchemy import text, delete
    from app.synthetic_seed import SeedError, seed_fixture, fixture_users, fixture_jobs, LOCK_KEY
    from app.synthetic_seed_cli import run, validate_target as cli_guard
    from app.master_read import read_master
    from app.models import Job

    global phase
    checks, races, groups = 0, 0, {}
    def check(value):
        nonlocal checks
        assert value, "seed_assertion"
        checks += 1

    phase = "guards"
    settings = SimpleNamespace(database_url="postgresql+asyncpg://db/"+database, ai_provider="mock", app_env="test")
    for changes in (dict(ai_provider="vertex"), dict(app_env="production"), dict(database_url="postgresql://remote/"+database)):
        try:
            cli_guard(SimpleNamespace(**(vars(settings) | changes)), database, True, "SEED")
        except SeedError:
            check(True)
        else:
            raise AssertionError("guard_missing")
    master, marker = uuid4(), uuid4().hex
    await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
        "VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)", master, marker, marker+"@example.invalid", ASOF-timedelta(days=10))
    groups[phase] = True

    async def counts():
        return tuple([await db.fetchval("SELECT count(*) FROM "+table) for table in
            ("users", "jobs", "credit_accounts", "credit_reservations", "credit_usage_records", "credit_grants", "credit_ledger_events")])
    args = SimpleNamespace(expected_database=database, execute=False, confirm=None, as_of=ASOF)
    phase = "dryrun"
    before = await counts()
    preview = await run(args)
    check(preview["mode"] == "preview" and not preview["replayed"])
    check(await counts() == before)
    check(preview["users"] == 120 and preview["jobs"] == 3000)
    groups[phase] = True

    phase = "seed"
    args.execute, args.confirm = True, "SEED"
    result = await run(args)
    check(not result["replayed"] and result["mode"] == "apply")
    check(await db.fetchval("SELECT count(*) FROM users") == 121)
    check(await db.fetchval("SELECT count(*) FROM jobs") == 3000)
    check(await db.fetchval("SELECT count(*) FROM user_sessions") == 0)
    check(await db.fetchval("SELECT count(*) FROM outbox_events") == 0)
    check(await db.fetchval("SELECT count(*) FROM assets") == 0)
    check(await db.fetchval("SELECT role FROM users WHERE id=$1", master) == "master")
    groups[phase] = True

    phase = "distribution"
    plans = {r["plan"]: r["n"] for r in await db.fetch("SELECT plan,count(*) n FROM credit_accounts GROUP BY plan")}
    check(plans == dict(free=84, pro=30, max=6))
    check(await db.fetchval("SELECT count(*) FROM users WHERE data_origin='synthetic' AND status='suspended'") == 12)
    check(await db.fetchval("SELECT count(*) FROM users u WHERE data_origin='synthetic' AND NOT EXISTS "
        "(SELECT 1 FROM jobs j WHERE j.owner_user_id=u.id AND j.created_at>$1)", ASOF-timedelta(days=30)) == 12)
    check(await db.fetchval("SELECT count(DISTINCT model) FROM jobs") == 5)
    check(await db.fetchval("SELECT count(*) FROM credit_grants WHERE kind='bonus' AND reason_code='synthetic_fixture'") == 9)
    check(await db.fetchval("SELECT min(created_at)>=$1 AND max(created_at)<$2 FROM jobs", ASOF-timedelta(days=90), ASOF))
    states = {r["state"]: r["n"] for r in await db.fetch("SELECT state::text,count(*) n FROM jobs GROUP BY state")}
    check(states == dict(completed=2400, failed=360, cancelled=240))
    for u in fixture_users(ASOF):
        found = await db.fetchrow("SELECT google_sub,email,email_verified,role::text,status::text FROM users WHERE id=$1", u.id)
        check(found["google_sub"] is None and found["email"] is None and not found["email_verified"] and found["role"] == "user")
        check(await db.fetchval("SELECT count(*) FROM jobs WHERE owner_user_id=$1", u.id) == 25)
    groups[phase] = True

    phase = "accounting"
    check(await db.fetchval("SELECT count(*) FROM credit_reservations") == 3000)
    check(await db.fetchval("SELECT count(*) FROM credit_usage_records") == 9000)
    check(await db.fetchval("SELECT count(DISTINCT meter) FROM credit_usage_records") == 7)
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE status='held'") == 0)
    check(await db.fetchval("SELECT coalesce(sum(reserved_microcredits),0) FROM credit_grants") == 0)
    check(await db.fetchval("SELECT sum(consumed_microcredits) FROM credit_grants") ==
          await db.fetchval("SELECT sum(charged_microcredits) FROM credit_usage_records"))
    check(await db.fetchval("SELECT count(*) FROM credit_usage_records WHERE delivery='no_deliverable' AND charged_microcredits<>0") == 0)
    check(await db.fetchval("SELECT count(*) FROM credit_grants g LEFT JOIN (SELECT grant_id,sum(granted_delta) granted,"
        "sum(reserved_delta) reserved,sum(consumed_delta) consumed,sum(expired_delta) expired FROM credit_ledger_events GROUP BY grant_id) l "
        "ON l.grant_id=g.id WHERE l.granted IS DISTINCT FROM g.granted_microcredits OR l.reserved IS DISTINCT FROM g.reserved_microcredits "
        "OR l.consumed IS DISTINCT FROM g.consumed_microcredits OR l.expired IS DISTINCT FROM g.expired_microcredits") == 0)
    groups[phase] = True

    phase = "replay"
    before = await counts()
    replay = await run(args)
    check(replay["replayed"] and await counts() == before)
    args.as_of = ASOF+timedelta(days=1)
    try:
        await run(args)
    except SeedError:
        check(await counts() == before)
    else:
        raise AssertionError("marker_conflict_missing")
    args.as_of = ASOF
    async with factory() as session, session.begin():
        one = fixture_jobs(fixture_users(ASOF)[0], ASOF)[0].id
        await session.execute(delete(Job).where(Job.id == one))
        try:
            await seed_fixture(session, as_of=ASOF)
        except SeedError:
            check(True)
        else:
            raise AssertionError("partial_conflict_missing")
        await session.rollback()
    check(await counts() == before)
    async def concurrent_replay():
        async with factory() as session, session.begin():
            return await seed_fixture(session, as_of=ASOF)
    lock = db.transaction()
    await lock.start()
    await db.execute("SELECT pg_advisory_xact_lock($1)", LOCK_KEY)
    task = asyncio.create_task(concurrent_replay())
    try:
        observed = False
        for _ in range(100):
            if await db.fetchval("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='seed-proof' "
                                 "AND cardinality(pg_blocking_pids(pid))>0)"):
                observed = True
                break
            await asyncio.sleep(.01)
        check(observed)
    finally:
        await lock.commit()
    check((await task)["replayed"])
    races += 1
    check(await counts() == before)
    groups[phase] = True

    phase = "denials"
    check(result["denial_observations"] == dict(plan=1, quota=1, concurrency=1))
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE reserve_operation_key LIKE 'seed_probe_%'") == 0)
    check(await db.fetchval("SELECT count(*) FROM jobs WHERE state='failed'") == 360)
    groups[phase] = True

    phase = "readmodel"
    async with factory() as session:
        overview = await read_master(session, actor_id=master, view="overview", now=ASOF, days=90, origin="synthetic")
    check(sum(r["count"] for r in overview["counts"]) == 120)
    check(overview["terminal_count"] == 2760)
    check(len(overview["usage"]) == 7)
    check(sum(int(r["charged_microcredits"]) for r in overview["usage"]) ==
          await db.fetchval("SELECT sum(charged_microcredits) FROM credit_usage_records"))
    check(sum(r["count"] for r in overview["jobs"]) == 3000)
    check(all(r["held_microcredits"] == "0" for r in overview["credits"]))
    check(all(r["model"] != "unknown" for r in overview["jobs"]))
    groups[phase] = True
    check(set(groups) == set(GROUPS))
    return dict(groups=groups, races=races, checks=checks, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(os.environ.get("SYNTHETIC_SEED_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"application_name": "seed-proof"}})
    try:
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        assert await db.fetchval("SELECT count(*) FROM users") == 0
        print(json.dumps(await proof(db, async_sessionmaker(engine, expire_on_commit=False), url.database)))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        kind = type(error).__name__
        if kind not in {"SeedError", "CreditAccountingError", "CreditLifecycleError", "IntegrityError", "ProgrammingError", "AssertionError", "TypeError", "AttributeError"}:
            kind = "other"
        code = getattr(error, "code", "none")
        if code not in {"monthly_credit_exhausted", "credit_plan_refused", "credit_input_invalid", "credit_account_inconsistent", "user_concurrency_limit"}:
            code = "none"
        print("master_proof_failed:"+phase+":"+kind+":"+code)
        sys.exit(1)
