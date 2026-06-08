# Troubleshooting Notes

This file preserves debugging lessons that are useful for production work.

## Health Is Not A Full Live QA

`/api/health` can show that the backend can configure a provider client, but it
does not prove model access, quota, billing, safety behavior, or live generation
quality. Treat health as a readiness gate before live QA, not as complete proof.

## Async ORM Lazy Loading

Avoid building API DTOs from lazily loaded SQLAlchemy relationships after the
async session context has moved on. Prefer explicit eager loading or explicit
queries for assets and relationships used in response models.

## Mock Provider Must Stay Credential-Free

Mock mode is a core development and test path. If a mock-mode test constructs a
Vertex client or needs credentials, the provider boundary has leaked.

## Frontend Host And Proxy Configuration

The frontend uses Vite and can proxy `/api` and `/files` to the backend. Keep
`VITE_API_BASE`, `VITE_API_PROXY_TARGET`, and allowed hosts aligned with the
current environment.

## Docker Credential Mounts

Host credential paths and container credential paths are different. Docker
Compose should mount the host file to the exact container path referenced by
`GOOGLE_APPLICATION_CREDENTIALS`.

Do not print credential file contents while debugging. Check only whether the
path exists and whether public readiness fields are configured.

## Pipeline Failures

If an I2V child starts too early, check parent completion, image asset creation,
`source_asset_id`, and the blocked/unblocked transition. The child job should
not run until a valid source image asset is linked.
