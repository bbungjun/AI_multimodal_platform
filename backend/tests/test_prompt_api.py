from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest

from app.api import prompts
from app.main import app
from app.models import GenerationMode, PromptEnhancement, utc_now
from app.prompt_enhancement import CreativityPreset, temperature_for_preset
from app.services.llm import enhancer
from app.services.vertex.errors import VertexRateLimitedError


class FakePromptSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.refresh_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, instance: object) -> None:
        self.refresh_count += 1
        if isinstance(instance, PromptEnhancement):
            if instance.id is None:
                instance.id = uuid4()
            if instance.created_at is None:
                instance.created_at = utc_now()


async def _post_prompt_enhance(payload: dict, session: FakePromptSession):
    async def override_session() -> AsyncIterator[FakePromptSession]:
        yield session

    app.dependency_overrides[prompts.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post("/api/prompts/enhance", json=payload)
    finally:
        app.dependency_overrides.pop(prompts.get_session, None)


async def test_enhance_prompt_persists_result_and_returns_response(monkeypatch):
    session = FakePromptSession()

    async def enhance_prompt(
        prompt: str,
        *,
        target_mode: GenerationMode,
        target_model: str,
        creativity_preset: CreativityPreset,
    ) -> enhancer.PromptEnhancementResult:
        assert prompt == "a quiet desk lamp"
        assert target_mode == GenerationMode.T2I
        assert target_model == "imagen-4.0-fast-generate-001"
        assert creativity_preset == CreativityPreset.IMAGINATIVE
        return enhancer.PromptEnhancementResult(
            original=prompt,
            enhanced="A quiet desk lamp on walnut wood with soft side light.",
            components={"subject": "desk lamp", "lighting": "soft side light"},
            target_mode=target_mode,
            target_model=target_model,
            llm_model="gemini-2.5-flash",
            latency_ms=42,
            tokens_in=21,
            tokens_out=13,
            creativity_preset=creativity_preset,
            temperature=temperature_for_preset(creativity_preset),
        )

    monkeypatch.setattr(prompts.enhancer, "enhance_prompt", enhance_prompt)

    response = await _post_prompt_enhance(
        {
            "prompt": "a quiet desk lamp",
            "target_mode": "t2i",
            "target_model": "imagen-4.0-fast-generate-001",
            "creativity_preset": "imaginative",
        },
        session,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["original"] == "a quiet desk lamp"
    assert body["enhanced"] == "A quiet desk lamp on walnut wood with soft side light."
    assert body["components"] == {
        "subject": "desk lamp",
        "lighting": "soft side light",
    }
    assert body["target_mode"] == "t2i"
    assert body["target_model"] == "imagen-4.0-fast-generate-001"
    assert body["llm_model"] == "gemini-2.5-flash"
    assert body["creativity_preset"] == "imaginative"
    assert body["temperature"] == 0.8
    assert body["latency_ms"] == 42
    assert body["tokens_in"] == 21
    assert body["tokens_out"] == 13

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, PromptEnhancement)
    assert body["id"] == str(row.id)
    assert row.original == "a quiet desk lamp"
    assert row.enhanced == "A quiet desk lamp on walnut wood with soft side light."
    assert row.components == {"subject": "desk lamp", "lighting": "soft side light"}
    assert row.target_mode == GenerationMode.T2I
    assert row.target_model == "imagen-4.0-fast-generate-001"
    assert row.llm_model == "gemini-2.5-flash"
    assert row.latency_ms == 42
    assert row.tokens_in == 21
    assert row.tokens_out == 13
    assert session.commit_count == 1
    assert session.refresh_count == 1


async def test_enhance_prompt_maps_vertex_error_without_persisting(monkeypatch):
    session = FakePromptSession()

    async def enhance_prompt(*_args: object, **_kwargs: object) -> object:
        raise VertexRateLimitedError(status_code=429)

    monkeypatch.setattr(prompts.enhancer, "enhance_prompt", enhance_prompt)

    response = await _post_prompt_enhance(
        {
            "prompt": "a quiet desk lamp",
            "target_mode": "t2i",
            "target_model": "imagen-4.0-fast-generate-001",
        },
        session,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "vertex_rate_limited",
        "message": "Vertex AI request was rate limited.",
        "retryable": True,
        "status_code": 429,
    }
    assert session.added == []
    assert session.commit_count == 0
    assert session.refresh_count == 0


@pytest.mark.parametrize(
    ("payload", "expected_field"),
    [
        (
            {
                "prompt": "",
                "target_mode": "t2i",
                "target_model": "imagen-4.0-fast-generate-001",
            },
            "prompt",
        ),
        (
            {
                "prompt": "a quiet desk lamp",
                "target_mode": "audio",
                "target_model": "imagen-4.0-fast-generate-001",
            },
            "target_mode",
        ),
        (
            {
                "prompt": "a quiet desk lamp",
                "target_mode": "t2i",
                "target_model": "",
            },
            "target_model",
        ),
        (
            {
                "prompt": "a quiet desk lamp",
                "target_mode": "t2i",
                "target_model": "imagen-4.0-fast-generate-001",
                "creativity_preset": "chaotic",
            },
            "creativity_preset",
        ),
    ],
)
async def test_enhance_prompt_rejects_invalid_request_without_calling_enhancer(
    monkeypatch,
    payload,
    expected_field,
):
    session = FakePromptSession()

    async def enhance_prompt(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid prompt enhancement requests must not call Gemini")

    monkeypatch.setattr(prompts.enhancer, "enhance_prompt", enhance_prompt)

    response = await _post_prompt_enhance(payload, session)

    assert response.status_code == 422
    validation_errors = response.json()["detail"]
    assert any(error["loc"][-1] == expected_field for error in validation_errors)
    assert session.added == []
    assert session.commit_count == 0
    assert session.refresh_count == 0
