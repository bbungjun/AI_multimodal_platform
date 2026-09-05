# G10 Master operations delivery specification

Status: Accepted execution direction; individual slices require their frozen
path/verification plan before implementation. User authorized design followed by
execution on 2026-09-05. Canonical product policy remains
[the initiative](auth-credits-master-console.md).

## Outcome and scope

An operator can administer accounts without direct database editing, with atomic
audit evidence and safe user-facing controls. Existing studio navigation/CSS,
Google-only login, owner-only content mutations, integer Credit and mock-only
verification remain unchanged. No payment, live OAuth/provider/cloud, production
seed, account deletion, role demotion or arbitrary SQL console is added.

## Sequential delivery slices

Each slice has its own Issue, branch, frozen SHA-256 Goal, at most20
non-document paths and a protected Ready PR. No claim of whole-G10 completion
until every slice passes. Exact paths and commands are frozen immediately before
that slice, using the preceding merged Interface.

1. **G10P1/P2 — schema proof compatibility.** Inspection found current-head
   literals throughout scripts and backend proof fixtures. Replace only live-head
   expectations with one code-derived revision contract; retain exact historical
   migration assertions and fail on multiple heads/missing lineage. No migration
   or product behavior change. Split host harness and container proof consumers.
2. **G10A — audited account administration.** One transactional Module, additive
   `0007_master_audit` migration, CLI promotion and Master-only Plan/bonus
   mutations. UI and suspension are not yet exposed. Audit insertion failure
   rolls back the business mutation. Promotion upgrades Credit to Max while the
   target is still a normal User, then changes role within the same transaction;
   never leave an existing Free account with an incoherent Master role.
3. **G10B — suspension lifecycle.** Extend the administration Interface with
   suspend/reactivate, revoke all Sessions and cancel work not yet dispatched.
   Coordinate dispatcher/worker/pipeline races without revoking running provider
   work or prematurely releasing a running pipeline Reservation. No new queue.
4. **G10C — operational read model.** Master-only paginated User/Audit views and
   bounded aggregate windows with safe error allowlists. Separate real/synthetic
   counts and disclose measurement definitions.
5. **G10D — console UX.** Reuse workspace styles and session-epoch cache isolation.
   Add role-gated navigation and account/metrics/Audit views with reason,
   confirmation, replay-safe submission and explicit error/empty/loading states.
6. **G10E — deterministic synthetic fixture.** Guarded dry-run/apply CLI for120
   login-disabled Users (84/30/6 Free/Pro/Max) and approximately3000 Jobs over90
   days. Deterministic namespaced keys and idempotency; never reset a DB. Refuse
   production, live provider and non-owned verification targets during execution.

## Administration Interface invariants

- Re-read the acting User under lock inside each mutation; a previously
  authenticated role is not sufficient authorization for a delayed request.
- Lock order: administration serialization lock, actor/target Users ordered by
  UUID, then existing credit/session/work locks according to the slice-specific
  proven protocol. Never hold a DB transaction across a provider/network call.
- UI cannot promote/demote roles. Promotion is exact-UUID operator CLI only with
  target database guard, default dry-run, explicit apply confirmation and bounded
  reason code. Bootstrap audit actor is the exact target User with an explicit
  `operator_cli` source; this is not a claim of a browser-authenticated actor.
- No self-suspension or suspension of the final active Master. Serialize checks
  so concurrent actions cannot eliminate the final active Master.
- Reactivation does not resurrect Sessions, cancelled Jobs or expired credits.
- Request UUID is stable across retries. Matching replay returns the original
  receipt without a second mutation/audit; mismatched payload returns409.
- Reasons are allowlisted codes, not unrestricted text that could contain PII.
- Audit stores actor/target UUID, action, source, request UUID, time and bounded
  before/after values. No email, cookie/session/token, prompt, raw error/response,
  SQL, arbitrary JSON or user-controlled free text. All HTTP responses including
  failures are private, no-store. CSRF uses existing trusted-Origin protection.
- Audit UPDATE/DELETE/TRUNCATE are blocked by database triggers for the runtime
  role. This is append-only application evidence, not tamper-proof evidence
  against a database owner/superuser capable of changing the schema.

## Suspension decision gate

Before G10B code, prove the actual dispatcher claim/publication and worker
provider-start commit points, including pipeline parent/child semantics. The
policy remains cancellation of not-yet-dispatched work, while already running
provider work completes/settles. A queue-publication race must not be papered over
with process locks, sleeps or a blanket release of every held Reservation.
If this needs a second delivery slice, split it before changing code.

## Read model and console

Use bounded time windows (default30 days, max90), deterministic cursor pagination
and fixed sort ordering. State aggregation denominator, duration source and
empty-sample behavior; never report zero p95 as if measured. Credit reservation,
consumption, release and observed meter units remain distinct. Exact provider
model attribution is used only where persisted, never guessed from meter names.
Admission denials without persisted Jobs are not fabricated as failed Jobs;
synthetic denial scenarios must be explicitly fixture observations or deferred
with an explicit contract. User list includes signup/renewal, status/origin,
Plan/pending Plan, available/consumed Credit. Details load lazily, avoiding a
global lazy-renewal write on opening the console.

## Verification and exit gates

Every Goal uses Todo1 baseline/RED, Todo2 Interface, Todo3 Implementation,
Todo4 Adapter, Todo5 focused security/races, Todo6 isolated and full regression,
Todo7 portfolio/handoff, Todo8 Ready PR/protected merge. Each Todo checks focused
tests, diff whitespace, status, staged paths and cumulative paths; commit small
coherent changes. F1 scope/plan, F2 correctness/security, F3 reproducibility and
F4 documentation/delivery must all APPROVE, backed by fresh results.

Mutation/schema slices require two independent local PostgreSQL proofs including
rollback, replay conflict, stale authority and actual observed lock races.
Migration verification covers upgrade/downgrade/re-upgrade only in disposable
projects. Suspension adds auth plus ownership/generation accounting regressions.
Frontend slices require Session/Chromium, role bypass/direct URL, expired Session,
double submission, mobile/desktop screenshots and lint/build. Seed proves exact
counts, rerun no duplication, dry-run no writes and guard refusal.

Every slice runs backend regression, frontend lint/build and public-template
Compose config; frozen plans define relevant additional regression commands and
bounded subprocess/cleanup times. On deadline, path or schema overrun, preserve
failure evidence and stop that plan for redesign rather than weakening a gate.
Final-head verify and both backend/frontend Scan/SBOM must succeed; no admin
merge or synthetic check bypass. Preserve developer/preview DBs and `.omo` files.

## Evidence

Record problem, root cause, failed alternatives, changes, commands/results,
remaining risks and merged PR per Issue. No live verification claims. G11 remains
the integrated acceptance and separately authorized real-browser/cloud stage.
