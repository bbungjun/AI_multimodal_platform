# G9B Personal Plan and Usage UI Specification

Status: **Accepted / Execution Prepared**, 2026-09-05. Issue
[#134](https://github.com/bbungjun/AI_multimodal_platform/issues/134) consumes
the merged G9A Interface without changing backend accounting behavior.

## Problem and outcome

Users can create charged AI work but cannot inspect their Plan, 30-day cycle,
Credit or request limit in the workspace. G9A already owns lifecycle and
aggregation semantics behind `GET /api/usage/me`; reproducing them in React
would create a shallow UI coupled to persistence details.

G9B adds one authenticated `/usage` route in the existing shell. It answers four
user questions: which Plan is active, when it renews, how much Credit is
available/held/charged, and which billing meters contributed observed units and
charges. It does not add purchase or Plan controls.

## Deep frontend Module and Interface

`src/ui/usage.ts` owns the frontend boundary:

```text
parsePersonalUsage(unknown) -> PersonalUsageSnapshot
buildPersonalUsageView(snapshot, now) -> PersonalUsageView
```

The parser validates the exact G9A allowlist, enums, seven-meter order, safe
integers, non-negative amounts, ISO instants and cycle ordering. Unknown/missing
fields or impossible values fail closed as `usage_response_invalid`; raw payloads
are never placed in errors. The view operation owns Korean labels, integer-only
microcredit formatting, unit formatting, clamped cycle/credit/concurrency ratios,
exact renewal text and pending downgrade presentation.

The HTTP Adapter adds only `getPersonalUsage()`. Existing `apiRequest` supplies
same-origin credentials, Session epoch rejection and 401 invalidation. React
Query caches by the stable `personal-usage` key inside the per-Session QueryClient,
does not poll, retries only through an explicit button and exposes background
refresh without replacing existing data.

The deletion test favors this Module: removing it would duplicate validation,
meter vocabulary, ratios and formatting across the API Adapter, page and tests.

## Page information architecture

- hero: Plan badge, exact cycle start/renewal and manual refresh state;
- Credit panel: all usable Credit, held Credit, current-cycle charged amount and
  a clearly labelled base allowance ratio (bonus is not inferred);
- concurrency panel: active top-level requests versus Free1/Pro3/Max5 contract;
- billing-meter table/cards: the seven fixed G9A meters in order with observed
  units and charged microcredits;
- pending Plan: visible as a next-cycle change, never presented as active;
- states: stable skeleton/status, bounded 503/invalid response alert and retry.

There is no chart suggesting history, currency conversion, invoice, external
provider bill, exact model attribution, Plan upgrade button or Master view.

## UX and accessibility

Reuse `creative-page`, hero, Panel, Badge, button, color and typography rules.
Add Usage-specific CSS only. The page must have one `h1`, semantic definition
data/table labels, native or ARIA progress values and focus-visible retry/refresh.
At 1440/920/390/320 widths content has no horizontal viewport overflow; the
meter table becomes labelled stacked rows on narrow screens. Reduced motion is
respected by the existing shell.

Korean copy distinguishes:

- `사용 가능 크레딧`: all currently usable base plus bonus Credit;
- `주기 기본 한도 대비 사용`: charged / base allowance only;
- `처리 중 예약`: held Credit;
- `관측 사용량`: retained provider units, including no-deliverable attempts;
- `차감 크레딧`: internal settled charge, not a provider invoice.

## Failure and privacy contract

- loading mounts no stale previous-account values;
- 401 continues through the existing Session guard and removes private UI;
- 503 `usage_busy` and `usage_unavailable`, network failure and invalid payload
  show bounded Korean messages without raw response/SQL/identity;
- manual retry issues one request and keeps controls disabled while pending;
- a late response from an old Session epoch cannot render in the next account;
- no email, User ID, operation key, prompt, Session/OAuth or provider raw data is
  displayed or written to evidence.

## Verification

Focused Module tests prove exact response parsing, seven meters, integer
formatting, boundary ratios, cycle dates, pending Plan and safe failures. Browser
tests mock only G9A/auth/health and prove success, loading, four bounded failure
classes, refresh deduplication, 401 Session transition, account epoch isolation,
keyboard semantics and 1440/920/390/320 overflow/accessibility.

Run frontend lint/build and the expanded Session/Chromium projects, Compose and
full backend regression. Final-head `verify` and both Scan/SBOM jobs remain
required. Evidence is UI Mock Verified only.

## Exact implementation boundary

Exactly these 11 non-document paths may change:

1. `frontend/src/App.tsx`
2. `frontend/src/api/client.ts`
3. `frontend/src/api/types.ts`
4. `frontend/src/ui/copy.ts`
5. `frontend/src/ui/usage.ts`
6. `frontend/src/pages/UsagePage.tsx`
7. `frontend/src/index.css`
8. `frontend/tests/auth-fixtures.ts`
9. `frontend/tests/usage-model.spec.ts`
10. `frontend/tests/usage-ux.spec.ts`
11. `frontend/playwright.config.ts`

Migration/backend changes, a 12th non-document path or a second feature Module
are STOP-and-redesign. Permitted docs are this spec, the canonical initiative,
current-work, testing, portfolio index and Issue134 portfolio record.

## Completion

Ready PR closing #134, final required CI, protected squash auto-merge, Issue
closure and synchronized local main. G9 completes only as Mock Verified; G10 and
all live OAuth/provider/cloud work remain separate.
