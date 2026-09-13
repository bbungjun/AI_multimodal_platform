# Issue162 — Test-only mock Google OAuth browser journey

Status: Mock Verified at core `c3b1b6b` and protected delivery completed through
[PR163](https://github.com/bbungjun/AI_multimodal_platform/pull/163), squash
`ba24316`.

## Background and problem

The production login button correctly calls `/api/auth/google/start`, but local
credential-free Compose returns `auth_not_configured`. Existing browser suites
either intercept frontend HTTP or seed hash-only Sessions. They prove Session UX
and authenticated product behavior but do not prove that a browser can cross the
real start/callback/flow/cookie boundary without contacting Google.

AI-assisted E2E work needs a deterministic authentication entry point. Adding a
product mock-login route would weaken the deployed boundary and contradict the
single product-login policy, so the replacement must exist only inside an owned
test runtime.

## Observation and diagnosis

The visible login page exposed a plain React button. Source and access logs
confirmed `GET /api/auth/me -> 401` followed by
`GET /api/auth/google/start -> 303` when Google settings were absent. The
existing Google adapter already separates authorization URL construction and
code exchange from `AuthService`, so dependency injection can replace the
outbound provider while preserving Redis, PostgreSQL and cookies.

Three failed harness attempts were retained as engineering findings:

- Detached Compose briefly returned the backend in `created` state, so an
  immediate running-only `ps -q` produced no container id. The verifier now
  resolves the owned container with `ps --all` and waits at most 30 seconds for
  one loopback port binding.
- The first override expected a prior verifier origin while the inherited
  Compose fragment contained `http://localhost:5173`; the test app correctly
  refused to start. The replacement now targets the exact inherited value and
  the unit contract asserts the fixed `18156` origin.
- The first browser completion checked the workspace immediately after URL
  navigation, before React finished `/api/auth/me`. The browser now waits for
  the authenticated workspace element within Playwright's bounded timeout.

No failure was bypassed by sleeps, credential injection, a product endpoint, or
weaker assertions.

## Solution and safety decisions

`backend/tests/mock_oauth_app.py` is an alternate Uvicorn test entry point. It
imports the unchanged product app and overrides only `get_auth_service` with an
`AuthService` using the real database Session factory and Redis flow store plus
a deterministic no-network Google adapter. Import refuses unless all of these
are true: `APP_ENV=test`, `AI_PROVIDER=mock`, fixed loopback frontend origin,
insecure local cookie mode, login enabled, and empty Google settings.

The browser follows the unchanged product URLs. The mock authorization URL is a
same-origin callback containing one in-memory test code; the existing auth log
filter removes callback query values. The driver blocks and counts every
non-frontend-origin browser request. It emits only groups, checks, external
request count and cleanup status—never OAuth values, cookies, fixture identity,
headers, prompts, response bodies, or raw logs.

Every cycle owns a random labelled Compose project, dynamic loopback backend
port, fresh PostgreSQL and ephemeral Redis, fixed collision-checked frontend
port, Node process and Chromium. Cleanup verifies exact labels before removing
only that cycle's containers, volumes and network.

Rollback is deletion of the five test-only code paths. There is no schema,
product configuration or persistent developer-data rollback.

## Verification

Core checkpoint `c3b1b6b`:

```powershell
python scripts/verify_mock_oauth_browser.py
# complete=true, cycles=2, groups=6, checks=20,
# external_requests=0, cleanup=0

cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_verify_mock_oauth_browser.py tests/test_auth_api.py tests/test_auth_service.py tests/test_google_identity_adapter.py -q
# 70 passed, 2 guarded skips

cd ../frontend
node --test tests/mock-oauth-browser-driver.test.mjs
# 2 passed
npm run lint
npm run build
# PASS

cd ..
docker compose --env-file .env.example config --quiet
git diff --check
# PASS
```

The two browser cycles independently covered login start, callback Session,
authenticated profile, logout, consumed-flow replay refusal and re-login. Each
reported six groups, ten checks, zero external requests and zero owned resources
after cleanup.

Final documented head `d2f7422` repeated the same two-cycle receipt with
20 aggregate checks, external requests zero and cleanup zero. The full Windows
quality gate ran1808 backend tests:1804 passed, three guarded tests skipped and
only the already-documented Bash/Windows absolute-path syntax check failed with
exit127. Rerunning the complete suite with that exact one test deselected passed
1804 with three skips. This host limitation is not counted as an Issue162
product or harness regression.

## Result and impact

Local E2E automation can now begin from the real login button and reach an
authenticated workspace without Google credentials or network traffic. This
closes the deterministic OAuth-flow gap while preserving production behavior
and gives later AI QA work a stable, replayable authentication boundary.

## Remaining risks and next steps

- This does not validate Google consent, token semantics, deployed callback URI,
  TLS, Secure cookies, ingress/proxy behavior or account policy.
- The fixed loopback port intentionally prevents concurrent runs of this
  verifier; collision is a safe refusal.
- Structured request events, cross-service trace bundles and AI-generated test
  candidates are not implemented here. They should remain separate Issues so
  observability schema, evidence sanitization and generated-test review can be
  accepted independently.
