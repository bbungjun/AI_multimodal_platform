# Vertex Prompt Enhancement Invalid Response

## Symptom

The Vertex pilot can stop at `POST /api/prompts/enhance` with public code
`prompt_enhancement_invalid_response`. The API maps this contract failure to
HTTP 502. It is distinct from credential, quota, rate-limit, or Vertex 5xx
failures.

The provider response reached the application, but it did not satisfy the
prompt-enhancement response contract. Possible contract failures include
malformed JSON, missing or empty required fields, schema validation failure, or
an invalid language result. Do not infer the exact subreason unless the
prompt-free failure metadata records it.

## Immediate containment

1. Do not create a replacement run or retry the failed step automatically.
2. Preserve the failed run directory and its `pilot_usage.json` ledger.
3. Stop the Vertex Compose stack after collecting public evidence; do not delete
   volumes or rewrite the failed manifest.
4. Record only request counts, public code, HTTP status, and normalized
   `reason`/`field`/`source` metadata. Never copy prompts, raw model responses,
   tokens, ADC content, or authorization headers into an issue or document.

## What to inspect

`pilot_usage.json` must retain these safe fields for a failed API request:

- `http_status`
- `provider_failure_code`
- `failure_reason`
- `failure_field`
- `failure_source`
- `failure_type`

The run `manifest.json` must end in `lifecycle=failed` and contain a generic
`last_error`. If either artifact omits the failure state, treat that as a runner
defect; the ledger remains the request-count source of truth.

## Root-cause workflow

1. Reproduce the API contract failure with a mock HTTP client that returns a
   normalized public error body. Assert that no prompt or raw response is
   written into the ledger or manifest.
2. Fix the persistence boundary before any additional Vertex request:
   preserve only public error metadata in the ledger and atomically set the
   manifest to `failed`.
3. Run the focused evaluation tests and the no-cost mock gate.
4. Because a code change creates a new Git revision, regenerate the clean
   preflight and 20-case mock evidence. Obtain a new plan-specific approval
   that accounts for all earlier billable requests before attempting another
   live run.

## 2026-07-15 incident evidence

Real run `issue66-vertex-main-6f2f0ce-002` completed one Raw/Enhanced pair,
then the next enhancement request returned
`prompt_enhancement_invalid_response`. Its ledger recorded two enhancement
requests, two generation requests, four requested images, and one failed HTTP
request. The original runner left its manifest in `enhancing` without
`last_error`; this document and the accompanying persistence fix track that
gap. This partial run is not benchmark-quality evidence.
