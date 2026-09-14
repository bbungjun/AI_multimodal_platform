"""Owned, test-only fixture protocol for Agent QA workspace journeys."""
from __future__ import annotations
import asyncio,json,re,sys
from datetime import timedelta
from sqlalchemy import func,select
from sqlalchemy.engine import make_url
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.identity_models import User,UserOrigin,UserRole,UserStatus
from app.models import Asset,GenerationMode,Job,JobState,utc_now

PROJECT=re.compile(r"^ownership-verify-[0-9a-f]{12}$")
def validate(payload,url,provider,app_env):
 if type(payload)is not dict or payload.get('operation')not in{'prepare','promote','inspect'}or set(payload)!={'operation'}:raise ValueError('workspace_fixture_refused')
 u=make_url(url);project=(u.database or'').replace('_','-')
 if not PROJECT.fullmatch(project)or u.host!='db'or provider!='mock'or app_env!='test':raise ValueError('workspace_fixture_target_refused')
 return payload['operation']
def path(job):
 states=['pending']
 for e in job.state_history or[]:
  raw=e.get('state')if isinstance(e,dict)else None;s=raw if raw in{'completed','failed','cancelled'}else('running'if raw in{'queued','generating','polling','downloading'}else None)
  if s and states[-1]!=s:states.append(s)
 return','.join(states)
async def execute(payload):
 s=get_settings();op=validate(payload,s.database_url,s.ai_provider,s.app_env);now=utc_now()
 async with AsyncSessionLocal()as db:
  user=await db.scalar(select(User).where(User.google_sub=='mock-oauth-browser-user'))
  if user is None:
   user=User(google_sub='mock-oauth-browser-user',email='oauth-fixture@example.test',email_verified=True,
    display_name='OAuth Fixture',profile_image_url=None,role=UserRole.USER,status=UserStatus.ACTIVE,
    data_origin=UserOrigin.OAUTH,signed_up_at=now,updated_at=now)
   db.add(user);await db.flush()
  if op=='prepare':
   existing=await db.scalar(select(func.count()).select_from(Job).where(Job.owner_user_id==user.id))
   if existing:raise ValueError('workspace_fixture_nonempty')
   retry_id=None
   for i in range(22):
    job=Job(owner_user_id=user.id,mode=GenerationMode.T2I,model='imagen-4.0-fast-generate-001',state=JobState.FAILED,
      prompt='A recoverable studio image.' if i==0 else 'fixture',blocked=False,attempts=1,
      parameters={'aspect_ratio':'1:1','number_of_images':1},state_history=[{'state':'failed','at':(now-timedelta(minutes=i)).isoformat(),'detail':None}],
      error={'message':'Controlled QA failure'},created_at=now-timedelta(minutes=i),updated_at=now-timedelta(minutes=i))
    db.add(job);await db.flush()
    if i==0:retry_id=job.id
   await db.commit();return{'jobs':22,'retry_job_id':str(retry_id)}
  if op=='promote':user.role=UserRole.MASTER;await db.commit();return{'promoted':True}
  original=await db.scalar(select(Job).where(Job.owner_user_id==user.id,Job.prompt=='A recoverable studio image.').order_by(Job.created_at.asc()).limit(1))
  retry=await db.scalar(select(Job).where(Job.retry_of_job_id==original.id).order_by(Job.created_at.desc()).limit(1))if original else None
  return{'retry_created':retry is not None,'retry_distinct':bool(retry and retry.id!=original.id),'retry_link':bool(retry and retry.retry_of_job_id==original.id),
    'retry_state_path':path(retry)if retry else'missing','retry_assets':await db.scalar(select(func.count()).select_from(Asset).where(Asset.job_id==retry.id))if retry else 0}
def main():
 try:
  raw=sys.stdin.read(1025)
  if len(raw)>1024:raise ValueError('workspace_fixture_refused')
  result=asyncio.run(execute(json.loads(raw)))
 except Exception as e:
  code=str(e)if isinstance(e,ValueError)and re.fullmatch(r'workspace_fixture_[a-z_]+',str(e))else'workspace_fixture_failed';print(json.dumps({'complete':False,'error':code},separators=(',',':')));return 1
 print(json.dumps({'complete':True,**result},separators=(',',':')));return 0
if __name__=='__main__':raise SystemExit(main())
