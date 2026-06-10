from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models import Asset, AssetKind, GenerationMode, Job, JobState, PromptEnhancement, utc_now
from app.schemas import GenerationCreate, GenerationResponse, job_response_from_job
from app.services import storage
from app.services.jobs.outbox import add_job_dispatch_event
from app.services.rate_limit import DEFAULT_MODEL_LIMITS
from app.state_machine import TERMINAL_STATES


router = APIRouter(prefix="/api/generations", tags=["generations"])


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@router.post(
    "",
    response_model=GenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_generation(
    payload: GenerationCreate = Body(...),
    session: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    if payload.auto_enhance:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Automatic prompt enhancement is not implemented for generation requests.",
        )

    if payload.mode == "t2i":
        _validate_model(payload.model, prefix="imagen-", detail="Unsupported Imagen model.")
        generation_mode = GenerationMode.T2I
        parent_job_id = None
        source_asset_id = None
        parameters = {
            "aspect_ratio": payload.aspect_ratio,
            "number_of_images": payload.number_of_images,
        }
    elif payload.mode == "t2v":
        _validate_model(payload.model, prefix="veo-", detail="Unsupported Veo model.")
        generation_mode = GenerationMode.T2V
        parent_job_id = None
        source_asset_id = None
        parameters = {
            "aspect_ratio": payload.aspect_ratio,
            "duration_sec": payload.duration_sec,
        }
    elif payload.mode == "i2v":
        _validate_model(payload.model, prefix="veo-", detail="Unsupported Veo model.")
        generation_mode = GenerationMode.I2V
        source_asset_id = payload.source_asset_id
        source_asset = await session.get(Asset, source_asset_id)
        if source_asset is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source asset was not found.",
            )
        if source_asset.kind != AssetKind.IMAGE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source asset must be an image.",
            )
        parent_job_id = source_asset.job_id
        parameters = {
            "aspect_ratio": payload.aspect_ratio,
            "duration_sec": payload.duration_sec,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Generation mode is not implemented.",
        )

    prompt_enhancement = await _get_matching_prompt_enhancement(
        session,
        enhancement_id=payload.enhancement_id,
        generation_mode=generation_mode,
        model=payload.model,
    )

    now = utc_now()
    job = Job(
        id=uuid4(),
        mode=generation_mode,
        model=payload.model,
        state=JobState.PENDING,
        prompt=payload.prompt,
        enhanced_prompt=(
            prompt_enhancement.enhanced if prompt_enhancement is not None else None
        ),
        enhancement_id=(
            prompt_enhancement.id if prompt_enhancement is not None else None
        ),
        parent_job_id=parent_job_id,
        source_asset_id=source_asset_id,
        blocked=False,
        attempts=0,
        parameters=parameters,
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    add_job_dispatch_event(session, job.id, reason="generation_created")
    await session.commit()
    return job_response_from_job(job, assets=[])


@router.get("", response_model=list[GenerationResponse])
async def list_generations(
    mode: GenerationMode | None = Query(default=None),
    asset_kind: AssetKind | None = Query(default=None),
    model: str | None = Query(default=None, min_length=1, max_length=128),
    state: JobState | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[GenerationResponse]:
    statement = select(Job).options(selectinload(Job.assets))
    if mode is not None:
        statement = statement.where(Job.mode == mode)
    if asset_kind is not None:
        statement = statement.where(Job.assets.any(Asset.kind == asset_kind))
    if model is not None:
        statement = statement.where(Job.model == model)
    if state is not None:
        statement = statement.where(Job.state == state)

    statement = statement.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    result = await session.scalars(statement)
    jobs = list(result.all())
    return [job_response_from_job(job, assets=list(job.assets)) for job in jobs]


@router.get("/{job_id}", response_model=GenerationResponse)
async def get_generation(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    job = await session.get(Job, job_id, options=[selectinload(Job.assets)])
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation job was not found.",
        )
    return job_response_from_job(job, assets=list(job.assets))


@router.post(
    "/{job_id}/retry",
    response_model=GenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_generation(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    source = await session.get(Job, job_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation job was not found.",
        )
    if source.state != JobState.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed generation jobs can be retried.",
        )

    source_asset_id = source.source_asset_id
    if source.mode == GenerationMode.I2V:
        if source_asset_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry source asset is no longer available.",
            )
        source_asset = await session.get(Asset, source_asset_id)
        if source_asset is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry source asset is no longer available.",
            )
        if source_asset.kind != AssetKind.IMAGE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry source asset must be an image.",
            )

    now = utc_now()
    retry = Job(
        id=uuid4(),
        mode=source.mode,
        model=source.model,
        state=JobState.PENDING,
        prompt=source.prompt,
        enhanced_prompt=source.enhanced_prompt,
        enhancement_id=source.enhancement_id,
        parent_job_id=source.parent_job_id,
        retry_of_job_id=source.id,
        source_asset_id=source_asset_id,
        blocked=False,
        vertex_operation_name=None,
        attempts=0,
        parameters=dict(source.parameters or {}),
        state_history=[],
        error=None,
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )
    session.add(retry)
    add_job_dispatch_event(session, retry.id, reason="generation_retry_created")
    await session.commit()
    return job_response_from_job(retry, assets=[])


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
async def delete_generation(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    job = await session.get(Job, job_id, options=[selectinload(Job.assets)])
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation job was not found.",
        )

    referencing_jobs = await _validate_job_deletable(session, job)

    try:
        for asset in job.assets:
            storage.delete_file(asset.local_path, missing_ok=True)
    except storage.StoragePathError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generation asset file path is unsafe; job was not deleted.",
        ) from exc

    _detach_deleted_job_references(job, referencing_jobs)
    await session.delete(job)
    await session.commit()


