# Issue127 — Imagen/Veo and pipeline credit integration

## Evidence status

`Mock Verified — Merged` at implementation revision `7e795c2`. Ready PR128 passed
required `verify` and backend/frontend Scan/SBOM before protected squash merge
`0a88b94`; Issue127 closed. No Vertex request, cloud deployment or real GCP
billing verification was performed.

## Background and problem

G5C supplied atomic credit reserve, settle and release, and G6 connected it to
Gemini prompt enhancement. Imagen, Veo and the T2I-to-I2V pipeline could still
enqueue work without reserving a User's credit. A completed Job also had no
trusted conversion from persisted delivery facts to Usage. This allowed product
work and accounting to diverge precisely where image/video cost is highest.

The required result was not another thin API wrapper. Admission, retries,
pipeline partial delivery and worker replay needed one reviewable boundary that
could preserve the existing Job/Outbox/Celery architecture without holding a
database transaction across provider I/O.

## Observations and root-cause analysis

- Job creation and Outbox dispatch were previously unaware of G5C accounting.
  A credit refusal therefore had no fail-closed position before provider work.
- Provider response claims were not a sufficient billing source of truth. Only
  persisted image/video Assets prove what the product actually delivered.
- A pipeline has two Jobs but represents one purchase attempt. Reserving both
  independently would double-hold credit; releasing the parent on image success
  would under-account a later video.
- Queue replay and concurrent terminal attempts can revisit the same Job. A
  status-only guard without accounting operation identity could double charge.
- Focused implementation exposed six integration faults: internal metadata was
  initially public; legacy retry parameters lacked required estimate fields;
  an Outbox could be inserted before rejected admission; inherited ownership
  fixtures left legitimate credit holds or used incidental one-per-minute rate
  limits; proof actors did not always match persisted owners; and terminal usage
  accepted a delivery Asset of the wrong media kind.

The original failures and each bounded redesign remain in the local Goal/evidence
record. They were not rewritten as first-pass success.

## Solution and rationale

`backend/app/generation_credit.py` is the deep Module for generation accounting.
It hides model-to-meter policy, maximum estimates, opaque operation identities,
trusted Job metadata and the terminal matrix behind admission and terminalization
operations.

- API admission inserts Job(s), Reservation state and Outbox in the caller's one
  transaction. Rejected credit leaves no dispatchable work.
- Standalone Imagen reserves requested image count; Veo reserves requested
  duration in milliseconds. Settlement counts only persisted Assets of the
  expected media kind and rejects malformed, cross-owner or over-reservation
  delivery facts.
- A pipeline reserves image plus video maxima once at the parent. Image success
  keeps the hold; child success settles both deliveries, while child/link failure
  settles the image only. Parent failure releases the entire hold.
- A manual retry creates a new Job and reservation. Legacy Jobs receive bounded
  compatibility defaults, while copied internal metadata is stripped.
- Server-only metadata is removed from public Job parameters. Safe reason codes,
  not raw exceptions or provider responses, enter accounting records.
- Existing G5C operation keys make reserve/terminal replay converge. No database
  transaction spans provider execution.

The implementation deliberately excludes HTTP create-request idempotency, G8
per-User concurrency enforcement, payment, Usage UI and live provider work.

## Verification

All product execution used local Docker and `AI_PROVIDER=mock`; development and
preview databases and volumes were not reset or adopted.

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_generation_credit.py --env-file .env.example
python scripts/verify_generation_credit.py --env-file .env.example
python scripts/verify_credit_accounting.py --env-file .env.example
python scripts/verify_credit_lifecycle.py --env-file .env.example
python scripts/verify_auth_postgres.py --env-file .env.example
python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 2
docker compose --env-file .env.example config --quiet
```

Results at code `7e795c2`:

| Gate | Result |
| --- | --- |
| Generation credit cycle1 | 8/8 groups, 2 races, 120 checks, work35.203s, cleanup0 |
| Generation credit cycle2 | 8/8 groups, 2 races, 120 checks, work14.860s, cleanup0 |
| Inherited accounting/lifecycle/auth | Each passed once in fresh isolated resources |
| Ownership aggregate | ownership2 + file-ops2, complete in523.235s, cleanup0 |
| Linux backend | 1487 passed, 3 guarded skips |
| Windows backend | 1486 product tests passed, 3 guarded skips; existing native Bash path test returned127 |
| Frontend | lint/build, Session48 and Chromium34 passed |
| Compose | `.env.example` mock config passed |

Bare `docker compose config` was not promoted to a pass on this checkout: the
intentionally absent local `.env` leaves required database variables undefined.
No secret-bearing `.env` was created merely to satisfy that local precondition.
CI remains the delivery authority for the committed configuration.

## Result and impact

Imagen, Veo and pipeline work now fail closed before dispatch when monthly credit
is unavailable, and successful/partial delivery produces Usage from persisted
facts. Failure releases unused credit, retry is a distinct billable attempt, and
queue replay cannot duplicate the same settlement. The change fits the existing
transaction and worker boundaries with zero schema migrations and 19 approved
non-document paths.

For an AI Platform/FDE portfolio, this demonstrates translating an ambiguous
"charge generation" request into explicit transactional, ownership, delivery
and failure invariants, then testing those invariants against the existing
distributed workflow instead of proving only a happy-path API response.

## Remaining risks and next steps

- All evidence is mock-only. Vertex quota, provider usage and live GCP billing
  remain unverified and require a separately authorized bounded QA run.
- Two independently accepted HTTP create requests are separate billable attempts;
  transport-level request idempotency is not part of G7.
- Storage bytes written before a failed database commit can remain orphaned; the
  existing operational repair boundary remains necessary.
- Held-reservation reconciliation/sweeping is not implemented here.
- G8 should add atomic per-User concurrency enforcement before broader multi-user
  load and G9 Usage UX work.
