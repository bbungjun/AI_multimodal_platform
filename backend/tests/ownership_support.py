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
        await validate_fixture_inventory(session)
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


async def validate_fixture_inventory(session):
    from sqlalchemy import select, text
    from app.identity_models import User
    if await session.scalar(text("SELECT version_num FROM alembic_version")) != EXPECTED_REVISION:
        raise ValueError("admission_revision_refused")
    users = set((await session.scalars(select(User.id))).all())
    if users != {uuid5(NAMESPACE_URL, "ownership-fixture/" + case) for case in CASES}:
        raise ValueError("admission_identity_inventory_refused")


ACCESS_OPERATIONS = {"prepare_metadata","inspect_metadata","check_read_queries","clear_metadata",
                     "prepare_delete_race","inspect_delete_race","hold_delete_source","delete_waiters",
                     "prepare_files","clear_files"}
DELETE_CASES = ("delete_create","delete_retry")


def access_id(case,kind):
    return uuid5(NAMESPACE_URL,"ownership-access/"+case+"/"+kind)


def access_owner(case):
    return uuid5(NAMESPACE_URL,"ownership-fixture/"+case)


def validate_access_payload(payload,url,provider,app_env):
    from uuid import UUID
    if type(payload) is not dict or set(payload)!={"project","access_operation","case","records"}:
        raise ValueError("access_payload_refused")
    operation=payload["access_operation"]
    race=operation in {"prepare_delete_race","inspect_delete_race","hold_delete_source","delete_waiters"}
    if operation not in ACCESS_OPERATIONS or payload["case"] not in (DELETE_CASES if race else ("",)):
        raise ValueError("access_operation_refused")
    records=payload["records"]
    if type(records) is not list or len(records)>16 or (records and operation!="inspect_delete_race"):
        raise ValueError("access_records_refused")
    for record in records:
        if type(record) is not dict or set(record)!={"kind","id"} or record["kind"]!="admitted":
            raise ValueError("access_records_refused")
        UUID(record["id"])
    validate_target({"project":payload["project"],"hashes":{}},url,provider,app_env)


def access_job(case,kind,**kwargs):
    from app.models import Job,GenerationMode,JobState
    defaults=dict(owner_user_id=access_owner(case),mode=GenerationMode.T2I,state=JobState.COMPLETED,
                  model="imagen-4.0-fast-generate-001",prompt="fixture",parameters={},state_history=[],attempts=0)
    return Job(id=access_id(case,kind),**(defaults|kwargs))


async def access_source(session,case,kind="parent",*,user=None):
    from app.models import Asset,AssetKind
    from app.services import storage
    from app.services.mock_media import generate_mock_pngs
    parent=access_job(case,kind,owner_user_id=access_owner(user or case))
    session.add(parent)
    await session.flush()
    data=generate_mock_pngs(parent.model,"fixture",number_of_images=1,aspect_ratio="1:1")[0]
    path=storage.save_bytes(parent.id,"source.png",data)
    asset=Asset(id=access_id(case,kind+"-asset"),job_id=parent.id,kind=AssetKind.IMAGE,
                local_path=path,mime="image/png",size_bytes=len(data))
    session.add(asset)
    await session.flush()
    return parent,asset


def access_metadata_ids():
    kinds=[*("row-"+str(i) for i in range(100)),"parent","child","own-delete","own-dependent",
           "corrupt-parent","corrupt-retry","corrupt-source","corrupt-enhancement","corrupt-pipeline","corrupt-child",
           "x-parent","x-retry","x-source","x-parent-dependent","x-retry-dependent","x-source-dependent"]
    return {access_id(case,kind) for case in ("a","b","master") for kind in kinds}


