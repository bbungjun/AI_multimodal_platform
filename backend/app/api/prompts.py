from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import PromptEnhancement
from app.prompt_enhancement import (
    PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY,
    PROMPT_ENHANCEMENT_TEMPLATE_VERSION,
)
from app.schemas import PromptEnhanceRequest, PromptEnhancementResponse
from app.services.llm import enhancer
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
) -> PromptEnhancementResponse:
    try:
        result = await enhancer.enhance_prompt(
            payload.prompt,
            target_mode=payload.target_mode,
            target_model=payload.target_model,
            creativity_preset=payload.creativity_preset,
        )
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

    components = dict(result.components)
    components[PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY] = {
        "creativity_preset": result.creativity_preset.value,
        "temperature": result.temperature,
        "template_version": PROMPT_ENHANCEMENT_TEMPLATE_VERSION,
    }
    prompt_enhancement = PromptEnhancement(
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
    session.add(prompt_enhancement)
    await session.commit()
    await session.refresh(prompt_enhancement)

    return PromptEnhancementResponse(
        id=prompt_enhancement.id,
        original=prompt_enhancement.original,
        enhanced=prompt_enhancement.enhanced,
        components=prompt_enhancement.components,
        target_mode=prompt_enhancement.target_mode,
        target_model=prompt_enhancement.target_model,
        llm_model=prompt_enhancement.llm_model,
        template_version=PROMPT_ENHANCEMENT_TEMPLATE_VERSION,
        creativity_preset=result.creativity_preset,
        temperature=result.temperature,
        latency_ms=prompt_enhancement.latency_ms,
        tokens_in=prompt_enhancement.tokens_in,
        tokens_out=prompt_enhancement.tokens_out,
        created_at=prompt_enhancement.created_at,
    )


def _status_code_for_vertex_error(exc: VertexServiceError) -> int:
    if exc.retryable:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_502_BAD_GATEWAY
