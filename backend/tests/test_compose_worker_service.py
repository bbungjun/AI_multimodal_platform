from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
VERTEX_COMPOSE_PATH = REPO_ROOT / "docker-compose.vertex.yml"


def _compose_text() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def _service_block(compose_text: str, service_name: str) -> str:
    marker = f"\n  {service_name}:\n"
    start = compose_text.find(marker)
    assert start != -1, f"Expected compose service {service_name!r}."
    block_start = start + 1
    tail = compose_text[block_start + len(marker) - 1 :]
    next_service = re.search(r"\n  [A-Za-z0-9_-]+:\n", tail)
    if next_service is None:
        return compose_text[block_start:]
    return compose_text[block_start : block_start + len(marker) - 1 + next_service.start()]


def _environment_line(service_block: str, key: str) -> str:
    prefix = f"{key}:"
    for line in service_block.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped
    raise AssertionError(f"Expected environment key {key!r} in service block.")


def test_compose_defines_redis_for_celery_broker():
    compose_text = _compose_text()

    assert "\n  worker:\n" in compose_text
    assert "\n  dispatcher:\n" in compose_text
    assert "\n  redis:\n" in compose_text
    assert "image: redis:7-alpine" in _service_block(compose_text, "redis")

    worker_block = _service_block(compose_text, "worker")
    assert "command: celery -A app.celery_app worker" in worker_block
    assert "--hostname=worker@%h" in worker_block
    assert "--queues=${CELERY_DEFAULT_QUEUE:-generation}" in worker_block
    assert "--concurrency=${CELERY_WORKER_CONCURRENCY:-2}" in worker_block
    assert "python -m app.worker" not in worker_block
    assert "stop_signal: SIGTERM" in worker_block
    assert "stop_grace_period: ${CELERY_WORKER_SHUTDOWN_GRACE_SEC:-60}s" in worker_block


def test_worker_uses_backend_image_env_asset_volume_and_broker():
    compose_text = _compose_text()
    backend_block = _service_block(compose_text, "backend")
    worker_block = _service_block(compose_text, "worker")

    assert "build: ./backend" in backend_block
    assert "build: ./backend" in worker_block
    assert "- assets:/data/assets" in backend_block
    assert "- assets:/data/assets" in worker_block

    shared_env_keys = [
        "DATABASE_URL",
        "AI_PROVIDER",
        "DATA_DIR",
        "JOB_RUNNER_CONCURRENCY",
        "JOB_RUNNER_AUTO_START",
        "JOB_DISPATCH_MODE",
        "CELERY_BROKER_URL",
        "CELERY_DEFAULT_QUEUE",
        "RATE_LIMIT_IMAGEN_PER_MIN",
        "RATE_LIMIT_VEO_PER_MIN",
        "RATE_LIMIT_GEMINI_PER_MIN",
        "PROVIDER_RETRY_MAX_ATTEMPTS",
        "PROVIDER_RETRY_BASE_DELAY_SEC",
        "PROVIDER_RETRY_MAX_DELAY_SEC",
    ]
    for key in shared_env_keys:
        assert _environment_line(worker_block, key) == _environment_line(backend_block, key)

    assert _environment_line(backend_block, "JOB_RUNNER_AUTO_START") == (
        'JOB_RUNNER_AUTO_START: "false"'
    )
    assert _environment_line(backend_block, "JOB_DISPATCH_MODE") == (
        "JOB_DISPATCH_MODE: ${JOB_DISPATCH_MODE:-celery}"
    )
    assert _environment_line(backend_block, "CELERY_BROKER_URL") == (
        "CELERY_BROKER_URL: ${CELERY_BROKER_URL:-redis://redis:6379/0}"
    )
    assert _environment_line(backend_block, "CELERY_DEFAULT_QUEUE") == (
        "CELERY_DEFAULT_QUEUE: ${CELERY_DEFAULT_QUEUE:-generation}"
    )
    assert _environment_line(backend_block, "RATE_LIMIT_IMAGEN_PER_MIN") == (
        "RATE_LIMIT_IMAGEN_PER_MIN: ${RATE_LIMIT_IMAGEN_PER_MIN:-5}"
    )
    assert _environment_line(backend_block, "RATE_LIMIT_VEO_PER_MIN") == (
        "RATE_LIMIT_VEO_PER_MIN: ${RATE_LIMIT_VEO_PER_MIN:-1}"
    )
    assert _environment_line(backend_block, "RATE_LIMIT_GEMINI_PER_MIN") == (
        "RATE_LIMIT_GEMINI_PER_MIN: ${RATE_LIMIT_GEMINI_PER_MIN:-10}"
    )
    assert _environment_line(backend_block, "PROVIDER_RETRY_MAX_ATTEMPTS") == (
        "PROVIDER_RETRY_MAX_ATTEMPTS: ${PROVIDER_RETRY_MAX_ATTEMPTS:-3}"
    )
    assert _environment_line(backend_block, "PROVIDER_RETRY_BASE_DELAY_SEC") == (
        "PROVIDER_RETRY_BASE_DELAY_SEC: ${PROVIDER_RETRY_BASE_DELAY_SEC:-1.0}"
    )
    assert _environment_line(backend_block, "PROVIDER_RETRY_MAX_DELAY_SEC") == (
        "PROVIDER_RETRY_MAX_DELAY_SEC: ${PROVIDER_RETRY_MAX_DELAY_SEC:-20.0}"
    )


