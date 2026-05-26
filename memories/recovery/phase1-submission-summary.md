# Phase 1 Submission Summary

Date: 2026-05-27

This memo summarizes the recovered Phase 1 state of the KRAFTON take-home
assignment workspace. The goal of this phase was recovery of the submitted
Vertex AI multimodal generation platform shape, not new feature development.

## Recovered Scope

- Backend import and API skeleton are restored:
  - `GET /api/health`
  - `POST /api/prompts/enhance`
  - `POST /api/generations`
  - `GET /api/generations`
  - `GET /api/generations/{job_id}`
  - `DELETE /api/generations/{job_id}`
  - `POST /api/pipelines`
  - `GET /api/pipelines/{parent_job_id}`
  - `GET /api/assets/{asset_id}`
  - `GET /files/{job_uuid}/{filename}`
- Vertex service boundary files for Imagen, Veo, and public error mapping are
  restored while preserving the `google-genai` / `genai.Client(vertexai=True,
  ...)` integration path.
- Local no-cost `AI_PROVIDER=mock` mode is restored for deterministic T2I PNG
  output, deterministic prompt enhancement drafts, and provider readiness that
  does not require Vertex credentials.
- Backend mock/fake-only test coverage is restored across API contracts,
  storage, job runner, job handlers, state machine, pipeline linking, Vertex
  adapter parsing, and prompt enhancement behavior.
- Frontend Vite/React/TypeScript recovery is complete enough for lint/build and
  browser smoke across `/generate`, `/history`, and completed job detail image
  preview.
- Docker Compose local mock smoke is restored across db, backend, frontend
  proxy, job runner, storage, and `/files` asset streaming.

## Verified Commands

Latest recorded Phase 1 regression bundle:

```bash
cd backend
python -m pytest
python -m compileall app
python -c "import app.main; print('import ok')"

cd ../frontend
npm run lint
npm run build

cd ..
docker compose --env-file .env.example config --quiet
```

Observed results:

- `python -m pytest`: `65 passed`
- `python -m compileall app`: passed
- `python -c "import app.main; print('import ok')"`: `import ok`
- `npm run lint`: passed
- `npm run build`: passed
- `docker compose --env-file .env.example config --quiet`: passed

Latest recorded Compose smoke used `AI_PROVIDER=mock` and verified:

- `db` healthy.
- backend reachable on `http://127.0.0.1:8000`.
- frontend reachable on `http://127.0.0.1:5173`.
- backend direct `/api/health` returned `200`.
- frontend proxy `/api/health` returned `200`.
- frontend proxy `/api/generations` returned `200`.
- mock T2I generation completed and produced a readable PNG asset through both
  backend direct and frontend proxy `/files/...` routes.
- Playwright browser smoke passed for `/generate`, `/history`, and the completed
  mock job detail page.

## Provider Modes

`AI_PROVIDER=mock` is the local recovery and test path. It is intentionally
no-cost and must not call Vertex, Gemini, Imagen, or Veo. It generates
deterministic media and prompt-enhancement responses so the API, database, job
runner, storage, file streaming, and frontend preview flows can be tested
without credentials or external AI requests.

`AI_PROVIDER=vertex` is the original submission provider path. It keeps the
Vertex boundary through the `google-genai` SDK and `genai.Client(vertexai=True,
...)`, uses Imagen 4 for text-to-image, Veo 3 for text-to-video and
image-to-video, and Gemini 2.5 Flash for prompt enhancement. In this path, real
GCP project/location configuration and a service-account JSON file path are
required, but secret contents must never be written into `.env`, logs, docs, or
commits.

Compose currently declares the backend credential mount even in mock mode. For
mock Compose smoke, `GOOGLE_APPLICATION_CREDENTIALS_HOST` must point to a dummy
JSON file outside the repository. That dummy file is only used to satisfy the
mount shape and must not be committed.

## Live QA Status

Real Vertex/Gemini/Imagen/Veo live QA was not executed during Phase 1 recovery
because those calls can incur cost. Automated tests and local smoke checks were
kept mock/fake-only by design.

Not proven by Phase 1:

- Real provider authentication with valid GCP credentials.
- Live Imagen/Veo/Gemini request quality and latency.
- Vertex quota behavior beyond the recovered in-process rate-limiter boundary.
- End-to-end live media generation against the actual cloud provider.

## Git, Compose, And Repo Hygiene

- Branch: `main`
- Remote: `origin` -> `https://github.com/bbungjun/AI_mult_modal.git`
- Pre-summary baseline commit: `ee02155 docs: align phase1 submission guidance`
- Summary memo commit: `eff941a docs: add phase1 submission summary`
- Working tree was clean at the start of this memo, with no staged files.
- Docker Compose mock smoke was completed and `docker compose down` was run
  afterward; no project containers are expected to be running for this handoff.
- Repository hygiene checks found no real `.env`, service-account JSON,
  credential JSON, API key, private credential, or generated runtime media
  candidate staged or committed.
- Allowed environment example material remains limited to `.env.example` and
  documentation that uses placeholder paths/values only.

## Remaining Risks And Manual Checks

- Run real Vertex mode only when the reviewer intentionally accepts provider
  cost and has valid GCP credentials available.
- Before any final external handoff, re-check `git status --short --branch` and
  `git diff --cached --name-only` to confirm only intended files are staged.
- If live Vertex QA is required, verify prompt enhancement, T2I, T2V, I2V, and
  T2I to I2V pipeline flows separately, then record any provider-specific
  errors without exposing credential material.
- If Compose is started again, confirm it is stopped afterward unless an active
  manual review session still needs it.
