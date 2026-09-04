# Authentication, Credits, and Master Console Initiative

## Document Contract

- Status: `Accepted / Planned`
- Last updated: `2026-09-05`
- This document is the single source of truth for the initiative-wide product
  decisions, invariants, Goal order, and current progress.
- Implementation details that apply to only one Goal belong in that Goal's
  Issue, plan, tests, and portfolio record. Do not duplicate this document into
  a new initiative specification.
- At the end of every Goal, update only the Goal Status table, verified result,
  decision changes if any, and the Next Goal section. Also update
  `docs/current-work.md` with the short handoff.
- `Planned`, `Implemented`, `Mock Verified`, and `Live Verified` must not be
  conflated. All capabilities in this document remain `Planned` until a Goal
  records fresh evidence.

Canonical domain terms are defined in [CONTEXT.md](../../CONTEXT.md).

## Problem and Outcome

CreativeOps Studio currently demonstrates multimodal generation but does not
separate users, enforce per-user product limits, or provide a product operator
with usage and failure visibility. The initiative adds Google login, ownership
isolation, plan-aware credits, personal usage visibility, and a Master console
without turning the product into a generic customer-support chatbot.

The portfolio outcome is an end-to-end AI product slice that demonstrates AI
Full Stack delivery, forward-deployed integration judgment, AX-style operating
policy, and AI platform reliability. The default implementation and automated
verification remain mock-first and must not call paid providers.

## Fixed Scope

### Included

- Google OAuth login and server-managed sessions.
- RBAC roles `user | master`.
- Product plans `free | pro | max`, separate from RBAC.
- Per-user ownership for newly created product data.
- Versioned internal credit rates for Gemini, Imagen, and Veo usage.
- Atomic reserve, settle, and release behavior with idempotency.
- Personal usage UI and Master operations console.
- Append-only audit history for Master mutations.
- Deterministic synthetic data for realistic local operations views.
- Alembic schema versioning on a clean database.

### Excluded

- Real payment collection, checkout, invoices, tax, or provider-cost parity.
- Product mock-login routes or password authentication.
- Permanent account deletion and anonymization.
- Preservation or ownership backfill of the current disposable database data.
- Customer-support chatbot or Operations Copilot functionality.
- Paid Vertex calls during implementation or automated verification.

## Identity and Session Decisions

- Google OAuth is the only product login method.
- Use Authorization Code Flow with PKCE and validate `state` and `nonce`.
- The backend owns the callback and token exchange. The browser receives only
  an `HttpOnly`, `Secure`, `SameSite=Lax` session cookie.
- Google `sub` is the stable external identity. A verified email, display name,
  and profile image URL are profile data, not the identity key.
- OAuth authorization codes and access or refresh tokens are never persisted.
- Sessions expire after 12 hours of inactivity and seven absolute days.
- Store only a SHA-256 session identifier hash and allow at most five active
  sessions per User.
- A sixth successful login revokes the oldest Active Session by
  `(created_at, id)` and then creates the new Session in the same User-locked
  transaction. It does not reject the login.
- Authentication refreshes `last_seen_at` at most once per five minutes using
  a conditional update. Every request still evaluates the 12-hour inactivity
  and seven-day absolute limits against database state.
- A suspended User cannot log in or create, enhance, or retry work. Suspension
  revokes every session and cancels not-yet-dispatched work while already
  running provider work completes and settles normally.
- Every OAuth signup starts as `user`. An operations CLI promotes an exact User
  UUID to `master` with dry-run and reason fields.
- The final remaining Master and the acting Master cannot be suspended.

## Plans and Entitlements

Every cycle starts at the exact signup timestamp and lasts exactly 30 days. It
is not a calendar-month or same-day-of-month policy. Unused base credits expire
at the next cycle. Bonus credits are separate ledger grants with a reason and
optional expiry.

| Entitlement | Free | Pro | Max |
|---|---:|---:|---:|
| Credits per 30-day cycle | 1,000 | 10,000 | 50,000 |
| Gemini prompt enhancement | Yes | Yes | Yes |
| Imagen Fast | Yes | Yes | Yes |
| Imagen Standard | No | Yes | Yes |
| Imagen Ultra | No | No | Yes |
| Veo Fast | Yes | Yes | Yes |
| Veo Standard | No | No | Yes |
| Images per request | 1 | Up to 4 | Up to 4 |
| Video duration | Up to 4 seconds | Up to 8 seconds | Up to 8 seconds |
| Concurrent top-level requests | 1 | 3 | 5 |

- A Master uses the Max plan but does not bypass credits or usage recording.
- An upgrade applies immediately by replacing the current cycle allowance; the
  already consumed amount remains consumed.
- A downgrade is scheduled for the next cycle. There is no proration.
- A pipeline occupies one top-level concurrency slot even when it creates
  multiple child Jobs.

## Rate Card V1

Credits are an internal product policy, not a representation of Google pricing.
Calculations use integer microcredits; the UI may display two decimal places.
Every ledger event stores the applied rate-card version.

