"""Owner-only admission queries. Callers retain transaction ownership."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthenticatedUser
from app.models import Asset, GenerationMode, Job, JobState, PromptEnhancement


class OwnershipReferenceMismatch(RuntimeError):
    code = "ownership_reference_mismatch"

    def __init__(self):
        super().__init__("Content ownership reference validation failed.")


async def validate_execution_references(session: AsyncSession, job: Job) -> Asset | None:
    """Check persisted relations without borrowing an HTTP actor or transaction."""
    owner = job.owner_user_id
    if owner is None:
        raise OwnershipReferenceMismatch()
    for model, reference in (
        (PromptEnhancement, job.enhancement_id),
        (Job, job.parent_job_id),
        (Job, job.retry_of_job_id),
    ):
        if reference is None:
            continue
        statement = select(model).where(model.id == reference, model.owner_user_id == owner)
        related = (await session.scalars(statement.execution_options(populate_existing=True))).first()
        if related is None or related.id != reference or related.owner_user_id != owner:
            raise OwnershipReferenceMismatch()
    if job.source_asset_id is None:
        if job.mode == GenerationMode.I2V and not (
            job.state == JobState.POLLING and job.vertex_operation_name
        ):
            raise OwnershipReferenceMismatch()
        return None
    statement = select(Asset, Job.owner_user_id).join(Job, Asset.job_id == Job.id).where(
        Asset.id == job.source_asset_id, Job.owner_user_id == owner,
    ).execution_options(populate_existing=True)
    result = (await session.execute(statement)).one_or_none()
    if result is None:
        raise OwnershipReferenceMismatch()
    asset, source_owner = result
    if asset.id != job.source_asset_id or source_owner != owner:
        raise OwnershipReferenceMismatch()
    return asset


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
