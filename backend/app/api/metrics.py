from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.services.ops.prometheus import render_prometheus_metrics


router = APIRouter(tags=["ops"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(
        content=render_prometheus_metrics(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