def _validate_model(model: str, *, prefix: str, detail: str) -> None:
    if model not in DEFAULT_MODEL_LIMITS or not model.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


async def _get_matching_prompt_enhancement(
    session: AsyncSession,
    *,
    enhancement_id: UUID | None,
    generation_mode: GenerationMode,
    model: str,
) -> PromptEnhancement | None:
    if enhancement_id is None:
        return None

    prompt_enhancement = await session.get(PromptEnhancement, enhancement_id)
    if prompt_enhancement is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt enhancement was not found.",
        )
    if (
        prompt_enhancement.target_mode != generation_mode
        or prompt_enhancement.target_model != model
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt enhancement target does not match generation request.",
        )
    return prompt_enhancement


async def _validate_job_deletable(session: AsyncSession, job: Job) -> list[Job]:
    if job.state not in TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only terminal jobs can be deleted from History.",
        )

    referencing_jobs = await _jobs_referencing_job(session, job)
    if any(reference.state not in TERMINAL_STATES for reference in referencing_jobs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Jobs with active dependent jobs cannot be deleted from History.",
        )
    return referencing_jobs


async def _jobs_referencing_job(session: AsyncSession, job: Job) -> list[Job]:
    references: dict[UUID, Job] = {}
    for reference in await _child_jobs(session, job.id):
        if reference.id != job.id:
            references[reference.id] = reference

    asset_ids = [asset.id for asset in job.assets]
    if asset_ids:
        for reference in await _jobs_using_assets(session, job.id, asset_ids):
            if reference.id != job.id:
                references[reference.id] = reference

    for reference in await _retry_jobs(session, job.id):
        if reference.id != job.id:
            references[reference.id] = reference

    return list(references.values())


async def _child_jobs(session: AsyncSession, job_id: UUID) -> list[Job]:
    result = await session.scalars(select(Job).where(Job.parent_job_id == job_id))
    return list(result.all())


async def _retry_jobs(session: AsyncSession, job_id: UUID) -> list[Job]:
    result = await session.scalars(select(Job).where(Job.retry_of_job_id == job_id))
    return list(result.all())


async def _jobs_using_assets(
    session: AsyncSession,
    job_id: UUID,
    asset_ids: list[UUID],
) -> list[Job]:
    statement = select(Job).where(
        Job.id != job_id,
        Job.source_asset_id.in_(asset_ids),
    )
    result = await session.scalars(statement)
    return list(result.all())


def _detach_deleted_job_references(job: Job, referencing_jobs: list[Job]) -> None:
    asset_ids = {asset.id for asset in job.assets}
    for reference in referencing_jobs:
        if reference.parent_job_id == job.id:
            reference.parent_job_id = None
        if reference.retry_of_job_id == job.id:
            reference.retry_of_job_id = None
        if reference.source_asset_id in asset_ids:
            reference.source_asset_id = None
