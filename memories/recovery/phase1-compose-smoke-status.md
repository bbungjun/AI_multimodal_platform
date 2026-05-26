# Phase 1 Compose Smoke Status

Date: 2026-05-26

This checkpoint records the first recovered Docker Compose smoke pass after
backend import/API recovery, mock-only backend test recovery, frontend build
recovery, and compose env hygiene restoration.

## Scope

- Docker Compose runtime smoke only.
- Provider mode was overridden to `AI_PROVIDER=mock` for local no-cost testing.
- A temporary dummy service-account JSON path outside the repo was used only to
  satisfy the compose read-only mount requirement.
- No real Vertex, Gemini, Imagen, or Veo calls were made.
- No `.env`, credential file, service-account JSON content, or generated asset
  was committed.

## Verified

Commands/checks executed:

```bash
docker compose --env-file .env.example up -d --build
docker compose --env-file .env.example ps
```

Observed services:

- `db` running and healthy.
- `backend` running on host port `8000`.
- `frontend` running on host port `5173`.

HTTP/API smoke:

- `GET http://127.0.0.1:8000/api/health` -> `200`
- `GET http://127.0.0.1:5173/api/health` -> `200`
- `GET http://127.0.0.1:5173/api/generations?limit=20&offset=0` -> `200`

Mock generation smoke:

- `POST http://127.0.0.1:5173/api/generations` with a T2I mock payload created
  job `d92dd477-e18c-440e-a126-e2850574f630`.
- The in-process runner completed the job.
- The generated PNG asset was readable from both:
  - frontend proxy `/files/d92dd477-e18c-440e-a126-e2850574f630/output.png`
  - backend direct `/files/d92dd477-e18c-440e-a126-e2850574f630/output.png`
- Both asset responses returned `200` with `image/png`.

Browser smoke with Playwright:

- `/generate` rendered with API connected state.
- `/history` rendered and showed the mock job.
- `/jobs/d92dd477-e18c-440e-a126-e2850574f630` rendered the completed image
  result view.
- No unexpected console errors, page errors, or unexpected `4xx`/`5xx`
  responses were observed. Development-only React DevTools/router warnings and
  favicon noise were treated as non-blocking.

## Current Status

Compose smoke is green for the recovered local mock path:

- db -> backend -> frontend proxy -> job runner -> storage -> `/files`

The smoke does not prove real Vertex/Gemini/Veo access. That remains a separate
manual QA path and must not be part of automated tests.

## Next Gate

Run the final local regression bundle:

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
