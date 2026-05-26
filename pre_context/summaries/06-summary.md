# krafton_assignment_06 요약

## 핵심 주제

Phase 8 Veo backend를 mock 기반 완료 상태로 닫고, Phase 9 Prompt Enhance backend 구현을 계획한 뒤 Unit 1~4까지 진행한 세션입니다. 복구 시 Gemini prompt enhancement 관련 schema, service, API, DB persistence의 경계를 확인하는 핵심 자료입니다.

## 주요 키워드

- Phase 8 closeout, polling resume docs, `169 passed`
- Phase 9 Prompt Enhance, Gemini 2.5 Flash
- `PromptEnhancement`, `enhancement_id`, `enhanced_prompt`
- `backend/app/services/llm/enhancer.py`
- `backend/app/api/prompts.py`
- `PromptEnhanceRequest`, `PromptEnhancementResponse`
- `/api/prompts/enhance`
- mock Gemini, no real Vertex/Gemini call
- `auto_enhance=True` 제외, existing `enhancement_id` linkage

## 복구에 중요한 내용

- 세션 시작 시 Phase 8은 mock 기반 backend 구현이 거의 완료된 상태로 정리되었습니다. full backend regression 결과는 `backend/.venv/bin/pytest backend/tests -> 169 passed in 1.45s`로 기록되었습니다.
- actual Veo manual QA는 credentials missing으로 보류되었고, 더 진행하지 말라는 판단이 남았습니다. Phase 8은 문서 closeout 후 Phase 9로 넘어가는 흐름입니다.
- Phase 9의 목표는 `/api/prompts/enhance`, Gemini enhancer service, `PromptEnhancement` DB 저장, mock 기반 테스트입니다.
- Phase 9 시작 전 이미 존재하던 것은 `PromptEnhancement` model, `Job.enhancement_id`, `Job.enhanced_prompt`, `PromptEnhancementResponse`, `GenerationRequestBase.auto_enhance/enhancement_id`였습니다. 없던 것은 `enhancer.py`, `prompts.py`, prompts router wiring, request schema, 관련 테스트였습니다.
- `auto_enhance=True`를 generation 생성 중 Gemini 직접 호출 흐름으로 여는 것은 Phase 9 초반 범위에서 제외하기로 했습니다. 기존 `enhancement_id`를 generation job에 연결하는 최소 경로만 별도 Unit 5 후보로 남겼습니다.
- Unit 1은 `PromptEnhanceRequest`와 API contract/schema validation 테스트를 추가했습니다. 관련 generation flow 테스트까지 포함해 `24 passed`가 기록되었습니다.
- Unit 2는 `backend/app/services/llm/enhancer.py`와 `backend/tests/test_prompt_enhancer_service.py`를 추가했습니다. `enhance_prompt(prompt, target_mode, target_model, llm_model="gemini-2.5-flash", client=None)` 경계가 잡혔고 fake Gemini response parsing이 검증되었습니다.
- Unit 3은 enhancer failure/parsing hardening입니다. malformed JSON, provider error sanitize 등 service 경계의 대표 실패 경로를 보강했고 `20 passed`가 기록되었습니다.
- Unit 4는 `POST /api/prompts/enhance` API와 DB persistence입니다. `backend/app/api/prompts.py`, `backend/tests/test_prompt_enhance_api.py`가 추가되었고, 성공 시 row 저장/응답, 실패 시 row 미생성/error shape가 검증되었습니다.
- Unit 5는 아직 다음 단계로 남았습니다. 범위는 existing `enhancement_id` generation linkage만이며, `auto_enhance=True` 자동 실행은 계속 차단해야 합니다.

## 확인해야 할 Phase 9 구현/테스트 흐름

- Unit 1: `PromptEnhanceRequest`와 API contract/schema validation 테스트가 있는지 확인합니다.
- Unit 2: `enhance_prompt(...)` service boundary와 fake Gemini response parsing 테스트가 있는지 확인합니다.
- Unit 3: malformed JSON, provider error sanitize 등 대표 failure/parsing 테스트가 있는지 확인합니다.
- Unit 4: `/api/prompts/enhance` route가 enhancer를 호출하고 `PromptEnhancement` row를 저장/응답하는지 확인합니다.
- 실제 복구 시 Git 이력보다 현재 파일 상태와 테스트 흔적을 기준으로 판단합니다.
- Unit 1 테스트: prompt enhance schema + T2I/T2V/I2V flow 묶음 `24 passed`
- Unit 2 테스트: prompt enhancer service + schema + vertex errors `14 passed`
- Unit 3 테스트: prompt enhancer service + schema + vertex errors `20 passed`
- Unit 4 테스트:
  - `backend/tests/test_prompt_enhance_api.py -> 4 passed`
  - prompt enhance/schema/service/health 묶음 `20 passed`
  - job runner + prompt API 묶음 `17 passed`

## 원문에서 찾아볼 위치

- Phase 8 현재 상태와 다음 단계: 대략 149~194
- Phase 8 closeout 프롬프트와 결과: 대략 225~343
- Phase 9 backend 구현 프롬프트: 대략 345~383
- Phase 9 계획 본문: 대략 401~484
- Phase 9 계획 세분화와 범위 축소: 대략 538~686
- Unit 1 schema/API contract: 대략 714~904
- Unit 2 enhancer service: 대략 916~984
- Unit 3 failure/parsing hardening: 대략 996~1073
- Unit 4 prompts API + DB persistence: 대략 1086~1177
- Unit 5 handoff와 남은 linkage 범위: 대략 1185~1271

## 복구 판단 메모

- Prompt Enhance 복구는 `schemas.py`, `models.py`, `services/llm/enhancer.py`, `api/prompts.py`, prompts router wiring, tests 순서로 확인합니다.
- 테스트에서는 `enhancer.enhance_prompt()` 또는 내부 fake client를 monkeypatch해야 하며 실제 Gemini/Vertex 호출은 금지합니다.
- `auto_enhance=True`가 generation 생성 중 LLM을 호출하도록 확장되어 있으면 원래 Phase 9 범위를 넘어선 것입니다. 먼저 기존 `enhancement_id` 연결만 확인합니다.
- Unit 4 이후 상태에서는 `generation linkage with existing enhancement_id`가 다음 미완 후보입니다.
