"""Bounded per-process HTTP admission before auth and database checkout.

This is short-lived request backpressure, not the durable generation queue.
Each process must budget its admitted requests against its database pool.
"""
import asyncio

from starlette.responses import JSONResponse


class RequestAdmission:
    def __init__(self, app, *, concurrency: int, max_waiters: int, wait_seconds: float):
        if concurrency < 1 or max_waiters < 0 or wait_seconds <= 0:
            raise ValueError('invalid_request_admission_budget')
        self.app = app
        self.slots = asyncio.Semaphore(concurrency)
        self.capacity = concurrency + max_waiters
        self.outstanding = 0
        self.wait_seconds = wait_seconds

    async def reject(self, scope, receive, send):
        response = JSONResponse({'detail': 'request_capacity_exceeded'}, status_code=503,
                                headers={'Retry-After': '1', 'Cache-Control': 'no-store'})
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope.get('method') == 'OPTIONS'
                or scope.get('path') in ('/api/health', '/metrics')):
            await self.app(scope, receive, send)
            return
        # No await between reading/updating this per-event-loop counter.
        if self.outstanding >= self.capacity:
            await self.reject(scope, receive, send)
            return
        self.outstanding += 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(self.slots.acquire(), timeout=self.wait_seconds)
                acquired = True
            except TimeoutError:
                await self.reject(scope, receive, send)
                return
            await self.app(scope, receive, send)
        finally:
            if acquired:
                self.slots.release()
            self.outstanding -= 1
