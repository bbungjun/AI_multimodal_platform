# G9A — Personal Plan and usage read-model specification

Status: **In Progress**, 2026-09-05. Issue
[#131](https://github.com/bbungjun/AI_multimodal_platform/issues/131) is the
backend read slice of G9. G9B will consume this Interface in the existing
frontend; it is not part of this Goal.

## 1. Problem and outcome

G5–G8 persist the Plan, exact 30-day Credit cycle, original Usage, internal
microcredit accounting and active held Reservations. The authenticated User
cannot inspect any of it. Building the frontend directly over several tables
would duplicate renewal, aggregation, unit and privacy policy in every caller.

G9A adds one deep `personal_usage` Module and one authenticated Interface:

```text
GET /api/usage/me
```

The Interface returns one coherent current snapshot. It has no User selector,
pagination, date filter or Master scope. G9B therefore learns one stable shape
instead of account/cycle/grant/reservation/usage persistence details.

## 2. Scope and exclusions

Included:

- current Plan and pending downgrade;
- current exact 30-day cycle start, renewal instant, index and allowance;
- all usable Credit, all currently held Credit and current-cycle charged Credit;
- active top-level requests and the current Plan limit;
- original observed units and charged microcredits for each V1 billing meter;
- authenticated owner-only HTTP read with private/no-store responses;
- lazy current-cycle materialization through the existing lifecycle seam;
- unit, HTTP and isolated PostgreSQL snapshot/race/rollback verification.

Excluded:

- G9B frontend, charts, formatting and navigation;
- migrations, persistence/index changes or a Usage cache/table;
- Plan mutation, bonus grant, payment, Master console/Audit and synthetic seed;
- historical pagination, custom time ranges, invoices or cost forecasts;
- User ID parameters, cross-owner reads and `scope=all`;
- prompt, Job/Asset history, email, session/OAuth data and provider raw payload;
- real OAuth, Vertex/provider/cloud, GCP, Kubernetes or Terraform execution.

All runtime verification uses local Docker and `AI_PROVIDER=mock`. Development
and preview databases and volumes are preserved.

## 3. Deep Module and Interface

The external Module Interface is one transaction-composable operation:

```python
read_personal_usage(session, *, user_id: UUID, now: datetime) -> PersonalUsageView
```

The caller supplies an authenticated User ID, an aware timestamp and an active
`AsyncSession` transaction. The Module never creates an engine, reads a clock,
commits, rolls back or performs provider work. It may use the existing G5B
`ensure_cycle` Interface, which locks User first and lazily creates or advances
the account/cycle/grants. The HTTP adapter owns the outer transaction and commits
that deterministic lifecycle materialization before returning.

The deletion test favors this seam: without it, the route and future G9B callers
must each understand renewal, bonus availability, held projections, current-cycle
time attribution, meter units, integer overflow and consistency checks. The
Module keeps that complexity local behind one read operation.

## 4. Snapshot and aggregation contract

The snapshot keeps the existing lock order:

```text
User -> CreditAccount -> current CreditCycle -> CreditGrants ordered by id
     -> held CreditReservations -> current-cycle CreditUsageRecords
```

`ensure_cycle` runs first inside the same transaction. Because all reserve,
settle, release and lifecycle mutations acquire the same User lock first, the
remaining owner-scoped reads form one coherent snapshot. No `READ UNCOMMITTED`,
Redis cache or process-local lock is introduced.

Calculations use integers only:

- `available_microcredits`: sum of every User grant's
  `granted - reserved - consumed - expired` after lifecycle advancement;
- `held_microcredits`: sum of grant reserved projections, which must equal the
  sum of held Reservation amounts;
- `active_requests`: number of held Reservations;
- `cycle_charged_microcredits`: sum of Usage charges whose `recorded_at` is in
  `[cycle.starts_at, now]`; at the exact renewal boundary `ensure_cycle` first
  advances the cycle, so boundary records belong to the new cycle;
- meter totals use those same current-cycle Usage rows. `observed_units` includes
  retained no-deliverable attempt Usage, while `charged_microcredits` remains
  zero for that released work.

Negative values, signed-BIGINT overflow, an unknown Plan/meter, projection drift
or lifecycle inconsistency fail closed. A read never repairs accounting rows.

## 5. Response contract

The response contains:

```text
plan: free | pro | max
pending_plan: free | pro | null
rate_card_version: v1
cycle:
  index, starts_at, renews_at, allowance_microcredits,
  charged_microcredits
credit:
  available_microcredits, held_microcredits
concurrency:
  active_requests, limit
usage:
  [{meter, unit, observed_units, charged_microcredits}, ...]
```

`usage` always has these seven entries in this order so G9B needs no missing-row
logic:

1. `gemini_input_token` / `token`
2. `gemini_output_token` / `token`
3. `imagen_fast_image` / `image`
4. `imagen_standard_image` / `image`
5. `imagen_ultra_image` / `image`
6. `veo_fast_ms` / `millisecond`
7. `veo_standard_ms` / `millisecond`

Current persistence does not retain an exact provider model identifier on every
Usage record. G9A does not infer one from prompts, operation keys or unrelated
Job metadata; the billing meter is the truthful aggregation dimension. G9B may
apply human-readable labels without changing accounting meaning.

The payload contains no User ID, email, plan mutation controls, grant/reservation
IDs, operation keys, prompt, Job/Asset fields, session/OAuth material or provider
response. All success and error responses under `/api/usage` are private and
`no-store`.

## 6. HTTP and error contract

`GET /api/usage/me` takes identity exclusively from `require_user`. Query and body
User selectors are unsupported. Missing/invalid sessions remain the existing
401 contract. The adapter maps fixed internal failures to safe responses:

| HTTP | Public code | Meaning |
|---:|---|---|
| 503 | `usage_busy` | PostgreSQL lock/serialization/timeout contention; caller may retry |
| 503 | `usage_unavailable` | missing/inconsistent accounting state or bounded internal failure |

No response distinguishes another User, leaks a count for another owner or
returns SQL/internal exception text. A failed request rolls back lazy lifecycle
materialization.

## 7. Verification contract

The G9A verifier owns one random disposable Compose project and PostgreSQL volume,
forces mock mode, upgrades to `0006_credit_accounting_persistence` and cleans only
its labelled resources. Run two independent cycles at the same committed code
SHA. Each cycle proves eight groups:

1. new User lazy Free account/cycle and all-zero fixed meter shape;
2. Free/Pro/Max/Master policy, pending downgrade and 1/3/5/5 limits;
3. base plus bonus availability and held projection reconciliation;
4. all seven meter units, observed no-deliverable Usage and charged totals;
5. exact 30-day boundary, pending-plan application and current-window reset;
6. active held count and slot return after settle/release;
7. at least three observed User-lock races across read/reserve, read/terminal and
   read/lifecycle operations without mixed snapshots;
8. rollback, inconsistency fail-closed, owner isolation and privacy allowlist.

Each cycle must report all eight groups, at least three races, at least160 checks,
schema/code revisions and container/volume/network cleanup zero. Inherited gates:

- lifecycle, accounting, concurrency, prompt-credit, generation-credit and auth
  isolated verifiers once each;
- ownership `--suite all --cycles 2` as four completed aggregate cycles;
- tracked-only Linux and documented native Windows backend pytest;
- Compose `.env.example`, frontend lint/build, Session48 and Chromium34;
- final-head required `verify` and backend/frontend Scan/SBOM.

## 8. Exact implementation boundary and stop conditions

No migration is permitted. Implementation may change only these 11
non-document paths:

1. `backend/app/personal_usage.py`
2. `backend/app/api/usage.py`
3. `backend/app/schemas.py`
4. `backend/app/main.py`
5. `backend/tests/test_personal_usage.py`
6. `backend/tests/test_usage_api.py`
7. `backend/tests/personal_usage_support.py`
8. `backend/tests/test_personal_usage_support.py`
9. `backend/tests/test_verify_personal_usage_script.py`
10. `scripts/verify_personal_usage.py`
11. `backend/tests/test_ownership_integration.py`

An additional non-document path, schema change, second public Module, historical
query/pagination feature, frontend change or time-limit relaxation is
STOP-and-redesign. Unused allowlisted paths need not be edited.

Completion requires Todo1–8, F1–F4 APPROVE, two same-SHA isolated cycles, all
inherited/full regressions, portfolio/handoff documentation, a Ready PR, final
required CI, protected squash auto-merge, actual `MERGED`, Issue closure and local
`main` synchronization. Evidence is **Mock Verified**, not live provider/cloud.
