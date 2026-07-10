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
        outcomes: list[SimpleNamespace | Exception] | None = None,
    ) -> None:
        self.responses = responses or []
        self.exc = exc
        self.outcomes = outcomes or []
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
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


def _vertex_retry_settings(*, max_attempts: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider="vertex",
        enhance_model=enhancer.DEFAULT_LLM_MODEL,
        provider_retry_max_attempts=max_attempts,
        provider_retry_base_delay_sec=0.0,
        provider_retry_max_delay_sec=0.0,
    )


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


async def test_enhance_prompt_uses_configured_model_by_default(monkeypatch):
    settings = _vertex_retry_settings()
    settings.enhance_model = "gemini-configured-for-test"
    monkeypatch.setattr(enhancer, "get_settings", lambda: settings)
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "A glass cup on a plain table.",
                    "components": {"subject": "glass cup"},
                }
            )
        ]
    )

    result = await enhancer.enhance_prompt(
        "glass cup",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        client=FakeGenerateContentClient(models),
    )

    assert result.llm_model == "gemini-configured-for-test"
    assert models.calls[0]["model"] == "gemini-configured-for-test"


async def test_enhance_prompt_builds_t2i_prompt_with_image_component_guidance():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "A glass teapot on a linen cloth with soft light.",
                    "components": {
                        "subject": "glass teapot",
                        "lighting": "soft light",
                    },
                }
            )
        ]
    )

    await enhancer.enhance_prompt(
        "glass teapot",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        creativity_preset=CreativityPreset.BALANCED,
        client=FakeGenerateContentClient(models),
    )

    call = models.calls[0]
    prompt = call["contents"][0]
    assert isinstance(prompt, str)
    assert getattr(call["config"], "temperature") == 0.5
    assert "target_mode: t2i" in prompt
    assert "creativity_preset: balanced" in prompt
    assert "Creativity strategy: Balanced" in prompt
    assert "For image generation" in prompt
    assert "T2I format example" in prompt
    for component_key in (
        '"subject"',
        '"setting"',
        '"composition"',
        '"lighting"',
        '"style"',
        '"mood"',
    ):
        assert component_key in prompt
    assert "source image as the fixed visual reference" not in prompt


async def test_enhance_prompt_builds_korean_language_preservation_guidance():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "비 내리는 서울 골목의 젖은 포장도로 옆에 네온 간판이 은은하게 비칩니다.",
                    "components": {
                        "subject": "비 내리는 서울 골목",
                        "lighting": "젖은 도로에 반사되는 네온 빛",
                    },
                }
            )
        ]
    )

    await enhancer.enhance_prompt(
        "비 내리는 서울 골목, 네온 간판",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        creativity_preset=CreativityPreset.BALANCED,
        client=FakeGenerateContentClient(models),
    )

    prompt = models.calls[0]["contents"][0]
    assert isinstance(prompt, str)
    assert "Write the enhanced prompt and component values in Korean." in prompt
    assert "Do not translate Korean user text into English." in prompt
    assert '"provider_prompt_en"' in prompt
    assert "English provider prompt" in prompt
    assert "한국어 형식 예시" in prompt
    assert (
        "<<<USER_PROMPT_START>>>\n"
        "비 내리는 서울 골목, 네온 간판\n"
        "<<<USER_PROMPT_END>>>"
    ) in prompt


async def test_enhance_prompt_retries_korean_input_when_response_is_english():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "A rainy Seoul alley with neon signs reflected on wet pavement.",
                    "components": {
                        "subject": "rainy Seoul alley",
                        "lighting": "neon reflections on wet pavement",
                    },
                }
            ),
            SimpleNamespace(
                parsed={
                    "enhanced": "비 내리는 서울 골목의 젖은 포장도로에 네온 간판 빛이 반사됩니다.",
                    "components": {
                        "subject": "비 내리는 서울 골목",
                        "lighting": "젖은 포장도로에 반사되는 네온 간판 빛",
                    },
                }
            ),
        ]
    )

    result = await enhancer.enhance_prompt(
        "비 내리는 서울 골목, 네온 간판",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        creativity_preset=CreativityPreset.BALANCED,
        client=FakeGenerateContentClient(models),
    )

    assert result.enhanced == "비 내리는 서울 골목의 젖은 포장도로에 네온 간판 빛이 반사됩니다."
    assert len(models.calls) == 2
    assert "LANGUAGE RETRY" not in models.calls[0]["contents"][0]
    assert "LANGUAGE RETRY" in models.calls[1]["contents"][0]