| Usage | V1 credit rate |
|---|---:|
| Gemini input | 1 per 1,000 tokens |
| Gemini output | 4 per 1,000 tokens |
| Imagen Fast | 50 per delivered image |
| Imagen Standard | 100 per delivered image |
| Imagen Ultra | 200 per delivered image |
| Veo Fast | 60 per delivered second |
| Veo Standard | 120 per delivered second |

Original usage remains separately recorded:

- Gemini: input and output tokens.
- Imagen: delivered image count and model.
- Veo: delivered video seconds and model.
- Usage source: `provider_reported`, `platform_measured`, `mock_estimate`, or
  `estimated`.

## Admission and Settlement Invariants

- Plan permission, concurrency, and balance checks happen before provider calls
  and before enqueue.
- Admission locks the User billing account and atomically creates the credit
  Reservation, Job, and OutboxEvent.
- Provider calls run outside database transactions.
- Settlement atomically records actual Usage, consumes or releases Credit, and
  changes terminal Job state.
- No deliverable result releases all User Credit even when provider-attempt
  Usage is retained for operations analysis.
- Partial image success charges only delivered images.
- Unique idempotency keys prevent duplicate charges across queue redelivery and
  worker retries.
- A pipeline reserves once at its top level; child Jobs never reserve the same
  work again.
- Files are written through the storage helper. A repair procedure detects and
  removes orphaned files created before a failed database commit.

Public admission and provider conditions stay distinct:

| HTTP | Code | Meaning |
|---:|---|---|
| 402 | `monthly_credit_exhausted` | Available Credit cannot cover the Reservation. |
| 403 | `plan_feature_not_allowed` | The Plan does not allow the requested model or shape. |
| 429 | `user_concurrency_limit` | Active top-level requests reached the Plan limit. |
| 503 | `vertex_rate_limited` | The external provider rate-limited the platform. |

## Ownership Invariants

- Every new Job and Prompt Enhancement has a non-null owning User.
- Asset ownership derives from its Job; OutboxEvent remains internal
  infrastructure data and does not duplicate ownership.
- Parent and child Jobs in a pipeline have the same owner.
- An I2V source Asset must belong to the requesting User.
- A normal User can list, read, retry, and delete only owned data.
- Requests for another User's object return `404` to avoid existence leakage.
- A Master can inspect all User data for operations purposes.
- Master cross-owner access is read-only. Retry/delete and generation references
  (source Asset/Prompt Enhancement) remain owner-only, including for Master.
- Work lists default to the acting User's data, including Master. Explicit
  `scope=all` is Master-only; another User's object remains indistinguishable
  from a missing object for unauthorized operations.
- G4.3 restricts global ops JSON and `/metrics` to Master. Machine scraping
  requires a separately approved private/service-auth contract before deployment;
  G4 does not silently change cloud scrapers or bypass this restriction.
- Existing database data is disposable and will be deleted. It is not assigned
  to a Master and no ownership-backfill path will be implemented.

## Master Console and Audit

The personal usage view shows the current Plan, available Credit, cycle renewal
timestamp, and model-level Usage. The Master console shows:

- real OAuth and Synthetic User counts, Plan distribution, and account status;
- reserved, consumed, and released Credit by Plan, model, and time;
- generation success rate, failure rate, p95 duration, and public error mix;
- recent failed Jobs and safe provider failure metadata;
- User signup, next renewal, Plan, consumed Credit, and available Credit;
- Plan changes, bonus grants, and suspension or reactivation controls.

Master mutations produce append-only audit records containing actor User ID,
target User ID, action, safe before and after values, reason, request ID, and
timestamp. OAuth tokens, session identifiers, prompt text, and provider raw
responses are forbidden in audit records.

## Synthetic Data

- Create 120 login-disabled Synthetic Users: 84 Free, 30 Pro, and 6 Max.
- Generate about 3,000 deterministic Jobs across the most recent 90 days.
- Include active, dormant, and suspended users plus success, provider failure,
  quota exhaustion, Plan denial, and concurrency denial cases.
- Cover Gemini, Imagen, and Veo usage across supported models.
- The seed CLI is idempotent, supports dry-run, reports expected counts, marks
  `data_origin=synthetic`, and refuses production execution.
- Automated OAuth tests use a fake adapter at the Google verification seam;
  the product does not expose a fake login route.
- Browser smoke uses one real Master and one real normal User only after local
  mock verification passes.

## Database Strategy

- Current database contents may be deleted; no data-preserving migration or
  ownership backfill is required.
- Introduce Alembic as the schema source of truth and create the final required
  constraints on a clean database.
- `owner_user_id` is non-null from its introduction.
- Database reset tooling must display and validate the exact environment and
  database target, support a safe preview, and refuse production execution.
- Verify clean upgrade, downgrade, and re-upgrade. Restrict or remove runtime
  `create_all()` so it cannot silently diverge from Alembic.

## Goal Decomposition and Context Budget

Each Goal uses `gpt-5.6-sol` at medium reasoning in a fresh context. It reads
`AGENTS.md`, `docs/current-work.md`, this document's relevant section, and only
the directly related implementation references. It must not load every project
document or inherit the full design interview.

