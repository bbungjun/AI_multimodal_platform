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


def test_compose_defines_worker_without_redis_or_celery():
    compose_text = _compose_text()

    assert "\n  worker:\n" in compose_text
    assert "\n  redis:\n" not in compose_text
    assert "celery" not in compose_text.lower()

    worker_block = _service_block(compose_text, "worker")
    assert "command: python -m app.worker" in worker_block
    assert "stop_grace_period: 45s" in worker_block


def test_worker_uses_backend_image_env_and_asset_volume():
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
    ]
    for key in shared_env_keys:
        assert _environment_line(worker_block, key) == _environment_line(backend_block, key)

    assert _environment_line(backend_block, "JOB_RUNNER_AUTO_START") == (
        'JOB_RUNNER_AUTO_START: "false"'
    )


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
