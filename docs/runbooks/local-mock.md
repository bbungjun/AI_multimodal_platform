# Local Mock Runbook

Use this runbook for no-cost local development and smoke checks.

## Goal

Run the full app stack without calling paid AI providers.

## Environment

Set mock mode in `.env`:

```env
AI_PROVIDER=mock
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal
GCP_PROJECT_ID=
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10
VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
VITE_ALLOWED_HOSTS=localhost,127.0.0.1
```

Mock mode should not require live Google credentials.

## Start

```powershell
docker compose config
docker compose up -d --build
docker compose ps
```

Expected services:

- `db` healthy
- `backend` on `http://127.0.0.1:8000`
- `frontend` on `http://127.0.0.1:5173`

## Health

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health"
```

Expected provider status in mock mode:

```json
{
  "ready": true,
  "status": "mock_provider",
  "credentials": "not_required"
}
```

## Smoke Flow

Create a text-to-image job, wait for completion, and verify that the returned
asset URL streams from `/files/...`. The generated image should be deterministic
mock PNG bytes.

Do not use this runbook to judge AI output quality. It verifies application
flow: API, runner, database, storage, and frontend preview.

## Stop

```powershell
docker compose down
```

Use `down -v` only when intentionally removing local database and asset volumes.
