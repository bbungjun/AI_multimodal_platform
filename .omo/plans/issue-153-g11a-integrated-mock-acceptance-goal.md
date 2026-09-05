# G11A Issue153 execution plan

Read AGENTS.md, docs/current-work.md, canonical Initiative Completion Gate and
docs/initiatives/g11-integrated-acceptance-spec.md. Sequential; no subagents.
Branch codex/issue-153-integrated-mock-acceptance. Local Docker/AI_PROVIDER=mock.

## Todo1-8

1. Verify G10 merge/main, dirty/staged baseline, freeze this plan hash and spec.
2. Add test-only HTTP scenario over the existing owned runtime, eight groups.
3. Add receipt/privacy/failure/guard unit contracts; no product changes.
4. Focused tests and stable implementation commit; inspect exact cumulative scope.
5. Two independent HTTP cycles,360s work/90s cleanup each,900s aggregate;
   eight groups and at least40 assertions each. Stop on failure; preserve receipt.
6. Existing proof matrix from spec and full regression, unchanged time limits.
7. Portfolio/current-work/canonical state, failure evidence and honest live gaps.
8. Ready PR, final head verify/backend+frontend Scan/SBOM success, squash auto-merge,
   actual MERGED/#153 closed/main sync. Keep #152 open for separately authorized gates.

F1 APPROVE: only scripts/verify_integrated_acceptance.py and
backend/tests/test_verify_integrated_acceptance.py non-document changes; migration0.
F2 APPROVE: eight real HTTP groups, no identity/provider bypass in product.
F3 APPROVE: fresh independent proofs, regression/CI and cleanup0.
F4 APPROVE: safe truthful evidence, protected delivery, remaining live gate explicit.

Each checkpoint focused tests, git diff --check/status/cached path check and small
commit. No edits during proofs. Seventh/extra scope not implicit; any third code
path/product fix requires redesign. No .omo-wide staging or developer DB resets.

## Commands

Backend focused `python -m pytest tests/test_verify_integrated_acceptance.py -q`
120s; full `python -m pytest -q`300s with AI_PROVIDER=mock.
Root `python scripts/verify_integrated_acceptance.py`900s aggregate.
Root existing scripts verify_schema_migrations.py (twice), verify_credit_lifecycle.py,
verify_credit_accounting.py, verify_concurrency.py, verify_prompt_credit.py,
verify_generation_credit.py, verify_personal_usage.py, verify_auth_sessions.py,
verify_master_admin.py, verify_master_read.py, verify_master_suspension.py once;
all `--env-file .env.example` and inherited work/cleanup limits.
`python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 2`
1800s aggregate. Frontend npm run lint/build/test:auth/test:auth:browser each180s.
`docker compose --env-file .env.example config --quiet`60s. Linux full pytest via CI.
