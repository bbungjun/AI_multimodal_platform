import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.assets import router as assets_router
from app.api.files import router as files_router
from app.api.generations import router as generations_router
from app.api.health import router as health_router
from app.api.pipelines import router as pipelines_router
from app.api.prompts import router as prompts_router
from app.config import get_settings
from app.db import close_db_connection, init_db_schema
from app.services.jobs.runner import job_runner


logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_db_schema()
    runner_task = asyncio.create_task(job_runner(), name="job-runner")
    try:
        yield
    finally:
        runner_task.cancel()
        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Job runner stopped with error during shutdown: %s", exc)
        await close_db_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(generations_router)
app.include_router(pipelines_router)
app.include_router(prompts_router)
app.include_router(assets_router)
app.include_router(files_router)
