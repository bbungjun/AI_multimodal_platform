# Issue140 G10P2 Goal

Input: AGENTS, current-work, g10-master-operations-spec and merged G10P1
schema_revision.CODE_REVISION Interface. Branch codex/issue-140-container-proof-head.
Sequential, no subagents. User authorized design and execution of G10.

## Exact allowed19 non-document paths

- backend/tests/concurrency_support.py
- backend/tests/credit_accounting_schema_support.py
- backend/tests/credit_accounting_support.py
- backend/tests/credit_foundation_support.py
- backend/tests/credit_lifecycle_support.py
- backend/tests/emergency_sessions_support.py
- backend/tests/generation_credit_support.py
- backend/tests/ownership_support.py
- backend/tests/personal_usage_support.py
- backend/tests/prompt_credit_support.py
- backend/tests/test_credit_accounting_schema_support.py
- backend/tests/test_credit_accounting_support.py
- backend/tests/test_credit_foundation_support.py
- backend/tests/test_credit_lifecycle_support.py
- backend/tests/test_emergency_sessions_support.py
- backend/tests/test_personal_usage_support.py
- backend/tests/test_ownership_persistence.py
- backend/tests/test_verify_schema_migrations_script.py
- backend/tests/test_schema_revision.py

No migration/product/frontend changes. Replace current-head literals only;
historical migrations/lineage assertions stay. No test threshold, count, privacy,
runtime budget or cleanup guard relaxation. Developer/preview DBs preserved.

## Todo1–8

1. Verify plan SHA and clean tracked baseline; run focused tests below.
2. Connect10 proof consumers through imported CODE_REVISION aliases.
3. Replace current-head assertions with exported values; preserve graph oracle
   coverage by comparing resolver against Alembic's independently loaded head.
4. Focused tests/hygiene/path audit and coherent commit.
5. Security/lineage review; compile/test actual proof imports and guard refusal.
6. Stable committed checkout only: isolated schema once and personal usage once;
   full Windows backend, frontend lint/build/Session/Chromium and Compose.
7. Portfolio/current-work/canonical update; document G10P1 merge and all evidence.
8. Ready PR, final-head verify plus both Scan/SBOM PASS, squash auto-merge and
   actual MERGED; synchronize main. Close140, keep parent137 open.

Each Todo runs focused tests, git diff --check, git status --short --branch,
git diff --cached --name-only, cumulative git diff --name-only origin/main;
stage exact paths, small commits, never whole .omo.

## Commands and deadlines

From backend, AI_PROVIDER=mock:
`python -m pytest tests/test_schema_revision.py tests/test_credit_accounting_schema_support.py tests/test_credit_accounting_support.py tests/test_credit_foundation_support.py tests/test_credit_lifecycle_support.py tests/test_emergency_sessions_support.py tests/test_personal_usage_support.py tests/test_ownership_persistence.py tests/test_verify_schema_migrations_script.py -q` (120s).
`python -m pytest -q` (300s; preserve established Windows Bash exception).
From root: `python scripts/verify_schema_migrations.py --env-file .env.example`
(work300/cleanup90, existing); `python scripts/verify_personal_usage.py --env-file .env.example`
(work120/cleanup60, existing). No edits/commits during each proof. Cleanup0.
`docker compose --env-file .env.example config --quiet` (60s).
From frontend: npm run lint, npm run build, npm run test:auth,
npm run test:auth:browser (each180s).

F1 scope19/migration0 APPROVE; F2 all old security guards and invalid lineage
rejection APPROVE; F3 fresh regression/isolated/CI evidence APPROVE;
F4 documentation and protected merge APPROVE. Path/time overrun stops for
redesign, never verification bypass. No real OAuth/provider/cloud/data reset.
