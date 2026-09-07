# Issue160 — Authenticated journeys under local load

Status: In Progress. Local mock only; no live Google, Vertex or cloud execution.

## Problem and acceptance

Previous k6 profiles checked readiness and prompt responses. They did not prove
that an authenticated user receives an asset and consistent credit usage after
an asynchronous generation. Historical Issue84 also records DB exhaustion and
stranded jobs; local results cannot close its GKE acceptance criteria.

This delivery joins browser acceptance to multi-user HTTP journeys, records
failures before changes, and reruns the same workload after bounded fixes.

Frozen normal gates: journey success >=99%, server 5xx=0, API p95<1s/p99<2s,
mock completion p95<15s, dropped iterations=0. Stress reports the same gates;
failing them identifies an unsupported load, never a reason to lower the gate.
After drain: no nonterminal jobs, pending/failed outbox or held credits; saved
image/video usage and credit ledger must reconcile. Dispatcher recovery <=60s.

## Scenarios and method

- Browser: authenticated studio, enhancement review/accept, generate, visible
  decoded PNG, download, library and usage. Real frontend/API/DB/worker.
- k6: independent Max users; 60% image (half enhanced), 20% video, 20% image to
  video pipeline. Every journey reads usage, creates, polls, downloads each
  output, reads the library and verifies settled usage. One journey per VU.
- Baseline: 1 journey/2s for 20s. Steady: 2/s for 30s. Burst: 10/s for 10s.
- Soak: 2/s for 120s. Explicit arrival rates avoid silently reducing offered
  load when the server slows; record dropped iterations.
- Recovery: stop only the owned dispatcher, submit work, verify durable pending
  outbox/held credit, test one user's Max5 limit, restart and drain within 60s.

Test sessions are synthetic fixtures stored as hashes, never a product login
bypass. Google login/TLS are excluded. Mock video is a placeholder, not evidence
of real provider latency or playable video quality. Load-generator and server
share a local machine; capture Docker resource configuration and DB connections.

## Results, diagnosis and changes

Exploratory baseline at product revision `2b280f8`: 10/10 baseline journeys,
59/60 steady journeys (one enhancement 5xx), 100/100 burst journeys. After drain
all accepted jobs completed and the credit/asset audit passed. This is a failed
normal-load gate, despite the low latency and passing burst.

The same-user recovery case then admitted only 2/10 requests, with 8
`credit_busy` failures and no expected 429. A second fresh run reproduced the
same counts. Diagnostic run `20260907-125609` measured PostgreSQL deadlocks
increasing from 0 to 8, while connections remained 6/100 and admission clock-
regression diagnostics stayed zero. The clock-order hypothesis did not explain
this first failure; the initial clock-interface experiment was removed so the
lock change could be measured independently.

Cause: inserting a Job/PromptEnhancement takes a FK KEY SHARE lock on User.
Accounting requested FOR UPDATE on that same User; concurrent transactions
could each retain KEY SHARE and wait to upgrade, forming a deadlock. Nested
credit lifecycle also requested FOR UPDATE, so changing just the outer query
would not eliminate the conflict. PostgreSQL aborted victims, surfaced as
credit_busy. Existing accounting-only concurrency tests did not exercise the
same HTTP/child-row insertion sequence.

Both credit lock helpers now use FOR NO KEY UPDATE only for User. That mode
still conflicts with other credit writers and suspension/update operations,
but is compatible with FK KEY SHARE. Account, grant and other row locks keep
FOR UPDATE. No capacity, pricing or retry limits were increased. The lock-mode
regression failed before the fix; related accounting/lifecycle/prompt/generation/
usage/API checks: 158 passed after it.

Lock compatibility is specified in the [PostgreSQL 16 lock matrix](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS);
SQLAlchemy emits NO KEY UPDATE for `key_share=True, read=False` as documented in
[with_for_update](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.GenerativeSelect.with_for_update).

Test-harness startup corrections were kept separate from product failures:
synthetic Session expiry must match the schema's seven-day contract, and the
library uses a clickable row rather than an anchor. Those failed setup/browser
runs are not counted as server-load observations.

The lock-only run `20260907-125755` passed baseline and steady (60/60 journeys,
zero 5xx/deadlocks), then exposed a second failure during burst: two failed Jobs
and one downloading Job with a held reservation after drain. Worker failure was
`GenerationCreditError: credit_account_inconsistent`. Deadlocks remained zero.
The run stopped before soak/recovery; it is not a successful stabilization.

Terminal accounting rejects `now < account.updated_at`. Live callers captured
time before delivery queries and before waiting on User. A concurrent usage
read can advance lifecycle time while that terminal operation waits. A focused
reproduction preserves the stale-timestamp refusal, then settles the same held
reservation successfully when live time is sampled after acquiring User.

Reserve, settle and release now accept a clock callable as well as an explicit
instant. HTTP generation/prompt, worker terminalization, pipeline failure and
personal usage pass a live clock; the core samples it after User serialization.
Explicit historical time, replay identities and clock-regression refusal remain
strict. No sleep, timestamp clamping, forced settlement or silent retry hides
the failure. Related accounting/lifecycle/generation/usage/API/Celery checks:
171 passed. Both unsuccessful phases remain in evidence.

The first deferred-clock run `20260907-130401` is also **failed**: all baseline
Jobs finished but one journey failed its delivery/usage assertion; steady load
left one downloading Job and a held reservation. Two terminal clock-regression
diagnostics appeared. This candidate is not verified stable. More precise
bounded diagnostics now distinguish fixed/live clocks and record only the lag
in microseconds; their next runtime execution is pending.

Diagnostic run `20260907-130827` could not start: Docker Engine returned HTTP
500 and cleanup could not be confirmed. Docker Desktop subsequently reported
an inaccessible zero-length `dockerInference` runtime socket during startup.
Force stop/relaunch did not restore the engine. Automated deletion of that
socket was rejected by approval review; manual local Docker recovery was
requested. No factory reset, volume pruning or cloud fallback was attempted.

Full Windows regression at this candidate: 1820 passed, three guarded skips,
one already-documented Bash/Windows-path failure in the release-script test.
Frontend lint/typecheck and production build passed. These results do not
override the failed real-runtime gates above.

Final combined-fix load/recovery results: pending. Reproduce via the
[local runbook](../runbooks/local-user-journey-load.md).

Reviewed aggregate artifacts (no cookies, prompts, account identifiers or raw
logs): [initial load](../evidence/issue-160/initial-load.json),
[deadlock reproduction](../evidence/issue-160/deadlock-reproduction.json),
[lock-only failure](../evidence/issue-160/lock-only.json),
[deferred-clock candidate failure](../evidence/issue-160/deferred-clock-candidate.json),
[Docker startup failure](../evidence/issue-160/docker-start-failure.json).
These are exploratory dirty-tree measurements with source hashes, not evidence
of a deployed or stable final revision. Initial harness diagnostics were refined
between runs; compare product outcomes, not minor latency differences as gains.

## Remaining risks

Local capacity does not establish GKE capacity. Dispatcher interruption does not
prove Redis-loss or arbitrary worker-crash recovery. HTTP create idempotency,
provider billing and provider latency remain outside this evidence.
