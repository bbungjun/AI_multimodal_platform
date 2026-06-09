from __future__ import annotations

import pytest

from app.config import Settings


def _settings(ai_provider: str) -> Settings:
    return Settings(_env_file=None, ai_provider=ai_provider)


def _validate_worker_environment():
    from app.worker import validate_worker_environment

    return validate_worker_environment


def test_worker_allows_mock_provider_without_vertex_client():
    validate_worker_environment = _validate_worker_environment()

    validate_worker_environment(_settings("mock"), environ={})


def test_worker_rejects_implicit_vertex_provider():
    validate_worker_environment = _validate_worker_environment()

    with pytest.raises(RuntimeError, match="AI_PROVIDER"):
        validate_worker_environment(_settings("vertex"), environ={})


def test_worker_allows_explicit_vertex_provider_without_touching_credentials():
    validate_worker_environment = _validate_worker_environment()

    validate_worker_environment(_settings("vertex"), environ={"AI_PROVIDER": "vertex"})


def test_worker_rejects_case_mismatched_mock_provider():
    validate_worker_environment = _validate_worker_environment()

    with pytest.raises(RuntimeError, match="AI_PROVIDER"):
        validate_worker_environment(_settings("MOCK"), environ={"AI_PROVIDER": "MOCK"})
