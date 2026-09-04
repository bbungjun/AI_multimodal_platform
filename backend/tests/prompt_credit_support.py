"""Fixed PostgreSQL proof for G6 prompt-credit integration."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from uuid import uuid4

HEAD = "0006_credit_accounting_persistence"
GROUPS = ("preflight", "admission", "terminal", "replay_race")
T = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"prompt-credit-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.port != 5432 or url.database != project.replace("-", "_")
            or url.username != "credit" or provider != "mock" or app_env != "test"):
        raise ValueError("prompt_credit_target_refused")


async def proof(db, factory):
    from app.auth.service import AuthenticatedUser
    from app.credit_accounting import (
        CreditAccountingError, ReservationRequest, UsageEstimate, UsageLine,
        UsageReport, reserve, settle,
    )
    from app.credit_policy import plan_policy
    from app.models import GenerationMode
    from app.prompt_credit import PromptCreditError, execute_prompt_enhancement
    import app.prompt_credit as module
    from app.prompt_enhancement import CreativityPreset
    from app.schemas import PromptEnhanceRequest
    from app.services.llm import enhancer
    from app.services.vertex.errors import (
        VertexRateLimitedError, VertexTransientError,
    )
    global phase
    checks = races = provider_calls = 0
    groups = {}

    def check(value):
        nonlocal checks
        assert value, "prompt_credit_assertion"
        checks += 1

    async def seed(*, master=False):
        uid = uuid4()
        if master:
            await db.execute(
                "INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)",
                uid, uid.hex, uid.hex + "@example.invalid", T,
            )
        else:
            await db.execute(
                "INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) "
                "VALUES($1,false,'user','active','synthetic',$2,$2)", uid, T,
            )
        return uid

    def actor(uid, *, master=False):
        return AuthenticatedUser(
            id=uid, role="master" if master else "user", status="active",
            email="fixture@invalid.test",
        )

    def payload(request_id=None, prompt="fixture"):
        return PromptEnhanceRequest(
            request_id=request_id or uuid4(), prompt=prompt,
            target_mode=GenerationMode.T2I,
            target_model="imagen-4.0-fast-generate-001",
            creativity_preset=CreativityPreset.BALANCED,
        )

    async def invoke(uid, request, *, master=False):
        async with factory() as session:
            return await execute_prompt_enhancement(
                session, actor=actor(uid, master=master), payload=request,
                clock=lambda: T,
            )

    async def mock_success(prompt, *, target_mode, target_model,
                           creativity_preset, llm_model=None, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return enhancer.PromptEnhancementResult(
            original=prompt, enhanced="fixture enhanced",
            components={"subject": "fixture"}, target_mode=target_mode,
            target_model=target_model, llm_model=llm_model or "gemini-mock",
            latency_ms=0, tokens_in=7, tokens_out=11,
            usage_source="mock_estimate", creativity_preset=creativity_preset,
        )

    original_enhance = module.enhancer.enhance_prompt
    module.enhancer.enhance_prompt = mock_success
    try:
        phase = "preflight"
        plan = enhancer.plan_prompt_enhancement(
            "fixture", target_mode=GenerationMode.T2I,
            target_model="imagen-4.0-fast-generate-001",
        )
        check(plan.maximum_input_tokens > 0)
        check(plan.maximum_output_tokens == 4800)
        check(all("gemini_input_token" in plan_policy(name).permitted_meters
                  for name in ("free", "pro", "max")))
        check(all("gemini_output_token" in plan_policy(name).permitted_meters
                  for name in ("free", "pro", "max")))
        groups[phase] = True

        phase = "admission"
        normal = await seed()
        request = payload()
        outcome = await invoke(normal, request)
        check(outcome.enhancement.id == request.request_id)
        check(outcome.enhancement.owner_user_id == normal)
        check(await db.fetchval("SELECT count(*) FROM credit_accounts WHERE user_id=$1", normal) == 1)
        check(await db.fetchval("SELECT count(*) FROM credit_cycles WHERE user_id=$1", normal) == 1)
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", normal) == 1)
        check(provider_calls == 1)
        master = await seed(master=True)
        await invoke(master, payload(), master=True)
        check(await db.fetchval("SELECT plan FROM credit_accounts WHERE user_id=$1", master) == "max")

        exhausted = await seed()
        async with factory() as session, session.begin():
            held = await reserve(session, request=ReservationRequest(
                exhausted, "exhaust", (UsageEstimate("gemini_input_token", 1_000_000),)
            ), now=T)
        async with factory() as session, session.begin():
            await settle(
                session, user_id=exhausted, reservation_id=held.reservation_id,
                usage=UsageReport((UsageLine("gemini_input_token", 1_000_000, "mock_estimate"),)),
                delivery="delivered", operation_key="exhaust_t", now=T,
            )
        before_calls = provider_calls
        try:
            await invoke(exhausted, payload())
        except PromptCreditError as error:
            check(error.code == "monthly_credit_exhausted")
        else:
            raise AssertionError("exhaustion_missing")
        check(provider_calls == before_calls)
        groups[phase] = True

        phase = "terminal"
        check(await db.fetchval(
            "SELECT count(*) FROM credit_usage_records WHERE user_id=$1 AND charged_microcredits>0", normal
        ) == 2)
        check(await db.fetchval(
            "SELECT count(*) FROM credit_usage_records WHERE user_id=$1 AND source='mock_estimate'", normal
        ) == 2)
        for error, reason in (
            (VertexRateLimitedError(status_code=429), "provider_rate_limited"),
            (VertexTransientError(status_code=504), "provider_timeout"),
            (enhancer.PromptEnhancementResponseError(), "provider_failed"),
        ):
            failed = await seed()
            async def fail(*_args, error=error, **_kwargs):
                raise error
            module.enhancer.enhance_prompt = fail
            try:
                await invoke(failed, payload())
            except type(error):
                pass
            else:
                raise AssertionError("provider_failure_missing")
            check(await db.fetchval(
                "SELECT status FROM credit_reservations WHERE user_id=$1", failed
            ) == "released")
            check(await db.fetchval(
                "SELECT terminal_reason_code FROM credit_reservations WHERE user_id=$1", failed
            ) == reason)
            check(await db.fetchval(
                "SELECT coalesce(sum(charged_microcredits),0) FROM credit_usage_records WHERE user_id=$1", failed
            ) == 0)
        module.enhancer.enhance_prompt = mock_success

        rollback_user = await seed()
        original_settle = module.settle
        async def broken_settle(*_args, **_kwargs):
            raise CreditAccountingError("credit_account_inconsistent")
        module.settle = broken_settle
        try:
            await invoke(rollback_user, payload())
        except PromptCreditError as error:
            check(error.code == "credit_account_unavailable")
        else:
            raise AssertionError("settle_failure_missing")
        finally:
            module.settle = original_settle
        check(await db.fetchval("SELECT count(*) FROM prompt_enhancements WHERE owner_user_id=$1", rollback_user) == 0)
        check(await db.fetchval("SELECT status FROM credit_reservations WHERE user_id=$1", rollback_user) == "released")
        groups[phase] = True

        phase = "replay_race"
        module.enhancer.enhance_prompt = mock_success
        replay_calls = provider_calls
        replay = await invoke(normal, request)
        check(replay.replayed and replay.enhancement.id == request.request_id)
        check(provider_calls == replay_calls)
        try:
            await invoke(normal, payload(request.request_id, "changed"))
        except PromptCreditError as error:
            check(error.code == "credit_idempotency_conflict")
        else:
            raise AssertionError("collision_missing")
        stranger = await seed()
        try:
            await invoke(stranger, request)
        except PromptCreditError as error:
            check(error.code == "credit_idempotency_conflict")
        else:
            raise AssertionError("cross_owner_missing")

        race_user = await seed()
        race_request = payload()
        entered, allow = asyncio.Event(), asyncio.Event()
        async def blocked_success(*args, **kwargs):
            nonlocal provider_calls
            provider_calls += 1
            entered.set()
            await allow.wait()
            result = await mock_success(*args, **kwargs)
            provider_calls -= 1
            return result
        module.enhancer.enhance_prompt = blocked_success
        first = asyncio.create_task(invoke(race_user, race_request))
        await entered.wait()
        try:
            await invoke(race_user, race_request)
        except PromptCreditError as error:
            check(error.code == "prompt_enhancement_in_progress")
        else:
            raise AssertionError("held_replay_missing")
        allow.set()
        completed = await first
        check(completed.enhancement.id == race_request.request_id)
        check(await db.fetchval("SELECT count(*) FROM prompt_enhancements WHERE owner_user_id=$1", race_user) == 1)
        check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1", race_user) == 1)
        races += 1
        groups[phase] = True
    finally:
        module.enhancer.enhance_prompt = original_enhance

    assert set(groups) == set(GROUPS) and all(groups.values()) and checks >= 30 and races >= 1
    return dict(groups=groups, races=races, checks=checks, provider_calls=provider_calls, complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import app.models
    import app.credit_models
    global phase
    raw_url = os.environ.get("DATABASE_URL", "")
    url = make_url(raw_url)
    validate_target(os.environ.get("PROMPT_CREDIT_PROOF_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"))
    db = await asyncpg.connect(raw_url.replace("postgresql+asyncpg:", "postgresql:"))
    engine = create_async_engine(raw_url)
    try:
        assert await db.fetchval("SELECT version_num FROM alembic_version") == HEAD
        assert await db.fetchval("SELECT count(*) FROM users") == 0
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
        print("prompt_credit_proof_failed:" + phase)
        sys.exit(124)
    except Exception:
        print("prompt_credit_proof_failed:" + phase)
        sys.exit(1)
