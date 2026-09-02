from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from google.auth import jwt

from app.auth.service import AuthError, VerifiedIdentity

AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
CERTS_URL = 'https://www.googleapis.com/oauth2/v1/certs'
MAX_RESPONSE_BYTES = 65536


def identity_from_claims(claims: dict, client_id: str, nonce: str, now: float) -> VerifiedIdentity:
    try:
        if (claims['iss'] not in ('accounts.google.com', 'https://accounts.google.com')
                or claims['aud'] != client_id
                or ('azp' in claims and claims['azp'] != client_id)
                or type(claims['exp']) not in (int, float) or claims['exp'] <= now
                or type(claims['iat']) not in (int, float) or claims['iat'] > now + 30
                or not isinstance(claims['nonce'], str)
                or not secrets.compare_digest(claims['nonce'].encode(), nonce.encode())
                or claims['email_verified'] is not True):
            raise ValueError
        sub, email = claims['sub'], claims['email']
        if (not isinstance(sub, str) or not 1 <= len(sub) <= 255 or not sub.isascii()
                or any(ord(c) < 33 for c in sub)
                or not isinstance(email, str) or not 3 <= len(email) <= 320
                or '@' not in email or any(ord(c) < 32 for c in email)):
            raise ValueError
        name, picture = claims.get('name'), claims.get('picture')
        if name is not None and (not isinstance(name, str) or len(name) > 200):
            raise ValueError
        if picture is not None and (not isinstance(picture, str) or len(picture) > 2048
                                    or urlsplit(picture).scheme != 'https'):
            raise ValueError
        return VerifiedIdentity(sub, email, name, picture)
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise AuthError('oauth_identity_rejected') from None


class GoogleIdentityAdapter:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str,
                 *, transport=None, timeout: float = 5.0, clock=time.time):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._transport = transport
        self._timeout = timeout
        self._clock = clock

    def authorization_url(self, state: str, nonce: str, challenge: str) -> str:
        return AUTHORIZE_URL + '?' + urlencode(dict(
            client_id=self._client_id, redirect_uri=self._redirect_uri,
            response_type='code', response_mode='query', scope='openid email profile',
            access_type='online', code_challenge_method='S256', code_challenge=challenge,
            state=state, nonce=nonce))

    async def _json(self, client, method, url, **kwargs):
        async with client.stream(method, url, **kwargs) as response:
            if response.status_code != 200:
                code = 'oauth_provider_unavailable' if response.status_code >= 500 else 'oauth_identity_rejected'
                raise AuthError(code)
            body = bytearray()
            async for part in response.aiter_bytes():
                body.extend(part)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise AuthError('oauth_identity_rejected')
            value = json.loads(body)
            if not isinstance(value, dict):
                raise AuthError('oauth_identity_rejected')
            return value

    async def exchange_code(self, code: str, verifier: str, nonce: str) -> VerifiedIdentity:
        try:
            async with asyncio.timeout(self._timeout * 2):
                async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout,
                                             follow_redirects=False, trust_env=False) as client:
                    response = await self._json(client, 'POST', TOKEN_URL, data=dict(
                        code=code, client_id=self._client_id, client_secret=self._client_secret,
                        redirect_uri=self._redirect_uri, grant_type='authorization_code',
                        code_verifier=verifier))
                    encoded = response.get('id_token')
                    response.clear()
                    if not isinstance(encoded, str) or len(encoded) > 16384:
                        raise AuthError('oauth_identity_rejected')
                    certs = await self._json(client, 'GET', CERTS_URL)
                    try:
                        claims = jwt.decode(encoded, certs=certs, audience=self._client_id)
                        return identity_from_claims(claims, self._client_id, nonce, self._clock())
                    except AuthError:
                        raise
                    except Exception:
                        raise AuthError('oauth_identity_rejected') from None
                    finally:
                        encoded = None
        except AuthError:
            raise
        except (httpx.HTTPError, TimeoutError, OSError):
            raise AuthError('oauth_provider_unavailable') from None
        except (ValueError, TypeError, UnicodeError):
            raise AuthError('oauth_identity_rejected') from None


class CallbackLogFilter(logging.Filter):
    """Remove query data from auth request targets, including HTTP client logs."""

    def filter(self, record):
        if isinstance(record.args, tuple):
            sanitized = []
            for arg in record.args:
                if isinstance(arg, (str, httpx.URL)):
                    value = str(arg)
                    if '/api/auth/' in value:
                        arg = value.split('?', 1)[0]
                sanitized.append(arg)
            record.args = tuple(sanitized)
        if isinstance(record.msg, str) and '/api/auth/' in record.msg:
            record.msg = record.msg.split('?', 1)[0]
        return True


def install_auth_log_filter():
    for name in ('uvicorn.access', 'httpx'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, CallbackLogFilter) for f in logger.filters):
            logger.addFilter(CallbackLogFilter())
