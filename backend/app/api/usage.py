"""Authenticated adapter for the coherent personal usage read model."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import require_user
from app.api.generations import get_session
from app.auth.service import AuthenticatedUser
from app.models import utc_now
from app.personal_usage import PersonalUsageError, read_personal_usage
from app.schemas import PersonalUsageResponse


router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/me", response_model=PersonalUsageResponse)
async def personal_usage_me(
    session: AsyncSession = Depends(get_session),
    actor: AuthenticatedUser = Depends(require_user),
) -> PersonalUsageResponse:
    try:
        async with session.begin():
            view = await read_personal_usage(session, user_id=actor.id, now=utc_now())
    except PersonalUsageError as error:
        code = error.code if error.code in {"usage_busy", "usage_unavailable"} else "usage_unavailable"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=code) from None
    return PersonalUsageResponse.model_validate(view)
