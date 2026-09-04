# Emergency Session Revocation Specification

Status: **Accepted / Execution Prepared**, 2026-09-05. Issue
[#99](https://github.com/bbungjun/AI_multimodal_platform/issues/99) is the
pre-live operational authentication blocker. It does not add Master suspension,
Audit, a public mutation endpoint or live deployment execution.

## Problem and outcome

A suspected Session incident needs two coordinated controls: stop creating new
Sessions and revoke every currently active Session. A bulk UPDATE alone has a
race with OAuth callback and can leave a newly admitted Session alive. Suspending
every User would mix incident containment with G10 account policy, while a new
database control table would force an unrelated migration and broad verifier
head updates.

The accepted outcome is a small emergency Module plus a guarded operator CLI:

1. every application instance is first deployed with
   `AUTH_LOGIN_ENABLED=false`;
2. `/api/auth/google/start` and in-flight callback completion fail closed with
   `login_disabled`;
3. the CLI refuses execution unless that process sees the disabled setting,
   previews the active count, requires an exact database name and confirmation,
   then revokes all active Sessions in one transaction;
4. existing Session authentication fails after commit;
5. login stays disabled until an operator explicitly restores the setting and
   redeploys after incident review.

## Deep Module and Interface

The seam is one transaction-composable Interface:

```python
revoke_active_sessions(
    session,
    *,
    reason: str,
    now: datetime,
    execute: bool,
) -> EmergencyRevocationReceipt
```

The caller owns the transaction and supplies an aware timestamp. The Module
does not create an engine, load settings, commit, roll back or print. It accepts
only `suspected_compromise`, `credential_rotation` and `operator_drill`.
Preview (`execute=False`) counts active Sessions without mutation. Execute locks
active rows in `(user_id, created_at, id)` order and sets one fixed, bounded
revoke reason. Repeated execution is successful with zero newly revoked rows.

The deletion test favors this Module: without it, target guards, time safety,
reason vocabulary, deterministic locking, preview/apply equality and idempotent
receipt rules would be duplicated in the CLI and tests.

## Login-disable contract

`AuthService` accepts a `login_enabled` policy injected by its adapter. Both
`begin_google_login` and `complete_google_login` reject with
`login_disabled` before flow creation, provider exchange or database admission.
Authentication and logout remain available so already-running instances can
converge safely while the revocation transaction completes.

The default remains enabled to preserve existing local and test behavior.
Incident execution requires an explicit false setting. The production runbook
must verify the disabled response through the deployed load balancer before
running the revocation CLI. This Issue implements and mock-verifies the
mechanism; it does not change cloud configuration or claim a live drill.

## Guarded CLI contract

Run through `python -m app.auth.emergency` with:

- required `--expected-database` matching the configured PostgreSQL URL;
- required safe `--reason`;
- preview by default, with count-only output;
- mutation only with `--execute --confirm REVOKE_ALL:<database>`;
- `AUTH_LOGIN_ENABLED=false`, supported PostgreSQL and a non-system database;
- no DSN, target override, secret, Session hash, User identity or row listing in
  arguments/output.

The CLI re-runs the plan inside the execution transaction. Count drift is
reported as safe numeric before/newly-revoked/remaining fields. Partial failure
rolls back. There is no force, skip-guard, keep-session or raw-output flag.

## Verification

One random disposable `emergency-auth-verify-<12hex>` Compose project runs with
`AI_PROVIDER=mock`, `APP_ENV=test` and login disabled. It upgrades a new database
to schema head0006 and proves:

1. enabled/disabled login start and callback gating before provider work;
2. preview immutability and count-only receipt;
3. wrong database, enabled login, reason and confirmation refusal;
4. atomic revocation and existing Session authentication refusal;
5. repeated execution revokes zero additional Sessions;
6. Session admission is disabled during the operation;
7. concurrent authentication/revocation converges with no active Session;
8. injected failure rolls back and guarded cleanup leaves zero resources.

Run two independent cycles at one committed code SHA. Existing auth verifier,
full backend, Compose and frontend Session/Chromium regressions remain required.

## Exact implementation boundary

At most these 12 non-document paths may change:

1. `.env.example`
2. `backend/app/config.py`
3. `backend/app/api/auth_dependencies.py`
4. `backend/app/auth/service.py`
5. `backend/app/auth/emergency.py`
6. `backend/tests/test_auth_service.py`
7. `backend/tests/test_auth_api.py`
8. `backend/tests/test_emergency_sessions.py`
9. `backend/tests/emergency_sessions_support.py`
10. `backend/tests/test_emergency_sessions_support.py`
11. `backend/tests/test_verify_emergency_sessions_script.py`
12. `scripts/verify_emergency_sessions.py`

No migration is permitted. User suspension, Master/Audit, public mutation API,
frontend changes, real OAuth/provider/cloud, development/preview DB mutation and
credential access are excluded. A 13th non-document path, schema change or need
to mutate cloud configuration is STOP-and-redesign.

## Completion

Completion requires two isolated cycles, auth/full regressions, portfolio and
runbook evidence, a Ready PR, final required CI, protected squash auto-merge,
Issue closure and local `main` synchronization. Evidence remains Mock Verified;
a real incident drill and restored live login are separate operator decisions.
