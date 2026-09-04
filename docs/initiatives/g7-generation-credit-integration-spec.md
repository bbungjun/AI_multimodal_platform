# G7 — Imagen/Veo generation credit integration specification

## 1. Problem and outcome

G5C provides atomic `reserve`, `settle`, and `release`; G6 proves that boundary
for Gemini prompt enhancement. Imagen/Veo generation and the T2I-to-I2V
pipeline still enqueue provider work without reserving User credit, and worker
completion does not turn delivered Asset facts into Usage. G7 closes that caller
gap in mock mode without changing the accounting schema or calling Vertex.

The outcome is one deep `generation_credit` Module. API and worker adapters pass
Jobs and terminal facts through a small Interface; model-to-meter policy,
estimate construction, opaque operation keys, trusted Job metadata, pipeline
single-reservation rules, Asset-based Usage, and accounting error normalization
remain hidden inside the Module.

## 2. Scope and exclusions

Included:

- standalone Imagen T2I and Veo T2V/I2V admission;
- retry admission as a new billable attempt with a new server Job identity;
- pipeline top-level admission with one combined Imagen and Veo reservation;
- success settlement, no-deliverable release, and pipeline partial settlement;
- queue redelivery and terminal replay idempotency;
- focused unit/API/worker tests and an isolated PostgreSQL two-cycle verifier;
- inherited accounting, lifecycle, auth, ownership, backend, frontend, and
  Compose regression gates.

Excluded:

- G8 per-User concurrency enforcement;
- frontend Plan, Usage, Master, or billing UX;
- payment, Audit, held-reservation sweeper, and operator repair mutation;
- database migration or persistence model changes;
- real OAuth, Vertex/provider/cloud calls, GCP, Kubernetes, or Terraform work.

`AI_PROVIDER=mock` is mandatory for every execution and proof in this Goal.

## 3. Module Interface and trusted metadata

The Module exposes a narrow async Interface:

```python
admit_generation(session, *, job, now, pipeline_child=None) -> AdmissionReceipt
terminalize_generation(session, *, job, succeeded, reason_code, now) -> TerminalResult
```

Admission requires an existing caller-owned SQLAlchemy transaction. It validates
the supported model and request bounds, calls G5C `reserve`, then writes a
server-owned metadata object below a namespaced key in `Job.parameters`. The API
commits Job, Outbox, Reservation, allocations, ledger events, and metadata once.
An accounting refusal rolls the transaction back; no Job or Outbox remains and
no provider call is possible.

Metadata contains only bounded non-secret identifiers and policy facts:

- version and role (`standalone`, `pipeline_parent`, `pipeline_child`);
- reservation UUID, reserve operation key, and terminal operation key;
- top-level Job UUID and, for a pipeline, parent/child UUIDs;
- normalized reserved meter maxima.

The client never supplies this object. Retry strips inherited credit metadata
and creates a new reservation keyed by the new Job UUID. Operation keys use
bounded opaque server identities, not prompt or email data. No prompt, OAuth
token, credential, provider response, or account identifier enters evidence.

## 4. Meter and estimate policy

| Product model | Meter | Maximum units at admission | Actual units |
| --- | --- | ---: | ---: |
| `imagen-4.0-fast-generate-001` | `imagen_fast_image` | requested images | persisted image Assets |
| `imagen-4.0-generate-001` | `imagen_standard_image` | requested images | persisted image Assets |
| `imagen-4.0-ultra-generate-001` | `imagen_ultra_image` | requested images | persisted image Assets |
| `veo-3.0-fast-generate-001` | `veo_fast_ms` | requested seconds × 1000 | persisted video duration × 1000 |
| `veo-3.0-generate-001` | `veo_standard_ms` | requested seconds × 1000 | persisted video duration × 1000 |

Plan permission and available balance remain G5 policy. G7 does not add a bypass:
a Master is still billed under Max policy. A pipeline reserves the parent image
maximum and child video maximum in one `ReservationRequest`; the blocked child
does not call `reserve` again.

