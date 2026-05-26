# Phase 2 Vertex Live QA Runbook

Date: 2026-05-27

This runbook defines the next manual recovery gate after Phase 1. It is a plan
for validating the original `AI_PROVIDER=vertex` submission path with real GCP
credentials, not a record that live QA has already been executed.

No real Vertex, Gemini, Imagen, or Veo calls were made while creating this
document.

## Goal

Verify, only after explicit cost acceptance, that the recovered repository can
run the submitted Vertex AI provider path end to end:

- Gemini 2.5 Flash prompt enhancement.
- Imagen 4 text-to-image generation.
- Veo 3 text-to-video generation.
- Veo 3 image-to-video generation from a completed image asset.
- T2I -> I2V pipeline linking.

The local mock path remains the automated regression path. Live provider QA is
manual because it requires credentials, quota, model access, and paid provider
requests.

## Preconditions

Before any live provider request:

- The reviewer explicitly accepts possible Vertex AI cost.
- The GCP project has billing enabled and Vertex AI access for the selected
  region.
- The service account has the permissions needed to call Gemini, Imagen, and
  Veo through Vertex AI.
- The service-account JSON file exists outside the repository.
- `.env` exists only locally and is ignored by git.
- No service-account JSON content, API key, private credential, or real `.env`
  value is pasted into docs, terminal notes, commits, or issue comments.
- The working tree starts clean:

```bash
git status --short --branch
git diff --cached --name-only
```

Expected:

- `git status --short --branch` shows `## main...origin/main`.
- `git diff --cached --name-only` prints nothing.

## Environment Setup

Use `.env.example` as the shape reference and create a local `.env` that is not
committed. Do not put JSON contents in `.env`; only set the host file path.

Required live-provider values:

```env
AI_PROVIDER=vertex
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/outside/repo/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
```

The current Compose file always mounts
`GOOGLE_APPLICATION_CREDENTIALS_HOST` read-only to `/secrets/sa.json` in the
backend container. The host path must be absolute and must point outside this
repository.

## Config-Only Checks

These commands should not create media or call Imagen/Veo/Gemini:

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env ps
```

Expected:

- Compose config exits `0`.
- No stale project containers are running unless a live QA session is already
  in progress.

Start the stack only after config is clean:

```bash
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
```

Expected:

- `db` is healthy.
- `backend` is reachable on host port `8000`.
- `frontend` is reachable on host port `5173`.

## Non-Generating Readiness Check

Health readiness loads provider configuration and credentials, but should not
submit a media generation request.

PowerShell:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health"
```

Expected response shape:

```json
{
  "ok": true,
  "ready": true,
  "service": "vertex-studio",
  "db": "up",
  "vertex": {
    "ready": true,
    "status": "ready",
    "credentials": "available",
    "project": "configured",
    "location": "us-central1"
  }
}
```

If `ready` is false, stop before any paid QA request and record only the public
readiness fields. Do not paste credential paths or JSON contents into notes.

## Poll Helper

The generation endpoints are asynchronous. Use a small polling helper for live
jobs:

```powershell
function Wait-Generation {
  param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [int]$MaxAttempts = 120,
    [int]$DelaySeconds = 5
  )

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    $job = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations/$JobId"
    if ($job.state -in @("completed", "failed", "cancelled")) {
      return $job
    }
    Start-Sleep -Seconds $DelaySeconds
  }

  throw "Generation $JobId did not reach a terminal state."
}
```

## Paid QA Sequence

Run the smallest useful set first. To control cost, run direct I2V or the
pipeline flow only if T2I passes. Do not run both direct I2V and pipeline unless
the reviewer specifically wants both paths proven in the same session.

### 1. Gemini Prompt Enhancement

This request can incur Gemini/Vertex cost.

```powershell
$enhanceBody = @{
  prompt = "A cinematic rainy Seoul alley at night with neon reflections"
  target_mode = "t2i"
  target_model = "imagen-4.0-fast-generate-001"
  creativity_preset = "balanced"
} | ConvertTo-Json

$enhancement = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/prompts/enhance" `
  -ContentType "application/json" `
  -Body $enhanceBody

$enhancement
```

Expected:

- Response includes `id`, `original`, `enhanced`, `components`,
  `target_mode`, `target_model`, `llm_model`, `creativity_preset`, and
  `temperature`.
- `llm_model` is `gemini-2.5-flash`.
- No generation job is created automatically.

### 2. Imagen Text-To-Image

This request can incur Imagen/Vertex cost.

```powershell
$t2iBody = @{
  mode = "t2i"
  prompt = "A cinematic rainy Seoul alley at night with neon reflections"
  model = "imagen-4.0-fast-generate-001"
  aspect_ratio = "1:1"
  number_of_images = 1
} | ConvertTo-Json

$t2iJob = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -ContentType "application/json" `
  -Body $t2iBody

