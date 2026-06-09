# Vertex Live QA Runbook

Use this runbook only when real provider calls are intended. These checks can
create billable Gemini, Imagen, or Veo requests.

## Preconditions

Confirm before sending generation requests:

- billing is enabled for the selected Google Cloud project
- Vertex AI and target generative models are available in the selected location
- credentials are configured through ADC or an explicit mounted credential file
- `GCP_PROJECT_ID` and `GCP_LOCATION` are set
- the current operator accepts cost risk
- no credential values or JSON contents are printed, logged, or committed

## Start Stack

```powershell
docker compose -f docker-compose.yml -f docker-compose.vertex.yml config
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
docker compose ps
```

The vertex override mounts the configured credential file into both `backend`
and `worker`. Do not print the credential file path if it is sensitive in your
environment, and never print credential JSON contents.

## Health

Health checks do not create media. They only check database and provider
readiness.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health"
```

Expected provider readiness:

```json
{
  "ready": true,
  "status": "ready",
  "credentials": "available",
  "project": "configured"
}
```

If readiness is false, stop here and fix configuration before generation.

## Manual QA Order

Run the smallest useful live checks first:

1. Prompt enhancement with Gemini.
2. One text-to-image job with the fast Imagen model.
3. One text-to-video job only if video cost is acceptable.
4. One image-to-video job or pipeline only after a successful image asset exists.

Record only public evidence:

- job id
- final state
- model id
- asset MIME type
- public error code if failed

Do not record proprietary prompts, credential paths, terminal logs containing
environment values, or credential JSON contents.

## Stop

```powershell
docker compose down
```

Keep generated media only if needed for product screenshots or QA evidence.
