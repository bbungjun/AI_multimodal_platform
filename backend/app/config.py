from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Multimodal Content Platform"
    database_url: str = "postgresql+asyncpg://app:changeme@localhost:5432/multimodal"
    data_dir: Path = Path("/data/assets")
    job_runner_concurrency: int = 10
    job_runner_auto_start: bool = False
    job_dispatch_mode: str = "celery"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False
    celery_default_queue: str = "generation"
    celery_worker_concurrency: int = 2
    celery_worker_healthcheck_timeout_sec: int = 5
    celery_worker_shutdown_grace_sec: int = 60
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
    celery_worker_prefetch_multiplier: int = 1
    outbox_dispatcher_batch_size: int = 50
    outbox_dispatcher_poll_interval_sec: float = 1.0
    outbox_dispatcher_max_attempts: int = 10
    rate_limit_imagen_per_min: int = 5
    rate_limit_veo_per_min: int = 1
    rate_limit_gemini_per_min: int = 10
    provider_retry_max_attempts: int = 3
    provider_retry_base_delay_sec: float = 1.0
    provider_retry_max_delay_sec: float = 20.0
    ai_provider: str = "vertex"
    google_application_credentials: Path | None = None
    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
