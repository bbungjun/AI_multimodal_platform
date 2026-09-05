"""Authenticated HTTP Adapter for bounded Master commands only."""
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth_dependencies import require_master
from app.api.generations import get_session
from app.master_admin import MasterCommand, MasterError, administer
from app.master_read import MasterReadError, read_master
from app.models import utc_now

router = APIRouter(prefix="/api/master", tags=["master"])


async def _read(view, request, actor, session):
    allowed = {"overview": {"days", "origin"}, "users": {"limit", "after", "origin", "status"},
               "audit": {"limit", "after"}}[view]
    params = dict(request.query_params)
    if set(params)-allowed or len(params) != len(request.query_params.multi_items()):
        raise HTTPException(422, detail="master_input_invalid")
    try:
        for key in {"days", "limit"} & params.keys():
            if not params[key].isascii() or not params[key].isdigit():
                raise ValueError()
            params[key] = int(params[key])
        if "after" in params:
            params["after"] = UUID(params["after"])
        return await read_master(session, actor_id=actor.id, view=view, now=utc_now(), **params)
    except MasterReadError as error:
        code = error.code if error.code in {"master_input_invalid", "master_required", "master_busy"} else "master_unavailable"
        raise HTTPException({"master_input_invalid": 422, "master_required": 403}.get(code, 503), detail=code) from None
    except (ValueError, OverflowError):
        raise HTTPException(422, detail="master_input_invalid") from None
    except SQLAlchemyError:
        raise HTTPException(503, detail="master_unavailable") from None


@router.get("/overview")
async def overview(request: Request, actor=Depends(require_master), session=Depends(get_session)):
    return await _read("overview", request, actor, session)


@router.get("/users")
async def users(request: Request, actor=Depends(require_master), session=Depends(get_session)):
    return await _read("users", request, actor, session)


@router.get("/audit")
async def audit(request: Request, actor=Depends(require_master), session=Depends(get_session)):
    return await _read("audit", request, actor, session)


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
