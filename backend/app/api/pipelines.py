from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.generations import get_session
from app.models import GenerationMode, Job, JobState, utc_now
from app.schemas import PipelineCreateRequest, PipelineResponse, job_response_from_job
from app.services.jobs.outbox import add_job_dispatch_event
from app.services.rate_limit import DEFAULT_MODEL_LIMITS


router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.post(
    "",
    response_model=PipelineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pipeline(
    payload: PipelineCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> PipelineResponse:
    _validate_pipeline_model(
        payload.image_model,
        prefix="imagen-",
        detail="Unsupported Imagen model.",
    )
    _validate_pipeline_model(
        payload.video_model,
        prefix="veo-",
        detail="Unsupported Veo model.",
    )

    now = utc_now()
    parent = Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model=payload.image_model,
        state=JobState.PENDING,
        prompt=payload.image_prompt,
        blocked=False,
        attempts=0,
        parameters={
            "aspect_ratio": payload.image_aspect_ratio,
            "number_of_images": 1,
        },
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )
    child = Job(
        id=uuid4(),
        mode=GenerationMode.I2V,
        model=payload.video_model,
        state=JobState.PENDING,
        prompt=payload.video_prompt,
        parent_job_id=parent.id,
        blocked=True,
        attempts=0,
        parameters={
            "aspect_ratio": payload.video_aspect_ratio,
            "duration_sec": payload.duration_sec,
        },
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )
    session.add_all([parent, child])
    add_job_dispatch_event(session, parent.id, reason="pipeline_parent_created")
    await session.commit()

    return PipelineResponse(
        id=parent.id,
        parent=job_response_from_job(parent, assets=[]),
        child=job_response_from_job(child, assets=[]),
    )


@router.get("/{parent_job_id}", response_model=PipelineResponse)
async def get_pipeline(
    parent_job_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PipelineResponse:
    parent = await session.get(Job, parent_job_id, options=[selectinload(Job.assets)])
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline parent job was not found.",
        )

    child = await _get_pipeline_child(session, parent_job_id)
    if child is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline child job was not found.",
        )

    return PipelineResponse(
        id=parent.id,
        parent=job_response_from_job(parent, assets=list(parent.assets)),
        child=job_response_from_job(child, assets=list(child.assets)),
    )


def _validate_pipeline_model(model: str, *, prefix: str, detail: str) -> None:
    if model not in DEFAULT_MODEL_LIMITS or not model.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


async def _get_pipeline_child(session: AsyncSession, parent_job_id: UUID) -> Job | None:
    statement = (
        select(Job)
        .options(selectinload(Job.assets))
        .where(
            Job.parent_job_id == parent_job_id,
            Job.mode == GenerationMode.I2V,
        )
        .order_by(Job.created_at, Job.id)
    )
    result = await session.scalars(statement)
    return result.first()
