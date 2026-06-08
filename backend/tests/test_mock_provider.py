from __future__ import annotations

import pytest

from app.config import Settings
from app.models import GenerationMode
from app.services.llm import enhancer
from app.services.vertex import client as vertex_client
from app.services.vertex import imagen
from app.services.vertex import veo


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _fail_vertex_client() -> None:
    raise AssertionError("mock provider must not create a Vertex client")


def _mock_settings() -> Settings:
    return Settings(ai_provider="mock")


def _png_size(data: bytes) -> tuple[int, int]:
    return (
        int.from_bytes(data[16:20], byteorder="big"),
        int.from_bytes(data[20:24], byteorder="big"),
    )


async def test_mock_image_provider_returns_pngs_without_vertex_client(monkeypatch):
    monkeypatch.setattr(imagen, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(imagen, "get_vertex_client", _fail_vertex_client)

    images = await imagen.generate_image(
        "imagen-4.0-fast-generate-001",
        "a quiet desk lamp",
        number_of_images=2,
        aspect_ratio="16:9",
    )

    assert len(images) == 2
    assert all(image.startswith(PNG_SIGNATURE) for image in images)
    assert [_png_size(image) for image in images] == [(640, 360), (640, 360)]
    assert images[0] != images[1]


async def test_mock_image_provider_failure_sentinel_raises_without_vertex_client(
    monkeypatch,
):
    monkeypatch.setattr(imagen, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(imagen, "get_vertex_client", _fail_vertex_client)

    with pytest.raises(imagen.MockProviderFailureError) as exc_info:
        await imagen.generate_image(
            "imagen-4.0-fast-generate-001",
            "a quiet desk lamp [[mock-fail:imagen]]",
            number_of_images=1,
            aspect_ratio="1:1",
        )

    assert exc_info.value.code == "mock_provider_failure"
    assert exc_info.value.public_message == "Mock provider failure was requested."
    assert exc_info.value.retryable is False


async def test_mock_prompt_enhancement_returns_draft_without_vertex_client(monkeypatch):
    monkeypatch.setattr(enhancer, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(enhancer, "get_vertex_client", _fail_vertex_client)

    result = await enhancer.enhance_prompt(
        "a quiet desk lamp",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        creativity_preset="faithful",
    )

    assert result.original == "a quiet desk lamp"
    assert "a quiet desk lamp" in result.enhanced
    assert result.components["provider"] == "mock"
    assert result.target_mode == GenerationMode.T2I
    assert result.target_model == "imagen-4.0-fast-generate-001"


async def test_mock_video_provider_returns_mp4_without_vertex_client(monkeypatch):
    monkeypatch.setattr(veo, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(veo, "get_vertex_client", _fail_vertex_client)

    operation = await veo.submit_video(
        "veo-3.0-fast-generate-001",
        "a slow dolly through a rainy alley",
        aspect_ratio="16:9",
        duration_sec=4,
    )
    video = await veo.poll_operation(operation)

    assert operation.done is True
    assert str(operation.name).startswith("mock://veo/")
    assert video[4:8] == b"ftyp"


async def test_mock_i2v_provider_uses_source_image_without_vertex_client(monkeypatch):
    monkeypatch.setattr(veo, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(veo, "get_vertex_client", _fail_vertex_client)

    t2v_operation = await veo.submit_video(
        "veo-3.0-fast-generate-001",
        "a slow dolly through a rainy alley",
        aspect_ratio="16:9",
        duration_sec=4,
    )
    i2v_operation = await veo.submit_video(
        "veo-3.0-fast-generate-001",
        "a slow dolly through a rainy alley",
        aspect_ratio="16:9",
        duration_sec=4,
        image_bytes=b"source-image",
        image_mime="image/png",
    )

    assert await veo.poll_operation(t2v_operation) != await veo.poll_operation(
        i2v_operation
    )


def test_mock_vertex_readiness_does_not_require_credentials(monkeypatch):
    monkeypatch.setattr(vertex_client, "get_settings", _mock_settings, raising=False)
    monkeypatch.setattr(vertex_client, "get_vertex_client", _fail_vertex_client)

    readiness = vertex_client.get_vertex_readiness()

    assert readiness.ready is True
    assert readiness.status == "mock_provider"
    assert readiness.credentials == "not_required"
    assert readiness.project == "not_required"
    assert readiness.location == "local"
