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
print exception repr, response body or identity. Diagnosis remains open.

## Verification status

In Progress. No complete/mock-verified claim until fresh independent cycles and
the frozen regression matrix pass. No actual Google, browser/backend live,
provider/cloud, real account mutation or developer DB modification authorized.

## Rollback and remaining risks

Changes are test-only. Remove the new coordinator to revert; existing product,
schema and proof commands remain unchanged. The existing owned runtime supplies
local mock Sessions without an OAuth call; this is not proof of Google login.