async def test_enhance_prompt_rejects_language_mismatch_after_retry():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "A rainy Seoul alley with neon signs reflected on wet pavement.",
                    "components": {
                        "subject": "rainy Seoul alley",
                        "lighting": "neon reflections on wet pavement",
                    },
                }
            ),
            SimpleNamespace(
                parsed={
                    "enhanced": "A rain-soaked Seoul alley with bright neon reflections.",
                    "components": {
                        "subject": "rain-soaked Seoul alley",
                        "lighting": "bright neon reflections",
                    },
                }
            ),
        ]
    )

    with pytest.raises(enhancer.PromptEnhancementResponseError) as exc_info:
        await enhancer.enhance_prompt(
            "비 내리는 서울 골목, 네온 간판",
            target_mode=GenerationMode.T2I,
            target_model="imagen-4.0-fast-generate-001",
            creativity_preset=CreativityPreset.BALANCED,
            client=FakeGenerateContentClient(models),
        )

    assert exc_info.value.code == "prompt_enhancement_invalid_response"
    assert exc_info.value.reason == "language_mismatch"
    assert exc_info.value.source == "response"
    assert exc_info.value.field == "enhanced"
    assert len(models.calls) == 2
    assert "LANGUAGE RETRY" not in models.calls[0]["contents"][0]
    assert "LANGUAGE RETRY" in models.calls[1]["contents"][0]


async def test_enhance_prompt_builds_i2v_prompt_with_source_preservation_guidance():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "Hands gently lift the plated dish as the camera holds.",
                    "components": {
                        "motion": "gentle lift",
                        "camera_work": "locked-off close shot",
                    },
                }
            )
        ]
    )

    await enhancer.enhance_prompt(
        "move the plated dish gently",
        target_mode=GenerationMode.I2V,
        target_model="veo-3.0-fast-generate-001",
        creativity_preset=CreativityPreset.IMAGINATIVE,
        client=FakeGenerateContentClient(models),
    )

    call = models.calls[0]
    prompt = call["contents"][0]
    assert isinstance(prompt, str)
    assert getattr(call["config"], "temperature") == 0.8
    assert "target_mode: i2v" in prompt
    assert "target_model: veo-3.0-fast-generate-001" in prompt
    assert "creativity_preset: imaginative" in prompt
    assert "Creativity strategy: Imaginative" in prompt
    assert "For video generation" in prompt
    assert "source image as the fixed visual reference" in prompt
    assert "Preserve subject identity" in prompt
    assert "Do not add a new primary subject" in prompt
    assert "Video format example" in prompt
    for component_key in (
        '"subject"',
        '"motion"',
        '"camera_work"',
        '"continuity"',
        '"duration"',
        '"sound_cue"',
    ):
        assert component_key in prompt
    assert (
        "<<<USER_PROMPT_START>>>\n"
        "move the plated dish gently\n"
        "<<<USER_PROMPT_END>>>"
    ) in prompt


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


async def test_enhance_prompt_repairs_schema_invalid_response_once():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "",
                    "components": {},
                }
            ),
            SimpleNamespace(
                parsed={
                    "enhanced": "A desk lamp with soft side light.",
                    "components": {"subject": "desk lamp"},
                }
            ),
        ]
    )

    result = await enhancer.enhance_prompt(
        "desk lamp",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        client=FakeGenerateContentClient(models),
    )

    assert result.enhanced == "A desk lamp with soft side light."
    assert result.components == {"subject": "desk lamp"}
    assert len(models.calls) == 2
    assert "STRICT JSON RETRY" not in models.calls[0]["contents"][0]
    assert "STRICT JSON RETRY" in models.calls[1]["contents"][0]