async def prepare_metadata(session):
    from sqlalchemy import select
    from app.models import Job,Asset,AssetKind,PromptEnhancement,GenerationMode,JobState
    if await session.scalar(select(Job.id).where(Job.id.in_(access_metadata_ids())).limit(1)):
        raise ValueError("access_fixture_collision")
    now=datetime.now(timezone.utc)
    for case in ("a","b","master"):
        parent,asset=await access_source(session,case)
        enhancement=PromptEnhancement(id=access_id(case,"enhancement"),owner_user_id=access_owner(case),
            original="fixture",enhanced="fixture",components={},target_mode=GenerationMode.T2I,
            target_model=parent.model,llm_model="mock")
        session.add(enhancement)
        await session.flush()
        for i in range(100):
            row=access_job(case,"row-"+str(i),created_at=now,updated_at=now,parent_job_id=parent.id,
                retry_of_job_id=parent.id,enhancement_id=enhancement.id,source_asset_id=asset.id)
            if i==1:
                row.mode,row.model,row.state=GenerationMode.T2V,"veo-3.0-fast-generate-001",JobState.FAILED
            session.add(row)
        session.add(access_job(case,"child",mode=GenerationMode.I2V,model="veo-3.0-fast-generate-001",
            state=JobState.PENDING,parent_job_id=parent.id,blocked=True))
        target,output=await access_source(session,case,"own-delete")
        session.add(access_job(case,"own-dependent",parent_job_id=target.id,retry_of_job_id=target.id,source_asset_id=output.id))
        await session.flush()
        session.add(Asset(id=access_id(case,"video-asset"),job_id=access_id(case,"row-1"),kind=AssetKind.VIDEO,
            local_path=str(access_id(case,"row-1"))+"/fixture.mp4",mime="video/mp4",size_bytes=0))
    await session.flush()
    broken=access_job("a","corrupt-pipeline",model="access-corrupt")
    session.add(broken)
    await session.flush()
    session.add(access_job("a","corrupt-child",owner_user_id=access_owner("b"),model="access-corrupt",
                          mode=GenerationMode.I2V,state=JobState.PENDING,parent_job_id=broken.id,blocked=True))
    for kind,field in (("parent","parent_job_id"),("retry","retry_of_job_id"),
                       ("source","source_asset_id"),("enhancement","enhancement_id")):
        ref=access_id("b","parent-asset" if kind=="source" else "enhancement" if kind=="enhancement" else "parent")
        session.add(access_job("a","corrupt-"+kind,model="access-corrupt",**{field:ref}))
    for kind,field in (("parent","parent_job_id"),("retry","retry_of_job_id"),("source","source_asset_id")):
        target,output=await access_source(session,"a","x-"+kind)
        session.add(access_job("a","x-"+kind+"-dependent",owner_user_id=access_owner("b"),
            model="access-corrupt",state=JobState.PENDING,**{field:output.id if kind=="source" else target.id}))
    await session.commit()
    return {"prepared":True}


