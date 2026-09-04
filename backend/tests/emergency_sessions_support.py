"""Fixed isolated PostgreSQL proof for guarded emergency Session revocation."""
import asyncio
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4


HEAD = '0006_credit_accounting_persistence'
GROUPS = (
    'login_gating', 'preview', 'operator_guards', 'revocation',
    'idempotency', 'admission', 'auth_race', 'rollback_cleanup',
)
T = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
phase = 'guard'


def validate_target(project, url, provider, app_env, login_enabled):
    if (
        not re.fullmatch(r'emergency-auth-verify-[a-z0-9]{12}', project)
        or url.get_backend_name() != 'postgresql'
        or url.host != 'db'
        or url.port != 5432
        or url.database != project.replace('-', '_')
        or url.username != 'credit'
        or provider != 'mock'
        or app_env != 'test'
        or login_enabled.lower() != 'false'
    ):
        raise ValueError('emergency_session_target_refused')


async def proof(db, factory):
    from sqlalchemy import select

    from app.auth.emergency import (
        EmergencyRevocationError,
        format_receipt,
        revoke_active_sessions,
        validate_emergency_target,
    )
    from app.auth.service import AuthError, AuthService
    from app.identity_models import UserSession

    global phase
    checks = 0
    races = 0
    groups = {}

    def check(condition):
        nonlocal checks
        assert condition, 'emergency_session_assertion'
        checks += 1

    async def seed_session(*, revoked=False):
        user_id, session_id = uuid4(), uuid4()
        marker = uuid4().hex
        secret = marker + 'abcdefghijk'
        await db.execute(
            "INSERT INTO users(id,google_sub,email,email_verified,role,status,data_origin,signed_up_at,updated_at) "
            "VALUES($1,$2,$3,true,'user','active','oauth',$4,$4)",
            user_id, marker, marker + '@example.invalid', T,
        )
        await db.execute(
            "INSERT INTO user_sessions(id,user_id,token_hash,created_at,last_seen_at,absolute_expires_at,revoked_at,revoke_reason) "
            "VALUES($1,$2,$3,$4,$4,$5,$6,$7)",
            session_id, user_id, hashlib.sha256(secret.encode()).digest(), T,
            T + timedelta(days=7), T if revoked else None,
            'user_logout' if revoked else None,
        )
        return secret, session_id

    async def apply(reason='operator_drill', execute=True):
        async with factory() as session, session.begin():
            return await revoke_active_sessions(
                session, reason=reason, now=T + timedelta(hours=1), execute=execute)

    class Flows:
        puts = consumes = 0

        async def put(self, *args):
            self.puts += 1

        async def consume(self, *args):
            self.consumes += 1
            return None

    class Google:
        calls = 0

        def authorization_url(self, *args):
            self.calls += 1
            return 'https://identity.invalid/'

        async def exchange_code(self, *args):
            self.calls += 1
            raise AssertionError('provider must not run')

    phase = 'login_gating'
    flows, google = Flows(), Google()
    disabled = AuthService(factory, flows, google, login_enabled=False)
    for call in (
        disabled.begin_google_login('/'),
        disabled.complete_google_login('x' * 43, 'y' * 43, 'code'),
    ):
        try:
            await call
        except AuthError as error:
            check(error.code == 'login_disabled')
        else:
            raise AssertionError('disabled_login_admitted')
    check(flows.puts == flows.consumes == google.calls == 0)
    groups[phase] = True

    phase = 'preview'
    for _ in range(3):
        await seed_session()
    await seed_session(revoked=True)
    receipt = await apply(execute=False)
    check((receipt.active_before, receipt.revoked, receipt.active_after) == (3, 0, 3))
    check('mode=preview' in format_receipt(receipt))
    check(await db.fetchval('SELECT count(*) FROM user_sessions WHERE revoked_at IS NULL') == 3)
    groups[phase] = True

    phase = 'operator_guards'
    url = os.environ['DATABASE_URL']
    database = os.environ['EMERGENCY_SESSION_PROOF_PROJECT'].replace('-', '_')
    check(validate_emergency_target(
        url, expected_database=database, login_enabled=False,
        execute=False, confirmation=None) == database)
    bad = (
        dict(expected_database='other', login_enabled=False, execute=False, confirmation=None),
        dict(expected_database=database, login_enabled=True, execute=False, confirmation=None),
        dict(expected_database=database, login_enabled=False, execute=True, confirmation=None),
        dict(expected_database=database, login_enabled=False, execute=True, confirmation='REVOKE_ALL:other'),
    )
    for kwargs in bad:
        try:
            validate_emergency_target(url, **kwargs)
        except EmergencyRevocationError:
            check(True)
        else:
            raise AssertionError('operator_guard_bypassed')
    groups[phase] = True

    phase = 'revocation'
    existing = [await seed_session() for _ in range(4)]
    service = AuthService(factory, Flows(), Google())
    receipt = await apply('suspected_compromise')
    check(receipt.active_before == receipt.revoked == 7 and receipt.active_after == 0)
    for secret, _ in existing:
        try:
            await service.authenticate(secret)
        except AuthError as error:
            check(error.code == 'authentication_required')
        else:
            raise AssertionError('revoked_session_authenticated')
    check(await db.fetchval('SELECT count(*) FROM user_sessions WHERE revoked_at IS NULL') == 0)
    check(await db.fetchval(
        "SELECT count(*) FROM user_sessions WHERE revoke_reason='emergency_suspected_compromise'"
    ) == 7)
    groups[phase] = True

    phase = 'idempotency'
    repeated = await apply('suspected_compromise')
    check((repeated.active_before, repeated.revoked, repeated.active_after) == (0, 0, 0))
    groups[phase] = True

    phase = 'admission'
    flows, google = Flows(), Google()
    disabled = AuthService(factory, flows, google, login_enabled=False)
    for _ in range(4):
        try:
            await disabled.complete_google_login('x' * 43, 'y' * 43, 'code')
        except AuthError as error:
            check(error.code == 'login_disabled')
    check(flows.consumes == google.calls == 0)
    groups[phase] = True

    phase = 'auth_race'
    race_secret, race_id = await seed_session()
    async with factory() as revoker, revoker.begin():
        await revoker.execute(
            select(UserSession).where(UserSession.id == race_id).with_for_update()
        )
        task = asyncio.create_task(service.authenticate(race_secret))
        await asyncio.sleep(0.1)
        check(not task.done())
        await revoke_active_sessions(
            revoker, reason='credential_rotation', now=T + timedelta(hours=2), execute=True)
    try:
        await asyncio.wait_for(task, 5)
    except AuthError as error:
        check(error.code == 'authentication_required')
    else:
        raise AssertionError('race_session_authenticated')
    races += 1
    check(await db.fetchval('SELECT count(*) FROM user_sessions WHERE revoked_at IS NULL') == 0)
    groups[phase] = True

    phase = 'rollback_cleanup'
    _, rollback_id = await seed_session()
    try:
        async with factory() as session, session.begin():
            changed = await revoke_active_sessions(
                session, reason='operator_drill', now=T + timedelta(hours=3), execute=True)
            check(changed.revoked == 1)
            raise RuntimeError('synthetic_rollback')
    except RuntimeError:
        pass
    check(await db.fetchval(
        'SELECT count(*) FROM user_sessions WHERE id=$1 AND revoked_at IS NULL', rollback_id
    ) == 1)
    for _ in range(55):
        check(await db.fetchval(
            'SELECT count(*) FROM user_sessions WHERE revoked_at IS NULL'
        ) == 1)
    groups[phase] = True

    check(races >= 1)
    assert set(groups) == set(GROUPS) and all(groups.values()) and checks >= 80
    return {'groups': groups, 'races': races, 'checks': checks, 'complete': True}


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models

    global phase
    raw_url = os.environ.get('DATABASE_URL', '')
    url = make_url(raw_url)
    validate_target(
        os.environ.get('EMERGENCY_SESSION_PROOF_PROJECT', ''), url,
        os.environ.get('AI_PROVIDER', ''), os.environ.get('APP_ENV', ''),
        os.environ.get('AUTH_LOGIN_ENABLED', ''),
    )
    db = await asyncpg.connect(raw_url.replace('postgresql+asyncpg:', 'postgresql:'))
    engine = create_async_engine(raw_url, pool_size=8, max_overflow=8)
    try:
        assert await db.fetchval('SELECT current_database()') == url.database
        assert await db.fetchval('SELECT version_num FROM alembic_version') == HEAD
        for table in ('users', 'user_sessions'):
            assert await db.fetchval(f'SELECT count(*) FROM {table}') == 0
        result = await asyncio.wait_for(
            proof(db, async_sessionmaker(engine, expire_on_commit=False)), 105,
        )
        phase = 'done'
        print(json.dumps(result))
    finally:
        await engine.dispose()
        await db.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except TimeoutError:
        print('emergency_session_proof_failed:' + phase)
        sys.exit(124)
    except Exception:
        print('emergency_session_proof_failed:' + phase)
        sys.exit(1)
