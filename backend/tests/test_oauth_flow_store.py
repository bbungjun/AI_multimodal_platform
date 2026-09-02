import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def flow_module():
    assert (Path(__file__).parents[1] / 'app/auth/flow_store.py').is_file(), 'G3 flow store missing'
    return importlib.import_module('app.auth.flow_store')


async def test_flow_is_consumed_once_and_expires():
    m = flow_module()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = m.MemoryFlowStore()
    flow = m.OAuthFlow(b'x' * 32, 'n' * 43, 'v' * 43, '/', now)
    await store.put(b'f' * 32, flow)
    results = await asyncio.gather(*[store.consume(b'f' * 32, now) for _ in range(8)])
    assert sum(item is not None for item in results) == 1
    await store.put(b'f' * 32, flow)
    assert await store.consume(b'f' * 32, now + timedelta(seconds=600)) is None
    assert 'n' * 43 not in repr(flow)


@pytest.mark.parametrize('payload', [b'null', b'[]', b'{}', b'x' * 9000, b'not-json', b'[' * 2000 + b']' * 2000], ids=['null', 'list', 'empty', 'oversized', 'invalid', 'nested'])
def test_flow_decode_rejects_malformed_values(payload):
    assert flow_module().decode_flow(payload) is None


async def test_redis_contract_ttl_digest_key_atomic_consume_and_outage():
    from unittest.mock import AsyncMock
    from redis.exceptions import ConnectionError
    m = flow_module()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    flow = m.OAuthFlow(b'x' * 32, 'n' * 43, 'v' * 43, '/', now)
    client = AsyncMock()
    store = m.RedisFlowStore(client)
    await store.put(b'f' * 32, flow)
    args, kwargs = client.set.call_args
    assert args[0] == 'creativeops:oauth:flow:' + (b'f' * 32).hex()
    assert kwargs == {'ex': 600, 'nx': True}
    client.getdel.return_value = m.encode_flow(flow)
    assert await store.consume(b'f' * 32, now) == flow
    client.getdel.assert_awaited_once()
    client.getdel.side_effect = ConnectionError('sensitive sentinel')
    with pytest.raises(m.AuthError) as error:
        await store.consume(b'f' * 32, now)
    assert str(error.value) == 'oauth_provider_unavailable'
    client.set.side_effect = ConnectionError('sensitive sentinel')
    with pytest.raises(m.AuthError, match='oauth_provider_unavailable'):
        await store.put(b'f' * 32, flow)


async def test_real_redis_flow_and_outage():
    import os
    from urllib.parse import urlsplit
    from redis.asyncio import Redis
    from app.auth.service import new_secret, digest
    url = os.environ.get('AUTH_TEST_REDIS_URL')
    if not url:
        pytest.skip('requires guarded isolated Redis verifier')
    assert urlsplit(url).hostname == '127.0.0.1' and urlsplit(url).path == '/1'
    m = flow_module()
    client = Redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2)
    store = m.RedisFlowStore(client)
    key = digest(new_secret())
    now = datetime.now(timezone.utc)
    flow = m.OAuthFlow(digest(new_secret()), new_secret(), new_secret(), '/', now)
    try:
        if os.environ.get('AUTH_TEST_REDIS_DOWN') == '1':
            with pytest.raises(m.AuthError, match='oauth_provider_unavailable'):
                await store.put(key, flow)
            with pytest.raises(m.AuthError, match='oauth_provider_unavailable'):
                await store.consume(key, now)
            return
        await store.put(key, flow)
        assert 590 <= await client.ttl(store.key(key)) <= 600
        results = await asyncio.gather(*[store.consume(key, now) for _ in range(12)])
        assert sum(item is not None for item in results) == 1
        assert await store.consume(key, now) is None
        await store.put(key, flow)
        assert await store.consume(key, now + timedelta(seconds=600)) is None
        if os.environ.get('AUTH_TEST_FLOW_METRICS_PATH'):
            import json
            Path(os.environ['AUTH_TEST_FLOW_METRICS_PATH']).write_text(json.dumps({
                'flow_consume_requests': 12, 'flow_consumed': 1,
                'flow_replay_refusals': 12, 'expired_flow_refusals': 1}))
    finally:
        await client.aclose()