async def access_query_proof(session):
    from sqlalchemy import select,event
    from app.models import Job
    from app.ownership import OwnershipAccess
    from types import SimpleNamespace
    # Measure content SELECTs only, after target/identity checks and before any auth.
    engine=session.bind.sync_engine
    statements=[]
    def observed(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(True)
    event.listen(engine,"before_cursor_execute",observed)
    try:
        for size in (1,20,100):
            session.expunge_all()
            statements.clear()
            access=OwnershipAccess(session,SimpleNamespace(id=access_owner("a"),role="user"))
            rows=list((await session.scalars(access.jobs_statement().where(
                Job.id.in_([access_id("a","row-"+str(i)) for i in range(100)]))
                .order_by(Job.created_at.desc(),Job.id.desc()).limit(size))).all())
            await access.validate_read_jobs(rows)
            assert len(rows)==size and len(statements)==5
    finally:
        event.remove(engine,"before_cursor_execute",observed)
    return {"query_checks":3}


async def access_race(session,operation,case,records):
    from sqlalchemy import select,text,func
    from app.models import Job,Asset,JobState,GenerationMode,OutboxEvent
    from uuid import UUID
    if operation=="prepare_delete_race":
        if await session.get(Job,access_id(case,"parent")):
            raise ValueError("access_race_collision")
        parent,asset=await access_source(session,case,user="a")
        if case=="delete_retry":
            session.add(access_job(case,"retry",owner_user_id=access_owner("a"),mode=GenerationMode.I2V,
                model="veo-3.0-fast-generate-001",state=JobState.FAILED,
                parent_job_id=parent.id,source_asset_id=asset.id))
        await session.commit()
        return {"prepared":True}
    if operation=="delete_waiters":
        count=await session.scalar(text("""WITH RECURSIVE blocked(pid) AS (
            SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND application_name=:holder
            UNION SELECT a.pid FROM pg_stat_activity a JOIN blocked b ON b.pid=ANY(pg_blocking_pids(a.pid))
            WHERE a.datname=current_database()) SELECT count(*) FROM pg_stat_activity a JOIN blocked b USING(pid)
            WHERE a.wait_event_type='Lock' AND a.query LIKE '%FOR UPDATE OF assets%'"""),
            {"holder":"g43a_source_"+case})
        return {"lock_waiters":count}
    if operation=="hold_delete_source":
        import queue,threading,time
        from ownership_execution_support import validate_release_line
        await session.execute(text("SELECT set_config('application_name',:name,true)"),{"name":"g43a_source_"+case})
        assert await session.scalar(select(Asset.id).where(Asset.id==access_id(case,"parent-asset")).with_for_update())
        incoming=queue.Queue(maxsize=1)
        threading.Thread(target=lambda:incoming.put(sys.stdin.readline(128)),daemon=True).start()
        print('{"locked":true}',flush=True)
        deadline=time.monotonic()+20
        try:
            while time.monotonic()<deadline:
                try:
                    line=incoming.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue
                validate_release_line(line)
                return {"released":True}
            raise ValueError("access_lock_timeout")
        finally:
            await session.rollback()
    parent=await session.get(Job,access_id(case,"parent"))
    rows=list((await session.scalars(select(Job).where(Job.source_asset_id==access_id(case,"parent-asset")))).all())
    new=[row for row in rows if row.id!=access_id(case,"retry")]
    if records:
        assert len(records)==1 and len(new)==1 and new[0].id==UUID(records[0]["id"]) and parent is not None
        assert new[0].owner_user_id==access_owner("a") and new[0].state==JobState.PENDING
        assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.aggregate_id==new[0].id))==1
    else:
        assert parent is None and not rows
        assert await session.get(Asset,access_id(case,"parent-asset")) is None
        retry=await session.get(Job,access_id(case,"retry"))
        assert retry is None or (retry.source_asset_id is None and retry.parent_job_id is None and retry.state==JobState.FAILED)
    return {"race_checks":1}


async def access_run(payload):
    from sqlalchemy import select,delete,or_
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.models import Job,Asset,PromptEnhancement,OutboxEvent
    from app.services import storage
    settings=get_settings()
    validate_access_payload(payload,make_url(os.environ.get("DATABASE_URL","")),settings.ai_provider,settings.app_env)
    operation,case=payload["access_operation"],payload["case"]
    async with AsyncSessionLocal() as session:
        await validate_fixture_inventory(session)
        if operation in ("prepare_files","clear_files"):
            return await file_fixtures(session,operation)
        if case:
            return await access_race(session,operation,case,payload["records"])
        if operation=="prepare_metadata":
            return await prepare_metadata(session)
        if operation=="check_read_queries":
            return await access_query_proof(session)
        if operation=="inspect_metadata":
            present=[]
            for user in ("a","b","master"):
                target=await session.get(Job,access_id(user,"own-delete"))
                present.append(target is not None)
                dep=await session.get(Job,access_id(user,"own-dependent"))
                assert dep
                if target is None:
                    assert dep.parent_job_id is None and dep.retry_of_job_id is None and dep.source_asset_id is None
                else:
                    assert target.owner_user_id==access_owner(user) and dep.parent_job_id==target.id
                    asset=await session.get(Asset,access_id(user,"own-delete-asset"))
                    assert asset and storage.read_bytes(asset.local_path).startswith(b"\x89PNG")
            assert all(present) or not any(present)
            for kind in ("parent","retry","source"):
                target=await session.get(Job,access_id("a","x-"+kind))
                assert target and target.owner_user_id==access_owner("a")
                asset=await session.get(Asset,access_id("a","x-"+kind+"-asset"))
                assert asset and storage.read_bytes(asset.local_path).startswith(b"\x89PNG")
            return {"inspected":True}
        assert operation=="clear_metadata"
        ids=access_metadata_ids()|{access_id(case,kind) for case in DELETE_CASES for kind in ("parent","retry")}
        race_assets=[access_id(case,"parent-asset") for case in DELETE_CASES]
        related=list((await session.scalars(select(Job).where(Job.source_asset_id.in_(race_assets)))).all())
        if any(row.owner_user_id!=access_owner("a") for row in related):
            raise ValueError("access_cleanup_owner_refused")
        ids.update(row.id for row in related)
        stored=list((await session.scalars(select(Asset).where(Asset.job_id.in_(ids)))).all())
        for asset in stored:
            if not asset.local_path.startswith(str(asset.job_id)+"/"):
                raise ValueError("access_cleanup_path_refused")
            storage.delete_file(asset.local_path,missing_ok=True)
        await session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(ids)))
        await session.execute(delete(Asset).where(Asset.job_id.in_(ids)))
        await session.execute(delete(Job).where(Job.id.in_(ids)))
        await session.execute(delete(PromptEnhancement).where(PromptEnhancement.id.in_([access_id(c,"enhancement") for c in ("a","b","master")])))
        await session.commit()
        return {"cleared":True}


