# Issue155 G11B mock browser acceptance Goal

Design: gpt-6-astra (verified design-turn metadata). Implementation MUST run
gpt-5.6-sol, medium reasoning, sequentially without subagents. Read AGENTS.md,
docs/current-work.md, docs/initiatives/g11b-mock-browser-acceptance-spec.md and
canonical G11/Completion Gate. Baseline main1214dfd (G11A PR154 merged).
Branch codex/issue-155-mock-browser-acceptance. Preserve all .omo history/user data.

## Exact8 non-document paths; migration0/product0

1. scripts/verify_browser_acceptance.py
2. scripts/browser_acceptance_support.py
3. frontend/tests/browser-acceptance-driver.mjs
4. frontend/tests/browser-acceptance-driver.test.mjs
5. backend/tests/test_verify_browser_acceptance.py
6. backend/tests/test_browser_acceptance_support.py
7. backend/tests/browser_acceptance_fixtures.py
8. backend/tests/test_browser_acceptance_fixtures.py

Do not edit existing shared harnesses, application/auth/accounting/worker code,
frontend UX, package manifests, CI or migrations. Ninth path/product fix/time
relaxation => stop, preserve failure and report redesign. No actual OAuth/provider,
cloud/Kubernetes/Terraform, developer/preview DB or permanent account mutation.

## Todo1-8 (ordered checkpoints)

1. Verify this file SHA matches dispatch, model Sol/medium, branch/main predecessor,
   clean tracked/staged baseline; update G11B state In Progress. Read relevant
   existing OwnedRuntime, emergency CLI, UI labels and fixture contracts.
2. Implement strict coordinator/receipt/protocol guards and unit tests. Closed
   local target, port18155 collision refusal, deadlines, stderr suppression,
   no raw secret/ID/SQL/prompt/body output and owned-process cleanup.
3. Implement test-only runtime subclass and recovery fixture, reusing owned G4
   startup/seed/cleanup. Exact origin, login disabled, insecure cookie ONLY local
   HTTP verifier. Hash-only append of fresh A/Master Sessions; never undo revocation.
4. Implement Node/Vite/Chromium real browser driver and Node unit tests. All eight
   spec groups, real HTTP responses (no fulfill); actual User/Master UI commands,
   generation detail/Usage/ownership, suspension/logout, CLI preview/execute/replay,
   fresh test-session recovery. All browser data ephemeral; external egress blocked.
5. Focused tests + stable implementation commit. Run new verifier exactly two
   independent cycles, each8 groups/80 meaningful checks minimum,360s work/90s
   cleanup,900s aggregate, browser180s within remaining budget. Enforce all-stage
   success and code revision binding; cleanup Docker0, owned Node/Chromium0,
   port release. No code edits while proof runs; no automatic timeout retry.
6. Fresh regression commands below. Preserve failed attempts and known Windows
   exception; full Linux CI required. No unchanged G11A full matrix rerun needed.
7. Portfolio problem/observation/failed approach/fix/commands/results/risks;
   canonical row/Decision Change Log/current-work and docs/testing update. Explicit
   mock recovery vs real Google/TLS/live distinctions. No whole-G11 completion.
8. Push, main-target Ready PR. Final-head verify and both Scan/SBOM SUCCESS,
   protected squash auto-merge and actual MERGED. Verify155 closed/152 OPEN;
   sync local main. No bypass/admin merge.

Each checkpoint focused tests, git diff --check, git status --short --branch,
git diff --cached --name-only and cumulative code-path check; small commits.
Stage only explicit paths, never all .omo. Record implementation model honestly.

## Verification commands and limits

- Backend AI_PROVIDER=mock `python -m pytest tests/test_verify_browser_acceptance.py
  tests/test_browser_acceptance_support.py tests/test_browser_acceptance_fixtures.py
  -q`120s. Use only created subset during scaffolding.
- Frontend `node --test tests/browser-acceptance-driver.test.mjs`120s.
- Root `python scripts/verify_browser_acceptance.py`900s aggregate, above budgets.
- Root `python scripts/verify_emergency_sessions.py --env-file .env.example`
  twice, each120s work/60s cleanup,8 groups/80checks/1race minimum.
- Root `python scripts/verify_integrated_acceptance.py` once (its2 cycles),900s.
- Root `python scripts/verify_auth_sessions.py --env-file .env.example` once,
  and `python scripts/verify_master_suspension.py --env-file .env.example` once;
  preserve each existing command's built-in deadlines (suspension180/60).
- Backend `AI_PROVIDER=mock python -m pytest -q`300s; known Bash127 path failure
  distinct from actual regressions, no new skip. Linux full pytest via required CI.
- Frontend npm run lint/build/test:auth/test:auth:browser each180s; existing70/61.
- Root `docker compose --env-file .env.example config --quiet`60s.

F1 APPROVE: exact8/test-only scope, model constraint, migration0, no live/data leak.
F2 APPROVE: eight real browser/proxy/CLI groups, permanent old-session refusal,
fresh mock recovery, no response stubs or product auth bypass.
F3 APPROVE: two independent proofs+regressions+Linux CI, counts/deadlines/cleanup0.
F4 APPROVE: truthful safe docs, protected merge, parent152 remains open.
