from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from types import SimpleNamespace
from typing import Any

from google.genai import types

from app.config import get_settings
from app.services import mock_media
from app.services.vertex.client import get_vertex_client
from app.services.vertex.errors import (
    VertexOperationFailedError,
    VertexOutputUnavailableError,
    map_vertex_error,
)


class VeoTimeoutError(TimeoutError):
    def __init__(self, operation_name: str | None) -> None:
        self.operation_name = operation_name
        super().__init__("Veo generation timed out while polling.")


async def submit_video(
    model_id: str,
    prompt: str,
    *,
    aspect_ratio: str = "16:9",
    duration_sec: int = 4,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
    client: Any | None = None,
) -> Any:
    if client is None and get_settings().ai_provider == "mock":
        video_bytes = mock_media.generate_mock_mp4(
            model_id,
            prompt,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            image_bytes=image_bytes,
        )
        digest = hashlib.sha256(video_bytes).hexdigest()[:16]
        return SimpleNamespace(
            name=f"mock://veo/{digest}",
            done=True,
            response=SimpleNamespace(
                generated_videos=[
                    SimpleNamespace(
                        video=SimpleNamespace(video_bytes=video_bytes),
                    )
                ],
            ),
        )

    vertex_client = client or get_vertex_client()
    config = types.GenerateVideosConfig(
        aspect_ratio=aspect_ratio,
        duration_seconds=duration_sec,
    )
    image = (
        types.Image(image_bytes=image_bytes, mime_type=image_mime or "image/png")
        if image_bytes is not None
        else None
    )

    try:
        return await asyncio.to_thread(
            vertex_client.models.generate_videos,
            model=model_id,
            prompt=prompt,
            image=image,
            config=config,
        )
    except Exception as exc:
        raise map_vertex_error(exc) from exc


async def poll_operation(
    operation: Any,
    *,
    max_interval: float = 30.0,
    deadline_sec: float = 600.0,
    client: Any | None = None,
) -> bytes:
    if client is None and get_settings().ai_provider == "mock":
        video_bytes = _extract_video_bytes(operation)
        if not video_bytes:
            raise VertexOutputUnavailableError()
        return video_bytes

    vertex_client = client or get_vertex_client()
    current = operation
    deadline = time.monotonic() + deadline_sec
    interval = 5.0

    while not bool(getattr(current, "done", False)):
        if time.monotonic() > deadline:
            raise VeoTimeoutError(_operation_name(current))
        await asyncio.sleep(interval)
        interval = min(max_interval, interval * 1.5)
        try:
            current = await asyncio.to_thread(vertex_client.operations.get, current)
        except Exception as exc:
            raise map_vertex_error(exc) from exc

    error = getattr(current, "error", None)
    if error:
        raise VertexOperationFailedError()

    video_bytes = _extract_video_bytes(current)
    if not video_bytes:
        raise VertexOutputUnavailableError()
    return video_bytes


async def poll_operation_name(
    operation_name: str,
    *,
    max_interval: float = 30.0,
    deadline_sec: float = 600.0,
    client: Any | None = None,
) -> bytes:
    if client is None and get_settings().ai_provider == "mock":
        return mock_media.generate_mock_mp4(
            "veo-3.0-fast-generate-001",
            operation_name,
            aspect_ratio="16:9",
            duration_sec=4,
        )

    vertex_client = client or get_vertex_client()
    operation = types.GenerateVideosOperation(name=operation_name)
    try:
        operation = await asyncio.to_thread(vertex_client.operations.get, operation)
    except Exception as exc:
        raise map_vertex_error(exc) from exc
    return await poll_operation(
        operation,
        max_interval=max_interval,
        deadline_sec=deadline_sec,
        client=vertex_client,
    )


poll_operation_by_name = poll_operation_name


def _operation_name(operation: Any) -> str | None:
    name = getattr(operation, "name", None)
    return str(name) if name else None


def _extract_video_bytes(operation: Any) -> bytes | None:
    result = getattr(operation, "result", None) or getattr(operation, "response", None)
    videos = getattr(result, "generated_videos", None) or []
    if not videos:
        return None

    video = getattr(videos[0], "video", videos[0])
    data = getattr(video, "video_bytes", None)
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except ValueError:
            return None
    return None
