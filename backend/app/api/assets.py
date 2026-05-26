from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.generations import get_session
from app.models import Asset
from app.schemas import AssetResponse


router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AssetResponse:
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset was not found.",
        )
    return AssetResponse.model_validate(asset)
