from __future__ import annotations

import base64
import hashlib
import secrets
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.identity_models import User, UserSession, UserOrigin, UserRole, UserStatus


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
    """One transactional interface for OAuth and server-managed Sessions."""

    def __init__(self, session_factory, flow_store, google, *, clock=utc_now, secret_factory=new_secret):
        self._sessions = session_factory
        self._flows = flow_store
        self._google = google
        self._clock = clock
        self._secret = secret_factory

    @staticmethod
    def _valid_secret(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{43}', value) is not None

    @staticmethod
    def _principal(user):
        return AuthenticatedUser(user.id, user.role.value, user.status.value,
                                 user.email, user.display_name, user.profile_image_url)

    async def begin_google_login(self, return_to: str) -> LoginStart:
        from app.auth.flow_store import OAuthFlow
        if self._google is None:
            raise AuthError('auth_not_configured')
        now = self._clock()
        flow_secret, state, nonce, verifier = (self._secret() for _ in range(4))
        flow = OAuthFlow(digest(state), nonce, verifier, safe_return_path(return_to), now)
        await self._flows.put(digest(flow_secret), flow)
        return LoginStart(self._google.authorization_url(state, nonce, pkce_challenge(verifier)), flow_secret)

    async def complete_google_login(self, flow_secret: str, state: str, code: str | None,
                                    *, provider_error: str | None = None) -> LoginCompletion:
        now = self._clock()
        if not self._valid_secret(flow_secret):
            raise AuthError('oauth_flow_invalid')
        flow = await self._flows.consume(digest(flow_secret), now)
        if (flow is None or not self._valid_secret(state)
                or not secrets.compare_digest(flow.state_digest, digest(state))):
            raise AuthError('oauth_flow_invalid')
        if provider_error is not None:
            raise AuthError('oauth_denied' if provider_error == 'access_denied' else 'oauth_flow_invalid')
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise AuthError('oauth_flow_invalid')
        if self._google is None:
            raise AuthError('auth_not_configured')
        identity = await self._google.exchange_code(code, flow.verifier, flow.nonce)
        try:
            async with self._sessions() as db, db.begin():
                await db.execute(insert(User).values(
                    id=uuid4(), google_sub=identity.sub, email=identity.email, email_verified=True,
                    display_name=identity.display_name, profile_image_url=identity.picture,
                    role=UserRole.USER, status=UserStatus.ACTIVE, data_origin=UserOrigin.OAUTH,
                    signed_up_at=now, updated_at=now).on_conflict_do_nothing(index_elements=['google_sub']))
                user = (await db.execute(select(User).where(User.google_sub == identity.sub).with_for_update())).scalar_one()
                if user.status != UserStatus.ACTIVE or user.data_origin != UserOrigin.OAUTH:
                    raise AuthError('oauth_identity_rejected')
                now = max(now, user.signed_up_at, user.updated_at)
                user.email, user.email_verified = identity.email, True
                user.display_name, user.profile_image_url = identity.display_name, identity.picture
                user.updated_at = now
                sessions = (await db.execute(select(UserSession).where(
                    UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
                ).order_by(UserSession.created_at, UserSession.id).with_for_update())).scalars().all()
                active = []
                for session in sessions:
                    reason = expiry_reason(session.last_seen_at, session.absolute_expires_at, now)
                    if reason:
                        session.revoked_at, session.revoke_reason = now, reason
                    else:
                        active.append(session)
                while len(active) >= 5:
                    victim = active.pop(0)
                    victim.revoked_at, victim.revoke_reason = max(now, victim.created_at), 'session_limit_eviction'
                secret = self._secret()
                db.add(UserSession(id=uuid4(), user_id=user.id, token_hash=digest(secret),
                                   created_at=now, last_seen_at=now, absolute_expires_at=now + timedelta(days=7)))
                principal = self._principal(user)
            return LoginCompletion(principal, secret, flow.return_to)
        except SQLAlchemyError:
            raise AuthError('oauth_provider_unavailable') from None

    async def _locked_session(self, db, token_hash):
        user_id = (await db.execute(select(UserSession.user_id).where(UserSession.token_hash == token_hash))).scalar_one_or_none()
        if user_id is None:
            return None, None
        user = (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
        session = (await db.execute(select(UserSession).where(UserSession.token_hash == token_hash).with_for_update())).scalar_one_or_none()
        return user, session

    async def authenticate(self, session_secret: str) -> AuthenticatedUser:
        if not self._valid_secret(session_secret):
            raise AuthError('authentication_required')
        now, principal = self._clock(), None
        try:
            async with self._sessions() as db, db.begin():
                user, session = await self._locked_session(db, digest(session_secret))
                if user is not None and session is not None and session.revoked_at is None:
                    reason = expiry_reason(session.last_seen_at, session.absolute_expires_at, now)
                    if user.status != UserStatus.ACTIVE or user.data_origin != UserOrigin.OAUTH:
                        reason = 'user_suspended'
                    if reason:
                        session.revoked_at, session.revoke_reason = max(now, session.created_at), reason
                    else:
                        if session.last_seen_at <= now - timedelta(minutes=5):
                            await db.execute(update(UserSession).where(
                                UserSession.id == session.id,
                                UserSession.last_seen_at == session.last_seen_at,
                                UserSession.revoked_at.is_(None),
                            ).values(last_seen_at=now))
                        principal = self._principal(user)
        except SQLAlchemyError:
            raise AuthError('oauth_provider_unavailable') from None
        if principal is None:
            raise AuthError('authentication_required')
        return principal

    async def logout(self, session_secret: str | None) -> None:
        if not self._valid_secret(session_secret):
            return
        now = self._clock()
        try:
            async with self._sessions() as db, db.begin():
                _, session = await self._locked_session(db, digest(session_secret))
                if session is not None and session.revoked_at is None:
                    session.revoked_at, session.revoke_reason = max(now, session.created_at), 'user_logout'
        except SQLAlchemyError:
            raise AuthError('oauth_provider_unavailable') from None
