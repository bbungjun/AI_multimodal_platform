# Authentication, Credits, and Master Console Initiative

## Document Contract

- Status: `Accepted / Planned`
- Last updated: `2026-09-02`
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
| G3.1 | Authenticated workspace entry and browser Session UX | Planned — Spec Accepted | [Accepted spec](g3-1-authenticated-workspace-ux-spec.md), [Issue #101](https://github.com/bbungjun/AI_multimodal_platform/issues/101), branch `codex/issue-101-authenticated-workspace-ux` from `edd7208` | Prepare frozen Goal; execution not started; first check is baseline lint/build and collection-safe failing contracts |
| G4 | Ownership policy across Job, Prompt Enhancement, and Asset | Planned | G3 interface available | Consume `app.api.auth_dependencies.require_user` and `AuthenticatedUser`; generation currently remains unauthenticated |
| G5 | Credit account, Plan lifecycle, Rate Card, Reservation and Settlement | Planned | None | Blocked by G2 |
| G6 | Gemini prompt-enhancement credit integration | Planned | None | Blocked by G5 |
| G7 | Imagen/Veo and pipeline credit integration | Planned | None | Blocked by G4, G5 |
| G8 | Atomic per-User concurrency enforcement | Planned | None | Blocked by G7 |
| G9 | Personal Plan and Usage UI | Planned | None | Blocked by G6, G7 |
| G10 | Master promotion/suspension, console, audit controls, and deterministic seed | Planned | None | Blocked by G3, G4, G5, G8 |
| G11 | Integrated E2E, race, migration, security, and portfolio evidence | Planned | None | Blocked by G1-G10, including G3.1 |

Per-Goal soft limits:

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

G3's backend interface is mock verified at `ec42d61`; delivery and strict CI /
squash auto-merge status are tracked in [PR #100](https://github.com/bbungjun/AI_multimodal_platform/pull/100).
After merge, design G3.1 around `/me`, logout,
host-only HttpOnly/Lax/Secure cookies and the start/callback redirect contract.
G3.1 must not duplicate Google verification or Session policy. G4 separately
consumes `require_user` for ownership enforcement. Existing generation endpoints
are not yet protected, and there is no product mock-login bypass. Live operation
remains blocked by emergency revocation [#99](https://github.com/bbungjun/AI_multimodal_platform/issues/99)
and later browser/proxy verification. No Plan/Credit or Master mutation is
delivered by G3.

G3 merged at `edd7208`. The [G3.1 specification](g3-1-authenticated-workspace-ux-spec.md)
is accepted, including the existing-CSS constraint, auth UI states, mobile account
access, activity/cache/race policies, `ui=1` start error redirect and unsaved-input
reset. Issue #101 and its branch exist with a 17-path/zero-migration prediction.
The next step is the frozen Goal's explicit execution request, not further
feature design or automatic implementation. Delivery ends at a Draft PR with
passing required CI; ready/merge/auto-merge needs separate authorization.
