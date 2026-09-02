import importlib
import logging
from pathlib import Path

import pytest


def api_module():
    assert (Path(__file__).parents[1] / 'app/api/auth.py').is_file(), 'G3 auth HTTP module missing'
    return importlib.import_module('app.api.auth')


def test_routes_and_cookie_contract():
    m = api_module()
    assert {route.path for route in m.router.routes} == {
        '/api/auth/google/start', '/api/auth/google/callback', '/api/auth/me', '/api/auth/logout'}
    assert m.SESSION_COOKIE == 'creativeops_session'
    assert m.FLOW_COOKIE == 'creativeops_oauth_flow'


def test_callback_access_log_is_sanitized():
    assert (Path(__file__).parents[1] / 'app/auth/google.py').is_file(), 'G3 access-log sanitizer missing'
    m = importlib.import_module('app.auth.google')
    record = logging.LogRecord('uvicorn.access', 20, '', 0, '%s %s %s %s %s',
                              ('client', 'GET', '/api/auth/google/callback?code=sentinel&state=sentinel', '1.1', 303), None)
    assert m.CallbackLogFilter().filter(record)
    assert 'sentinel' not in record.getMessage()


def test_http_cookie_profile_logout_and_safe_callback_errors(monkeypatch):
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth_dependencies as deps
    from app.auth.service import AuthenticatedUser, LoginStart, LoginCompletion, AuthError
    from app.config import Settings
    m = api_module()
    settings = Settings(_env_file=None, ai_provider='mock', auth_frontend_origin='https://studio.test',
                        cors_origins=['https://studio.test'])
    monkeypatch.setattr(m, 'get_settings', lambda: settings)
    monkeypatch.setattr(deps, 'get_settings', lambda: settings)
    principal = AuthenticatedUser(uuid4(), 'user', 'active', 'fixture@example.test')
    class Service:
        fail = False
        async def begin_google_login(self, path):
            return LoginStart('https://identity.test/authorize', 'f' * 43)
        async def complete_google_login(self, *args, **kwargs):
            if self.fail:
                raise AuthError('oauth_flow_invalid')
            return LoginCompletion(principal, 's' * 43, '/library')
        async def authenticate(self, secret):
            if secret != 's' * 43:
                raise AuthError('authentication_required')
            return principal
        async def logout(self, secret):
            pass
    service = Service()
    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[deps.get_auth_service] = lambda: service
    with TestClient(app, base_url='https://studio.test', follow_redirects=False) as client:
        assert client.get('/api/auth/me').status_code == 401
        start = client.get('/api/auth/google/start')
        assert start.status_code == 307
        flow_cookie = start.headers['set-cookie']
        assert 'HttpOnly' in flow_cookie and 'Secure' in flow_cookie and 'SameSite=lax' in flow_cookie
        assert 'Max-Age=600' in flow_cookie and 'Path=/api/auth/google/callback' in flow_cookie
        done = client.get('/api/auth/google/callback?code=sentinel&state=sentinel')
        assert done.status_code == 303 and done.headers['location'] == 'https://studio.test/library'
        assert done.headers['cache-control'] == 'no-store' and done.headers['referrer-policy'] == 'no-referrer'
        cookies = done.headers.get_list('set-cookie')
        assert any('Max-Age=604800' in value and 'HttpOnly' in value and 'Secure' in value for value in cookies)
        profile = client.get('/api/auth/me')
        assert profile.status_code == 200 and profile.json()['id'] == str(principal.id)
        assert not {'session_secret', 'token_hash', 'session_id'} & profile.json().keys()
        for origin in (None, 'null', 'https://evil.test', 'http://studio.test', 'https://studio.test:444'):
            headers = {} if origin is None else {'origin': origin}
            assert client.post('/api/auth/logout', headers=headers).status_code == 403
        out = client.post('/api/auth/logout', headers={'origin': 'https://studio.test'})
        assert out.status_code == 204 and 'Max-Age=0' in out.headers['set-cookie']
        assert 'Secure' in out.headers['set-cookie'] and 'HttpOnly' in out.headers['set-cookie']
        service.fail = True
        failed = client.get('/api/auth/google/callback?code=sentinel')
        assert failed.headers['location'].endswith('/?auth_error=oauth_flow_invalid')
        assert 'sentinel' not in str(dict(failed.headers))
        assert 'Max-Age=0' in failed.headers['set-cookie']


