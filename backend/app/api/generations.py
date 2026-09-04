from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app import generation_credit
from app.api.auth_dependencies import require_user
from app.auth.service import AuthenticatedUser
from app.ownership import OwnershipAccess
from app.models import Asset, AssetKind, GenerationMode, Job, JobState, PromptEnhancement, utc_now
from app.prompt_enhancement import (
    PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY,
    PROMPT_PROVENANCE_PARAMETER_KEY,
    prompt_sha256,
)
from app.schemas import GenerationCreate, GenerationResponse, job_response_from_job
from app.services import storage
from app.services.jobs import i2v_guard
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
    actor: AuthenticatedUser = Depends(require_user),
) -> GenerationResponse:
    access = OwnershipAccess(session, actor)
    prompt_enhancement = (
        await access.enhancement(payload.enhancement_id, intent="use")
        if payload.enhancement_id is not None else None
    )
    source_asset = (
        await access.asset(payload.source_asset_id, intent="use", lock=True)
        if payload.mode == "i2v" else None
    )
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
        if source_asset.kind != AssetKind.IMAGE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source asset must be an image.",
            )
        active_result = await session.scalars(
            i2v_guard.active_i2v_job_statement(source_asset_id)
        )
        if active_result.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=i2v_guard.ACTIVE_I2V_DUPLICATE_MESSAGE,
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

    _validate_matching_prompt_enhancement(
        prompt_enhancement,
        generation_mode=generation_mode,
        model=payload.model,
    )
    parameters = _with_prompt_provenance(
        parameters,
        execution_prompt=payload.prompt,
        prompt_enhancement=prompt_enhancement,
    )

    now = utc_now()
    job = Job(
        id=uuid4(),
        owner_user_id=actor.id,
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
    try:
        await _admit_generation(session, job, now=now)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if (
            generation_mode == GenerationMode.I2V
            and _is_active_i2v_conflict(exc)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=i2v_guard.ACTIVE_I2V_DUPLICATE_MESSAGE,
            ) from None
        raise
    except Exception:
        await session.rollback()
        raise
    return job_response_from_job(job, assets=[])


@router.get("", response_model=list[GenerationResponse])
async def list_generations(
    mode: GenerationMode | None = Query(default=None),
    asset_kind: AssetKind | None = Query(default=None),
    model: str | None = Query(default=None, min_length=1, max_length=128),
    state: JobState | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    scope: str = Query(default="mine"),
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> list[GenerationResponse]:
    access = OwnershipAccess(session, actor)
    statement = access.jobs_statement(scope)
    if mode is not None:
        statement = statement.where(Job.mode == mode)
    if asset_kind is not None:
        statement = statement.where(Job.assets.any(Asset.kind == asset_kind))
    if model is not None:
        statement = statement.where(Job.model == model)
    if state is not None:
        statement = statement.where(Job.state == state)

    statement = statement.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit).offset(offset)
    result = await session.scalars(statement)
    jobs = list(result.all())
    await access.validate_read_jobs(jobs)
    return [job_response_from_job(job, assets=list(job.assets)) for job in jobs]


@router.get("/{job_id}", response_model=GenerationResponse)
async def get_generation(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> GenerationResponse:
    access = OwnershipAccess(session, actor)
    job = await access.job(job_id, intent="read")
    await access.validate_read_jobs([job])
    return job_response_from_job(job, assets=list(job.assets))


@router.post(
    "/{job_id}/retry",
    response_model=GenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_generation(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> GenerationResponse:
    access = OwnershipAccess(session, actor)
    source = await access.job(job_id, intent="mutate")
    if source.state != JobState.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed generation jobs can be retried.",
        )

    source_mode = source.mode
    source_asset_id = source.source_asset_id
    if source.enhancement_id is not None:
        await access.enhancement(source.enhancement_id, intent="use")
    if source.parent_job_id is not None:
        await access.job(source.parent_job_id, intent="mutate")
    source_asset = (
        await access.asset(source_asset_id, intent="use", lock=True)
        if source_asset_id is not None else None
    )
    if source.mode == GenerationMode.I2V:
        if source_asset_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry source asset is no longer available.",
            )
        if source_asset.kind != AssetKind.IMAGE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry source asset must be an image.",
            )
        active_result = await session.scalars(i2v_guard.active_i2v_job_statement(source_asset_id))
        if active_result.first() is not None:
            raise HTTPException(status_code=409, detail=i2v_guard.ACTIVE_I2V_DUPLICATE_MESSAGE)

    now = utc_now()
    retry = Job(
        id=uuid4(),
        owner_user_id=actor.id,
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
        parameters=generation_credit.strip_credit_metadata(source.parameters),
        state_history=[],
        error=None,
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )
    session.add(retry)
    add_job_dispatch_event(session, retry.id, reason="generation_retry_created")
    try:
        await _admit_generation(session, retry, now=now)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if source_mode == GenerationMode.I2V and _is_active_i2v_conflict(exc):
            raise HTTPException(status_code=409, detail=i2v_guard.ACTIVE_I2V_DUPLICATE_MESSAGE) from None
        raise
    except Exception:
        await session.rollback()
        raise
    return job_response_from_job(retry, assets=[])


async def _admit_generation(session: AsyncSession, job: Job, *, now,
                            pipeline_child: Job | None = None) -> None:
    try:
        await generation_credit.admit_generation(
            session, job=job, pipeline_child=pipeline_child, now=now)
    except generation_credit.GenerationCreditError as error:
        await session.rollback()
        status_code = {
            "monthly_credit_exhausted": status.HTTP_402_PAYMENT_REQUIRED,
            "credit_plan_refused": status.HTTP_403_FORBIDDEN,
            "credit_busy": status.HTTP_503_SERVICE_UNAVAILABLE,
            "credit_account_inconsistent": status.HTTP_503_SERVICE_UNAVAILABLE,
        }.get(error.code, status.HTTP_409_CONFLICT)
        detail = error.code
        raise HTTPException(status_code=status_code, detail=detail) from None


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
async def delete_generation(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> None:
    access = OwnershipAccess(session, actor)
    await access.job(job_id, intent="mutate")
    # Admission locks Asset before its parent Job FK; deletion must use that order.
    locked_assets = list((await session.scalars(
        select(Asset).where(Asset.job_id == job_id).order_by(Asset.id)
        .with_for_update(of=Asset).execution_options(populate_existing=True)
    )).all())
    job = await access.job(job_id, intent="mutate", lock=True)
    await session.refresh(job, attribute_names=["assets"])
    if (any(asset.job_id != job.id for asset in job.assets)
            or {asset.id for asset in job.assets} != {asset.id for asset in locked_assets}):
        raise HTTPException(status_code=409, detail="ownership_reference_mismatch")

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


def _is_active_i2v_conflict(exc: IntegrityError) -> bool:
    # SQLAlchemy's asyncpg adapter chains the original PG exception. Read its
    # structured fields: str(exc) also contains caller-controlled SQL parameters.
    original = exc.orig
    cause = getattr(original, "__cause__", None)
    diagnostic = getattr(original, "diag", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    constraint = (
        getattr(diagnostic, "constraint_name", None)
        or getattr(original, "constraint_name", None)
        or getattr(cause, "constraint_name", None)
    )
    return (
        sqlstate == "23505"
        and constraint == i2v_guard.ACTIVE_I2V_UNIQUE_INDEX_NAME
        and i2v_guard.is_active_i2v_unique_violation(exc)
    )


def _validate_model(model: str, *, prefix: str, detail: str) -> None:
    if model not in DEFAULT_MODEL_LIMITS or not model.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _with_prompt_provenance(
    parameters: dict[str, object],
    *,
    execution_prompt: str,
    prompt_enhancement: PromptEnhancement | None,
) -> dict[str, object]:
    if prompt_enhancement is None:
        return parameters

    provenance: dict[str, object] = {
        "source": "enhancement",
        "enhancement_id": str(prompt_enhancement.id),
        "llm_model": prompt_enhancement.llm_model,
        "target_mode": prompt_enhancement.target_mode.value,
        "target_model": prompt_enhancement.target_model,
        "original_prompt_sha256": prompt_sha256(prompt_enhancement.original),
        "enhanced_draft_sha256": prompt_sha256(prompt_enhancement.enhanced),
        "execution_prompt_sha256": prompt_sha256(execution_prompt),
        "edited_after_enhancement": execution_prompt != prompt_enhancement.enhanced,
    }
    metadata = (prompt_enhancement.components or {}).get(
        PROMPT_ENHANCEMENT_METADATA_COMPONENT_KEY
    )
    if isinstance(metadata, dict):
        for key in ("template_version", "creativity_preset", "temperature"):
            value = metadata.get(key)
            if isinstance(value, str | int | float):
                provenance[key] = value

    return {**parameters, PROMPT_PROVENANCE_PARAMETER_KEY: provenance}


def _validate_matching_prompt_enhancement(
    prompt_enhancement: PromptEnhancement | None,
    *,
    generation_mode: GenerationMode,
    model: str,
) -> PromptEnhancement | None:
    if prompt_enhancement is None:
        return None
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
    if any(reference.owner_user_id != job.owner_user_id for reference in referencing_jobs):
        raise HTTPException(status_code=409, detail="ownership_reference_mismatch")
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
    result = await session.scalars(select(Job).where(Job.parent_job_id == job_id).execution_options(populate_existing=True))
    return list(result.all())


async def _retry_jobs(session: AsyncSession, job_id: UUID) -> list[Job]:
    result = await session.scalars(select(Job).where(Job.retry_of_job_id == job_id).execution_options(populate_existing=True))
    return list(result.all())


async def _jobs_using_assets(
    session: AsyncSession,
    job_id: UUID,
    asset_ids: list[UUID],
) -> list[Job]:
    statement = select(Job).where(
        Job.id != job_id,
        Job.source_asset_id.in_(asset_ids),
    ).execution_options(populate_existing=True)
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
