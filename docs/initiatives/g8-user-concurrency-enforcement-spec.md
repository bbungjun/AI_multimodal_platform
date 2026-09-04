# G8 — Atomic per-User request concurrency specification

## 1. Problem and outcome

G6 and G7 reserve Credit before Prompt Enhancement, Imagen, Veo and pipeline
execution, but `PlanPolicy.max_concurrent_requests` is not enforced. A burst from
one User can therefore consume every worker/provider slot even though Free, Pro
and Max promise limits of one, three and five top-level requests.

G8 deepens the existing `credit_accounting` Module rather than adding a Redis
semaphore or a second lifecycle. A held `CreditReservation` is the durable
top-level concurrency slot. The same PostgreSQL User lock already used by
`reserve`, `settle` and `release` serializes slot acquisition and return.

## 2. Scope and exclusions

Included:

- atomic Free1, Pro3 and Max5 admission for one User;
- Master uses Max5 and receives no bypass;
- Prompt Enhancement, standalone Imagen/Veo, retry and pipeline admission;
- one pipeline reservation equals one top-level slot despite two Jobs;
- slot return on both settlement and release;
- same-operation replay at a full limit without a second slot;
- public HTTP429 with fixed code `user_concurrency_limit`;
- real isolated PostgreSQL races and inherited mock regressions.

Excluded:

- Redis locks, process-local semaphores or worker-global concurrency changes;
- a new lease table, Job schema change or any migration;
- G9 Plan/Usage UI, G10 Master mutation/Audit, payment or operator repair;
- abandoned-held-reservation sweeper or automatic timeout reconciliation;
- real OAuth, Vertex/provider/cloud, GCP, Kubernetes or Terraform execution.

Every runtime proof uses local Docker with `AI_PROVIDER=mock`. Development and
preview databases and volumes are never reset or adopted.

## 3. Deep Module Interface and seam

The external Interface remains the existing caller-owned transaction operation:

```python
reserve(session, *, request: ReservationRequest, now: datetime) -> ReservationReceipt
```

Callers learn no new lease Interface and terminal callers require no new release
operation. The Implementation counts held reservations after locking the User and
resolving the current Plan. `settle` and `release` already change a reservation
out of `held`, so terminal accounting returns the slot in the same commit as
Usage/Credit mutation.

The deletion test favors this design: removing the Module would force prompt,
generation, retry and pipeline callers to reproduce locking, plan lookup, replay
ordering, counting and error policy. Keeping it here provides locality and one
real PostgreSQL seam for every product adapter.

## 4. Ordering and atomicity contract

Within one caller transaction, a new reserve attempt follows this order:

1. validate the request and lock the owning User;
2. find the same `(user_id, operation_key)` reservation;
3. if present, validate the stored estimate and return replay without consuming
   another slot, even when the Plan is currently full;
4. ensure the current Credit cycle and lock the Credit account/grants;
5. reject suspended/unknown Plan or disallowed meter/shape;
6. count the User's `status='held'` reservations under the same serialization
   lock and reject when count is at least the Plan limit;
7. quote and allocate available Credit;
8. insert the held reservation and let the caller atomically persist its
   Prompt/Job/Outbox state.

Every reserve/settle/release path locks the same User first. Concurrent new
admissions therefore cannot both observe the same free final slot. Terminal-vs-
admission races may conservatively reject if the terminal transaction has not
committed yet, but they never oversubscribe; retrying after commit succeeds.

Public failure precedence is:

1. request/identity and suspended-account refusal;
2. idempotent replay/conflict;
3. Plan feature refusal;
4. `user_concurrency_limit`;
5. `monthly_credit_exhausted`;
6. bounded lock/account failures.

## 5. Slot semantics

All current production reservations are billable top-level product attempts and
therefore occupy one slot while held. No operation-key prefix is parsed to infer
product kind.

| Flow | Slot acquired | Slot returned |
| --- | --- | --- |
| Prompt Enhancement | before provider call | prompt settle or release |
| Standalone Imagen/Veo | Job/Outbox admission | worker settle or release |
| Manual retry | new retry Job admission | retry terminal accounting |
| T2I-to-I2V pipeline | once on parent reservation | child combined/partial terminal or parent release |
| Queue replay | no new slot | no duplicate terminal mutation |

