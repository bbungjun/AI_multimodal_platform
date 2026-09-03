# G5 — Credit delivery split and G5A executable specification

Status: `Planned / execution prepared`, 2026-09-03. No G5 code is implemented.
Parent [#114](https://github.com/bbungjun/AI_multimodal_platform/issues/114).
The user requested split design and Goal preparation, not execution.
An explicit request carrying the frozen G5A Goal hash starts implementation.

## 1. Inputs and scope

Product policy remains in [the canonical initiative](auth-credits-master-console.md),
sections Plans and Entitlements, Rate Card V1, Admission and Settlement Invariants.
This document specifies only G5 delivery seams; it does not replace that policy.
G4 is merged at `6537025535b1006f6ca03366765e8a0f7e6bf978` (PR113), parent109 closed.
G5 consumes `User.id`, `User.signed_up_at`, existing Session authentication and
owner-tagged admission. Master cross-owner read is not mutation permission.

Use the codebase-design vocabulary: a Credit Module hides accounting behavior
behind a small Interface; database storage is its Implementation. Do not add a
repository wrapper, alternate datastore, generic accounting framework or new
Adapter without an actual varying dependency. A caller-owned AsyncSession and
explicit aware clock are the future transaction/time Seams.

| Delivery | Issue | Frozen scope | Handoff / completion boundary |
|---|---|---|---|
| G5A | [#115](https://github.com/bbungjun/AI_multimodal_platform/issues/115) | Four credit tables, additive migration, pure plan/rate/time policy and schema compatibility proof | Persistence and deterministic policy only; no automatic grants or enforced billing |
| G5B | [#116](https://github.com/bbungjun/AI_multimodal_platform/issues/116) | Account initialization, 30-day renewal, base/bonus grants, Plan transitions | Transaction-composable lifecycle; no reservation workflow or public Master controls |
| G5C | [#117](https://github.com/bbungjun/AI_multimodal_platform/issues/117) | Reservation allocations, Usage, settle/release and idempotency | Accounting transaction Interface for G6/G7; no generation wiring |

Each gets a separate context, Issue branch, <=20 exact non-document paths and
<=1 migration. A is frozen below. B/C have dependency-gated planning envelopes,
not speculative executable hashes. After each predecessor merge, inspect its
actual Interface and freeze the successor's paths, commands, tests and hash.
If B or C cannot fit, split before implementation; never expand A to fit them.

G6 integrates Gemini, G7 integrates Imagen/Veo/pipelines, G8 enforces per-User
concurrency, G9 supplies personal UI, G10 supplies Master mutations/Audit/seed.
No real payment, provider price lookup, Google login, cloud execution, frontend,
job/state-machine/worker/outbox change, production seed or Master control in A.

## 2. G5A Interface

`app.credit_policy` exposes only immutable policy values and pure functions:

- `MICROCREDITS_PER_CREDIT = 1_000_000`, `RATE_CARD_VERSION = "v1"`.
- `plan_policy(plan)` returns immutable allowance, permitted meters and existing
  request limits from the canonical table. Unknown Plan is refused; role is not
  accepted as an unlimited-credit switch. No current User is read or updated.
- `quote_usage(*, version, meter, units) -> int` returns microcredits. Meters:
  `gemini_input_token`, `gemini_output_token`, `imagen_fast_image`,
  `imagen_standard_image`, `imagen_ultra_image`, `veo_fast_ms`, `veo_standard_ms`.
  Exact V1 microcredit rates per unit: 1000, 4000, 50000000, 100000000,
  200000000, 60000, 120000 respectively. Zero units yields zero. No float math.
- `cycle_bounds(*, signed_up_at, now)` returns immutable index/start/end with
  `index = floor((now - signup)/2_592_000 seconds)`. Normalize aware instants to
  UTC; reject naive instants and `now < signup`. Intervals are half-open [start,end).
  An exact end instant belongs to the next cycle. Do not use calendar months or
  DST-local date arithmetic. This is calculation, not renewal or grant issuance.

Strict types: reject bool, float, string, negative or >signed-BIGINT units;
reject products outside 0..9_223_372_036_854_775_807. Unknown version/meter/Plan and
datetime overflow fail closed with fixed safe ValueError codes (no input echo).
No provider SDK, filesystem, DB, environment access or HTTP exception here.
G6/G7 map actual supported model identifiers and normalize duration into these
meters; unknown models must never silently fall back to a cheaper tier.

`app.credit_models` declares the four ORM tables below against the existing Base.
Alembic imports it explicitly. It may import identity_models to register users;
do not modify User or app.models merely to add reverse relationships. No public
CRUD, implicit commit, background task, startup backfill or OAuth hook in A.

## 3. G5A persistent contract

Use named constraints, PostgreSQL UUID, BIGINT and TIMESTAMPTZ. Use bounded
VARCHAR plus CHECK for new finite vocabularies (no new native enum types).
All identifiers/timestamps are non-null except explicitly optional fields.
UUID defaults may be application-side. Monetary columns have no permissive
database defaults. A migration creates empty credit tables, not free money.

### CreditAccount — `credit_accounts`

- `user_id`: primary key, FK users.id ON DELETE RESTRICT, exactly one account/User.
- `cycle_anchor_at`: immutable signup instant copied from User.signed_up_at by B.
- `plan`: free/pro/max; `pending_plan`: nullable free/pro/max, different from plan.
- `created_at`, `updated_at`: updated >= created >= anchor.
- No account balance column; grant balances are the authoritative projections.
  Account row is the future serialization lock, not a second sum to synchronize.
- B validates anchor against User and Plan against Master rules. A does not
  mutate roles or create accounts when a User signs in.

### CreditCycle — `credit_cycles`

- `id` PK, `user_id` FK account RESTRICT, `cycle_index` BIGINT >=0.
- `starts_at`, `ends_at`: exact 2,592,000 elapsed seconds apart. Use UTC/elapsed
  semantics in both SQL constraints and Python; no session-timezone DST drift.
- `plan`: free/pro/max snapshot; `allowance_microcredits`: BIGINT >=0.
- `created_at` >= starts_at. Unique (user_id,cycle_index); unique (id,user_id)
  is the ownership target for composite FKs. Named user/time index.
- B validates alignment with account anchor and allowance with policy under lock;
  a CHECK constraint cannot enforce another row's anchor or total ledger balance.

### CreditGrant — `credit_grants`

- `id` PK, `user_id` FK account RESTRICT, `cycle_id` optional.
- Composite (cycle_id,user_id) FK cycles(id,user_id) RESTRICT prevents foreign
  cycle attribution. Unique (id,user_id) supports ledger/next-stage allocations.
- `kind`: base/bonus. Base requires cycle_id and expires_at; bonus has no cycle_id
  and optional expiry. One base grant per cycle via named partial unique index.
- `created_at`, optional `expires_at` strictly later than created_at.
- `granted_microcredits`, `reserved_microcredits`, `consumed_microcredits`,
  `expired_microcredits`: nonnegative BIGINT, reserved+consumed+expired <= granted.
  Widen the SQL sum to NUMERIC for validation rather than overflowing BIGINT.
- Available = granted - reserved - consumed - expired. Never store another
  available balance. Never transfer an old reservation to the new cycle.
- `reason_code`: safe bounded lowercase code, not unrestricted operator text.
  Human reasons/Audit, permissions and bonus mutation commands belong to G10.
- Named user/expiry/id index for deterministic allocation later.

### CreditLedgerEvent — `credit_ledger_events`

- `id` PK; `user_id` FK account RESTRICT; `grant_id` and composite
  (grant_id,user_id) FK grants(id,user_id) RESTRICT.
- `kind`: grant/adjust/reserve/settle/release/expire.
- `operation_key`: safe opaque code of 1..128 ASCII alphanumeric/underscore/hyphen
  characters; no prompts, email, tokens or caller-provided free text.
- Unique (user_id,operation_key,grant_id,kind). This supports one operation's
  several grant allocations and distinguishes reserve from terminal events.
  Unique keys alone do NOT prove payload-equivalent retries; B/C must compare
  immutable business inputs and reject a collision without changing balances.
- `rate_card_version`: bounded version identifier (`v` plus 1..9 digits, first
  digit nonzero); actual supported version validation lives in policy/next-stage
  writes. V1 is not Google pricing and historical rows must not be rewritten.
- Four signed BIGINT deltas: `granted_delta`, `reserved_delta`, `consumed_delta`,
  `expired_delta`; `created_at` and safe `reason_code`. No arbitrary JSON payload.
- CHECK shapes (arithmetic widened to NUMERIC): grant/adjust means positive
  granted delta, others zero; reserve means positive reserved, others zero;
  settle means negative reserved, nonnegative consumed/expired with their sum
  <= released reservation, granted zero; release means negative reserved,
  consumed/granted zero and 0<=expired<=released reservation; expire means
  positive expired only. All-zero events are invalid.
- Named user/created_at/id index. SQL triggers reject UPDATE, DELETE and TRUNCATE
  with a fixed safe error `credit_ledger_append_only`. This is not protection
  against a database owner disabling triggers or dropping the schema.
- A does not expose a ledger writer. B/C atomically update grant projections and
  append matching ledger deltas in a caller-owned transaction. Summed events
  must reconstruct every grant projection; arbitrary SQL writes remain trusted
  operator capabilities, not a supported product Interface.

These tables intentionally do not contain Reservation, Usage, Job, Enhancement or
Outbox foreign keys. C adds allocation/usage persistence, within its own migration
and file budget. G6/G7 determine safe linkage without undermining existing deletion.

## 4. Migration and compatibility

Exactly one new file/revision: `0004_credit_foundation`, parent
`0003_content_ownership`. Do not edit 0001/0002/0003 or stamp a real DB current.

- Upgrade is additive even with existing Users/Sessions/content. No data reset,
  backfill, rewriting generation rows, seed credit, or create_all fallback.
- Downgrade locks all four credit tables with bounded 5s lock_timeout, checks all
  are empty before any DDL, otherwise refuses `credit_foundation_requires_empty_tables`.
  Drop only new tables/triggers/functions after successful guard. Existing
  content remains untouched. Migration operations are transactional.
- Empty round trips 0004->0003->0004, ->0001->head and ->base->head must pass;
  old 0003 constraints/refusals still apply at their historical revision.
- The old schema verifier contains exact inventory and an embedded 0003 proof.
  Keep that proof explicitly pinned: downgrade empty new tables to 0003, run
  its original 8 nonempty refusals and lock refusal, then upgrade to 0004.
  Do not globally replace every 0003 literal or weaken old assertions.
- Update only current-head expectations in auth runner, ownership fixture and
  authenticated harness. Production schema_control already discovers Alembic
  head; it does not need editing. Retain stale-revision checks for all three
  processes, including refusal at 0003 when code expects 0004, then recovery.
- Add fixed `backend/tests/credit_foundation_support.py` proof loaded by the
  schema verifier as source into its freshly owned migrate container. The image
  does not package tests or pytest; do not assume it does, mount credentials,
  modify Dockerfile or install development dependencies in the runtime image.
  Run using the installed application/SQLAlchemy/asyncpg, with fixed proof mode
  and exact isolated project context; no arbitrary SQL/DSN/target flags.
- Runtime order: empty chain/inventory -> legacy identity -> pinned 0003 proof
  -> additive upgrade with populated legacy fixtures -> credit proof -> stale
  refusal/recovery -> optional existing guarded reset -> exact-project cleanup.
  Credit proof may leave committed synthetic ledger rows in that owned DB. Never
  disable append-only triggers to clean them: teardown removes the isolated DB.
  For --include-reset, preserve/extend existing preview/count checks to include
  populated credit tables and all legacy rows; compare pre-reset snapshots and
  require every application table empty after reset. Without flag, report reset
  not_requested, not pass. No reset on default/preview developer resources.

## 5. Exact G5A non-document allowlist (17)

```text
backend/app/credit_models.py
backend/app/credit_policy.py
backend/migrations/env.py
backend/migrations/versions/0004_credit_foundation.py
backend/tests/test_credit_models.py
backend/tests/test_credit_policy.py
backend/tests/credit_foundation_support.py
backend/tests/test_credit_foundation_support.py
backend/tests/test_alembic_schema.py
scripts/verify_schema_migrations.py
backend/tests/test_verify_schema_migrations_script.py
scripts/verify_auth_sessions.py
backend/tests/test_verify_auth_sessions_script.py
scripts/mock_auth_support.py
backend/tests/ownership_support.py
backend/tests/test_ownership_persistence.py
backend/tests/test_mock_auth_support.py
```

This is an allowlist, not permission to invent changes in every path. Count
committed + staged + unstaged + new non-document paths cumulatively from 6537025.
No rename/deletion laundering. If an 18th path or a second migration is necessary,
STOP and request redesign; the general 20-path ceiling does not expand this list.
Harness edits are only head compatibility and its tests; suites, workload,
budgets, assertions, quotas and worker settings stay unchanged.

## 6. G5A acceptance matrix

| ID | Required assertion / proof |
|---|---|
| A01 | Exactly four additive tables, one new linear revision, old revision bytes unchanged |
| A02 | Populated 0003 User/Session/Job/Asset/Enhancement/Outbox rows and legacy schema survive upgrade unchanged |
| A03 | Empty down/re-up/full-chain round trips; populated credit downgrade refuses before DDL; lock timeout refuses |
| A04 | Account uniqueness, valid Plans/pending plan, timestamp order, unknown User FK and delete RESTRICT |
| A05 | Cycle uniqueness, nonnegative index, exact elapsed 30 days, cross-owner references refused |
| A06 | Base/bonus shape, one base grant/cycle, valid expiry and safe reason code |
| A07 | Grant nonnegativity/BIGINT bounds, sums cannot overspend; derived available remains correct |
| A08 | Every ledger event shape, zero/overflow/unsafe key rejection and version syntax |
| A09 | Ledger FK ownership/unique operation keys; UPDATE/DELETE/TRUNCATE refused, rows unchanged |
| A10 | Committed valid fixture deltas reconstruct grant projections; forced transaction rollback changes neither |
| A11 | Two independent concurrent inserts for same account/cycle/ledger key: one commit, one unique rejection, exact final counts (no billing-service idempotency claim) |
| A12 | Free/Pro/Max entitlement table exact; no role-based bypass argument or mutable global policy |
| A13 | All seven V1 rates, zero/exact/scaled/maximum values; mixed Gemini input/output and video milliseconds without floats |
| A14 | Unknown version/meter/Plan; bool/float/string/negative/overflow refused without input in error |
| A15 | Signup/before-end/exact-end/multiple skipped cycles/leap-year/DST-equivalent instants/naive/future signup/overflow |
| A16 | Schema inventory/metadata parity, no new native enum, no startup account grant or identity/content mutation |
| A17 | backend/worker/dispatcher reject stale 0003 and recover to 0004; reset preview non-mutating and exact guarded reset |
| A18 | Legacy identity and pinned ownership schema proof retain all old checks, including eight nonempty refusals |
| A19 | Auth PostgreSQL/Redis regression once at 0004; no raw identity/session evidence |
| A20 | Explicit ownership all/2 yields all four fresh cycles with legacy metadata348/delete-race2 and F/O/V/E, not just single-suite success |
| A21 | Two separate schema+credit cycles at same clean code SHA, bounded runtime, truthful receipts and independent resource-zero cleanup |
| A22 | Full Linux backend, existing frontend lint/build/Session/browser, final-head required CI and actual squash merge |

Unit tests target policy/ORM Interface, real PostgreSQL tests prove enforcement.
Do not call a compiled string or inspected source a database proof. All A01–A22
must map to tests/evidence before F2 APPROVE. A11 is uniqueness evidence only;
overspend/settlement races remain C and are not claimed by this Goal.

## 7. Successor planning envelopes (not executable Goals)

### G5B — after A merge

Proposed small Interface: `ensure_cycle(session, user_id, now)`,
`change_plan(session, user_id, target, now, operation_key)`,
`grant_bonus(session, user_id, amount, expiry, reason_code, operation_key, now)`.
Caller owns commit/rollback; lock account in a documented User/account order;
serialize first-account creation under User lock. No implicit commit, HTTP
endpoint, background scheduler or public Master promotion in B. Lazy renewal on
first accounting access must not change signup anchor or award missed cycles
as accumulated spendable credit. Master starts Max; suspension/auth remain intact.

Before B freeze resolve exact pending downgrade replacement/cancel semantics,
expired base/bonus handling with held reservations, upgrades with existing
reserved/consumed amounts, repeated operation payload collision, and immutable
rate/ledger references. Do not reinterpret the accepted allowance or expiry
policy silently. Require tests of just-before/exact/after renewal, skipped cycles,
same-operation retries, two independent DB connections racing initialization and
renewal, rollback, plan transition matrix, bonus expiry and ledger reconstruction.
Expected additions concentrate in credit lifecycle + tests/proof; at most one
migration only if demonstrated necessary. Re-enumerate paths from merged A.

### G5C — after B merge

Proposed Interface: `reserve(session, request, now)`,
`settle(session, reservation_id, usage, delivery, operation_key, now)`,
`release(session, reservation_id, reason_code, operation_key, now)`.
Same caller-owned transaction; lock account/grants/reservation in fixed order.
Add reservation/allocation/Usage records in at most one migration. A reservation
retains its rate version and exact grants even when renewal or upgrade occurs.
Provider work never runs within that transaction. The Interface must compose
with Job+Outbox creation and terminal transitions later in G6/G7.

Before C freeze determine deterministic grant consumption (expiring first and
stable tie-break), expiry of released old grants, estimation ceilings/output
limits, usage exceeding reservation, failure/partial-delivery matrix and payload
collision rejection. Do not implement free excess usage, negative balances or
double child-job reservations as an unstated policy. Prove serialized overspend
refusal, duplicate queue delivery/settlement, late old-cycle completion, rollback
of usage+ledger+projections, expiry/reserve/settle races and original usage source.
Ordinary test transactions prove composition; product Jobs stay unwired until G7.

## 8. Delivery, evidence and rollback

G5A Goal freezes Todo1–8, F1–F4, commands and budgets. Prepared is not In Progress.
Use Ready PR and existing protected squash auto-merge only on an explicit Goal
execution request; preparation makes no PR or CI/merge completion claim.
Preserve failures and exact cleanup evidence; redact identities and environment.

A rollback is a reviewed code revert plus empty-credit-schema downgrade only
when its guard permits; otherwise stop and preserve data for a forward fix.
After A, an existing dev DB at 0003 is intentionally stale for new code until an
operator-approved additive migration. This Goal never upgrades/resets preview
or development DBs. No live deployment safety or billing enforcement is claimed.
