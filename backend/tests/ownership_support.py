"""Test-only hash fixtures. No product imports this module; no raw secrets enter it."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from uuid import NAMESPACE_URL, uuid5

CASES = ("a", "b", "master", "idle", "absolute", "revoked", "suspended", "synthetic", "logout")
EXPECTED_REVISION = "0002_user_session_persistence"


def validate_target(payload, url, provider, app_env):
    if (set(payload) != {"project", "hashes"}
            or not re.fullmatch(r"ownership-verify-[0-9a-f]{12}", payload["project"])
            or url.host != "db" or url.database != payload["project"].replace("-", "_")
            or provider != "mock" or app_env != "local"):
        raise ValueError("seed_target_refused")


def fixture_rows(hashes, now):
    if set(hashes) != set(CASES) or len(set(hashes.values())) != len(CASES):
        raise ValueError("invalid_fixture_hashes")
    if any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes.values()):
        raise ValueError("invalid_fixture_hashes")
    rows = []
    for case in CASES:
        created = now - timedelta(days=8) if case == "absolute" else now - timedelta(days=1)
        last_seen = created if case in ("idle", "absolute") else now
        rows.append(dict(case=case, user_id=uuid5(NAMESPACE_URL, "ownership-fixture/" + case),
                         role="master" if case == "master" else "user", created=created,
                         last_seen=last_seen, expires=created + timedelta(days=7), hash=bytes.fromhex(hashes[case])))
    return rows


async def seed(payload):
    # Verify inside the container as well as at the coordinator's Docker seam.
    from sqlalchemy import func, select, text
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.identity_models import User, UserSession
    from app.models import Job, Asset, PromptEnhancement, OutboxEvent

    settings = get_settings()
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(payload, url, settings.ai_provider, settings.app_env)
    now = datetime.now(timezone.utc)
    rows = fixture_rows(payload["hashes"], now)
    async with AsyncSessionLocal() as session:
        if await session.scalar(text("SELECT version_num FROM alembic_version")) != EXPECTED_REVISION:
            raise ValueError("seed_revision_refused")
        for model in (User, UserSession, Job, Asset, PromptEnhancement, OutboxEvent):
            if await session.scalar(select(func.count()).select_from(model)):
                raise ValueError("seed_nonempty_refused")
        for row in rows:
            case = row["case"]
            synthetic = case == "synthetic"
            session.add(User(id=row["user_id"], google_sub=None if synthetic else "fixture-" + case,
                             email=None if synthetic else case + "@example.invalid",
                             email_verified=not synthetic, role=row["role"],
                             status="suspended" if case == "suspended" else "active",
                             data_origin="synthetic" if synthetic else "oauth", signed_up_at=row["created"],
                             suspended_at=now if case == "suspended" else None, updated_at=now))
        await session.flush()
        for row in rows:
            session.add(UserSession(user_id=row["user_id"], token_hash=row["hash"],
                                   created_at=row["created"], last_seen_at=row["last_seen"],
                                   absolute_expires_at=row["expires"],
                                   revoked_at=now if row["case"] == "revoked" else None,
                                   revoke_reason="test_revoked" if row["case"] == "revoked" else None))
        await session.commit()


if __name__ == "__main__":
    try:
        asyncio.run(seed(json.loads(sys.stdin.read())))
    except Exception:
        print("seed_failed", file=sys.stderr)
        sys.exit(1)
    print("seeded")