The persisted Asset rows, not provider response claims, are the delivery source
of truth. Image actual units are the count of IMAGE Assets for the covered Job.
Video actual units are the exact sum of persisted `duration_sec`, converted to
integer milliseconds. Unsupported, malformed, cross-owner, or over-reservation
facts fail closed without accounting mutation.

## 5. Transaction and terminal matrix

Provider work never runs inside a database transaction held by accounting.

1. API validates ownership and request shape.
2. One transaction inserts Job(s), Outbox, and G5C reservation state.
3. Commit makes work dispatchable; only then may the worker call the provider.
4. Worker writes Asset(s), asks the Module to terminalize, transitions the Job,
   and commits those changes atomically.

| Case | Accounting action | Usage | Delivery |
| --- | --- | --- | --- |
| standalone success | settle | persisted image count or video ms | delivered |
| standalone failure with no Asset | release | empty before attempt, otherwise zero-unit attempt line | no_deliverable |
| pipeline parent failure | release once | empty/zero-unit attempt evidence | no_deliverable |
| pipeline parent success | keep held | none yet | pending child |
| pipeline child success | settle once | parent image count + child video ms | delivered |
| pipeline child failure after parent delivery | settle once | parent image count only | partial |
| pipeline link failure after parent delivery | settle once | parent image count only | partial |

The Module derives release reason from an explicit safe adapter reason:
`cancelled_before_delivery`, `provider_failed`, `provider_timeout`,
`provider_rate_limited`, or `delivery_failed`. It never records raw exception or
provider payload data in Usage.

## 6. Idempotency and failure semantics

The server Job UUID defines one billable attempt. Queue redelivery sees a terminal
Job and returns before mutation; replay of the same reserve or terminal operation
converges through G5C unique keys. A manual retry is a new Job UUID and therefore
a new reservation after the failed attempt was released or partially settled.

G7 does not promise HTTP transport idempotency for two independently accepted
create requests. A future request-id contract can add that guarantee without
changing worker settlement. The current required invariant is queue/redelivery
idempotency for one accepted Job.

Terminal accounting and terminal Job state share one commit. If accounting
rejects the terminal facts, the Asset and Job transition roll back and the job is
not falsely exposed as completed. Storage bytes written before rollback may need
the existing orphan-file operational repair; adding a file transaction is out of
scope and is recorded as residual risk.

## 7. Verification contract

The isolated verifier creates a disposable Docker Compose project and fresh
PostgreSQL volume, fixes `AI_PROVIDER=mock`, upgrades to the current Alembic head,
and runs two complete cycles. Each cycle must prove these eight groups:

1. model/meter/estimate and Plan refusal before Job/Outbox persistence;
2. standalone Imagen success and actual delivered-image settlement;
3. standalone Veo success and measured-millisecond settlement;
4. no-deliverable provider failure/timeout/rate-limit release;
5. retry creates a distinct reservation after prior terminal release;
6. pipeline combined reservation and successful combined settlement;
7. pipeline parent failure release and child failure partial settlement;
8. queue/terminal replay plus competing terminal attempts produce one charge.

Each cycle reports groups, races, checks, schema head, and cleanup counts. Both
cycles must finish with container/volume/network cleanup zero. Existing G5C
accounting once, lifecycle once, auth PostgreSQL/Redis once, and ownership
`--suite all --cycles 2` remain required, followed by full Linux backend pytest,
the documented Windows regression, both Compose configs, frontend lint/build,
and existing authentication browser tests.

## 8. Delivery boundaries and stop conditions

Implementation may touch only the exact non-document paths frozen in the Goal
plan and may add no migration. A path outside that list, a schema change, a real
provider/cloud call, or a time-limit relaxation is a STOP-and-redesign condition.
Development and preview databases/volumes must remain untouched.

Completion requires Todo 1–8, F1–F4 APPROVE, a Ready PR, final-head `verify` and
both backend/frontend Scan/SBOM success, protected squash auto-merge, actual
`MERGED`, and closure of Issue #127. Evidence states **Mock Verified**, never
Vertex usage or live GCP billing verified.

