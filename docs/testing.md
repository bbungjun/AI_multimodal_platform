# Testing Strategy

Tests should prove the app flow without making real AI calls.

## Default Test Mode

Use `AI_PROVIDER=mock` or fake provider clients for automated tests. Tests must
not call Vertex AI, Gemini, Imagen, or Veo directly.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

## Coverage Anchors

Important backend contracts are already protected by focused tests:

- health readiness and mock-provider readiness
- state machine transitions and terminal behavior
- storage path safety, file roundtrips, and range streaming
- job runner row locking, concurrency, orphan sweep, and polling resume
- job handlers for T2I, T2V, I2V, and pipeline linking
- prompt enhancement parsing, validation, and retry behavior
- Vertex adapter parsing and public error mapping with fake clients
- generation, pipeline, asset, and delete API contracts
- failed-generation retry API contracts, including I2V source asset validation
- model relationship behavior and cascade/detach rules

These tests are the safety net for repository detox and productionization.

The mock Imagen provider also has a test-only failure sentinel:
`[[mock-fail:imagen]]`. In `AI_PROVIDER=mock`, and only when no explicit client is
passed, this prompt fragment raises a deterministic non-retryable provider error
without constructing a Vertex client. Use it in automated tests to verify failed
job error serialization, no-asset writes, `vertex_charged: false`, single-attempt
failure, and pipeline child cascade behavior.

## Frontend Checks

Frontend verification should keep:

```powershell
cd frontend
npm install
npm run build
```

Future work should add stronger UI tests around:

- Generate Studio request flow
- Asset Library previews
- Job Timeline state display
- Ops Console health and error states
- backend error code rendering

## Compose Checks

Docker Compose config should be checked before starting the stack:

```powershell
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

For no-cost local smoke checks, use mock mode. For live Vertex QA, follow the
manual runbook and expect provider cost risk.

## Backend HTTP Smoke

Use the mock-only golden-path smoke to verify the backend HTTP contract, internal
job runner, database persistence, local asset storage, and byte-range file
streaming without calling Vertex AI, Gemini, Imagen, or Veo.

From the repository root, start only `db` and `backend` through Compose and run
the smoke:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
```

If the backend is already running in mock mode, run the same flow against its
base URL:

```powershell
python scripts/smoke_mock_golden_path.py --base-url http://127.0.0.1:8000
```

The script refuses `--env-file .env`, parses only plain `KEY=VALUE` names from
the selected env file, requires `AI_PROVIDER=mock`, and passes
`AI_PROVIDER=mock` to `docker compose` when `--compose` is used.

Expected coverage:

- `GET /api/health` reports `ok`, `ready`, DB up, `mock_provider`, and
  credentials `not_required`
- `POST /api/prompts/enhance` creates a mock prompt draft
- `POST /api/generations` creates a T2I Imagen job using the accepted enhanced
  prompt
- `GET /api/generations/{job_id}` reaches `completed` with
  `queued -> generating -> downloading -> completed` history
- `GET /api/assets/{asset_id}` returns matching asset metadata
- `/files/...` returns PNG bytes and supports `Range: bytes=0-7` with HTTP 206
- `DELETE /api/generations/{job_id}` removes the terminal job and local asset

In mock mode, `vertex_charged: true` means the generation handler completed its
provider step. It does not indicate real Vertex billing or external provider
usage.

## Secret Hygiene

Verification should include checks that `.env`, credential files, generated
media, and runtime assets are not staged or committed.

Useful commands:

```powershell
git status --short --branch
git diff --cached --name-only
git ls-files --others --exclude-standard
```
