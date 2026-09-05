# Issue146 — coherent, private operational reads

## Problem and decision

Personal usage initializes/renews billing under locks. Reusing it for a whole
console would mutate many accounts on a GET and mix snapshots with concurrent
reserve/settle operations. G10C instead exposes one master_read Module with three
HTTP Adapters, REPEATABLE READ READ ONLY, actor revalidation and5s SQL deadlines.
Keyset pages are bounded50; aggregate windows default30/max90 days.

Unmaterialized30-day renewals are projected without writes: expired base grant
availability is excluded, pending Plan becomes effective, unexpired bonus and
older held work are retained. The response explicitly marks projected balances.
Audit values are allowlisted by both key and scalar value, not trusted because
they happen to be JSON. All HTTP success/errors remain private,no-store.
No email/profile, prompt, SQL, raw errors or provider operations are returned.

## Measurement definitions and limitations

Money and observed units use integer decimal strings, including large aggregates;
counts reject unsafe JavaScript integers. Current held is separate from reserved
in creation window and charged/released in terminal window. Per-Reservation
charges are aggregated before joins to avoid meter fanout double counting.
Plan aggregation is explicitly current persisted account Plan, not historical
Plan at usage time. Job model groups use persisted known models only; billing
meters are not reverse-mapped to exact models. No provider invoice parity claim.
Success denominator excludes cancelled/active Jobs. p95 is queue-inclusive
updated-minus-created for each model/terminal-state group, not provider latency;
no samples returns null. Later Job timestamp edits can affect this proxy.
Admission denials with no Job are not fabricated as failed Jobs.

## Failure and correction

First isolated proof failed in jobs because its direct SQL fixture omitted
required state_history/vertex_charged fields. Receipt
`.omo/evidence/issue-146/master-read-verify-d99ffcac2fa7.json` preserves failure
35.579s/cleanup2.781s PASS; no DB constraint was relaxed. Fixture corrected and
proof strengthened with actual transaction settings and corrupt Audit rejection.
One Compose invocation from backend used the wrong relative cwd; repeated from
repository root with the public template passed. No local secret env was read.

## Fresh evidence

Frozen Goal SHA-256:
`1bf79e36505ae4359215c91e9e219523b6a844800d36dc465b43d190b31d5a1c`.
Core7a389cf,8 of9 allowed code paths, no migration or writer change.

- Focused Master/read/API/harness tests80 PASS.
- `python scripts/verify_master_read.py --env-file .env.example` twice:
 8 groups/3 event-gated MVCC interleavings/112 checks each; old read snapshot
 remains unchanged while reserve,settle or audited bonus commits, fresh read
 sees the change. Guard, pagination, cycle, seven meters, credits, p95, privacy,
 corrupted Audit refusal and no lazy writes pass.
 Receipts `.omo/evidence/issue-146/master-read-verify-7fd768e27c48.json`
 (37.953s/2.734s cleanup) and `master-read-verify-897ba300bce8.json`
 (15.296s/2.719s cleanup); all owned resources removed.
- Inherited Master-admin8 groups/4 races/85 checks PASS16.375s/2.609s cleanup.
- Windows1724 PASS/3 existing guarded skips/known Bash-path127 failure only;
 final fresh Linux CI required. Frontend lint/build,Session60/Chromium47 PASS.
- Repository-root public Compose config,diff/status/staged/path hygiene PASS.

## Outcome and handoff

Implemented/Mock Verified read APIs, not console UX or live metrics. F1 scope
APPROVE,F2 coherence/security APPROVE,F3 local verification APPROVE pending
Linux CI,F4 records complete/protected merge pending. G10D consumes decimal-string
amounts, nullable samples, keyset cursors and explicit measurement definitions.
Global queries are timeout-bounded, not proven at large production cardinality;
query-plan/index tuning needs measured follow-up. Pagination is per-request
snapshot, not a frozen multi-page export. Snapshot-time authorization cannot
recall bytes already in flight after a concurrent suspension. Rollback removes
read routes only and leaves business data/Audit untouched.
