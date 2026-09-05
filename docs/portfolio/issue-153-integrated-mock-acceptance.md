# Issue153 G11A integrated mock acceptance

## Problem and hypothesis

G1-G10 isolated proofs do not alone demonstrate a continuous User-generation-
accounting-Master workflow over real HTTP. G11A adds that verification and fixes
the discovered auth error-cache gap. Parent152 retains separately authorized live gates.

## First failed approach

Core12d96a2, first owned cycle: identity group failed, auth12 checks passed;
work22.843s/cleanup6.594s, zero remaining resources. The test incorrectly required
`private` for `/api/auth/me`, whose established contract is `no-store`.
Content/Usage/Master require `private, no-store`. Fix the test's contract mapping,
not the application or its protection. Added focused cache-mapping regression.
Original bounded receipt remains under `.omo/evidence/issue-153/`.

Core89c9d6f reached suspension after identity/usage/prompt/generation/admin/
concurrency, then failed; work29.656s/cleanup5.235s, cleanup0. Add only a bounded
HTTP-status/error-code and completed-check count to locate the failure; never
print exception repr, response body or identity.

Core92fee38 reproduced suspension-group failure after97 successful assertions:
work30.156s/cleanup5.094s, cleanup0. The failed assertion is the cache header on
`GET /api/auth/me` returning401 after suspension/reactivation. Session revocation
works; the error response lacks `Cache-Control: no-store`. `require_user` raises
HTTPException before the endpoint's success-only header assignment. The outer
PrivateContentResponses middleware does not cover `/api/auth`. An independent
FastAPI router/real require_user check with a rejecting AuthService Adapter also
returned status401/cache_control_present=false; no actual credentials or DB used.

## Preserved stop and redesign proposal

The original exact2 test-only scope cannot fix product headers. Stop before any
third code path; do not weaken no-store verification or declare success. Proposed
v2 adds only backend/app/main.py and backend/tests/test_auth_api.py (total4 paths,
migration0). At the existing outer response-start wrapper, cover `/api/auth`
with `no-store` for success/error/redirect responses, preserving existing content
`private, no-store`, streaming, Set-Cookie and Origin behavior. Add anonymous,
revoked/suspended401,503 and callback/redirect cache regressions. Then run original
two-cycle integration and full frozen matrix unchanged. Approval is required
before applying this product fix. No Ready PR/merge until all gates pass.

## Verification status

User approved resumption with total4 paths. Original plan SHA confirmed unchanged.
v2 plan SHA256 cba354c4e78e68e4561bba89160da614c8e249ba8bda8e848e7066250063e6f0.
Final implementation core **ebbfc76**. Auth response-start wrapper now covers
all `/api/auth` statuses with no-store, outside the error middleware. Only the
cache header is replaced; cookies, status, streaming and Origin behavior remain.
No-store protects both browser and shared caches; existing content routes keep
private/no-store. A global cache policy was rejected because unrelated public
health responses are outside this change. No dependency rewrite or schema change.

### Fresh local mock results

All commands run from repo root with `--env-file .env.example`, except the new
integration coordinator (no arguments). Work/cleanup durations are seconds.
Receipts retain their original `.omo/evidence/issue-*/` locations; the table is
the durable sanitized summary, not a claim of cloud/provider measurements.

| Command (`python scripts/…`) | Checks / races | Work / cleanup | Result |
| --- | --- | --- | --- |
| verify_integrated_acceptance.py cycle1 | 8 groups,108 checks | 53.844 / 5.093 | PASS |
| same cycle2 | 8 groups,108 checks | 29.438 / 4.953 | PASS |
| verify_schema_migrations.py run1 | credit90, accounting42, downgrade4 | 146.969 / 1.953 | PASS |
| same run2 | credit90, accounting42, downgrade4 | 151.562 / 1.985 | PASS |
| verify_credit_lifecycle.py | 320 / 8 | 16.234 / 2.766 | PASS |
| verify_credit_accounting.py | 299 / 8 | 16.015 / 2.985 | PASS |
| verify_concurrency.py | 259 / 6; fifty simultaneous admissions | 22.796 / 2.891 | PASS |
| verify_prompt_credit.py | 35 / 1 | 16.031 / 2.734 | PASS |
| verify_generation_credit.py | 120 / 2 | 15.328 / 2.891 | PASS |
| verify_personal_usage.py | 451 / 3 | 15.734 / 2.766 | PASS |
| verify_master_admin.py | 85 / 4 | 16.437 / 2.797 | PASS |
| verify_master_read.py | 112 / 3 | 15.859 / 2.860 | PASS |
| verify_master_suspension.py | 112 / 4 | 17.875 / 2.906 | PASS |

Auth `verify_auth_sessions.py --env-file .env.example`: PostgreSQL/Redis and
Redis outage/recovery PASS. Auth requests50, p95 10.623ms; concurrent touch20
with one effective write, flow consume12 with one consumption. Local fixture
latency only. Guarded DB/Redis tests skipped in generic pytest were exercised here.

`verify_ownership.py --env-file .env.example --suite all --cycles 2` completed
all four cycles, aggregate584.781s/1800s budget:

- Ownership: each metadata348/eight groups, admission111, worker20, pipeline4,
  HTTP races3, expiry1, deletion races2. Work203.922/264.782, cleanup7.234/7.031.
- File-ops: each310/four groups, two actors each complete all ten E2E stages.
  Work44.141/43.329, cleanup6.765/6.718. Actual mock golden path and retry included.
- Every receipt cleanup passed. Fresh Docker label inventory across all18
  proof projects found containers/volumes/networks remaining **0**.

Backend `AI_PROVIDER=mock python -m pytest -q`: Windows1788 PASS, three guarded
integration skips and exactly the existing `test_supply_chain_release` Bash127
path failure. This is not a fully passing Windows suite; no skip was added to
hide it. Full Linux pytest is required in final-head CI before protected merge.
Focused auth/integration51 PASS/one guarded skip. Frontend `npm run lint`,
`npm run build`, `npm run test:auth`70 and `npm run test:auth:browser`61 PASS.
Chromium31.6s; response-fixture UI contracts, not a Google login or live UI/API flow.
Public Compose config and git diff --check PASS.

### Outcome and delivery gate

Previously an authenticated-session error could be returned without a no-store
instruction; now all auth responses carry it. Real mock HTTP flow verifies
generation/Usage changes, exact replay, Plan/bonus, concurrency rejection,
unpublished cancellation, Session revocation/reactivation and exactly four Audit
records without replay duplicates. All frozen local limits were retained.

F1 scope4/migration0 and F2 behavior APPROVE. Local F3 checks pass with the
documented Windows exception; final Linux CI and F4 protected delivery are
recorded on [Issue153](https://github.com/bbungjun/AI_multimodal_platform/issues/153)
and its linked PR. Parent152 remains open. No actual Google, browser/backend live,
provider/cloud, real account mutation or developer DB modification performed.

## Rollback and remaining risks

The approved product delta is only auth response cache protection; a reviewed
revert would reopen this gap and is not the preferred recovery. No data rollback
or migration is needed. The test-only coordinator can be removed independently.
The existing owned runtime supplies local mock Sessions without an OAuth call;
this is not proof of Google login. Full initiative completion still needs the
separately authorized real Master/User browser smoke, emergency revocation drill
and proxy checks. No actual provider pricing/throughput result is inferred.
