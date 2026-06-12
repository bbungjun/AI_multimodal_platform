from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.generations import get_session
from app.schemas import OpsHealthResponse
from app.services.ops.metrics import collect_ops_health


router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/health", response_model=OpsHealthResponse)
async def ops_health(session: AsyncSession = Depends(get_session)) -> OpsHealthResponse:
    return await collect_ops_health(session)
