from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models import GenerationMode
from app.prompt_enhancement import CreativityPreset
from app.services.llm import enhancer
from app.services.vertex.errors import VertexRateLimitedError


class FakeGenerateContentModels:
    def __init__(
        self,
        *,
        responses: list[SimpleNamespace] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.responses = responses or []
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.responses.pop(0)


class FakeGenerateContentClient:
    def __init__(self, models: FakeGenerateContentModels) -> None:
        self.models = models


class StatusError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"status {status_code}")


async def test_enhance_prompt_parses_schema_payload_without_vertex_client():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "A quiet desk lamp on walnut wood with soft side light.",
                    "components": {
                        "subject": "quiet desk lamp",
                        "lighting": "soft side light",
                    },
                },
                usage_metadata=SimpleNamespace(
                    prompt_token_count=21,
                    candidates_token_count=13,
                ),
            )
        ]
    )

    result = await enhancer.enhance_prompt(
        "a quiet desk lamp",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        creativity_preset=CreativityPreset.FAITHFUL,
        client=FakeGenerateContentClient(models),
    )

    assert result.original == "a quiet desk lamp"
    assert result.enhanced == "A quiet desk lamp on walnut wood with soft side light."
    assert result.components == {
        "subject": "quiet desk lamp",
        "lighting": "soft side light",
    }
    assert result.target_mode == GenerationMode.T2I
    assert result.target_model == "imagen-4.0-fast-generate-001"
    assert result.llm_model == enhancer.DEFAULT_LLM_MODEL
    assert result.creativity_preset == CreativityPreset.FAITHFUL
    assert result.temperature == 0.2
    assert result.tokens_in == 21
    assert result.tokens_out == 13

    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == enhancer.DEFAULT_LLM_MODEL
    assert "a quiet desk lamp" in call["contents"][0]
    assert getattr(call["config"], "temperature") == 0.2


async def test_enhance_prompt_retries_malformed_json_text_once():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(text="not json"),
            SimpleNamespace(
                text=(
                    '{"enhanced":"A small paper boat drifting slowly.",'
                    '"components":{"motion":"slow drift"}}'
                )
            ),
        ]
    )

    result = await enhancer.enhance_prompt(
        "paper boat",
        target_mode=GenerationMode.T2V,
        target_model="veo-3.0-fast-generate-001",
        client=FakeGenerateContentClient(models),
    )

    assert result.enhanced == "A small paper boat drifting slowly."
    assert result.components == {"motion": "slow drift"}
    assert len(models.calls) == 2
    assert "STRICT JSON RETRY" not in models.calls[0]["contents"][0]
    assert "STRICT JSON RETRY" in models.calls[1]["contents"][0]


async def test_enhance_prompt_rejects_schema_invalid_response():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "",
                    "components": {},
                }
            )
        ]
    )

    with pytest.raises(enhancer.PromptEnhancementResponseError) as exc_info:
        await enhancer.enhance_prompt(
            "desk lamp",
            target_mode=GenerationMode.T2I,
            target_model="imagen-4.0-fast-generate-001",
            client=FakeGenerateContentClient(models),
        )

    assert exc_info.value.code == "prompt_enhancement_invalid_response"
    assert exc_info.value.reason == "schema_validation_failed"
    assert exc_info.value.source == "parsed"
    assert exc_info.value.field == "enhanced"


async def test_enhance_prompt_maps_provider_rate_limit_error():
    models = FakeGenerateContentModels(exc=StatusError(429))

    with pytest.raises(VertexRateLimitedError) as exc_info:
        await enhancer.enhance_prompt(
            "desk lamp",
            target_mode=GenerationMode.T2I,
            target_model="imagen-4.0-fast-generate-001",
            client=FakeGenerateContentClient(models),
        )

    assert exc_info.value.code == "vertex_rate_limited"
    assert exc_info.value.status_code == 429
