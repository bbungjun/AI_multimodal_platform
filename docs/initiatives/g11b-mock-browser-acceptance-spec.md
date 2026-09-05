# G11B mock browser/proxy/emergency acceptance

## Authorization and evidence boundary

Issue155, parent152. User requested mock-first execution, **gpt-6-astra design**
and **gpt-5.6-sol / medium implementation**. Design turn model was verified from
local turn metadata. No subagents or new Codex task; hand off the frozen plan to
the next turn of the same task with an explicit implementation model override.
G11A PR154 merged1214dfd, all required CI successful; preserve its failed proofs.

This slice supplies browser-to-real-frontend-to-loopback-proxy-to-real-backend
evidence missing from route-fixture UI tests. Google and AI providers are never
called. Ephemeral test Sessions are supplied out of band ONLY inside the owned
verifier; no product fake login endpoint, OAuth Adapter, auth dependency bypass,
role bypass, DB schema or frontend UX change is permitted.

**Not verified:** real Google callback/relogin, HTTPS termination, Secure-cookie
transport, deployed ingress/proxy, live revocation and provider/cloud behavior.
Parent152 stays open. Fresh test-session injection after revocation is mock
recovery, not a Google re-login or restoration of a revoked Session.

## One Module and Interface

One test-only acceptance Module, exposed as
`python scripts/verify_browser_acceptance.py`. No arbitrary URL, project, DB,
credential or port CLI options. The coordinator runs exactly two independent
cycles and emits safe result receipts. Runtime, subprocess protocol and fixtures
are internal implementation. Product HTTP/CLI Interfaces remain unchanged.

Reuse `scripts/mock_auth_support.py` OwnedRuntime: local Docker guard, random
`ownership-verify-<12hex>` project, nonce labels, exact .env.example, current
schema, loopback API port, DB/assets volumes and guarded cleanup. Do not edit that
module. Subclass only in the new support file to override test configuration:
AUTH_FRONTEND_ORIGIN and CORS_ORIGINS exactly `http://127.0.0.1:18155`,
AUTH_LOGIN_ENABLED=false, AUTH_COOKIE_SECURE=false, APP_ENV=local and AI_PROVIDER=mock.
All Google credential fields blank. Port18155 is reserved for this verifier;
preflight refuses occupied port, never adopts/stops an existing server. Remains
loopback-only. The cookie setting is test-local HTTP only, not a deployment change.

Use OwnedRuntime lifecycle directly rather than pretending this is an existing
ownership suite; its auth_proof has the old fixed Origin and does not fit this
browser fixture. Preserve its safety/360s work/90s cleanup limits. Pass the same
remaining monotonic deadline to every Docker/protocol/browser command.

### Browser Adapter

