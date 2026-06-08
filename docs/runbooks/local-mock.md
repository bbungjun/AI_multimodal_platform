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

The backend golden-path smoke automates this flow from the repository root:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
```

Use this variant when `db` and `backend` are already running:

```powershell
python scripts/smoke_mock_golden_path.py --base-url http://127.0.0.1:8000
```

The smoke intentionally starts only `db` and `backend` when `--compose` is used.
It refuses `--env-file .env`, requires `AI_PROVIDER=mock` in the selected env
file, checks prompt enhancement, T2I job completion, asset metadata, PNG file
serving, byte-range streaming, and then deletes the generated job unless
`--keep-job` is passed.

Backend tests may use the exact prompt sentinel `[[mock-fail:imagen]]` to force a
deterministic Imagen mock provider failure. Treat it as a test-only failure-path
trigger for job error contracts, not as part of manual smoke or normal studio
usage.

In mock mode, a completed job may report `vertex_charged: true`; this only means
the mock provider handler finished its generation step. It is not real Vertex
billing and does not prove any external AI call happened.

Do not use this backend smoke to judge AI output quality or frontend preview
behavior. It verifies the backend HTTP flow: API, runner, database, storage, and
file streaming.

## Stop

```powershell
docker compose down
```

Use `down -v` only when intentionally removing local database and asset volumes.