def test_missing_oauth_configuration_and_cookie_environment_guard(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth_dependencies as deps
    from app.config import Settings
    m = api_module()
    settings = Settings(_env_file=None, ai_provider='mock', app_env='production')
    monkeypatch.setattr(deps, 'get_settings', lambda: settings)
    app = FastAPI()
    app.include_router(m.router)
    with TestClient(app, base_url='https://studio.test') as client:
        assert client.get('/api/auth/google/start').json() == {'detail': 'auth_not_configured'}
    with pytest.raises(ValueError, match='insecure auth cookies'):
        Settings(_env_file=None, app_env='production', auth_cookie_secure=False)
    assert Settings(_env_file=None, app_env='test', auth_cookie_secure=False).auth_cookie_secure is False


def test_oauth_compose_values_are_backend_only():
    import re
    text = (Path(__file__).parents[2] / 'docker-compose.yml').read_text()
    for name in ('AUTH_GOOGLE_CLIENT_ID', 'AUTH_GOOGLE_CLIENT_SECRET', 'AUTH_GOOGLE_REDIRECT_URI'):
        assert len(re.findall(r'^\s+' + name + ':', text, flags=re.MULTILINE)) == 1
        assert name + ':' in text.split('  backend:')[1].split('  worker:')[0]
    assert 'command: ["redis-server", "--save", "", "--appendonly", "no"]' in text


@pytest.mark.parametrize('code', ['auth_not_configured', 'oauth_provider_unavailable',
                                 'oauth_flow_invalid', 'oauth_denied', 'oauth_identity_rejected',
                                 'authentication_required', 'origin_not_allowed', 'untrusted-value'])
def test_opt_in_start_error_redirect_preserves_default_contract(monkeypatch, code):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth_dependencies as deps
    from app.auth.service import AuthError
    from app.config import Settings
    m = api_module()
    settings = Settings(_env_file=None, ai_provider='mock', auth_frontend_origin='https://studio.test')
    monkeypatch.setattr(m, 'get_settings', lambda: settings)

    class Service:
        async def begin_google_login(self, path):
            raise AuthError(code)

    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[deps.get_auth_service] = lambda: Service()
    expected = code if code in AuthError.CODES else 'authentication_required'
    with TestClient(app, base_url='https://hostile.test', follow_redirects=False) as client:
        for query in ('', '?ui=0', '?ui=true', '?ui=1&ui=1', '?ui=1&ui=0'):
            response = client.get('/api/auth/google/start' + query)
            assert response.status_code == 503
            assert response.json() == {'detail': expected}
        response = client.get('/api/auth/google/start?ui=1&return_to=https://hostile.test',
                              headers={'origin': 'https://hostile.test'})
        assert response.status_code == 303
        assert response.headers['location'] == 'https://studio.test/login?auth_error=' + expected
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['referrer-policy'] == 'no-referrer'
        cookie = response.headers['set-cookie']
        assert 'Max-Age=0' in cookie and 'Path=/api/auth/google/callback' in cookie
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie


@pytest.mark.parametrize('query', ['', '?ui=1'])
def test_start_success_unchanged_with_browser_opt_in(monkeypatch, query):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth_dependencies as deps
    from app.auth.service import LoginStart
    from app.config import Settings
    m = api_module()
    monkeypatch.setattr(m, 'get_settings', lambda: Settings(_env_file=None, ai_provider='mock'))
    class Service:
        calls = 0
        async def begin_google_login(self, path):
            self.calls += 1
            return LoginStart('https://identity.test/authorize', 'f' * 43)
    service = Service()
    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[deps.get_auth_service] = lambda: service
    with TestClient(app, base_url='https://studio.test', follow_redirects=False) as client:
        response = client.get('/api/auth/google/start' + query)
        assert response.status_code == 307
        assert response.headers['location'] == 'https://identity.test/authorize'
        assert response.headers['cache-control'] == 'no-store'
        assert 'Max-Age=600' in response.headers['set-cookie']
        assert service.calls == 1


async def test_real_postgres_redis_http_lifecycle(monkeypatch):
    """Full HTTP-to-storage seam, with only external identity replaced."""
    import os
    from urllib.parse import parse_qs, urlencode, urlsplit
    from uuid import uuid4
    import httpx
    from fastapi import FastAPI
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.api import auth_dependencies as deps
    from app.auth.flow_store import RedisFlowStore
    from app.auth.service import AuthService, VerifiedIdentity
    from app.config import Settings
    db_url, redis_url = os.environ.get('AUTH_TEST_DATABASE_URL'), os.environ.get('AUTH_TEST_REDIS_URL')
    if not db_url or not redis_url:
        pytest.skip('requires guarded isolated Postgres and Redis verifier')
    assert urlsplit(db_url).hostname == '127.0.0.1' and urlsplit(db_url).path == '/auth_verify'
    assert urlsplit(redis_url).hostname == '127.0.0.1' and urlsplit(redis_url).path == '/1'
    m = api_module()
    settings = Settings(_env_file=None, ai_provider='mock', app_env='test',
                        auth_frontend_origin='https://studio.test', cors_origins=['https://studio.test'])
    monkeypatch.setattr(m, 'get_settings', lambda: settings)
    monkeypatch.setattr(deps, 'get_settings', lambda: settings)
    engine = create_async_engine(db_url, hide_parameters=True)
    redis = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    subject = 'http-' + uuid4().hex
    class Google:
        def authorization_url(self, state, nonce, challenge):
            return 'https://identity.test/?' + urlencode({'state': state})
        async def exchange_code(self, *args):
            return VerifiedIdentity(subject, 'fixture@example.test')
    service = AuthService(async_sessionmaker(engine, expire_on_commit=False), RedisFlowStore(redis), Google())
    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[deps.get_auth_service] = lambda: service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='https://studio.test', follow_redirects=False) as client:
            assert (await client.get('/api/auth/me')).status_code == 401
            start = await client.get('/api/auth/google/start', params={'return_to': '/library'})
            assert start.status_code == 307
            state = parse_qs(urlsplit(start.headers['location']).query)['state'][0]
            callback = await client.get('/api/auth/google/callback', params={'state': state, 'code': 'test-only-code'})
            assert callback.status_code == 303 and callback.headers['location'] == 'https://studio.test/library'
            assert m.FLOW_COOKIE not in client.cookies and m.SESSION_COOKIE in client.cookies
            assert (await client.get('/api/auth/me')).status_code == 200
            replay = await client.get('/api/auth/google/callback', params={'state': state, 'code': 'test-only-code'})
            assert replay.headers['location'].endswith('auth_error=oauth_flow_invalid')
            assert (await client.post('/api/auth/logout')).status_code == 403
            assert (await client.get('/api/auth/me')).status_code == 200
            headers = {'origin': 'https://studio.test'}
            assert (await client.post('/api/auth/logout', headers=headers)).status_code == 204
            assert (await client.get('/api/auth/me')).json() == {'detail': 'authentication_required'}
            assert (await client.post('/api/auth/logout', headers=headers)).status_code == 204
    finally:
        await redis.aclose()
        await engine.dispose()
