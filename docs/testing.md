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
- model relationship behavior and cascade/detach rules

These tests are the safety net for repository detox and productionization.

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
docker compose config
```

For no-cost local smoke checks, use mock mode. For live Vertex QA, follow the
manual runbook and expect provider cost risk.

## Secret Hygiene

Verification should include checks that `.env`, credential files, generated
media, and runtime assets are not staged or committed.

Useful commands:

```powershell
git status --short --branch
git diff --cached --name-only
git ls-files --others --exclude-standard
```
