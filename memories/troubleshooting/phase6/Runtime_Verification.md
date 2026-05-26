# Phase 6 Runtime Verification

## Purpose

After Phase 6, verify that the backend and frontend can run on `0.0.0.0` and that the frontend health screen can read the backend health response. No Vertex generation calls were made.

## Docker/Compose Blockers

- `docker compose up --build` failed because the Docker CLI did not have the Compose v2 plugin behavior available.
- `docker-compose up --build` failed before startup with a Docker Python client `http+docker` URL scheme error.
- Direct Docker daemon checks failed with `permission denied` on `/var/run/docker.sock`, even when retried with escalated command execution.
- Current judgment: Docker/Compose verification is blocked by environment constraints, not by the app code.

## Split Runtime Verification

- Local `postgres` binary was not present, so no local DB recovery was attempted.
- Backend started successfully on `0.0.0.0:8000`.
- `GET /api/health` returned HTTP 200 with `ok: false`, `ready: false`, and `db: "down"` as expected without Postgres.
- Frontend started successfully on `0.0.0.0:5173`.
- Frontend HTML was served successfully.
- Backend health was readable from the frontend origin with CORS headers using `Origin: http://127.0.0.1:5173`.

## Browser Limitation

Actual browser rendering was not verified because no browser or browser automation binary was available in the environment (`chromium`, `google-chrome`, `firefox`, `playwright`, `wkhtmltoimage` were absent). The served Vite module was inspected and confirmed to render `health.data` into the health payload area.

## Application Issue Found

When shutting down the backend without a reachable DB, the Phase 6 job runner startup orphan sweep can still be waiting on DB connection work. Cancelling the app lifespan then produced a traceback from the orphan sweep path:

- `app/main.py` awaits `runner_task` during shutdown.
- `app/services/jobs/runner.py` starts with `sweep_orphans()`.
- With DB unavailable, the sweep DB connection raised `ConnectionRefusedError`.

Current judgment: this is an application follow-up bugfix target. The runner should tolerate DB-unavailable startup/shutdown more cleanly.

## Next Actions

- Do not spend more time on Docker/Postgres recovery in this environment unless the environment changes.
- Add a follow-up bugfix for runner startup/shutdown behavior when the DB is unavailable.
- Re-run runtime verification with Docker/Compose in an environment where Docker daemon access is available.
- Re-run browser rendering verification when a browser or Playwright runtime is available.
