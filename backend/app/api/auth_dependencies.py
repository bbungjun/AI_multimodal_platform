from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis

from app.auth.flow_store import RedisFlowStore
from app.auth.google import GoogleIdentityAdapter
from app.auth.service import AuthError, AuthService
from app.config import get_settings
from app.db import AsyncSessionLocal


async def get_auth_service():
    settings = get_settings()
    redis = Redis.from_url(settings.auth_flow_redis_url, socket_connect_timeout=2, socket_timeout=2)
    google = None
    if (settings.auth_google_client_id and settings.auth_google_client_secret.get_secret_value()
            and settings.auth_google_redirect_uri):
        google = GoogleIdentityAdapter(settings.auth_google_client_id,
            settings.auth_google_client_secret.get_secret_value(), settings.auth_google_redirect_uri,
            timeout=settings.auth_provider_timeout_sec)
    try:
        yield AuthService(AsyncSessionLocal, RedisFlowStore(redis), google)
    finally:
        await redis.aclose()


def require_trusted_origin(request: Request):
    settings = get_settings()
    trusted = {settings.auth_frontend_origin.rstrip('/'), *settings.cors_origins}
    if request.headers.get('origin') not in trusted:
        raise HTTPException(403, detail='origin_not_allowed')


async def require_user(request: Request, service=Depends(get_auth_service)):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        require_trusted_origin(request)
    try:
        return await service.authenticate(request.cookies.get('creativeops_session', ''))
    except AuthError as error:
        status = 503 if error.code == 'oauth_provider_unavailable' else 401
        raise HTTPException(status, detail=error.code) from None


async def require_master(actor=Depends(require_user)):
    if actor.role != 'master':
        raise HTTPException(403, detail='master_required')
    return actor
