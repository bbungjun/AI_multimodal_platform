"""Read-only, count-only DB probe for the owned prompt/T2I Agent QA runtime."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.credit_models import CreditReservation
from app.db import AsyncSessionLocal
from app.generation_credit import CREDIT_PARAMETER_KEY
from app.models import Asset, GenerationMode, Job, JobState, OutboxEvent


PROJECT = re.compile(r"^ownership-verify-[0-9a-f]{12}$")


def validate_request(payload, *, database_url: str, provider: str, app_env: str) -> tuple[str, UUID | None]:
    if type(payload) is not dict or payload.get("operation") not in {"counts", "job", "latest_image_source"}:
        raise ValueError("prompt_t2i_probe_refused")
    required = {"operation"} if payload["operation"] in {"counts", "latest_image_source"} else {"operation", "job_id"}
    if set(payload) != required:
        raise ValueError("prompt_t2i_probe_refused")
    url = make_url(database_url)
    database = url.database or ""
    project = database.replace("_", "-")
    if (not PROJECT.fullmatch(project) or url.host != "db" or provider != "mock"
            or app_env != "test"):
        raise ValueError("prompt_t2i_probe_target_refused")
    try:
        job_id = UUID(payload["job_id"]) if payload["operation"] == "job" else None
    except (ValueError, TypeError, AttributeError):
        raise ValueError("prompt_t2i_probe_refused") from None
    return payload["operation"], job_id


async def inspect(payload) -> dict:
    settings = get_settings()
    operation, job_id = validate_request(
        payload,
        database_url=settings.database_url,
        provider=settings.ai_provider,
        app_env=settings.app_env,
    )
    async with AsyncSessionLocal() as session:
        if operation == "counts":
            return {
                "jobs": await session.scalar(select(func.count()).select_from(Job)),
                "outbox": await session.scalar(select(func.count()).select_from(OutboxEvent)),
                "reservations": await session.scalar(select(func.count()).select_from(CreditReservation)),
            }
        if operation == "latest_image_source":
            row = (await session.execute(
                select(Job.id, Asset.id).join(Asset, Asset.job_id == Job.id).where(
                    Job.mode == GenerationMode.T2I, Job.state == JobState.COMPLETED,
                    Asset.mime == "image/png").order_by(Job.created_at.desc(), Asset.id).limit(1)
            )).first()
            if row is None:
                raise ValueError("prompt_t2i_probe_source_missing")
            return {"job_id": str(row[0]), "asset_id": str(row[1])}
        job = await session.get(Job, job_id)
        if job is None:
            raise ValueError("prompt_t2i_probe_job_missing")
        try:
            reservation_id = UUID((job.parameters or {})[CREDIT_PARAMETER_KEY]["reservation_id"])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError("prompt_t2i_probe_reservation_missing") from None
        return {
            "state": job.state.value,
            "assets": await session.scalar(select(func.count()).select_from(Asset).where(Asset.job_id == job.id)),
            "png_assets": await session.scalar(select(func.count()).select_from(Asset).where(
                Asset.job_id == job.id, Asset.mime == "image/png")),
            "outbox": await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.aggregate_id == job.id)),
            "reservations": await session.scalar(select(func.count()).select_from(CreditReservation).where(
                CreditReservation.id == reservation_id)),
        }


def main() -> int:
    try:
        raw = sys.stdin.read(2049)
        if len(raw) > 2048:
            raise ValueError("prompt_t2i_probe_refused")
        result = asyncio.run(inspect(json.loads(raw)))
        if (type(result) is not dict or not result
                or any(type(value) not in {int, str} for value in result.values())):
            raise ValueError("prompt_t2i_probe_result_invalid")
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) and re.fullmatch(
            r"prompt_t2i_probe_[a-z_]+", str(error)) else "prompt_t2i_probe_failed"
        print(json.dumps({"complete": False, "error": code}, separators=(",", ":")))
        return 1
    print(json.dumps({"complete": True, **result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
