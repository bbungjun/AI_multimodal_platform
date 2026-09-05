"""Fixed PostgreSQL accounting proof. No pytest, target/source flags, or raw output."""
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
GROUPS = ("input_quote", "allocation", "reserve_replay", "settlement", "release",
          "transaction", "integrity", "concurrency")
TABLES = ("credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events",
          "credit_operations", "credit_reservations", "credit_reservation_items",
          "credit_reservation_allocations", "credit_usage_records")
T = datetime(2024, 2, 29, 23, 59, 59, 123456, tzinfo=timezone.utc)
END = T + timedelta(days=30)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"accounting-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db" or url.port != 5432
            or url.database != project.replace("-", "_") or url.username != "credit"
            or provider != "mock" or app_env != "test"):
        raise ValueError("accounting_target_refused")


async def proof(db, factory):
    from sqlalchemy import select, text
    from app.credit_accounting import (
        CreditAccountingError, ReservationRequest, UsageEstimate, UsageLine, UsageReport,
        release, reserve, settle,
    )
    from app.credit_lifecycle import ensure_cycle, grant_bonus
    from app.credit_models import CreditGrant
    import asyncpg
    global phase
    checks = races = 0
    groups = {}

    def check(condition):
        nonlocal checks
        assert condition, "accounting_assertion"
        checks += 1

    async def seed(master=False):
        uid = uuid4()
        if master:
            await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)", uid, uid.hex, uid.hex+"@example.invalid", T)
        else:
            await db.execute("INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,false,'user','active','synthetic',$2,$2)", uid, T)
        return uid

    async def snapshot():
        return {table: await db.fetch(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1") for table in TABLES}

    async def in_tx(fn):
        async with factory() as session, session.begin():
            return await fn(session)

    async def cycle(uid, now=T):
        return await in_tx(lambda session: ensure_cycle(session, user_id=uid, now=now))

    def estimate(meter="gemini_input_token", units=1):
        return UsageEstimate(meter, units)

    def line(meter="gemini_input_token", units=1, source="mock_estimate"):
        return UsageLine(meter, units, source)

    async def hold(uid, key, estimates=(UsageEstimate("gemini_input_token", 1),), now=T):
        request = ReservationRequest(uid, key, tuple(estimates))
        return await in_tx(lambda session: reserve(session, request=request, now=now))

    async def finish(uid, rid, key, lines, delivery="delivered", now=T):
        usage = UsageReport(tuple(lines))
        return await in_tx(lambda session: settle(
            session, user_id=uid, reservation_id=rid, usage=usage,
            delivery=delivery, operation_key=key, now=now))

    async def refund(uid, rid, key, lines=(), reason="provider_failed", now=T):
        usage = UsageReport(tuple(lines))
        return await in_tx(lambda session: release(
            session, user_id=uid, reservation_id=rid, usage=usage,
            reason_code=reason, operation_key=key, now=now))

    async def refuse(fn, code):
        before = await snapshot()
        try:
            await fn()
        except CreditAccountingError as error:
            check(error.code == code and str(error) == code)
        else:
            raise AssertionError("domain_refusal_missing")
        check(await snapshot() == before)

    async def user_counts(uid):
        return {table: await db.fetchval(f"SELECT count(*) FROM {table} WHERE user_id=$1", uid)
                for table in TABLES}

    async def reconstruct():
        rows = await db.fetch("SELECT * FROM credit_grants ORDER BY id")
        for row in rows:
            sums = await db.fetchrow("SELECT coalesce(sum(granted_delta),0),coalesce(sum(reserved_delta),0),"
                "coalesce(sum(consumed_delta),0),coalesce(sum(expired_delta),0) "
                "FROM credit_ledger_events WHERE grant_id=$1", row["id"])
            values = tuple(row[name+"_microcredits"] for name in ("granted", "reserved", "consumed", "expired"))
            check(tuple(sums) == values)
            check(all(type(value) is int and value >= 0 for value in values))
            check(sum(values[1:]) <= values[0])
            check(await db.fetchval("SELECT count(*) FROM credit_ledger_events WHERE grant_id=$1", row["id"]) >= 1)

    phase = "input_quote"
    normal, master = await seed(), await seed(True)
    r = await hold(normal, "quote", (estimate("gemini_input_token", 3), estimate("gemini_output_token", 2)))
    check(r.reserved_microcredits == 11_000 and r.status == "held" and not r.replayed)
    check(await db.fetchval("SELECT count(*) FROM credit_reservation_items WHERE reservation_id=$1", r.reservation_id) == 2)
    check(await db.fetchval("SELECT sum(quoted_microcredits) FROM credit_reservation_items WHERE reservation_id=$1", r.reservation_id) == 11_000)
    check((await hold(master, "master", (estimate("imagen_ultra_image", 1),))).reserved_microcredits == 200_000_000)
    for value in (True, 0, -1, 1.5, "1", 2**63):
        bad_user = await seed()
        await refuse(lambda value=value, uid=bad_user: hold(uid, "bad", (estimate(units=value),)), "credit_input_invalid")
    for estimates in ((), (estimate("unknown", 1),), (estimate(), estimate())):
        bad_user = await seed()
        await refuse(lambda estimates=estimates, uid=bad_user: hold(uid, "bad", estimates), "credit_input_invalid")
    for key in ("", "bad key", "x"*97):
        bad_user = await seed()
        await refuse(lambda key=key, uid=bad_user: hold(uid, key), "credit_input_invalid")
    free = await seed()
    await refuse(lambda: hold(free, "unentitled", (estimate("imagen_ultra_image", 1),)), "credit_plan_refused")
    groups[phase] = True

    phase = "allocation"
    alloc = await seed()
    await in_tx(lambda session: grant_bonus(session, user_id=alloc, amount_microcredits=5_000,
        expires_at=T+timedelta(days=1), reason_code="promo", operation_key="bonus", now=T))
    ar = await hold(alloc, "multi", (estimate(units=6),))
    rows = await db.fetch("SELECT a.ordinal,a.reserved_microcredits,g.kind FROM credit_reservation_allocations a "
                          "JOIN credit_grants g ON g.id=a.grant_id WHERE a.reservation_id=$1 ORDER BY a.ordinal", ar.reservation_id)
    check([(row["kind"], row["reserved_microcredits"]) for row in rows] == [("bonus", 5_000), ("base", 1_000)])
    check([row["ordinal"] for row in rows] == [0, 1])
    exhausted = await seed()
    await refuse(lambda: hold(exhausted, "too_much", (estimate(units=1_000_001),)), "monthly_credit_exhausted")
    check((await user_counts(exhausted))["credit_accounts"] == 0)
    check(await db.fetchval("SELECT sum(reserved_microcredits) FROM credit_grants WHERE user_id=$1", alloc) == 6_000)
    groups[phase] = True

    phase = "reserve_replay"
    replay_user = await seed()
    original = await hold(replay_user, "same", (estimate(units=7),))
    before = await snapshot()
    replayed = await hold(replay_user, "same", (estimate(units=7),), END+timedelta(days=60))
    check(replayed == replace(original, replayed=True) and await snapshot() == before)
    check((await hold(replay_user, "same", (estimate(units=7),), T-timedelta(microseconds=1))).replayed)
    await refuse(lambda: hold(replay_user, "same", (estimate(units=8),), END), "credit_idempotency_conflict")
    await db.execute("UPDATE users SET status='suspended',suspended_at=$2 WHERE id=$1", replay_user, T)
    check((await hold(replay_user, "same", (estimate(units=7),), END)).replayed)
    await refuse(lambda: hold(replay_user, "new", (estimate(),), END), "credit_plan_refused")
    groups[phase] = True

    phase = "settlement"
    settle_user = await seed()
    sr = await hold(settle_user, "settle", (estimate("gemini_input_token", 10), estimate("gemini_output_token", 4)))
    terminal = await finish(settle_user, sr.reservation_id, "terminal",
                            (line("gemini_input_token", 4, "platform_measured"),
                             line("gemini_output_token", 1, "provider_reported")), "partial")
    check((terminal.consumed_microcredits, terminal.released_microcredits, terminal.usage_line_count) == (8_000, 18_000, 2))
    check(await db.fetchval("SELECT sum(charged_microcredits) FROM credit_usage_records WHERE reservation_id=$1", sr.reservation_id) == 8_000)
    check(await db.fetchval("SELECT count(*) FROM credit_usage_records WHERE reservation_id=$1 AND source IN ('platform_measured','provider_reported')", sr.reservation_id) == 2)
    over = await hold(settle_user, "over", (estimate(units=5),))
    await refuse(lambda: finish(settle_user, over.reservation_id, "over_t", (line(units=6),)), "credit_usage_exceeds_reservation")
    await refuse(lambda: finish(settle_user, over.reservation_id, "zero", (line(units=0),)), "credit_input_invalid")
    await cycle(settle_user, END)
    check((await finish(settle_user, sr.reservation_id, "terminal",
                        (line("gemini_input_token", 4, "platform_measured"),
                         line("gemini_output_token", 1, "provider_reported")), "partial", T)).replayed)
    exp = await hold(await seed(), "exp", (estimate(units=10),))
    exp_user = await db.fetchval("SELECT user_id FROM credit_reservations WHERE id=$1", exp.reservation_id)
    exp_done = await finish(exp_user, exp.reservation_id, "exp_t", (line(units=4),), now=END)
    check((exp_done.consumed_microcredits, exp_done.released_microcredits) == (4_000, 6_000))
    check(await db.fetchval("SELECT expired_delta FROM credit_ledger_events WHERE operation_key=$1", "terminal_"+exp.reservation_id.hex) == 6_000)
    groups[phase] = True

    phase = "release"
    release_user = await seed()
    rr = await hold(release_user, "release", (estimate(units=5),))
    released = await refund(release_user, rr.reservation_id, "release_t", (line(units=3, source="estimated"),), "provider_timeout")
    check((released.consumed_microcredits, released.released_microcredits, released.usage_line_count) == (0, 5_000, 1))
    check(await db.fetchval("SELECT charged_microcredits FROM credit_usage_records WHERE reservation_id=$1", rr.reservation_id) == 0)
    empty = await hold(release_user, "empty", (estimate(units=2),))
    check((await refund(release_user, empty.reservation_id, "empty_t", reason="cancelled_before_delivery")).usage_line_count == 0)
    before = await snapshot()
    check((await refund(release_user, rr.reservation_id, "release_t", (line(units=3, source="estimated"),), "provider_timeout")).replayed)
    check(await snapshot() == before)
    await refuse(lambda: refund(release_user, rr.reservation_id, "release_t", (line(units=2),), "provider_timeout"), "credit_idempotency_conflict")
    await refuse(lambda: refund(release_user, rr.reservation_id, "second"), "credit_reservation_state_conflict")
    for reason in ("provider_failed", "provider_rate_limited", "delivery_failed"):
        item = await hold(await seed(), "reason_"+reason, (estimate(),))
        uid = await db.fetchval("SELECT user_id FROM credit_reservations WHERE id=$1", item.reservation_id)
        check((await refund(uid, item.reservation_id, "t_"+reason, reason=reason)).status == "released")
    groups[phase] = True

    phase = "transaction"
    tx_user = await seed()
    async with factory() as session:
        await refuse(lambda: reserve(session, request=ReservationRequest(tx_user, "none", (estimate(),)), now=T), "credit_transaction_required")
    before = await snapshot()
    async with factory() as session:
        tx = await session.begin()
        pending = await reserve(session, request=ReservationRequest(tx_user, "rollback", (estimate(),)), now=T)
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE id=$1", pending.reservation_id) == 0)
        await tx.rollback()
    check(await snapshot() == before)
    lock_user = await seed()
    async with factory() as holder, holder.begin(), factory() as waiter, waiter.begin():
        await holder.execute(text("SELECT id FROM users WHERE id=:u FOR UPDATE").bindparams(u=lock_user))
        await waiter.execute(text("SET LOCAL lock_timeout='100ms'"))
        await refuse(lambda: reserve(waiter, request=ReservationRequest(lock_user, "busy", (estimate(),)), now=T), "credit_busy")
        check(await waiter.scalar(text("SELECT 1")) == 1)
    corrupt = await seed()
    cr = await hold(corrupt, "corrupt", (estimate(units=5),))
    async with factory() as session, session.begin():
        await session.execute(text("UPDATE credit_grants SET reserved_microcredits=reserved_microcredits+1 WHERE user_id=:u").bindparams(u=corrupt))
        try:
            await settle(session, user_id=corrupt, reservation_id=cr.reservation_id,
                         usage=UsageReport((line(units=2),)), delivery="delivered",
                         operation_key="corrupt_t", now=T)
        except CreditAccountingError as error:
            check(error.code == "credit_account_inconsistent")
        else:
            raise AssertionError("corruption_not_refused")
        await session.rollback()
    groups[phase] = True

    phase = "integrity"
    await reconstruct()
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE reserved_microcredits<=0") == 0)
    check(await db.fetchval("SELECT count(*) FROM credit_usage_records WHERE delivery='no_deliverable' AND charged_microcredits<>0") == 0)
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE status='held' AND terminal_operation_key IS NOT NULL") == 0)
    check(await db.fetchval("SELECT count(*) FROM credit_reservation_allocations a LEFT JOIN credit_grants g ON g.id=a.grant_id AND g.user_id=a.user_id WHERE g.id IS NULL") == 0)
    for reservation in await db.fetch("SELECT id,reserved_microcredits FROM credit_reservations ORDER BY id"):
        check(await db.fetchval("SELECT sum(quoted_microcredits) FROM credit_reservation_items WHERE reservation_id=$1", reservation["id"]) == reservation["reserved_microcredits"])
        check(await db.fetchval("SELECT sum(reserved_microcredits) FROM credit_reservation_allocations WHERE reservation_id=$1", reservation["id"]) == reservation["reserved_microcredits"])
        check(await db.fetchval("SELECT count(*) FROM credit_reservation_allocations WHERE reservation_id=$1", reservation["id"]) >= 1)
    missing = await seed()
    await cycle(missing)
    await refuse(lambda: refund(missing, uuid4(), "missing"), "credit_reservation_missing")
    groups[phase] = True

    phase = "concurrency"
    async def race(uid, first, second, validate, second_code=None):
        nonlocal races
        pending = None
        async with factory() as s1, factory() as s2:
            tx1, tx2 = await s1.begin(), await s2.begin()
            try:
                one = await asyncio.wait_for(first(s1, uid), 10)
                pid = await s2.scalar(text("SELECT pg_backend_pid()"))
                pending = asyncio.create_task(second(s2, uid))
                deadline = time.monotonic()+5
                while not await db.fetchval("SELECT wait_event_type='Lock' AND cardinality(pg_blocking_pids(pid))>0 FROM pg_stat_activity WHERE pid=$1", pid):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("race_lock_not_observed")
                    assert not pending.done(), "race_participant_ended_early"
                check(not pending.done())
                await tx1.commit()
                try:
                    two = await asyncio.wait_for(pending, 10)
                except CreditAccountingError as error:
                    check(error.code == second_code)
                    two = error.code
                else:
                    check(second_code is None)
                await tx2.commit()
                await validate(uid, one, two)
                races += 1
            finally:
                if pending and not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                if s1.in_transaction():
                    await s1.rollback()
                if s2.in_transaction():
                    await s2.rollback()

    def reserve_op(key, units=1, now=T):
        return lambda session, uid: reserve(session, request=ReservationRequest(uid, key, (estimate(units=units),)), now=now)

    def settle_op(rid, key, units=1, now=T):
        return lambda session, uid: settle(session, user_id=uid, reservation_id=rid,
            usage=UsageReport((line(units=units),)), delivery="delivered", operation_key=key, now=now)

    def release_op(rid, key, now=T):
        return lambda session, uid: release(session, user_id=uid, reservation_id=rid,
            usage=UsageReport(()), reason_code="provider_failed", operation_key=key, now=now)

    compete = await seed()
    async def compete_ok(uid, one, two):
        check(one.status == "held" and two == "user_concurrency_limit")
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", uid) == 1)
    await race(compete, reserve_op("one", 600_000), reserve_op("two", 600_000), compete_ok, "user_concurrency_limit")

    same = await seed()
    async def same_ok(uid, one, two):
        check(two == replace(one, replayed=True))
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", uid) == 1)
    await race(same, reserve_op("same", 2), reserve_op("same", 2), same_ok)

    changed = await seed()
    async def changed_ok(uid, one, two):
        check(two == "credit_idempotency_conflict")
        check(await db.fetchval("SELECT reserved_microcredits FROM credit_reservations WHERE user_id=$1", uid) == 2_000)
    await race(changed, reserve_op("same", 2), reserve_op("same", 3), changed_ok, "credit_idempotency_conflict")

    terminal_user = await seed(); terminal_hold = await hold(terminal_user, "h", (estimate(units=5),))
    async def terminal_ok(uid, one, two):
        check(two == replace(one, replayed=True))
        check(await db.fetchval("SELECT count(*) FROM credit_usage_records WHERE user_id=$1", uid) == 1)
    await race(terminal_user, settle_op(terminal_hold.reservation_id, "same_t", 2),
               settle_op(terminal_hold.reservation_id, "same_t", 2), terminal_ok)

    collision_user = await seed(True); h1 = await hold(collision_user, "h1", (estimate(units=5),)); h2 = await hold(collision_user, "h2", (estimate(units=5),))
    async def terminal_collision(uid, one, two):
        check(two == "credit_idempotency_conflict")
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1 AND status='settled'", uid) == 1)
    await race(collision_user, settle_op(h1.reservation_id, "shared_t", 2),
               settle_op(h2.reservation_id, "shared_t", 2), terminal_collision, "credit_idempotency_conflict")

    choose_user = await seed(); choose_hold = await hold(choose_user, "h", (estimate(units=5),))
    async def choose_ok(uid, one, two):
        check(two == "credit_reservation_state_conflict")
        check(await db.fetchval("SELECT status FROM credit_reservations WHERE id=$1", choose_hold.reservation_id) == "settled")
    await race(choose_user, settle_op(choose_hold.reservation_id, "settle", 2),
               release_op(choose_hold.reservation_id, "release"), choose_ok, "credit_reservation_state_conflict")

    renewal_user = await seed(); await cycle(renewal_user)
    async def renewal_ok(uid, one, two):
        check(one.cycle_index == 1 and two.status == "held")
        check(await db.fetchval("SELECT count(*) FROM credit_cycles WHERE user_id=$1", uid) == 2)
    await race(renewal_user, lambda session, uid: ensure_cycle(session, user_id=uid, now=END),
               reserve_op("after", 2, END), renewal_ok)

    late_user = await seed(); late_hold = await hold(late_user, "old", (estimate(units=10),))
    async def late_ok(uid, one, two):
        check(one.cycle_index == 1 and two.consumed_microcredits == 4_000 and two.released_microcredits == 6_000)
        check(await db.fetchval("SELECT expired_delta FROM credit_ledger_events WHERE operation_key=$1", "terminal_"+late_hold.reservation_id.hex) == 6_000)
    await race(late_user, lambda session, uid: ensure_cycle(session, user_id=uid, now=END),
               settle_op(late_hold.reservation_id, "late", 4, END), late_ok)

    await reconstruct()
    check(races == 8)
    groups[phase] = True
    assert set(groups) == set(GROUPS) and all(groups.values()) and checks >= 160
    return dict(groups=groups, races=races, checks=checks, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import app.models
    import app.credit_models
    global phase
    raw_url = os.environ.get("DATABASE_URL", "")
    url = make_url(raw_url)
    validate_target(os.environ.get("ACCOUNTING_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(raw_url.replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(raw_url)
    try:
        assert await db.fetchval("SELECT current_database()") == url.database
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        for table in ("users",)+TABLES:
            assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0, "nonempty_target_refused"
        result = await asyncio.wait_for(proof(db, async_sessionmaker(engine, expire_on_commit=False)), 260)
        phase = "done"
        print(json.dumps(result))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print("accounting_proof_failed:"+phase)
        sys.exit(124)
    except Exception:
        print("accounting_proof_failed:"+phase)
        sys.exit(1)
