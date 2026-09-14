import json

import pytest

import prompt_t2i_probe


URL = "postgresql+asyncpg://user:value@db:5432/ownership_verify_0123456789ab"


def test_counts_request_accepts_only_owned_mock_test_target():
    assert prompt_t2i_probe.validate_request(
        {"operation": "counts"}, database_url=URL, provider="mock", app_env="test"
    ) == ("counts", None)
    assert prompt_t2i_probe.validate_request(
        {"operation": "latest_image_source"}, database_url=URL, provider="mock", app_env="test"
    ) == ("latest_image_source", None)


@pytest.mark.parametrize(
    ("url", "provider", "app_env"),
    [
        ("postgresql+asyncpg://user:value@external:5432/ownership_verify_0123456789ab", "mock", "test"),
        (URL, "vertex", "test"),
        (URL, "mock", "local"),
        ("postgresql+asyncpg://user:value@db:5432/product", "mock", "test"),
    ],
)
def test_foreign_or_non_mock_target_is_refused(url, provider, app_env):
    with pytest.raises(ValueError, match="prompt_t2i_probe_target_refused"):
        prompt_t2i_probe.validate_request(
            {"operation": "counts"}, database_url=url, provider=provider, app_env=app_env
        )


def test_job_request_requires_uuid_and_closed_fields():
    with pytest.raises(ValueError, match="prompt_t2i_probe_refused"):
        prompt_t2i_probe.validate_request(
            {"operation": "job", "job_id": "not-a-uuid"}, database_url=URL,
            provider="mock", app_env="test"
        )
    with pytest.raises(ValueError, match="prompt_t2i_probe_refused"):
        prompt_t2i_probe.validate_request(
            {"operation": "counts", "identity": "not-allowed"}, database_url=URL,
            provider="mock", app_env="test"
        )


def test_cli_failure_is_bounded(monkeypatch, capsys):
    monkeypatch.setattr(prompt_t2i_probe.sys, "stdin", type("Input", (), {"read": lambda self, size: "{}"})())
    assert prompt_t2i_probe.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "complete": False, "error": "prompt_t2i_probe_refused"
    }
