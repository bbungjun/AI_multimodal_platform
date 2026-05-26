from __future__ import annotations

import asyncio
import base64
from typing import Any

from google.genai import types

from app.config import get_settings
from app.services import mock_media
from app.services.vertex.client import get_vertex_client
from app.services.vertex.errors import VertexOutputUnavailableError, map_vertex_error


async def generate_image(
    model_id: str,
    prompt: str,
    *,
    number_of_images: int = 1,
    aspect_ratio: str = "1:1",
    client: Any | None = None,
) -> list[bytes]:
    if client is None and get_settings().ai_provider == "mock":
        return mock_media.generate_mock_pngs(
            model_id,
            prompt,
            number_of_images=number_of_images,
            aspect_ratio=aspect_ratio,
        )

    vertex_client = client or get_vertex_client()
    config = types.GenerateImagesConfig(
        number_of_images=number_of_images,
        aspect_ratio=aspect_ratio,
    )

    try:
        response = await asyncio.to_thread(
            vertex_client.models.generate_images,
            model=model_id,
            prompt=prompt,
            config=config,
        )
    except Exception as exc:
        raise map_vertex_error(exc) from exc

    images = getattr(response, "generated_images", None) or []
    image_bytes = [_coerce_image_bytes(item) for item in images]
    image_bytes = [data for data in image_bytes if data]
    if not image_bytes:
        raise VertexOutputUnavailableError()
    return image_bytes


def _coerce_image_bytes(generated_image: Any) -> bytes | None:
    image = getattr(generated_image, "image", generated_image)
    data = getattr(image, "image_bytes", None)
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except ValueError:
            return None
    return None
