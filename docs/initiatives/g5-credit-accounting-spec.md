# G5C — Credit reservation and settlement specification

Status: `G5C1 Mock Verified — Merged; G5C2 locally Mock Verified / delivery pending`, 2026-09-04. This document is the
normative aggregate design for Issues
[#117](https://github.com/bbungjun/AI_multimodal_platform/issues/117),
[#120](https://github.com/bbungjun/AI_multimodal_platform/issues/120), and
[#121](https://github.com/bbungjun/AI_multimodal_platform/issues/121). It records
approved policy and executable boundaries. G5C1 implementation evidence is linked
below; G5C2 code and local proof are complete at `41b1bf3`, while final-head CI and
protected merge remain delivery evidence.

## 1. Problem, inputs and split decision

G5A provides versioned integer pricing and empty account/cycle/grant/ledger
persistence. G5B provides caller-owned transactions, exact 30-day cycles, Plan
transitions, grant issuance/expiry, immutable lifecycle command replay and this
lock prefix:

```text
User -> CreditAccount -> current CreditCycle -> CreditGrants ordered by id
```

Generation still cannot reject exhausted accounts, hold credit before external
work, preserve original usage, or atomically turn a hold into consumption or a
refund. Product callers must not derive balances or write ledger rows themselves.
The new deep Module is `app.credit_accounting`; its database tables and ledger
events are Implementation details behind a three-operation Interface.

A single G5C Goal is not executable under the repository's 20-path limit. Adding
one Alembic head requires 15 existing schema/auth/ownership/credit proof paths to
move from `0005` to `0006`. Combining that compatibility work with the new Module,
its unit tests and its real PostgreSQL verifier requires at least 22 paths. G5C is
therefore split without changing product policy:

| Slice | Issue | Module / delivery boundary | Migration |
|---|---|---|---:|
| G5C1 | [#120](https://github.com/bbungjun/AI_multimodal_platform/issues/120) | Mock Verified and merged by [PR122](https://github.com/bbungjun/AI_multimodal_platform/pull/122): four accounting tables, constraints, mutation guards and head compatibility | exactly one, `0006_credit_accounting_persistence` |
| G5C2 | [#121](https://github.com/bbungjun/AI_multimodal_platform/issues/121) | Frozen execution design: `reserve`, `settle`, `release`, deterministic allocation, replay and PostgreSQL race/rollback proof | zero |

Issue117 is the G5C aggregate, not an executable Goal. G5C2 freezes its own exact
paths and Goal only after G5C1 actually merges. G5C completion does not mean Jobs
are billed: G6/G7 remain the product-call-site integration slices.

## 2. Small accounting Interface

G5C2 will add `app.credit_accounting` and export exactly these operations plus
immutable request/result value objects:

```text
reserve(session, *, request, now) -> ReservationReceipt
settle(session, *, user_id, reservation_id, usage, delivery,
       operation_key, now) -> TerminalReceipt
release(session, *, user_id, reservation_id, usage, reason_code,
        operation_key, now) -> TerminalReceipt
```

`ReservationRequest` contains `user_id`, one safe `operation_key`, and an ordered
tuple of unique `UsageEstimate(meter, maximum_units)`. `UsageReport` is an ordered
tuple of unique `UsageLine(meter, actual_units, source)`. The order is canonicalized
by meter before persistence or comparison; caller ordering is never meaningful.

`ReservationReceipt` exposes reservation_id, operation_key, status,
reserved_microcredits, rate_card_version and replayed. `TerminalReceipt` exposes
reservation_id, operation_key, status, consumed_microcredits,
released_microcredits, usage_line_count, effective_at and replayed. Grant IDs,
ledger shapes and row mutation are not part of the caller Interface.

Every call requires an already-active `AsyncSession` transaction. The Module may
use a nested savepoint but never begins or commits the outer transaction, never
rolls it back, never creates an engine and never reads the clock. A successful
return remains uncommitted until the caller commits. A caller rollback must undo
the reservation/terminal rows, usage, allocations, ledger events and grant
projections together. Provider work is forbidden while accounting locks are held.

The Module consumes public G5B lifecycle behavior rather than duplicating renewal
or grant issuance. It preserves this complete lock order:

```text
User -> CreditAccount -> current CreditCycle -> all CreditGrants ordered by id
     -> CreditReservation -> items ordered by meter
     -> allocations ordered by ordinal
```

Rows already present in the ORM identity map are refreshed under lock. Never lock
an account before its User, never lock grants in allocation priority order, and
never silently retry a lock timeout/deadlock/serialization failure. The caller
owns `lock_timeout` and any retry policy.

## 3. Requests, quotes and admission

- Valid meters remain exactly the seven G5A V1 meters. One request has 1..7 unique
  meters and each maximum_units is a strict positive integer. Boolean, float,
  string, duplicate/unknown meter, zero, negative and signed-BIGINT overflow are
  refused before mutation.
- `reserve` snapshots `RATE_CARD_VERSION` and calls `quote_usage` for each line.
  The exact integer sum must be positive and fit signed BIGINT. No floating point,
  provider price lookup or cheaper-model fallback is allowed.
- The current account Plan must permit every normalized meter. G6/G7 remain
  responsible for mapping public model identifiers, enforcing image/duration
  shape and constructing estimates. Gemini callers reserve exact known input
  tokens plus their configured hard maximum output tokens. Imagen callers reserve
  requested maximum images. Veo callers reserve requested maximum milliseconds.
  Provider output limits must make actual billable units no greater than the hold.
- A suspended User cannot create a new reservation. An already-running reservation
  may still settle or release after suspension. A Master uses Max policy but has
  no free-credit or usage-recording bypass.
- G5B first materializes/renews the current cycle and expires available credit.
  All grants are locked by UUID order. Allocation then uses a separate stable
  priority: finite `expires_at` first, earliest expiry, earliest `created_at`, then
  UUID; grants without expiry are last. Only positive available credit is used.
- The reservation is all-or-nothing. Insufficient total available credit raises
  `monthly_credit_exhausted`; it creates no reservation, allocation, ledger event
  or projection change. Success increments each selected grant's reserved
  projection and appends one reserve ledger event per allocation.
- A reservation snapshots its quote lines, rate-card version, total and exact
  grant allocations. Renewal, Plan upgrade, bonus expiry or later rate versions
  never move or reprice an existing hold.

G5C has no Job/Outbox/Prompt/Asset foreign key. G6/G7 must call `reserve` inside
the same outer transaction that creates the top-level Job and OutboxEvent. A
pipeline reserves once at that top-level call; preventing a caller from inventing
a distinct child operation key requires the future product linkage and is not
falsely claimed by G5C.

## 4. Settlement and release matrix

The stored quote version, not the process's newest version, prices a terminal
operation. Terminal usage meters must be a subset of the reserved meters, unique
after canonicalization and valid strict nonnegative signed-BIGINT units. A missing
reserved meter is equivalent to zero actual units. Unknown or extra meters fail
closed. Original units and source are persisted separately from internal credit.

| Situation | Operation | Usage retained | Credit result | Delivery |
|---|---|---|---|---|
| Complete deliverable | `settle` | actual per-meter units/source | consume actual quote; release remainder | `delivered` |
| Partial image/video result | `settle` | delivered units/source | consume delivered units only; release remainder | `partial` |
| Provider failed/timed out/rate-limited, no deliverable | `release` | supplied attempt lines, including zero-unit evidence | consume zero; release all | `no_deliverable` |
| Cancelled before provider attempt | `release` | empty tuple | consume zero; release all | `no_deliverable` |
| Asset/delivery failed after provider attempt, no deliverable | `release` | observed attempt lines | consume zero under accepted product policy | `no_deliverable` |

`settle` accepts only `delivered|partial`, at least one usage line and a positive
total charge. Each actual line must be no greater than its reserved maximum.
Anything larger raises `credit_usage_exceeds_reservation` without mutation; G6/G7
must enforce provider maximums so this indicates a contract violation, not a free
overage policy. No negative balance, automatic top-up, debt or silent truncation.

`release` fixes delivery to `no_deliverable`; usage may be empty and all charged
amounts are zero. Its reason is one of `provider_failed`, `provider_timeout`,
`provider_rate_limited`, `cancelled_before_delivery`, or `delivery_failed`. This
preserves provider-attempt usage for operations analysis without charging for a
result the user cannot use.

Terminal allocation walks the reservation's immutable allocation ordinals.
Settlement consumes the actual total from that sequence and releases the rest.
For each grant, the full allocated hold leaves `reserved_microcredits`. Consumed
credit enters `consumed_microcredits`. An unused amount released at or after that
grant's `expires_at` enters `expired_microcredits`; otherwise it becomes available
by projection arithmetic. Release follows the same expiry rule with zero consumed.
One settle/release ledger event per allocation reconstructs the projections.

## 5. Idempotency namespaces and safe failures

Lifecycle, reservation and terminal commands are distinct idempotency domains:

- G5B `credit_operations`: `(user_id, operation_key)` for Plan/bonus commands.
- G5C reservation: `(user_id, reserve_operation_key)` in reservations.
- G5C terminal: one partial unique `(user_id, terminal_operation_key)` across all
  reservations, plus exactly one terminal transition per reservation.

The same text may exist in different domains because each represents a different
business verb. G6/G7 must generate opaque keys in the correct domain. Ledger keys
are not caller strings: G5C derives bounded `reserve_<reservation hex>` and
`terminal_<reservation hex>` keys, eliminating cross-domain ledger collisions and
preventing free text from entering the ledger.

A retry with the same key and byte-equivalent normalized business payload returns
the original IDs/timestamp/outcome with `replayed=true`, even after renewal or User
suspension. A changed meter, unit, source, delivery, reason, reservation or owner
raises `credit_idempotency_conflict` and changes nothing. Missing User still fails.
Rollback before commit leaves no replay receipt, so a later retry executes once.

`CreditAccountingError(code)` is not an HTTP exception and never contains identity,
prompt, usage payload, SQL or credentials. Fixed codes are:

```text
credit_transaction_required
credit_user_missing
credit_input_invalid
credit_plan_refused
monthly_credit_exhausted
credit_reservation_missing
credit_reservation_state_conflict
credit_usage_exceeds_reservation
credit_idempotency_conflict
credit_account_inconsistent
credit_amount_overflow
credit_busy
```

Unexpected database errors never become success. Contention SQLSTATEs map to
`credit_busy` only after savepoint rollback; corruption, ownership mismatch and
projection/ledger inconsistencies fail closed.

## 6. G5C1 persistent contract

G5C1 adds exactly revision `0006_credit_accounting_persistence`, parent
`0005_credit_lifecycle_operations`. Existing migrations and populated G5A/G5B
tables remain unchanged. All new tables are empty after upgrade. Use named
constraints, PostgreSQL UUID/BIGINT/TIMESTAMPTZ, bounded VARCHAR vocabularies and
widened NUMERIC arithmetic where sums could overflow.

### `credit_reservations`

- UUID `id` primary key; `user_id` references CreditAccount RESTRICT; unique
  `(id,user_id)` supports ownership FKs.
- Safe `reserve_operation_key` VARCHAR96 and unique `(user_id,key)`; bounded
  `rate_card_version`; positive `reserved_microcredits`; `created_at`.
- `status` is `held|settled|released`. Held rows have null terminal fields.
  Terminal rows have safe `terminal_operation_key`, `terminal_at >= created_at`,
  safe `terminal_reason_code`, and delivery `delivered|partial|no_deliverable`.
  Settled allows delivered/partial; released requires no_deliverable.
- A partial unique index on `(user_id,terminal_operation_key)` excludes nulls.
  A named `(user_id,status,created_at,id)` index supports account inspection.
- A trigger permits only one `held -> settled|released` transition and only the
  terminal fields/status to change. UPDATE after terminal, DELETE and TRUNCATE
  fail with `credit_reservation_immutable`.

### `credit_reservation_items`

- `(reservation_id,meter)` primary key, explicit `user_id`, and composite
  `(reservation_id,user_id)` ownership FK to reservation RESTRICT.
- Meter is one of the seven V1 names. `maximum_units` and
  `quoted_microcredits` are strict positive BIGINT. Exact rate equality is checked
  by the Module/proof because a CHECK cannot call mutable application policy.
- Unique `(reservation_id,user_id,meter)` supports Usage ownership FKs. Rows are
  append-only; UPDATE/DELETE/TRUNCATE raises `credit_accounting_append_only`.

### `credit_reservation_allocations`

- `(reservation_id,grant_id)` primary key; explicit `user_id`; composite owner
  FKs to reservation and grant, both RESTRICT.
- Nonnegative integer `ordinal`, unique per reservation, and positive
  `reserved_microcredits`. Ordinal records deterministic terminal consumption
  order independently of later cycle/rate changes.
- Named `(grant_id,reservation_id)` index supports held-grant inspection. Rows are
  append-only with the same fixed error.

### `credit_usage_records`

- `(reservation_id,meter)` primary key; explicit `user_id`; composite FK to the
  corresponding reservation item. Safe `terminal_operation_key`, stored
  `rate_card_version`, nonnegative `actual_units` and `charged_microcredits`,
  `recorded_at`, source and delivery.
- Source is exactly `provider_reported|platform_measured|mock_estimate|estimated`.
  Delivery is exactly `delivered|partial|no_deliverable`; no-deliverable requires
  zero charged credit. A unique `(user_id,terminal_operation_key,meter)` prevents
  duplicate Usage under queue redelivery.
- Rows are append-only with `credit_accounting_append_only`. They contain no
  prompt, provider response, email, credential, filename or free text.

The C1 downgrade takes bounded ACCESS EXCLUSIVE locks in reverse dependency-safe
order and refuses with `credit_accounting_requires_empty_tables` if any new table
has a row. Empty downgrade to0005 and re-upgrade succeed; populated refusal leaves
head/data intact and supports recovery. Never reset a development or preview DB.

## 7. Verification contract

### G5C1 acceptance

| ID | Requirement |
|---|---|
| C101 | Frozen base/branch/hash, clean tracked/index state and mock-only environment |
| C102 | Exact20 non-document allowlist, exactly one new0006 migration, 0001–0005 byte-identical |
| C103 | Exact four-table inventory, columns, types, named constraints/indexes/triggers |
| C104 | Cross-owner reservation-item/allocation/Usage references are refused by PostgreSQL |
| C105 | Invalid status/key/version/meter/source/delivery/time/negative/overflow shapes are refused |
| C106 | Reservation permits held-to-one-terminal only; child/Usage mutation and all protected deletes/truncates are refused with fixed safe codes |
| C107 | Existing populated account/cycle/grant/operation/ledger rows survive upgrade unchanged; new tables are empty |
| C108 | Empty0006 downgrade/re-upgrade works; each populated new table blocks downgrade and recovers at0006 with data intact |
| C109 | Backend, worker and dispatcher reject stale0005 and recover to0006; guarded reset remains preview-only/non-mutating unless exact authorization |
| C110 | Two fresh isolated schema/accounting cycles produce matching counts and independent resource-zero cleanup |
| C111 | Existing G5A foundation and G5B lifecycle proof remain true at head0006 |
| C112 | Existing auth Postgres/Redis proof and ownership `--suite all --cycles 2` remain true |
| C113 | Full Linux backend and unchanged frontend regressions pass; Windows-only known exception is reproduced from untouched base before documentation |
| C114 | No writer/public API/product/provider/cloud/frontend/Plan/Master/Audit capability is claimed |
| C115 | Problem/design/verification/result/risk documentation is safe and consistent |
| C116 | Ready PR, final-head verify and both Scan/SBOM checks succeed; protected squash is actually MERGED; only Issue120 closes |

The new `credit_accounting_schema_support.py` is executed inside the owned migrate
image by the existing schema verifier; tests/pytest are not assumed installed in
that runtime. Run the schema verifier twice in separate
`schema-verify-[a-z0-9]{12}` projects. Each run owns only its exact project and
must independently leave matching containers/volumes/networks at zero.

Timeouts: each schema work/cleanup/total is 300/90/390s (two <=780s); lifecycle
300/90/390s; auth total300s; ownership work360/cleanup90 per cycle and aggregate
all<=1800s; Linux600s; Windows120s; frontend600s. A timeout is No-Go: clean only
the exact owned project, retain the first failure and STOP for redesign. Do not
inflate a limit or auto-rerun.

### G5C2 frozen acceptance

| ID | Requirement |
|---|---|
| C201 | Start from merged PR122 squash, matching Goal hash, Issue/branch and clean tracked/index state with `AI_PROVIDER=mock` |
| C202 | Change only the exact six non-document paths in section8; zero migration and no existing schema/model/lifecycle/product path change |
| C203 | Export only the three operations and immutable request/result value objects from section2; errors are fixed safe codes, not HTTP/SQL/identity text |
| C204 | Require a caller-owned active AsyncSession transaction; use a nested savepoint; never begin/commit/rollback the outer transaction or create an engine/clock |
| C205 | Normalize UTC time, safe keys and canonical unique meter tuples; reject bool/float/string, unknown/duplicate/empty/overflow input before mutation |
| C206 | Quote every estimate with stored V1 integer policy, enforce current Plan meters, positive BIGINT total and no provider pricing/fallback |
| C207 | Reserve replay is checked under User lock before renewal/expiry; equal normalized payload returns the original receipt, changed payload conflicts atomically |
| C208 | New reserve composes only with public `ensure_cycle`, then refresh-locks Account/current Cycle/all grants by UUID; no private lifecycle import or lock inversion |
| C209 | Allocation is expiring-first, then expiry/created_at/UUID, all-or-nothing; insufficient credit returns `monthly_credit_exhausted` with no lifecycle/accounting side effect |
| C210 | Reserve persists header/items/ordinal allocations, updates grant reserved projections and appends one derived-key reserve ledger event per allocation atomically |
| C211 | Active normal Users use their Plan; Master has Max policy without bypass; suspended User cannot make a new hold but may replay a committed hold |
| C212 | Terminal calls lock User→Account→latest Cycle→all grants by UUID→Reservation→items by meter→allocations by ordinal and refresh stale identity-map rows |
| C213 | `settle` accepts delivered/partial, at least one line and positive total charge; meters are a subset and actual units never exceed held maxima |
| C214 | `release` fixes no-deliverable, permits empty or attempt Usage, validates one fixed reason and always charges zero |
| C215 | Settlement uses the reservation's stored rate version; original units/source remain separate from charged microcredits; missing held meters mean zero Usage |
| C216 | Terminal allocation consumes ordinal holds, releases remainder, and sends unused expired-grant credit to expired rather than available |
| C217 | Terminal atomically updates reservation once, appends supplied Usage and one settle/release ledger event per allocation, and updates all projections coherently |
| C218 | Same terminal key/equal normalized reservation+usage+delivery/reason returns the original receipt; changed payload/owner/reservation conflicts with no side effect |
| C219 | A second terminal key or settle/release after terminal returns state conflict; missing/cross-owner reservation is a safe missing error without existence leak |
| C220 | Before money movement, every locked grant projection reconstructs from its ledger and reservation item/allocation sums match the held total; corruption fails closed |
| C221 | Signed-BIGINT sums and projection deltas use widened arithmetic and reject overflow, negative, impossible or under-reserved state without mutation |
| C222 | A caught validation/contention rejection leaves the caller transaction usable; deliberate outer rollback removes reservation/terminal/Usage/ledger/projections together |
| C223 | Existing lifecycle renewal/expiry and a late old-cycle terminal serialize without moving or repricing the original allocation |
| C224 | Race1: two different holds compete for one remaining balance; exactly one succeeds and no overspend occurs |
| C225 | Race2: same reserve key/equal payload; one reservation/allocation/event set and two equivalent receipts |
| C226 | Race3: same reserve key/different payload; one winner and one idempotency conflict without mixed rows |
| C227 | Race4: same terminal key/equal payload; one terminal/Usage/event set and two equivalent receipts |
| C228 | Race5: same terminal key/different payload or reservation; one winner and one conflict without mixed projections |
| C229 | Race6: settle versus release on one hold; exactly one terminal outcome and one projection transition |
| C230 | Race7: renewal/expiry versus reserve; lock overlap is observed and final allocation/refusal is serializable |
| C231 | Race8: renewal/expiry versus late old-cycle settle; original grant attribution and expired remainder are correct |
| C232 | Two fresh fixed accounting verifier cycles each report all eight groups, races8, checks>=160, same committed SHA/head0006 and exact resource cleanup0 |
| C233 | One schema, lifecycle, auth and ownership-all2 compatibility run plus Linux backend, Windows/base exception reproduction, Compose and unchanged frontend all pass |
| C234 | Problem/cause/decision/failed proof/results/rollback are documented; Ready PR final-head required3 CI succeeds, protected squash actually merges, and Issues121/117/114 close |

The Goal maps tests to strict quote/Plan input; deterministic
multi-grant allocation; exact exhaustion and all-or-nothing refusal; same/different
reservation replay; complete/partial/no-deliverable matrix; original source/units
versus credit; same/different terminal replay; stale identity-map refresh; caller
rollback; old-cycle late settle/release and expired remainder; projection-ledger
reconstruction; suspended/Master behavior; overflow/corruption; and these real
PostgreSQL races:

1. two holds competing for one remaining balance: exactly one success;
2. same reserve key/equal payload: one reservation/allocation/event set;
3. same reserve key/different payload: one winner, one collision;
4. same terminal key/equal payload: one terminal/Usage/event set;
5. same terminal key/different payload: one winner, one collision;
6. settle versus release on one reservation: exactly one terminal outcome;
7. expiry/renewal versus reserve: serialized valid allocation or refusal;
8. expiry/renewal versus late settle: held grant attribution and remainder correct.

Two independent accounting verifier cycles must report eight groups, races8,
checks>=160,
exact same-code revision and resource-zero cleanup. G5C2 has zero migration and
does not change the C1 schema to make a failing implementation pass.

## 8. Exact paths

G5C1 non-document allowlist, cumulative from base `ffc4b506466662f3e57e0f8dca72e16955273749`:

```text
backend/app/credit_models.py
backend/migrations/versions/0006_credit_accounting_persistence.py
backend/tests/test_credit_models.py
backend/tests/test_alembic_schema.py
backend/tests/credit_accounting_schema_support.py
backend/tests/test_credit_accounting_schema_support.py
backend/tests/credit_foundation_support.py
backend/tests/test_credit_foundation_support.py
backend/tests/credit_lifecycle_support.py
backend/tests/test_credit_lifecycle_support.py
scripts/verify_credit_lifecycle.py
backend/tests/test_verify_credit_lifecycle_script.py
scripts/verify_schema_migrations.py
backend/tests/test_verify_schema_migrations_script.py
scripts/verify_auth_sessions.py
backend/tests/test_verify_auth_sessions_script.py
scripts/mock_auth_support.py
backend/tests/test_mock_auth_support.py
backend/tests/ownership_support.py
backend/tests/test_ownership_persistence.py
```

This is an allowlist, not a requirement to touch every path. A21st path, a second
migration, modification of0001–0005, or accounting writer means STOP/replan.
Allowed documents are current-work, the canonical initiative, G5 split spec, this
spec, testing, local-mock runbook, portfolio README and Issue120 record.

G5C2 has exactly these six non-document paths, cumulative from merged PR122 squash
`68e3df6254b1aa9acfba5f1d4bc7965e60b06fa4`:

```text
backend/app/credit_accounting.py
backend/tests/test_credit_accounting.py
backend/tests/credit_accounting_support.py
backend/tests/test_credit_accounting_support.py
scripts/verify_credit_accounting.py
backend/tests/test_verify_credit_accounting_script.py
```

This is both an allowlist and the expected implementation set. A seventh code
path, any migration, schema/model/lifecycle change, or product caller means
STOP/replan. Allowed documents are current-work, the canonical initiative, this
aggregate spec, testing, local-mock runbook, portfolio README and Issue121 record.
G5C2 must not change Job/Prompt/Asset/Outbox/worker/state-machine/frontend,
OAuth/provider/cloud, Plan/Master/Audit, dependency, Compose, CI or infrastructure.

## 9. Delivery, rollback and remaining risk

Preparation changes only documents, Issues and a branch; it performs no migration,
Docker mutation, database reset or billing operation. G5C1 execution uses local
Docker with `AI_PROVIDER=mock`, preserves development/preview data, records each
failed approach, and ends only after actual protected squash merge. Issue120 then
closes; Issues121/117/114 remain open.

G5C1 merged by PR122 as `68e3df6`; its tested final head and squash tree matched.
Local final-SHA evidence at `b4ce32e` passed two independent schema/accounting
cycles (42 checks and four populated downgrade cases each), existing credit90/races3,
G5B lifecycle8/races8, auth PostgreSQL/Redis, ownership/file four-cycle aggregate,
Linux1347, and unchanged frontend48+34. Every owned project cleaned to zero.
PR122 final-head verify and both Scan/SBOM checks succeeded. Issue120 is closed;
Issues121/117/114 remain open for the frozen G5C2 delivery.

Rollback is a reviewed code revert plus downgrade only when all four new tables
are empty. Once any accounting row exists, preserve data and use a forward fix;
never force-drop rows or bypass the downgrade guard. Product-level abandoned-hold
reconciliation, Job linkage, terminal state composition, concurrency admission,
personal UI, Master/Audit and real provider behavior remain explicit later Goals.

G5C2 local verification at `41b1bf3` passed two independent accounting projects,
each with eight groups, eight observed races and299 checks. Schema, lifecycle,
auth and ownership-all2 compatibility, Linux1429 and unchanged frontend48+34 also
passed with every owned Docker project cleaned to zero. Two earlier ownership
harness failures were preserved and cleaned before a complete fresh run. These
results establish the accounting Module only; G6/G7 still own generation callers.
