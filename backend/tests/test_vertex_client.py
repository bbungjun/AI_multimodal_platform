from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.services.vertex import client as vertex_client


class FakeGenaiClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def test_vertex_client_uses_adc_when_no_credentials_file_is_configured(
    monkeypatch,
):
    fake_credentials = object()
    default_calls: list[dict[str, object]] = []

    def fake_default(*, scopes: list[str]) -> tuple[object, str]:
        default_calls.append({"scopes": scopes})
        return fake_credentials, "adc-project"

    def fail_from_file(path: str, **kwargs: object) -> object:
        raise AssertionError(f"service-account JSON should not be read: {path}")

    settings = Settings(
        google_application_credentials=None,
        gcp_project_id=None,
        gcp_location="asia-northeast3",
    )

    vertex_client.get_vertex_client.cache_clear()
    monkeypatch.setattr(vertex_client, "get_settings", lambda: settings)
    monkeypatch.setattr(vertex_client.google_auth, "default", fake_default)
    monkeypatch.setattr(
        vertex_client.service_account.Credentials,
        "from_service_account_file",
        fail_from_file,
    )
    monkeypatch.setattr(vertex_client.genai, "Client", FakeGenaiClient)

    try:
        client = vertex_client.get_vertex_client()
    finally:
        vertex_client.get_vertex_client.cache_clear()

    assert isinstance(client, FakeGenaiClient)
    assert default_calls == [{"scopes": [vertex_client.VERTEX_AUTH_SCOPE]}]
    assert client.kwargs == {
        "vertexai": True,
        "credentials": fake_credentials,
        "project": "adc-project",
        "location": "asia-northeast3",
    }


def test_vertex_client_prefers_explicit_credentials_file_when_configured(
    monkeypatch,
    tmp_path,
):
    explicit_path = tmp_path / "service-account.json"
    explicit_path.write_text("{}", encoding="utf-8")
    fake_credentials = type("FakeCredentials", (), {"project_id": "file-project"})()
    from_file_calls: list[dict[str, object]] = []

    def fail_default(*, scopes: list[str]) -> tuple[object, str]:
        raise AssertionError("ADC should not be used with an explicit file path")

    def fake_from_file(path: str, **kwargs: object) -> object:
        from_file_calls.append({"path": Path(path), **kwargs})
        return fake_credentials

    settings = Settings(
        google_application_credentials=explicit_path,
        gcp_project_id=None,
        gcp_location="us-central1",
    )

    vertex_client.get_vertex_client.cache_clear()
    monkeypatch.setattr(vertex_client, "get_settings", lambda: settings)
    monkeypatch.setattr(vertex_client.google_auth, "default", fail_default)
    monkeypatch.setattr(
        vertex_client.service_account.Credentials,
        "from_service_account_file",
        fake_from_file,
    )
    monkeypatch.setattr(vertex_client.genai, "Client", FakeGenaiClient)

    try:
        client = vertex_client.get_vertex_client()
    finally:
        vertex_client.get_vertex_client.cache_clear()

    assert isinstance(client, FakeGenaiClient)
    assert from_file_calls == [
        {
            "path": explicit_path.resolve(),
            "scopes": [vertex_client.VERTEX_AUTH_SCOPE],
        }
    ]
    assert client.kwargs == {
        "vertexai": True,
        "credentials": fake_credentials,
        "project": "file-project",
        "location": "us-central1",
    }


def test_vertex_client_treats_cloud_sdk_adc_file_path_as_adc(
    monkeypatch,
    tmp_path,
):
    adc_path = tmp_path / "gcloud" / "application_default_credentials.json"
    adc_path.parent.mkdir()
    adc_path.write_text("{}", encoding="utf-8")
    fake_credentials = object()
    default_calls: list[dict[str, object]] = []

    def fake_default(*, scopes: list[str]) -> tuple[object, str]:
        default_calls.append({"scopes": scopes})
        return fake_credentials, "adc-project"

    def fail_from_file(path: str, **kwargs: object) -> object:
        raise AssertionError(f"ADC JSON should not be loaded as service account: {path}")

    settings = Settings(
        google_application_credentials=adc_path,
        gcp_project_id=None,
        gcp_location="us-central1",
    )

    vertex_client.get_vertex_client.cache_clear()
    monkeypatch.setattr(vertex_client, "get_settings", lambda: settings)
    monkeypatch.setattr(vertex_client.google_auth, "default", fake_default)
    monkeypatch.setattr(
        vertex_client.service_account.Credentials,
        "from_service_account_file",
        fail_from_file,
    )
    monkeypatch.setattr(vertex_client.genai, "Client", FakeGenaiClient)

    try:
        client = vertex_client.get_vertex_client()
    finally:
        vertex_client.get_vertex_client.cache_clear()

    assert isinstance(client, FakeGenaiClient)
    assert default_calls == [{"scopes": [vertex_client.VERTEX_AUTH_SCOPE]}]
    assert client.kwargs["credentials"] is fake_credentials
    assert client.kwargs["project"] == "adc-project"
