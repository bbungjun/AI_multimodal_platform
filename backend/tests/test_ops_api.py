from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.api import ops
from app.main import app
from app.models import JobState, OutboxEventStatus
from app.schemas import (
    OpsDispatchResponse,
    OpsHealthResponse,
    OpsJobsResponse,
    OpsOutboxResponse,
)


class FakeOpsSession:
    pass


async def test_ops_health_endpoint_returns_operational_metrics(monkeypatch):
    session = FakeOpsSession()

    async def override_session() -> AsyncIterator[FakeOpsSession]:
        yield session

    async def fake_collect_ops_health(received_session):
        assert received_session is session
        return OpsHealthResponse(
            ok=True,
            db="up",
            service="AI Multimodal Content Platform",
            dispatch=OpsDispatchResponse(
                mode="celery",
                queue="generation",
                task_acks_late=True,
                task_reject_on_worker_lost=True,
                worker_prefetch_multiplier=1,
            ),
            jobs=OpsJobsResponse(
                total=2,
                active=1,
                blocked=0,
                resumable_polling=1,
                by_state={state: 0 for state in JobState} | {JobState.POLLING: 1},
            ),
            outbox=OpsOutboxResponse(
                total=1,
                pending=1,
                published=0,
                failed=0,
                by_status={
                    status: 0 for status in OutboxEventStatus
                } | {OutboxEventStatus.PENDING: 1},
            ),
            recent_failures=[],
        )

    app.dependency_overrides[ops.get_session] = override_session
    monkeypatch.setattr(ops, "collect_ops_health", fake_collect_ops_health)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/ops/health")
    finally:
        app.dependency_overrides.pop(ops.get_session, None)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] == "up"
    assert body["dispatch"]["mode"] == "celery"
    assert body["jobs"]["resumable_polling"] == 1
    assert body["jobs"]["by_state"]["polling"] == 1
    assert body["outbox"]["pending"] == 1
