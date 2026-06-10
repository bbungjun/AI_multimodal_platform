from __future__ import annotations

import importlib

from app.config import Settings


def test_dispatch_mode_defaults_are_explicit():
    settings = Settings(_env_file=None)

    assert settings.job_dispatch_mode == "celery"
    assert settings.celery_broker_url == "redis://redis:6379/0"
    assert settings.celery_result_backend is None
    assert settings.celery_task_always_eager is False
    assert settings.celery_default_queue == "generation"
    assert settings.celery_worker_concurrency == 2
    assert settings.celery_worker_healthcheck_timeout_sec == 5
    assert settings.celery_worker_shutdown_grace_sec == 60
    assert settings.celery_task_acks_late is True
    assert settings.celery_task_reject_on_worker_lost is True
    assert settings.celery_worker_prefetch_multiplier == 1
    assert settings.rate_limit_imagen_per_min == 5
    assert settings.rate_limit_veo_per_min == 1
    assert settings.rate_limit_gemini_per_min == 10
    assert settings.provider_retry_max_attempts == 3
    assert settings.provider_retry_base_delay_sec == 1.0
    assert settings.provider_retry_max_delay_sec == 20.0


def test_celery_app_names_jobs_namespace():
    from app.celery_app import celery_app

    assert celery_app.main == "multimodal.jobs"


def test_celery_config_uses_broker_without_result_backend():
    from app.celery_app import celery_app

    settings = Settings(_env_file=None)

    assert celery_app.conf.broker_url == settings.celery_broker_url
    assert celery_app.conf.result_backend is None
    assert celery_app.conf.task_ignore_result is True


def test_celery_app_uses_json_and_generation_queue():
    from app.celery_app import celery_app

    settings = Settings(_env_file=None)

    assert celery_app.conf.task_default_queue == settings.celery_default_queue
    assert celery_app.conf.worker_concurrency == settings.celery_worker_concurrency
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ("json",)


def test_celery_config_keeps_long_running_video_tasks_recoverable():
    from app.celery_app import celery_app

    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_celery_app_import_does_not_construct_vertex_client(monkeypatch):
    from app.services.vertex import imagen, veo
    import app.celery_app as celery_module

    def fail_vertex_client(*_args, **_kwargs):
        raise AssertionError("Celery app import must not construct Vertex clients")

    monkeypatch.setattr(imagen, "get_vertex_client", fail_vertex_client, raising=False)
    monkeypatch.setattr(veo, "get_vertex_client", fail_vertex_client, raising=False)

    importlib.reload(celery_module)
