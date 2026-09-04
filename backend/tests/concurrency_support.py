"""Fixed isolated PostgreSQL proof for G8 per-User concurrency admission."""
import asyncio, json, os, re, sys
from datetime import datetime, timezone
from uuid import uuid4

HEAD = "0006_credit_accounting_persistence"
GROUPS = ("plans", "sequential", "terminal_return", "replay", "same_user_race",
          "cross_user", "product_callers", "failure_safety")
T = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"concurrency-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.port != 5432 or url.database != project.replace("-", "_")
            or url.username != "credit" or provider != "mock" or app_env != "test"):
        raise ValueError("concurrency_target_refused")


async def proof(db, factory):
    from fastapi import HTTPException
    from app.api import generations, pipelines, prompts
    from app.auth.service import AuthenticatedUser
    from app.credit_accounting import (CreditAccountingError, ReservationRequest,
        UsageEstimate, UsageLine, UsageReport, release, reserve, settle)
    from app.credit_lifecycle import change_plan, ensure_cycle
    from app.models import GenerationMode, Job, JobState
    from app.prompt_credit import PromptCreditError, execute_prompt_enhancement
    from app.prompt_enhancement import CreativityPreset
    from app.schemas import PromptEnhanceRequest
    from app.services.llm import enhancer
    global phase
    checks = races = 0
    groups = {}

    def check(value):
        nonlocal checks
        assert value, "concurrency_assertion"
        checks += 1

    async def seed(plan="free", *, master=False):
        uid = uuid4()
        if master:
            await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)",
                             uid, uid.hex, uid.hex+"@example.invalid", T)
        else:
            await db.execute("INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) VALUES($1,false,'user','active','synthetic',$2,$2)", uid, T)
        async with factory() as session, session.begin():
            await ensure_cycle(session, user_id=uid, now=T)
            if plan != "free" and not master:
                await change_plan(session, user_id=uid, target_plan=plan,
                                  operation_key="g8_plan_"+uid.hex, now=T)
        return uid

    def request(uid, key, *, meter="gemini_input_token", units=1):
        return ReservationRequest(uid, key, (UsageEstimate(meter, units),))

    async def hold(uid, key, *, meter="gemini_input_token", units=1, delay=0):
        async with factory() as session, session.begin():
            result = await reserve(session, request=request(uid, key, meter=meter, units=units), now=T)
            if delay:
                await asyncio.sleep(delay)
            return result

    async def refund(uid, rid, key, *, delay=0):
        async with factory() as session, session.begin():
            result = await release(session, user_id=uid, reservation_id=rid,
                usage=UsageReport(()), reason_code="provider_failed",
                operation_key=key, now=T)
            if delay:
                await asyncio.sleep(delay)
            return result

    async def consume(uid, rid, key):
        async with factory() as session, session.begin():
            return await settle(session, user_id=uid, reservation_id=rid,
                usage=UsageReport((UsageLine("gemini_input_token", 1, "mock_estimate"),)),
                delivery="delivered", operation_key=key, now=T)

    async def refusal(call, code):
        try:
            await call()
        except CreditAccountingError as error:
            check(error.code == code)
            return error.code
        raise AssertionError("concurrency_refusal_missing")

    async def observe_lock(tasks):
        nonlocal races
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            waiting = await db.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'")
            if waiting:
                races += 1
                check(waiting >= 1)
                return
            if all(task.done() for task in tasks):
                break
            await asyncio.sleep(0.01)
        raise AssertionError("concurrency_lock_not_observed")

    async def burst(uid, limit, label):
        start = asyncio.Event()
        async def attempt(index):
            await start.wait()
            try:
                return await hold(uid, f"{label}_{index}", delay=.05)
            except CreditAccountingError as error:
                return error.code
        tasks = [asyncio.create_task(attempt(index)) for index in range(50)]
        start.set()
        await observe_lock(tasks)
        outcomes = await asyncio.gather(*tasks)
        accepted = [item for item in outcomes if not isinstance(item, str)]
        refused = [item for item in outcomes if isinstance(item, str)]
        check(len(accepted) == limit)
        check(len(refused) == 50-limit)
        for value in outcomes:
            check(not isinstance(value, str) or value == "user_concurrency_limit")
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1 AND status='held'", uid) == limit)
        return accepted

    phase = "plans"
    plan_cases = (("free", 1, False), ("pro", 3, False),
                  ("max", 5, False), ("max", 5, True))
    plan_users = []
    for plan, limit, master in plan_cases:
        uid = await seed(plan, master=master)
        plan_users.append((uid, limit, plan, master))
        check(await db.fetchval("SELECT plan FROM credit_accounts WHERE user_id=$1", uid) == plan)
        check(limit in (1, 3, 5))
    groups[phase] = True

    phase = "sequential"
    uid = await seed()
    first = await hold(uid, "sequential_1")
    before = await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", uid)
    await refusal(lambda: hold(uid, "sequential_2"), "user_concurrency_limit")
    check(before == 1 == await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", uid))
    await refusal(lambda: hold(uid, "unentitled", meter="imagen_ultra_image"), "credit_plan_refused")
    check(first.status == "held")
    groups[phase] = True

    phase = "terminal_return"
    settled_user = await seed(); held = await hold(settled_user, "settle_hold")
    done = await consume(settled_user, held.reservation_id, "settle_terminal")
    replacement = await hold(settled_user, "after_settle")
    check(done.status == "settled" and replacement.status == "held")
    released_user = await seed(); held = await hold(released_user, "release_hold")
    done = await refund(released_user, held.reservation_id, "release_terminal")
    replacement = await hold(released_user, "after_release")
    check(done.status == "released" and replacement.status == "held")
    groups[phase] = True

    phase = "replay"
    replay_user = await seed(); original = await hold(replay_user, "same")
    locked = asyncio.Event()
    async def slow_replay():
        async with factory() as session, session.begin():
            result = await reserve(session, request=request(replay_user, "same"), now=T)
            locked.set(); await asyncio.sleep(.1); return result
    async def waiting_replay():
        await locked.wait(); return await hold(replay_user, "same")
    tasks = [asyncio.create_task(slow_replay()), asyncio.create_task(waiting_replay())]
    await observe_lock(tasks)
    replayed = await asyncio.gather(*tasks)
    check(all(item.replayed and item.reservation_id == original.reservation_id for item in replayed))
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", replay_user) == 1)
    await refusal(lambda: hold(replay_user, "same", units=2), "credit_idempotency_conflict")
    groups[phase] = True

    phase = "same_user_race"
    for uid, limit, plan, master in plan_users:
        accepted = await burst(uid, limit, "burst")
        check(len({item.reservation_id for item in accepted}) == limit)
        check((plan, master) in (("free", False), ("pro", False), ("max", False), ("max", True)))
    groups[phase] = True

    phase = "cross_user"
    left, right = await seed(), await seed()
    start = asyncio.Event()
    async def side(uid, label):
        await start.wait(); return await hold(uid, label, delay=.05)
    tasks = [asyncio.create_task(side(left, "left")), asyncio.create_task(side(right, "right"))]
    start.set(); outcomes = await asyncio.gather(*tasks)
    check(all(item.status == "held" for item in outcomes))
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=ANY($1::uuid[])", [left, right]) == 2)
    groups[phase] = True

    phase = "product_callers"
    product_user = await seed(); await hold(product_user, "occupied")
    actor = AuthenticatedUser(id=product_user, role="user", status="active", email="synthetic@example.invalid")
    payload = PromptEnhanceRequest(request_id=uuid4(), prompt="synthetic",
        target_mode=GenerationMode.T2I, target_model="imagen-4.0-fast-generate-001",
        creativity_preset=CreativityPreset.BALANCED)
    provider_calls = 0
    original_enhance = enhancer.enhance_prompt
    async def forbidden_provider(*_args, **_kwargs):
        nonlocal provider_calls; provider_calls += 1
        raise AssertionError("provider_called_after_concurrency_refusal")
    enhancer.enhance_prompt = forbidden_provider
    try:
        async with factory() as session:
            try: await execute_prompt_enhancement(session, actor=actor, payload=payload)
            except PromptCreditError as error: check(error.code == "user_concurrency_limit")
            else: raise AssertionError("prompt_concurrency_refusal_missing")
    finally: enhancer.enhance_prompt = original_enhance
    check(provider_calls == 0)
    check(prompts._status_code_for_prompt_credit_error(PromptCreditError("user_concurrency_limit")) == 429)

    def make_job(mode=GenerationMode.T2I, *, parent=None, blocked=False):
        return Job(id=uuid4(), owner_user_id=product_user, mode=mode,
            model="imagen-4.0-fast-generate-001" if mode == GenerationMode.T2I else "veo-3.0-fast-generate-001",
            state=JobState.PENDING, prompt="synthetic", parent_job_id=parent,
            blocked=blocked, attempts=0,
            parameters={"number_of_images": 1} if mode == GenerationMode.T2I else {"duration_sec": 4},
            state_history=[], vertex_charged=False, created_at=T, updated_at=T)
    for kind in ("generation", "retry"):
        async with factory() as session:
            item = make_job(); session.add(item)
            try: await generations._admit_generation(session, item, now=T)
            except HTTPException as error: check(error.status_code == 429 and error.detail == "user_concurrency_limit")
            else: raise AssertionError(kind+"_concurrency_refusal_missing")
    async with factory() as session:
        parent = make_job(); child = make_job(GenerationMode.I2V, parent=parent.id, blocked=True)
        session.add_all([parent, child])
        try: await pipelines._admit_generation(session, parent, pipeline_child=child, now=T)
        except HTTPException as error: check(error.status_code == 429 and error.detail == "user_concurrency_limit")
        else: raise AssertionError("pipeline_concurrency_refusal_missing")
    check(await db.fetchval("SELECT count(*) FROM jobs WHERE owner_user_id=$1", product_user) == 0)
    check(await db.fetchval("SELECT count(*) FROM prompt_enhancements WHERE owner_user_id=$1", product_user) == 0)
    groups[phase] = True

    phase = "failure_safety"
    rollback_user = await seed()
    try:
        async with factory() as session, session.begin():
            await reserve(session, request=request(rollback_user, "rolled_back"), now=T)
            raise RuntimeError("synthetic_rollback")
    except RuntimeError:
        pass
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", rollback_user) == 0)

    race_user = await seed(); old = await hold(race_user, "old")
    terminal_locked = asyncio.Event()
    async def slow_terminal():
        async with factory() as session, session.begin():
            result = await release(session, user_id=race_user, reservation_id=old.reservation_id,
                usage=UsageReport(()), reason_code="provider_failed", operation_key="old_terminal", now=T)
            terminal_locked.set(); await asyncio.sleep(.1); return result
    async def after_terminal():
        await terminal_locked.wait(); return await hold(race_user, "new")
    tasks = [asyncio.create_task(slow_terminal()), asyncio.create_task(after_terminal())]
    await observe_lock(tasks); terminal, admitted = await asyncio.gather(*tasks)
    check(terminal.status == "released" and admitted.status == "held")
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1 AND status='held'", race_user) == 1)
    abandoned = await seed(); await hold(abandoned, "abandoned")
    await refusal(lambda: hold(abandoned, "blocked"), "user_concurrency_limit")
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", abandoned) == 1)
    groups[phase] = True

    check(races >= 6)
    assert set(groups) == set(GROUPS) and all(groups.values()) and checks >= 180
    return dict(groups=groups, races=races, checks=checks, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import app.models, app.credit_models
    global phase
    raw = os.environ.get("DATABASE_URL", ""); url = make_url(raw)
    validate_target(os.environ.get("CONCURRENCY_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(raw.replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(raw, pool_size=12, max_overflow=50)
    try:
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        for table in ("users", "credit_reservations", "jobs", "prompt_enhancements"):
            assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0
        result = await asyncio.wait_for(proof(db, async_sessionmaker(engine, expire_on_commit=False)), 330)
        phase = "done"; print(json.dumps(result))
    finally:
        await engine.dispose(); await db.close()


if __name__ == "__main__":
    try: asyncio.run(main())
    except TimeoutError: print("concurrency_proof_failed:"+phase); sys.exit(124)
    except Exception: print("concurrency_proof_failed:"+phase); sys.exit(1)
