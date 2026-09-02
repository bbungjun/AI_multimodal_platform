from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Multimodal Content Platform"
    app_env: str = "local"
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
    google_application_credentials_json: str | None = None
    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"
    enhance_model: str = "gemini-2.5-flash"
    auth_google_client_id: str = Field(default='', repr=False)
    auth_google_client_secret: SecretStr = Field(default=SecretStr(''), repr=False)
    auth_google_redirect_uri: str = ''
    auth_frontend_origin: str = 'http://localhost:5173'
    auth_flow_redis_url: str = Field(default='redis://redis:6379/1', repr=False)
    auth_cookie_secure: bool = True
    auth_provider_timeout_sec: float = Field(default=5.0, ge=0.1, le=30.0)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode='after')
    def validate_auth_settings(self):
        local = self.app_env in ('local', 'test')
        configured = bool(self.auth_google_client_id and self.auth_google_client_secret.get_secret_value()
                          and self.auth_google_redirect_uri)
        if not self.auth_cookie_secure and not local:
            raise ValueError('insecure auth cookies require local or test environment')
        if '*' in self.cors_origins:
            raise ValueError('credentialed CORS requires exact origins')
        for value in (self.auth_frontend_origin, self.auth_google_redirect_uri):
            if not value:
                continue
            parts = urlsplit(value)
            if (parts.scheme not in ('http', 'https') or not parts.hostname
                    or parts.username or parts.password or parts.query or parts.fragment
                    or (parts.scheme != 'https' and not local and configured)):
                raise ValueError('invalid auth origin or callback configuration')
        if urlsplit(self.auth_frontend_origin).path not in ('', '/'):
            raise ValueError('auth frontend must be an origin')
        if self.auth_google_redirect_uri and urlsplit(self.auth_google_redirect_uri).path != '/api/auth/google/callback':
            raise ValueError('invalid auth callback path')
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
