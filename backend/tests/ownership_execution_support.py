"""Fixed local-only PostgreSQL proofs; never imported by production code."""
import asyncio
from datetime import timedelta
import json
import os
import queue
import sys
import threading
import time
from uuid import NAMESPACE_URL, UUID, uuid5

from ownership_support import validate_target, validate_fixture_inventory

RACES = ("create_create", "create_retry", "retry_retry")
OPERATIONS = {"worker_proof", "pipeline_proof", "prepare_race", "check_race",
              "hold_source", "lock_waiters", "race_completed", "expire_session", "check_completed"}


def content_id(case, kind):
    return uuid5(NAMESPACE_URL, "ownership-execution/" + case + "/" + kind)


def owner(case="b"):
    return uuid5(NAMESPACE_URL, "ownership-fixture/" + case)


def validate_payload(payload, url, provider, app_env):
    if (not isinstance(payload, dict) or set(payload) != {"project", "operation", "case", "records"}
            or payload["operation"] not in OPERATIONS or type(payload["records"]) is not list
            or len(payload["records"]) > 2):
        raise ValueError("execution_target_refused")
    validate_target({"project": payload["project"], "hashes": {}}, url, provider, app_env)
    race_op = payload["operation"] in {"prepare_race", "check_race", "hold_source", "lock_waiters", "race_completed"}
    if payload["case"] not in (RACES if race_op else ("",)):
        raise ValueError("execution_case_refused")
    if payload["operation"] != "check_completed" and payload["records"]:
        raise ValueError("execution_records_refused")
    for record in payload["records"]:
        if not isinstance(record, dict) or set(record) != {"kind", "id"} or record["kind"] not in {"pipeline", "expiry"}:
            raise ValueError("execution_records_refused")
        UUID(record["id"])


def job(case, kind, *, user="b", mode="t2i", state="completed", **kwargs):
    from app.models import Job, GenerationMode, JobState
    return Job(id=content_id(case,kind), owner_user_id=owner(user), mode=GenerationMode(mode),
               state=JobState(state), model="imagen-4.0-fast-generate-001" if mode == "t2i" else "veo-3.0-fast-generate-001",
               prompt="fixture", attempts=0, parameters={}, state_history=[], **kwargs)


async def source_fixture(session, case, *, user="b", real_bytes=False, state="completed"):
    from app.models import Asset, AssetKind
    parent = job(case,"parent",user=user,state=state)
    session.add(parent)
    await session.flush()
    data = b"fixture"
    path = str(parent.id) + "/source.png"
    if real_bytes:
        from app.services import storage
        from app.services.mock_media import generate_mock_pngs
        data = generate_mock_pngs(parent.model,"fixture",number_of_images=1,aspect_ratio="1:1")[0]
        path = storage.save_bytes(parent.id,"source.png",data)
    asset = Asset(id=content_id(case,"asset"),job_id=parent.id,kind=AssetKind.IMAGE,
                  local_path=path,mime="image/png",size_bytes=len(data))
    session.add(asset)
    await session.flush()
    return parent, asset


async def count_outbox(session, job_id):
    from sqlalchemy import func, select
    from app.models import OutboxEvent
    return await session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.aggregate_id == job_id))


async def worker_proof():
    from sqlalchemy import func, select
    from app.db import AsyncSessionLocal
    from app.models import Asset, PromptEnhancement, JobState
    from app.services.jobs import handlers
    checked = 0
    for entry in ("t2i","t2v","i2v","poll_t2v","poll_i2v"):
        for reference in ("enhancement_id","parent_job_id","retry_of_job_id","source_asset_id"):
            case = entry + "_" + reference
            async with AsyncSessionLocal() as session:
                source_parent, asset = await source_fixture(session,case,user="a")
                related_parent = job(case,"related",user="a")
                retry = job(case,"retry",user="a",state="failed")
                enhancement = PromptEnhancement(id=content_id(case,"enhancement"),owner_user_id=owner("a"),
                    original="fixture",enhanced="fixture",components={},target_mode="t2i",
                    target_model=source_parent.model,llm_model="mock")
                session.add_all([related_parent,retry,enhancement])
                await session.flush()
                relations = dict(enhancement_id=enhancement.id,parent_job_id=related_parent.id,
                                 retry_of_job_id=retry.id,source_asset_id=asset.id)
                target = {"enhancement_id":enhancement,"parent_job_id":related_parent,
                          "retry_of_job_id":retry,"source_asset_id":source_parent}[reference]
                target.owner_user_id = owner("b")
                current = job(case,"execution",user="a",mode=entry.removeprefix("poll_"),
                              state="polling" if entry.startswith("poll_") else "pending",
                              vertex_operation_name="mock-operation" if entry.startswith("poll_") else None,
                              **relations)
                session.add(current)
                await session.commit()
                current_id, target_id = current.id, target.id
                snapshot = (target.owner_user_id, getattr(target,"state",None), getattr(target,"state_history",None))
                await getattr(handlers,"handle_" + entry.removeprefix("poll_"))(session,current)
                await session.refresh(current)
                await session.refresh(target)
                assert current.id == current_id and target.id == target_id
                assert current.state == JobState.FAILED and current.error["code"] == "ownership_reference_mismatch"
                assert current.attempts == 0 and not current.vertex_charged
                assert snapshot == (target.owner_user_id,getattr(target,"state",None),getattr(target,"state_history",None))
                assert await session.scalar(select(func.count()).select_from(Asset).where(Asset.job_id == current_id)) == 0
                assert await count_outbox(session,current_id) == 0
                checked += 1
    return {"execution_checks":checked}


