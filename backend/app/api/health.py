from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.db import check_db_connection
from app.schemas import HealthResponse, VertexReadinessResponse
from app.services.vertex.client import get_vertex_readiness


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, bool | str]:
    return {
        "ok": True,
        "service": get_settings().app_name,
    }


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_up = await check_db_connection()
    vertex = get_vertex_readiness()
    settings = get_settings()
    return HealthResponse(
        ok=db_up,
        ready=db_up and vertex.ready,
        service=settings.app_name,
        db="up" if db_up else "down",
        provider_retry_max_attempts=settings.provider_retry_max_attempts,
        vertex=VertexReadinessResponse(**vertex.to_public_dict()),
    )
