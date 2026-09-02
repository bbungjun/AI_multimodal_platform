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
