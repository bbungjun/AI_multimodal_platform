from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import Asset, AssetKind, GenerationMode, Job, JobState
from app.state_machine import TERMINAL_STATES, transition
from app.services import rate_limit, storage
from app.services.jobs import pipeline_link
from app.services.retry import with_retry
from app.services.vertex import imagen, veo
from app.services.vertex.errors import VertexServiceError, map_vertex_error


class JobHandlerError(RuntimeError):
    pass


class I2VSourceAssetNotFoundError(JobHandlerError):
    pass


class I2VSourceAssetNotImageError(JobHandlerError):
    pass


async def handle(job_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise JobHandlerError(f"Job {job_id} was not found.")

        if job.mode == GenerationMode.T2I:
            await handle_t2i(session, job)
            return
        if job.mode == GenerationMode.T2V:
            await handle_t2v(session, job)
            return
        if job.mode == GenerationMode.I2V:
            await handle_i2v(session, job)
            return

        raise JobHandlerError(f"Unsupported generation mode: {job.mode!s}")


async def handle_t2i(session: AsyncSession, job: Job) -> None:
    if job.state in TERMINAL_STATES:
        return

    try:
        if job.state == JobState.PENDING:
            transition(job, JobState.QUEUED, detail={"runner": "direct-handler"})
            await session.commit()

        wait_seconds = await rate_limit.acquire(job.model)
        transition(
            job,
            JobState.GENERATING,
            detail={"rate_limit_wait_sec": wait_seconds},
        )
        await session.commit()

        params = job.parameters or {}
        number_of_images = int(params.get("number_of_images", 1))
        aspect_ratio = str(params.get("aspect_ratio", "1:1"))

        image_bytes = await with_retry(
            lambda: _attempt_imagen_generation(
                session,
                job,
                number_of_images=number_of_images,
                aspect_ratio=aspect_ratio,
            )
        )

        job.vertex_charged = True
        transition(
            job,
            JobState.DOWNLOADING,
            detail={"image_count": len(image_bytes)},
        )
        await session.commit()

        for index, data in enumerate(image_bytes):
            filename = "output.png" if index == 0 else f"output-{index + 1}.png"
            local_path = storage.save_bytes(job.id, filename, data)
            session.add(
                Asset(
                    job_id=job.id,
                    kind=AssetKind.IMAGE,
                    local_path=local_path,
                    mime="image/png",
                    size_bytes=len(data),
                )
            )

        transition(job, JobState.COMPLETED)
        await session.commit()
        await pipeline_link.link_completed_parent(session, job)
    except Exception as exc:
        await session.rollback()
        refreshed = await session.get(Job, job.id)
        if refreshed is not None:
            job = refreshed
        await _mark_failed(session, job, exc)
        if job.state == JobState.FAILED:
            await pipeline_link.fail_blocked_children_for_parent(session, job)


async def _attempt_imagen_generation(
    session: AsyncSession,
    job: Job,
    *,
    number_of_images: int,
    aspect_ratio: str,
) -> list[bytes]:
    job.attempts += 1
    await session.commit()
    return await imagen.generate_image(
        job.model,
        job.prompt,
        number_of_images=number_of_images,
        aspect_ratio=aspect_ratio,
    )


async def _attempt_veo_submit(
    session: AsyncSession,
    job: Job,
    *,
    aspect_ratio: str,
    duration_sec: int,
) -> object:
    job.attempts += 1
    await session.commit()
    return await veo.submit_video(
        job.model,
        job.prompt,
        aspect_ratio=aspect_ratio,
        duration_sec=duration_sec,
    )


async def _attempt_veo_i2v_submit(
    session: AsyncSession,
    job: Job,
    *,
    aspect_ratio: str,
    duration_sec: int,
    image_bytes: bytes,
    image_mime: str,
) -> object:
    job.attempts += 1
    await session.commit()
    return await veo.submit_video(
        job.model,
        job.prompt,
        aspect_ratio=aspect_ratio,
        duration_sec=duration_sec,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )


async def _mark_failed(session: AsyncSession, job: Job, exc: Exception) -> None:
    if job.state in TERMINAL_STATES:
        return

    now = datetime.now(timezone.utc)
    error = _public_error(exc, retry_count=job.attempts, at=now)
    job.error = error
    transition(job, JobState.FAILED, detail={"error": error["code"]}, at=now)
    await session.commit()


def _public_error(
    exc: Exception,
    *,
    retry_count: int,
    at: datetime,
) -> dict[str, object]:
    if isinstance(exc, I2VSourceAssetNotFoundError):
        return {
            "code": "i2v_source_asset_not_found",
            "message": "I2V source asset was not found.",
            "retryable": False,
            "retry_count": retry_count,
            "last_attempt_at": at.isoformat(),
        }

    if isinstance(exc, I2VSourceAssetNotImageError):
        return {
            "code": "i2v_source_asset_not_image",
            "message": "I2V source asset must be an image.",
            "retryable": False,
            "retry_count": retry_count,
            "last_attempt_at": at.isoformat(),
        }

    if isinstance(exc, veo.VeoTimeoutError):
        return {
            "code": "veo_timeout",
            "message": "Veo generation timed out while polling.",
            "retryable": True,
            "operation_name": exc.operation_name,
            "retry_count": retry_count,
            "last_attempt_at": at.isoformat(),
        }

    if isinstance(exc, VertexServiceError):
        public = exc.to_public_dict()
        error: dict[str, object] = {
            "code": public["code"],
            "message": public["message"],
            "retryable": public["retryable"],
            "retry_count": retry_count,
            "last_attempt_at": at.isoformat(),
        }
        if public["status_code"] is not None:
            error["status_code"] = public["status_code"]
        return error

    return {
        "code": _exception_code(exc),
        "message": str(exc) or exc.__class__.__name__,
        "retry_count": retry_count,
        "last_attempt_at": at.isoformat(),
    }


def _exception_code(exc: Exception) -> str:
    name = exc.__class__.__name__
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()


async def handle_t2v(session: AsyncSession, job: Job) -> None:
    if job.state in TERMINAL_STATES:
        return

    try:
        params = job.parameters or {}
        aspect_ratio = str(params.get("aspect_ratio", "16:9"))
        duration_sec = int(params.get("duration_sec", 4))

        if job.state == JobState.POLLING and job.vertex_operation_name:
            try:
                video_bytes = await veo.poll_operation_name(job.vertex_operation_name)
            except veo.VeoTimeoutError:
                raise
            except VertexServiceError:
                raise
            except Exception as exc:
                raise map_vertex_error(exc) from exc

            job.vertex_charged = True
            transition(
                job,
                JobState.DOWNLOADING,
                detail={"size_bytes": len(video_bytes)},
            )
            await session.commit()

            local_path = storage.save_bytes(job.id, "output.mp4", video_bytes)
            session.add(
                Asset(
                    job_id=job.id,
                    kind=AssetKind.VIDEO,
                    local_path=local_path,
                    mime="video/mp4",
                    size_bytes=len(video_bytes),
                    duration_sec=float(duration_sec),
                )
            )

            transition(job, JobState.COMPLETED)
            await session.commit()
            return

        if job.state == JobState.PENDING:
            transition(job, JobState.QUEUED, detail={"runner": "direct-handler"})
            await session.commit()

        wait_seconds = await rate_limit.acquire(job.model)
        transition(
            job,
            JobState.GENERATING,
            detail={"rate_limit_wait_sec": wait_seconds},
        )
        await session.commit()

        try:
            operation = await with_retry(
                lambda: _attempt_veo_submit(
                    session,
                    job,
                    aspect_ratio=aspect_ratio,
                    duration_sec=duration_sec,
                )
            )
        except VertexServiceError:
            raise
        except Exception as exc:
            raise map_vertex_error(exc) from exc

        operation_name = str(getattr(operation, "name", ""))
        job.vertex_operation_name = operation_name
        transition(
            job,
            JobState.POLLING,
            detail={"operation_name": operation_name},
        )
        await session.commit()

        try:
            video_bytes = await veo.poll_operation(operation)
        except veo.VeoTimeoutError:
            raise
        except VertexServiceError:
            raise
        except Exception as exc:
            raise map_vertex_error(exc) from exc

        job.vertex_charged = True
        transition(
            job,
            JobState.DOWNLOADING,
            detail={"size_bytes": len(video_bytes)},
        )
        await session.commit()

        local_path = storage.save_bytes(job.id, "output.mp4", video_bytes)
        session.add(
            Asset(
                job_id=job.id,
                kind=AssetKind.VIDEO,
                local_path=local_path,
                mime="video/mp4",
                size_bytes=len(video_bytes),
                duration_sec=float(duration_sec),
            )
        )

        transition(job, JobState.COMPLETED)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        refreshed = await session.get(Job, job.id)
        if refreshed is not None:
            job = refreshed
        await _mark_failed(session, job, exc)


async def handle_i2v(session: AsyncSession, job: Job) -> None:
    if job.state in TERMINAL_STATES:
        return

    try:
        params = job.parameters or {}
        aspect_ratio = str(params.get("aspect_ratio", "16:9"))
        duration_sec = int(params.get("duration_sec", 4))

        if job.state == JobState.POLLING and job.vertex_operation_name:
            try:
                video_bytes = await veo.poll_operation_name(job.vertex_operation_name)
            except veo.VeoTimeoutError:
                raise
            except VertexServiceError:
                raise
            except Exception as exc:
                raise map_vertex_error(exc) from exc

            job.vertex_charged = True
            transition(
                job,
                JobState.DOWNLOADING,
                detail={"size_bytes": len(video_bytes)},
            )
            await session.commit()

            local_path = storage.save_bytes(job.id, "output.mp4", video_bytes)
            session.add(
                Asset(
                    job_id=job.id,
                    kind=AssetKind.VIDEO,
                    local_path=local_path,
                    mime="video/mp4",
                    size_bytes=len(video_bytes),
                    duration_sec=float(duration_sec),
                )
            )

            transition(job, JobState.COMPLETED)
            await session.commit()
            return

        if job.state == JobState.PENDING:
            transition(job, JobState.QUEUED, detail={"runner": "direct-handler"})
            await session.commit()

        wait_seconds = await rate_limit.acquire(job.model)
        transition(
            job,
            JobState.GENERATING,
            detail={"rate_limit_wait_sec": wait_seconds},
        )
        await session.commit()

        if job.source_asset_id is None:
            raise JobHandlerError("I2V source asset is required.")
        source_asset = await session.get(Asset, job.source_asset_id)
        if source_asset is None:
            raise I2VSourceAssetNotFoundError("I2V source asset was not found.")
        if source_asset.kind != AssetKind.IMAGE:
            raise I2VSourceAssetNotImageError("I2V source asset must be an image.")

        source_bytes = storage.read_bytes(source_asset.local_path)
        try:
            operation = await with_retry(
                lambda: _attempt_veo_i2v_submit(
                    session,
                    job,
                    aspect_ratio=aspect_ratio,
                    duration_sec=duration_sec,
                    image_bytes=source_bytes,
                    image_mime=source_asset.mime,
                )
            )
        except VertexServiceError:
            raise
        except Exception as exc:
            raise map_vertex_error(exc) from exc

        operation_name = str(getattr(operation, "name", ""))
        job.vertex_operation_name = operation_name
        transition(
            job,
            JobState.POLLING,
            detail={"operation_name": operation_name},
        )
        await session.commit()

        try:
            video_bytes = await veo.poll_operation(operation)
        except veo.VeoTimeoutError:
            raise
        except VertexServiceError:
            raise
        except Exception as exc:
            raise map_vertex_error(exc) from exc

        job.vertex_charged = True
        transition(
            job,
            JobState.DOWNLOADING,
            detail={"size_bytes": len(video_bytes)},
        )
        await session.commit()

        local_path = storage.save_bytes(job.id, "output.mp4", video_bytes)
        session.add(
            Asset(
                job_id=job.id,
                kind=AssetKind.VIDEO,
                local_path=local_path,
                mime="video/mp4",
                size_bytes=len(video_bytes),
                duration_sec=float(duration_sec),
            )
        )

        transition(job, JobState.COMPLETED)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        refreshed = await session.get(Job, job.id)
        if refreshed is not None:
            job = refreshed
        await _mark_failed(session, job, exc)
