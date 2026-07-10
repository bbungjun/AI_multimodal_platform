# Provider Modes

CreativeOps Studio supports two provider modes so development can stay
cost-free while the same app can run real Vertex AI jobs when explicitly
configured.

## Mock Mode

`AI_PROVIDER=mock` is the deterministic local and test mode.

Mock mode:

- does not require Google credentials
- must not construct a Vertex client
- returns deterministic PNG bytes for text-to-image flows
- returns deterministic MP4 placeholder bytes for video flows
- returns deterministic prompt enhancement drafts
- keeps API, job runner, storage, and frontend previews testable without paid AI
  calls

Use mock mode for normal development, automated tests, and no-cost smoke checks.

For backend tests only, an Imagen prompt containing the exact sentinel
`[[mock-fail:imagen]]` forces a deterministic mock provider failure. This is a
test trigger for failed-job contracts and pipeline cascade behavior; it is not a
normal user workflow.

## Vertex Mode

`AI_PROVIDER=vertex` is the real provider mode.

Vertex mode:

- uses the `google-genai` SDK only
- constructs a shared `genai.Client(vertexai=True, ...)`
- supports ADC, an explicitly mounted credential file, or
  `GOOGLE_APPLICATION_CREDENTIALS_JSON` injected by a secret manager
- requires `GCP_PROJECT_ID` and `GCP_LOCATION`
- uses `ENHANCE_MODEL` as the runtime-selected Gemini model for prompt
  enhancement, with `gemini-2.5-flash` as the default
- may create billable Gemini, Imagen, or Veo requests
- retries Gemini prompt-enhancement provider calls for retryable Vertex
  failures such as 429 rate limits and transient 5xx/timeouts using the
  configured `PROVIDER_RETRY_*` backoff policy
- retries invalid Gemini prompt-enhancement payloads once with stricter JSON
  repair instructions before returning the stable public
  `prompt_enhancement_invalid_response` error
- retries prompt-enhancement language mismatches once, then returns
  `prompt_enhancement_invalid_response` with reason `language_mismatch` if the
  retry still ignores the requested display language

Health readiness confirms that backend configuration and credentials can create
the client. It does not prove every model is enabled or quota is available.
Live generation checks are separate manual QA steps.

## Credentials

Do not commit credentials, `.env`, API keys, or service-account JSON files.

For local host execution, ADC can be created with Google Cloud tooling and used
by `google-auth`. For Docker execution, mount the host credential file into a
container path and set `GOOGLE_APPLICATION_CREDENTIALS` to that container path.
For AWS ECS execution, store the service-account JSON in Secrets Manager and
inject it as `GOOGLE_APPLICATION_CREDENTIALS_JSON`; do not put the JSON into
Terraform variables or committed `.env` files.

The app should treat credential contents as opaque. It only needs the runtime
credential object, project id, and location.

## Boundary Rules

- API routes, database models, job handlers, storage, and frontend code should
  not need to know whether the active provider is mock or Vertex.
- Provider selection belongs inside the service boundary.
- Automated tests should patch or fake provider calls instead of relying on
  live external services.
- Real provider flows should include visible cost and readiness cues before
  generation requests are sent.
