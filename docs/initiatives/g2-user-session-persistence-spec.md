# G2 User and Session Persistence Specification

## Document Status

- Status: `Accepted / Execution Planned`
- Last updated: `2026-09-02`
- Parent: [Authentication, Credits, and Master Console Initiative](auth-credits-master-console.md)
- Dependency: G1 merged through PR #95 at `91cf903`
- Provider mode for all verification: `AI_PROVIDER=mock`
- Tracker: [Issue #96](https://github.com/bbungjun/AI_multimodal_platform/issues/96)
- Branch: `codex/issue-96-user-session-persistence`
- Goal plan: `.omo/plans/issue-96-g2-user-session-persistence-goal.md`
- Goal plan SHA-256:
  `67263d2460eb7dcabfd9cd4d9af41daf61ece6f3a94b5dc6fd62124ec54ff311`
- Base revision: accepted specification on `main` at `eefe939`

This specification narrows G2 to the persistence contract required by later
identity work. Google authorization, callback handling, cookie issuance,
request authentication, ownership filtering, plans, and credits remain outside
G2.

## Outcome

CreativeOps Studio gains a reproducible Postgres representation for User and
Session with explicit identity, status, origin, expiry, revocation, and
credential-safety invariants. A clean database can migrate from G1 head to G2
head, downgrade exactly one revision back to G1, and re-upgrade without changing
the existing generation schema or product behavior.

G3 receives stable mapped persistence types. It must not revise table meaning
while adding Google OAuth and the server-managed session lifecycle.

## Why G2 Stops Before OAuth

User and Session storage is a persistence seam. OAuth protocol handling is a
different module with redirect, state, nonce, PKCE, Google token verification,
cookies, and HTTP error behavior. Combining both would enlarge the review and
security surface and make migration failures difficult to separate from OAuth
failures.

G2 therefore proves schema and persistence invariants with deterministic local
data only. It does not expose a mock login route or generate an authentication
cookie.

## Domain Language

Canonical terms are maintained in [CONTEXT.md](../../CONTEXT.md):

- **User** owns product data and entitlements; a User may be OAuth-backed or
  synthetic.
- **OAuth User** is linked to a Google identity and can become login-capable.
- **Synthetic User** is login-disabled and exists for operations/test data.
- **Session** is a bounded server-recognized login continuation for one OAuth
  User; it is not an OAuth access token.
- **Master** is a role of a User, not a separate account type.

## Scope

### Must Have

- One new Alembic revision after `0001_generation_baseline`.
- Dedicated identity persistence module containing User and Session mappings,
  enums, relationships, and schema constraints.
- User roles exactly `user | master`.
- User statuses exactly `active | suspended`.
- User origins exactly `oauth | synthetic`.
- Nullable but unique Google `sub`; it is mandatory only for OAuth Users.
- Email, verified-email flag, display name, and profile-image URL as mutable
  profile data rather than identity keys.
- An immutable signup timestamp suitable as the future 30-day cycle anchor.
- Session storage containing only a SHA-256 digest, never a raw session secret.
- Session timestamps sufficient to enforce 12-hour inactivity and seven-day
  absolute expiry in G3.
- Revocation timestamp and bounded safe reason.
- Foreign-key, uniqueness, length, timestamp-order, status, and origin
  consistency constraints.
- Migration inventory, downgrade, reset, and mock regression evidence.
- Portfolio record of the design problem, trade-offs, verification, and result.

### Must Not Have

- Google OAuth routes, redirect/callback logic, PKCE, state, nonce, token
  exchange, or Google SDK calls.
- Cookie creation, raw session-token generation, request authentication, or
  FastAPI dependencies.
- Password, refresh token, OAuth access token, authorization code, ID token, or
  raw session secret persistence.
- Job, Prompt Enhancement, or Asset ownership columns; those belong to G4.
- Plan, Credit, Usage, Reservation, Audit, or billing-cycle tables.
- Master promotion CLI, suspension workflow, last-Master rules, or session-limit
  eviction policy; those belong to G3/G10.
- Synthetic data seeding; that belongs to G10.
- Frontend, Compose topology, provider, cloud, Terraform, Kubernetes, or paid
  API changes.
- Preservation or backfill of disposable existing application data.
- A second Alembic revision.

## Persistence Seam and Interface

The seam lives in a dedicated identity model module rather than expanding the
generation-oriented `backend/app/models.py`. Its intentionally small external
interface is the mapped domain vocabulary:

```python
User
UserSession
UserRole
UserStatus
UserOrigin
```

Callers may construct and query these types through an injected SQLAlchemy
session. G2 does not add repository pass-through functions. G3 will own the
deeper authentication module that combines transactional lookup, session
limits, expiry, revocation, and cookie behavior behind its own smaller
interface.

Alembic must import both generation and identity mappings so metadata drift can
be detected. Generation modules must not import identity mappings during G2.

## User Schema Contract

Table: `users`

| Column | Type | Null | Contract |
|---|---|---:|---|
| `id` | UUID | No | Primary key generated by the application |
| `google_sub` | varchar(255) | Yes | Stable Google identity; unique when present |
| `email` | varchar(320) | Yes | Mutable profile field; not an identity key and not unique |
| `email_verified` | boolean | No | True only for a verified OAuth profile |
| `display_name` | varchar(200) | Yes | Mutable profile field |
| `profile_image_url` | varchar(2048) | Yes | Mutable profile field; no fetch occurs in G2 |
| `role` | `user_role` enum | No | `user` or `master`; default `user` |
| `status` | `user_status` enum | No | `active` or `suspended`; default `active` |
| `data_origin` | `user_origin` enum | No | `oauth` or `synthetic`; explicitly supplied |
| `signed_up_at` | timestamptz | No | Future billing-cycle anchor; no update path may change it |
| `suspended_at` | timestamptz | Yes | Present exactly when status is suspended |
| `updated_at` | timestamptz | No | Mutable profile/status update timestamp |

Database invariants:

- OAuth User: `google_sub`, `email`, and `email_verified=true` are required.
- Synthetic User: `google_sub IS NULL`, `email_verified=false`, and role is
  `user`; it cannot be a login-capable Master.
- Active User has `suspended_at IS NULL`; suspended User has a non-null
  `suspended_at` not earlier than `signed_up_at`.
- `updated_at >= signed_up_at`.
- Google `sub` is the only external identity key. Email is deliberately
  non-unique because identity must not follow a mutable profile field.

## Session Schema Contract

Table: `user_sessions`

The explicit table name avoids ambiguity with database/ORM sessions while the
domain term remains Session.

| Column | Type | Null | Contract |
|---|---|---:|---|
| `id` | UUID | No | Internal row primary key; never sent as the cookie secret |
| `user_id` | UUID | No | References `users.id`; deletes cascade only for explicit local cleanup |
| `token_hash` | bytea | No | Exactly 32 SHA-256 bytes; globally unique |
| `created_at` | timestamptz | No | Session creation time |
| `last_seen_at` | timestamptz | No | Anchor for future 12-hour inactivity expiry |
| `absolute_expires_at` | timestamptz | No | Exactly seven days after creation when G3 creates a Session |
| `revoked_at` | timestamptz | Yes | Null while not explicitly revoked |
| `revoke_reason` | varchar(64) | Yes | Safe bounded code, present only when revoked |

Database invariants:

- `octet_length(token_hash) = 32`.
- `last_seen_at >= created_at`, `last_seen_at <= absolute_expires_at`, and
  `absolute_expires_at = created_at + interval '7 days'`.
- Revocation timestamp and reason are either both null or both present;
  `revoked_at >= created_at`; reason is a lowercase safe code of at most 64
  characters.
- One User owns zero or more Sessions; one Session belongs to exactly one User.
- Index the digest lookup, active Sessions per User, and absolute-expiry cleanup
  paths. A time-dependent partial predicate must not use `now()`.

G2 does not define whether a sixth login is rejected or evicts the oldest
Session, nor how frequently `last_seen_at` is refreshed. G3 must decide and test
those lifecycle policies without changing this schema.

## Migration Contract

Revision: `0002_user_session_persistence`

- `down_revision = "0001_generation_baseline"`.
- Upgrade creates the three identity enums, `users`, then `user_sessions`.
- Downgrade drops `user_sessions`, `users`, then the identity enums.
- No existing generation table, enum, foreign key, index, or row is changed.
- No data copy, ownership backfill, stamping, or runtime DDL is allowed.
- `alembic heads` must return exactly `0002_user_session_persistence`.

## Reset and Verifier Compatibility Decision

G1's external schema-control interface remains unchanged. Its reset preview
currently lists a fixed set of generation tables, which becomes incomplete as
soon as G2 adds identity tables. G2 must generalize the internal preview
inventory to discover all ordinary tables in `public` except
`alembic_version`, sort them deterministically, quote identifiers safely, and
count them in the same transaction.

This is an approved-interface-preserving integration change, not a second
public module. Tests must prove that identity rows appear in preview, execution
still resets only `public`, and no table name from user input reaches SQL.

The isolated migration verifier becomes schema-head oriented rather than
Issue-94 oriented:

- generated projects use `schema-verify-[a-z0-9]{8,32}`;
- local redacted receipts use `.omo/evidence/schema/`;
- inventory expects both generation and identity schema at G2 head;
- downgrade target for the G2-specific assertion is
  `0001_generation_baseline`, where generation schema remains and identity
  schema is absent;
- a separate full downgrade to `base` may remain as the complete-chain check;
- stale-revision refusal/recovery and exact cleanup remain mandatory.

## Verification Plan

### Static and Focused

- Exactly two ordered revisions and one Alembic head.
- Mapped fields, enum values, defaults, relationships, constraints, and indexes
  match this specification.
- Forbidden credential/token columns and OAuth code paths are absent.
- Generation model metadata remains unchanged.
- Reset inventory is dynamic but only queries identifiers obtained from the
  Postgres catalog.

### Real Postgres

Run twice in fresh isolated Compose projects:

1. Upgrade a clean database to G2 head and assert exact tables, enums,
   constraints, indexes, and revision.
2. Insert one valid OAuth User, one valid Synthetic User, and deterministic
   Sessions using only digest bytes.
3. Prove duplicate Google `sub`, duplicate digest, malformed digest, invalid
   origin/profile combinations, inconsistent suspension, and invalid timestamp
   ordering fail.
4. Downgrade to G1 head; identity tables/enums disappear while all generation
   tables/enums remain.
5. Re-upgrade to G2 head and repeat inventory assertions.
6. Force stale revision; backend, worker, and dispatcher must refuse work.
7. Restore head and prove the three schema checks recover.
8. Seed identity rows, inspect reset preview, execute exact guarded reset, and
   prove all application rows are gone at G2 head.
9. Remove only the exact isolated projects and volumes.

### Regression

- Full backend pytest in mock mode.
- Frontend lint and production build, even though frontend is unchanged.
- Docker Compose configuration with `.env.example`.
- Existing mock prompt-enhancement/generation/asset golden path.
- `git diff --check`, changed-path count, staged-file review, and secret scan.

## Expected Changed Paths

Predicted non-document paths: 10.

1. `backend/app/identity_models.py` (new)
2. `backend/app/schema_control.py`
3. `backend/migrations/env.py`
4. `backend/migrations/versions/0002_user_session_persistence.py` (new)
5. `scripts/verify_schema_migrations.py`
6. `backend/tests/test_alembic_schema.py`
7. `backend/tests/test_identity_models.py` (new)
8. `backend/tests/test_schema_control.py`
9. `backend/tests/test_verify_schema_migrations_script.py`
10. `backend/tests/test_model_relationships.py` only if cross-model metadata
    coverage cannot remain entirely in the new identity test

Expected document paths:

- `CONTEXT.md`
- this specification
- `docs/initiatives/auth-credits-master-console.md`
- `docs/current-work.md`
- `docs/testing.md`
- `docs/runbooks/local-mock.md`
- `docs/portfolio/README.md`
- `docs/portfolio/issue-<number>-user-session-persistence.md`

Stop for re-planning before implementation if non-document paths exceed 12,
if a second migration is required, or if OAuth/API/ownership behavior becomes
necessary.

## Sequential Delivery Plan

1. Preflight and write failing migration/model/reset compatibility contracts.
2. Add identity enums and mapped User/Session types.
3. Add the single G2 migration and prove source metadata matches it.
4. Generalize reset preview inventory without changing its external interface.
5. Generalize and extend the isolated schema verifier.
6. Run two real Postgres constraint/migration/reset/drift cycles.
7. Run the existing mock product golden path and full regression gates.
8. Record portfolio evidence, update handoff/status, push, and open a draft PR.

Every step runs its focused tests, `git diff --check`, `git status`, staged-path
review, and a small meaningful commit before continuing.

## Acceptance Criteria

- One head: `0002_user_session_persistence`.
- Exactly one new revision and no generation-schema mutation.
- All User and Session constraints are enforced by real Postgres.
- No raw session secret or OAuth credential field exists.
- Reset preview and execution include identity tables without accepting table
  identifiers from callers.
- Two isolated real Postgres cycles and exact cleanup pass.
- Three runtime processes still fail closed on revision drift.
- Existing mock generation golden path and regression gates pass.
- Documentation distinguishes `Implemented`, `Mock Verified`, and unperformed
  OAuth/live verification.
- F1-F4 final reviewers return unconditional `APPROVE`.

## Stop Conditions

Stop and report instead of expanding scope if:

- G2 needs an OAuth route, cookie, raw token generator, auth dependency, or
  frontend change;
- Job/Prompt Enhancement/Asset ownership becomes necessary;
- more than one migration or 12 non-document paths are required;
- reset safety cannot be preserved without changing its external interface;
- a real provider, credential, cloud resource, or default developer database
  would be touched;
- an existing tracked user change conflicts with an allowed path.

Ordinary failing tests, migration syntax errors, and Docker startup issues are
diagnosed within scope; they are not reasons to weaken acceptance criteria.

## Rollback and Recovery

- Before merge, revert only G2 commits on its branch.
- In an isolated/local database, downgrade exactly one revision with
  `python -m alembic downgrade 0001_generation_baseline` and verify generation
  schema remains current for G1 code.
- Do not downgrade a shared/cloud database under this Goal.
- If reset drops `public` but upgrade fails, use the existing G1 recovery
  command and require schema readiness before starting processes.

## Approval Gates

Approval fixes the following decisions before Issue creation:

1. User table supports OAuth and Synthetic origins from the first revision.
2. Google `sub` is nullable/unique; email is nullable and non-unique profile
   data.
3. Session stores a unique 32-byte digest plus lifecycle timestamps, never a
   raw secret.
4. Sixth-session behavior and last-seen refresh frequency are deferred to G3.
5. G2 may generalize G1 reset inventory internally while keeping its public
   interface unchanged.
6. G2 has one migration and a 12 non-document-path stop limit.
