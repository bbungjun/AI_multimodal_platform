# CreativeOps Studio

CreativeOps Studio is a personal AI creative workspace for generating images,
videos, and image-to-video pipelines while keeping the operational details of
each job visible. It combines a creative studio surface with an operations-grade
FastAPI backend for stateful Vertex AI workflows.

The app supports:

- Imagen text-to-image generation
- Veo text-to-video generation
- Veo image-to-video generation
- Gemini prompt enhancement as an editable draft
- T2I -> I2V pipeline jobs
- job history, detail timelines, generated asset previews, and provider
  readiness checks

## Architecture

```text
React/Vite frontend
  -> FastAPI backend
    -> PostgreSQL jobs, assets, and prompt records
    -> Internal asyncio job runner
    -> Local DATA_DIR asset storage
    -> Vertex AI through google-genai
```

The frontend never calls Vertex AI directly. Provider access is isolated in the
backend service boundary. Local development can run with a deterministic mock
provider so tests and smoke checks do not create paid AI requests.

## Stack

- Backend: Python 3.11, FastAPI, SQLAlchemy async, asyncpg
- Database: PostgreSQL 16
- Frontend: Vite, React, TypeScript, TanStack Query
- AI SDK: `google-genai`
- Runtime: Docker Compose with local Postgres and asset volumes

## Quick Start: Mock Mode

Mock mode is the safest default for local development. It does not require
Google credentials and does not call Gemini, Imagen, or Veo.

1. Create `.env` from the example.

```powershell
Copy-Item .env.example .env
```

1. In `.env`, keep or set:

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

Credential variables can be left empty in mock mode.

1. Start the stack.

```powershell
docker compose config
docker compose up -d --build
```

1. Open the app.

- Frontend: <http://127.0.0.1:5173>
- Backend API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>

## Vertex Mode

Vertex mode sends real provider requests and may create cost. Use it only when
you intend to run live Gemini, Imagen, or Veo checks.

Required settings:

```env
AI_PROVIDER=vertex
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
```

For Docker plus ADC, set a host credential path and a matching container path:

```env
GOOGLE_APPLICATION_CREDENTIALS=/secrets/google-credentials.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/google-credentials.json
```

For a service-account file, use the same pattern with a service-account JSON
path. Do not paste credential JSON contents into `.env`, docs, logs, or commits.

Health readiness checks provider configuration, not model quality or quota:

```powershell
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
```

Follow [the Vertex live QA runbook](docs/runbooks/vertex-live-qa.md) before
sending cost-bearing generation requests.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Database and provider readiness |
| POST | `/api/prompts/enhance` | Create an editable prompt enhancement draft |
| POST | `/api/generations` | Create T2I, T2V, or I2V generation jobs |
| GET | `/api/generations` | List job history with filters |
| GET | `/api/generations/{job_id}` | Read one job with assets and state history |
| DELETE | `/api/generations/{job_id}` | Delete terminal jobs and local assets |
| POST | `/api/pipelines` | Create a T2I parent plus blocked I2V child |
| GET | `/api/pipelines/{parent_job_id}` | Read a parent/child pipeline |
| GET | `/api/assets/{asset_id}` | Read asset metadata |
| GET | `/files/{job_uuid}/{filename}` | Stream validated local media files |

## Development Checks

Backend:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Frontend:

```powershell
cd frontend
npm install
npm run build
```

Compose:

```powershell
docker compose config
```

## Documentation

- [Architecture](docs/architecture.md)
- [Provider modes](docs/provider-modes.md)
- [Job lifecycle](docs/job-lifecycle.md)
- [Storage and assets](docs/storage-and-assets.md)
- [Testing strategy](docs/testing.md)
- [Local mock runbook](docs/runbooks/local-mock.md)
- [Vertex live QA runbook](docs/runbooks/vertex-live-qa.md)
- [Troubleshooting notes](docs/troubleshooting.md)
- [Architecture decision records](docs/adr)

## Safety Notes

- Do not commit `.env`, credential JSON files, generated media, or runtime logs.
- Automated tests should use mock or fake providers.
- Live Vertex QA should be explicit, manual, and cost-aware.
- The current private repository still contains archived legacy context in git
  history. Create a clean public history before making a portfolio/public repo.
