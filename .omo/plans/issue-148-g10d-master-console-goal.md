# Issue148 G10D Goal

Read AGENTS/current-work/canonical Master policy/G10 design and
docs/initiatives/g10d-master-console-spec.md. Sequential/no subagents.
Branch codex/issue-148-master-console. Preserve existing UI/CSS and Session guard.

## Exact9 non-document paths, migration0

1. frontend/src/App.tsx
2. frontend/src/api/client.ts
3. frontend/src/ui/master.ts
4. frontend/src/pages/MasterPage.tsx
5. frontend/src/index.css
6. frontend/tests/master-model.spec.ts
7. frontend/tests/master-ux.spec.ts
8. frontend/tests/master-fixtures.ts
9. frontend/playwright.config.ts

Only one console slice. No backend/writer/schema/provider/login changes, no seed,
real OAuth/cloud or developer/preview database mutation. Exact staging only; do
not stage .omo wholesale or identity-bearing screenshots/raw errors.

## Todo1–8

1. Verify Goal SHA, baseline frontend Session/Chromium, status and merged G10C;
   record Issue/branch In Progress. Read current UI and Session/client contracts.
2. Pure response/view/amount/command Interface tests, strict integer precision.
3. Existing-guard HTTP functions, role-gated App navigation/direct route.
4. Console panels, filters/keyset pages, command confirmation/replay gate and CSS.
5. Focused model/browser tests: forbidden role, stale session, mutation failure/
   double-submit/sameUUID replay, empty/error, responsive and masked screenshots.
6. Fresh full Session/Chromium twice, lint/build; Windows backend full known Bash
   exception reproduced, Master read proof1, public Compose. Inspect desktop/mobile
   screenshots and interact via Playwright skill CLI where useful.
7. Portfolio problem/decision/failure/verification/result/risks, current-work,
   canonical status and prior merge evidence. Do not claim actual OAuth/live UI.
8. Ready PR, final-head verify and both Scan/SBOM SUCCESS, protected squash
   auto-merge confirmed MERGED, Issue148 closed/main sync; parent137 remains open.

Each Todo focused tests/diff --check/status/staged/cumulative path inspection,
small commits. F1 scope9/migration0, F2 security/precision/replay/UX, F3 fresh
tests/screenshot inspection/cleanup0/CI, F4 truthful records/protected delivery
must all APPROVE. Path/time limits cannot be silently relaxed.

## Commands and limits

Frontend npm run lint/build/test:auth/test:auth:browser each180s; focused
`npx playwright test --project=session master-model.spec.ts`120s and
`npx playwright test --project=chromium master-ux.spec.ts`180s.
Full Session/Chromium twice. Browser calls local intercepted mock only.
Backend AI_PROVIDER=mock `python -m pytest -q`300s; known Windows Bash127 failure
preserved, Linux CI required. Root public Compose config60s and
`python scripts/verify_master_read.py --env-file .env.example`180s work/60s
cleanup,8 groups/3 interleavings/100checks minimum. No edits during proof.
All owned proof resources removed; developer/preview projects untouched.
