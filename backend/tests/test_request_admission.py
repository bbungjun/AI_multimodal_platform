import asyncio

import pytest

from app.request_admission import RequestAdmission


async def invoke(app, path='/api/generations'):
    messages = []
    async def send(message):
        messages.append(message)
    async def receive():
        return {'type': 'http.request', 'body': b''}
    await app({'type': 'http', 'path': path, 'method': 'POST'}, receive, send)
    return messages


async def test_burst_queues_before_product_entry_and_refuses_only_overflow():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def product(scope, receive, send):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        await send({'type': 'http.response.start', 'status': 201})
    app = RequestAdmission(product, concurrency=1, max_waiters=1, wait_seconds=2)
    first = asyncio.create_task(invoke(app))
    await entered.wait()
    second = asyncio.create_task(invoke(app))
    await asyncio.sleep(0)
    rejected = await invoke(app)
    assert rejected[0]['status'] == 503
    assert (b'retry-after', b'1') in rejected[0]['headers']
    assert calls == 1  # overflow and waiter have not run auth/DB/product code
    release.set()
    assert (await first)[0]['status'] == (await second)[0]['status'] == 201
    assert calls == 2 and app.outstanding == 0


async def test_wait_timeout_cancellation_and_product_failure_do_not_leak_slots():
    entered, release = asyncio.Event(), asyncio.Event()
    async def product(scope, receive, send):
        entered.set()
        await release.wait()
        raise RuntimeError('product_failure')
    app = RequestAdmission(product, concurrency=1, max_waiters=2, wait_seconds=.02)
    first = asyncio.create_task(invoke(app))
    await entered.wait()
    cancelled = asyncio.create_task(invoke(app))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert (await invoke(app))[0]['status'] == 503
    assert app.outstanding == 1
    release.set()
    with pytest.raises(RuntimeError):
        await first
    assert app.outstanding == 0
    with pytest.raises(RuntimeError):
        await invoke(app)
    assert app.outstanding == 0


async def test_health_probe_is_not_queued_behind_generation():
    entered, release = asyncio.Event(), asyncio.Event()
    async def product(scope, receive, send):
        if scope['path'] != '/api/health':
            entered.set()
            await release.wait()
        await send({'type': 'http.response.start', 'status': 200})
    app = RequestAdmission(product, concurrency=1, max_waiters=0, wait_seconds=1)
    blocked = asyncio.create_task(invoke(app))
    await entered.wait()
    assert (await invoke(app, '/api/health'))[0]['status'] == 200
    release.set()
    await blocked
