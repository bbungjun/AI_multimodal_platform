"""Fixed, disposable PostgreSQL proof. Never print identities or SQL/errors."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import time
from uuid import uuid4

from app.schema_revision import CODE_REVISION as HEAD

GROUPS = ("guards", "promotion", "plan", "bonus", "replay", "rollback", "append_only", "races")
phase = "guard"
T = datetime(2025, 1, 1, tzinfo=timezone.utc)
NOW = T + timedelta(days=1)


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"master-admin-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.database != project.replace("-", "_") or provider != "mock" or app_env != "test"):
        raise ValueError("master_proof_target_refused")


async def proof(db, factory):
    from sqlalchemy import text
    from app.credit_accounting import ReservationRequest, UsageEstimate, UsageReport, UsageLine, reserve, settle
    from app.master_admin import MasterCommand, MasterError, administer

    global phase
    checks, races, groups = 0, 0, {}

    def check(value):
        nonlocal checks
        assert value, "master_assertion"
        checks += 1

    async def seed(*, origin="oauth", role="user", suspended=False):
        uid, marker = uuid4(), uuid4().hex
        await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,"
            "signed_up_at,updated_at,suspended_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8,$9)", uid,
            marker if origin == "oauth" else None, marker + "@example.invalid" if origin == "oauth" else None,
            origin == "oauth", role, "suspended" if suspended else "active", origin, T, T if suspended else None)
        return uid

    master, user = await seed(role="master"), await seed()

    def cmd(target=user, action="plan_change", **kwargs):
        return MasterCommand(target, uuid4(), action, "support_adjustment", **kwargs)

    async def act(command, *, actor=None, source="browser", rollback=False):
        async with factory() as session:
            async with session.begin():
                result = await administer(session, actor_id=master if actor is None else actor,
                                          command=command, now=NOW, source=source)
                if rollback:
                    await session.rollback()
            return result

    async def refused(command, expected, **kwargs):
        try:
            await act(command, **kwargs)
        except MasterError as error:
            check(error.code == expected)
        else:
            raise AssertionError("refusal_missing")

    async def counts():
        return tuple([await db.fetchval("SELECT count(*) FROM " + table) for table in
                      ("master_audit", "credit_operations", "credit_grants", "credit_ledger_events")])

    phase = "guards"
    for actor in (user, uuid4(), await seed(role="master", suspended=True)):
        before = await counts()
        await refused(cmd(target_plan="pro"), "master_required", actor=actor)
        check(await counts() == before)
    await refused(cmd(target=uuid4(), target_plan="pro"), "master_target_missing")
    await refused(cmd(target=await seed(suspended=True), target_plan="pro"), "master_conflict")
    synthetic = await seed(origin="synthetic")
    await refused(cmd(target=synthetic, action="promote"), "master_conflict", actor=synthetic, source="operator_cli")
    groups[phase] = True

    phase = "promotion"
    promoted = await seed()
    async with factory() as session, session.begin():
        reserved = await reserve(session, request=ReservationRequest(promoted, "proof_reserve",
            (UsageEstimate("imagen_fast_image", 1),)), now=NOW)
        await settle(session, user_id=promoted, reservation_id=reserved.reservation_id,
            usage=UsageReport((UsageLine("imagen_fast_image", 1, "mock_estimate"),)),
            delivery="delivered", operation_key="proof_settle", now=NOW)
    promotion = cmd(target=promoted, action="promote")
    before_counts = await counts()
    preview = await act(promotion, actor=promoted, source="operator_cli", rollback=True)
    check(preview.after["role"] == "master")
    check(await counts() == before_counts)
    check(await db.fetchval("SELECT role FROM users WHERE id=$1", promoted) == "user")
    receipt = await act(promotion, actor=promoted, source="operator_cli")
    check(receipt.before["role"] == "user")
    check(receipt.before["plan"] == "free")
    check(receipt.after["role"] == "master")
    check(receipt.after["plan"] == "max")
    check(receipt.after["pending_plan"] is None)
    check(not receipt.replayed)
    check(await db.fetchval("SELECT sum(consumed_microcredits) FROM credit_grants WHERE user_id=$1", promoted) == 50_000_000)
    check(await db.fetchval("SELECT plan FROM credit_accounts WHERE user_id=$1", promoted) == "max")
    check(await db.fetchval("SELECT allowance_microcredits FROM credit_cycles WHERE user_id=$1", promoted) == 50_000_000_000)
    row = await db.fetchrow("SELECT source,actor_id,target_id FROM master_audit WHERE request_id=$1", promotion.request_id)
    check(row["source"] == "operator_cli")
    check(row["actor_id"] == row["target_id"] == promoted)
    groups[phase] = True

    phase = "plan"
    for plan, expected, pending in (("pro", "pro", None), ("max", "max", None),
                                    ("free", "max", "free"), ("max", "max", None)):
        receipt = await act(cmd(target_plan=plan))
        check(receipt.after["plan"] == expected)
        check(receipt.after["pending_plan"] == pending)
        check(await db.fetchval("SELECT count(*) FROM master_audit WHERE request_id=$1", receipt.request_id) == 1)
    await refused(cmd(target=promoted, target_plan="free"), "master_conflict")
    groups[phase] = True

    phase = "bonus"
    for amount, expiry in ((12345, None), (54321, NOW + timedelta(days=2))):
        receipt = await act(cmd(action="bonus_grant", amount_microcredits=amount, expires_at=expiry))
        check(receipt.after["bonus_microcredits"] == amount)
        check(receipt.before["bonus_microcredits"] == 0)
        check(await db.fetchval("SELECT count(*) FROM credit_grants WHERE user_id=$1 AND kind='bonus' "
                                "AND granted_microcredits=$2", user, amount) == 1)
    await refused(cmd(action="bonus_grant", amount_microcredits=1, expires_at=T), "master_input_invalid")
    groups[phase] = True

    phase = "replay"
    replay = cmd(action="bonus_grant", amount_microcredits=8765)
    first = await act(replay)
    before = await counts()
    for _ in range(3):
        repeated = await act(replay)
        check(repeated.replayed)
        check(repeated.created_at == first.created_at and repeated.after == first.after)
    check(await counts() == before)
    for changed in (replace(replay, amount_microcredits=8766), replace(replay, reason_code="service_recovery"),
                    replace(replay, target_id=promoted)):
        await refused(changed, "master_conflict")
    check(await counts() == before)
    groups[phase] = True

    phase = "rollback"
    before = await counts()
    await act(cmd(action="bonus_grant", amount_microcredits=333), rollback=True)
    check(await counts() == before)
    await db.execute("CREATE FUNCTION proof_refuse_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
                     "BEGIN RAISE EXCEPTION 'proof_refusal' USING ERRCODE='23514'; END $$")
    await db.execute("CREATE TRIGGER proof_refuse BEFORE INSERT ON master_audit FOR EACH ROW EXECUTE FUNCTION proof_refuse_audit()")
    try:
        await refused(cmd(action="bonus_grant", amount_microcredits=334), "master_unavailable")
        check(await counts() == before)
    finally:
        await db.execute("DROP TRIGGER proof_refuse ON master_audit")
        await db.execute("DROP FUNCTION proof_refuse_audit()")
    groups[phase] = True

    phase = "append_only"
    for sql in ("UPDATE master_audit SET reason_code='account_policy'", "DELETE FROM master_audit",
                "TRUNCATE master_audit"):
        before = await counts()
        try:
            await db.execute(sql)
        except Exception as error:
            check(getattr(error, "sqlstate", None) == "23514")
        else:
            raise AssertionError("append_only_missing")
        check(await counts() == before)
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "alembic", "downgrade",
        "0006_credit_accounting_persistence", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    output, error = await asyncio.wait_for(process.communicate(), 20)
    check(process.returncode != 0 and b"master_audit_requires_empty_table" in output + error)
    check(await db.fetchval("SELECT version_num FROM alembic_version") == HEAD)
    groups[phase] = True

    phase = "races"
    async def observed_wait():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if await db.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND application_name='master-proof' AND cardinality(pg_blocking_pids(pid)) > 0"):
                check(True)
                return
            await asyncio.sleep(.01)
        raise AssertionError("lock_not_observed")

    async def blocked(commands, *, actor=master, mutate=None):
        nonlocal races
        lock = db.transaction()
        await lock.start()
        await db.execute("SELECT id FROM users WHERE id=$1 FOR UPDATE", actor)
        tasks = [asyncio.create_task(act(command, actor=actor)) for command in commands]
        try:
            await observed_wait()
            if mutate:
                await db.execute(mutate, actor)
        finally:
            await lock.commit()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        races += 1
        return results

    same = cmd(action="bonus_grant", amount_microcredits=1001)
    results = await blocked([same] * 8)
    check(sum(not r.replayed for r in results) == 1)
    check(all(r.after["bonus_microcredits"] == 1001 for r in results))
    check(await db.fetchval("SELECT count(*) FROM master_audit WHERE request_id=$1", same.request_id) == 1)
    commands = [cmd(action="bonus_grant", amount_microcredits=2000 + i) for i in range(8)]
    results = await blocked(commands)
    for index, result in enumerate(results):
        check(not result.replayed and result.after["bonus_microcredits"] == 2000 + index)
    stale = cmd(action="bonus_grant", amount_microcredits=3000)
    results = await blocked([stale], mutate="UPDATE users SET role='user' WHERE id=$1")
    check(isinstance(results[0], MasterError) and results[0].code == "master_required")
    check(await db.fetchval("SELECT count(*) FROM master_audit WHERE request_id=$1", stale.request_id) == 0)
    await db.execute("UPDATE users SET role='master' WHERE id=$1", master)
    results = await blocked([cmd(action="bonus_grant", amount_microcredits=3001)],
                            mutate="UPDATE users SET status='suspended',suspended_at=signed_up_at WHERE id=$1")
    check(isinstance(results[0], MasterError) and results[0].code == "master_required")
    check(await db.fetchval("SELECT count(*) FROM credit_grants WHERE user_id=$1 AND kind='bonus' "
                            "AND granted_microcredits=3001", user) == 0)
    groups[phase] = True
    check(set(groups) == set(GROUPS))
    return dict(groups=groups, races=races, checks=checks, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(os.environ.get("MASTER_ADMIN_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"application_name": "master-proof"}})
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
