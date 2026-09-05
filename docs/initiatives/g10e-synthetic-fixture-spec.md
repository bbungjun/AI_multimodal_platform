# G10E — deterministic, guarded synthetic operations fixture

One fixture Module and CLI Adapter, no schema or product writer changes. Create
exact120 synthetic login-disabled Users (84Free/30Pro/6Max),25 historical Jobs
each (3000 total) across last90 days relative to required explicit --as-of UTC.
Stable UUID5 User/Job IDs and operation keys; internal writer receipt IDs remain
opaque. Fixed protocol/as-of marker on fixture Jobs binds reruns. Existing complete
fixture is a no-op; partial/conflicting fixture refuses, never overwrites/repairs
arbitrary data. Serialize seed attempts with a transaction advisory lock.

Users signed up100..116 days before as-of, staggered30-day cycles. Twelve dormant
users have no Jobs in last30 days; twelve suspended after history;96 other active
users. Dormancy is an activity pattern, not an invented User status. All synthetic
Users have null Google subject/email, unverified email, user role, zero Sessions.
No fake login API. No real Master created by seed.

Fixture correction after failed dry-run: the compressed44-day dormant Free history
can exceed a real monthly allowance. The nine dormant Free fixtures therefore
receive an explicit1000-Credit nonexpiring synthetic bonus through grant_bonus
before history construction. Do not bypass quota or write balances directly.
The denial probe uses a non-bonus active Free fixture and remains unchanged.

Jobs are explicit content-free synthetic history, no assets/provider/Outbox/queue.
Use existing state_machine for transitions while constructing history. Completed,
provider-failed and cancelled outcomes; five persisted supported generation model
IDs by Plan. Each fixture event uses existing Credit reserve/settle/release with
Gemini input/output plus image/video observed usage to cover all seven meters;
mark source mock_estimate. This is fixture accounting, not a claim that a Job's
production generation flow bundles these meters or delivered real media.

Plan/quota/concurrency denial scenarios execute real accounting calls inside a
rolled-back diagnostic savepoint. Return safe observation counts; do not insert
nonexistent failed Jobs for pre-admission denials. No retained diagnostic holds.

Default dry-run constructs/validates then rolls back, reports expected counts.
Apply requires --execute --confirm SEED and exact --expected-database, local
PostgreSQL host, AI_PROVIDER=mock, APP_ENV=test and database name belonging to an
explicit master_seed_verify_<12hex> target. CLI deliberately refuses ordinary
developer/preview/production DBs. Harness owns labels/nonce/volumes and cleans up.
Seed exists for reproducible operations verification; loading a persistent demo
DB requires a separately guarded operational request, not an implicit write now.

Atomic all-or-nothing caller transaction, no deletion/reset/upsert of foreign data.
Rerun checks expected IDs, fixture protocol/as-of marker and synthetic identity
invariants, not current balances which may legitimately have later operator
changes. Unknown/partial namespace or mismatched as-of refuses. Report only counts
and safe codes, never IDs/prompt/SQL/raw exceptions/credentials.

Two independently owned PostgreSQL proofs (work600s/cleanup60 each) include
dry-run0writes, exact120/3000 and Plan/status/activity distribution, seven meters,
no Sessions/Outbox/Assets, ledger/held consistency, read-model aggregation,
idempotent rerun, as-of/partial collision refusal and3 denial observations.
At least8 groups/100checks. Also existing Master read/admin proofs, backend and
frontend regressions. Final protected PR/CI merge then parent137 close only when
all G10 slices have actual merged evidence; G11/live work remains outside.
