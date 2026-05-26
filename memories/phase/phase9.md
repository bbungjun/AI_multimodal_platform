# Phase 9 — Prompt Enhance Plan

> Current handoff plan as of 2026-05-23. Keep Phase 9 small, TDD-first,
> mock/fake-based, and free of real Gemini/Vertex calls unless explicitly
> approved.

## Scope

Phase 9 adds prompt enhancement through Gemini 2.5 Flash on Vertex AI, but the
implementation should be split into narrow units. The first plan draft grouped
too much into the service boundary and generation integration; this plan
separates schema/API contract, enhancer service behavior, persistence, and
generation linkage.

## Current Status

- `PromptEnhancement` exists in `backend/app/models.py`.
- `Job.enhancement_id` and `Job.enhanced_prompt` exist.
- `PromptEnhancementResponse` and `PromptEnhanceRequest` exist in
  `backend/app/schemas.py`.
- `backend/app/services/llm/enhancer.py` exists and is covered with fake
  Gemini/Vertex service tests.
- `POST /api/prompts/enhance` exists and persists `PromptEnhancement` rows.
- `backend/app/main.py` wires the prompts router.
- Generation requests already include `auto_enhance` and `enhancement_id`, but
  generation linkage is not implemented yet. This is the next unit.
- `auto_enhance=True` automatic execution remains explicitly excluded.
- No completed Phase 9 automated test has made a real Gemini/Vertex call.

## Completed Units

### 2026-05-23 — Phase 9 Plan

- Commit: `75d850e docs: add phase 9 prompt enhance plan`
- Files:
  - `.codex/memories/phase9/phase9_plan.md`
- Notes: Split Phase 9 into small TDD units and excluded `auto_enhance=True`,
  frontend, Phase 10 pipeline, and actual Gemini/Vertex manual QA.

### 2026-05-23 — Unit 1: Schema / API Contract

- Commit: `b2c95f4 feat: add prompt enhance request schema`
- Files:
  - `backend/app/schemas.py`
  - `backend/tests/test_prompt_enhance_schema.py`
- Notes: Added `PromptEnhanceRequest` and confirmed
  `PromptEnhancementResponse` is reused as the output contract.

### 2026-05-23 — Unit 2: Enhancer Service Happy Path

- Commit: `2cc0fdb feat: add Gemini prompt enhancer service`
- Files:
  - `backend/app/services/llm/enhancer.py`
  - `backend/tests/test_prompt_enhancer_service.py`
- Notes: Added `enhance_prompt(...)` service boundary using fake
  Vertex/Gemini client tests. Parses enhanced prompt, components, model,
  token counts, and latency.

### 2026-05-23 — Unit 3: Enhancer Failure / Parsing Hardening

- Commit: `6918a5f fix: handle prompt enhancer failures safely`
- Files:
  - `backend/app/services/llm/enhancer.py`
  - `backend/tests/test_prompt_enhancer_service.py`
- Notes: Covered missing `enhanced`, missing/empty `components`, non-object
  JSON, parsed dict responses, and sanitized provider failures without exposing
  raw provider messages or credential paths.

### 2026-05-23 — Unit 4: Prompt Enhance API Persistence

- Commit: `7d312c5 feat: persist prompt enhancements`
- Files:
  - `backend/app/api/prompts.py`
  - `backend/app/main.py`
  - `backend/tests/test_prompt_enhance_api.py`
- Notes:
  - Added `POST /api/prompts/enhance`.
  - Wired prompts router in `main.py`.
  - Persists `PromptEnhancement` rows on success.
  - API tests monkeypatch `enhancer.enhance_prompt()` to block real
    Gemini/Vertex calls.
  - Covers success `201`, sanitized enhancer failure, validation `422`, and no
    row creation on failure.

## Last Green Tests

- `backend/.venv/bin/pytest backend/tests/test_prompt_enhance_api.py` ->
  `4 passed`.
- `backend/.venv/bin/pytest backend/tests/test_prompt_enhance_api.py backend/tests/test_prompt_enhance_schema.py backend/tests/test_prompt_enhancer_service.py backend/tests/test_health.py` ->
  `20 passed`.
- `backend/.venv/bin/pytest backend/tests/test_job_runner.py backend/tests/test_prompt_enhance_api.py` ->
  `17 passed`.

## Explicit Exclusions

- Do not implement frontend prompt enhancement UI in Phase 9 backend units.
- Do not open Phase 10 pipeline work.
- Do not run actual Gemini/Vertex manual QA unless a later unit explicitly asks
  for approved credentials/configuration.
- Do not request or print credentials, `.env`, service-account JSON, API keys,
  or environment variable contents.
