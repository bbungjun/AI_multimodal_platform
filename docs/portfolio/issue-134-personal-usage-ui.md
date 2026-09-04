# Issue #134 — Personal Plan and Usage workspace UI

Evidence level: **UI Mock Verified locally**. Final delivery is complete only
after the linked Ready PR passes final-head CI and protected squash merge. This
record does not claim live OAuth, Vertex usage, an external invoice or provider
model attribution.

## Background and problem

G5–G8 already enforced durable Credit and concurrency rules, and G9A exposed one
authenticated snapshot. Users still had no workspace view answering which Plan
is active, when their exact 30-day period renews, how much Credit is available or
held, and which billing meters produced internal charges. That made a real cost
control feature operationally invisible.

## Observation and rejected approaches

The API deliberately exposes seven stable billing meters rather than an exact
provider model for every record. Joining frontend requests across Credit,
Reservation and Usage endpoints would duplicate lifecycle and consistency logic.
Inferring model names from prompts or Job metadata would fabricate billing
precision. Historical charts, currency conversion and an upgrade button were
also rejected because the API provides neither history nor payment controls.

## Solution and design rationale

One deep `ui/usage` Module validates the complete unknown JSON boundary and
builds a presentation model. It owns exact field allowlists, seven-meter order,
safe integers, ISO cycle ordering, microcredit/unit formatting and clamped
cycle/allowance/concurrency ratios. The API Adapter remains one owner-only
`GET /api/usage/me` call and inherits same-origin credentials, Session epoch
rejection and 401 handling.

The `/usage` page reuses the existing shell, Panel, Badge, button, color and
typography vocabulary. It distinguishes all usable Credit from base allowance,
held reservations from settled charges, and observed provider units from
internal Credit. Pending downgrade is explicitly shown as next-cycle state.
There is no polling; manual refresh preserves current data and is single-flight.

## Verification

- parser/presentation plus original Session project: **60 passed**;
- Chromium plus original authenticated UX: **47 passed**;
- new browser coverage: success, private loading, four bounded failures, retry,
  refresh, 401, old-account epoch and four responsive widths;
- 1440 and320 privacy-masked local captures visually reviewed with no horizontal
  overflow; narrow meter rows retain explicit labels;
- frontend lint/build and Compose config: pass;
- focused G9A/auth backend: **67 passed / 2 guarded skips**;
- unchanged full Windows backend: **1588 passed / 3 guarded skips**, with only
  the documented Bash absolute-path exception reproduced;
- latest tracked-only Linux baseline from the immediately preceding merged
  Issue99: **1589 passed / 3 guarded skips**; final Linux runs again in CI.

No retries, new skips, backend modifications or schema changes were introduced.

## Result and impact

An authenticated User can now understand current Plan, renewal, available/held/
charged Credit, request-slot pressure and all seven truthful billing meters in
the same workspace used for generation. Malformed or expanded payloads fail
closed without exposing raw data. Session changes discard the per-account query
cache and late responses cannot render into the next account.

## Remaining risks and next step

- Values are mock-backed local UI evidence until live OAuth/Vertex verification.
- The page is not a provider invoice and does not attribute exact models.
- Plan changes, payment, bonus administration and Master/Audit remain G10 or a
  later commercial slice.
- Final-head `verify` and both Scan/SBOM checks, protected merge, Issue closure
  and synchronized main must be linked before marking G9 complete.