async def wait_pipeline_locks():
    from sqlalchemy import text
    from app.db import AsyncSessionLocal
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        async with AsyncSessionLocal() as session:
            count = await session.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND application_name='g4b_pipeline_link' AND wait_event_type='Lock'"))
        if count == 2:
            return
        await asyncio.sleep(0.02)
    raise ValueError("pipeline_lock_overlap_missing")


async def pipeline_proof():
    from sqlalchemy import select, text
    from app.db import AsyncSessionLocal
    from app.models import Job, JobState
    from app.services.jobs.pipeline_link import link_completed_parent, fail_blocked_children_for_parent
    async with AsyncSessionLocal() as session:
        parent, asset = await source_fixture(session,"pipeline_race",real_bytes=True)
        child = job("pipeline_race","child",mode="i2v",state="pending",blocked=True,parent_job_id=parent.id)
        session.add(child)
        await session.commit()
        parent_id, child_id = parent.id, child.id
    barrier = asyncio.Barrier(3)
    async def link():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET LOCAL application_name='g4b_pipeline_link'"))
            parent = await session.get(Job,parent_id)
            await barrier.wait()
            return await link_completed_parent(session,parent)
    async with AsyncSessionLocal() as holder:
        await holder.execute(select(Job.id).where(Job.id == child_id).with_for_update())
        tasks = [asyncio.create_task(link()) for _ in range(2)]
        try:
            await asyncio.wait_for(barrier.wait(),5)
            await wait_pipeline_locks()
            await holder.rollback()
            results = await asyncio.wait_for(asyncio.gather(*tasks),10)
        finally:
            await holder.rollback()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    assert sum(result.linked for result in results) == 1
    assert {result.reason for result in results} == {None,"child_already_unblocked"}
    async with AsyncSessionLocal() as session:
        parent = await session.get(Job,parent_id)
        repeat = await link_completed_parent(session,parent)
        assert not repeat.linked and await count_outbox(session,child_id) == 1
        child = await session.get(Job,child_id)
        assert child.source_asset_id == content_id("pipeline_race","asset") and not child.blocked
    for failed in (False, True):
        async with AsyncSessionLocal() as session:
            case = "pipeline_foreign_failed" if failed else "pipeline_foreign_completed"
            parent, asset = await source_fixture(session,case,user="a",state="failed" if failed else "completed")
            child = job(case,"child",mode="i2v",state="pending",blocked=True,parent_job_id=parent.id)
            session.add(child)
            await session.commit()
            child_id = child.id
            if failed:
                result = await fail_blocked_children_for_parent(session,parent)
                assert result.failed_count == 0 and result.skipped_count == 1
            else:
                result = await link_completed_parent(session,parent)
                assert not result.linked
            assert result.reason == "ownership_reference_mismatch"
            await session.refresh(child)
            assert child.state == JobState.PENDING and child.blocked and child.source_asset_id is None
            assert await count_outbox(session,child_id) == 0
    return {"pipeline_checks":3}


