"""Test-only FastAPI entry point for the isolated mock OAuth browser verifier.

The default product entry point never imports this module.  It deliberately
keeps the real auth routes, Redis flow store, PostgreSQL Session writes, and
cookie handling while replacing only the outbound Google adapter. Browser QA
may reuse this entry point, but its import guards remain the security boundary.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from redis.asyncio import Redis

from app.api.auth_dependencies import get_auth_service
from app.auth.flow_store import RedisFlowStore
from app.auth.service import AuthError, AuthService, VerifiedIdentity
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.main import app


FRONTEND_ORIGIN = "http://127.0.0.1:18156"
MOCK_CODE = "mock-e2e-code"
SECRET = re.compile(r"[A-Za-z0-9_-]{43}")


class MockGoogleIdentityAdapter:
    """Same interface as GoogleIdentityAdapter, without any network client."""

    def authorization_url(self, state: str, nonce: str, challenge: str) -> str:
        if not all(SECRET.fullmatch(value) for value in (state, nonce, challenge)):
            raise AuthError("oauth_flow_invalid")
        return "/api/auth/google/callback?" + urlencode({"state": state, "code": MOCK_CODE})

    async def exchange_code(self, code: str, verifier: str, nonce: str) -> VerifiedIdentity:
        if code != MOCK_CODE or not SECRET.fullmatch(verifier) or not SECRET.fullmatch(nonce):
            raise AuthError("oauth_identity_rejected")
        return VerifiedIdentity(
            sub="mock-oauth-browser-user",
            email="oauth-fixture@example.test",
            display_name="OAuth Fixture",
        )


settings = get_settings()
if (
    settings.app_env != "test"
    or settings.ai_provider != "mock"
    or settings.auth_frontend_origin != FRONTEND_ORIGIN
    or settings.auth_cookie_secure
    or not settings.auth_login_enabled
    or settings.auth_google_client_id
    or settings.auth_google_client_secret.get_secret_value()
    or settings.auth_google_redirect_uri
):
    raise RuntimeError("mock_oauth_test_app_refused")


async def get_mock_auth_service():
    redis = Redis.from_url(settings.auth_flow_redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        yield AuthService(
            AsyncSessionLocal,
            RedisFlowStore(redis),
            MockGoogleIdentityAdapter(),
            login_enabled=True,
        )
    finally:
        await redis.aclose()


app.dependency_overrides[get_auth_service] = get_mock_auth_service
