from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.generations import get_session
from app.api.auth_dependencies import require_user
from app.auth.service import AuthenticatedUser
from app.ownership import OwnershipAccess
from app.schemas import AssetResponse


router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> AssetResponse:
    asset = await OwnershipAccess(session, actor).asset(asset_id, intent="read")
    return AssetResponse.model_validate(asset)
