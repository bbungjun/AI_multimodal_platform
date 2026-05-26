from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from app.services.vertex import veo
from app.services.vertex.errors import VertexOutputUnavailableError


def _completed_operation_with_video(video_bytes: bytes | str) -> SimpleNamespace:
    return SimpleNamespace(
        done=True,
        result=SimpleNamespace(
            generated_videos=[
                SimpleNamespace(
                    video=SimpleNamespace(video_bytes=video_bytes),
                )
            ],
        ),
    )


async def test_poll_operation_returns_inline_video_bytes_without_vertex_call():
    operation = _completed_operation_with_video(b"video-bytes")

    result = await veo.poll_operation(operation, client=object())

    assert result == b"video-bytes"


async def test_poll_operation_decodes_base64_video_bytes_without_vertex_call():
    encoded = base64.b64encode(b"encoded-video").decode("ascii")
    operation = _completed_operation_with_video(encoded)

    result = await veo.poll_operation(operation, client=object())

    assert result == b"encoded-video"


async def test_poll_operation_raises_output_unavailable_when_video_is_missing():
    operation = SimpleNamespace(
        done=True,
        result=SimpleNamespace(generated_videos=[]),
    )

    with pytest.raises(VertexOutputUnavailableError) as exc_info:
        await veo.poll_operation(operation, client=object())

    assert exc_info.value.code == "vertex_output_unavailable"
