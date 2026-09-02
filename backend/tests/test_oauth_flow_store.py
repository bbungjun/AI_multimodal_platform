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


@pytest.mark.parametrize('payload', [b'null', b'[]', b'{}', b'x' * 9000, b'not-json'])
def test_flow_decode_rejects_malformed_values(payload):
    assert flow_module().decode_flow(payload) is None
