from __future__ import annotations

from celery import Celery

from app.config import get_settings
from app.worker import validate_worker_environment


settings = get_settings()
validate_worker_environment(settings)

celery_app = Celery(
    "multimodal.jobs",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.services.jobs.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_default_queue=settings.celery_default_queue,
    task_ignore_result=True,
    task_acks_late=settings.celery_task_acks_late,
    task_reject_on_worker_lost=settings.celery_task_reject_on_worker_lost,
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    task_serializer="json",
    result_serializer="json",
    accept_content=("json",),
)
