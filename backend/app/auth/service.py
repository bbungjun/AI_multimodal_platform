from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit
from uuid import UUID


class AuthError(Exception):
    """Only bounded public codes may cross the authentication interface."""

    CODES = {'auth_not_configured', 'oauth_flow_invalid', 'oauth_denied',
             'oauth_provider_unavailable', 'oauth_identity_rejected',
             'authentication_required', 'origin_not_allowed'}

    def __init__(self, code: str):
        self.code = code if code in self.CODES else 'authentication_required'
        super().__init__(self.code)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode('utf-8')).digest()


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(digest(verifier)).rstrip(b'=').decode('ascii')


def safe_return_path(value: str) -> str:
    if not isinstance(value, str) or len(value.encode('utf-8')) > 512:
        return '/'
    decoded = value
    for _ in range(4):
        if (not decoded.startswith('/') or decoded.startswith('//') or '\\' in decoded
                or any(ord(c) < 32 or ord(c) == 127 for c in decoded)):
            return '/'
        try:
            parts = urlsplit(decoded)
        except ValueError:
            return '/'
        if parts.scheme or parts.netloc:
            return '/'
        next_value = unquote(decoded)
        if next_value == decoded:
            return value
        decoded = next_value
    return '/'


def expiry_reason(last_seen: datetime, expires: datetime, now: datetime) -> str | None:
    if now >= expires:
        return 'absolute_expired'
    if now >= last_seen + timedelta(hours=12):
        return 'inactivity_expired'
    return None


@dataclass(frozen=True, repr=False)
class VerifiedIdentity:
    sub: str
    email: str
    display_name: str | None = None
    picture: str | None = None


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    role: str
    status: str
    email: str = field(repr=False)
    display_name: str | None = field(default=None, repr=False)
    picture: str | None = field(default=None, repr=False)


@dataclass(frozen=True, repr=False)
class LoginStart:
    location: str
    flow_secret: str


@dataclass(frozen=True, repr=False)
class LoginCompletion:
    user: AuthenticatedUser
    session_secret: str
    return_to: str


class AuthService:
    """Lifecycle implementation follows after flow/provider contracts pass."""

    async def begin_google_login(self, return_to: str) -> LoginStart:
        raise NotImplementedError

    async def complete_google_login(self, flow_secret: str, state: str, code: str) -> LoginCompletion:
        raise NotImplementedError

    async def authenticate(self, session_secret: str) -> AuthenticatedUser:
        raise NotImplementedError

    async def logout(self, session_secret: str | None) -> None:
        raise NotImplementedError
