"""Fixed isolated PostgreSQL proof for G7 generation credit integration."""
import asyncio, json, os, re, sys
from datetime import datetime, timezone
from uuid import uuid4

HEAD = "0006_credit_accounting_persistence"
GROUPS = ("mapping_admission", "imagen", "veo", "failure", "retry", "pipeline_success", "pipeline_partial", "replay_race")
T = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
phase = "guard"


def validate_target(project, url, provider, app_env):
    if (not re.fullmatch(r"generation-credit-verify-[a-z0-9]{12}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or url.port != 5432 or url.database != project.replace("-", "_")
            or url.username != "credit" or provider != "mock" or app_env != "test"):
        raise ValueError("generation_credit_target_refused")


async def proof(db, factory):
    from app import generation_credit as gc
    from app.models import Asset, AssetKind, GenerationMode, Job, JobState
    global phase
    checks = races = 0
    groups = {}

    def check(value):
        nonlocal checks
        assert value, "generation_credit_assertion"
        checks += 1

    async def seed(plan="free"):
        uid = uuid4()
        role = "master" if plan == "master" else "user"
        if plan == "master":
            await db.execute("INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) VALUES($1,$2,$3,true,'master','active','oauth',$4,$4)", uid, uid.hex, uid.hex+"@example.invalid", T)
        else:
            await db.execute("INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) VALUES($1,false,$2,'active','synthetic',$3,$3)", uid, role, T)
        return uid

    def make(uid, mode, model, units, *, parent=None, blocked=False):
        return Job(id=uuid4(), owner_user_id=uid, mode=mode, model=model,
                   state=JobState.PENDING, prompt="synthetic", parent_job_id=parent,
                   blocked=blocked, attempts=0,
                   parameters={"number_of_images": units} if mode == GenerationMode.T2I else {"duration_sec": units},
                   state_history=[], vertex_charged=False, created_at=T, updated_at=T)

    async def admit(uid, mode, model, units):
        item = make(uid, mode, model, units)
        async with factory() as session, session.begin():
            session.add(item)
            receipt = await gc.admit_generation(session, job=item, now=T)
        return item.id, receipt

    async def finish(job_id, kind, *, duration=None, ok=True, reason="provider_failed"):
        async with factory() as session, session.begin():
            item = await session.get(Job, job_id)
            if kind:
                session.add(Asset(job_id=job_id, kind=kind, local_path=job_id.hex+"/synthetic",
                                  mime="image/png" if kind == AssetKind.IMAGE else "video/mp4",
                                  size_bytes=1, duration_sec=duration, created_at=T))
            return await gc.terminalize_generation(session, job=item, succeeded=ok,
                                                    reason_code=None if ok else reason, now=T)

    phase = "mapping_admission"
    cases = [
        ("free", GenerationMode.T2I, "imagen-4.0-fast-generate-001", 1, "imagen_fast_image", 1),
        ("master", GenerationMode.T2I, "imagen-4.0-generate-001", 2, "imagen_standard_image", 2),
        ("master", GenerationMode.T2I, "imagen-4.0-ultra-generate-001", 1, "imagen_ultra_image", 1),
        ("free", GenerationMode.T2V, "veo-3.0-fast-generate-001", 4, "veo_fast_ms", 4000),
        ("master", GenerationMode.T2V, "veo-3.0-generate-001", 4, "veo_standard_ms", 4000),
    ]
    admitted = []
    for plan, mode, model, units, meter, maximum in cases:
        uid = await seed(plan); jid, receipt = await admit(uid, mode, model, units); admitted.append((uid,jid))
        row = await db.fetchrow("SELECT r.status,i.meter,i.maximum_units,r.reserve_operation_key FROM credit_reservations r JOIN credit_reservation_items i ON i.reservation_id=r.id WHERE r.user_id=$1", uid)
        for value in (receipt.reserved_microcredits > 0, row["status"] == "held", row["meter"] == meter,
                      row["maximum_units"] == maximum, row["reserve_operation_key"].startswith("g7r_"),
                      await db.fetchval("SELECT count(*) FROM jobs WHERE id=$1",jid)==1): check(value)
    denied = await seed()
    try: await admit(denied, GenerationMode.T2I, "imagen-4.0-generate-001", 1)
    except gc.GenerationCreditError as error: check(error.code == "credit_plan_refused")
    else: raise AssertionError("plan_refusal_missing")
    check(await db.fetchval("SELECT count(*) FROM jobs WHERE owner_user_id=$1", denied) == 0)
    groups[phase] = True

    phase = "imagen"
    uid=await seed(); jid,_=await admit(uid,GenerationMode.T2I,"imagen-4.0-fast-generate-001",2)
    result=await finish(jid,AssetKind.IMAGE); status=await db.fetchval("SELECT status FROM credit_reservations WHERE user_id=$1",uid)
    for value in (result.status=="settled",status=="settled",result.consumed_microcredits==50_000_000,
                  result.released_microcredits==50_000_000,await db.fetchval("SELECT actual_units FROM credit_usage_records WHERE user_id=$1",uid)==1): check(value)
    groups[phase]=True

    phase="veo"
    uid=await seed(); jid,_=await admit(uid,GenerationMode.T2V,"veo-3.0-fast-generate-001",4)
    result=await finish(jid,AssetKind.VIDEO,duration=3.5); status=await db.fetchval("SELECT status FROM credit_reservations WHERE user_id=$1",uid)
    for value in (result.status=="settled",status=="settled",result.consumed_microcredits==210_000_000,
                  result.released_microcredits==30_000_000,await db.fetchval("SELECT actual_units FROM credit_usage_records WHERE user_id=$1",uid)==3500): check(value)
    groups[phase]=True

    phase="failure"
    for reason in ("provider_failed","provider_timeout","provider_rate_limited","cancelled_before_delivery","delivery_failed"):
        uid=await seed(); jid,_=await admit(uid,GenerationMode.T2I,"imagen-4.0-fast-generate-001",1)
        result=await finish(jid,None,ok=False,reason=reason); row=await db.fetchrow("SELECT status,terminal_reason_code FROM credit_reservations WHERE user_id=$1",uid)
        for value in (result.status=="released",row["status"]=="released",row["terminal_reason_code"]==reason,
                      result.consumed_microcredits==0,result.released_microcredits==50_000_000): check(value)
    groups[phase]=True

    phase="retry"
    uid=await seed(); first,_=await admit(uid,GenerationMode.T2I,"imagen-4.0-fast-generate-001",1); await finish(first,None,ok=False)
    second,_=await admit(uid,GenerationMode.T2I,"imagen-4.0-fast-generate-001",1)
    keys=await db.fetch("SELECT reserve_operation_key,status FROM credit_reservations WHERE user_id=$1 ORDER BY created_at,id",uid)
    for value in (first!=second,len(keys)==2,keys[0]["status"]=="released",keys[1]["status"]=="held",keys[0]["reserve_operation_key"]!=keys[1]["reserve_operation_key"]): check(value)
    groups[phase]=True

    async def pipeline():
        uid=await seed(); parent=make(uid,GenerationMode.T2I,"imagen-4.0-fast-generate-001",1); child=make(uid,GenerationMode.I2V,"veo-3.0-fast-generate-001",4,parent=parent.id,blocked=True)
        async with factory() as session, session.begin():
            session.add_all([parent,child]); await gc.admit_generation(session,job=parent,pipeline_child=child,now=T)
        return uid,parent.id,child.id

    phase="pipeline_success"
    uid,pid,cid=await pipeline()
    async with factory() as session,session.begin():
        p=await session.get(Job,pid); session.add(Asset(job_id=pid,kind=AssetKind.IMAGE,local_path=pid.hex+"/i",mime="image/png",size_bytes=1,created_at=T)); held=await gc.terminalize_generation(session,job=p,succeeded=True,reason_code=None,now=T)
    check(held.status=="held"); check(await db.fetchval("SELECT status FROM credit_reservations WHERE user_id=$1",uid)=="held")
    result=await finish(cid,AssetKind.VIDEO,duration=4); usages=await db.fetch("SELECT meter,actual_units FROM credit_usage_records WHERE user_id=$1 ORDER BY meter",uid)
    for value in (result.status=="settled",len(usages)==2,usages[0]["meter"]=="imagen_fast_image",usages[0]["actual_units"]==1,
                  usages[1]["meter"]=="veo_fast_ms",usages[1]["actual_units"]==4000): check(value)
    groups[phase]=True

    phase="pipeline_partial"
    uid,pid,cid=await pipeline()
    async with factory() as session,session.begin():
        p=await session.get(Job,pid); session.add(Asset(job_id=pid,kind=AssetKind.IMAGE,local_path=pid.hex+"/i",mime="image/png",size_bytes=1,created_at=T)); await gc.terminalize_generation(session,job=p,succeeded=True,reason_code=None,now=T)
    result=await finish(cid,None,ok=False); row=await db.fetchrow("SELECT status,delivery FROM credit_reservations WHERE user_id=$1",uid)
    for value in (result.status=="settled",row["status"]=="settled",row["delivery"]=="partial",result.consumed_microcredits==50_000_000,result.released_microcredits==240_000_000): check(value)
    groups[phase]=True

    phase="replay_race"
    uid=await seed(); jid,_=await admit(uid,GenerationMode.T2I,"imagen-4.0-fast-generate-001",1)
    async with factory() as session,session.begin():
        session.add(Asset(job_id=jid,kind=AssetKind.IMAGE,local_path=jid.hex+"/i",mime="image/png",size_bytes=1,created_at=T))
    async def terminal(ok):
        async with factory() as session,session.begin():
            item=await session.get(Job,jid)
            return await gc.terminalize_generation(session,job=item,succeeded=ok,reason_code=None if ok else "provider_failed",now=T)
    outcomes=await asyncio.gather(terminal(True),terminal(False),return_exceptions=True)
    check(sum(not isinstance(x,Exception) for x in outcomes)==1); check(await db.fetchval("SELECT count(*) FROM credit_usage_records WHERE user_id=$1",uid)==1)
    check(await db.fetchval("SELECT count(*) FROM credit_reservations WHERE user_id=$1",uid)==1); races+=1
    async with factory() as session,session.begin():
        item=await session.get(Job,jid); replay=await gc.terminalize_generation(session,job=item,succeeded=True,reason_code=None,now=T)
    check(replay.replayed); check(await db.fetchval("SELECT count(*) FROM credit_usage_records WHERE user_id=$1",uid)==1); races+=1
    groups[phase]=True

    # Cross-table invariants are independently counted for every admitted actor.
    for uid,jid in admitted:
        for value in (
            await db.fetchval("SELECT count(*) FROM credit_accounts WHERE user_id=$1",uid)==1,
            await db.fetchval("SELECT count(*) FROM credit_cycles WHERE user_id=$1",uid)==1,
            await db.fetchval("SELECT count(*) FROM credit_grants WHERE user_id=$1",uid)>=1,
            await db.fetchval("SELECT count(*) FROM credit_reservation_items i JOIN credit_reservations r ON r.id=i.reservation_id WHERE r.user_id=$1",uid)==1,
            await db.fetchval("SELECT count(*) FROM credit_reservation_allocations a JOIN credit_reservations r ON r.id=a.reservation_id WHERE r.user_id=$1",uid)>=1,
            await db.fetchval("SELECT count(*) FROM jobs WHERE id=$1 AND owner_user_id=$2",jid,uid)==1,
        ): check(value)
    assert set(groups)==set(GROUPS) and all(groups.values()) and checks>=120 and races>=2
    return dict(groups=groups,races=races,checks=checks,complete=True)


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import app.models, app.credit_models
    global phase
    raw=os.environ.get("DATABASE_URL",""); url=make_url(raw)
    validate_target(os.environ.get("GENERATION_CREDIT_PROOF_PROJECT",""),url,os.environ.get("AI_PROVIDER"),os.environ.get("APP_ENV"))
    db=await asyncpg.connect(raw.replace("postgresql+asyncpg:","postgresql:")); engine=create_async_engine(raw)
    try:
        assert await db.fetchval("SELECT version_num FROM alembic_version")==HEAD
        result=await asyncio.wait_for(proof(db,async_sessionmaker(engine,expire_on_commit=False)),330)
        phase="done"; print(json.dumps(result))
    finally: await engine.dispose(); await db.close()


if __name__=="__main__":
    try: asyncio.run(main())
    except TimeoutError: print("generation_credit_proof_failed:"+phase); sys.exit(124)
    except Exception: print("generation_credit_proof_failed:"+phase); sys.exit(1)
