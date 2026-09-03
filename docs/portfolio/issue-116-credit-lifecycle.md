# Issue116 — G5B credit lifecycle design and evidence

Status: Planned / Prepared, 2026-09-04. No G5B implementation or runtime claim.
Issue [#116](https://github.com/bbungjun/AI_multimodal_platform/issues/116);
[spec](../initiatives/g5-credit-lifecycle-spec.md); parent114 remains open.

## Problem

G5A supplies durable balances/ledger and pure policy, but no account initialization,
renewal, Plan change or grants. Writing these directly in authentication/generation
would duplicate transaction and retry rules. A replayed downgrade has no monetary
delta, so the existing ledger alone cannot remember its immutable request/result.

## Observations and alternatives

Inspected merged a003257's credit_models/policy, User roles/status, Alembic/schema
proof, auth/current-head helpers and prior delivery evidence. No unrelated edits
were present; existing .omo was preserved.

- Ledger-only idempotency was rejected: scheduling/cancellation/no-op cannot append
  a valid zero-valued event and cannot identify later replay from current Plan alone.
- A generic repository/event framework was rejected: PostgreSQL is the only store.
- Signup hook and background renewal were deferred: B must be transaction-composable
  without changing authentication or introducing paid/product side effects.
- Head changes affect schema/auth/ownership proofs. Counting that compatibility
  work yields exactly20 code paths, not only the new lifecycle module.

## Proposed solution and trade-offs

codebase-design guided a small three-operation Interface with caller-owned Session
and explicit time: ensure_cycle/change_plan/grant_bonus. Lock User/account/cycle/
grants in one order, refresh locked ORM state, isolate rejected writes in savepoint
and leave final commit/rollback to caller. No provider call within the transaction.

One additive0005 operation table stores immutable typed request/result receipts.
The existing four-table DDL and rate policy remain unchanged. Command replay
precedes renewal/expiry so a retry after a boundary cannot apply twice. Separate
ledger/projection updates remain in the same transaction; no-op Plan requests
write only the receipt.

The spec explicitly resolves pending downgrade replacement/cancellation, current-
cycle-only skipped renewal, immediate allowance difference, Master/suspended
handling, held-credit expiry, strict overflow and original-result replay. The
hash-bearing execution request approves these details; they are not live behavior.

Rollback preserves all existing data: populated operation downgrade refuses under
bounded locks. Empty-operation downgrade preserves populated0004 rows. There are
no product callers to unwind in this slice. No destructive development/preview QA.

## Preparation performed and verification

- Confirmed PR118 actually MERGED at a003257, Issue115 closed;114/117 open.
- Synchronized main by fast-forward and created codex/issue-116-credit-lifecycle.
- Read and inspected predecessor contracts; added B spec and frozen Goal only.
- Baseline from backend with AI_PROVIDER=mock:

```powershell
python -m pytest tests/test_credit_policy.py tests/test_credit_models.py tests/test_credit_foundation_support.py tests/test_alembic_schema.py tests/test_schema_control.py tests/test_verify_schema_migrations_script.py tests/test_verify_auth_sessions_script.py tests/test_ownership_persistence.py tests/test_mock_auth_support.py tests/test_verify_ownership_script.py -q
```

Result: **446 PASS/3.01s**. This verifies existing code, not proposed lifecycle.
Final fresh rerun: **446 PASS/1.77s**. Exact20 spec/Goal path parity, all24
acceptance IDs,11 PowerShell command blocks,101 relative links, frozen SHA,
static Compose config and diff/status/staged checks PASS. Non-document edits0.
No Docker runtime, OAuth/provider/cloud call, DB reset/migration, frontend change
or application-code edit was performed. All new capability remains Planned.

Frozen local plan: `.omo/plans/issue-116-g5b-credit-lifecycle-goal.md`.
SHA256: `d17f47ac85b21ff11f3c95081794fb81517277368c6b1196427fd53669dcb590`.
Transfer exact file bytes when changing machines; do not stage .omo wholesale.

## Execution checkpoints

### Todo1 — preflight

User approved spec section3 and the frozen SHA. Starting8e2f3fb, origin/main
unchanged a003257; tracked/index clean and existing .omo preserved. Local daemon
desktop-linux/npipe with no DOCKER_HOST override; preview4 running and developer/
preview DB/media volumes present. Backend dotenv guard passed without reading
private configuration. First B0 command above:446 PASS/2.39s. Scope/hygiene checks
pass; implementation is not yet runtime verified. Next: operation schema.

## Planned acceptance and remaining risk

### Todo2 — operation persistence

Added one typed append-only credit_operations table and additive0005 migration.
Nullable request fields have explicit IS NOT NULL shape guards to avoid SQL CHECK
null acceptance. Composite owner FKs and User/key PK prevent cross-owner receipt
references; downgrade locks5s and refuses nonempty operations before DDL. Existing
four-table contracts/migrations preserved. M23 PASS/1.63s; structural tests only,
not real DB proof. Scope4/20; current-head compatibility is intentionally Todo5.
The first staged check found a trailing blank line in the new migration; it was
removed and the owned, unpushed checkpoint amended after fresh staged validation.

### Todo3 — initialization and renewal

Added caller-transaction requirement, savepoint rollback, fresh User/account/cycle/
grant locking, immutable CycleView and current-only signup-anchored renewal.
Held/consumed amounts remain on expired grants; only available moves to expired.
Corrupt anchor/allowance/base/Master state and clock regression fail closed. No
product caller or provider work. Unit fake tests prove Interface decisions, not
PostgreSQL locking. C72 PASS/0.76s, M23 PASS/0.85s; scope6/20, D PASS.

Todo1–8/F1–F4: exact20/new migration1, all24 acceptance IDs, schema2 and lifecycle2
independent projects, auth1, unchanged ownership all/2, authoritative Linux full
backend and existing frontend regression, Ready PR/final-head3 CI/protected squash
actual merge. New proof requires eight completed groups and eight lock-observed
races; partial checks cannot count as complete. Fixed deadlines stop on overrun.

The20-path cap leaves no spare path. Any21st path, second migration, missing required
Interface or runtime timeout requires redesign before scope expansion. No account/
grant/renewal/charge currently runs for users. G5C reservation/Usage/settlement and
G6/G7 generation wiring remain separate; no overspend/settlement or live claim.
