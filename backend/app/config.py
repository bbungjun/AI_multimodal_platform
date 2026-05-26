from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Multimodal Content Platform"
    database_url: str = "postgresql+asyncpg://app:changeme@localhost:5432/multimodal"
    data_dir: Path = Path("/data/assets")
    job_runner_concurrency: int = 10
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