The Node runner uses installed frontend dependencies and a fresh Chromium process
(no user's browser/profile). Use programmatic Vite createServer with configFile:false,
envFile:false, explicit React plugin, silent logger, strict18155 loopback binding,
and real /api and /files proxy to the coordinator-validated backend loopback URL.
Explicit VITE_API_BASE empty; no local dotenv loading. No npm/package upgrades.
This does not require changing package.json, vite.config or playwright.config.

Three separate BrowserContexts: normal A, foreign B and Master. Fresh initial
secrets stay in coordinator/Node memory and piped stdin, never argv, environment,
disk, snapshots or output. Store only hashes in owned DB using test fixtures.
Cookies use exact loopback host, HttpOnly, SameSite=Lax, path=/, secure=false in
this local HTTP test. Real auth dependencies still validate them on every request.
Do not override request responses, use route.fulfill or synthesize API results.
Request interception may only continue the exact local origin or abort external
requests; report only counts. Block service workers; traces/video/screenshots,
storageState/HAR/error-context artifacts and console dumps off. Vite/HMR requests
are loopback-only. No actual Google domain may be reached.

UI assertions use existing accessible labels in App, UsagePage, MasterPage and
existing auth/usage/master tests. Read current source; do not invent selectors.
Browser fetch may admit a content-free fixture generation and inspect headers/
file bytes, but generation detail/Usage/Master mutations/Session reset must also
be observed in the real UI. Distinguish browser HTTP calls from clicked UI actions.

### Protocol and cleanup

Bounded JSON-lines between Python and Node: initial config/secrets goes stdin,
then fixed phase messages (ready, preview, execute, replay, recovery, complete).
Closed payload key sets, max line size, fixed phase order, per-phase timeout and
invalid/EOF refusal. No arbitrary commands/paths/IDs from Node control the CLI.
Only the initial secret payload and recovery secret payload carry test identity
in memory; no such fields may cross the result/evidence Interface.

The coordinator alone runs emergency CLI after verifying nonce ownership and
exact database name derived from its validated project. Preview/execute/replay
use `python -m app.auth.emergency --expected-database <owned_db> --reason
operator_drill`, adding exact `--execute --confirm REVOKE_ALL:<owned_db>` only
after preview. Parse the existing count-only CLI receipt; never output raw errors.
AUTH_LOGIN_ENABLED=false must first be observed through the browser's proxy via
the JSON start route503/login_disabled (no redirect followed externally).

Node closes every context/browser and Vite in finally. Parent has a bounded
graceful shutdown and fallback for its exact owned PID tree, never all Node/
Chromium processes. Drain/discard child stderr safely to avoid pipe deadlock;
only allowlisted diagnostic codes/phases/counts reach evidence. Verify child
termination and frontend port release, plus Docker containers/volumes/networks0.
Cleanup always runs after failure/interrupt/partial startup. Unknown ownership
stops destructive cleanup and reports the bounded failure. No development volumes.

## Eight ordered acceptance groups

1. **anonymous_proxy:** real app/login gate, JSON login-disabled503/no-store;
   no actual Google traffic; Vite proxy reaches ready mock backend.
2. **user_usage:** A and B show Free/current30-day cycle and seven meters; real
   Usage response private/no-store; ordinary User cannot see/access Master console.
3. **generation_ownership:** A admits one fast image through browser HTTP; worker
   completes, detail UI and PNG file work, Usage charge/zero held update; B gets
   404 for A's job and file. No prompt/raw body in evidence.
4. **master_commands:** actual Master UI changes A to Pro and grants fixed bonus;
   A refreshes Usage and sees persisted results; Audit UI shows each command once.
5. **suspension:** Master UI suspends A; A refresh returns401/no-store and private
   UI disappears. Reactivate via UI, old A cookie still401; no session resurrection.
6. **logout:** B uses actual logout control; stale UI/back navigation cannot restore
   protected data and /auth/me remains401/no-store.
7. **emergency:** Master still works before preview; preview mutates nothing,
   execute revokes all unrevoked test Sessions, active_after0; Master refresh401
   clears console; replay revoked0. Preserve all prior revoked rows and Job/Usage/
   Audit data. Local CLI/HTTP proof, not a deployed operator drill.
8. **mock_recovery:** test-only fixture appends fresh hash-only Sessions for A and
   Master without rewriting/deleting old rows; fresh contexts regain User/Master
   screens with previous Plan/Usage/Audit intact; old cookies still refused.
   Login admission remains disabled; this is test-session recovery only.

New fixture module runs only inside exact owned DB after provider/local/project/
schema/expected User inventory checks. Reuse existing hash-only initial ownership
seed; recovery accepts only the fixed A/Master case hash map, no arbitrary User
selector. Assert fresh hashes cannot equal old ones and old revocations persist.
No synthetic seed or development account promotion.

## Scope and completion

Exactly these eight allowed non-document paths, all new/test-only:

1. scripts/verify_browser_acceptance.py
2. scripts/browser_acceptance_support.py
3. frontend/tests/browser-acceptance-driver.mjs
4. frontend/tests/browser-acceptance-driver.test.mjs
5. backend/tests/test_verify_browser_acceptance.py
6. backend/tests/test_browser_acceptance_support.py
7. backend/tests/browser_acceptance_fixtures.py
8. backend/tests/test_browser_acceptance_fixtures.py

Migration0, product0, dependency/config/CI/cloud changes0. A ninth code path,
product fix or deadline relaxation requires stopping for redesign. No global
shared harness edits. One delivery slice, no second product Module.

Two new independent cycles, each8 groups/at least80 meaningful assertions and
cleanup0; no repeated checks used only to inflate counts. Each360s work/90s
cleanup;900s aggregate. Node scenario bounded180s within remaining work budget.
Startup readiness polls bounded by deadline, no arbitrary sleeps replacing state
checks. Preserve failure receipt; no automatic retry or timeout increase.

Regression: existing emergency verifier twice (120s work/60s cleanup), G11A
integrated once (it supplies2 cycles), auth once, Master suspension once,
full Windows backend (known Bash127 separate)/Linux CI, frontend lint/build,
Session70/Chromium61 and new Node unit suite. No need to rerun the unchanged full
G1-G10 matrix from G11A again unless a new defect changes the planned scope.
Safe portfolio/current-work/canonical updates; final Ready PR and final-head
verify plus both Scan/SBOM SUCCESS, squash auto-merge/actual MERGED, #155 closed,
main synchronized. Keep #152 OPEN and all actual OAuth/TLS/cloud gates explicit.
