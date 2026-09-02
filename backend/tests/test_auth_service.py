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
