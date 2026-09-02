# G3 Backend Google OAuth and Session Lifecycle Specification

## Status

- Specification: `Accepted`
- Implementation: `Implemented`
- Evidence level: `Mock Verified` (not live Google/browser verification)
- Base: merged G2 on `main` at `58f405b`
- Tracker: [Issue #98](https://github.com/bbungjun/AI_multimodal_platform/issues/98)
- Branch: `codex/issue-98-auth-session-lifecycle`
- Goal plan: `.omo/plans/issue-98-g3-auth-session-lifecycle-goal.md`
- Goal plan SHA-256:
  `95dd3c913c080a2550e77ed39c2948e1ca24d779dd2bc3a85ee396e827c4da6c`
- Accepted planning checkpoint: `fa19ae0`
- Verified code/test checkpoint: `ec42d61`; 17 non-document paths, zero migrations.
- Evidence: [Issue #98 portfolio record](../portfolio/issue-98-auth-session-lifecycle.md).
- Delivery: [PR #100](https://github.com/bbungjun/AI_multimodal_platform/pull/100),
  strict required checks and squash auto-merge; current delivery status is on PR.
- Fresh Postgres/Redis proofs: `auth-verify-d44013ba240b` and
  `auth-verify-d462709efd3b`; HTTP-to-storage, rollback, concurrency,
  expiry, replay and Redis outage/recovery passed; cleanup passed.
- Existing mock generation golden path: `auth-verify-golden0298` passed at
  `ec42d61`. Redis RDB/AOF are explicitly disabled and runtime-checked.
- Live operational readiness remains blocked by
  [Issue #99](https://github.com/bbungjun/AI_multimodal_platform/issues/99),
  proxy query-redaction verification and the later real-browser gate.

This specification narrows G3 to one deep backend authentication module. It
turns Google's verified identity into a bounded CreativeOps Studio Session and
offers one request-authentication seam to later ownership work. Browser workspace
UX belongs to G3.1. Master promotion, suspension mutation, audit, and console
work belong to G10.

## Outcome

After G3, a browser can begin Google Authorization Code Flow, complete a backend
callback, receive a server-managed Session cookie, inspect its own safe profile,
and log out. Later modules can require an authenticated User without knowing
Google, cookies, token hashing, expiry, activity touch, or Session eviction.

G3 is `Mock Verified` only after deterministic fake-Google tests, real isolated
Postgres and Redis lifecycle tests, and the existing mock generation golden path
pass. It does not claim a real Google login, frontend login experience, cloud
deployment, content ownership, credit enforcement, or Master operations.

## Accepted Policy Inputs

- Google OAuth is the only product login method; no password or product mock
  login route exists.
- Authorization Code Flow uses PKCE S256 and validates both `state` and `nonce`.
- Google `sub` is the identity key. Email, display name, and picture are mutable
  profile fields and never drive identity lookup.
- Authorization codes, ID tokens, access tokens, refresh tokens, PKCE verifiers,
  raw Session secrets, and OAuth flow secrets are never persisted in Postgres.
- Session storage contains only the SHA-256 digest introduced by G2.
- Inactivity expiry is 12 hours; absolute expiry is exactly seven days.
- A User may have at most five Active Sessions.
- A sixth successful login revokes the oldest Active Session ordered by
  `(created_at, id)` and admits the new Session in the same User-locked
  transaction.
- Authentication updates `last_seen_at` only when its stored value is at least
  five minutes old. Every request still evaluates both expiry limits.
- A suspended User cannot establish or use a Session.

Google's current OpenID Connect reference confirms that `sub`, not email, is the
stable identifier and that ID tokens require issuer, audience, expiry, signature,
and nonce validation. The web-server flow keeps the code exchange in the
backend. References:

- [Google OpenID Connect reference](https://developers.google.com/identity/openid-connect/reference)
- [Google OAuth web-server applications](https://developers.google.com/identity/protocols/oauth2/web-server)

## Alternatives and Trade-offs

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Sixth login | Evict oldest Active Session | Reject the new login | Preserves access on the device in front of the User while keeping a deterministic five-Session cap. The trade-off is that an older device signs out without an interactive warning. |
| Activity writes | Conditional touch every five minutes | Write every request; never touch | Bounds write amplification while preserving a meaningful sliding 12-hour inactivity limit. The observed inactivity timestamp may lag real activity by less than five minutes. |
| Product Session | Opaque random secret with Postgres digest | Self-contained JWT | Immediate revocation, suspension, Session cap, and activity expiry require authoritative server state; a JWT would duplicate or weaken those checks. |
| OAuth flow state | One-time Redis record keyed by flow-secret digest | Durable Postgres row; signed browser payload | Flow state is transient and replay-sensitive. Redis supplies TTL and atomic consumption without durable protocol debris; login becomes temporarily unavailable when Redis is unavailable. |
| Provider integration | Internal Google seam with production and fake adapters | Product mock-login route | Tests exercise the same deep module without creating a deployable authentication bypass. |
| Delivery size | Backend G3, browser G3.1, Master operations G10 | One full-stack authentication Goal | Smaller interfaces keep security, transaction, UX, and operations review independently verifiable within the context budget. |

## Scope

### Must Have

- A deep authentication module whose external interface covers login start,
  callback completion, Session authentication, and logout.
- A true-external Google identity seam with a production adapter and deterministic
  fake adapter used only by tests.
- A transient OAuth flow-store seam with Redis and in-memory test adapters.
- One-time, ten-minute OAuth flow records containing state, nonce, PKCE verifier,
  and safe return path. Consumption is atomic.
- Cryptographically random flow, state, nonce, PKCE, and Session material.
- Google ID-token verification for signature, issuer, audience, expiry, nonce,
  required `sub`, required email, and `email_verified=true`.
- Transactional OAuth User upsert that never overwrites role, status,
  `signed_up_at`, or suspension fields from provider claims.
- Transactional five-Session enforcement and deterministic oldest-session
  eviction under a User row lock.
- Constant-shape public authentication failures without raw provider details.
- `HttpOnly` host-only cookies with `SameSite=Lax`, bounded lifetime, explicit
  path, and `Secure=true` outside an explicit local/test override.
- Exact trusted-Origin checks for cookie-authenticated unsafe requests.
- Safe configuration, mock-only automated verification, local runbook, and
  portfolio evidence.

### Must Not Have

- A product fake-login route, password, bearer-token login, magic link, or a
  second identity provider.
- OAuth access beyond `openid email profile`, offline access, or a dependency on
  refresh tokens.
- Durable persistence or logging of raw credentials, authorization code,
  provider token, PKCE verifier, nonce, state value, flow secret, Session secret,
  or cookie. The ten-minute Redis flow record is the only approved transient
  storage for nonce and PKCE verifier.
- A new Alembic migration or a change to G2 table meaning.
- Job, Prompt Enhancement, Asset ownership, Plan, Credit, Usage, Reservation,
  Settlement, Audit, or concurrency enforcement.
- Frontend login controls, workspace gate, profile menu, or browser E2E; those
  belong to G3.1.
- Master promotion, suspension mutation, last-Master protection, operations CLI,
  or console; those belong to G10. Authentication only honors existing role and
  status values.
- Vertex/Gemini/Imagen/Veo calls, cloud deployment, Kubernetes, or Terraform.

## Domain Invariants

`Active Session` means all of the following at one database evaluation time:

- `revoked_at IS NULL`;
- `absolute_expires_at > now`;
- `last_seen_at > now - 12 hours`;
- its User has `status=active`.

Therefore `revoked_at IS NULL` alone is not an Active Session query. G3 may mark
an expired Session revoked lazily with `absolute_expired` or
`inactivity_expired`, but correctness cannot depend on cleanup having run.

OAuth profile refresh changes only `email`, `email_verified`, `display_name`,
`profile_image_url`, and `updated_at`. A provider callback cannot promote a User,
reactivate a suspended User, change `signed_up_at`, or turn a Synthetic User into
an OAuth User.

## Deep Module and Seams

The external seam is an `AuthService`-equivalent interface. Names may be refined
during the Goal, but callers and tests must require no more behavior than:

```python
begin_google_login(return_to: str) -> LoginStart
complete_google_login(flow_secret: str, state: str, code: str) -> LoginCompletion
authenticate(session_secret: str) -> AuthenticatedUser
logout(session_secret: str | None) -> LogoutResult
```

The interface includes these non-type facts:

- all timestamps come from one injected UTC clock per operation;
- callback completion is transactional after identity verification;
- `LoginCompletion` exposes a raw Session secret exactly once for cookie
  issuance and never stores or logs it;
- `AuthenticatedUser` contains internal User ID, role, status, and safe profile,
  never provider or Session credentials;
- logout is idempotent and always permits cookie deletion;
- domain failures are typed internally and mapped to bounded public codes at the
  HTTP seam.

The module owns SQLAlchemy transaction ordering and Session lifecycle policy.
There must not be a shallow repository layer that merely mirrors ORM calls.

### Internal Google Identity Seam

The Google adapter accepts authorization parameters and exchanges a code for a
verified identity. Its output is a small immutable value containing only
`sub`, verified email, optional display name, and optional picture URL.

The production adapter:

- builds the authorization URL with `response_type=code`, scopes
  `openid email profile`, query response mode, PKCE S256, state, and nonce;
- requests online access only;
- exchanges the code on the backend with an explicit timeout;
- verifies signature, issuer, audience, expiry, nonce, and required claims;
- discards all provider tokens immediately after mapping the verified identity;
- maps timeout, denial, malformed response, and verification failure without
  exposing provider payloads.

The deterministic fake adapter exists only behind dependency injection in tests.
No application setting may expose it as a product login route.

### Internal OAuth Flow-Store Seam

Redis is the production adapter because OAuth flow state is short-lived,
one-time, and not part of durable User history. The browser receives an opaque
flow cookie; Redis is keyed by its SHA-256 digest and holds the state digest,
nonce, PKCE verifier, safe return path, and creation time for at most ten
minutes.

Callback consumes the record atomically before code exchange. Missing, expired,
replayed, cookie-mismatched, or state-mismatched flows all produce the same safe
public failure class. Redis unavailability fails login closed and does not make
the core application unready.

An in-memory adapter supplies the second implementation for focused tests. It
must preserve one-time consume and expiry semantics rather than becoming a
looser fake.

## Transaction Algorithms

### Callback Completion

1. Atomically consume and validate the OAuth flow before provider exchange.
2. Exchange the authorization code and verify the ID token through the Google
   adapter; retain only the verified identity value.
3. Begin a Postgres transaction and upsert by `google_sub`.
4. On first signup, create an active OAuth User with role `user`; on later login,
   update mutable profile fields only.
5. Lock the exact User row. Reject a suspended User without creating a Session.
6. Evaluate Sessions against one database `now`; mark already expired rows with
   bounded revoke reasons.
7. Lock remaining Active Sessions. If five remain, revoke exactly the oldest by
   `(created_at, id)` as `session_limit_eviction`.
8. Generate a new Session secret, persist only its SHA-256 digest, and set
   `created_at=last_seen_at=now` and `absolute_expires_at=now+7 days`.
9. Commit, return the secret once, set the Session cookie, clear the flow cookie,
   and redirect only to the previously validated local return path.

The User lock serializes concurrent callbacks for one User, so two simultaneous
sixth logins cannot leave more than five Active Sessions. Different Users do not
share that lock.

### Request Authentication

1. Missing cookie returns the generic unauthenticated result without a database
   write.
2. Hash the presented secret and load Session plus User using the digest index.
3. Reject a missing, revoked, absolutely expired, inactive, or suspended Session
   using one public `authentication_required` shape.
4. Expired or suspended paths may apply bounded revocation codes in the same
   transaction, but never extend validity.
5. If still Active and `last_seen_at <= now-5 minutes`, issue a conditional
   update with the previously read timestamp. Concurrent requests may produce at
   most one effective touch for that window.
6. Return `AuthenticatedUser`. Never return the Session digest or row ID to the
   caller.

### Logout

Hash a present Session secret, revoke a matching non-revoked Session as
`user_logout`, and return success whether the cookie was absent, unknown,
expired, or already revoked. The HTTP adapter always emits an expired cookie
with the same attributes used at issuance.

## HTTP Contract

| Method and path | Success | Notes |
|---|---:|---|
| `GET /api/auth/google/start?return_to=/...` | `307` | Sets flow cookie and redirects to Google |
| `GET /api/auth/google/callback` | `303` | Sets Session cookie, clears flow cookie, redirects to safe local path |
| `GET /api/auth/me` | `200` | Returns User ID, role, and safe profile only |
| `POST /api/auth/logout` | `204` | Requires trusted Origin, revokes if present, always clears cookie |

`return_to` must be a relative path beginning with one `/`, must not begin with
`//`, contain a scheme or host, include control characters, or exceed 512 bytes.
The fallback is `/`.

Callback failures clear the flow cookie and redirect to one configured local
login-error path with only a bounded error code. No authorization code, state,
provider message, email, or token is placed in the redirect.

Google's query response mode places the short-lived authorization code and state
in the callback URL. G3 must install and test an access-log sanitizer before the
route is enabled so Uvicorn records only the callback path, never its query.
Callback responses set `Cache-Control: no-store` and
`Referrer-Policy: no-referrer`, then immediately redirect to a clean local URL.
Deployment proxies and load balancers remain a later environment-specific
verification gate and must apply the same query-redaction rule before live
OAuth is claimed.

Public error classes are intentionally small:

- `auth_not_configured` (`503`) for missing required OAuth configuration;
- `oauth_flow_invalid` for missing, expired, replayed, or mismatched flow;
- `oauth_denied` for explicit user denial;
- `oauth_provider_unavailable` for bounded provider timeout/5xx cases;
- `oauth_identity_rejected` for unverified or invalid identity;
- `authentication_required` (`401`) for every unusable Session state;
- `origin_not_allowed` (`403`) for unsafe cookie-authenticated requests.

Logs may contain the public code, request ID, and operation duration. They must
not contain identity profile values or any raw protocol/session material.

## Cookie Contract

Session cookie:

- host-only name `creativeops_session`;
- `HttpOnly`, `SameSite=Lax`, `Path=/`;
- `Secure=true` by default and mandatory outside `local` or `test`;
- `Max-Age=604800`, while the database remains authoritative for both expiry
  rules;
- no Domain attribute and no JavaScript-readable duplicate.

OAuth flow cookie:

- host-only name `creativeops_oauth_flow`;
- `HttpOnly`, `SameSite=Lax`, callback-only Path, ten-minute maximum age;
- same Secure policy as the Session cookie;
- deleted on every callback outcome.

An explicit insecure-cookie override may operate only in `APP_ENV=local|test`.
Startup refuses that override in any other environment.

## Configuration Contract

Only backend needs these values:

- Google OAuth client ID and opaque client secret;
- exact callback URI;
- safe frontend success and error base paths/origin;
- OAuth flow Redis URL;
- cookie Secure override for local/test only;
- provider connect/read timeout.

Missing Google configuration does not break general health/readiness or existing
mock generation. It makes only login start return `auth_not_configured`.
`.env.example` contains empty non-secret placeholders and documentation; Compose
passes OAuth values only to backend, not worker, dispatcher, frontend, or
migration containers.

## Security and Failure Matrix

Required negative cases include:

- absent/mismatched/replayed/expired state and absent/mismatched flow cookie;
- callback error/denial, missing code, duplicate callback, and unsafe return path;
- PKCE or nonce mismatch;
- invalid signature, issuer, audience, expiry, `sub`, email, or verified-email;
- provider timeout, 4xx, 5xx, malformed JSON, and oversized response;
- Redis unavailable on start and callback;
- duplicate/concurrent first signup for one `sub`;
- suspended User callback and suspended User request;
- missing, malformed, unknown, revoked, inactive, and absolutely expired Session;
- exactly five Sessions, sequential sixth login, and concurrent sixth logins;
- touch before/at/after five minutes and concurrent touch attempts;
- wrong/missing Origin on logout;
- cookie flag parity between issue and deletion;
- exception/log/receipt scans proving forbidden values are absent.
- Uvicorn access-log capture proving callback query values are redacted.

No test may weaken nonce, state, PKCE, cookie, or ID-token verification merely to
fit a fake. Fake adapters must satisfy the production interface contract.

## Verification Strategy

Verification proceeds from narrow to integrated:

1. Pure tests for secret generation, hashing, PKCE, return paths, cookie options,
   error mapping, and Active Session classification.
2. AuthService interface tests with fake Google, in-memory flow store, injected
   clock, and controlled Session secrets.
3. HTTP tests for redirects, callbacks, cookies, `/me`, logout, trusted Origin,
   and dependency behavior.
4. Production Google adapter contract tests with `httpx.MockTransport`; no Google
   network call or real credential.
5. Redis adapter tests proving TTL, atomic consume, replay refusal, and outage
   behavior.
6. Two fresh isolated Postgres+Redis Compose cycles proving first/repeat signup,
   max-five invariant, concurrent sixth-login serialization, expiry, touch,
   logout, suspension rejection, cleanup, and safe evidence.
7. Full backend pytest, Compose config, frontend build, and existing mock
   generation golden path with `AI_PROVIDER=mock`.
8. Draft PR CI: `verify`, backend Scan/SBOM, and frontend Scan/SBOM.

Real Google browser login is an explicit later manual gate after G3.1 supplies
the browser UX. It is never inferred from fake-adapter success.

## Portfolio and Operational Measures

G3 records numbers rather than only pass/fail claims:

- Active Session count after sequential and concurrent admission attempts;
- eviction victim ordering for exactly five existing Sessions;
- Session touch write count across a five-minute window and at its boundary;
- OAuth flow TTL and replay-rejection count;
- authentication request count, success/error mix, and local p95 duration for a
  bounded mock workload;
- provider timeout duration and bounded public error classification;
- zero forbidden raw credential, protocol, profile, and Session values in logs,
  receipts, and committed evidence;
- zero remaining isolated Compose projects and volumes after verification.

The portfolio record must explain the before state—persistence existed but no
request could establish or resolve a User—and the after state—later modules can
consume one authenticated-User interface without understanding OAuth or Session
internals. Machine-dependent latency is recorded as observation, not presented
as a universal production SLO.

## Scope Budget and Stop Conditions

Predicted non-document paths: 17.

- auth module: four paths;
- request dependency and auth router: two paths;
- config/main/dependency metadata: three paths;
- Compose and safe env example: two paths;
- isolated verifier: one path;
- focused tests: five paths.

No migration is expected. Stop and redesign before implementation if:

- non-document paths would exceed 20;
- any schema revision appears necessary;
- frontend, ownership, credit, Master mutation, cloud, or provider workload code
  becomes required;
- a second unrelated production module appears;
- deterministic fake-adapter tests cannot exercise the external interface;
- max-five concurrency cannot be proved on real PostgreSQL;
- safe local verification would require a real Google credential or call.

## Proposed Goal Decomposition

1. Freeze contracts and expected failing tests.
2. Implement cryptographic primitives and the one-time flow-store adapters.
3. Implement and contract-test the Google identity adapter.
4. Implement AuthService callback and Session lifecycle transactions.
5. Add the request dependency, HTTP routes, cookies, configuration, and safe
   public errors.
6. Build and run the isolated Postgres+Redis verifier twice.
7. Run full mock regression and generation golden path.
8. Record portfolio evidence, update handoff, push, and open a Draft PR with
   auto-merge enabled.

Final reviewers must independently approve:

- F1: plan/scope/path compliance;
- F2: OAuth, cookie, credential, CSRF, and Session security;
- F3: real local Postgres+Redis concurrency/runtime evidence;
- F4: documentation and portfolio claim fidelity.

## Completion Gate

G3 may become `Mock Verified` only when all proposed Todos and F1-F4 pass, two
isolated Postgres+Redis cycles and the existing mock generation golden path pass,
the branch is pushed, and a Draft PR with required CI and auto-merge is open.
Real Google execution, G3.1 browser UX, G4 ownership, G10 Master operations,
cloud deployment, and AI provider calls remain outside this gate.

## Rollback and Recovery

G3 adds no migration, so rollback does not alter User or Session schema. Before
release, reverting the G3 commits removes the routes and module while preserving
G2 data. After release, operators can disable login by removing or invalidating
the OAuth-enabled configuration; existing non-authenticated generation behavior
must remain healthy, while login start fails closed with `auth_not_configured`.

If Redis is unavailable, restore Redis and require Users to restart login because
consumed or expired flow records are never reconstructed. If Google is
unavailable, no local Session is created; retry begins with a new flow. If a
Session-security defect is suspected, the recovery path is a bounded operation
that revokes all non-revoked Sessions with a safe reason before re-enabling
login. Implementing that emergency operation must not silently expand G3; the
Goal must either include it inside the auth module's locked path budget or open a
follow-up blocker before claiming operational readiness.

## Approval Gates

Implementation must not begin until all are explicitly accepted:

1. **Scope:** backend OAuth/Session only; G3.1 owns browser UX and G10 owns
   Master mutations.
2. **Lifecycle:** sixth login evicts oldest Active Session; activity touch is
   throttled to five minutes.
3. **Deep module:** callers learn only start, complete, authenticate, and logout;
   Google and flow-store seams remain internal.
4. **Security:** PKCE/state/nonce, verified `sub`, no token persistence, bounded
   cookies, trusted Origin, and safe errors/logs are mandatory.
5. **Transactions:** User lock proves max five; expiry is evaluated independently
   of cleanup; profile refresh cannot change role/status/signup.
6. **Verification:** fake Google plus real isolated Postgres+Redis, concurrency,
   negative matrix, full mock regression, and required CI.
7. **Budget:** no migration, 17 predicted non-document paths, hard stop above 20.
8. **Delivery:** evidence-backed docs, Draft PR, required checks, and auto-merge;
   no real Google or cloud execution.
