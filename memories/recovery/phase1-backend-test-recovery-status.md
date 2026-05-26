# Phase 1 Backend Test Recovery Status

Updated: 2026-05-26

This checkpoint records the backend recovery work completed after the initial
import/API skeleton phase. The goal remains recovery of the submitted KRAFTON
assignment shape, not new feature development.

## Current Git Baseline

- Branch: `main`
- Remote: `origin` -> `https://github.com/bbungjun/AI_mult_modal.git`
- Latest test-recovery commit before this note: `d3092e5 test: restore prompt enhance api contract`
- Working tree was clean before this documentation update.

## Verified Backend Commands

Use these as the current backend recovery gate:

```bash
cd backend
python -m pytest
python -m compileall app
python -c "import app.main; print('import ok')"
```

The latest run before this note had:

- `python -m pytest`: `58 passed`
- `python -m compileall app`: passed
- `python -c "import app.main; print('import ok')"`: `import ok`

## Restored Test Coverage

The backend test suite now includes these recovered mock-only contracts:

- `test_mock_provider.py`
  - `AI_PROVIDER=mock` image generation returns deterministic PNG bytes.
  - mock prompt enhancement returns deterministic draft data.
  - mock readiness does not require credentials or Vertex client creation.

- `test_health.py`
  - health/readiness response shape.
  - mock provider readiness contract.

- `test_storage.py`
  - storage write/read behavior.
  - unsafe path rejection.
  - `/files/{job_uuid}/{filename}` stream, range, and missing file behavior.

- `test_generation_api.py`
  - `POST /api/generations` T2I job creation.
  - `auto_enhance` rejection.
  - prompt enhancement linkage.
  - `GET /api/generations` and `GET /api/generations/{job_id}` response DTOs.
  - terminal delete, non-terminal delete rejection, dependent job protection,
    and terminal dependent detach behavior.

- `test_pipeline_api.py`
  - `POST /api/pipelines` parent T2I plus blocked child I2V creation.
  - `GET /api/pipelines/{parent_job_id}` response contract.

- `test_pipeline_link.py`
  - completed parent links image asset to blocked child.
  - missing/non-image source asset failure.
  - terminal child skip.
  - parent failure cascades only to blocked active children.

- `test_job_runner.py`
  - pending unblocked job selection.
  - `pending -> queued` runner transition.
  - handler task execution.
  - handler exception marks job failed.
  - runner restart resumes polling jobs.
  - orphan sweep marks stale non-terminal jobs failed.

- `test_job_handlers.py`
  - T2I happy path and Vertex/output failure path.
  - T2V happy path, polling resume path, and timeout failure path.
  - I2V happy path, missing source asset failure, and non-image source failure.

- `test_vertex_veo.py`
  - inline video bytes extraction.
  - base64 video bytes decoding.
  - missing output error.
  - operation error mapping.
  - polling timeout preserves operation name.

- `test_vertex_imagen.py`
  - inline image bytes extraction.
  - base64 image bytes decoding.
  - missing output error.
  - provider 429 maps to rate-limited public error.

- `test_prompt_enhancer.py`
  - Gemini-style parsed payload handling.
  - usage token metadata extraction.
  - malformed JSON strict retry.
  - schema-invalid response error.
  - provider 429 maps to rate-limited public error.

- `test_prompt_api.py`
  - `/api/prompts/enhance` persists `PromptEnhancement`.
  - response includes creativity preset, temperature, latency, and token counts.
  - retryable Vertex service errors map to HTTP 503 with public detail.

## Safety Notes

- Automated tests remain mock/fake-only.
- No tests create a real Vertex, Gemini, Imagen, or Veo request.
- No service-account JSON, `.env` secret, API key, or private credential was
  printed or committed.
- Redis, Celery, GCS, and new DB infrastructure were not introduced.

## Known Remaining Gaps

- Explicit tests for `GET /api/assets/{asset_id}` still need to be restored.
- Direct state-machine tests can still be restored, although handler/runner
  tests already exercise many transitions indirectly.
- Frontend build/typecheck recovery is still pending.
- Docker Compose config/build verification is still pending.
- Real provider smoke tests are intentionally not run during local recovery.

## Recommended Next Recovery Order

1. Restore `GET /api/assets/{asset_id}` API contract tests.
2. Add focused state-machine tests if recovered context confirms they existed.
3. Move to frontend build/typecheck recovery.
4. Verify Docker Compose config/build once backend and frontend are stable.
