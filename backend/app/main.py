import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.assets import router as assets_router
from app.api.auth import router as auth_router
from app.auth.google import install_auth_log_filter
from app.api.files import router as files_router
from app.api.generations import router as generations_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.ops import router as ops_router
from app.api.pipelines import router as pipelines_router
from app.api.prompts import router as prompts_router
from app.config import get_settings
from app.db import close_db_connection
from app.schema_control import require_current_schema
from app.services.jobs.runner import job_runner
from app.services.ops.runtime import runtime_metrics


logger = logging.getLogger(__name__)
settings = get_settings()
install_auth_log_filter()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await require_current_schema()
    runner_task = None
    if settings.job_runner_auto_start:
        runner_task = asyncio.create_task(job_runner(), name="job-runner")
    try:
        yield
    finally:
        if runner_task is not None:
            runner_task.cancel()
            try:
                await runner_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Job runner stopped with error during shutdown: %s", exc)
        await close_db_connection()


class PrivateContentResponses:
    """Only intercept response-start; keep streaming and exception propagation intact."""

    prefixes = ("/api/generations", "/api/pipelines", "/api/assets", "/api/prompts", "/files", "/api/ops")

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        protected = scope["type"] == "http" and (path in ("/metrics", "/metrics/") or any(
            path == prefix or path.startswith(prefix + "/") for prefix in self.prefixes
        ))

        async def send_private(message):
            if protected and message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", [])
                           if key.lower() != b"cache-control"]
                message = {**message, "headers": [*headers, (b"cache-control", b"private, no-store")]}
            await send(message)

        await self.application(scope, receive, send_private)


class ContentApplication(FastAPI):
    def build_middleware_stack(self):
        # Outside ServerErrorMiddleware so even unhandled500 cannot be cached.
        return PrivateContentResponses(super().build_middleware_stack())


app = ContentApplication(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def record_runtime_metrics(request: Request, call_next):
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        runtime_metrics.record_http_request(
            method=request.method,
            path=runtime_metrics.path_for_request(request),
            status_code=status_code,
            duration_ms=(perf_counter() - started) * 1000,
        )


app.include_router(health_router, prefix="/api")
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(ops_router)
app.include_router(generations_router)
app.include_router(pipelines_router)
app.include_router(prompts_router)
app.include_router(assets_router)
app.include_router(files_router)
