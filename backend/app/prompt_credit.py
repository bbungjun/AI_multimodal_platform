"""Credit-admitted prompt enhancement behind one transactional Module Interface."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.service import AuthenticatedUser
from app.credit_accounting import (
    CreditAccountingError,
    ReservationRequest,
    UsageEstimate,
    UsageLine,
    UsageReport,
    release,
    reserve,
    settle,
)
from app.credit_models import CreditReservation
from app.models import PromptEnhancement, utc_now
from app.prompt_enhancement import (
    PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY,
    PROMPT_ENHANCEMENT_TEMPLATE_VERSION,
    CreativityPreset,
    normalize_creativity_preset,
    temperature_for_preset,
)
from app.schemas import PromptEnhanceRequest
from app.services.llm import enhancer
from app.services.vertex.errors import VertexServiceError


logger = logging.getLogger(__name__)


class PromptCreditError(Exception):
    """A fixed public code at the prompt/accounting seam."""

    def __init__(self, code: str, *, cause: Exception | None = None) -> None:
        self.code = code
        self.cause = cause
        super().__init__(code)


@dataclass(frozen=True)
class PromptCreditOutcome:
    enhancement: PromptEnhancement
    creativity_preset: CreativityPreset
    temperature: float
    replayed: bool


def _keys(request_id: Any) -> tuple[str, str]:
    return f"pe_r_{request_id.hex}", f"pe_t_{request_id.hex}"


def _mapped_accounting_error(error: CreditAccountingError) -> PromptCreditError:
    code = error.code
    if code == "credit_plan_refused":
        code = "plan_feature_not_allowed"
    elif code not in {
        "monthly_credit_exhausted",
        "user_concurrency_limit",
        "credit_idempotency_conflict",
        "credit_busy",
    }:
        code = "credit_account_unavailable"
    return PromptCreditError(code, cause=error)


def _stored_preset(record: PromptEnhancement) -> CreativityPreset:
    metadata = record.components.get(PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY, {})
    value = metadata.get("creativity_preset") if isinstance(metadata, dict) else None
    try:
        return normalize_creativity_preset(value)
    except (TypeError, ValueError):
        raise PromptCreditError("credit_account_unavailable") from None


def _matches(record: PromptEnhancement, payload: PromptEnhanceRequest) -> bool:
    return (
        record.original == payload.prompt
        and record.target_mode == payload.target_mode
        and record.target_model == payload.target_model
        and _stored_preset(record) == payload.creativity_preset
    )


def _replay(
    record: PromptEnhancement,
    payload: PromptEnhanceRequest,
    actor: AuthenticatedUser,
) -> PromptCreditOutcome:
    if record.owner_user_id != actor.id or not _matches(record, payload):
        raise PromptCreditError("credit_idempotency_conflict")
    preset = _stored_preset(record)
    return PromptCreditOutcome(
        enhancement=record,
        creativity_preset=preset,
        temperature=temperature_for_preset(preset),
        replayed=True,
    )


def _usage_report(result: enhancer.PromptEnhancementResult) -> UsageReport:
    if type(result.tokens_in) is not int or type(result.tokens_out) is not int:
        raise PromptCreditError("credit_account_unavailable")
    return UsageReport(
        lines=(
            UsageLine("gemini_input_token", result.tokens_in, result.usage_source),
            UsageLine("gemini_output_token", result.tokens_out, result.usage_source),
        )
    )


async def _release_hold(
    session: Any,
    *,
    actor: AuthenticatedUser,
    reservation_id: Any,
    terminal_key: str,
    reason: str,
    usage: UsageReport | None = None,
    clock: Callable[[], Any],
) -> None:
    try:
        async with session.begin():
            await release(
                session,
                user_id=actor.id,
                reservation_id=reservation_id,
                usage=usage or UsageReport(lines=()),
                reason_code=reason,
                operation_key=terminal_key,
                now=clock(),
            )
    except Exception as error:
        safe_code = getattr(error, "code", "credit_account_unavailable")
        logger.error("Prompt credit release failed: code=%s", safe_code)


async def execute_prompt_enhancement(
    session: Any,
    *,
    actor: AuthenticatedUser,
    payload: PromptEnhanceRequest,
    clock: Callable[[], Any] = utc_now,
) -> PromptCreditOutcome:
    """Reserve, call the provider outside a transaction, and terminalize once."""
    plan = enhancer.plan_prompt_enhancement(
        payload.prompt,
        target_mode=payload.target_mode,
        target_model=payload.target_model,
        creativity_preset=payload.creativity_preset,
    )
    reserve_key, terminal_key = _keys(payload.request_id)

    try:
        async with session.begin():
            existing = await session.scalar(
                select(PromptEnhancement).where(PromptEnhancement.id == payload.request_id)
            )
            if existing is not None:
                return _replay(existing, payload, actor)
            receipt = await reserve(
                session,
                request=ReservationRequest(
                    user_id=actor.id,
                    operation_key=reserve_key,
                    estimates=(
                        UsageEstimate("gemini_input_token", plan.maximum_input_tokens),
                        UsageEstimate("gemini_output_token", plan.maximum_output_tokens),
                    ),
                ),
                now=clock(),
            )
            reservation_status = await session.scalar(
                select(CreditReservation.status).where(
                    CreditReservation.id == receipt.reservation_id,
                    CreditReservation.user_id == actor.id,
                )
            )
            if receipt.replayed:
                code = (
                    "prompt_enhancement_in_progress"
                    if reservation_status == "held"
                    else "prompt_enhancement_terminal"
                )
                raise PromptCreditError(code)
    except CreditAccountingError as error:
        raise _mapped_accounting_error(error) from error

    try:
        result = await enhancer.enhance_prompt(
            payload.prompt,
            target_mode=payload.target_mode,
            target_model=payload.target_model,
            creativity_preset=payload.creativity_preset,
            llm_model=plan.llm_model,
        )
    except VertexServiceError as error:
        if error.code == "vertex_rate_limited":
            reason = "provider_rate_limited"
        elif error.status_code in {408, 504}:
            reason = "provider_timeout"
        else:
            reason = "provider_failed"
        await _release_hold(
            session,
            actor=actor,
            reservation_id=receipt.reservation_id,
            terminal_key=terminal_key,
            reason=reason,
            clock=clock,
        )
        raise

    try:
        usage = _usage_report(result)
    except PromptCreditError:
        await _release_hold(
            session,
            actor=actor,
            reservation_id=receipt.reservation_id,
            terminal_key=terminal_key,
            reason="delivery_failed",
            clock=clock,
        )
        raise
    components = dict(result.components)
    components[PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY] = {
        "creativity_preset": result.creativity_preset.value,
        "temperature": result.temperature,
        "template_version": PROMPT_ENHANCEMENT_TEMPLATE_VERSION,
    }
    record = PromptEnhancement(
        id=payload.request_id,
        owner_user_id=actor.id,
        original=result.original,
        enhanced=result.enhanced,
        components=components,
        target_mode=result.target_mode,
        target_model=result.target_model,
        llm_model=result.llm_model,
        latency_ms=result.latency_ms,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
    )
    try:
        async with session.begin():
            session.add(record)
            await session.flush()
            await settle(
                session,
                user_id=actor.id,
                reservation_id=receipt.reservation_id,
                usage=usage,
                delivery="delivered",
                operation_key=terminal_key,
                now=clock(),
            )
    except (CreditAccountingError, IntegrityError) as error:
        await _release_hold(
            session,
            actor=actor,
            reservation_id=receipt.reservation_id,
            terminal_key=terminal_key,
            reason="delivery_failed",
            usage=usage,
            clock=clock,
        )
        if isinstance(error, CreditAccountingError):
            raise _mapped_accounting_error(error) from error
        raise PromptCreditError("credit_account_unavailable", cause=error) from error
    except Exception as error:
        await _release_hold(
            session,
            actor=actor,
            reservation_id=receipt.reservation_id,
            terminal_key=terminal_key,
            reason="delivery_failed",
            usage=usage,
            clock=clock,
        )
        raise PromptCreditError("credit_account_unavailable", cause=error) from error

    return PromptCreditOutcome(
        enhancement=record,
        creativity_preset=result.creativity_preset,
        temperature=result.temperature,
        replayed=False,
    )
