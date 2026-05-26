# Phase 1 Recovery Closeout

Date: 2026-05-26

This note closes the first recovery phase for the KRAFTON take-home assignment
workspace. The goal was not new feature development. It was to recover the
submitted project shape far enough that backend imports, mock-only backend
contracts, frontend build/typecheck, and Docker Compose local mock smoke all
work from the recovered repository.

## Current Git Baseline

- Branch: `main`
- Remote: `origin` -> `https://github.com/bbungjun/AI_mult_modal.git`
- Latest closeout-related commits:
  - `9aca9ae fix: restore pipeline page module`
  - `cd34f5a chore: restore compose env hygiene`
  - `2a4b8c6 docs: record compose smoke status`

## Restored Scope

- Backend import/API skeleton:
  - `backend/app/api/{health,generations,prompts,pipelines,assets,files}.py`
  - Vertex service boundary files for Imagen/Veo/error mapping.
  - `app.main` imports and router wiring.

- Local no-cost provider path:
  - `AI_PROVIDER=mock` returns deterministic T2I PNG bytes.
  - Prompt enhancement mock returns deterministic draft data.
  - Health/readiness reports mock provider without requiring credentials.

- Backend tests:
  - API contracts for health, generations, prompts, pipelines, assets, files.
  - Job runner, job handlers, pipeline linking, state machine, storage.
  - Vertex adapter output/error parsing boundaries for Imagen and Veo.
  - All recovered tests remain mock/fake-only.

- Frontend recovery:
  - Vite/React/TypeScript build and lint pass.
  - `PipelinePage` module restored to match existing `usePipeline`, API types,
    and `pipeline-*` CSS.
  - Browser smoke passed for `/generate`, `/history`, and a completed job
    detail route.

- Docker Compose:
  - `.env.example` restored with non-secret sample values.
  - backend/frontend `.dockerignore` restored.
  - Compose passes config/build gates.
  - Compose smoke passed using `AI_PROVIDER=mock`.

## Final Local Regression Bundle

Latest verified commands:

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

## Compose Smoke Result

Compose was started with `AI_PROVIDER=mock` and a temporary dummy credential
file outside the repository only to satisfy the service-account mount path.

Verified:

- `db` healthy.
- `backend` reachable on `http://127.0.0.1:8000`.
- `frontend` reachable on `http://127.0.0.1:5173`.
- Backend direct `/api/health` returned `200`.
- Frontend proxy `/api/health` returned `200`.
- Frontend proxy `/api/generations` returned `200`.
- Mock T2I generation created job `d92dd477-e18c-440e-a126-e2850574f630`.
- The in-process runner completed that job.
- Generated PNG asset was readable through both backend direct and frontend
  proxy `/files/...` routes with `image/png`.
- Playwright browser smoke passed for `/generate`, `/history`, and
  `/jobs/d92dd477-e18c-440e-a126-e2850574f630`.

## Safety Status

- No real Vertex, Gemini, Imagen, or Veo calls were made.
- No `.env`, service-account JSON content, API key, private credential, or
  generated runtime asset was committed.
- Redis, Celery, GCS, a new DB, and a new frontend framework were not
  introduced.

## Not Proven By Phase 1

- Real provider access with valid GCP credentials.
- Real Imagen/Veo/Gemini live QA.
- Final README/submission narrative consistency.
- Production hardening beyond the recovered take-home project shape.

## Recommended Next Phase

Run a final submission consistency review:

- Compare `README.md`, `AGENTS.md`, `memories/architecture.md`, and current
  code behavior.
- Confirm endpoint tables and environment instructions match recovered code.
- Confirm mock vs real provider guidance is clear.
- Confirm no generated artifacts or credentials are staged.
- Decide whether to stop Compose services after manual UI review.
