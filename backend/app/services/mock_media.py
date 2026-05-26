from __future__ import annotations

import hashlib
import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def generate_mock_pngs(
    model_id: str,
    prompt: str,
    *,
    number_of_images: int,
    aspect_ratio: str,
) -> list[bytes]:
    width, height = _dimensions_for_aspect_ratio(aspect_ratio)
    return [
        _generate_png(
            width,
            height,
            seed_text=f"{model_id}:{prompt}:{aspect_ratio}:{index}",
        )
        for index in range(number_of_images)
    ]


def generate_mock_mp4(
    model_id: str,
    prompt: str,
    *,
    aspect_ratio: str,
    duration_sec: int,
    image_bytes: bytes | None = None,
) -> bytes:
    seed = hashlib.sha256(
        b"|".join(
            [
                model_id.encode("utf-8"),
                prompt.encode("utf-8"),
                aspect_ratio.encode("utf-8"),
                str(duration_sec).encode("ascii"),
                image_bytes or b"",
            ]
        )
    ).digest()
    payload = (b"mock-veo-placeholder:" + seed) * max(1, duration_sec)
    return b"".join(
        [
            _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41"),
            _box(b"free", b"Vertex Studio mock Veo placeholder"),
            _box(b"mdat", payload),
        ]
    )


def _dimensions_for_aspect_ratio(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "16:9":
        return 640, 360
    if aspect_ratio == "9:16":
        return 360, 640
    if aspect_ratio == "4:3":
        return 512, 384
    if aspect_ratio == "3:4":
        return 384, 512
    return 512, 512


def _generate_png(width: int, height: int, *, seed_text: str) -> bytes:
    seed = hashlib.sha256(seed_text.encode("utf-8")).digest()
    raw = bytearray()

    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(
                (
                    (seed[0] + x * 3 + y) % 256,
                    (seed[7] + x + y * 2) % 256,
                    (seed[15] + x // 2 + y // 2) % 256,
                )
            )

    return b"".join(
        [
            PNG_SIGNATURE,
            _chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
            ),
            _chunk(b"IDAT", zlib.compress(bytes(raw), level=6)),
            _chunk(b"IEND", b""),
        ]
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _box(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data) + 8) + kind + data