$t2iDone = Wait-Generation -JobId $t2iJob.id -MaxAttempts 60 -DelaySeconds 5
$t2iDone
```

Expected:

- Job reaches `completed`.
- `mode` is `t2i`.
- `vertex_charged` is `true`.
- At least one asset exists with `kind=image`, `mime=image/png`, and a
  `/files/...` URL.

Optional asset fetch:

```powershell
$imageUrl = "http://127.0.0.1:5173$($t2iDone.assets[0].url)"
Invoke-WebRequest -Uri $imageUrl -OutFile "$env:TEMP\vertex-t2i-output.png"
```

### 3. Veo Text-To-Video

This request can incur Veo/Vertex cost and can take longer than T2I.

```powershell
$t2vBody = @{
  mode = "t2v"
  prompt = "A slow dolly forward through a rainy neon Seoul alley"
  model = "veo-3.0-fast-generate-001"
  aspect_ratio = "16:9"
  duration_sec = 4
} | ConvertTo-Json

$t2vJob = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -ContentType "application/json" `
  -Body $t2vBody

$t2vDone = Wait-Generation -JobId $t2vJob.id -MaxAttempts 180 -DelaySeconds 10
$t2vDone
```

Expected:

- Job reaches `completed`, or records a public provider error if Vertex rejects
  the request.
- `mode` is `t2v`.
- Successful jobs include `vertex_operation_name`, `vertex_charged=true`, and a
  `video/mp4` asset.

### 4. Veo Image-To-Video From T2I Asset

This request can incur Veo/Vertex cost. Only run it after the T2I job has a
usable image asset.

```powershell
$sourceAssetId = $t2iDone.assets[0].id

$i2vBody = @{
  mode = "i2v"
  prompt = "Slow camera push-in, rain ripples, subtle steam movement"
  model = "veo-3.0-fast-generate-001"
  source_asset_id = $sourceAssetId
  aspect_ratio = "16:9"
  duration_sec = 4
} | ConvertTo-Json

$i2vJob = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -ContentType "application/json" `
  -Body $i2vBody

$i2vDone = Wait-Generation -JobId $i2vJob.id -MaxAttempts 180 -DelaySeconds 10
$i2vDone
```

Expected:

- Job reaches `completed`, or records a public provider error if Vertex rejects
  the request.
- `mode` is `i2v`.
- `source_asset_id` matches the completed T2I image asset.
- Successful jobs include `vertex_operation_name`, `vertex_charged=true`, and a
  `video/mp4` asset.

### 5. T2I To I2V Pipeline

This flow can incur both Imagen and Veo cost. It proves parent/child pipeline
linking against real provider outputs.

```powershell
$pipelineBody = @{
  image_prompt = "A cinematic rainy Seoul alley at night with a cyclist"
  video_prompt = "Slow dolly forward as the cyclist passes and steam rises"
  image_model = "imagen-4.0-fast-generate-001"
  video_model = "veo-3.0-fast-generate-001"
  image_aspect_ratio = "1:1"
  video_aspect_ratio = "16:9"
  duration_sec = 4
} | ConvertTo-Json

$pipeline = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/pipelines" `
  -ContentType "application/json" `
  -Body $pipelineBody

$parentDone = Wait-Generation -JobId $pipeline.parent.id -MaxAttempts 60 -DelaySeconds 5
$pipelineState = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/pipelines/$($pipeline.parent.id)"
$childDone = Wait-Generation -JobId $pipelineState.child.id -MaxAttempts 180 -DelaySeconds 10

$pipelineState
$parentDone
$childDone
```

Expected:

- Parent job reaches `completed` with an image asset.
- Child job starts as blocked, then becomes unblocked after parent image asset
  linking.
- Child job uses the parent image asset as `source_asset_id`.
- Successful child jobs include `vertex_operation_name`, `vertex_charged=true`,
  and a `video/mp4` asset.

## Frontend Manual Review

After at least one live job completes, review these pages in the browser:

- `http://127.0.0.1:5173/generate`
- `http://127.0.0.1:5173/history`
- `http://127.0.0.1:5173/jobs/{job_id}`

Expected:

- API connection indicator is healthy.
- History shows live jobs with the correct mode/state/model.
- Completed image assets render as previews.
- Completed video assets render through `/files/...` and support preview
  playback.
- Job detail shows state history, request parameters, and asset previews.

## Recording Results

Record sanitized results in a follow-up memo under `memories/recovery/`.

Use only public, non-secret fields:

```markdown
| Check | Result | Evidence | Notes |
|---|---|---|---|
| Health | pass/fail | `ready=true`, `status=ready` | No secret values |
| Prompt enhance | pass/fail | enhancement id, model id | No prompt if proprietary |
| T2I | pass/fail | job id, final state, asset mime | No credential paths |
| T2V | pass/fail | job id, final state/public error | No raw provider secrets |
| I2V or pipeline | pass/fail | job ids, final states | No raw provider secrets |
```

Provider errors may be recorded only through the public API error shape:

- `code`
- `message`
- `retryable`
- `status_code`
- `operation_name`, only when it is already returned by the app response

Do not record service-account JSON content, API keys, private credentials, or
full terminal logs that include local secret paths.

## Shutdown And Hygiene

Stop the live QA stack when review is complete:

```bash
docker compose --env-file .env down
```

Use `down -v` only if deleting the local Postgres and asset volumes is
intentional.

Final hygiene checks:

```bash
git status --short --branch
git diff --cached --name-only
git ls-files --others --exclude-standard
```

Expected:

- No `.env`, service-account JSON, credential JSON, generated media, or secret
  material is staged.
- Any follow-up memo contains only sanitized public results.
- Compose containers are stopped unless a reviewer is still actively using the
  local stack.
