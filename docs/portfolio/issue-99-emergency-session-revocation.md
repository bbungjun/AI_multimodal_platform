# Issue #99 — Guarded emergency Session revocation

Evidence level: **Mock Verified**. This record proves a local disposable
PostgreSQL containment mechanism. It does not claim a live OAuth incident drill,
cloud rollout, credential rotation or restored production login.

## Background and problem

The backend already supported individual logout, expiry and suspension, but an
operator had no safe way to contain a suspected Session-wide incident. Updating
all rows alone was insufficient: an in-flight OAuth callback could admit a new
Session while revocation was running. Suspending every User would incorrectly
mix incident containment with G10 account policy and would damage account state.

## Observation and cause analysis

The OAuth service admitted Sessions in two entry points: flow creation and
callback completion. Therefore containment needed an admission policy at both
Interfaces plus a transactional database operation. A first exact12-path design
put the new setting in `.env.example` but omitted the Compose adapter. Inspection
showed auth variables are explicitly forwarded to backend; the setting would
otherwise remain enabled in the container. Work stopped before the gate was
wired, and v2 added only `docker-compose.yml` (exact13, migration0).

Rejected approaches:

- bulk SQL without admission disable, because callback/revoke races remain;
- mass User suspension, because it changes account policy and G10 semantics;
- a new control table, because a migration was unnecessary for this bounded
  pre-live mechanism;
- a force or guard-bypass flag, because it converts an incident tool into an
  unsafe general mutation path.

## Solution and rationale

`AuthService` now receives `login_enabled` from its adapter. When false, both
OAuth start and callback fail with `login_disabled` before Redis, provider or DB
side effects. The deep `revoke_active_sessions` Module requires a caller-owned
transaction, aware time and fixed reason. Preview is immutable; execute locks
active Session rows deterministically, writes a bounded reason and is idempotent.

The CLI requires a matching non-system PostgreSQL database, disabled login and
the exact `REVOKE_ALL:<database>` confirmation. It prints counts only. There is
no DSN override, force, keep-session or raw-record output. Partial failure rolls
back; after commit revocation is deliberately irreversible. Operational recovery
is an explicit login restore/redeploy followed by fresh sign-in.

## Verification

At committed code `1822679`, two independent random Compose projects passed at
schema head0006:

| Cycle | Groups | Races | Checks | Work | Cleanup |
|---|---:|---:|---:|---:|---:|
| 1 | 8/8 | 1 | 85 | 41.391s | 2.578s, zero resources |
| 2 | 8/8 | 1 | 85 | 14.656s | 2.672s, zero resources |

The groups cover login gating, preview, operator guards, atomic revocation,
idempotency, disabled admission, a real authentication/revocation lock race and
failure rollback. Existing auth PostgreSQL/Redis passed with outage recovery;
one authenticated ownership/golden-path cycle passed. Linux tracked-only backend
passed1589 with3 guarded skips. Windows passed1588 with3 guarded skips and only
the pre-existing Bash absolute-path test failure. Compose, frontend lint/build,
Session48 and Chromium34 passed.

## Result and impact

The service now has a reproducible incident-containment sequence that prevents
new Session admission before invalidating all active Sessions. The operation is
bounded, target-guarded, privacy-safe and independently testable without external
OAuth or provider cost. The v2 correction also demonstrates validation of the
actual configuration delivery path rather than only the application setting.

## Remaining risks and next step

- No real load-balancer/multi-replica disable propagation or live OAuth drill was
  run; those remain required before a Live Verified readiness claim.
- Execute cannot restore Sessions. The rollback is restoring login only after
  incident review and requiring fresh authentication.
- Master suspension and Audit are intentionally deferred to G10.
- [PR133](https://github.com/bbungjun/AI_multimodal_platform/pull/133)
  passed final-head `verify` and both Scan/SBOM checks and protected
  squash-merged as `d249e97`; Issue99 closed. Live drill risk remains unchanged.
