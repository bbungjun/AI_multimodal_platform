# Issue153 G11A integrated mock acceptance

## Problem and hypothesis

G1-G10 isolated proofs do not alone demonstrate a continuous User-generation-
accounting-Master workflow over real HTTP. G11A adds that verification without
changing product contracts. Parent152 retains separately authorized live gates.

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

## Stop and redesign proposal

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

Needs redesign approval. Focused19 PASS; integration failed with cleanup0.
No complete/mock-verified claim until fresh independent cycles and
the frozen regression matrix pass. No actual Google, browser/backend live,
provider/cloud, real account mutation or developer DB modification authorized.

## Rollback and remaining risks

Changes are test-only. Remove the new coordinator to revert; existing product,
schema and proof commands remain unchanged. The existing owned runtime supplies
local mock Sessions without an OAuth call; this is not proof of Google login.
