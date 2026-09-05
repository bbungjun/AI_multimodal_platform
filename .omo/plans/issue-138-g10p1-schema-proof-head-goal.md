# Issue138 G10P1 execution Goal

Parent137; branch codex/issue-138-schema-proof-head; sequential, no subagents.
Read AGENTS, current-work and g10-master-operations-spec before execution.

## Frozen scope

At most18 non-document paths, no migration/runtime behavior change:

1. backend/app/schema_revision.py
2. backend/tests/test_schema_revision.py
3. scripts/mock_auth_support.py
4. scripts/verify_auth_sessions.py
5. scripts/verify_credit_accounting.py
6. scripts/verify_concurrency.py
7. scripts/verify_credit_lifecycle.py
8. scripts/verify_emergency_sessions.py
9. scripts/verify_generation_credit.py
10. scripts/verify_personal_usage.py
11. scripts/verify_prompt_credit.py
12. scripts/verify_schema_migrations.py
13. backend/tests/test_verify_auth_sessions_script.py
14. backend/tests/test_verify_credit_accounting_script.py
15. backend/tests/test_verify_credit_lifecycle_script.py
16. backend/tests/test_verify_emergency_sessions_script.py
17. backend/tests/test_verify_personal_usage_script.py
18. backend/tests/test_mock_auth_support.py

Only current-head expectations change. Existing historical migration assertions
and fixture literals stay for G10P2/A. Resolver parses AST literals without
executing migration files. Exactly one connected linear chain, one root/head,
unique valid revision names, no branches/cycles/missing parents. It must not read
settings, .env, DB or credentials. Scripts use stdlib runpy on this trusted repo
helper so standalone host scripts require no backend installation.

## Todo1–8

1. Baseline/hygiene; create resolver RED tests for valid and malformed graphs.
2. Implement resolver; focused tests pass. Commit.
3. Connect host consumers preserving all budgets, groups and cleanup guards.
4. Update named consumer assertions; focused regression and commit.
5. Inspect AST/output safety and cumulative paths; test fail-closed graph cases.
6. Full Windows backend regression (known Bash path failure must be reproduced,
   not hidden), frontend lint/build/Session/Chromium and Compose. Run schema
   verifier once on fresh isolated Docker project; cleanup must be0.
7. Update parent/initiative/current-work/Issue portfolio with actual evidence.
8. Push, main Ready PR, final-head verify and both Scan/SBOM success; squash
   auto-merge without admin override, confirm MERGED and synchronize main.

Every Todo: focused `python -m pytest tests/test_schema_revision.py -q` from
backend after test creation; `git diff --check`, `git status --short --branch`,
`git diff --cached --name-only`, cumulative `git diff --name-only origin/main`.
Commit small coherent units, stage exact files (never whole .omo).

## Verification commands and limits

- backend: AI_PROVIDER=mock python -m pytest -q (300s, include known native Bash
  exception evidence); focused tests 120s.
- frontend: npm run lint; npm run build; npm run test:auth;
  npm run test:auth:browser (each180s).
- docker compose --env-file .env.example config --quiet (60s).
- python scripts/verify_schema_migrations.py --env-file .env.example
  (existing internal budgets unchanged; outer600s). No dev/preview DB changes.
- Required CI provides fresh full Linux backend evidence on final PR revision.

F1 APPROVE: paths<=18, migration0, original user changes preserved.
F2 APPROVE: invalid lineage rejected, exact0006 unchanged, privacy and guards.
F3 APPROVE: fresh focused/full/schema/frontend/CI evidence, cleanup0.
F4 APPROVE: problem/cause/solution/results/risks docs, merged PR, closed138.
Parent137 stays open. Any path/budget expansion stops for redesign, never relaxes
tests. No OAuth/provider/cloud, data reset, runtime auth change or paid call.