async def test_enhance_prompt_parses_fenced_json_text_without_retry():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                text=(
                    "```json\n"
                    "{\n"
                    '  "enhanced": "A glass teapot on a linen cloth.",\n'
                    '  "components": {"subject": "glass teapot"}\n'
                    "}\n"
                    "```"
                )
            )
        ]
    )

    result = await enhancer.enhance_prompt(
        "glass teapot",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        client=FakeGenerateContentClient(models),
    )

    assert result.enhanced == "A glass teapot on a linen cloth."
    assert result.components == {"subject": "glass teapot"}
    assert len(models.calls) == 1
    assert "STRICT JSON RETRY" not in models.calls[0]["contents"][0]


async def test_enhance_prompt_extracts_json_object_from_explanatory_text():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                text=(
                    "Here is the enhanced prompt:\n"
                    '{"enhanced":"A quiet tram crosses a rain-slick street.",'
                    '"components":{"subject":"quiet tram",'
                    '"motion":"slow crossing with reflections"}}\n'
                    "Let me know if you want another version."
                )
            )
        ]
    )

    result = await enhancer.enhance_prompt(
        "quiet tram in rain",
        target_mode=GenerationMode.T2V,
        target_model="veo-3.0-fast-generate-001",
        client=FakeGenerateContentClient(models),
    )

    assert result.enhanced == "A quiet tram crosses a rain-slick street."
    assert result.components == {
        "subject": "quiet tram",
        "motion": "slow crossing with reflections",
    }
    assert len(models.calls) == 1


def test_parse_response_payload_logs_truncated_json_safe_diagnostics(caplog):
    with pytest.raises(enhancer.PromptEnhancementResponseError) as exc_info:
        enhancer._parse_response_payload(
            SimpleNamespace(
                text='{"enhanced":"A clipped response","components":'
            )
        )

    assert exc_info.value.reason == "malformed_json"
    assert exc_info.value.source == "text"
    assert any(
        "possible_truncated_json': True" in record.message
        and "A clipped response" not in record.message
        for record in caplog.records
    )


async def test_enhance_prompt_rejects_schema_invalid_response_after_repair_retry():
    models = FakeGenerateContentModels(
        responses=[
            SimpleNamespace(
                parsed={
                    "enhanced": "",
                    "components": {},
                }
            ),
            SimpleNamespace(
                parsed={
                    "enhanced": "",
                    "components": {},
                }
            ),
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
    assert len(models.calls) == 2
    assert "STRICT JSON RETRY" not in models.calls[0]["contents"][0]
    assert "STRICT JSON RETRY" in models.calls[1]["contents"][0]


async def test_enhance_prompt_retries_provider_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(
        enhancer,
        "get_settings",
        lambda: _vertex_retry_settings(max_attempts=2),
    )
    models = FakeGenerateContentModels(
        outcomes=[
            StatusError(429),
            SimpleNamespace(
                parsed={
                    "enhanced": "A desk lamp with soft side light.",
                    "components": {"subject": "desk lamp"},
                }
            ),
        ]
    )

    result = await enhancer.enhance_prompt(
        "desk lamp",
        target_mode=GenerationMode.T2I,
        target_model="imagen-4.0-fast-generate-001",
        client=FakeGenerateContentClient(models),
    )

    assert result.enhanced == "A desk lamp with soft side light."
    assert len(models.calls) == 2


async def test_enhance_prompt_maps_provider_rate_limit_error_after_retry_exhaustion(
    monkeypatch,
):
    monkeypatch.setattr(
        enhancer,
        "get_settings",
        lambda: _vertex_retry_settings(max_attempts=2),
    )
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
    assert len(models.calls) == 2
