"""Authenticated HTTP Adapter for bounded Master commands only."""
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth_dependencies import require_master
from app.api.generations import get_session
from app.master_admin import MasterCommand, MasterError, administer
from app.models import utc_now

router = APIRouter(prefix="/api/master", tags=["master"])


class CommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    action: Literal["plan_change", "bonus_grant", "suspend", "reactivate"]
    reason_code: Literal["entitlement_change", "support_adjustment", "service_recovery",
                         "account_policy", "account_reactivated", "operator_bootstrap"]
    target_plan: Literal["free", "pro", "max"] | None = None
    amount_microcredits: StrictInt | None = Field(default=None, gt=0, le=9_000_000_000_000_000)
    expires_at: datetime | None = None


@router.post("/users/{target_id}/commands")
async def execute_command(target_id: UUID, body: CommandBody,
                          actor=Depends(require_master), session=Depends(get_session)):
    command = MasterCommand(target_id=target_id, **body.model_dump())
    try:
        async with session.begin():
            receipt = await administer(session, actor_id=actor.id, command=command, now=utc_now())
        return asdict(receipt)
    except MasterError as error:
        status = {"master_required": 403, "master_target_missing": 404, "master_conflict": 409,
                  "master_input_invalid": 422}.get(error.code, 503)
        code = error.code if error.code in {"master_required", "master_target_missing", "master_conflict",
            "master_input_invalid", "master_busy", "master_unavailable"} else "master_unavailable"
        raise HTTPException(status, detail=code) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail="master_unavailable") from None
