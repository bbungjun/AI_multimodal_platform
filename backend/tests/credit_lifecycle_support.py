"""Fixed runtime PostgreSQL proof. No pytest, target/source flags, or raw output."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import time
from uuid import uuid4

HEAD = "0006_credit_accounting_persistence"
GROUPS = ("init", "renewal", "plan", "bonus", "expiry", "idempotency", "transaction", "concurrency")
TABLES = ("credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events", "credit_operations")
T = datetime(2024, 2, 29, 23, 59, 59, 123456, tzinfo=timezone.utc)
END = T + timedelta(days=30)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"credit-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db" or url.port != 5432
            or url.database != project.replace("-", "_") or url.username != "credit"
            or provider != "mock" or app_env != "test"):
        raise ValueError("lifecycle_target_refused")


async def proof(db, factory):
    from sqlalchemy import select, text
    from app.credit_lifecycle import ensure_cycle, change_plan, grant_bonus, CreditLifecycleError
    from app.credit_models import CreditAccount, CreditGrant
    from app.credit_policy import plan_policy
    import asyncpg
    global phase
    checks, races = 0, 0
    groups = {}

    def check(condition):
        nonlocal checks
        assert condition, "lifecycle_assertion"
        checks += 1

    async def seed(master=False):
        uid = uuid4()
        if master:
            # Synthetic fixture identity only; never emitted or used for OAuth.
            await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)", uid, uid.hex, uid.hex+"@example.invalid", T)
        else:
            await db.execute("INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,false,'user','active','synthetic',$2,$2)", uid, T)
        return uid

    async def snapshot():
        return {table: await db.fetch(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1") for table in TABLES}

    async def run(fn, uid, now=T, **kwargs):
        async with factory() as session, session.begin():
            return await fn(session, user_id=uid, now=now, **kwargs)

    async def bonus(uid, key, amount=100, now=T, expiry=None, reason="fixture"):
        return await run(grant_bonus, uid, now, amount_microcredits=amount, expires_at=expiry,
                         reason_code=reason, operation_key=key)

    async def plan(uid, target, key, now=T):
        return await run(change_plan, uid, now, target_plan=target, operation_key=key)

    async def refuse(fn, code):
        before = await snapshot()
        try:
            await fn()
        except CreditLifecycleError as error:
            check(error.code == code and str(error) == code)
        else:
            raise AssertionError("domain_refusal_missing")
        check(await snapshot() == before)

    async def counts(uid):
        return tuple([await db.fetchval(f"SELECT count(*) FROM {table} WHERE user_id=$1", uid) for table in TABLES])

    async def reconstruct():
        for row in await db.fetch("SELECT * FROM credit_grants"):
            sums = await db.fetchrow("SELECT coalesce(sum(granted_delta),0),coalesce(sum(reserved_delta),0),"
                "coalesce(sum(consumed_delta),0),coalesce(sum(expired_delta),0) FROM credit_ledger_events WHERE grant_id=$1", row["id"])
            check(tuple(sums) == tuple(row[name+"_microcredits"] for name in ("granted", "reserved", "consumed", "expired")))
            check(sums[0] >= sum(sums[1:]))

    async def held(uid, grant_id):
        # Matching fixture reserve/settle ledger, not a G5C reservation implementation.
        async with db.transaction():
            for kind, reserved, consumed, expired in (("reserve", 40, 0, 0), ("settle", -10, 10, 0), ("expire", 0, 0, 20)):
                await db.execute("INSERT INTO credit_ledger_events(id,user_id,grant_id,kind,operation_key,rate_card_version,"
                    "granted_delta,reserved_delta,consumed_delta,expired_delta,created_at,reason_code) "
                    "VALUES($1,$2,$3,$4,$5,'v1',0,$6,$7,$8,$9,'fixture')", uuid4(),uid,grant_id,kind,
                    "held_"+uuid4().hex,reserved,consumed,expired,T)
            await db.execute("UPDATE credit_grants SET reserved_microcredits=30,consumed_microcredits=10,expired_microcredits=20 WHERE id=$1", grant_id)

    phase = "init"
    u, master = await seed(), await seed(True)
    a, m = await run(ensure_cycle,u), await run(ensure_cycle,master)
    check(a.plan == "free" and m.plan == "max")
    check(a.allowance_microcredits == plan_policy("free").allowance_microcredits)
    check(m.allowance_microcredits == plan_policy("max").allowance_microcredits)
    check(await counts(u) == (1,1,1,1,0))
    check(await run(ensure_cycle,u) == a and await counts(u) == (1,1,1,1,0))
    late = await seed()
    check((await run(ensure_cycle,late,T+timedelta(days=95))).cycle_index == 3)
    check(await counts(late) == (1,1,1,1,0))
    await refuse(lambda: run(ensure_cycle,uuid4()), "credit_user_missing")
    groups[phase] = True

    phase = "renewal"
    check((await run(ensure_cycle,u,END-timedelta(microseconds=1))).cycle_id == a.cycle_id)
    b = await run(ensure_cycle,u,END.astimezone(timezone(timedelta(hours=9))))
    check(b.cycle_index == 1 and b.starts_at == END and b.ends_at-END == timedelta(seconds=2592000))
    check((await run(ensure_cycle,u,END+timedelta(microseconds=1))).cycle_id == b.cycle_id)
    check(await counts(u) == (1,2,2,3,0))
    d = await seed()
    await plan(d,"max","max")
    await plan(d,"free","lower")
    c = await run(ensure_cycle,d,T+timedelta(days=125))
    check(c.plan == "free" and c.pending_plan is None and c.cycle_index == 4)
    check(await db.fetchval("SELECT cycle_anchor_at FROM credit_accounts WHERE user_id=$1",d) == T)
    check((await counts(d))[1] == 2)
    groups[phase] = True

    phase = "plan"
    rank = {"free":0,"pro":1,"max":2}
    for source in rank:
        for target in rank:
            p = await seed()
            await plan(p,source,"start")
            base = await run(ensure_cycle,p)
            await held(p,base.base_grant_id)
            r = await plan(p,target,"target")
            check(r.outcome == ("upgraded" if rank[target]>rank[source] else "scheduled" if rank[target]<rank[source] else "unchanged"))
            g = await db.fetchrow("SELECT * FROM credit_grants WHERE id=$1",base.base_grant_id)
            check(g["granted_microcredits"] == plan_policy(max((source,target),key=rank.get)).allowance_microcredits)
            check(g["reserved_microcredits"] == 30 and g["consumed_microcredits"] == 10 and g["expired_microcredits"] == 20)
            before = g["granted_microcredits"]
            await plan(p,target,"again")
            check(await db.fetchval("SELECT granted_microcredits FROM credit_grants WHERE id=$1",base.base_grant_id) == before)
    p = await seed()
    await plan(p,"max","start")
    check((await plan(p,"pro","lower")).outcome == "scheduled")
    check((await plan(p,"free","replace")).outcome == "scheduled")
    check((await plan(p,"free","noop")).outcome == "unchanged")
    check((await plan(p,"max","cancel")).outcome == "cancelled")
    check((await run(ensure_cycle,p)).pending_plan is None)
    await refuse(lambda: plan(master,"free","bad"),"credit_plan_refused")
    await refuse(lambda: run(ensure_cycle,u,T),"credit_clock_regressed")
    groups[phase] = True

    phase = "bonus"
    v = await seed()
    finite = await bonus(v,"finite",expiry=END)
    unlimited = await bonus(v,"unlimited")
    check(finite.grant_id != unlimited.grant_id)
    check(await db.fetchval("SELECT cycle_id IS NULL AND expires_at IS NULL FROM credit_grants WHERE id=$1",unlimited.grant_id))
    for amount in (True,1.5,"2",0,-1,2**63):
        await refuse(lambda: bonus(v,"invalid",amount),"credit_input_invalid")
    for key,reason,expiry in (("bad key","ok",None),("ok","Bad",None),("ok","ok",T),("ok","ok",T.replace(tzinfo=None))):
        await refuse(lambda: bonus(v,key,expiry=expiry,reason=reason),"credit_input_invalid")
    await refuse(lambda: bonus(v,"overflow",2**63-1),"credit_amount_overflow")
    groups[phase] = True

    phase = "expiry"
    base = await run(ensure_cycle,v)
    await held(v,base.base_grant_id)
    await held(v,finite.grant_id)
    await run(ensure_cycle,v,END)
    for grant_id in (base.base_grant_id,finite.grant_id):
        g = await db.fetchrow("SELECT * FROM credit_grants WHERE id=$1",grant_id)
        check(g["reserved_microcredits"] == 30 and g["consumed_microcredits"] == 10)
        check(g["expired_microcredits"] == g["granted_microcredits"]-40)
    before = await counts(v)
    await run(ensure_cycle,v,END)
    check(await counts(v) == before)
    check(await db.fetchval("SELECT expired_microcredits FROM credit_grants WHERE id=$1",unlimited.grant_id) == 0)
    await reconstruct()
    groups[phase] = True

    phase = "idempotency"
    before = await snapshot()
    replay = await bonus(v,"finite",now=END+timedelta(days=90),expiry=END)
    check(replay == replace(finite,replayed=True) and await snapshot() == before)
    for amount,expiry,reason in ((101,END,"fixture"),(100,None,"fixture"),(100,END,"changed")):
        await refuse(lambda: bonus(v,"finite",amount,now=END+timedelta(days=90),expiry=expiry,reason=reason),"credit_idempotency_conflict")
    await refuse(lambda: plan(v,"max","finite",END+timedelta(days=90)),"credit_idempotency_conflict")
    r = await plan(p,"free","schedule")
    before = await snapshot()
    check(await plan(p,"free","schedule",END) == replace(r,replayed=True))
    check(await snapshot() == before)
    await refuse(lambda: plan(p,"pro","schedule",END),"credit_idempotency_conflict")
    for key,target in (("cancel","max"),("noop","free")):
        original = await plan(p,target,key)
        before = await snapshot()
        check(original.replayed)
        check(await plan(p,target,key,END+timedelta(days=90)) == original)
        check(await snapshot() == before)
    check(not (await bonus(await seed(),"finite",expiry=END)).replayed)
    await db.execute("UPDATE users SET status='suspended',suspended_at=$2 WHERE id=$1",v,END)
    check((await bonus(v,"finite",now=END,expiry=END)).replayed)
    await refuse(lambda: bonus(v,"new",now=END),"credit_plan_refused")
    await refuse(lambda: plan(v,"max","new",END),"credit_plan_refused")
    check((await run(ensure_cycle,v,END)).cycle_index == 1)
    groups[phase] = True

    phase = "transaction"
    async with factory() as session:
        await refuse(lambda: ensure_cycle(session,user_id=u,now=END),"credit_transaction_required")
    rollback_user = await seed()
    before = await snapshot()
    async with factory() as session:
        tx = await session.begin()
        await grant_bonus(session,user_id=rollback_user,now=T,operation_key="rollback",amount_microcredits=1,expires_at=None,reason_code="fixture")
        check(await counts(rollback_user) == (0,0,0,0,0))
        await tx.rollback()
    check(await snapshot() == before)
    # Savepoint rollback must undo lazy creation on a late capacity refusal.
    async with factory() as session, session.begin():
        try:
            await grant_bonus(session,user_id=rollback_user,now=T,operation_key="huge",amount_microcredits=2**63-1,expires_at=None,reason_code="fixture")
        except CreditLifecycleError as error:
            check(error.code == "credit_amount_overflow")
        else:
            raise AssertionError("savepoint_refusal_missing")
        check(await session.scalar(text("SELECT count(*) FROM credit_accounts WHERE user_id=:u").bindparams(u=rollback_user)) == 0)
        check(await session.scalar(text("SELECT 1")) == 1)
    check(await snapshot() == before)
    # Stale identity map loaded without a lock, then changed by another connection.
    fresh = await seed()
    await run(ensure_cycle,fresh)
    async with factory() as session, session.begin():
        old = await session.scalar(select(CreditAccount).where(CreditAccount.user_id == fresh))
        old_grant = await session.scalar(select(CreditGrant).where(CreditGrant.user_id == fresh))
        await plan(fresh,"max","external")
        check(old.plan == "free")
        result = await change_plan(session,user_id=fresh,target_plan="pro",operation_key="fresh",now=T)
        check(result.outcome == "scheduled" and old.plan == "max")
        check(old_grant.granted_microcredits == plan_policy("max").allowance_microcredits)
    # An actual database lock_timeout maps to a safe code, preserving caller writes.
    lock_user = await seed()
    async with factory() as holder, holder.begin(), factory() as waiter, waiter.begin():
        await holder.execute(text("SELECT id FROM users WHERE id=:u FOR UPDATE").bindparams(u=lock_user))
        await waiter.execute(text("SET LOCAL lock_timeout='100ms'"))
        await refuse(lambda: ensure_cycle(waiter,user_id=lock_user,now=T),"credit_busy")
        check(await waiter.scalar(text("SELECT 1")) == 1)
    # Corrupt-but-DDL-valid projections must fail closed, never repair themselves.
    for table,assignment in (("credit_accounts","cycle_anchor_at=cycle_anchor_at-interval '1 second'"),
                             ("credit_accounts","plan='free',pending_plan=NULL"),
                             ("credit_cycles","allowance_microcredits=allowance_microcredits+1"),
                             ("credit_grants","granted_microcredits=granted_microcredits+1")):
        async with factory() as session, session.begin():
            await session.execute(text(f"UPDATE {table} SET {assignment} WHERE user_id=:u").bindparams(u=fresh))
            try:
                await ensure_cycle(session,user_id=fresh,now=T)
            except CreditLifecycleError as error:
                check(error.code == "credit_account_inconsistent")
            else:
                raise AssertionError("corruption_not_refused")
            await session.rollback()
    async with factory() as session, session.begin():
        await session.execute(text("UPDATE credit_accounts SET plan='pro' WHERE user_id=:u").bindparams(u=master))
        try:
            await ensure_cycle(session,user_id=master,now=T)
        except CreditLifecycleError as error:
            check(error.code == "credit_account_inconsistent")
        else:
            raise AssertionError("master_inconsistency_not_refused")
        await session.rollback()
    # Real operation constraints / owner FKs / three immutable-history mutations.
    template = dict(await db.fetchrow("SELECT * FROM credit_operations WHERE user_id=$1 AND operation_key='finite'",v))
    for changes in ({"operation_key":"bad key"},{"amount_microcredits":0},{"reason_code":None},
                    {"target_plan":"free"},{"rate_card_version":"v0"},{"outcome":"unchanged"},
                    {"expires_at":T},{"result_cycle_id":a.cycle_id},{"result_grant_id":a.base_grant_id},
                    {"user_id":uuid4()},{"operation_key":"finite"},{"amount_microcredits":None},
                    {"kind":"plan_change","target_plan":None},{"result_grant_id":None}):
        values = dict(template,operation_key=uuid4().hex)
        values.update(changes)
        before = await snapshot()
        tx = db.transaction()
        await tx.start()
        try:
            try:
                await db.execute("INSERT INTO credit_operations ("+",".join(values)+") VALUES ("+
                    ",".join("$"+str(i) for i in range(1,len(values)+1))+")",*values.values())
            except asyncpg.IntegrityConstraintViolationError:
                check(True)
            else:
                raise AssertionError("operation_constraint_missing")
        finally:
            await tx.rollback()
        check(await snapshot() == before)
    for sql in ("UPDATE credit_operations SET outcome=outcome", "DELETE FROM credit_operations", "TRUNCATE credit_operations"):
        before = await snapshot()
        try:
            await db.execute(sql)
        except asyncpg.CheckViolationError as error:
            check(str(error) == "credit_operation_append_only")
        else:
            raise AssertionError("operation_mutation_allowed")
        check(await snapshot() == before)
    groups[phase] = True

    phase = "concurrency"
    async def race(uid, first, second, validate, conflict=False):
        nonlocal races
        pending = None
        async with factory() as s1, factory() as s2:
            tx1, tx2 = await s1.begin(), await s2.begin()
            try:
                one = await asyncio.wait_for(first(s1,uid),10)
                pid = await s2.scalar(text("SELECT pg_backend_pid()"))
                pending = asyncio.create_task(second(s2,uid))
                deadline = time.monotonic()+5
                while not await db.fetchval("SELECT wait_event_type='Lock' AND cardinality(pg_blocking_pids(pid))>0 FROM pg_stat_activity WHERE pid=$1",pid):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("race_lock_not_observed")
                    assert not pending.done(),"race_participant_ended_early"
                check(not pending.done())
                await tx1.commit()
                try:
                    two = await asyncio.wait_for(pending,10)
                except CreditLifecycleError as error:
                    check(conflict and error.code == "credit_idempotency_conflict")
                    two = None
                else:
                    check(not conflict)
                await tx2.commit()
                await validate(uid,one,two)
                races += 1
            finally:
                if pending and not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending,return_exceptions=True)
                if s1.in_transaction():
                    await s1.rollback()
                if s2.in_transaction():
                    await s2.rollback()

    def ensure_at(now):
        return lambda s,u: ensure_cycle(s,user_id=u,now=now)

    def bonus_at(key,amount=100,now=T):
        return lambda s,u: grant_bonus(s,user_id=u,now=now,operation_key=key,
            amount_microcredits=amount,expires_at=None,reason_code="fixture")

    def plan_at(target,key,now=T):
        return lambda s,u: change_plan(s,user_id=u,now=now,target_plan=target,operation_key=key)

    async def same_init(uid,one,two):
        check(one == two and await counts(uid) == (1,1,1,1,0))

    await race(await seed(),ensure_at(T),ensure_at(T),same_init)
    r = await seed()
    await run(ensure_cycle,r)
    async def same_renew(uid,one,two):
        check(one == two and one.cycle_index == 1 and await counts(uid) == (1,2,2,3,0))
    await race(r,ensure_at(END),ensure_at(END),same_renew)
    async def same_bonus(uid,one,two):
        check(two == replace(one,replayed=True) and await counts(uid) == (1,1,2,2,1))
    await race(await seed(),bonus_at("same"),bonus_at("same"),same_bonus)
    async def conflict_bonus(uid,one,two):
        check(two is None and await counts(uid) == (1,1,2,2,1))
        check(await db.fetchval("SELECT granted_microcredits FROM credit_grants WHERE id=$1",one.grant_id) == 100)
    await race(await seed(),bonus_at("same"),bonus_at("same",101),conflict_bonus,True)
    r = await seed()
    await plan(r,"max","start")
    async def same_schedule(uid,one,two):
        check(two == replace(one,replayed=True) and one.outcome == "scheduled")
        check(await counts(uid) == (1,1,1,2,2))
        check(await db.fetchval("SELECT pending_plan FROM credit_accounts WHERE user_id=$1",uid) == "free")
    await race(r,plan_at("free","same"),plan_at("free","same"),same_schedule)
    async def distinct_bonus(uid,one,two):
        check(one.grant_id != two.grant_id and await counts(uid) == (1,1,3,3,2))
        check(await db.fetchval("SELECT sum(granted_microcredits) FROM credit_grants WHERE user_id=$1 AND kind='bonus'",uid) == 201)
    await race(await seed(),bonus_at("one"),bonus_at("two",101),distinct_bonus)
    r = await seed()
    await run(ensure_cycle,r)
    async def boundary(uid,one,two):
        check(one.cycle_id == two.cycle_id and two.plan == "pro" and two.cycle_index == 1)
        check(await counts(uid) == (1,2,2,4,1))
        check(await db.fetchval("SELECT granted_microcredits FROM credit_grants WHERE id=$1",two.base_grant_id) == plan_policy("pro").allowance_microcredits)
    await race(r,plan_at("pro","upgrade",END),ensure_at(END),boundary)
    r = await seed()
    old = await bonus(r,"old",expiry=T+timedelta(seconds=1))
    async def expired(uid,one,two):
        check(await counts(uid) == (1,1,3,4,2))
        check(await db.fetchval("SELECT expired_microcredits FROM credit_grants WHERE id=$1",old.grant_id) == 100)
    await race(r,ensure_at(T+timedelta(seconds=1)),bonus_at("new",now=T+timedelta(seconds=1)),expired)
    await reconstruct()
    check(races == 8)
    groups[phase] = True
    assert set(groups) == set(GROUPS) and all(groups.values()) and checks >= 80
    return dict(groups=groups,races=races,checks=checks,complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import app.models  # Register existing relationships, no product calls.
    import app.credit_models
    global phase
    raw_url = os.environ.get("DATABASE_URL", "")
    url = make_url(raw_url)
    validate_target(os.environ.get("CREDIT_PROOF_PROJECT", ""),url,os.environ.get("AI_PROVIDER"),os.environ.get("APP_ENV"))
    db = await asyncpg.connect(raw_url.replace("postgresql+asyncpg:","postgresql:"))
    engine = create_async_engine(raw_url)
    try:
        assert await db.fetchval("SELECT current_database()") == url.database
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        for table in ("users",)+TABLES:
            assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0, "nonempty_target_refused"
        result = await asyncio.wait_for(proof(db,async_sessionmaker(engine,expire_on_commit=False)),180)
        phase = "done"
        print(json.dumps(result))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print("lifecycle_proof_failed:"+phase)
        sys.exit(124)
    except Exception:
        print("lifecycle_proof_failed:"+phase)
        sys.exit(1)
