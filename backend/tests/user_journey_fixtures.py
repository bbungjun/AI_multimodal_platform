"""Owned local load fixtures and aggregate evidence; no raw Session input/output."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import traceback
from uuid import NAMESPACE_URL, uuid5


def validate(payload, host, database, provider, app_env):
    if (not isinstance(payload, dict) or set(payload) != {"project", "operation", "hashes"}
            or not isinstance(payload["project"], str)
            or re.fullmatch(r"ownership-verify-[0-9a-f]{12}", payload["project"]) is None
            or host != "db" or database != payload["project"].replace("-", "_")
            or provider != "mock" or app_env != "local"
            or payload["operation"] not in {"seed", "snapshot", "audit"}
            or not isinstance(payload["hashes"], list)):
        raise ValueError("load_target_refused")
    hashes = payload["hashes"]
    if payload["operation"] == "seed":
        if (len(hashes) != 64 or len(set(hashes)) != 64
                or any(not isinstance(h, str) or re.fullmatch(r"[0-9a-f]{64}", h) is None for h in hashes)):
            raise ValueError("load_hashes_refused")
    elif hashes:
        raise ValueError("load_hashes_refused")


async def execute(payload):
    from sqlalchemy import func, select, text
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.db import AsyncSessionLocal, engine
    from app.identity_models import User, UserSession
    from app.models import Job, Asset, OutboxEvent
    from app.credit_models import CreditReservation, CreditGrant, CreditUsageRecord
    from app.credit_lifecycle import change_plan
    from app.credit_accounting import _ledger_coherent
    from app.schema_revision import CODE_REVISION

    settings = get_settings()
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate(payload, url.host, url.database, settings.ai_provider, settings.app_env)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        if await session.scalar(text("SELECT version_num FROM alembic_version")) != CODE_REVISION:
            raise ValueError("load_revision_refused")
        if payload["operation"] == "seed":
            if await session.scalar(select(func.count()).select_from(Job)):
                raise ValueError("load_nonempty_refused")
            for index, digest in enumerate(payload["hashes"]):
                user_id = uuid5(NAMESPACE_URL, "load-fixture/" + str(index))
                if await session.get(User, user_id):
                    raise ValueError("load_reseed_refused")
                session.add(User(id=user_id, google_sub=f"load-fixture-{index}",
                    email=f"load-{index}@example.invalid", email_verified=True, role="user",
                    status="active", data_origin="oauth", signed_up_at=now, updated_at=now))
                await session.flush()
                session.add(UserSession(user_id=user_id, token_hash=bytes.fromhex(digest),
                    created_at=now, last_seen_at=now, absolute_expires_at=now + timedelta(days=7)))
                await change_plan(session, user_id=user_id, target_plan="max",
                    operation_key=f"load_plan_{index}", now=now)
            await session.commit()
            result = {"seeded": 64}
        else:
            async def grouped(model, column):
                rows = await session.execute(select(column, func.count()).select_from(model).group_by(column))
                return {str(getattr(key, "value", key)): count for key, count in rows}
            result = {"jobs": await grouped(Job, Job.state),
                      "outbox": await grouped(OutboxEvent, OutboxEvent.status),
                      "reservations": await grouped(CreditReservation, CreditReservation.status),
                      "assets": await grouped(Asset, Asset.kind),
                      "connections": int(await session.scalar(text(
                          "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"))),
                      "max_connections": int(await session.scalar(text("SHOW max_connections"))),
                      "deadlocks": int(await session.scalar(text(
                          "SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()"))),
                      "held_microcredits": int(await session.scalar(select(func.coalesce(
                          func.sum(CreditGrant.reserved_microcredits), 0))))}
            if payload["operation"] == "audit":
                users = list((await session.scalars(select(User.id))).all())
                for user_id in users:
                    grants = list((await session.scalars(select(CreditGrant).where(
                        CreditGrant.user_id == user_id))).all())
                    await _ledger_coherent(session, user_id, grants)
                    charged = await session.scalar(select(func.coalesce(func.sum(
                        CreditUsageRecord.charged_microcredits), 0)).where(CreditUsageRecord.user_id == user_id))
                    if charged != sum(g.consumed_microcredits for g in grants):
                        raise ValueError("load_charge_mismatch")
                units = dict((await session.execute(select(CreditUsageRecord.meter,
                    func.sum(CreditUsageRecord.actual_units)).group_by(CreditUsageRecord.meter))).all())
                image_units = sum(v for k, v in units.items() if k.startswith("imagen_"))
                video_units = sum(v for k, v in units.items() if k.startswith("veo_"))
                duration = await session.scalar(select(func.coalesce(func.sum(Asset.duration_sec), 0)))
                if (image_units != result["assets"].get("image", 0)
                        or video_units != round(float(duration) * 1000)):
                    raise ValueError("load_asset_usage_mismatch")
                duplicate_assets = await session.scalar(text(
                    "SELECT count(*) FROM (SELECT job_id FROM assets GROUP BY job_id HAVING count(*) > 1) a"))
                result.update(ledger_consistent=True, asset_usage_consistent=True,
                              duplicate_asset_jobs=int(duplicate_assets),
                              image_units=int(image_units), video_ms=int(video_units))
    await engine.dispose()
    return result


if __name__ == "__main__":
    try:
        raw = sys.stdin.read(16385)
        if len(raw) > 16384:
            raise ValueError("load_input_refused")
        print(json.dumps(asyncio.run(execute(json.loads(raw)))))
    except Exception as error:
        frames = traceback.extract_tb(error.__traceback__)
        own = [f for f in frames if f.filename.endswith('user_journey_fixtures.py')]
        code = getattr(error, "code", "unknown")
        if not isinstance(code, str) or re.fullmatch(r"[a-z_]{1,64}", code) is None:
            code = "unknown"
        print(json.dumps({"error": "load_fixture_failed", "kind": type(error).__name__,
                          "line": own[-1].lineno if own else 0, "code": code}))
