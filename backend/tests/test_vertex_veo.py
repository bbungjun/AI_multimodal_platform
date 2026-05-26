from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from app.services.vertex import veo
from app.services.vertex.errors import (
    VertexOperationFailedError,
    VertexOutputUnavailableError,
)


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


async def test_poll_operation_raises_operation_failed_when_operation_has_error():
    operation = SimpleNamespace(
        done=True,
        error=SimpleNamespace(message="generation failed"),
    )

    with pytest.raises(VertexOperationFailedError) as exc_info:
        await veo.poll_operation(operation, client=object())

    assert exc_info.value.code == "vertex_operation_failed"


async def test_poll_operation_raises_timeout_with_operation_name_after_deadline():
    operation = SimpleNamespace(
        done=False,
        name="projects/demo/locations/us/operations/veo-timeout",
    )

    with pytest.raises(veo.VeoTimeoutError) as exc_info:
        await veo.poll_operation(operation, deadline_sec=-1, client=object())

    assert exc_info.value.operation_name == operation.name