| Goal | Deep module or delivery slice | Status | Current evidence | Next input |
|---|---|---|---|---|
| G1 | Alembic schema control, fail-closed readiness, and safe local reset | Mock Verified | [Issue #94](https://github.com/bbungjun/AI_multimodal_platform/issues/94), [spec](g1-schema-control-spec.md), [portfolio record](../portfolio/issue-94-schema-control.md), verified checkpoint `6aa8a1f` | Complete; cloud rollout remains Deferred / No-Go |
| G2 | User and Session persistence | Mock Verified | [Issue #96](https://github.com/bbungjun/AI_multimodal_platform/issues/96), [spec](g2-user-session-persistence-spec.md), [portfolio record](../portfolio/issue-96-user-session-persistence.md), PR #97 merged at `58f405b` | Complete; cloud rollout Deferred / No-Go |
| G3 | Backend Google OAuth and Session lifecycle | Mock Verified | [Issue #98](https://github.com/bbungjun/AI_multimodal_platform/issues/98), [PR #100](https://github.com/bbungjun/AI_multimodal_platform/pull/100), [spec](g3-auth-session-lifecycle-spec.md), [portfolio record](../portfolio/issue-98-auth-session-lifecycle.md), code/tests `ec42d61`: two real Postgres/Redis cycles, mock generation passed, 17 paths / zero migrations | G3.1 interface available; live readiness blocked by #99 and browser/proxy gates |
| G3.1 | Authenticated workspace entry and browser Session UX | Mock Verified — Merged | [Spec](g3-1-authenticated-workspace-ux-spec.md), [Issue #101](https://github.com/bbungjun/AI_multimodal_platform/issues/101), [PR #102](https://github.com/bbungjun/AI_multimodal_platform/pull/102) merged at `100f5e7`, [portfolio](../portfolio/issue-101-authenticated-workspace-ux.md); final head `85cb215` verify + both scans PASS; module48, browser34, backend467 PASS / 3 conditional SKIP; isolated golden/cleanup PASS | G3 interfaces consumed; G4 receives browser Session interface and must enforce backend ownership. 17 paths / zero migrations; no live login |
| Auth emergency | Guarded emergency Session revocation | Mock Verified locally — delivery pending | [Issue99](https://github.com/bbungjun/AI_multimodal_platform/issues/99), [accepted spec](emergency-session-revocation-spec.md), [record](../portfolio/issue-99-emergency-session-revocation.md); code `1822679` | Exact13/migration0 after adding the omitted Compose env adapter; isolated2 each8 groups/race1/checks85, auth/golden/full regressions PASS. Mock proof only; live drill remains separate |
| G4.1 | Authenticated mock verification harness | Mock Verified | [Spec](g4-ownership-access-control-spec.md), [Issue #103](https://github.com/bbungjun/AI_multimodal_platform/issues/103), [record](../portfolio/issue-103-authenticated-mock-harness.md); implementation `471b76e`, branch `codex/issue-103-authenticated-mock-harness` | Two fresh Docker cycles: auth12/scenarios3/cleanup each; focused106, Linux542 PASS / 3 existing SKIP; frontend48+34 PASS. Exactly13 paths, zero migrations. Delivery status tracked by Issue/PR |
| G4.2 | Owner persistence and admission/reference invariants | Mock Verified — A/B | [Accepted G4 policy](g4-ownership-access-control-spec.md), [split spec and implementation handoff](g4-2-owner-persistence-admission-spec.md) | G4.3 read/file/delete/ops/cache enforcement remains; no public multi-user deployment |
| G4.2A | Owner persistence and authenticated admission | Ownership Admission Mock Verified; delivery tracked below | [Issue #105](https://github.com/bbungjun/AI_multimodal_platform/issues/105), branch `codex/issue-105-owner-persistence-admission`, [execution record](../portfolio/issue-105-owner-persistence-admission.md); implementation `e3c98f1` | Exact20 paths/migration1/head0003; schema2/auth1/final admission2 PASS, cleanup0. Linux658 PASS/3 existing SKIP; frontend48+34 PASS. Developer/preview preserved; final CI/merge use delivery link |
| G4.2B | Worker references and pipeline/race proof | Mock Verified — delivery tracked in execution record | [Issue #107](https://github.com/bbungjun/AI_multimodal_platform/issues/107), branch `codex/issue-107-worker-ownership-invariants`, [B spec](g4-2-owner-persistence-admission-spec.md), [execution record](../portfolio/issue-107-worker-ownership-invariants.md); implementation ff808b0 | Exact11/migration0/head0003; two real cycles each auth12/admission111/smoke3/execution20/pipeline4/race3/expiry1/cleanup0. Linux782/3 existing SKIP, frontend48+34. G4.3 receives worker validator, safe pipeline results and expanded guarded harness; failed-link recovery/live verification remain excluded |
| G4.3 | Complete ownership access enforcement | Mock Verified — Merged | [Accepted policy/split](g4-ownership-access-control-spec.md), [parent109 closure](https://github.com/bbungjun/AI_multimodal_platform/issues/109#issuecomment-5525431496) | A PR111 and B PR113 actually merged; aggregate G4 closed. No live/public multi-user deployment claim |
| G4.3A | Metadata ownership access and safe deletion | Mock Verified — Merged | [Issue110](https://github.com/bbungjun/AI_multimodal_platform/issues/110), [PR111](https://github.com/bbungjun/AI_multimodal_platform/pull/111) squash cd654e5, [record](../portfolio/issue-110-metadata-ownership-access.md) | Exact16/migration0/head0003; implementation acb44a9; two real cycles337.73/338.12s, each access8/checks348/delete-race2 plus prior groups, cleanup0. Linux928/3 existing skips, frontend48+34. Final head5738c0d all3 required CI SUCCESS; B receives read/batch/cache/client Interfaces |
| G4.3B | File/Range, Master ops and final proof | Mock Verified — Merged | [PR113](https://github.com/bbungjun/AI_multimodal_platform/pull/113) squash6537025, [final evidence](https://github.com/bbungjun/AI_multimodal_platform/issues/112#issuecomment-5525436934), [record](../portfolio/issue-112-file-ops-access.md) | Original No-Go preserved; v2 c05b815 aggregate4/998.187s, each legacy348/races2 or FOVE310/A-B10, cleanup0. Schema2/auth1/Linux1128/frontend48+34 PASS. Final head8aa6ba8 all3 required CI SUCCESS; Issues112/109 closed |
| G5 | Credit account, Plan lifecycle, Rate Card, Reservation and Settlement | Mock Verified — Merged | [Parent114](https://github.com/bbungjun/AI_multimodal_platform/issues/114), [split spec](g5-credit-foundation-spec.md), G5C2 [PR123](https://github.com/bbungjun/AI_multimodal_platform/pull/123) squash `5e56ecb` | A/B/C1/C2 all merged and Issues121/117/114 closed; product callers remain G6/G7 |
| G5A | Credit persistence and pure Plan/rate/time policy | Mock Verified — Merged | [PR118](https://github.com/bbungjun/AI_multimodal_platform/pull/118), [final evidence](https://github.com/bbungjun/AI_multimodal_platform/issues/115#issuecomment-5528702729), [record](../portfolio/issue-115-credit-foundation.md) | Squash a003257; final b940be2 required3 CI SUCCESS. Exact17/migration1; schema2/credit90/races3, auth1, ownership all4/993.610s, Linux1229/frontend48+34/cleanup0. No automatic credit or product wiring |
| G5B | Account initialization, 30-day cycles, Plan transitions and grants | Mock Verified — Merged | [Issue116](https://github.com/bbungjun/AI_multimodal_platform/issues/116), [PR119](https://github.com/bbungjun/AI_multimodal_platform/pull/119), [spec](g5-credit-lifecycle-spec.md), [record](../portfolio/issue-116-credit-lifecycle.md) | Squash ffc4b50; final head7ab6254 required3 CI SUCCESS and exact tree match. Exact20/new0005; schema2, lifecycle2, auth1, ownership-file4, Linux1321/frontend48+34. No billing wiring |
| G5C | Reservation allocations, Usage and atomic settlement/release | Mock Verified — Merged | [Parent117](https://github.com/bbungjun/AI_multimodal_platform/issues/117), [frozen aggregate spec](g5-credit-accounting-spec.md), [PR123](https://github.com/bbungjun/AI_multimodal_platform/pull/123) | C1 persistence and C2 accounting Module merged; G6/G7 wiring stays separate |
| G5C1 | Reservation/allocation/Usage persistence and head compatibility | Mock Verified — Merged | [Issue120](https://github.com/bbungjun/AI_multimodal_platform/issues/120), [PR122](https://github.com/bbungjun/AI_multimodal_platform/pull/122), [record](../portfolio/issue-120-credit-accounting-persistence.md) | Squash68e3df6; exact20/new0006, schema2 accounting42/downgrade4, lifecycle8/races8, auth1, ownership-file4, Linux1347/frontend48+34, cleanup0; final required3 CI and tree match confirmed. No writer/product wiring |
| G5C2 | Atomic reserve, settle, release and PostgreSQL proof | Mock Verified — Merged | [Issue121](https://github.com/bbungjun/AI_multimodal_platform/issues/121), [PR123](https://github.com/bbungjun/AI_multimodal_platform/pull/123), [aggregate spec](g5-credit-accounting-spec.md), [execution record](../portfolio/issue-121-credit-accounting-module.md) | Code41b1bf3 exact6/migration0; accounting2 each8 groups/races8/299 checks, schema/lifecycle/auth/ownership-all2, Linux1429, frontend48+34 PASS and cleanup0. Required3 CI succeeded; squash `5e56ecb`, Issues121/117/114 closed. No generation billing caller |
| G6 | Gemini prompt-enhancement credit integration | Mock Verified — Merged | [Issue124](https://github.com/bbungjun/AI_multimodal_platform/issues/124), [PR125](https://github.com/bbungjun/AI_multimodal_platform/pull/125), [accepted spec](g6-gemini-credit-integration-spec.md) | Final code `87dca6b`; exact14/migration0, prompt-credit2, ownership all4 cycles, Linux1461 and frontend regressions passed. Final head `c0d65cb` required verify plus both Scan/SBOM succeeded; squash `a6d9656`; Issue124 closed |
| G7 | Imagen/Veo and pipeline credit integration | Mock Verified — Merged | [Issue127](https://github.com/bbungjun/AI_multimodal_platform/issues/127), [PR128](https://github.com/bbungjun/AI_multimodal_platform/pull/128), [accepted spec](g7-generation-credit-integration-spec.md), [portfolio record](../portfolio/issue-127-generation-credit-integration.md) | Code `7e795c2`; exact19/migration0, generation-credit2 each8 groups/races2/checks120, inherited ownership all4 cycles and full regressions passed. Final required3 CI succeeded; squash `0a88b94`; no live provider claim |
| G8 | Atomic per-User concurrency enforcement | Mock Verified — Merged | [Issue129](https://github.com/bbungjun/AI_multimodal_platform/issues/129), [PR130](https://github.com/bbungjun/AI_multimodal_platform/pull/130), [accepted spec](g8-user-concurrency-enforcement-spec.md), [portfolio record](../portfolio/issue-129-user-concurrency-enforcement.md) | Code `4e8132a`; concurrency2 each8 groups/races6/checks259 and full regressions passed. Final head `b8292ad` required3 CI succeeded; protected squash `b050320`; Issue129 closed |
| G9 | Personal Plan and Usage experience | Split — A merged, B next | [G9A Issue131](https://github.com/bbungjun/AI_multimodal_platform/issues/131), [G9A spec](g9a-personal-usage-read-model-spec.md) | G9B consumes the merged read Interface after Issue99 containment delivery |
| G9A | Personal Plan and Usage read model | Mock Verified — Merged | [PR132](https://github.com/bbungjun/AI_multimodal_platform/pull/132) squash `2565a7a`, [Issue131](https://github.com/bbungjun/AI_multimodal_platform/issues/131), [accepted spec](g9a-personal-usage-read-model-spec.md), [record](../portfolio/issue-131-personal-usage-read-model.md); code `d103a44` | One Module/one GET Interface; 10 changed of exact11 allowlisted paths, migration0; personal usage2 each8 groups/races3/checks451, inherited ownership4/Linux1558/frontend48+34; no G9B/live provider claim |
| G9B | Personal Plan and Usage frontend | Planned | Consumes only the G9A Interface | Existing UI/CSS, responsive states and browser proof; no backend accounting joins |
| G10 | Master promotion/suspension, console, audit controls, and deterministic seed | Planned | None | Blocked by G3, G4, G5, G8 |
| G11 | Integrated E2E, race, migration, security, and portfolio evidence | Planned | None | Blocked by G1-G10, including G3.1 |

Per-Goal soft limits:

G4 is the aggregate of G4.1–G4.3. Downstream references to G4 require all three.
Aggregate rows are not executable Goals. G5 now has three bounded child slices;
the current status table, not a historical fixed slice count, defines delivery.
PostgreSQL/Redis verification uses local Docker, never a paid managed service.

- one primary module or delivery slice and one independently reviewable PR;
- 0.5 to 2 expected working days;
- no more than one migration;
- preferably no more than 12 production files and 8 test files;
- stop and split before implementation when the expected changed-file map
  exceeds 20 files or requires a second unrelated module;
- discovered enhancements go to follow-up Issues rather than expanding the
  active Goal.

G1 has one explicitly approved exception to the general file-count limit: its
fresh preflight found 15 production/configuration/script paths and 7 test paths
(22 total). The two additional paths are the isolated Postgres verifier and
removal of the obsolete runtime-DDL test; the one-module and one-migration
limits remain unchanged.

## Goal Update Protocol

At the start of a Goal:

1. Sync `main`, create the bounded Issue branch, and record the Issue in its row.
2. Change only that row to `In Progress` and replace `Next input` with the exact
   branch, dependency assumptions, and first verification command.
3. Copy only the relevant fixed decisions into the Goal plan. Link back here
   for all other decisions.

At the end of a Goal:

1. Set its row to `Implemented`, `Mock Verified`, or `Live Verified` only when
   the corresponding evidence exists.
2. Record the PR or commit, exact verification summary, and remaining risk in
   that row without appending raw logs.
3. Update the next row's `Next input` with the newly available interface and
   its contract, not an implementation history dump.
4. Update `docs/current-work.md` with a short current-state handoff.
5. Update or create the Issue-specific portfolio record with problem,
   diagnosis, decision, verification, result, and remaining risk.
6. If a fixed decision changes, edit the canonical section here and add a short
   dated entry below. Do not silently let code and this document diverge.

## Decision Change Log

| Date | Decision | Reason |
|---|---|---|
| 2026-09-02 | Accepted the complete initiative scope and ten-Goal execution model. | A single Goal would exceed a reliable context and verification surface. |
| 2026-09-02 | Narrowed G1 to schema control and moved User/Session persistence to G2, producing eleven Goals. | Repository inspection showed runtime DDL and process-startup migration concerns form a separate deep module from identity persistence. |
| 2026-09-02 | Accepted the G1 schema-control specification. | The scope, interface, reset guards, verification, rollback, and stop conditions are explicit enough to create a bounded execution Goal. |
| 2026-09-02 | Created Issue #94 and the G1 branch from merged `main` revision `fd96acc`. | G1 planning now has an isolated execution context and must not absorb G2 identity persistence. |
| 2026-09-02 | Replaced legacy ownership backfill with a clean database reset while retaining Alembic. | Existing data is disposable; schema reproducibility remains portfolio-relevant. |
| 2026-09-02 | Named the elevated role `master` and removed `admin`. | The product will expose only `user` and `master` RBAC roles. |
| 2026-09-02 | Approved a G1-only changed-path limit of 22 while retaining one module and one migration. | Fresh preflight found that the isolated Postgres verifier and removal of the obsolete runtime-DDL test were missing from the initial 20-path estimate. |
| 2026-09-02 | Promoted G1 to `Mock Verified`. | Two fresh isolated migration/reset cycles, three-process stale-revision refusal and recovery, and the mock product golden path passed at `6aa8a1f`; no cloud or provider call was made. |
| 2026-09-02 | Accepted the G2 User/Session persistence specification and six approval gates. | Keeping OAuth in G3 lets G2 prove identity schema, credential exclusion, migration, reset, and constraint behavior independently. |
| 2026-09-02 | Created Issue #96 and froze the G2 execution plan from `main` revision `eefe939`. | The 460-line plan bounds execution to one migration, 10 predicted non-document paths, a 12-path hard stop, two isolated Postgres cycles, and four final reviewers. |
| 2026-09-02 | Fixed sixth-login eviction and five-minute activity-touch policies for G3. | A User keeps access on a new device while database writes remain bounded; User-row locking and conditional updates make both policies race-testable. |
| 2026-09-02 | Split backend authentication, browser UX, and Master operations across G3, G3.1, and G10, producing twelve delivery slices. | Combining three interfaces would exceed one reliable Goal and obscure OAuth/session security review. |
| 2026-09-02 | Accepted the G3 backend OAuth/Session specification and created Issue #98 from merged `main` at `58f405b`. | The deep module, security policy, 17-path prediction, no-migration rule, and real Postgres+Redis verification gates are fixed before implementation. |
| 2026-09-02 | Froze the Issue #98 G3 Goal plan at SHA-256 `95dd3c9…da6c`. | Eight sequential Todos and four final reviewers now bind implementation, real-runtime proof, documentation, strict CI, and auto-merge without reopening scope. |
| 2026-09-03 | User chose existing UI/UX and CSS reuse for G3.1 rather than a redesign. | Keep the current shell, generation layout and shared UI; extend only auth/account styles. Behavior and implementation remain subject to the G3.1 draft approval. |
| 2026-09-03 | Accepted all G3.1 draft choices and created Issue #101 from synced `main` at `edd7208`. | Preserve existing UI/CSS, explicitly handle unsaved-input loss, add only opt-in start error redirect, and prove activity/cache/race/browser contracts in a 17-path, zero-migration Goal. Execution and merge are not implied by plan preparation. |
| 2026-09-03 | After Goal completion, user explicitly authorized Ready and squash auto-merge for PR #102 once required CI passes. | Supersedes Draft-only delivery for this follow-up; check the final head without bypassing protection. Frozen Goal/hash and mock-only implementation scope remain unchanged. |
| 2026-09-03 | Recorded G3.1 merge at `100f5e7` and drafted G4 ownership design. | Inspection found more than 20 affected paths including anonymous verification tooling. Three bounded slices and detailed Master/metrics policies are proposed, not accepted product-policy changes. |
| 2026-09-03 | User accepted G4.1/G4.2/G4.3, owner-only mutations even for Master, and Master-only ops/metrics; clarified local Docker-only Redis/PostgreSQL and mock AI. | Keep each execution context bounded, prevent cross-owner side effects and avoid managed-cloud/provider cost. Issue #103 and its frozen Goal prepare G4.1 without starting implementation. |
| 2026-09-03 | Proposed, not accepted: split G4.2 into A persistence/admission and B worker/reference proof; keep product policy and one total migration. | Post-G4.1 inspection found missing harness-head, identity-column and handler/runtime paths in the old20-path estimate. Detailed spec records exact candidates and approval gate; no implementation started. |
| 2026-09-03 | User accepted G4.2A/B split and authorized A execution preparation only. Issue #105 and branch created from synchronized main4dd359a; A frozen Goal fixes20 paths, one migration, Todo1–8/F1–F4. | Preserve prior design, bound one delivery slice for sol/medium, retain real schema2/auth1/admission2 gates. Future execution ends Ready PR, final-head CI and actual squash merge; no implementation or DB operations during preparation. |
| 2026-09-03 | After A actually merged, user requested proceeding to B. Prepared Issue107/branch/frozen Goal with exact11 paths (original10 plus guarded execution helper), migration0 and explicit worker/pipeline/observed-lock proof. | Same ownership policy; separate test helper keeps proof and identity fixtures local and readable. Preparation only, no B implementation or Docker/DB operation. Execution requires the frozen SHA request. |
| 2026-09-05 | Recorded G8 protected merge and split G9 into A backend personal-usage read model and B frontend. Prepared G9A Issue131 with one `GET /api/usage/me` Interface, exact11 paths and migration0. | Existing Usage rows truthfully support fixed billing-meter aggregation, not inferred exact provider models. Separating the read Module from UI keeps both Goals bounded and prevents frontend accounting joins. |

2026-09-03 proposal update (not an accepted Decision Change): following B actual merge
at `c84394a`, Issue109 records G4.3A/B split candidates because the existing transport
rejects list queries/array responses and `/metrics`. Ownership policy is unchanged.
This proposal was subsequently accepted; see the following update. No implementation started.

2026-09-03 accepted update: user approved G4.3A/B and A Goal preparation. Issue110
fixes A16 paths (A15 plus the existing persistence unsupported-intent test), zero
migrations, same ownership policy and Ready/final-CI/squash delivery. Candidate union23
does not increase the per-Goal20 cap. A remains private/incomplete until B; preparation
does not activate a Goal or authorize implementation without the frozen-SHA request.

2026-09-03 accepted preparation: user requested G4.3B through its Goal command.
After PR111 actual squash merge cd654e5, Issue112 freezes existing B16 paths,
migration0 and unchanged ownership policy. Add raw-path/DB-path binding, narrow
Master dependency, four final proof groups; retain all prior metadata/race proof.
Schema2/auth1 use unchanged verifiers in new isolated projects only. Preparation
is Planned, not implementation authorization. Public deployment and machine-metrics
authentication remain separately gated.

2026-09-03 accepted verification redesign (Issue112): user approved splitting the
over-budget combined cycle into ownership2 and file-ops2 fresh cycles. Each retains
work360s/cleanup90s; each suite900s and explicit aggregate1800s for four projects.
Explicit `--suite all` must pass both suites at one code revision; partial suites never close
G4.3B. Keep all legacy proof and F/O/V/E, add fixed safe failure codes/phase timing.
Product policy/exact16/migration0 are unchanged; new edits limited to existing5
verification paths. Preserve original frozen plan and failure; a new v2 plan/SHA
governs resume. This is approved preparation, not a new runtime success or delivery.
Default ownership preserves the existing manual smoke20-minute workflow budget;
that unchanged workflow alone cannot prove full G4.3B.

G4.3B delivery source: [Ready PR113](https://github.com/bbungjun/AI_multimodal_platform/pull/113).
Issue112 records final-head CI/actual squash SHA and parent109 closure. The complete
local proof is not a live deployment claim; G5 receives the documented Interfaces.

2026-09-03 G5 split preparation requested: parent114 and children115/116/117
separate persistence/pure policy, Plan lifecycle, and reserve/settle/release.
Existing prices, entitlements, 30-day policy and RBAC do not change. G5A freezes
four empty additive credit tables, integer microcredits, a pure rate/time Module,
exact17 paths and one new migration; no automatic credits or product wiring.
G5B/C remain dependency-gated planning envelopes until predecessor Interfaces
are implemented. [Detailed split](g5-credit-foundation-spec.md). Preparation is
not authorization to execute, and no new capability is marked Implemented.

### G5B design refinement proposal — 2026-09-04

G5B design consumes merged A without changing accepted prices/entitlements.
The user's hash-bearing execution request approved the bounded refinements in
[B spec section3](g5-credit-lifecycle-spec.md#3-lifecycle-rules-proposed-for-execution-approval):
current-cycle-only lazy issuance, replacement/cancellation of pending downgrades,
allowance-difference upgrades preserving consumed/held credit, available-only
expiry, and immutable payload-equivalent command replay before renewal.
A small append-only operation table is needed because scheduled/cancel/no-op Plan
requests cannot be represented by zero-valued credit ledger events. Exactly one
new migration and20 code paths include new-head proof compatibility. Internal
accounting access does not authenticate users or expose public Master mutations.
The bounded B Module is now implemented and undergoing isolated verification;
no B/C product wiring or charged-generation behavior is claimed.

### G5C split and policy freeze — 2026-09-04

G5B actually merged through PR119 at ffc4b50. Repository inspection found that
moving the packaged schema from0005 to0006 affects 15 existing proof/harness paths;
combining them with a new accounting Module and verifier requires at least22 code
paths. G5C is therefore split into C1 Issue120 (four empty accounting tables and
all head compatibility, exact20 paths, one migration) and C2 Issue121 (three-operation
accounting Module and PostgreSQL races, zero migration). The accepted settlement
policy records original units separately, charges complete/partial deliverables,
releases all credit for no deliverable, rejects usage above a bounded reservation,
and sends expired-grant remainder to expired rather than available. Details and
failure matrices are frozen in [the aggregate spec](g5-credit-accounting-spec.md).
This is design/Goal preparation, not implementation or charged-generation evidence.

### G6 accepted design and execution preparation — 2026-09-04

After PR123 actually squash-merged as `5e56ecb`, the user requested completing G6
before G7. Issue124 and branch `codex/issue-124-gemini-credit-integration` were
created from synchronized main. The accepted design adds one `prompt_credit`
Module and a required UUID request identity, with `reserve commit -> mock enhancer
-> PromptEnhancement plus settle atomic commit` and fixed release handling. No DB
transaction remains open across provider I/O. The retry-aware token envelope
covers every response-bearing validation path, and observed retry Usage is summed
instead of billing only the final response. Exact scope is14 non-document paths,
zero migrations, mock-only local proof; G7, live GCP, Usage UI and held-reservation
reconciliation remain separate. Preparation does not claim implementation.

2026-09-04 approved G6 verification redesign: Todo1 correctly stopped when the
required request UUID exposed two omitted inherited callers. The user approved
replacing the standalone mock-provider and support-test paths with
`scripts/verify_ownership.py` and `scripts/smoke_mock_golden_path.py`, preserving
exact14 paths, migration0 and all product policy. Mock token assertions and proof
support safety consolidate into the remaining approved tests. The v1 Goal and RED
failure remain evidence; v2 SHA governs resumed execution. This does not authorize
G7 or live provider/cloud work.

Local implementation reached Mock Verified at `87dca6b`. The deep Module owns
reserve/provider/terminal composition without a transaction across provider I/O.
Required UUID, a three-response envelope, usage source, atomic result+settle,
release and owner-safe replay are implemented. The v1 omission, shared harness
UUID failure and inherited security-test seam failure remain recorded. Two final
prompt-credit projects each passed35 checks/race1/cleanup0; ownership all2 passed
four cycles/cleanup0; tracked Linux1461 and frontend48/34 passed. Delivery remains
pending until final-head required3 CI and actual protected squash merge.

### G7 implementation and local proof — 2026-09-04

Issue127 implements a single deep `generation_credit` Module over the G5C
accounting Interface. API admission persists Job, Outbox and maximum Reservation
in one transaction before dispatch. Worker completion derives chargeable units
only from persisted, correctly typed Assets; standalone failure releases the
hold, while a pipeline holds once at its parent and settles combined or partial
delivery at the child boundary. Retry receives a new reservation and queue
terminal replay converges without duplicate Usage.

Execution required six bounded verification redesigns without changing product
policy: private metadata was filtered from public parameters; legacy retries got
explicit safe defaults; Outbox was moved after successful credit admission;
inherited ownership fixtures released their own holds and used non-product mock
rate limits; proof actors were aligned with persisted ownership; and terminal
delivery now rejects mismatched Asset kinds. The final scope is 19 approved
non-document paths, zero migrations and mock-only local execution.

At code `7e795c2`, two independent generation-credit projects each passed all
eight groups, two races, 120 checks and cleanup zero. Accounting/lifecycle/auth
passed once, ownership-all completed four cycles in 523.235s, tracked Linux passed
1487 tests with three guarded skips, and frontend lint/build plus Session48 and
Chromium34 passed. Local F1–F4 are APPROVE; delivery remains pending until the
Ready PR final head passes required `verify` and both Scan/SBOM checks and merges
through branch protection. This is not live Vertex usage, cloud billing, HTTP
create-request idempotency or orphan-file reconciliation evidence.

### G8 delivery and G9 split — 2026-09-05

G8 [PR130](https://github.com/bbungjun/AI_multimodal_platform/pull/130)
passed its final-head required three checks and protected squash-merged as
`b050320`; Issue129 closed. The G8 proof remains Mock Verified, not a live
provider or cloud-capacity result.

G9 is split into G9A backend read model and G9B frontend. G9A Issue131 defines
one deep `personal_usage` Module and authenticated `GET /api/usage/me` Interface
over existing schema head0006. The response uses a fixed billing-meter dimension
because persistence does not truthfully retain an exact provider model for every
Usage row. Exact11 non-document paths, migration0, local mock-only verification
and no User selector keep the backend slice bounded. G9B begins only after G9A
merges and consumes that Interface without direct accounting-table knowledge.

## Initiative Completion Gate

The initiative is complete only when G1-G11, including G3.1, have
evidence-backed terminal statuses and the following fresh checks pass in mock
mode:

- backend full pytest;
- frontend typecheck and production build;
- Playwright authentication, ownership, quota, and Master flows;
- Docker Compose mock golden path;
- Alembic upgrade, downgrade, and re-upgrade;
- 50 concurrent admissions without overspend or duplicate settlement;
- actual Google browser smoke for one Master and one normal User;
- documentation and evidence safety checks with no credential, OAuth token,
  prompt, provider raw response, personal email, or absolute local path.

## Next Goal

G5–G9A are merged. **Emergency Session revocation Issue99** is the active
pre-live containment slice. It adds a migration-free Module and guarded CLI;
login start/callback admission must be disabled before the atomic bulk revoke.
Only disposable local mock verification is authorized. After its protected
merge, G9B consumes the existing authenticated personal Plan, cycle, balance,
concurrency and fixed-meter Usage Interface. G10 Master/Audit remains separate.

G4 supplies User.id/signed_up_at, require_user, owner-only mutations and read-only
Master inspection, protected files/Range and Master ops. PR113 merged6537025;
parent109 is closed. G5 supplies lazy account/cycle creation and the atomic
accounting Interface. G6 adds the Gemini caller and G7 adds Imagen/Veo and
pipeline accounting.

Live operation remains gated by emergency revocation [#99](https://github.com/bbungjun/AI_multimodal_platform/issues/99),
real OAuth/browser/proxy verification and a machine-metrics access contract.
Master mutations and Audit remain G10, not a shortcut inside G5.