def file_id(case, kind):
    return uuid5(NAMESPACE_URL,"ownership-files/"+case+"/"+kind)


async def file_fixtures(session, operation):
    from sqlalchemy import select, delete
    from app.models import Job, Asset, AssetKind, GenerationMode, JobState
    from app.services import storage
    cases=("a","b","logout","orphan","missing","confused")
    ids=[file_id(case,"job") for case in cases]
    existing=list((await session.scalars(select(Job).where(Job.id.in_(ids)))).all())
    if operation=="prepare_files":
        if existing:
            raise ValueError("file_fixture_collision")
        for case in cases:
            owner=access_owner(case if case in ("a","b","logout") else "a")
            session.add(Job(id=file_id(case,"job"),owner_user_id=owner,mode=GenerationMode.T2I,
                model="imagen-4.0-fast-generate-001",prompt="fixture",parameters={},
                state=JobState.COMPLETED,state_history=[],attempts=0))
        await session.flush()
        for case in cases:
            path=f"{file_id(case,'job')}/output.bin"
            if case!="missing":
                storage.save_bytes(file_id(case,"job"),"output.bin",b"0123456789")
            if case!="orphan":
                session.add(Asset(id=file_id(case,"asset"),job_id=file_id("a" if case=="confused" else case,"job"),
                    local_path=path,kind=AssetKind.IMAGE,mime="application/octet-stream",size_bytes=10))
        await session.commit()
        return {"prepared":True}
    for row in existing:
        case=next(case for case in cases if file_id(case,"job")==row.id)
        if row.owner_user_id!=access_owner(case if case in ("a","b","logout") else "a"):
            raise ValueError("file_cleanup_owner_refused")
    assets=list((await session.scalars(select(Asset).where(Asset.job_id.in_(ids)))).all())
    if any(row.id not in {file_id(c,"asset") for c in cases} for row in assets):
        raise ValueError("file_cleanup_asset_refused")
    for case in cases:
        storage.delete_file(f"{file_id(case,'job')}/output.bin",missing_ok=True)
    await session.execute(delete(Asset).where(Asset.id.in_([file_id(c,"asset") for c in cases])))
    await session.execute(delete(Job).where(Job.id.in_(ids)))
    await session.commit()
    return {"cleared":True}


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.readline(8192))
        if "access_operation" in payload:
            print(json.dumps(asyncio.run(access_run(payload))),flush=True)
        elif "operation" in payload:
            print(json.dumps(asyncio.run(admission(payload))))
        else:
            asyncio.run(seed(payload))
            print("seeded")
    except Exception:
        print("seed_failed", file=sys.stderr)
        sys.exit(1)
