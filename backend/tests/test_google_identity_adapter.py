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


async def test_real_signature_verification_with_generated_test_key_and_mock_transport():
    import time
    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from google.auth import crypt, jwt
    m = google_module()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    claims = dict(iss='https://accounts.google.com', aud='client', exp=int(time.time()) + 120,
                  iat=int(time.time()), nonce='expected', sub='subject', email='fixture@example.test', email_verified=True)
    encoded = jwt.encode(crypt.RSASigner.from_string(private, key_id='test-key'), claims).decode()
    calls = []
    def handle(request):
        calls.append(request.url.path)
        if request.url.path == '/token':
            assert parse_qs(request.content.decode())['code_verifier'] == ['verifier']
            return httpx.Response(200, json={'id_token': encoded, 'access_token': 'discard-me'})
        return httpx.Response(200, json={'test-key': public})
    adapter = m.GoogleIdentityAdapter('client', 'opaque', 'https://studio.test/callback', transport=httpx.MockTransport(handle))
    identity = await adapter.exchange_code('code', 'verifier', 'expected')
    assert identity.sub == 'subject'
    assert calls == ['/token', '/oauth2/v1/certs']
    assert 'fixture' not in repr(identity)
    with pytest.raises(m.AuthError, match='oauth_identity_rejected'):
        await adapter.exchange_code('code', 'verifier', 'wrong-nonce')


@pytest.mark.parametrize('mode', ['timeout', 'redirect', '400', '500', 'malformed', 'oversized', 'missing', 'signature'])
async def test_provider_failures_are_safe(mode):
    import httpx
    m = google_module()
    def handle(request):
        if mode == 'timeout':
            raise httpx.ReadTimeout('secret-sentinel')
        if mode in ('400', '500'):
            return httpx.Response(int(mode), text='secret-sentinel')
        if mode == 'redirect':
            return httpx.Response(302, headers={'location': 'https://evil.test'})
        if mode == 'malformed':
            return httpx.Response(200, text='secret-sentinel')
        if mode == 'oversized':
            return httpx.Response(200, content=b'x' * 70000)
        return httpx.Response(200, json={'id_token': 'bad-signature'} if mode == 'signature' else {})
    adapter = m.GoogleIdentityAdapter('client', 'opaque', 'https://studio.test/callback', transport=httpx.MockTransport(handle))
    with pytest.raises(m.AuthError) as error:
        await adapter.exchange_code('code', 'verifier', 'expected')
    assert str(error.value) in ('oauth_identity_rejected', 'oauth_provider_unavailable')
    assert 'secret-sentinel' not in str(error.value)
