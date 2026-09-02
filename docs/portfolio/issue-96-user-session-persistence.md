# Issue #96: User and Session Persistence

## Evidence Status

- Overall: `Mock Verified`
- Specification: `Accepted`
- Implementation: `Implemented` on branch
  `codex/issue-96-user-session-persistence`
- Real local Postgres verification: `Passed twice`
- Existing mock product regression: `Passed`
- Google OAuth, cookies, and authenticated browser verification: `Planned / G3`
- Cloud and provider verification: `Deferred / No-Go`
- Delivery: [Draft PR #97](https://github.com/bbungjun/AI_multimodal_platform/pull/97)

This record proves persistence and database behavior only. It does not claim a
working login, authenticated request, content ownership, credit enforcement,
or live cloud deployment.

## Background and Problem

CreativeOps Studio had durable generation data but no durable identity. Later
OAuth, ownership, per-User credits, and operations views need a stable User ID
and revocable Session representation before they can be added safely.

Adding OAuth routes and persistence together would mix protocol security with
schema correctness. It would also make failures in identity constraints,
migration ordering, session-secret handling, and Google verification difficult
to isolate.

## Expected and Previous Behavior

| Category | Behavior |
|---|---|
| Expected | One migration creates explicit OAuth/Synthetic User and bounded Session persistence contracts. |
| Previous | G1 head contained only generation tables and no identity persistence. |
| Impact | OAuth, ownership, and credits had no stable database seam and could not be implemented independently. |

## Observation and Root-Cause Analysis

Repository inspection confirmed that `Base.metadata` registered only generation
models and `0001_generation_baseline` was the sole revision. There was no field
that could safely act as an external identity key or Session revocation record.

Preflight also exposed an operational coupling in G1: reset preview counted a
fixed four-table tuple. Once identity tables existed, preview would omit rows
that reset execution would still delete because execution resets all of
`public`. That mismatch would make a destructive preview incomplete.

The first focused run deliberately failed 17 tests:

- eight for the absent identity module/revision;
- one for fixed reset inventory;
- eight for Issue-94-specific verifier names and head assumptions.

The other 33 focused contracts passed, showing the failures were G2-specific
rather than fixture or import regressions.

## Resolution and Design Rationale

### Dedicated Persistence Seam

`backend/app/identity_models.py` contains the five mapped domain types:

- `User`, `UserSession`;
- `UserRole` with `user | master`;
- `UserStatus` with `active | suspended`;
- `UserOrigin` with `oauth | synthetic`.

The module stores Google `sub` as the nullable unique external identity and
treats the profile address as mutable, non-unique profile data. Synthetic Users
cannot carry a Google subject, verified profile, or Master role. Status and
suspension timestamps must agree.

Session rows contain only a unique SHA-256 digest with an exact 32-byte database
constraint. Creation, last-seen, seven-day absolute expiry, and optional
revocation fields have ordering and consistency constraints. No password,
authorization code, provider token, or raw Session secret is modeled.

G2 intentionally does not add repository pass-through functions. G3 will place
OAuth verification, session limits, expiry/touch policy, and cookies behind a
deeper authentication interface.

### Additive Migration

`0002_user_session_persistence` has G1 as its only parent. It creates three
identity enums, `users`, and `user_sessions`; downgrade removes only those G2
objects. It does not alter a generation table or copy/backfill existing data.

### Truthful Reset and Reusable Verification

The G1 reset interface remains three operations, but its implementation now
discovers ordinary `public` tables from the Postgres catalog. It excludes the
revision table, sorts deterministically, and quotes only catalog-derived names
with the active dialect. Caller input never becomes a SQL identifier.

The isolated verifier is now schema-head oriented. It uses validated
`schema-verify-*` projects, verifies downgrade to G1 and full-chain round trips,
runs valid and invalid identity rows against Postgres, proves three runtime
processes reject stale revisions, and cleans only the exact project in
`finally`.

## Alternatives and Trade-offs

- Email as identity was rejected because profile data can change; Google `sub`
  remains the identity key.
- A raw Session token column was rejected because database disclosure would
  immediately disclose active credentials; only the digest is persisted.
- OAuth and persistence in one Goal was rejected to keep protocol behavior and
  database behavior independently testable.
- A fixed reset table list was rejected because every future migration could
  silently make preview incomplete. Catalog discovery adds implementation
  complexity but removes per-table maintenance and preserves the small external
  interface.
- Sixth-Session eviction/rejection and last-seen refresh frequency remain G3
  decisions. G2 persists the necessary timestamps without prematurely fixing
  request-time policy.

## Verification

Tested code checkpoint: `2a4c8ab` plus later documentation-only changes.
Provider mode was `AI_PROVIDER=mock`; no credential or provider call was used.

| Verification | Result | Evidence boundary |
|---|---|---|
| Alembic head/history/offline SQL | PASS | One head `0002_user_session_persistence`; one new revision |
| Focused migration/model/reset/verifier suite | PASS | 52 tests |
| Isolated Postgres cycle 1 | PASS | `schema-verify-75c5d479eb4a` |
| Isolated Postgres cycle 2 | PASS | `schema-verify-a0f92adacc0f` |
| Invalid identity rows | PASS | 11 rejected inserts across 10 named constraints |
| Downgrade compatibility | PASS | G2 identity objects absent at G1; generation schema preserved |
| Revision drift | PASS | Backend, worker, and dispatcher rejected stale revision and recovered at head |
| Guarded reset | PASS | Preview included identity rows; execution restored empty G2 head |
| Exact cleanup | PASS | Zero remaining `schema-verify-*` projects and volumes |
| Backend full pytest | PARTIAL | 396 passed; one pre-existing Windows Bash path-conversion failure |
| Frontend lint/build | PASS | 95 modules transformed; no frontend change |
| Compose/local verification | PASS | Mock config and `verify_local.py --skip-backend` |
| Mock product golden path | PASS | `schema-verify-golden02`; prompt, generation, PNG/range, cleanup |

The unchanged backend failure is
`test_release_script_guards_plan_scope_and_uses_terraform_rollback`. Windows
passes a drive-letter path to WSL Bash without conversion. It predates G2,
falls outside the locked paths, and was not skipped or weakened.

Performance, throughput, latency, queue, provider cost, and replica metrics are
not applicable: G2 adds no request path or provider workload. The meaningful
quantitative evidence is two clean databases, 11 invalid inserts, 10 named
constraint classes, three drift-refusing processes, 52 focused tests, and 396
passing regression tests.

## Result and Impact

- G3 can identify OAuth Users by a stable subject without relying on profile
  address uniqueness.
- A database leak does not directly expose Session credentials because only a
  digest is persisted.
- Invalid origin, role, suspension, digest, expiry, and revocation combinations
  fail in Postgres rather than depending only on application validation.
- Reset preview remains truthful as future tables are added.
- G1 generation behavior still completes end to end at G2 head.

Evidence level is `Mock Verified`: real local Postgres and mock application
runtime were exercised. OAuth and live user behavior remain unimplemented.

## Rollback and Recovery

Before merge, revert only Issue #96 commits. On an isolated/local database,
downgrade exactly one revision:

```powershell
cd backend
python -m alembic downgrade 0001_generation_baseline
```

Verify generation schema readiness with G1-compatible code. Do not downgrade a
shared/cloud database under this Issue. If a guarded local reset drops `public`
and upgrade fails, run `python -m alembic upgrade head`, then require the schema
check before starting application processes.

## Evidence Artifacts

- Models: `backend/app/identity_models.py`
- Migration: `backend/migrations/versions/0002_user_session_persistence.py`
- Reset boundary: `backend/app/schema_control.py`
- Isolated verifier: `scripts/verify_schema_migrations.py`
- Tests: `backend/tests/test_identity_models.py` and focused schema tests
- Local redacted receipts: `.omo/evidence/schema/` (not committed)

## Remaining Risks and Next Steps

- G3 must implement Google authorization-code flow with PKCE, state and nonce,
  server-managed cookies, and request authentication.
- G3 must decide whether a sixth active Session is rejected or evicts one and
  how often activity refresh is persisted.
- G3/G10 must enforce promotion, suspension, session revocation, and final
  Master rules transactionally.
- G4 must add non-null ownership to new product data after authentication exists.
- Cloud migration ordering and rollback remain `Deferred / No-Go`.
