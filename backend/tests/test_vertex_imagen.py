from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from app.services.vertex import imagen
from app.services.vertex.errors import (
    VertexOutputUnavailableError,
    VertexRateLimitedError,
)


class FakeImagenModels:
    def __init__(
        self,
        *,
        response: SimpleNamespace | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def generate_images(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


class FakeImagenClient:
    def __init__(self, models: FakeImagenModels) -> None:
        self.models = models


class StatusError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"status {status_code}")


def _response_with_image(image_bytes: bytes | str) -> SimpleNamespace:
    return SimpleNamespace(
        generated_images=[
            SimpleNamespace(
                image=SimpleNamespace(image_bytes=image_bytes),
            )
        ],
    )


async def test_generate_image_returns_inline_image_bytes_without_vertex_client():
    models = FakeImagenModels(response=_response_with_image(b"image-bytes"))
    client = FakeImagenClient(models)

    result = await imagen.generate_image(
        "imagen-4.0-fast-generate-001",
        "a quiet desk lamp",
        number_of_images=2,
        aspect_ratio="16:9",
        client=client,
    )

    assert result == [b"image-bytes"]
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == "imagen-4.0-fast-generate-001"
    assert call["prompt"] == "a quiet desk lamp"
    assert getattr(call["config"], "number_of_images") == 2
    assert getattr(call["config"], "aspect_ratio") == "16:9"


async def test_generate_image_decodes_base64_image_bytes_without_vertex_client():
    encoded = base64.b64encode(b"encoded-image").decode("ascii")
    models = FakeImagenModels(response=_response_with_image(encoded))

    result = await imagen.generate_image(
        "imagen-4.0-fast-generate-001",
        "a quiet desk lamp",
        client=FakeImagenClient(models),
    )

    assert result == [b"encoded-image"]


async def test_generate_image_raises_output_unavailable_when_images_are_missing():
    models = FakeImagenModels(response=SimpleNamespace(generated_images=[]))

    with pytest.raises(VertexOutputUnavailableError) as exc_info:
        await imagen.generate_image(
            "imagen-4.0-fast-generate-001",
            "a quiet desk lamp",
            client=FakeImagenClient(models),
        )

    assert exc_info.value.code == "vertex_output_unavailable"


async def test_generate_image_maps_provider_rate_limit_error():
    models = FakeImagenModels(exc=StatusError(429))

    with pytest.raises(VertexRateLimitedError) as exc_info:
        await imagen.generate_image(
            "imagen-4.0-fast-generate-001",
            "a quiet desk lamp",
            client=FakeImagenClient(models),
        )

    assert exc_info.value.code == "vertex_rate_limited"
    assert exc_info.value.status_code == 429
