# k6 GCP Load Test Runbook

Use this runbook to run bounded k6 load tests against the live GCP GKE
deployment. The current live frontend URL is recorded in `docs/current-work.md`.

## Safety

- Do not print `.env`, ADC files, service-account JSON, API keys, private keys,
  DB passwords, Terraform state, `backend.hcl`, `.tfvars`, or Kubernetes Secret
  payloads.
- The default k6 profile does not create media and does not call Imagen or Veo.
- The prompt profile calls live Gemini prompt enhancement and can create Vertex
  cost. It requires `ALLOW_VERTEX_PROMPT=1`.
- Imagen and Veo load tests are intentionally not included here. Add a separate
  cost-aware issue before load testing generation endpoints.

## Prerequisites

Install k6 locally or use the Windows `k6.exe` from WSL.

```bash
k6 version
# or from WSL when k6 is installed on Windows:
k6.exe version
```

Set the target URL explicitly:

```bash
export BASE_URL="http://34.50.26.152"
```

## Readiness Profile

This profile loads the frontend, `/api/health`, and `/api/ops/health`.

```bash
k6 run \
  -e BASE_URL="$BASE_URL" \
  -e PROFILE=readiness \
  -e EXPECTED_VERTEX_STATUS=ready \
  -e READINESS_MAX_VUS=10 \
  scripts/k6/creativeops_gcp_load.js
```

From WSL with Windows k6, copy the script to the Windows temp directory first:

```bash
WIN_TEMP="$(powershell.exe -NoProfile -Command '$env:TEMP' | tr -d '\r')"
WIN_TEMP_WSL="$(wslpath -u "$WIN_TEMP")"
mkdir -p "$WIN_TEMP_WSL/creativeops-k6"
cp scripts/k6/creativeops_gcp_load.js "$WIN_TEMP_WSL/creativeops-k6/"
SCRIPT_PATH="$(wslpath -w "$WIN_TEMP_WSL/creativeops-k6/creativeops_gcp_load.js")"

k6.exe run \
  -e BASE_URL="$BASE_URL" \
  -e PROFILE=readiness \
  -e EXPECTED_VERTEX_STATUS=ready \
  -e READINESS_MAX_VUS=10 \
  "$SCRIPT_PATH"
```

Default thresholds:

- checks rate greater than 99%
- HTTP failure rate below 1%
- p95 request duration below 1000 ms

## Vertex Prompt Profile

This profile calls live Gemini prompt enhancement through
`POST /api/prompts/enhance`. The default rate is intentionally conservative;
increase `PROMPT_RATE` for stress runs.

```bash
k6 run \
  -e BASE_URL="$BASE_URL" \
  -e PROFILE=prompt \
  -e ALLOW_VERTEX_PROMPT=1 \
  -e PROMPT_RATE=3 \
  -e PROMPT_DURATION=2m \
  scripts/k6/creativeops_gcp_load.js
```

From WSL with Windows k6, copy the script to the Windows temp directory first:

```bash
WIN_TEMP="$(powershell.exe -NoProfile -Command '$env:TEMP' | tr -d '\r')"
WIN_TEMP_WSL="$(wslpath -u "$WIN_TEMP")"
mkdir -p "$WIN_TEMP_WSL/creativeops-k6"
cp scripts/k6/creativeops_gcp_load.js "$WIN_TEMP_WSL/creativeops-k6/"
SCRIPT_PATH="$(wslpath -w "$WIN_TEMP_WSL/creativeops-k6/creativeops_gcp_load.js")"

k6.exe run \
  -e BASE_URL="$BASE_URL" \
  -e PROFILE=prompt \
  -e ALLOW_VERTEX_PROMPT=1 \
  -e PROMPT_RATE=3 \
  -e PROMPT_DURATION=2m \
  "$SCRIPT_PATH"
```

Default prompt thresholds:

- checks rate greater than 95%
- HTTP failure rate below 5%
- p95 request duration below 30000 ms

If this profile fails, treat it as a Vertex prompt reliability signal. The
script logs only failed HTTP status codes, not response bodies. HTTP 429 points
to quota or rate limiting, while HTTP 502 usually means the API mapped a
non-retryable provider/prompt-enhancement error to a gateway response. Do not
loosen thresholds just to hide these failures.

## Mixed Profile

Use this only when both frontend/API readiness and bounded Gemini prompt load
should run at the same time.

```bash
k6 run \
  -e BASE_URL="$BASE_URL" \
  -e PROFILE=mixed \
  -e EXPECTED_VERTEX_STATUS=ready \
  -e ALLOW_VERTEX_PROMPT=1 \
  -e READINESS_MAX_VUS=10 \
  -e PROMPT_RATE=3 \
  -e PROMPT_DURATION=2m \
  scripts/k6/creativeops_gcp_load.js
```

## Evidence To Record

Record only public-safe results:

- profile
- target URL
- VU or request rate settings
- checks rate
- HTTP failure rate
- request duration p95
- prompt request count if using the prompt profile

Do not record raw prompts beyond generic public-safe test prompts, response
bodies, credential paths, Secret payloads, or provider logs containing private
data.
