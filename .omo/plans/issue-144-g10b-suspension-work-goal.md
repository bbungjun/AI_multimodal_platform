# Issue144 G10B Goal

Read AGENTS, current-work, canonical Identity/Master policy, G10 specification,
master_admin Interface, generation_credit terminal Interface and pipeline_link.
Branch codex/issue-144-suspension-work-cancellation, sequential/no subagents.

## Exact allowed paths (max14), migration0

1. backend/app/master_admin.py
2. backend/app/master_work.py
3. backend/app/api/master.py
4. backend/app/services/jobs/pipeline_link.py
5. backend/tests/test_master_admin.py
6. backend/tests/test_master_api.py
7. backend/tests/test_master_work.py
8. backend/tests/test_pipeline_link.py
9. backend/tests/master_suspension_support.py
10. backend/tests/test_master_suspension_support.py
11. scripts/verify_master_suspension.py
12. backend/tests/test_verify_master_suspension_script.py
13. backend/tests/test_job_handlers.py (only affected fake-session contract)
14. backend/tests/test_ownership_execution.py (only affected fake-session contract)

No schema/credit engine/provider/frontend/dispatcher changes. Developer/preview
DBs preserved, local Docker+mock only. Console and seed remain later slices.

## Fixed semantics

- Extend existing browser command with suspend/reactivate; no HTTP promotion.
  Existing advisory/User lock and replay/fingerprint discipline remains.
- No self-suspension or suspension of final active Master. All Sessions revoked
  in the mutation transaction; reactivation does not revive Sessions or Jobs.
- No lazy billing initialization merely to change status. Audit may use null
  plan when the account has never been initialized; role/status stay explicit.
- Dispatch cut: a nonpending Job or any published Outbox event means previously
  dispatched/claimed; preserve it and normal terminal accounting. Pending Jobs
  without a published event are cancellation candidates. Lock Outbox rows before
  Jobs so a dispatcher publication transaction wins or loses before cancellation;
  delayed/redelivered messages see terminal cancelled Jobs and do not execute.
- Existing dispatcher holds Outbox locks across publication; suspension must
  re-read committed status after waiting. Do not add network calls or queue locks.
- Bound each target scan to500 pending Jobs/Outbox rows; more returns master_busy
  and rolls back everything. No partial success. DB deadlock/timeout similarly
  fails safely, never reports successful suspension with partial effects.
- Unpublished parent+child: cancel both, release once through existing parent
  terminal Interface. A blocked child of an already dispatched/running parent is
  deferred; never release that shared Reservation early. After parent completion,
  pipeline_link locks owner before child, cancels child if suspended and accounts
  for the delivered parent as partial success. Parent failure keeps the existing
  release, while its blocked child becomes cancelled for a suspended owner.
- Use state_machine transitions and existing generation terminal accounting only.
  Reactivation permits new work but does not resurrect cancelled/outbox-failed work.
- Audit records immediate revoked_sessions/cancelled_jobs counts. Deferred pipeline
  cancellation is visible in Job history, not fabricated as an immediate Audit count.

## Todo1–8 and gates

1. Baseline tests and In Progress record; SHA integrity gate.
2. Status command validation/auth/self protection and transaction changes.
3. Internal work-cancellation Implementation with safe pipeline accounting.
4. Pipeline and HTTP Adapters; focused tests/commit.
5. Fixed isolated proof/harness:8 groups (guards,sessions,reactivation,pending,
   published,pipeline,rollback,races), at least4 observed lock races and80 checks.
6. Stable committed proof2; inherited Master administration1,generation-credit1,
   auth1,ownership --suite all --cycles1; full backend/frontend/Compose regressions.
7. Problem/cause/failed approaches/solution/results/risks portfolio, current-work,
   canonical status. G10A merge evidence included.
8. Ready PR, final-head verify and both Scan/SBOM successful, protected squash
   auto-merge, confirm MERGED/Issue144 closed, sync main. Parent137 stays open.

Each Todo: focused tests, git diff --check, git status --short --branch,
git diff --cached --name-only, cumulative paths against origin/main; exact staging
and small commits. Never whole .omo. No edits/commits during isolated proof.

F1 scope14/migration0; F2 all-or-nothing revocation/cancellation, pipeline balance,
authority/replay/races; F3 fresh proof2/inherited/full/CI/cleanup0; F4 truthful
records/protected merge. All must APPROVE. Path/time overrun stops for redesign.

## Commands and limits

Backend AI_PROVIDER=mock focused `python -m pytest tests/test_master_admin.py
tests/test_master_api.py tests/test_master_work.py tests/test_pipeline_link.py
tests/test_master_suspension_support.py tests/test_verify_master_suspension_script.py
-q` (120s; select existing files during construction); full pytest300s with known
Windows Bash failure preserved and fresh Linux CI mandatory.
Root `python scripts/verify_master_suspension.py --env-file .env.example` twice,
work180/cleanup60. Existing master-admin180/60,generation-credit120/60,
auth existing per-command limits/outer600s, ownership existing internal limits
unchanged with explicit --suite all --cycles1 (outer1200s).
Frontend lint/build/test:auth/test:auth:browser each180s; public Compose60s.
All isolated containers/volumes/networks cleanup0. No actual OAuth/provider/cloud.
