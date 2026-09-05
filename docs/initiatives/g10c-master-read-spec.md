# G10C — bounded read-only operational views

One master_read Module, HTTP Adapter in existing /api/master router. No schema,
writer, frontend or provider change. Fresh REPEATABLE READ READ ONLY transaction;
recheck active OAuth Master in its snapshot, statement timeout5s. Authorization
is snapshot-time, not a promise to revoke bytes already in flight.

GET overview: days1..90 default30, origin all/oauth/synthetic. Counts by origin,
status and persisted account Plan (uninitialized user Free/Master Max). Label
historical usage grouping as current persisted-account-plan attribution, never
historical subscription attribution. Return distinct reserved (created window),
charged/released (terminal window), held (current snapshot), seven meter observed
units/charges and UTC daily charges. Money/observed unit aggregates are decimal
strings to preserve integer precision; counts remain bounded safe integers.
Reservation charges are preaggregated once per Reservation before joins.

Job metrics use Jobs created in the window, terminal completed/failed denominator,
cancelled separate; p95 is queue-inclusive updated_at-created_at duration, null
without terminal samples. Persisted known model only; unknown maps to unknown.
Errors only allowlisted codes, never raw messages. Return20 recent failed Job
summaries (id,model,time,safe code); no content, parameters, operation, email.
No admission rejection statistics invented from absent Jobs.

GET users: limit1..50 default25, after UUID, origin all/oauth/synthetic and
status all/active/suspended, stable ascending UUID keyset; limit+1 marks next.
IDs are needed for bounded administrative actions, but no profile/email/sub.
Batch queries (not one lifecycle call per user). Signup, exact30-day cycle bounds,
role/status/origin, effective current Plan/pending, available/held/current-cycle
charged, and balance_materialized. If cycle was not lazily renewed, project the
new allowance/effective pending Plan without writing; old base availability is
excluded, unexpired bonus included, all held retained. Corruption fails closed.

GET audit: limit1..50 default25, after UUID; resolve immutable timestamp/UUID
cursor, descending timestamp+request_id. Return source/action/reason/time,
actor/target/request IDs and strictly validated before/after scalar allowlist;
never fingerprint. Unknown keys/values cause503 rather than leaking values.

All responses/errors private,no-store. Unknown query fields422. Existing
require_master remains boundary; no scope bypass. Empty datasets explicit/null
percentile. Pagination is per-request snapshot, not a cross-request frozen export.
Global query scaling is bounded by5s SQL timeout and time window, not claimed as
large-scale benchmark. Audit scan has existing indexes; no speculative migration.

Proof2 in owned PostgreSQL: guards,users,cycles,credits,jobs,audit,privacy,snapshot;
at least100 meaningful checks and3 event-gated MVCC read/write interleavings
(reserve,terminal,administration). Reader old snapshot then fresh reader new state,
read-only write refusal and no lazy-write counts. No sleep-based race claims.