An abandoned held reservation continues to occupy both Credit and concurrency.
This is deliberately fail closed. A sweeper needs its own expiry, provider-state
and operator-repair policy and remains a later Goal.

## 6. Error and privacy contract

`credit_accounting` raises `CreditAccountingError('user_concurrency_limit')`.
Prompt and generation adapters preserve that fixed code; public endpoints map it
to HTTP429. A concurrency refusal must leave no new reservation, Prompt
Enhancement, Job or Outbox and must produce zero provider calls.

No response exposes active counts, another User's state, email, prompt, OAuth
data, credential or provider payload. Evidence records only synthetic identifiers,
plan labels, bounded counts, safe codes and timing.

## 7. Verification contract

The G8 verifier owns one disposable Compose project and fresh PostgreSQL volume,
forces mock mode, upgrades to head0006 and runs two independent cycles. Each
cycle proves eight groups:

1. Plan limits Free1/Pro3/Max5/Master5 and error precedence;
2. sequential fill, exact next refusal and no persistence side effect;
3. settle and release each return a slot;
4. same-operation replay at capacity remains one reservation;
5. at least50 same-User concurrent admissions never exceed the Plan limit;
6. separate Users progress independently under concurrent load;
7. Prompt, generation, retry and pipeline public HTTP429/provider-zero behavior;
8. rollback, lock contention, abandoned hold and terminal-vs-admission fail-closed
   behavior.

Each cycle reports all groups, at least six observed races, at least180 checks,
the exact code revision/schema head and container/volume/network cleanup zero.
Both cycles must pass at the same committed SHA.

Inherited gates run after the two G8 cycles:

- accounting, lifecycle, prompt-credit, generation-credit and auth once each;
- ownership `--suite all --cycles 2` as one aggregate completion;
- tracked-only Linux backend pytest and documented native Windows reproduction;
- Compose `.env.example`, frontend lint/build, Session48 and Chromium34;
- final-head required `verify` and backend/frontend Scan/SBOM.

## 8. Exact implementation boundary and stop conditions

No migration is permitted. Implementation may change only these 18
non-document paths:

1. `backend/app/credit_accounting.py`
2. `backend/app/prompt_credit.py`
3. `backend/app/api/prompts.py`
4. `backend/app/api/generations.py`
5. `backend/tests/test_credit_accounting.py`
6. `backend/tests/test_prompt_credit.py`
7. `backend/tests/test_prompt_api.py`
8. `backend/tests/test_generation_credit.py`
9. `backend/tests/test_generation_api.py`
10. `backend/tests/test_pipeline_api.py`
11. `backend/tests/concurrency_support.py`
12. `backend/tests/test_concurrency_support.py`
13. `backend/tests/test_verify_concurrency_script.py`
14. `scripts/verify_concurrency.py`
15. `backend/tests/credit_accounting_support.py`
16. `backend/tests/prompt_credit_support.py`
17. `backend/tests/generation_credit_support.py`
18. `backend/tests/ownership_support.py`

A nineteenth non-document path is not implicitly authorized. Any migration,
second Module, schema/Redis design, production setting change, provider/cloud
call or time-limit relaxation is STOP-and-redesign. Unused allowed paths need not
be edited.

Completion requires Todo1–8, F1–F4 APPROVE, the full local proof, portfolio and
handoff documentation, Ready PR, final-head required CI, protected squash
auto-merge, actual `MERGED`, and Issue closure. The evidence level is **Mock
Verified**, never live provider capacity or cloud quota verification.

## 9. Implementation evidence — 2026-09-05

Revision `4e8132a` implements the accepted seam using 14 allowlisted
non-document paths and zero migrations. Two final isolated cycles at that same
SHA each completed all eight groups, six observed races, 259 checks and cleanup
zero. The inherited accounting, lifecycle, prompt-credit, generation-credit,
auth and ownership-all2 gates plus full Linux/Windows/Compose/frontend regressions
passed as recorded in `docs/portfolio/issue-129-user-concurrency-enforcement.md`.

Status is **Mock Verified — Merged**. [PR130](https://github.com/bbungjun/AI_multimodal_platform/pull/130)
passed final-head `verify` and both Scan/SBOM checks before protected squash
auto-merge `b050320`; Issue129 closed. Live Vertex throughput, cloud quota and
held-reservation recovery remain unverified.
