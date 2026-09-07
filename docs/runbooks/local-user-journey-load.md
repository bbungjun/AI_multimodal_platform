# Local user journey load and recovery

This proof runs on a fresh, labelled local Docker project. It does not adopt a
developer database, read `.env`, contact Google/Vertex, or start cloud resources.
Browser Sessions are synthetic test fixtures; real Google login/TLS is excluded.

## Prerequisites and execution

Docker with Compose v2, Python/backend development dependencies, Node/frontend
dependencies, installed Playwright Chromium, and k6 on PATH are required. Use
the repository root. Port 18155 must be free for browser acceptance.

```powershell
python scripts/verify_user_journey_load.py --profiles baseline --browser
python scripts/verify_user_journey_load.py --profiles baseline steady burst soak recovery --browser
```

The runner accepts only named profiles and always uses `.env.example`, forced
mock mode, empty provider credentials and an owned loopback backend. Fixture
Session secrets stay in process memory (stdin to Node, environment to k6); only
their hashes enter the isolated database. Never run k6 with HTTP debug enabled
or save process environments. No product login bypass is added.

Read `output/load/<run>/report.json`. Every workload gate has a pass/fail result;
the process exits nonzero on any failure. Failed runs are retained. Screenshots
are masked and local at `output/playwright/user-journey/`. Export only reviewed
aggregate reports and the masked image, not raw logs, traces or browser state.

## Offered load and measurement

| Profile | Offered journeys | Duration | Maximum distinct active users |
| --- | --- | --- | --- |
| baseline | 1 per 2 seconds | 20 seconds | 4 |
| steady | 2 per second | 30 seconds | 20 |
| burst | 10 per second | 10 seconds | 50 |
| soak | 2 per second | 120 seconds | 20 |

Users have Max credits to exercise every mode without bypassing accounting or
concurrency policy. The workload is 60% image (half enhanced), 20% video and 20%
image-to-video pipeline, with one journey at a time per VU. A pipeline produces
two Jobs. Polls run every 0.5s, bounded to 60s. No timed human think period is
inserted; these are compressed user workflows for capacity testing, not an
estimate of human click rates. Fixed arrivals and dropped-iteration counts
prevent closed-loop load reduction from concealing overload.

Each journey verifies usage access, HTTP admission, terminal success, actual
download byte length/media signature, library membership and released credit
holds. k6 API p95/p99 and job completion latency are separate metrics. The
browser checks review/accept, generation payload, decoded PNG, library UI and
usage UI through a real Vite proxy. With `--browser`, this proof also runs while
the soak profile is producing load, using a separate fixture user. Video is the existing mock MP4 placeholder;
its bytes exercise transport/storage, not real video playback or AI quality.

All profiles retain fixed gates: >=99% journey success, zero 5xx, API p95<1s and
p99<2s, mock completion p95<15s, zero dropped iterations. Stress failure defines
an unsupported offered load; it must not be hidden by changing thresholds.
After drain, compare accepted/completed work and DB state. Zero held credits,
nonterminal Jobs, pending/failed outbox and queued messages are required. The
audit checks ledger/grant/usage agreement and image/video usage against Assets.

The current local resource profile is API1, dispatcher1, worker concurrency2,
PostgreSQL default max_connections100, with no imposed container CPU/memory
limits. Hardware is recorded from Docker. Model admission limits are raised to
600/min only in the inherited isolated mock runtime; production/demo limits are
unchanged. Samples record DB connections/deadlocks, job/outbox/queue counts,
holds and container CPU/memory. Sampling itself consumes local resources and
samples cannot prove an unsampled peak. Do not run unrelated benchmarks during
a comparison. Preserve identical workload and resource configuration.

## Recovery and safety

Recovery stops only the owned dispatcher. Twenty independent users submit work;
ten concurrent requests from another Max user must yield five accepted and five
429 refusals. While stopped, 25 pending outbox records and credit holds must be
visible. Restarting that dispatcher must complete all 25 within 60s with zero
duplicates, stranded work or held credit. This is dispatcher interruption,
not a destructive Redis-loss or in-flight worker-kill claim.

Cleanup runs in `finally` and verifies project and private ownership labels
before removing only that run's containers, network and volumes. A report with
cleanup other than zero is not a successful run. Do not use global Docker prune
or bring down unrelated projects. The runner leaves existing Docker images as
reusable build cache; it does not prune them.

## Stabilization rollback

Issue160 changes credit User locks from `FOR UPDATE` to `FOR NO KEY UPDATE` in
both accounting and nested lifecycle. User credit writers remain mutually
exclusive and conflict with account suspension; FK `KEY SHARE` checks can
coexist. Account/grant locks remain `FOR UPDATE`. No schema migration, API
payload, tariff, worker count or cloud configuration changes are involved.

Live reserve/settle/release and personal usage also defer clock sampling until
User is locked, so a queued operation is not rejected using an earlier arrival
timestamp. Explicit timestamp inputs keep strict historical/clock checks.

Rollback uses the prior application image/commit for API, worker and dispatcher
together. It restores the demonstrated FK lock-upgrade deadlock risk, so retain
the failed evidence and rerun the contention case before a rollback decision.
See [the evidence record](../portfolio/issue-160-user-journey-load.md).
