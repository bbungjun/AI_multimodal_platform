from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.api.auth_dependencies import require_user
from app.auth.service import AuthenticatedUser
from app import prompt_credit
from app.prompt_enhancement import PROMPT_ENHANCEMENT_TEMPLATE_VERSION
from app.schemas import PromptEnhanceRequest, PromptEnhancementResponse
from app.services.ops.runtime import runtime_metrics
from app.services.vertex.errors import VertexServiceError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompts", tags=["prompts"])


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@router.post(
    "/enhance",
    response_model=PromptEnhancementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enhance_prompt(
    payload: PromptEnhanceRequest,
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> PromptEnhancementResponse:
    try:
        outcome = await prompt_credit.execute_prompt_enhancement(
            session,
            actor=actor,
            payload=payload,
        )
    except prompt_credit.PromptCreditError as exc:
        raise HTTPException(
            status_code=_status_code_for_prompt_credit_error(exc),
            detail={"code": exc.code, "message": _message_for_prompt_credit_error(exc)},
        ) from exc
    except VertexServiceError as exc:
        public = exc.to_public_dict()
        runtime_metrics.record_provider_failure(
            code=str(public["code"]),
            status_code=(
                public["status_code"] if isinstance(public["status_code"], int) else None
            ),
            retryable=public["retryable"] is True,
        )
        logger.warning(
            "Prompt enhancement failed: code=%s retryable=%s status=%s",
            public["code"],
            public["retryable"],
            public["status_code"],
        )
        raise HTTPException(
            status_code=_status_code_for_vertex_error(exc),
            detail=public,
        ) from exc

    prompt_enhancement = outcome.enhancement

    return PromptEnhancementResponse(
        id=prompt_enhancement.id,
        original=prompt_enhancement.original,
        enhanced=prompt_enhancement.enhanced,
        components=prompt_enhancement.components,
        target_mode=prompt_enhancement.target_mode,
        target_model=prompt_enhancement.target_model,
        llm_model=prompt_enhancement.llm_model,
        template_version=PROMPT_ENHANCEMENT_TEMPLATE_VERSION,
        creativity_preset=outcome.creativity_preset,
        temperature=outcome.temperature,
        latency_ms=prompt_enhancement.latency_ms,
        tokens_in=prompt_enhancement.tokens_in,
        tokens_out=prompt_enhancement.tokens_out,
        created_at=prompt_enhancement.created_at,
    )


def _status_code_for_vertex_error(exc: VertexServiceError) -> int:
    if exc.retryable:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_502_BAD_GATEWAY


def _status_code_for_prompt_credit_error(exc: prompt_credit.PromptCreditError) -> int:
    return {
        "monthly_credit_exhausted": status.HTTP_402_PAYMENT_REQUIRED,
        "plan_feature_not_allowed": status.HTTP_403_FORBIDDEN,
        "credit_idempotency_conflict": status.HTTP_409_CONFLICT,
        "prompt_enhancement_in_progress": status.HTTP_409_CONFLICT,
        "prompt_enhancement_terminal": status.HTTP_409_CONFLICT,
        "credit_busy": status.HTTP_503_SERVICE_UNAVAILABLE,
        "credit_account_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    }.get(exc.code, status.HTTP_503_SERVICE_UNAVAILABLE)


def _message_for_prompt_credit_error(exc: prompt_credit.PromptCreditError) -> str:
    return {
        "monthly_credit_exhausted": "Monthly credits are exhausted.",
        "plan_feature_not_allowed": "The current plan does not allow this operation.",
        "credit_idempotency_conflict": "The request identity conflicts with prior input.",
        "prompt_enhancement_in_progress": "Prompt enhancement is already in progress.",
        "prompt_enhancement_terminal": "Prompt enhancement already ended without a result.",
        "credit_busy": "Credit accounting is busy; retry later.",
        "credit_account_unavailable": "Credit accounting is unavailable.",
    }.get(exc.code, "Credit accounting is unavailable.")