async def race_operation(session, operation, case):
    from sqlalchemy import select, text
    from app.models import Job, JobState
    from app.services.jobs.i2v_guard import ACTIVE_I2V_STATES
    if operation == "prepare_race":
        if await session.get(Job,content_id(case,"parent")):
            raise ValueError("race_fixture_collision")
        parent, asset = await source_fixture(session,case,real_bytes=True)
        for kind in ("retry1","retry2"):
            retry = job(case,kind,mode="i2v",state="failed",source_asset_id=asset.id,parent_job_id=parent.id)
            retry.attempts = 1
            session.add(retry)
        await session.commit()
        return {"prepared":True}
    if operation == "lock_waiters":
        count = await session.scalar(text("""WITH RECURSIVE blocked(pid) AS (
            SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND application_name=:holder
            UNION
            SELECT a.pid FROM pg_stat_activity a JOIN blocked b ON b.pid=ANY(pg_blocking_pids(a.pid))
            WHERE a.datname=current_database())
            SELECT count(*) FROM pg_stat_activity a JOIN blocked b USING(pid)
            WHERE a.wait_event_type='Lock' AND a.query LIKE '%FOR UPDATE OF assets%'"""),
            {"holder":"g4b_source_"+case})
        return {"lock_waiters":count}
    rows = list((await session.scalars(select(Job).where(Job.source_asset_id == content_id(case,"asset")))).all())
    originals = {content_id(case,"retry1"),content_id(case,"retry2")}
    assert all(row.state == JobState.FAILED and row.attempts == 1 for row in rows if row.id in originals)
    assert len([row for row in rows if row.id in originals]) == 2
    created = [row for row in rows if row.id not in originals]
    assert len(created) == 1 and created[0].owner_user_id == owner()
    assert await count_outbox(session,created[0].id) == 1
    if operation == "check_race":
        assert sum(row.state in ACTIVE_I2V_STATES for row in rows) == 1
        return {"race_checks":1}
    assert operation == "race_completed"
    assert created[0].state == JobState.COMPLETED and sum(row.state in ACTIVE_I2V_STATES for row in rows) == 0
    return {"race_completed":1}


async def completed_records(session, records):
    from sqlalchemy import select
    from app.models import Asset, Job, JobState
    from app.services import storage
    if not records:
        raise ValueError("completion_records_missing")
    checked = 0
    for record in records:
        parent = await session.get(Job,UUID(record["id"]))
        expected = owner("a") if record["kind"] == "expiry" else owner()
        assert parent and parent.owner_user_id == expected and parent.state == JobState.COMPLETED
        jobs = [parent]
        if record["kind"] == "pipeline":
            children = list((await session.scalars(select(Job).where(Job.parent_job_id == parent.id))).all())
            assert len(children) == 1
            child = children[0]
            assert child.owner_user_id == expected and child.state == JobState.COMPLETED and not child.blocked
            source = await session.get(Asset,child.source_asset_id)
            assert source and source.job_id == parent.id and await count_outbox(session,child.id) == 1
            jobs.append(child)
        for row in jobs:
            assets = list((await session.scalars(select(Asset).where(Asset.job_id == row.id))).all())
            assert assets
            for asset in assets:
                data = storage.read_bytes(asset.local_path)
                assert data.startswith(b"\x89PNG") or data[4:8] == b"ftyp"
        checked += 1
    return {"completed_records":checked}


def validate_release_line(line):
    # Windows text pipes emit CRLF; accept either line ending, not arbitrary commands.
    if not isinstance(line,str) or len(line) > 128 or not line.endswith("\n"):
        raise ValueError("lock_release_refused")
    value = json.loads(line)
    if not isinstance(value,dict) or set(value) != {"release"} or value["release"] is not True:
        raise ValueError("lock_release_refused")


async def hold_source(session, case):
    from sqlalchemy import select, text
    from app.models import Asset
    await session.execute(text("SELECT set_config('application_name',:name,true)"),{"name":"g4b_source_"+case})
    asset = await session.scalar(select(Asset.id).where(Asset.id == content_id(case,"asset")).with_for_update())
    if asset is None:
        raise ValueError("lock_fixture_missing")
    print('{"locked":true}',flush=True)
    incoming = queue.Queue(maxsize=1)
    def read_release():
        incoming.put(sys.stdin.readline(128))
    threading.Thread(target=read_release,daemon=True).start()
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            try:
                line = incoming.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            validate_release_line(line)
            return {"released":True}
        raise ValueError("lock_holder_timeout")
    finally:
        await session.rollback()


async def run(payload):
    from sqlalchemy import select
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.db import AsyncSessionLocal
    from app.identity_models import UserSession
    from app.models import utc_now
    settings = get_settings()
    validate_payload(payload,make_url(os.environ.get("DATABASE_URL","")),settings.ai_provider,settings.app_env)
    async with AsyncSessionLocal() as session:
        await validate_fixture_inventory(session)
        operation, case = payload["operation"], payload["case"]
        if operation == "worker_proof":
            return await worker_proof()
        if operation == "pipeline_proof":
            return await pipeline_proof()
        if operation == "hold_source":
            return await hold_source(session,case)
        if operation == "expire_session":
            rows = list((await session.scalars(select(UserSession).where(UserSession.user_id == owner("a")))).all())
            assert len(rows) == 1
            rows[0].last_seen_at = utc_now() - timedelta(days=1)
            await session.commit()
            return {"expired":True}
        if operation == "check_completed":
            return await completed_records(session,payload["records"])
        return await race_operation(session,operation,case)


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.readline(8192))
        result = asyncio.run(run(request))
        print(json.dumps(result),flush=True)
    except Exception:
        print("execution_proof_failed",file=sys.stderr)
        sys.exit(1)
