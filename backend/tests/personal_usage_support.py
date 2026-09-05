"""Fixed isolated PostgreSQL proof for the G9A personal usage read model."""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4


from app.schema_revision import CODE_REVISION as HEAD
GROUPS = (
    "new_user",
    "plans",
    "balance",
    "meters",
    "renewal",
    "active_requests",
    "snapshot_races",
    "failure_privacy",
)
T = datetime(2025, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
END = T + timedelta(days=30)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (
        not re.fullmatch(r"personal-usage-verify-[a-z0-9]{12}", project)
        or url.get_backend_name() != "postgresql"
        or url.host != "db"
        or url.port != 5432
        or url.database != project.replace("-", "_")
        or url.username != "credit"
        or provider != "mock"
        or app_env != "test"
    ):
        raise ValueError("personal_usage_target_refused")


async def proof(db, factory):
    from sqlalchemy import text

    from app.credit_accounting import (
        ReservationRequest,
        UsageEstimate,
        UsageLine,
        UsageReport,
        release,
        reserve,
        settle,
    )
    from app.credit_lifecycle import change_plan, ensure_cycle, grant_bonus
    from app.personal_usage import METER_UNITS, PersonalUsageError, read_personal_usage
    from app.schemas import PersonalUsageResponse

    global phase
    checks = 0
    races = 0
    groups = {}

    def check(condition):
        nonlocal checks
        assert condition, "personal_usage_assertion"
        checks += 1

    async def seed(*, master=False):
        uid = uuid4()
        if master:
            marker = uuid4().hex
            await db.execute(
                "INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)",
                uid,
                marker,
                marker + "@example.invalid",
                T,
            )
        else:
            await db.execute(
                "INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,false,'user','active','synthetic',$2,$2)",
                uid,
                T,
            )
        return uid

    async def in_tx(call):
        async with factory() as session, session.begin():
            return await call(session)

    async def read(uid, now=T):
        return await in_tx(lambda session: read_personal_usage(session, user_id=uid, now=now))

    async def set_plan(uid, plan, key):
        return await in_tx(
            lambda session: change_plan(
                session, user_id=uid, target_plan=plan, operation_key=key, now=T
            )
        )

    def estimate(meter="gemini_input_token", units=1):
        return UsageEstimate(meter, units)

    def line(meter="gemini_input_token", units=1, source="mock_estimate"):
        return UsageLine(meter, units, source)

    async def hold(uid, key, estimates=(UsageEstimate("gemini_input_token", 1),)):
        return await in_tx(
            lambda session: reserve(
                session,
                request=ReservationRequest(uid, key, tuple(estimates)),
                now=T,
            )
        )

    async def consume(uid, reservation_id, key, lines, delivery="delivered"):
        return await in_tx(
            lambda session: settle(
                session,
                user_id=uid,
                reservation_id=reservation_id,
                usage=UsageReport(tuple(lines)),
                delivery=delivery,
                operation_key=key,
                now=T,
            )
        )

    async def refund(uid, reservation_id, key, lines=()):
        return await in_tx(
            lambda session: release(
                session,
                user_id=uid,
                reservation_id=reservation_id,
                usage=UsageReport(tuple(lines)),
                reason_code="provider_failed",
                operation_key=key,
                now=T,
            )
        )

    def validate_view(view):
        check(view.plan in {"free", "pro", "max"})
        check(view.pending_plan in {None, "free", "pro"})
        check(view.rate_card_version == "v1")
        check(type(view.cycle.index) is int and view.cycle.index >= 0)
        check(view.cycle.starts_at < view.cycle.renews_at)
        check(type(view.cycle.allowance_microcredits) is int)
        check(type(view.cycle.charged_microcredits) is int)
        check(type(view.credit.available_microcredits) is int)
        check(type(view.credit.held_microcredits) is int)
        check(type(view.concurrency.active_requests) is int)
        check(type(view.concurrency.limit) is int)
        check(len(view.usage) == 7)
        check(tuple((item.meter, item.unit) for item in view.usage) == METER_UNITS)
        for item in view.usage:
            check(type(item.observed_units) is int and item.observed_units >= 0)
            check(type(item.charged_microcredits) is int and item.charged_microcredits >= 0)
        return view

    phase = "new_user"
    new_user = await seed()
    view = validate_view(await read(new_user))
    check(view.plan == "free" and view.cycle.index == 0)
    check(view.credit.available_microcredits == 1_000_000_000)
    check(view.credit.held_microcredits == 0 and view.concurrency.active_requests == 0)
    check(all(item.observed_units == item.charged_microcredits == 0 for item in view.usage))
    groups[phase] = True

    phase = "plans"
    cases = (("free", 1), ("pro", 3), ("max", 5))
    for plan, limit in cases:
        uid = await seed()
        if plan != "free":
            await set_plan(uid, plan, "plan_" + plan)
        item = validate_view(await read(uid))
        check(item.plan == plan and item.concurrency.limit == limit)
    pending_user = await seed()
    await set_plan(pending_user, "max", "plan_max")
    await set_plan(pending_user, "pro", "plan_down")
    pending = validate_view(await read(pending_user))
    check(pending.plan == "max" and pending.pending_plan == "pro")
    master = await seed(master=True)
    master_view = validate_view(await read(master))
    check(master_view.plan == "max" and master_view.concurrency.limit == 5)
    groups[phase] = True

    phase = "balance"
    balance_user = await seed()
    await read(balance_user)
    await in_tx(
        lambda session: grant_bonus(
            session,
            user_id=balance_user,
            amount_microcredits=200_000_000,
            expires_at=None,
            reason_code="support",
            operation_key="bonus",
            now=T,
        )
    )
    balance_hold = await hold(balance_user, "balance_hold", (estimate(units=100),))
    balance = validate_view(await read(balance_user))
    check(balance.credit.available_microcredits == 1_199_900_000)
    check(balance.credit.held_microcredits == 100_000)
    check(balance.concurrency.active_requests == 1)
    check(balance_hold.reserved_microcredits == balance.credit.held_microcredits)
    groups[phase] = True

    phase = "meters"
    meter_user = await seed()
    await set_plan(meter_user, "max", "meter_max")
    estimates = tuple(estimate(meter, index + 1) for index, (meter, _) in enumerate(METER_UNITS))
    meter_hold = await hold(meter_user, "meter_hold", estimates)
    meter_lines = tuple(line(meter, index + 1) for index, (meter, _) in enumerate(METER_UNITS))
    await consume(meter_user, meter_hold.reservation_id, "meter_done", meter_lines, "partial")
    attempted = await hold(meter_user, "attempted", (estimate("gemini_input_token", 9),))
    await refund(
        meter_user,
        attempted.reservation_id,
        "attempted_done",
        (line("gemini_input_token", 7, "estimated"),),
    )
    meters = validate_view(await read(meter_user))
    expected_observed = {meter: index + 1 for index, (meter, _) in enumerate(METER_UNITS)}
    expected_observed["gemini_input_token"] += 7
    for item in meters.usage:
        check(item.observed_units == expected_observed[item.meter])
        if item.meter == "gemini_input_token":
            check(item.charged_microcredits == 1_000)
    check(meters.cycle.charged_microcredits == sum(item.charged_microcredits for item in meters.usage))
    groups[phase] = True

    phase = "renewal"
    renewal_user = await seed()
    await set_plan(renewal_user, "max", "renew_max")
    await set_plan(renewal_user, "free", "renew_down")
    old = await hold(renewal_user, "renew_hold", (estimate(units=2),))
    await consume(renewal_user, old.reservation_id, "renew_done", (line(units=1),))
    before = validate_view(await read(renewal_user, END - timedelta(microseconds=1)))
    after = validate_view(await read(renewal_user, END))
    check(before.cycle.index == 0 and before.cycle.charged_microcredits == 1_000)
    check(after.cycle.index == 1 and after.cycle.starts_at == END)
    check(after.plan == "free" and after.pending_plan is None)
    check(after.cycle.charged_microcredits == 0)
    check(all(item.observed_units == item.charged_microcredits == 0 for item in after.usage))
    groups[phase] = True

    phase = "active_requests"
    active_user = await seed()
    await set_plan(active_user, "pro", "active_pro")
    first = await hold(active_user, "active_one", (estimate(units=3),))
    second = await hold(active_user, "active_two", (estimate(units=4),))
    held = validate_view(await read(active_user))
    check(held.concurrency.active_requests == 2 and held.credit.held_microcredits == 7_000)
    await consume(active_user, first.reservation_id, "active_one_done", (line(units=1),))
    await refund(active_user, second.reservation_id, "active_two_done")
    returned = validate_view(await read(active_user))
    check(returned.concurrency.active_requests == 0 and returned.credit.held_microcredits == 0)
    groups[phase] = True

    async def observe_lock(pid, pending):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            waiting = await db.fetchval(
                "SELECT wait_event_type='Lock' AND cardinality(pg_blocking_pids(pid))>0 "
                "FROM pg_stat_activity WHERE pid=$1",
                pid,
            )
            if waiting:
                check(not pending.done())
                return
            if pending.done():
                break
            await asyncio.sleep(0.01)
        raise AssertionError("personal_usage_lock_not_observed")

    async def race(uid, first, second, validate):
        nonlocal races
        pending = None
        async with factory() as left, factory() as right:
            left_tx = await left.begin()
            right_tx = await right.begin()
            try:
                one = await first(left, uid)
                pid = await right.scalar(text("SELECT pg_backend_pid()"))
                pending = asyncio.create_task(second(right, uid))
                await observe_lock(pid, pending)
                await left_tx.commit()
                two = await asyncio.wait_for(pending, 10)
                await right_tx.commit()
                await validate(uid, one, two)
                races += 1
            finally:
                if pending is not None and not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                if left.in_transaction():
                    await left.rollback()
                if right.in_transaction():
                    await right.rollback()

    phase = "snapshot_races"
    race_reserve_user = await seed()

    async def race_read(session, uid):
        return await read_personal_usage(session, user_id=uid, now=T)

    async def race_reserve(session, uid):
        return await reserve(
            session,
            request=ReservationRequest(uid, "race_reserve", (estimate(units=2),)),
            now=T,
        )

    async def reserve_ok(uid, first_view, reservation):
        check(first_view.concurrency.active_requests == 0 and reservation.status == "held")
        check((await read(uid)).concurrency.active_requests == 1)

    await race(race_reserve_user, race_read, race_reserve, reserve_ok)

    race_terminal_user = await seed()
    terminal_hold = await hold(race_terminal_user, "race_terminal_hold", (estimate(units=2),))

    async def race_terminal(session, uid):
        return await release(
            session,
            user_id=uid,
            reservation_id=terminal_hold.reservation_id,
            usage=UsageReport(()),
            reason_code="provider_failed",
            operation_key="race_terminal_done",
            now=T,
        )

    async def terminal_ok(uid, first_view, terminal):
        check(first_view.concurrency.active_requests == 1 and terminal.status == "released")
        check((await read(uid)).concurrency.active_requests == 0)

    await race(race_terminal_user, race_read, race_terminal, terminal_ok)

    race_lifecycle_user = await seed()

    async def race_renew(session, uid):
        return await ensure_cycle(session, user_id=uid, now=END)

    async def lifecycle_ok(uid, first_view, next_cycle):
        check(first_view.cycle.index == 0 and next_cycle.cycle_index == 1)
        check((await read(uid, END)).cycle.index == 1)

    await race(race_lifecycle_user, race_read, race_renew, lifecycle_ok)
    check(races == 3)
    groups[phase] = True

    phase = "failure_privacy"
    rollback_user = await seed()
    try:
        async with factory() as session, session.begin():
            validate_view(await read_personal_usage(session, user_id=rollback_user, now=T))
            raise RuntimeError("synthetic_rollback")
    except RuntimeError:
        pass
    check(await db.fetchval("SELECT count(*) FROM credit_accounts WHERE user_id=$1", rollback_user) == 0)

    corrupt_user = await seed()
    await read(corrupt_user)
    await db.execute(
        "UPDATE credit_grants SET reserved_microcredits=1 WHERE user_id=$1",
        corrupt_user,
    )
    try:
        await read(corrupt_user)
    except PersonalUsageError as error:
        check(error.code == "usage_unavailable")
    else:
        raise AssertionError("personal_usage_corruption_not_refused")

    owner_left = await seed()
    owner_right = await seed()
    left_hold = await hold(owner_left, "owner_left", (estimate(units=2),))
    await consume(owner_left, left_hold.reservation_id, "owner_left_done", (line(units=1),))
    left_view = validate_view(await read(owner_left))
    right_view = validate_view(await read(owner_right))
    check(left_view.cycle.charged_microcredits == 1_000)
    check(right_view.cycle.charged_microcredits == 0)
    check(set(PersonalUsageResponse.model_fields) == {
        "plan", "pending_plan", "rate_card_version", "cycle", "credit", "concurrency", "usage"
    })
    check(not ({"user_id", "email", "operation_key", "prompt", "session", "oauth"} & set(PersonalUsageResponse.model_fields)))
    groups[phase] = True

    check(races >= 3)
    assert set(groups) == set(GROUPS) and all(groups.values()) and checks >= 160
    return {"groups": groups, "races": races, "checks": checks, "complete": True}


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.credit_models
    import app.models

    global phase
    raw_url = os.environ.get("DATABASE_URL", "")
    url = make_url(raw_url)
    validate_target(
        os.environ.get("PERSONAL_USAGE_PROOF_PROJECT", ""),
        url,
        os.environ.get("AI_PROVIDER"),
        os.environ.get("APP_ENV"),
    )
    db = await asyncpg.connect(raw_url.replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(raw_url, pool_size=8, max_overflow=16)
    try:
        assert await db.fetchval("SELECT current_database()") == url.database
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        for table in ("users", "credit_accounts", "credit_reservations", "credit_usage_records"):
            assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0, "nonempty_target_refused"
        result = await asyncio.wait_for(
            proof(db, async_sessionmaker(engine, expire_on_commit=False)),
            105,
        )
        phase = "done"
        print(json.dumps(result))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print("personal_usage_proof_failed:" + phase)
        sys.exit(124)
    except Exception:
        print("personal_usage_proof_failed:" + phase)
        sys.exit(1)
