from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from redis.exceptions import RedisError

from app.auth.service import AuthError, safe_return_path

FLOW_TTL_SECONDS = 600
MAX_FLOW_BYTES = 4096
_SECRET = re.compile(r'^[A-Za-z0-9_-]{43}$')


@dataclass(frozen=True, repr=False)
class OAuthFlow:
    state_digest: bytes
    nonce: str
    verifier: str
    return_to: str
    created_at: datetime


class FlowStore(Protocol):
    async def put(self, key: bytes, flow: OAuthFlow) -> None: ...
    async def consume(self, key: bytes, now: datetime) -> OAuthFlow | None: ...


def encode_flow(flow: OAuthFlow) -> bytes:
    return json.dumps(dict(state_digest=flow.state_digest.hex(), nonce=flow.nonce,
                           verifier=flow.verifier, return_to=flow.return_to,
                           created_at=flow.created_at.isoformat()), separators=(',', ':')).encode()


def decode_flow(payload: bytes | str | None) -> OAuthFlow | None:
    if not payload or len(payload) > MAX_FLOW_BYTES:
        return None
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {'state_digest', 'nonce', 'verifier', 'return_to', 'created_at'}:
            return None
        state = bytes.fromhex(data['state_digest'])
        created = datetime.fromisoformat(data['created_at'])
        if (len(state) != 32 or not _SECRET.fullmatch(data['nonce'])
                or not _SECRET.fullmatch(data['verifier']) or created.tzinfo is None
                or safe_return_path(data['return_to']) != data['return_to']):
            return None
        return OAuthFlow(state, data['nonce'], data['verifier'], data['return_to'], created)
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def usable(flow: OAuthFlow | None, now: datetime) -> OAuthFlow | None:
    if flow and flow.created_at <= now < flow.created_at + timedelta(seconds=FLOW_TTL_SECONDS):
        return flow
    return None


class MemoryFlowStore:
    """Deterministic adapter for injection in tests, never selected by env."""

    def __init__(self):
        self._flows: dict[bytes, bytes] = {}

    async def put(self, key: bytes, flow: OAuthFlow) -> None:
        if key in self._flows:
            raise AuthError('oauth_flow_invalid')
        self._flows[key] = encode_flow(flow)

    async def consume(self, key: bytes, now: datetime) -> OAuthFlow | None:
        return usable(decode_flow(self._flows.pop(key, None)), now)


class RedisFlowStore:
    def __init__(self, client):
        self._client = client

    @staticmethod
    def key(key: bytes) -> str:
        if len(key) != 32:
            raise AuthError('oauth_flow_invalid')
        return 'creativeops:oauth:flow:' + key.hex()

    async def put(self, key: bytes, flow: OAuthFlow) -> None:
        try:
            saved = await self._client.set(self.key(key), encode_flow(flow), ex=FLOW_TTL_SECONDS, nx=True)
        except (RedisError, OSError):
            raise AuthError('oauth_provider_unavailable') from None
        if not saved:
            raise AuthError('oauth_flow_invalid')

    async def consume(self, key: bytes, now: datetime) -> OAuthFlow | None:
        try:
            payload = await self._client.getdel(self.key(key))
        except (RedisError, OSError):
            raise AuthError('oauth_provider_unavailable') from None
        return usable(decode_flow(payload), now)
