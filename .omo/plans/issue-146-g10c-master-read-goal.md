# Issue146 G10C Goal

Read AGENTS,current-work,canonical Master policy,G10 specification and
docs/initiatives/g10c-master-read-spec.md fully. Branch
codex/issue-146-master-operational-read. Sequential/no subagents, mock/local only.

## Exact paths, maximum9; no migration

1. backend/app/master_read.py
2. backend/app/api/master.py
3. backend/tests/test_master_read.py
4. backend/tests/test_master_read_api.py
5. backend/tests/master_read_support.py
6. backend/tests/test_master_read_support.py
7. scripts/verify_master_read.py
8. backend/tests/test_verify_master_read_script.py
9. backend/tests/test_master_api.py (affected adapter compatibility only)

No writer/lifecycle/model/provider/frontend change; no developer/preview DB
mutation. No broad .omo staging, raw errors/SQL/PII/prompt/credentials evidence.
Read contract is the slice spec: snapshot read-only, no lazy writes, strict safe
output, integer decimal strings, bounded windows/keyset pages and no invented
model attribution or admission metrics. Unknown query fields refused.

## Todo1–8

1. Verify SHA; baseline focused Master tests, record Issue/branch In Progress.
2. Pure safe projection/serialization/cursor Interface tests and implementation.
3. Read-only snapshot aggregate/user/Audit queries and actor recheck.
4. GET HTTP Adapter, bounds/privacy/auth/cache tests; no mutation regression.
5. Isolated PostgreSQL proof8 groups/100 checks/3 event-gated MVCC interleavings,
   guarded harness and refusal tests. Counts are evidence, not source assertions.
6. Stable committed proof twice, inherited master-admin once, full backend,
   frontend lint/build/Session/Chromium and public Compose. No edits during proof.
7. Portfolio problem/cause/failed approaches/solution/verification/result/risks;
   current-work and canonical latest status, previous G10B merge evidence.
8. Ready PR, final-head verify and both Scan/SBOM success, protected squash
   auto-merge and actual MERGED; Issue146 closed/main sync. Parent137 stays open.

Each Todo focused tests, diff --check/status/staged inspection and cumulative
allowlist, small exact-path commits. F1 scope9/migration0, F2 read coherence/
security/privacy, F3 fresh proofs/regressions/cleanup0/CI, F4 documentation and
protected delivery must all APPROVE. Do not relax path/time gates; redesign first.

## Verification commands and budgets

Backend AI_PROVIDER=mock:
`python -m pytest tests/test_master_read.py tests/test_master_read_api.py
tests/test_master_read_support.py tests/test_verify_master_read_script.py
tests/test_master_admin.py tests/test_master_api.py -q` <=120s (existing subset
while constructing). `python -m pytest -q` <=300s; known Windows Bash127 exception
preserved, mandatory fresh Linux CI. Public Compose config <=60s.
Root `python scripts/verify_master_read.py --env-file .env.example` twice;
each work180s/cleanup60s,8 groups (guards,users,cycles,credits,jobs,audit,privacy,
snapshot),3 interleavings/100 checks minimum, cleanup0.
Root `python scripts/verify_master_admin.py --env-file .env.example` once180/60.
Frontend npm run lint/build/test:auth/test:auth:browser each<=180s.
No actual OAuth/provider/cloud. Proof timeout preserved and stops for redesign.
