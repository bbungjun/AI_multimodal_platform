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

## Vertex Mode

`AI_PROVIDER=vertex` is the real provider mode.

Vertex mode:

- uses the `google-genai` SDK only
- constructs a shared `genai.Client(vertexai=True, ...)`
- supports ADC or an explicitly mounted credential file
- requires `GCP_PROJECT_ID` and `GCP_LOCATION`
- may create billable Gemini, Imagen, or Veo requests

Health readiness confirms that backend configuration and credentials can create
the client. It does not prove every model is enabled or quota is available.
Live generation checks are separate manual QA steps.

## Credentials

Do not commit credentials, `.env`, API keys, or service-account JSON files.

For local host execution, ADC can be created with Google Cloud tooling and used
by `google-auth`. For Docker execution, mount the host credential file into a
container path and set `GOOGLE_APPLICATION_CREDENTIALS` to that container path.

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
