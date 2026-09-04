# G6 Gemini Prompt Enhancement Credit Integration

Status: **Mock Verified locally at `87dca6b`; Ready PR delivery pending**

Issue: [#124](https://github.com/bbungjun/AI_multimodal_platform/issues/124)

Branch: `codex/issue-124-gemini-credit-integration`

Base: merged G5C2 squash `5e56ecb`

## 1. Problem and bounded outcome

The authenticated Prompt Enhancement endpoint currently calls Gemini and stores
the result without reserving or consuming the User's monthly credit. G5C2 now
provides atomic `reserve`, `settle`, and `release`, but intentionally has no
product caller. G6 closes that gap for Prompt Enhancement only.

After G6, a valid request has one durable attempt identity and follows this
observable sequence:

1. validate and derive a bounded worst-case Gemini token envelope;
2. commit a credit Reservation before any provider invocation;
3. refuse insufficient balance with `402 monthly_credit_exhausted` and zero
   provider calls;
4. invoke the existing enhancer in `AI_PROVIDER=mock` during verification;
5. atomically store the owned `PromptEnhancement` and settle observed Usage;
6. release the entire hold when no deliverable is returned.

G6 is not Imagen/Veo generation billing, a personal Usage UI, live GCP
verification, or abandoned-hold reconciliation.

## 2. Deep module and seam placement

Add one `prompt_credit` Module. Its small Interface accepts the caller-owned
`AsyncSession`, authenticated actor and validated Prompt Enhancement request,
and returns a completed Prompt Enhancement result. The Implementation owns:

- operation-key derivation from `request_id`;
- reserve/provider/terminal transaction ordering;
- composition with the G5 accounting Interface;
- persisted-result replay and collision checks;
- conversion of provider outcomes to fixed release reasons;
- safe product error codes without prompt, identity, SQL or credential text.

The HTTP route remains a thin adapter: authentication and Pydantic validation,
one call through the Module Interface, fixed error-to-status mapping, and response
serialization. The existing enhancer remains the true-external provider adapter
seam. Tests replace that adapter internally; the Module Interface does not expose
credit grant, ledger, lock, retry or provider-client details.

The deletion test justifies the Module: deleting it would redistribute three
transaction phases, two idempotency namespaces, token-envelope policy, replay
rules and error mapping into the route and provider adapter.

## 3. Request identity and idempotency

`PromptEnhanceRequest` gains required UUID `request_id`. The frontend creates it
once when the User presses Enhance and sends it in the request body. A transport
or proxy replay of the same body therefore preserves the same identity.

- `PromptEnhancement.id == request_id`.
- Reserve key: `pe_r_<32 lowercase UUID hex>`.
- Terminal key: `pe_t_<32 lowercase UUID hex>`.
- Same owner, request ID and normalized business payload after success returns
  the stored result without another provider call or charge.
- Reusing the ID with changed prompt, mode, target model or creativity is
  `credit_idempotency_conflict`.
- A replay that observes a held Reservation but no result is
  `prompt_enhancement_in_progress`; it does not duplicate the provider call.
- A replay of a released attempt is `prompt_enhancement_terminal` and requires a
  new request ID.
- Another owner's ID is indistinguishable from missing and must not expose the
  other owner or object.

Concurrent identical requests are serialized by G5's Reservation key. Only the
winner with `replayed=false` may cross the provider seam. This prevents duplicate
provider spend. A process crash after reserve and before terminal may leave a
held row; G6 fails it closed as in-progress. Automatic lease/reconciliation is a
separate operations Goal because guessing terminal outcome could double-charge
or make consumed provider work free.

## 4. Token envelope and Usage policy

Meters are exactly `gemini_input_token` and `gemini_output_token`. G6 never reads
Google price data; G5 Rate Card V1 converts units to internal microcredits.

The enhancer exposes a deterministic immutable preflight envelope for the exact
prompt templates and configured hard output limits it may use. Validation repair
can make at most three response-bearing calls. The maximum envelope covers the
larger of the permitted base/strict/contract and base/language paths, while each
call's output is capped by `PROMPT_ENHANCEMENT_MAX_OUTPUT_TOKENS`. This keeps all
observable successful usage within the Reservation or fails closed with the G5
contract-violation error.

For local mock, deterministic token units are derived by the same helper used by
preflight, and the result source is `mock_estimate`. For Vertex-capable code, all
available response `usage_metadata` from response-bearing validation attempts is
summed, not just the final response. Both token counts must be finite,
nonnegative integers. Missing metadata may use the documented conservative local
measurement with source `platform_measured`; raw provider payloads are never
persisted. Provider transport failures without a response do not invent usage.

Successful delivery settles both meter lines using observed units. At least one
line must produce a positive internal charge. A result that cannot be persisted
is not a deliverable and must not be presented as completed. Provider failure,
timeout, rate limiting or invalid response releases the full hold; any safely
known attempt units may be stored as non-charged Usage evidence.

The earlier G5 phrase “exact known input tokens plus hard maximum output tokens”
is interpreted at the product seam as the complete deterministic preflight
envelope for every response-bearing retry path, not only the first call. This is
necessary to keep retry behavior inside the held maximum.

## 5. Transaction and failure matrix

No database transaction or row lock remains open across provider I/O.

| Phase/outcome | Database action | Provider action | Public result |
|---|---|---|---|
| Invalid HTTP input | none | none | existing `422` |
| Insufficient credit/Plan denial | reserve transaction rolls back | none | fixed `402`/`403` |
| New admitted attempt | reserve transaction commits | one enhancer execution | continue |
| Duplicate held attempt | read/replay only | none | `409 prompt_enhancement_in_progress` |
| Provider success | Prompt Enhancement insert + `settle` in one transaction | already complete | `201` |
| Provider rate limit/timeout/failure/invalid response | `release` in a fresh transaction | no more calls | existing safe `502/503` |
| Result persistence or settle failure | success transaction rolls back together; best-effort release in a clean transaction when safe | no retry in request | fixed safe failure |
| Completed identical replay | verify stored result and terminal state | none | original `201` body |

The Module must not call commit or rollback inside G5. It owns only the three
outer transaction scopes needed by this product flow. A caught expected failure
must leave the request session usable. Database failure during best-effort release
is logged only with fixed codes; no false success is returned.

## 6. Error contract

G6 preserves existing Vertex public errors and adds fixed mappings:

| HTTP | Code | Meaning |
|---:|---|---|
| 402 | `monthly_credit_exhausted` | Reservation cannot be funded |
| 403 | `plan_feature_not_allowed` | Current Plan disallows the meter |
| 409 | `credit_idempotency_conflict` | Same request ID, changed business payload |
| 409 | `prompt_enhancement_in_progress` | Durable hold exists without terminal result |
| 409 | `prompt_enhancement_terminal` | Attempt was already released |
| 503 | `credit_busy` | Contended accounting operation may be retried |
| 503 | `credit_account_unavailable` | Safe generic accounting/integrity failure |

No error contains a User ID, email, prompt, model payload, SQL, grant balance,
credential or provider raw response.

## 7. Exact execution scope

Migration count is exactly zero. G6 may change exactly these 14 non-document
paths and no others:

```text
backend/app/prompt_credit.py
backend/app/api/prompts.py
backend/app/schemas.py
backend/app/services/llm/enhancer.py
backend/tests/test_prompt_credit.py
backend/tests/prompt_credit_support.py
backend/tests/test_prompt_api.py
backend/tests/test_prompt_enhancer.py
backend/tests/test_verify_prompt_credit_script.py
scripts/verify_prompt_credit.py
scripts/verify_ownership.py
scripts/smoke_mock_golden_path.py
frontend/src/api/types.ts
frontend/src/pages/GeneratePage.tsx
```

This list is both the allowlist and expected implementation set. A fifteenth
non-document path, any migration, or a required edit to G5 accounting/lifecycle,
Job, Asset, Outbox, worker, state machine or pipeline means STOP and redesign.

Allowed documents are this spec, the canonical initiative, current-work,
testing, local-mock runbook, portfolio index and Issue #124 portfolio record.
`.omo` remains local and must never be staged wholesale.

### Approved v2 path correction

Todo1 RED exposed that requiring `request_id` would break two real inherited
callers outside the v1 allowlist: the ownership verifier's direct Prompt request
and the golden-path Prompt request it invokes. Continuing v1 would therefore make
its own mandatory compatibility gate impossible. The approved v2 keeps the exact
14-path total and all product policy unchanged:

- replace `backend/tests/test_mock_provider.py`; its mock token assertions move
  into `backend/tests/test_prompt_enhancer.py`;
- replace `backend/tests/test_prompt_credit_support.py`; support/parser safety is
  exercised through `backend/tests/test_verify_prompt_credit_script.py` and both
  real verifier cycles;
- add `scripts/verify_ownership.py` and `scripts/smoke_mock_golden_path.py` so
  their authenticated Prompt payloads carry deterministic UUID request identities.

The original Goal and failing RED record remain preserved. Execution resumes only
under the v2 Goal overlay and its distinct SHA-256.

## 8. Verification contract

The focused proof groups are:

- **P1 Preflight:** deterministic request identity, all retry-path envelopes,
  mock non-null usage, metadata aggregation, maximum and overflow guards.
- **P2 Admission:** new account lazy initialization, Free/Pro/Max/Master,
  exact exhaustion, zero provider calls on rejection, safe error mapping.
- **P3 Terminal:** delivered settlement, provider failure/timeout/rate-limit and
  invalid-response release, persistence/settle rollback, original units/source.
- **P4 Replay/race:** completed equal replay, changed-payload conflict, held and
  released replay, cross-owner non-leakage, two concurrent identical requests
  with exactly one provider crossing and one charge.

`scripts/verify_prompt_credit.py` must use a fresh isolated PostgreSQL project,
assert schema head `0006_credit_accounting_persistence`, force
`AI_PROVIDER=mock`, emit a bounded JSON receipt only, enforce per-phase timeouts
and prove exact container/volume/network cleanup. Run two independent cycles;
each must report all four groups, at least one observed concurrency race, a
fixed minimum check count and resources zero.

Compatibility gates are one accounting cycle, lifecycle cycle, auth
PostgreSQL/Redis cycle, ownership `--suite all --cycles 2`, full Linux backend,
the known Windows/base exception check, Compose config, frontend lint/build and
existing Session/Chromium tests. Development and preview databases/volumes are
never reset or used for destructive proof.

## 9. Todo and completion gates

Execution is sequential and commits in small units:

1. freeze baseline, hash, path/migration guards and focused RED tests;
2. implement preflight envelope and deterministic/aggregated Usage;
3. implement the `prompt_credit` Module's admission and replay Interface;
4. implement atomic success persistence/settlement and route mapping;
5. implement release/failure and concurrency/idempotency cases;
6. add the isolated verifier and its parser/cleanup safety tests;
7. run focused, isolated and full compatibility verification;
8. document problem/cause/decision/failures/results/risks, create Ready PR and
   confirm protected squash merge after required CI and both Scan/SBOM checks.

Final reviewers must all return APPROVE:

- **F1 Scope/architecture:** exact14, migration0, one deep Module, no G7 creep.
- **F2 Accounting/security:** pre-provider admission, atomic terminal behavior,
  idempotency, ownership non-leakage and safe evidence.
- **F3 Verification/operations:** two isolated cycles, all regressions, time
  budgets, cleanup0 and truthful Mock/Live labels.
- **F4 Delivery:** documentation consistent, Ready PR final-head required CI and
  backend/frontend Scan/SBOM success, auto-merge enabled and actual squash
  `MERGED` without bypass or administrator force.

## 10. Rollback and next handoff

Rollback is a reviewed code revert. There is no schema downgrade. Already written
reservations, Usage and Prompt Enhancements are append-only evidence and must not
be deleted to simulate rollback. If a held attempt remains, keep it and record it
for the later reconciler rather than fabricating a terminal result.

After actual merge, G7 may consume only the established G5 accounting Interface
and G6 token-envelope/terminal lessons. G7 still owns Job/Outbox/worker/state/
Asset and pipeline semantics. A separate cost-bounded GCP Goal must calibrate and
Live Verify Vertex usage metadata before any production billing claim.

## 11. Local implementation evidence

The final local code changes exactly the approved14 paths and no migration. Two
isolated PostgreSQL projects at head0006 each passed the four fixed groups,35
checks, one race and zero residual resources. Accounting/lifecycle/auth and
ownership `--suite all --cycles 2` passed; ownership completed four cycles in
1006.641s with cleanup0. Tracked-only Linux passed1461 tests with three guarded
skips. Windows passed1460 with the inherited Bash native127 failure reproduced at
untouched base. Compose and frontend lint/build/Session48/Chromium34 passed.

This is mock verification, not Vertex usage or GCP billing evidence. Held-request
reconciliation, Imagen/Veo charging, Usage UI and live GCP remain later Goals.
