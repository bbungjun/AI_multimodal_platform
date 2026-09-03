"""Content access and reference integrity. Callers retain transaction ownership."""
from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    def _intent(self, actual: str, expected: str | tuple[str, ...]) -> None:
        if actual not in ((expected,) if isinstance(expected, str) else expected):
            raise ValueError("unsupported_ownership_intent")

    def _check_owner(self, owner: UUID | None, *, intent: str = "use") -> None:
        if owner is None or (owner != self.actor.id and not self._master_read(intent)):
            raise _not_found()

    def _master_read(self, intent: str) -> bool:
        return intent == "read" and self.actor.role == "master"

    def jobs_statement(self, scope: str = "mine"):
        if scope not in ("mine", "all"):
            raise HTTPException(status_code=422, detail="invalid_scope")
        if scope == "all" and self.actor.role != "master":
            raise HTTPException(status_code=403, detail="scope_forbidden")
        statement = select(Job).options(selectinload(Job.assets))
        return statement if scope == "all" else statement.where(Job.owner_user_id == self.actor.id)

    async def job(self, job_id: UUID, *, intent: Literal["read", "mutate"], lock: bool = False) -> Job:
        self._intent(intent, ("read", "mutate"))
        statement = select(Job).where(Job.id == job_id)
        if not self._master_read(intent):
            statement = statement.where(Job.owner_user_id == self.actor.id)
        if intent == "read":
            statement = statement.options(selectinload(Job.assets))
        if lock:
            statement = statement.with_for_update(of=Job).execution_options(populate_existing=True)
        row = (await self.session.scalars(statement)).first()
        if row is None or row.id != job_id:
            raise _not_found()
        self._check_owner(row.owner_user_id, intent=intent)
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

    async def asset(self, asset_id: UUID, *, intent: Literal["read", "use"], lock: bool = False) -> Asset:
        self._intent(intent, ("read", "use"))
        statement = select(Asset, Job.owner_user_id).join(Job, Asset.job_id == Job.id).where(
            Asset.id == asset_id,
        )
        if not self._master_read(intent):
            statement = statement.where(Job.owner_user_id == self.actor.id)
        if lock:
            statement = statement.with_for_update(of=Asset).execution_options(populate_existing=True)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            raise _not_found()
        asset, owner = row
        if asset.id != asset_id:
            raise _not_found()
        self._check_owner(owner, intent=intent)
        return asset

    async def file_asset(self, local_path: str) -> Asset:
        """An exact registered path, never a filesystem/prefix ownership fallback."""
        parts = local_path.split("/")
        if (len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", parts[0])
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", parts[1])):
            raise _not_found()
        statement = select(Asset, Job.owner_user_id).join(Job, Asset.job_id == Job.id).where(
            Asset.local_path == local_path,
        )
        if not self._master_read("read"):
            statement = statement.where(Job.owner_user_id == self.actor.id)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            raise _not_found()
        asset, owner = row
        if asset.local_path != local_path or str(asset.job_id) != parts[0]:
            raise _not_found()
        self._check_owner(owner, intent="read")
        return asset

    async def validate_read_jobs(self, jobs: list[Job]) -> None:
        """Validate only returned rows and known direct links, in at most3 queries."""
        for job in jobs:
            self._check_owner(job.owner_user_id, intent="read")
            if any(asset.job_id != job.id for asset in job.assets):
                raise _not_found()
        job_refs = {ref for job in jobs for ref in (job.parent_job_id, job.retry_of_job_id) if ref is not None}
        enhancement_refs = {job.enhancement_id for job in jobs if job.enhancement_id is not None}
        source_refs = {job.source_asset_id for job in jobs if job.source_asset_id is not None}
        owners = {}
        for model, refs in ((Job, job_refs), (PromptEnhancement, enhancement_refs)):
            if refs:
                rows = (await self.session.execute(select(model.id, model.owner_user_id).where(model.id.in_(refs)))).all()
                owners[model] = dict(rows)
            else:
                owners[model] = {}
        sources = {}
        if source_refs:
            sources = dict((await self.session.execute(
                select(Asset.id, Job.owner_user_id).join(Job, Asset.job_id == Job.id).where(Asset.id.in_(source_refs))
            )).all())
        for job in jobs:
            for ref, mapping in ((job.parent_job_id, owners[Job]), (job.retry_of_job_id, owners[Job]),
                                 (job.enhancement_id, owners[PromptEnhancement]), (job.source_asset_id, sources)):
                if ref is not None and mapping.get(ref) != job.owner_user_id:
                    raise _not_found()
