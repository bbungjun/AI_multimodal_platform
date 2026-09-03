# G5B — Credit lifecycle executable specification

Status: Prepared / awaiting hash-bearing execution approval, 2026-09-04.
Issue [#116](https://github.com/bbungjun/AI_multimodal_platform/issues/116);
parent [#114](https://github.com/bbungjun/AI_multimodal_platform/issues/114).
Branch: `codex/issue-116-credit-lifecycle`.
Base: `a003257c88e09d3e5404a73b44ebdf6deb4650db`, actual G5A PR118 squash.
No G5B code or runtime proof has been produced during preparation.

## 1. Scope and predecessor Interface

Product policy stays in [the canonical initiative](auth-credits-master-console.md),
Plans and Entitlements / Rate Card V1 / Admission and Settlement Invariants.
[G5A sections2–4](g5-credit-foundation-spec.md) provide four ORM tables, immutable
`plan_policy`, `quote_usage`, `cycle_bounds`, microcredits and packaged head0004.
B does not change the prices, entitlements, signup anchor or existing four-table
DDL. G5A is actually merged; [completion evidence](https://github.com/bbungjun/AI_multimodal_platform/issues/115#issuecomment-5528702729).

B implements one Credit lifecycle Module: account initialization, lazy renewal,
Plan transitions, bonus grants, expiry of available amounts and command replay.
Caller-owned AsyncSession and explicit aware time are its Seams. No repository
wrapper, alternate datastore, generic command/event framework or public endpoint.

Excluded: signup/OAuth hooks, role/status mutations, public Master controls/Audit,
Reservation/Usage tables or workflows, debit/settlement, Job/Outbox/worker changes,
provider calls, frontend features, scheduler, payment, cloud and infrastructure.
G5C will consume the transaction/expiry contract; G6/G7 perform product wiring.

## 2. Small caller Interface

New `app.credit_lifecycle` exports exactly these operations and immutable results:

- `ensure_cycle(session, *, user_id, now) -> CycleView`
- `change_plan(session, *, user_id, target_plan, operation_key, now) -> MutationReceipt`
- `grant_bonus(session, *, user_id, amount_microcredits, expires_at,
  reason_code, operation_key, now) -> MutationReceipt`

CycleView: user_id, plan, pending_plan, cycle_id, cycle_index, starts_at, ends_at,
allowance_microcredits and base_grant_id. No stored/account-level balance.
MutationReceipt: operation_key, kind, outcome, effective_at, cycle_id,
optional grant_id and replayed flag. A replay returns the original IDs, outcome
and effective_at, not a newly computed current-cycle receipt.

Caller requirements: existing active AsyncSession transaction, one task/User per
transaction, never share a Session across concurrent tasks. No implicit begin of
an outer transaction, commit, rollback of the caller's outer transaction, engine
creation or clock read. Successful writes/locks remain pending until caller commit.
Each public call uses a nested savepoint so a caught domain rejection does not
leave partial B changes; normal SQLAlchemy savepoint entry may flush caller-pending
state, so callers must flush their own prerequisites before invoking B. Caller
rollback must undo account/cycle/grant/operation/ledger changes together.

All decisions use fresh locked rows, including when the ORM identity map already
contains a stale instance (refresh/populate_existing required). Lock order:
User -> CreditAccount -> current CreditCycle -> CreditGrants ordered by id.
User lock serializes first-account creation and also Plan/bonus/expiry operations.
Future G5C must respect this order; never acquire account then User. Locks remain
until outer transaction end; no provider work may be done while holding them.
No silent retry of transaction failures. Caller controls lock_timeout; B does not
change session/transaction settings. Map contention failure to a fixed safe code
after savepoint rollback and let the caller decide whether to retry.

Use `CreditLifecycleError(code)`, never HTTP exceptions/raw SQL/identity in errors.
Fixed codes: credit_transaction_required, credit_user_missing,
credit_input_invalid, credit_plan_refused, credit_clock_regressed,
credit_account_inconsistent, credit_idempotency_conflict, credit_amount_overflow,
credit_busy. Unexpected DB failures are not reported as successful operations.
Reject naive time, pre-signup time, non-UUID identity, unsafe key/reason and
bool/float/string/nonpositive/overflow bonus amount before mutation. Normalize
aware timestamps to UTC with microseconds. New writes require now >= account.updated_at.
Do not accept caller role, allowance, ledger deltas or an unlimited-credit switch.

## 3. Lifecycle rules proposed for execution approval

These resolve previously open B details without changing accepted allowances.
The hash-bearing execution request approves this section; preparation alone is
not runtime implementation or authorization to publish a mutation endpoint.

### Initialization and renewal

- First accounting access creates exactly one account from User.signed_up_at.
  Normal User starts Free; Master starts Max. Existing legacy users are lazy, not
  backfilled. Initial cycle is the cycle containing now, not necessarily index0.
- Materialize only the current cycle and one base grant, with its full allowance,
  expiry=cycle.end and created_at=now. No spendable grants for skipped cycles.
  One grant ledger event accompanies the base projection in the same transaction.
- At an exact boundary, apply a pending downgrade before creating the new cycle;
  clear pending_plan. A skipped interval applies that pending Plan to the current
  materialized cycle without manufacturing intermediate cycles or credits.
- No signup-anchor changes. Existing account anchor must equal User signup.
  Cycle bounds/Plan/allowance and base grant ownership must be internally coherent;
  reject corruption, do not repair/delete/reissue silently.
- A Master account must already be Max with no pending lower Plan, otherwise fail
  closed; future G10 must coordinate promotion with Plan change. B never promotes.
- ensure_cycle permits suspended Users for future accounting reconciliation, but
  does not grant admission/auth rights. New change_plan/grant_bonus calls reject
  suspended Users. Valid previously committed command replay is read-only and
  remains available after suspension; missing User still refuses.

### Plan transitions

| Request relative to effective current Plan | Behavior |
|---|---|
| Higher Plan | Immediate; replace cycle allowance with higher entitlement, add only allowance difference to the same base grant, preserve reserved/consumed/expired, append adjust event; clear pending downgrade |
| Lower Plan | Set/replace pending_plan for next cycle; no current allowance or balance reduction |
| Same as current with pending lower Plan | Cancel pending downgrade |
| Same as current without pending | No-op |
| Same as existing pending lower Plan | No-op (keep original pending target) |
| Master -> Free/Pro | Refuse; no role/credit bypass |

On a NEW command at a boundary, first renew/apply pending state, then interpret
the requested Plan against that effective current Plan. Thus a new request can
upgrade that new cycle. On a replay, do not renew or reinterpret anything.
Cycle.plan/allowance describe the effective allowance (including an immediate
upgrade), while ledger events retain immutable change history. No proration.
Maximum allowance replaces previous allowance; repeated/new-key requests for the
same tier never replenish consumed or reserved credit.

### Expiry and bonus

- Expiry is inclusive at now >= expires_at. Move only positive AVAILABLE credit
  to expired and append an expire event. Already reserved amounts stay reserved
  on the original grant; consumed remains consumed. Never transfer to a new cycle.
- Expire due base and bonus grants on successful new lifecycle access. Unlimited
  bonus expiry is allowed only when expires_at=None. New finite bonus expiry must
  be strictly after now; an identical committed replay remains valid after expiry.
- Bonus is independent of cycle allowance/Plan; no cycle_id and positive strict
  integer amount. Safe reason code [a-z0-9_]{1,64}; no free-form operator text.
- Require outstanding available+reserved across all grants, plus any new base/
  bonus/upgrade increment, <= signed BIGINT. Use widened SQL/Python integer arithmetic;
  no floating point or overflow during SUM. Expired/consumed history is not
  included in outstanding. This is an accounting bound, not a product quota.
- Future C release from an expired grant moves released amount directly to expired,
  not available; B leaves held amounts untouched. B tests construct such held
  projections with matching fixture ledger only; no reservation writer in B.

### Idempotency, including operations with no ledger delta

Ledger uniqueness cannot encode a downgrade/cancel/no-op because they must not
fabricate zero-value ledger events. Add the small operation table in section4.
Under User/account lock, check an existing (user_id, operation_key) BEFORE renewal
or expiry. Compare kind and normalized immutable business fields. Ignore retry
now (a clock observation, not payload); return original receipt without writes.
Same key with another kind/target/amount/expiry/reason refuses with no side effects,
including no lazy renewal. Keys are scoped per User, not globally.
Validate request syntax first; replay precedes new-command temporal/suspension
checks. Both operations share the same key namespace.

New calls persist one operation record even for no-op/scheduling/cancellation.
Base/expiry auto-events use deterministic internal keys; command ledger key
`cmd_<operation_key>` (key<=96, ledger<=128). Internal cycle/expiry keys have
disjoint prefixes; never accept arbitrary ledger keys. All events use supported
RATE_CARD_VERSION; historical version/operation/ledger data never changes.
Rollback before commit leaves no replay record; retry may execute once normally.

## 4. One additive migration: operation persistence

Exactly `0005_credit_lifecycle_operations`, parent0004. Existing migrations unchanged.
Append CreditOperation to existing credit_models (already registered by Alembic).
Do not alter the existing four credit tables or their named constraints.

Table `credit_operations`:

- composite PK (user_id, operation_key); user_id FK account RESTRICT.
- operation_key VARCHAR96 with ASCII [A-Za-z0-9_-]{1,96} CHECK.
- kind VARCHAR11: plan_change | bonus; target_plan nullable VARCHAR4.
- amount_microcredits nullable BIGINT; expires_at nullable TIMESTAMPTZ;
  reason_code nullable VARCHAR64. Plan requests have valid target and all three
  bonus fields null. Bonus has target null, positive amount, safe non-null reason.
- rate_card_version VARCHAR10, same bounded version syntax as ledger.
- effective_at TIMESTAMPTZ non-null; finite bonus expiry > effective_at.
- result_cycle_id non-null; composite FK (result_cycle_id,user_id) to cycles.
- result_grant_id optional; composite FK (result_grant_id,user_id) to grants.
- outcome VARCHAR16: upgraded/scheduled/cancelled/unchanged/granted. Bonus requires
  granted + grant_id; plan requires one of the other four outcomes, and grant_id
  only for upgraded. All unspecified columns non-null except as above.
- named user/effective_at index. No JSON, email, prompt, credential or free text.
- UPDATE/DELETE/TRUNCATE triggers refuse credit_operation_append_only.

Upgrade preserves populated0004 data and adds an EMPTY table; no command backfill.
Downgrade takes a5s bounded exclusive lock and refuses if any operation exists,
using credit_operations_requires_empty_table, before DDL. Empty downgrade to0004
must preserve populated legacy four-table credit data. Refusal rolls back revision
and DDL. Existing0004 refusal still protects populated credit projections/ledger.

Schema verifier gains new-head inventory/reset plus empty/populated0005 migration
proof. Old0003 proof stays pinned; old0004 additive/constraint/ledger proof remains
semantically intact at current head (four-table assertions/count>=90/races3 retained).
Foundation helper may update its head and additive metadata expectation to include
the fifth table, but never replace/remove its old probes. Also test genuine
0004->0005 populated upgrade and back, not merely version-table stamping.
Three-process stale checks retain previous probes and add stale0004 refusal.

## 5. Exact non-document allowlist (20)

```text
backend/app/credit_lifecycle.py
backend/app/credit_models.py
backend/migrations/versions/0005_credit_lifecycle_operations.py
backend/tests/test_credit_lifecycle.py
backend/tests/credit_lifecycle_support.py
backend/tests/test_credit_lifecycle_support.py
backend/tests/test_credit_models.py
backend/tests/test_alembic_schema.py
scripts/verify_credit_lifecycle.py
backend/tests/test_verify_credit_lifecycle_script.py
scripts/verify_schema_migrations.py
backend/tests/test_verify_schema_migrations_script.py
backend/tests/credit_foundation_support.py
backend/tests/test_credit_foundation_support.py
scripts/verify_auth_sessions.py
backend/tests/test_verify_auth_sessions_script.py
scripts/mock_auth_support.py
backend/tests/test_mock_auth_support.py
backend/tests/ownership_support.py
backend/tests/test_ownership_persistence.py
```

Count cumulative committed/staged/unstaged/new paths against a003257. Old paths
needed only for head compatibility/assertion preservation; do not rewrite harnesses.
Existing credit_policy, User/Session, migrations0001–0004, verify_ownership,
frontend/dependencies/CI/Compose/infra remain byte-identical. A21st code path,
second migration or a second product Module means STOP/replan before implementation.

## 6. Acceptance and actual proof

| ID | Required assertion |
|---|---|
| B01 | One new table/revision, no old schema/data modification or auto-signup hook |
| B02 | Populated0004 upgrade and empty new-table downgrade/re-up preserve all old rows; populated operation/lock refusal |
| B03 | Operation field checks, ownership FKs, unique User/key and append-only three mutations in real PostgreSQL |
| B04 | Active caller transaction required; no caller commit; savepoint rejection and outer rollback leave no partial B rows |
| B05 | Free normal/Max Master initialization, one account/cycle/base/ledger |
| B06 | Late first access materializes current cycle only, no skipped credit accrual |
| B07 | Signup/just-before/exact/after30days, UTC offsets/microseconds/leap-year/skipped cycles |
| B08 | Pending downgrade applies before current-cycle issuance; anchor remains immutable |
| B09 | Every Plan pair, replacement/cancel/no-op, upgrade consumed/reserved/expired preservation |
| B10 | Upgrade adds allowance difference only; repeated same-tier never replenishes |
| B11 | Master nonMax refusal, corrupted anchor/Plan/base refusal, clock regression |
| B12 | Positive strict bonus/finite-or-none expiry, overflow/type/key/reason refusal |
| B13 | Base/bonus expiry moves available only; reserved old-cycle amounts stay attached |
| B14 | Repeated expiry no duplicate ledger; all projection columns reconstruct from ledger |
| B15 | Exact command replay before/after boundary/expiry has original receipt and zero side effects |
| B16 | Same key differing kind/target/amount/expiry/reason refuses atomically; cross-User keys independent |
| B17 | Suspended ensure is accounting-only; new mutation refused, committed read-only replay allowed |
| B18 | Caught validation/database contention rejection and deliberate outer rollback preserve caller semantics |
| B19 | Fresh locked ORM data defeats stale identity-map calculations |
| B20 | Eight independent lock-observed races specified below, no duplicates/lost updates |
| B21 | Guarded local proof cannot target dev/preview, private dotenv/remote Docker/unsafe evidence refused |
| B22 | Two fresh lifecycle cycles at one committed code SHA; all8 groups and all race cases complete, cleanup0 |
| B23 | Schema2 retains credit90/races3/old ownership8/stale/reset; auth1 and ownership all2 preserve every old group |
| B24 | Full Linux/backend and existing frontend, final-head3 CI and protected squash actual merge |

Lifecycle proof groups: init, renewal, plan, bonus, expiry, idempotency, transaction,
concurrency. Every group reports true only when all its named assertions finish.
Emit groups8, races8, checks>=80, complete=true only on whole-proof success.
The count is supplementary: B01–B24/group membership must not be traded for padding.

Eight actual races (independent connections, observed lock overlap, bounded waits):
1. Same User first ensure -> exactly one account/cycle/base/event.
2. Same User renewal -> exactly one new current cycle/base/event.
3. Same bonus key/payload -> one bonus/op/event, two equal receipts.
4. Same bonus key/different payload -> one winner, one collision, no mixed state.
5. Same Plan schedule key -> one op and pending target, no fabricated ledger.
6. Distinct bonus keys -> both additions preserved with correct total.
7. Immediate upgrade vs renewal at exact boundary -> one serializable outcome,
   new-cycle allowance correct, no duplicated grant or replenishment.
8. Expired bonus ensure vs new bonus -> expiry once and new bonus exactly once.

Fixture time is explicit; no sleeps to age a cycle. Lock waits use pg_blocking_pids/
wait_event_type observation (<=5s observer; <=10s race participants), not sleep as
proof. No injected production race hook or dependency override. Fixture reserved
amounts must have matching ledger and no claim of C settlement verification.

New fixed local verifier `scripts/verify_credit_lifecycle.py --env-file .env.example`
owns one fresh `credit-verify-[a-z0-9]{12}` Docker project per invocation, starts
only DB and one-shot migrate against current0005, executes the fixed proof source
through runtime Python stdin (tests/pytest are not assumed installed in image).
Capture only allowlisted revision/SHA/group/count/duration/fixed-code receipts.
No target/project/DSN/SQL/keep-volume flags, arbitrary proof source or private env.
Refuse remote daemon/DOCKER_HOST, non-.env.example, dirty code, existing resources
or unexpected DB name/host/head before fixture writes. Clear provider/OAuth env.
Use random names, label-checked cleanup including stopped/one-shot containers;
preserve first error separately from cleanup failure. No raw subprocess output.

Runtime limits: lifecycle work300s/cleanup90s/total390s each (two<=780s);
schema retains300/90/390 (two<=780s); auth total300s; ownership work360/cleanup90
each, suite900/all1800s unchanged; Linux600s/Windows120s/frontend600s.
Timeout is No-Go: cleanup exact project and STOP/replan, no rerun/budget inflation.

## 7. Delivery and G5C handoff

After local success document observed commands/counts/time, failed attempts,
rollback and limitations. Ready PR closes116 only. Final-head verify and both
Scan/SBOM SUCCESS, protected squash actually MERGED; parent114 and117 stay OPEN.
No implementation or PR in this preparation.

G5C input is the implemented three-operation Interface, lock/savepoint discipline,
immutable operation replay and held-expired-grant behavior. It must add its own
reservation/allocation/Usage schema and prove atomic debit/settlement; B provides
no product admission or insufficient-credit rejection yet. G5C also must decide
how reservation/settlement keys coexist with the lifecycle operation namespace.

Rollback: preserve data; populated operation downgrade refuses. Prefer reviewed
code forward fix. Reverting B callers is possible because none are wired into
the product, but never force-drop operation/ledger rows or downgrade a user DB.
