"""Owner-only admission queries. Callers retain transaction ownership."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthenticatedUser
from app.models import Asset, Job, PromptEnhancement


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="content_not_found")


def assert_same_owner(job: Job, related: Job | PromptEnhancement) -> None:
    owner = getattr(job, "owner_user_id", None)
    if owner is None or owner != getattr(related, "owner_user_id", None):
        raise _not_found()


class OwnershipAccess:
    def __init__(self, session: AsyncSession, actor: AuthenticatedUser):
        self.session = session
        self.actor = actor

    def _intent(self, actual: str, expected: str) -> None:
        if actual != expected:
            raise ValueError("unsupported_ownership_intent")

    def _check_owner(self, owner: UUID | None) -> None:
        if owner is None or owner != self.actor.id:
            raise _not_found()

    async def job(self, job_id: UUID, *, intent: Literal["mutate"], lock: bool = False) -> Job:
        self._intent(intent, "mutate")
        statement = select(Job).where(Job.id == job_id, Job.owner_user_id == self.actor.id)
        if lock:
            statement = statement.with_for_update(of=Job)
        row = (await self.session.scalars(statement)).first()
        if row is None:
            raise _not_found()
        self._check_owner(row.owner_user_id)
        return row

    async def enhancement(self, enhancement_id: UUID, *, intent: Literal["use"]) -> PromptEnhancement:
        self._intent(intent, "use")
        statement = select(PromptEnhancement).where(
            PromptEnhancement.id == enhancement_id,
            PromptEnhancement.owner_user_id == self.actor.id,
        )
        row = (await self.session.scalars(statement)).first()
        if row is None:
            raise _not_found()
        self._check_owner(row.owner_user_id)
        return row

    async def asset(self, asset_id: UUID, *, intent: Literal["use"], lock: bool = False) -> Asset:
        self._intent(intent, "use")
        statement = select(Asset, Job.owner_user_id).join(Job, Asset.job_id == Job.id).where(
            Asset.id == asset_id, Job.owner_user_id == self.actor.id,
        )
        if lock:
            statement = statement.with_for_update(of=Asset)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            raise _not_found()
        asset, owner = row
        self._check_owner(owner)
        return asset