def test_dispatcher_uses_backend_image_and_outbox_runtime_env():
    compose_text = _compose_text()
    backend_block = _service_block(compose_text, "backend")
    dispatcher_block = _service_block(compose_text, "dispatcher")

    assert "build: ./backend" in dispatcher_block
    assert "condition: service_healthy" in dispatcher_block
    assert "command: python -m app.services.jobs.outbox_dispatcher" in dispatcher_block
    assert "- ./backend/app:/app/app" in dispatcher_block

    shared_env_keys = [
        "DATABASE_URL",
        "AI_PROVIDER",
        "JOB_DISPATCH_MODE",
        "CELERY_BROKER_URL",
        "CELERY_DEFAULT_QUEUE",
    ]
    for key in shared_env_keys:
        assert _environment_line(dispatcher_block, key) == _environment_line(
            backend_block,
            key,
        )

    assert _environment_line(dispatcher_block, "OUTBOX_DISPATCHER_BATCH_SIZE") == (
        "OUTBOX_DISPATCHER_BATCH_SIZE: ${OUTBOX_DISPATCHER_BATCH_SIZE:-50}"
    )
    assert _environment_line(dispatcher_block, "OUTBOX_DISPATCHER_POLL_INTERVAL_SEC") == (
        "OUTBOX_DISPATCHER_POLL_INTERVAL_SEC: ${OUTBOX_DISPATCHER_POLL_INTERVAL_SEC:-1.0}"
    )
    assert _environment_line(dispatcher_block, "OUTBOX_DISPATCHER_MAX_ATTEMPTS") == (
        "OUTBOX_DISPATCHER_MAX_ATTEMPTS: ${OUTBOX_DISPATCHER_MAX_ATTEMPTS:-10}"
    )


def test_worker_has_celery_healthcheck_and_operational_env():
    compose_text = _compose_text()
    worker_block = _service_block(compose_text, "worker")

    assert "healthcheck:" in worker_block
    assert "celery -A app.celery_app inspect ping" in worker_block
    assert "--destination worker@$$HOSTNAME" in worker_block
    assert "--timeout=$${CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC:-5}" in worker_block
    assert "grep -q OK" in worker_block
    assert _environment_line(worker_block, "CELERY_WORKER_CONCURRENCY") == (
        "CELERY_WORKER_CONCURRENCY: ${CELERY_WORKER_CONCURRENCY:-2}"
    )
    assert _environment_line(worker_block, "CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC") == (
        "CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC: ${CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC:-5}"
    )


def test_no_celery_result_backend_source_of_truth():
    compose_text = _compose_text()
    backend_block = _service_block(compose_text, "backend")
    worker_block = _service_block(compose_text, "worker")

    assert "CELERY_RESULT_BACKEND" not in backend_block
    assert "CELERY_RESULT_BACKEND" not in worker_block


def test_vertex_compose_mounts_credentials_for_worker_and_backend():
    compose_text = VERTEX_COMPOSE_PATH.read_text(encoding="utf-8")

    backend_block = _service_block(compose_text, "backend")
    worker_block = _service_block(compose_text, "worker")

    credential_mount = (
        "${GOOGLE_APPLICATION_CREDENTIALS_HOST:?Set GOOGLE_APPLICATION_CREDENTIALS_HOST "
        "to the host credential JSON path}:${GOOGLE_APPLICATION_CREDENTIALS:?Set "
        "GOOGLE_APPLICATION_CREDENTIALS to the container credential JSON path}:ro"
    )
    assert credential_mount in backend_block
    assert credential_mount in worker_block
