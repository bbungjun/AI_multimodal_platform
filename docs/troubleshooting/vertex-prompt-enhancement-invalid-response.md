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

## 2026-07-15 retry evidence: unclassified HTTP request failure

After the persistence fix was merged, a fresh clean-main preflight and the
20-case `benchmark.v2.jsonl` mock gate passed. The user-approved retry
`issue66-vertex-main-5c87022-001` completed two Raw/Enhanced pairs, using three
enhancement HTTP requests, four generation HTTP requests, and eight requested
images. The seventh ledger event had `failure_type=HttpRequestError`.

The normalized HTTP status, public provider code, reason, field, and source
were all absent because this was not an HTTP error response. The ledger records
the request from `00:59:26.491Z` to `00:59:36.504Z`, which matches the
evaluation runner's hard-coded 10-second `HttpClient` deadline. `run_vertex_pilot`
constructed that client without overriding the default. No third enhancement
row was persisted in Postgres during the following minute. The runner correctly
closed the manifest as `failed` with generic public code
`vertex_pilot_request_failed`; it did not make a replacement request.

## 2026-07-16 timeout fix

Commit `4fe3887` adds a policy-bound evaluation HTTP deadline to the pilot.
The later contract-repair follow-up raises `limits.http_timeout_sec` to `180.0`
to allow all three permitted provider call groups to finish. The runner
classifies a socket deadline as `HttpRequestTimeoutError` and records only
`failure_reason=client_timeout` plus `timeout_sec` in `pilot_usage.json`.

The delayed-timeout unit test, 69-test evaluation suite, clean preflight, and
fresh 20-case mock gate all passed.

## 2026-07-16 revised-deadline evidence

User-approved run `issue66-vertex-timeout-594fdf3-001` completed seven pairs
before its next enhancement ended at `60,006 ms`. Its ledger safely recorded
`HttpRequestTimeoutError`, `failure_reason=client_timeout`, and
`timeout_sec=60.0`; no HTTP response reached the runner.

The backend and worker both had `OOMKilled=false` and restart count `0`.
Before the stack was stopped, the backend recorded safe provider code
`prompt_enhancement_invalid_response` with no provider status. The longer
deadline therefore rules out the prior 10-second runner setting as the only
cause: the delayed backend request still reached Gemini response-contract
validation. Do not retry this prompt automatically. Reproduce the invalid
response with a prompt-free fixture, preserve an operator-safe validation
reason, and fix the contract path before another paid run.

## Contract-repair fixture and path

The enhancement path now allows the policy's three permitted provider call
groups: the initial structured response, a STRICT JSON repair, and one final
CONTRACT REPAIR. The last repair requires a compact object with non-empty
`enhanced` text and non-empty string-valued `components`, including
`provider_prompt_en`. A safe fake client reproduces two schema-invalid payloads
followed by a valid third payload; a separate fixture proves three invalid
payloads still terminate as `prompt_enhancement_invalid_response` without raw
response text.

This is a bounded recovery path, not an automatic replacement run. Fresh
preflight and mock evidence plus explicit approval remain required before any
future paid execution.
