"""Fixed isolated PostgreSQL proof. Executed as source in owned migrate containers."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import time
from uuid import UUID

LEGACY = ("users", "user_sessions", "jobs", "assets", "prompt_enhancements", "outbox_events")
CREDIT = ("credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events")
NOW = datetime(2024, 3, 1, 13, tzinfo=timezone.utc)
HEAD = "0005_credit_lifecycle_operations"
PHASES = ("guard", "additive", "metadata", "constraints", "ledger", "races", "downgrade", "done")
phase = "guard"


def uid(number):
    return UUID(int=30000 + number)


def validate_target(project, url, provider, app_env, mode, database):
    if (not re.fullmatch(r"schema-verify-[a-z0-9]{8,32}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or not database or url.database != database
            or provider != "mock" or app_env != "test" or mode not in ("additive", "credit")):
        raise ValueError("credit_proof_target_refused")


async def migrate(direction, target, expected=None):
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "alembic", direction, target,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        output, error = await asyncio.wait_for(process.communicate(), 30)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.communicate()
        raise
    if expected is None:
        assert process.returncode == 0, "migration_failed"
    else:
        assert process.returncode != 0 and expected.encode() in output + error, "migration_refusal_missing"


async def snapshot(connection, tables):
    # Private in-memory comparisons; never emit rows or hashes of identities.
    return {table: await connection.fetch(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1") for table in tables}


async def insert(connection, table, values):
    assert table in CREDIT
    columns = ",".join(values)
    placeholders = ",".join(f"${i}" for i in range(1, len(values)+1))
    return await connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", *values.values())


def account(user_id=uid(1), **overrides):
    return dict(dict(user_id=user_id, cycle_anchor_at=NOW, plan="free", pending_plan=None,
                     created_at=NOW, updated_at=NOW), **overrides)


def cycle(id=uid(10), user_id=uid(1), **overrides):
    return dict(dict(id=id, user_id=user_id, cycle_index=0, starts_at=NOW, ends_at=NOW+timedelta(days=30),
                     plan="free", allowance_microcredits=1_000_000_000, created_at=NOW), **overrides)


def grant(id=uid(20), user_id=uid(1), **overrides):
    return dict(dict(id=id, user_id=user_id, cycle_id=uid(10), kind="base", created_at=NOW,
                     expires_at=NOW+timedelta(days=30), granted_microcredits=0, reserved_microcredits=0,
                     consumed_microcredits=0, expired_microcredits=0, reason_code="fixture"), **overrides)


def event(id=uid(30), **overrides):
    return dict(dict(id=id, user_id=uid(1), grant_id=uid(20), kind="grant", operation_key="fixture",
                     rate_card_version="v1", granted_delta=1000, reserved_delta=0,
                     consumed_delta=0, expired_delta=0, created_at=NOW, reason_code="fixture"), **overrides)


async def seed_user(connection, user_id):
    await connection.execute("INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                             "VALUES ($1,false,'user','active','synthetic',$2,$2)", user_id, NOW)


async def additive(connection):
    await migrate("downgrade", "0003_content_ownership")
    for table in CREDIT:
        assert await connection.fetchval("SELECT to_regclass($1)", table) is None
    await seed_user(connection, uid(99))
    await connection.execute("INSERT INTO user_sessions(id,user_id,token_hash,created_at,last_seen_at,absolute_expires_at) "
                             "VALUES ($1,$2,$3,$4,$4,$5)", uid(98), uid(99), bytes([19])*32, NOW, NOW+timedelta(days=7))
    await connection.execute("INSERT INTO prompt_enhancements(id,owner_user_id,original,enhanced,components,target_mode,target_model,llm_model,created_at) "
                             "VALUES ($1,$2,'fixture','fixture','{}','t2i','mock','mock',$3)", uid(97), uid(99), NOW)
    await connection.execute("INSERT INTO jobs(id,owner_user_id,mode,model,state,prompt,enhancement_id,blocked,attempts,parameters,state_history,vertex_charged,created_at,updated_at) "
                             "VALUES ($1,$2,'t2i','mock','failed','fixture',$3,false,0,'{}','[]',false,$4,$4)", uid(96), uid(99), uid(97), NOW)
    await connection.execute("INSERT INTO assets(id,job_id,kind,local_path,mime,size_bytes,created_at) "
                             "VALUES ($1,$2,'image','credit-proof.bin','image/png',1,$3)", uid(95), uid(96), NOW)
    await connection.execute("INSERT INTO outbox_events(id,event_type,aggregate_type,aggregate_id,payload,status,attempts,created_at,updated_at) "
                             "VALUES ($1,'fixture','job',$2,'{}','pending',0,$3,$3)", uid(94), uid(96), NOW)
    rows = await snapshot(connection, LEGACY)
    async def schema():
        columns = await connection.fetch("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns "
                                         "WHERE table_schema='public' AND table_name=ANY($1::text[]) ORDER BY 1,2", list(LEGACY))
        constraints = await connection.fetch("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint "
                                             "WHERE conrelid IN (SELECT oid FROM pg_class WHERE relname=ANY($1::text[]) AND relnamespace='public'::regnamespace) ORDER BY 1", list(LEGACY))
        indexes = await connection.fetch("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=ANY($1::text[]) ORDER BY 1", list(LEGACY))
        return columns, constraints, indexes
    before_schema = await schema()
    await migrate("upgrade", "head")
    assert await snapshot(connection, LEGACY) == rows and await schema() == before_schema
    assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
    for table in CREDIT:
        assert await connection.fetchval(f"SELECT count(*) FROM {table}") == 0
    for table, number in (("outbox_events",94),("assets",95),("jobs",96),("prompt_enhancements",97),("user_sessions",98),("users",99)):
        await connection.execute(f"DELETE FROM {table} WHERE id=$1", uid(number))


async def metadata():
    from sqlalchemy.ext.asyncio import create_async_engine
    from alembic.migration import MigrationContext
    from alembic.autogenerate import compare_metadata
    import app.models
    import app.credit_models
    from app.db import Base
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(lambda c: compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata))
            assert not differences, "metadata_mismatch"
    finally:
        await engine.dispose()


async def credit(connection, dsn):
    import asyncpg
    global phase
    checks = 0
    async def reject(table, values, sqlstate, constraint=None):
        nonlocal checks
        before = await snapshot(connection, LEGACY+CREDIT)
        tx = connection.transaction()
        await tx.start()
        try:
            try:
                await insert(connection, table, values)
            except asyncpg.PostgresError as error:
                assert error.sqlstate == sqlstate
                if constraint:
                    assert error.constraint_name == constraint
            else:
                raise AssertionError("constraint_not_enforced")
        finally:
            await tx.rollback()
        assert await snapshot(connection, LEGACY+CREDIT) == before
        checks += 1
    for number in (1,2,3):
        await seed_user(connection, uid(number))
    await insert(connection, "credit_accounts", account())
    await insert(connection, "credit_accounts", account(uid(2)))
    phase = "constraints"
    await reject("credit_accounts", account(), "23505")
    await reject("credit_accounts", account(uid(999)), "23503")
    for change in (dict(plan="bad"), dict(pending_plan="free"), dict(pending_plan="bad"),
                   dict(created_at=NOW-timedelta(microseconds=1)), dict(updated_at=NOW-timedelta(seconds=1))):
        await reject("credit_accounts", account(uid(3), **change), "23514")
    await insert(connection, "credit_cycles", cycle())
    await insert(connection, "credit_cycles", cycle(uid(11), uid(2)))
    await reject("credit_cycles", cycle(uid(12)), "23505")
    for change in (dict(cycle_index=-1), dict(ends_at=NOW+timedelta(days=30,microseconds=1)),
                   dict(created_at=NOW-timedelta(seconds=1)), dict(plan="bad"), dict(allowance_microcredits=-1)):
        await reject("credit_cycles", cycle(uid(12), **change), "23514")
    await reject("credit_cycles", cycle(uid(12), uid(999)), "23503")
    # Session timezone must not turn 30 days into a DST calendar interval.
    await connection.execute("SET TIME ZONE 'America/New_York'")
    tx = connection.transaction()
    await tx.start()
    await insert(connection, "credit_cycles", cycle(uid(12), cycle_index=9))
    await tx.rollback()
    await connection.execute("SET TIME ZONE 'UTC'")
    checks += 1
    await insert(connection, "credit_grants", grant())
    await insert(connection, "credit_grants", grant(uid(21), uid(2), cycle_id=None, kind="bonus", expires_at=None))
    await reject("credit_grants", grant(uid(22)), "23505")
    await reject("credit_grants", grant(uid(22), cycle_id=uid(11)), "23503", "fk_credit_grants_cycle_owner")
    for change in (dict(kind="bad"), dict(cycle_id=None), dict(expires_at=None), dict(kind="bonus"),
                   dict(expires_at=NOW), dict(reason_code="unsafe reason"),
                   *(dict(**{field:-1}) for field in ("granted_microcredits","reserved_microcredits","consumed_microcredits","expired_microcredits")),
                   dict(reserved_microcredits=1), dict(granted_microcredits=2**63-1,reserved_microcredits=2**63-1,consumed_microcredits=1)):
        await reject("credit_grants", grant(uid(22), **change), "23514")
    # BIGINT overflow checked by PostgreSQL, not asyncpg's client serializer.
    before = await snapshot(connection, CREDIT)
    tx = connection.transaction()
    await tx.start()
    try:
        try:
            await connection.execute("UPDATE credit_grants SET granted_microcredits=9223372036854775808 WHERE id=$1", uid(20))
        except asyncpg.NumericValueOutOfRangeError:
            checks += 1
        else:
            raise AssertionError("overflow_not_rejected")
    finally:
        await tx.rollback()
    assert await snapshot(connection, CREDIT) == before
    for sql in ("DELETE FROM users WHERE id=$1", "DELETE FROM credit_accounts WHERE user_id=$1"):
        tx = connection.transaction()
        await tx.start()
        try:
            try:
                await connection.execute(sql, uid(1))
            except asyncpg.ForeignKeyViolationError:
                checks += 1
            else:
                raise AssertionError("delete_restrict_missing")
        finally:
            await tx.rollback()
    for change in (dict(operation_key="unsafe key"), dict(operation_key=""), dict(rate_card_version="v0"),
                   dict(reason_code="unsafe reason"), dict(kind="unknown"), dict(granted_delta=0),
                   dict(kind="reserve", granted_delta=0, reserved_delta=-1),
                   dict(kind="settle", granted_delta=0, reserved_delta=-1, consumed_delta=2),
                   dict(kind="release", granted_delta=0, reserved_delta=-1, consumed_delta=1),
                   dict(kind="expire", granted_delta=0, expired_delta=-1)):
        await reject("credit_ledger_events", event(**change), "23514")
    await reject("credit_ledger_events", event(user_id=uid(2)), "23503", "fk_credit_ledger_grant_owner")
    await reject("credit_ledger_events", event(grant_id=uid(999)), "23503")
    for table, values in (("credit_accounts",account(uid(3))), ("credit_cycles",cycle(uid(12))),
                          ("credit_grants",grant(uid(22))), ("credit_ledger_events",event())):
        for field, value in values.items():
            if value is not None and not (table == "credit_grants" and field in ("cycle_id", "expires_at")):
                # Nullable expiry for bonus grants is already exercised above.
                await reject(table, dict(values, **{field:None}), "23502")
    phase = "ledger"
    fixtures = [event(), event(uid(31),kind="adjust",granted_delta=100),
                event(uid(32),kind="reserve",granted_delta=0,reserved_delta=400),
                event(uid(33),kind="settle",granted_delta=0,reserved_delta=-250,consumed_delta=200),
                event(uid(34),kind="release",granted_delta=0,reserved_delta=-100,expired_delta=50),
                event(uid(35),kind="expire",granted_delta=0,expired_delta=25)]
    async with connection.transaction():
        for row in fixtures:
            await insert(connection, "credit_ledger_events", row)
        await connection.execute("UPDATE credit_grants SET granted_microcredits=1100,reserved_microcredits=50,consumed_microcredits=200,expired_microcredits=75 WHERE id=$1", uid(20))
    await reject("credit_ledger_events", event(uid(36)), "23505", "uq_credit_ledger_operation")
    for sql in ("UPDATE credit_ledger_events SET reason_code='changed'", "DELETE FROM credit_ledger_events", "TRUNCATE credit_ledger_events"):
        before = await snapshot(connection, CREDIT)
        tx = connection.transaction()
        await tx.start()
        try:
            try:
                await connection.execute(sql)
            except asyncpg.CheckViolationError as error:
                assert str(error) == "credit_ledger_append_only"
                checks += 1
            else:
                raise AssertionError("append_only_missing")
        finally:
            await tx.rollback()
        assert await snapshot(connection, CREDIT) == before
    # Force rollback after both projection and ledger writes without deleting history.
    before = await snapshot(connection, CREDIT)
    tx = connection.transaction()
    await tx.start()
    await connection.execute("UPDATE credit_grants SET granted_microcredits=1101 WHERE id=$1", uid(20))
    await insert(connection, "credit_ledger_events", event(uid(36),kind="adjust",operation_key="rollback",granted_delta=1))
    await tx.rollback()
    assert await snapshot(connection, CREDIT) == before
    checks += 1
    phase = "races"
    async def race(table, first, second, adjust=False):
        nonlocal checks
        a, b = await asyncpg.connect(dsn), await asyncpg.connect(dsn)
        pending = None
        count = await connection.fetchval(f"SELECT count(*) FROM {table}")
        try:
            await a.execute("BEGIN")
            await insert(a, table, first)
            if adjust:
                await a.execute("UPDATE credit_grants SET granted_microcredits=granted_microcredits+1 WHERE id=$1", uid(20))
            pid = await b.fetchval("SELECT pg_backend_pid()")
            pending = asyncio.create_task(insert(b, table, second))
            deadline = time.monotonic()+5
            while not await connection.fetchval("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=$1", pid):
                assert not pending.done() and time.monotonic() < deadline, "unique_lock_not_observed"
            await a.execute("COMMIT")
            try:
                await asyncio.wait_for(pending, 5)
            except asyncpg.UniqueViolationError:
                pass
            else:
                raise AssertionError("duplicate_commit")
            assert await connection.fetchval(f"SELECT count(*) FROM {table}") == count+1
            checks += 1
        finally:
            if pending and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            await a.close()
            await b.close()
    await race("credit_accounts", account(uid(3)), account(uid(3)))
    await race("credit_cycles", cycle(uid(12),cycle_index=3), cycle(uid(13),cycle_index=3))
    await race("credit_ledger_events", event(uid(36),kind="adjust",operation_key="race",granted_delta=1),
               event(uid(37),kind="adjust",operation_key="race",granted_delta=1), adjust=True)
    for grant_id in (uid(20),uid(21)):
        sums = await connection.fetchrow("SELECT coalesce(sum(granted_delta),0),coalesce(sum(reserved_delta),0),coalesce(sum(consumed_delta),0),coalesce(sum(expired_delta),0) FROM credit_ledger_events WHERE grant_id=$1", grant_id)
        projection = await connection.fetchrow("SELECT granted_microcredits,reserved_microcredits,consumed_microcredits,expired_microcredits FROM credit_grants WHERE id=$1", grant_id)
        assert tuple(sums) == tuple(projection)
        assert projection[0]-sum(projection[1:]) >= 0
        checks += 1
    phase = "downgrade"
    before = await snapshot(connection, LEGACY+CREDIT)
    await migrate("downgrade", "0003_content_ownership", "credit_foundation_requires_empty_tables")
    assert await snapshot(connection, LEGACY+CREDIT) == before
    assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
    tx = connection.transaction()
    await tx.start()
    await connection.execute("LOCK TABLE credit_accounts IN ROW EXCLUSIVE MODE")
    try:
        await migrate("downgrade", "0003_content_ownership", "lock timeout")
    finally:
        await tx.rollback()
    assert await snapshot(connection, LEGACY+CREDIT) == before
    assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
    return checks+2


async def operation_migration(connection):
    """Real populated 0004 round trip; never stamp or delete accounting rows."""
    global phase
    phase = "downgrade"
    before = await snapshot(connection, LEGACY+CREDIT)
    async def schema():
        return await connection.fetch("SELECT table_name,column_name,data_type,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY($1::text[]) ORDER BY 1,2", list(LEGACY+CREDIT)), await connection.fetch(
            "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=ANY($1::text[]) ORDER BY 1", list(LEGACY+CREDIT)), await connection.fetch(
            "SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid IN "
            "(SELECT oid FROM pg_class WHERE relname=ANY($1::text[]) AND relnamespace='public'::regnamespace) ORDER BY 1", list(LEGACY+CREDIT))
    old_schema = await schema()
    await migrate("downgrade", "0004_credit_foundation")
    assert await connection.fetchval("SELECT to_regclass('credit_operations')") is None
    assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0004_credit_foundation"
    assert await snapshot(connection, LEGACY+CREDIT) == before and await schema() == old_schema
    await migrate("upgrade", "head")
    assert await connection.fetchval("SELECT count(*) FROM credit_operations") == 0
    assert await snapshot(connection, LEGACY+CREDIT) == before and await schema() == old_schema
    await metadata()
    # Populated new table must survive both row refusal and lock timeout unchanged.
    await connection.execute("INSERT INTO credit_operations(user_id,operation_key,kind,target_plan,"
        "rate_card_version,effective_at,result_cycle_id,outcome) VALUES($1,'migration_fixture',"
        "'plan_change','free','v1',$2,$3,'unchanged')", uid(1), NOW, uid(10))
    all_before = await snapshot(connection, LEGACY+CREDIT+("credit_operations",))
    await migrate("downgrade", "0004_credit_foundation", "credit_operations_requires_empty_table")
    tx = connection.transaction()
    await tx.start()
    await connection.execute("LOCK TABLE credit_operations IN ROW EXCLUSIVE MODE")
    try:
        await migrate("downgrade", "0004_credit_foundation", "lock timeout")
    finally:
        await tx.rollback()
    assert await snapshot(connection, LEGACY+CREDIT+("credit_operations",)) == all_before
    assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    global phase
    mode = os.environ.get("CREDIT_PROOF_MODE", "")
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(os.environ.get("CREDIT_PROOF_PROJECT", ""), url, os.environ.get("AI_PROVIDER"),
                    os.environ.get("APP_ENV"), mode, os.environ.get("CREDIT_PROOF_DATABASE"))
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:")
    connection = await asyncpg.connect(dsn)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
        if mode == "additive":
            phase = "additive"
            await additive(connection)
            result = {"mode": mode, "checks": 1}
        else:
            phase = "metadata"
            await metadata()
            result = {"mode": mode, "checks": await credit(connection, dsn)}
            await operation_migration(connection)
        phase = "done"
        print(json.dumps(result))
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print("credit_proof_failed:" + phase)
        sys.exit(124)
    except Exception:
        print("credit_proof_failed:" + phase)
        sys.exit(1)
