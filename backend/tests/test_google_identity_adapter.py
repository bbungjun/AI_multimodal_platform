import importlib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


def google_module():
    assert (Path(__file__).parents[1] / 'app/auth/google.py').is_file(), 'G3 Google adapter missing'
    return importlib.import_module('app.auth.google')


def test_authorization_contract():
    m = google_module()
    adapter = m.GoogleIdentityAdapter('client', 'opaque', 'https://studio.test/api/auth/google/callback')
    query = parse_qs(urlsplit(adapter.authorization_url('state', 'nonce', 'challenge')).query)
    assert query['scope'] == ['openid email profile']
    assert query['access_type'] == ['online']
    assert query['code_challenge_method'] == ['S256']
    assert query['response_type'] == ['code']


@pytest.mark.parametrize('field,value', [('iss', 'evil'), ('aud', 'other'), ('exp', 0), ('nonce', 'wrong'), ('sub', ''), ('email_verified', False), ('email', None)])
def test_rejects_invalid_identity_claims(field, value):
    m = google_module()
    claims = dict(iss='https://accounts.google.com', aud='client', exp=2000, iat=900,
                  nonce='expected', sub='subject', email='fixture@example.test', email_verified=True)
    claims[field] = value
    with pytest.raises(m.AuthError, match='oauth_identity_rejected'):
        m.identity_from_claims(claims, 'client', 'expected', 1000)
