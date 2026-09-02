import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def auth_module():
    assert (Path(__file__).parents[1] / 'app/auth/service.py').is_file(), 'G3 auth module missing'
    return importlib.import_module('app.auth.service')


@pytest.mark.parametrize('value', ['//evil.test', 'https://evil.test', '/\\evil.test', '/%2f%2fevil.test', '/a\n', '/' + 'x' * 513])
def test_return_path_refuses_unsafe_input(value):
    assert auth_module().safe_return_path(value) == '/'


def test_crypto_and_result_contract():
    m = auth_module()
    secret = m.new_secret()
    assert len(secret) == 43
    assert len(m.digest(secret)) == 32
    assert m.pkce_challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk') == 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'
    assert m.safe_return_path('/library?page=2') == '/library?page=2'
    for name in ('begin_google_login', 'complete_google_login', 'authenticate', 'logout'):
        assert callable(getattr(m.AuthService, name))


@pytest.mark.parametrize('offset,reason', [(0, None), (43200, 'inactivity_expired'), (604800, 'absolute_expired')])
def test_expiry_boundary(offset, reason):
    m = auth_module()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert m.expiry_reason(now, now + timedelta(days=7), now + timedelta(seconds=offset)) == reason


async def test_login_flow_replay_mismatch_denial_and_missing_configuration():
    from urllib.parse import urlencode, urlsplit, parse_qs
    from app.auth.flow_store import MemoryFlowStore
    m = auth_module()
    class Google:
        def authorization_url(self, state, nonce, challenge):
            return 'https://identity.test/?' + urlencode({'state': state})
        async def exchange_code(self, *args):
            raise AssertionError('invalid flows must not exchange a code')
    service = m.AuthService(None, MemoryFlowStore(), Google())
    for mode in ('mismatch', 'denial', 'missing_code'):
        start = await service.begin_google_login('/')
        state = parse_qs(urlsplit(start.location).query)['state'][0]
        with pytest.raises(m.AuthError):
            await service.complete_google_login(start.flow_secret, 'x' * 43 if mode == 'mismatch' else state,
                                                None, provider_error='access_denied' if mode == 'denial' else None)
        with pytest.raises(m.AuthError, match='oauth_flow_invalid'):
            await service.complete_google_login(start.flow_secret, state, 'code')
    with pytest.raises(m.AuthError, match='auth_not_configured'):
        await m.AuthService(None, MemoryFlowStore(), None).begin_google_login('/')
    await service.logout(None)
    with pytest.raises(m.AuthError, match='authentication_required'):
        await service.authenticate('malformed')


async def test_real_postgres_lifecycle():
    """Run only in the guarded auth verifier's fresh PostgreSQL database."""
    import asyncio
    import os
    from uuid import uuid4
    from urllib.parse import urlencode, urlsplit, parse_qs
    from sqlalchemy import select, update, event
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.identity_models import User, UserSession, UserRole, UserStatus
    from app.auth.flow_store import MemoryFlowStore
    url = os.environ.get('AUTH_TEST_DATABASE_URL')
    if not url:
        pytest.skip('requires guarded isolated Postgres verifier')
    assert urlsplit(url).hostname == '127.0.0.1' and urlsplit(url).path == '/auth_verify'
    m = auth_module()
    engine = create_async_engine(url, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    moment = [datetime.now(timezone.utc)]
    subject = 'fixture-' + uuid4().hex
    class Google:
        def authorization_url(self, state, nonce, challenge):
            return 'https://identity.test/?' + urlencode({'state': state})
        async def exchange_code(self, *args):
            return m.VerifiedIdentity(subject, 'fixture@example.test', 'Fixture')
    service = m.AuthService(factory, MemoryFlowStore(), Google(), clock=lambda: moment[0])
    async def login():
        start = await service.begin_google_login('/library')
        state = parse_qs(urlsplit(start.location).query)['state'][0]
        return await service.complete_google_login(start.flow_secret, state, 'test-only-code')
    try:
        first = await login()
        for _ in range(4):
            moment[0] += timedelta(seconds=1)
            await login()
        async with factory() as db:
            assert len((await db.execute(select(UserSession).where(UserSession.user_id == first.user.id,
                        UserSession.revoked_at.is_(None)))).scalars().all()) == 5
        moment[0] += timedelta(seconds=1)
        sixth = await login()
        with pytest.raises(m.AuthError, match='authentication_required'):
            await service.authenticate(first.session_secret)
        assert (await service.authenticate(sixth.session_secret)).id == first.user.id
        async with factory() as db:
            victim = (await db.execute(select(UserSession).where(UserSession.token_hash == m.digest(first.session_secret)))).scalar_one()
            assert victim.revoke_reason == 'session_limit_eviction'
            original_signup = (await db.get(User, first.user.id)).signed_up_at
        moment[0] += timedelta(seconds=1)
        admitted = await asyncio.gather(*[login() for _ in range(12)])
        async with factory() as db:
            live = (await db.execute(select(UserSession).where(UserSession.user_id == first.user.id,
                    UserSession.revoked_at.is_(None)))).scalars().all()
            assert len(live) == 5
            assert (await db.get(User, first.user.id)).signed_up_at == original_signup
            usable_hashes = {row.token_hash for row in live}
        chosen = next(item for item in admitted if m.digest(item.session_secret) in usable_hashes)
        touches = []
        def count_touch(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('UPDATE user_sessions SET last_seen_at='):
                touches.append(1)
        event.listen(engine.sync_engine, 'before_cursor_execute', count_touch)
        moment[0] += timedelta(seconds=299)
        await service.authenticate(chosen.session_secret)
        assert len(touches) == 0
        moment[0] += timedelta(seconds=1)
        await asyncio.gather(*[service.authenticate(chosen.session_secret) for _ in range(20)])
        assert len(touches) == 1
        await service.logout(chosen.session_secret)
        await service.logout(chosen.session_secret)
        with pytest.raises(m.AuthError, match='authentication_required'):
            await service.authenticate(chosen.session_secret)
        inactive = await login()
        moment[0] += timedelta(hours=12)
        with pytest.raises(m.AuthError, match='authentication_required'):
            await service.authenticate(inactive.session_secret)
        absolute = await login()
        moment[0] += timedelta(days=7)
        with pytest.raises(m.AuthError, match='authentication_required'):
            await service.authenticate(absolute.session_secret)
        async with factory() as db, db.begin():
            await db.execute(update(User).where(User.id == first.user.id).values(role=UserRole.MASTER))
        promoted = await login()
        assert promoted.user.role == 'master'
        async with factory() as db, db.begin():
            await db.execute(update(User).where(User.id == first.user.id).values(status=UserStatus.SUSPENDED,
                suspended_at=moment[0], updated_at=moment[0]))
        with pytest.raises(m.AuthError, match='oauth_identity_rejected'):
            await login()
        with pytest.raises(m.AuthError, match='authentication_required'):
            await service.authenticate(promoted.session_secret)
        subject = 'race-' + uuid4().hex
        new_signups = await asyncio.gather(*[login() for _ in range(8)])
        assert len({item.user.id for item in new_signups}) == 1
    finally:
        await engine.dispose()
