# Issue142 G10A Goal

Read AGENTS, current-work, g10-master-operations-spec, canonical initiative's
Identity/Plans/Master sections and existing credit_lifecycle Interface.
Sequential implementation, no subagents. Branch codex/issue-142-audited-master-administration.

## Frozen17 non-document paths

1. backend/app/master_models.py
2. backend/migrations/versions/0007_master_audit.py
3. backend/app/models.py
4. backend/app/master_admin.py
5. backend/app/master_cli.py
6. backend/app/api/master.py
7. backend/app/main.py
8. backend/tests/test_master_models.py
9. backend/tests/test_master_admin.py
10. backend/tests/test_master_api.py
11. backend/tests/test_master_cli.py
12. backend/tests/master_admin_support.py
13. backend/tests/test_master_admin_support.py
14. scripts/verify_master_admin.py
15. backend/tests/test_verify_master_admin_script.py
16. scripts/verify_schema_migrations.py
17. backend/tests/test_alembic_schema.py

Exactly one additive migration0007_master_audit;0001–0006 unchanged. No
suspension implementation, worker/Job/accounting/lifecycle/provider/frontend change.
No dev/preview DB mutation, actual OAuth/cloud/provider, seed or payment.

## Interface and invariants

One caller-transaction administration Module: plan change, bonus grant and
operator CLI promotion. Narrow command includes action,target,request UUID,
allowlisted reason,typed payload; actor comes from require_master, never HTTP
payload. Re-read actor under lock inside transaction (active OAuth Master).
Serialize administrative commands with a transaction advisory lock, then lock
actor/target Users in UUID order before existing credit lock order. All waits
bounded by local transaction lock/statement timeouts. No network in transaction.

Audit row contains actor/target UUID,request UUID,action,source,time,payload
fingerprint and allowlisted safe before/after JSON. Reasons:operator_bootstrap,
entitlement_change,support_adjustment,service_recovery,account_policy,
account_reactivated. No free text,PII,prompt,tokens,raw responses/SQL. Database
rejects UPDATE/DELETE/TRUNCATE; populated downgrade refuses before DDL. Audit
failure rolls back business changes. Runtime DB owner can alter schema: do not
claim superuser-proof tamper resistance.

Request UUID unique globally. Exact actor/target/action/reason/payload replay
returns prior result, changed reuse409. Auth is rechecked before replay. Existing
credit lifecycle operations use namespaced request key; promotion upgrades normal
User to Max before role assignment, clears pending downgrade, retains consumed
Credit. Synthetic/suspended target cannot be promoted. No demotion endpoint.

HTTP POST /api/master/users/{target_id}/commands accepts plan_change or bonus_grant
only, bounded strict payload, require_master/trusted Origin. All responses/errors
private,no-store. No list/console/suspend routes yet. Codes403 master_required,
404 master_target_missing,409 master_conflict,422 master_input_invalid,
503 master_busy/master_unavailable; never expose internal exception text.

CLI python -m app.master_cli --user-id UUID --request-id UUID --reason CODE
--expected-database NAME [--execute --confirm PROMOTE:UUID]. Default transactional
simulation rolls back all writes. Verify exact non-system PostgreSQL database,
local host, mock provider and development/test environment; no credential output.
Bootstrap audit source operator_cli explicitly identifies privileged operator
execution, with target as actor; it does not impersonate browser authentication.

## Todo1–8

1. Baseline/RED contract tests, register In Progress.
2. Audit model/migration/metadata registration and exact schema inventory.
3. Transactional Module, validation/replay/credit integration; focused commit.
4. HTTP and guarded CLI Adapters; privacy/security contract tests; commit.
5. Real proof and harness:8 groups (guards,promotion,plan,bonus,replay,rollback,
   append_only,races); at least4 actual races and60 meaningful checks. Unit tests
   prove parser guards, exact groups/receipt keys and bounded cleanup.
6. Commit all code, run stable independent PostgreSQL proof2 (separate projects),
   schema once, lifecycle once, accounting once, auth once; full Windows backend,
   frontend lint/build/Session/Chromium, Compose. No edits/commits during proofs.
7. Portfolio/canonical/current-work evidence and remaining risk updates.
8. Ready main PR, final-head verify and both Scan/SBOM successful, squash auto-
   merge, confirm MERGED/Issue142 closed, main sync. Parent137 stays open.

Each Todo runs focused tests, git diff --check, git status --short --branch,
git diff --cached --name-only and cumulative git diff --name-only origin/main;
small commits, exact staging, never whole .omo. Preserve failures and user files.

## Commands and hard limits

AI_PROVIDER=mock; backend focused `python -m pytest tests/test_master_models.py
tests/test_master_admin.py tests/test_master_api.py tests/test_master_cli.py
tests/test_master_admin_support.py tests/test_verify_master_admin_script.py -q`
(120s; only existing test files before all are created). Full `python -m pytest
-q`300s, preserve known native Bash exception and require Linux CI green.
Root `python scripts/verify_master_admin.py --env-file .env.example` twice;
work180/cleanup60 each. Existing schema work300/cleanup90; lifecycle/accounting
existing work300/cleanup90; auth existing per-command limits, outer600s.
Frontend lint/build/test:auth/test:auth:browser each180s; Compose60s.
All isolated cleanup container/volume/network0. Graphical console excluded.

F1 scope17/migration1; F2 authority/replay/rollback/append-only and locked races;
F3 fresh isolated2/inherited/full/CI; F4 accurate docs and protected merge: all
must APPROVE. Path/time expansion stops for documented redesign, never relaxed
verification or admin merge. Mock evidence is not live operations validation.
