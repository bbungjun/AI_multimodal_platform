"""Test-only hash fixtures. No product imports this module; no raw secrets enter it."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from uuid import NAMESPACE_URL, uuid5

CASES = ("a", "b", "master", "idle", "absolute", "revoked", "suspended", "synthetic", "logout")
EXPECTED_REVISION = "0003_content_ownership"


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


ADMISSION_OPERATIONS = {"prepare", "counts", "assert_rows", "arm_commit_failure", "disarm_commit_failure", "clear"}


def validate_admission_target(payload, url, provider, app_env):
    if (set(payload) != {"project", "operation", "records"}
            or payload["operation"] not in ADMISSION_OPERATIONS
            or not isinstance(payload["records"], list) or len(payload["records"]) > 40):
        raise ValueError("admission_target_refused")
    validate_target({"project": payload["project"], "hashes": {}}, url, provider, app_env)
    if payload["operation"] != "assert_rows" and payload["records"]:
        raise ValueError("admission_records_refused")
    for record in payload["records"]:
        if (set(record) != {"case", "kind", "id", "retry"}
                or record["case"] not in {"a", "b", "master"}
                or record["kind"] not in {"job", "prompt", "pipeline"}
                or type(record["retry"]) is not bool):
            raise ValueError("admission_records_refused")
        from uuid import UUID
        UUID(record["id"])


def content_id(case, kind):
    return uuid5(NAMESPACE_URL, "ownership-content/" + case + "/" + kind)


async def admission(payload):
    from sqlalchemy import delete, func, select, text
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.identity_models import User
    from app.models import Job, Asset, PromptEnhancement, OutboxEvent, GenerationMode, JobState, AssetKind
    settings = get_settings()
    validate_admission_target(payload, make_url(os.environ.get("DATABASE_URL", "")),
                              settings.ai_provider, settings.app_env)
    async with AsyncSessionLocal() as session:
        if await session.scalar(text("SELECT version_num FROM alembic_version")) != EXPECTED_REVISION:
            raise ValueError("admission_revision_refused")
        users = set((await session.scalars(select(User.id))).all())
        if users != {uuid5(NAMESPACE_URL, "ownership-fixture/" + case) for case in CASES}:
            raise ValueError("admission_identity_inventory_refused")
        operation = payload["operation"]
        models = (Job, Asset, PromptEnhancement, OutboxEvent)
        async def counts():
            return {m.__tablename__: await session.scalar(select(func.count()).select_from(m)) for m in models}
        if operation == "counts":
            return await counts()
        if operation == "prepare":
            if any((await counts()).values()):
                raise ValueError("admission_nonempty_refused")
            for case in ("a", "b", "master"):
                owner = uuid5(NAMESPACE_URL, "ownership-fixture/" + case)
                enhancement = PromptEnhancement(id=content_id(case,"enhancement"), owner_user_id=owner,
                    original="fixture",enhanced="fixture",components={},target_mode=GenerationMode.T2I,
                    target_model="imagen-4.0-fast-generate-001",llm_model="mock")
                session.add(enhancement)
                await session.flush()
                parent = Job(id=content_id(case,"parent"), owner_user_id=owner, mode=GenerationMode.T2I,
                    model="imagen-4.0-fast-generate-001",state=JobState.COMPLETED,prompt="fixture")
                session.add(parent)
                await session.flush()
                session.add(Asset(id=content_id(case,"asset"),job_id=parent.id,kind=AssetKind.IMAGE,
                    local_path=f"fixture-{case}.png",mime="image/png",size_bytes=1))
                session.add(Job(id=content_id(case,"retry"),owner_user_id=owner,mode=GenerationMode.T2I,
                    model=parent.model,state=JobState.FAILED,prompt="fixture",attempts=1,
                    parent_job_id=parent.id,enhancement_id=enhancement.id))
            await session.commit()
            return {"prepared": True}
        if operation in {"arm_commit_failure", "disarm_commit_failure", "clear"}:
            await session.execute(text("DROP TRIGGER IF EXISTS ownership_test_abort ON outbox_events"))
            await session.execute(text("DROP FUNCTION IF EXISTS ownership_test_abort()"))
            if operation == "arm_commit_failure":
                await session.execute(text("""CREATE FUNCTION ownership_test_abort() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'ownership_test_commit_abort'; END $$"""))
                await session.execute(text("""CREATE TRIGGER ownership_test_abort BEFORE INSERT ON outbox_events
                    FOR EACH ROW EXECUTE FUNCTION ownership_test_abort()"""))
            if operation == "clear":
                for model in (OutboxEvent, Asset, Job, PromptEnhancement):
                    await session.execute(delete(model))
            await session.commit()
            return {"completed": True}
        checked = 0
        from uuid import UUID
        for record in payload["records"]:
            expected_owner = uuid5(NAMESPACE_URL, "ownership-fixture/" + record["case"])
            model = PromptEnhancement if record["kind"] == "prompt" else Job
            row = await session.get(model, UUID(record["id"]))
            if row is None or row.owner_user_id != expected_owner:
                raise ValueError("admission_owner_mismatch")
            if model is Job:
                events = await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                    OutboxEvent.aggregate_id == row.id))
                if events != 1:
                    raise ValueError("admission_outbox_mismatch")
                if record["retry"]:
                    source = await session.get(Job, content_id(record["case"],"retry"))
                    if (row.retry_of_job_id != source.id or row.id == source.id
                            or source.state != JobState.FAILED or source.attempts != 1
                            or row.parent_job_id != source.parent_job_id
                            or row.enhancement_id != source.enhancement_id):
                        raise ValueError("admission_retry_lineage_mismatch")
                if record["kind"] == "pipeline":
                    children = (await session.scalars(select(Job).where(Job.parent_job_id == row.id))).all()
                    if len(children) != 1 or children[0].owner_user_id != expected_owner or not children[0].blocked:
                        raise ValueError("admission_pipeline_mismatch")
                    if await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                            OutboxEvent.aggregate_id == children[0].id)):
                        raise ValueError("admission_child_outbox_mismatch")
            checked += 1
        return {"rows_checked": checked, "owners": True, "outbox": True, "lineage": True}


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read())
        if "operation" in payload:
            print(json.dumps(asyncio.run(admission(payload))))
        else:
            asyncio.run(seed(payload))
            print("seeded")
    except Exception:
        print("seed_failed", file=sys.stderr)
        sys.exit(1)