- Do not allow automated tests to make real external AI calls.
- Do not implement `auto_enhance=True` automatic execution in early Phase 9.
  This would touch generation creation, LLM execution, `enhancing` state, and
  runner/state-machine behavior, so it should stay out of the initial scope.

## Proposed Units

### Unit 1 — Prompt Enhance Schema / API Contract

- Status: complete in `b2c95f4`.
- Add `PromptEnhanceRequest` with:
  - `prompt`
  - `target_mode`
  - `target_model`
- Reuse `PromptEnhancementResponse` for output.
- Keep this focused on DTO shape and validation rules.
- Do not call Gemini/Vertex in this unit.

### Unit 2 — LLM Enhancer Service Happy Path

- Status: complete in `2cc0fdb`.
- Add `backend/app/services/llm/enhancer.py`.
- Implement a narrow Gemini enhancer boundary using the existing single Vertex
  SDK/client path.
- Use fake Vertex client / fake `generate_content` response in tests.
- Validate parsing of:
  - `enhanced`
  - `components`
  - `llm_model`
  - latency/tokens when available.
- Do not persist DB rows in this unit.
- Do not call real Gemini/Vertex.

### Unit 3 — LLM Enhancer Failure / Parsing Paths

- Status: complete in `6918a5f`.
- Cover malformed JSON.
- Cover missing required fields such as `enhanced` or `components`.
- Cover raw Gemini/Vertex failure mapped to sanitized public errors.
- Verify raw credential paths, prompt internals, and raw traceback text are not
  exposed.
- Keep retry policy unchanged.

### Unit 4 — `POST /api/prompts/enhance` Persistence

- Status: complete in `7d312c5`.
- Add `backend/app/api/prompts.py`.
- Wire the prompts router in `backend/app/main.py`.
- Route calls `enhancer.enhance_prompt()` and stores a `PromptEnhancement` row.
- Tests should monkeypatch the enhancer service and use the existing fake
  session/factory pattern.
- Verify response contains stored `original`, `enhanced`, `components`,
  `target_mode`, `target_model`, `llm_model`, token counts, and latency.
- Failure path should verify no DB row is created.

### Unit 5 — Generation Linkage With Existing `enhancement_id`

- Status: next implementation unit.
- Only allow linking an already-created prompt enhancement.
- `auto_enhance=True` remains rejected or deferred.
- `POST /api/generations` should fetch the existing enhancement row by
  `enhancement_id` and connect it to the Job.
- Decide and test the prompt storage policy before implementation:
  - likely store submitted final prompt in `job.prompt`,
  - store enhancement text in `job.enhanced_prompt`,
  - store `job.enhancement_id`.
- Reject missing or incompatible `enhancement_id` before creating a Job.

### Unit 6 — Phase 9 Regression / Docs

- Run focused backend tests for prompt enhancement plus related generation
  coverage.
- Run broader backend regression when Phase 9 backend units settle.
- Update Phase 9 progress docs.
- Confirm no automated test makes a real Gemini/Vertex call.

## Test Strategy

- Mock `app.services.llm.enhancer` at the API layer.
- Use fake Vertex client / fake Gemini response at the service layer.
- Add guards so accidental real `get_vertex_client()` usage fails tests unless
  the test explicitly injects a fake.
- Happy path coverage:
  - service parses structured Gemini JSON.
  - API persists and returns `PromptEnhancement`.
  - generation can link to an existing enhancement.
- Failure coverage:
  - validation errors.
  - malformed Gemini response.
  - sanitized Vertex/Gemini service failure.
  - missing `enhancement_id`.
  - incompatible target mode/model linkage.

## Commit Units

1. `b2c95f4 feat: add prompt enhance request schema`
2. `2cc0fdb feat: add Gemini prompt enhancer service`
3. `6918a5f fix: handle prompt enhancer failures safely`
4. `7d312c5 feat: persist prompt enhancements`
5. Next: `feat: link generations to prompt enhancements`
6. Later: `docs: update phase 9 prompt enhance progress`

## Next Session Starting Point

- Start with **Unit 5 — Generation Linkage With Existing `enhancement_id`**.
- Keep `auto_enhance=True` excluded.
- Do not call real Gemini/Vertex.
- Do not request or print credentials, `.env`, service-account JSON, API keys,
  or environment variable contents.
- Suggested first TDD slice:
  - add a generation API test that creates or seeds an existing
    `PromptEnhancement`;
  - post `POST /api/generations` with `enhancement_id`;
  - verify the Job stores `enhancement_id` and `enhanced_prompt`;
  - verify missing/incompatible `enhancement_id` is rejected before Job
    creation.
