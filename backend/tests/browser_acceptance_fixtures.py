"""Strict, test-only fixtures for the owned browser acceptance database."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from uuid import NAMESPACE_URL, uuid5

from app.schema_revision import CODE_REVISION as EXPECTED_REVISION

PROJECT_PATTERN = re.compile(r"ownership-verify-[0-9a-f]{12}")
RECOVERY_CASES = ("a", "master")


def expected_user_id(case: str):
    if case not in RECOVERY_CASES:
        raise ValueError("recovery_case_refused")
    return uuid5(NAMESPACE_URL, "ownership-fixture/" + case)


def validate_payload(payload: object, *, database_host: str | None,
                     database_name: str | None, provider: str, app_env: str) -> dict[str, str]:
    if not isinstance(payload, dict) or set(payload) != {"project", "hashes"}:
        raise ValueError("recovery_input_refused")
    project = payload["project"]
    hashes = payload["hashes"]
    if (not isinstance(project, str) or PROJECT_PATTERN.fullmatch(project) is None
            or database_host != "db" or database_name != project.replace("-", "_")
            or provider != "mock" or app_env != "local"
            or not isinstance(hashes, dict) or set(hashes) != set(RECOVERY_CASES)
            or len(set(hashes.values())) != len(RECOVERY_CASES)
            or any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in hashes.values())):
        raise ValueError("recovery_input_refused")
    return hashes


async def recover(payload: object) -> dict[str, int]:
    from sqlalchemy import func, select, text
    from sqlalchemy.engine import make_url

    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.identity_models import User, UserSession, UserStatus

    settings = get_settings()
    url = make_url(os.environ.get("DATABASE_URL", ""))
    hashes = validate_payload(
        payload,
        database_host=url.host,
        database_name=url.database,
        provider=settings.ai_provider,
        app_env=settings.app_env,
    )
    now = datetime.now(timezone.utc)
    ids = [expected_user_id(case) for case in RECOVERY_CASES]
    async with AsyncSessionLocal() as session:
        if await session.scalar(text("SELECT version_num FROM alembic_version")) != EXPECTED_REVISION:
            raise ValueError("recovery_revision_refused")
        users = list((await session.scalars(select(User).where(User.id.in_(ids)))).all())
        if len(users) != len(ids) or any(user.status != UserStatus.ACTIVE for user in users):
            raise ValueError("recovery_inventory_refused")
        existing = list((await session.scalars(
            select(UserSession).where(UserSession.user_id.in_(ids))
        )).all())
        if any(row.revoked_at is None for row in existing):
            raise ValueError("recovery_active_session_refused")
        old_hashes = {row.token_hash for row in existing}
        new_hashes = {bytes.fromhex(value) for value in hashes.values()}
        if old_hashes & new_hashes:
            raise ValueError("recovery_hash_reuse_refused")
        old_revoked = len(existing)
        for case in RECOVERY_CASES:
            session.add(UserSession(
                user_id=expected_user_id(case),
                token_hash=bytes.fromhex(hashes[case]),
                created_at=now,
                last_seen_at=now,
                absolute_expires_at=now + timedelta(days=7),
            ))
        await session.commit()
        active = await session.scalar(select(func.count()).select_from(UserSession).where(
            UserSession.user_id.in_(ids), UserSession.revoked_at.is_(None)
        ))
    return {"recovered": len(RECOVERY_CASES), "old_revoked": old_revoked, "active": int(active or 0)}


async def main() -> None:
    raw = sys.stdin.read(8193)
    if not raw or len(raw) > 8192:
        raise ValueError("recovery_input_refused")
    result = await recover(json.loads(raw))
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
