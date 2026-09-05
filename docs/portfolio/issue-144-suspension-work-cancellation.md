# Issue144 — atomic suspension and pending-work cancellation

## Problem and decision

Revoking authentication alone leaves already admitted, unpublished Jobs runnable.
Releasing every held Reservation instead would undercharge an in-flight pipeline.
The dispatch boundary is persisted Outbox publication, not a process-local flag.
G10B extends the existing audited administration transaction, without a migration.

## Implementation and failure modes

Suspend revokes all Sessions, refuses self/final-Master suspension, cancels pending
unpublished work through state_machine and existing terminal accounting, and writes
one replay-safe Audit receipt atomically. Outbox rows are locked before Job rows;
a dispatcher that has published wins the race and its work is preserved. Scans
over500 pending rows fail closed and roll back, rather than partly suspending.
Running/claimed work settles normally. A pending child of a dispatched pipeline
parent is deferred until parent completion/failure; cancellation then preserves
partial parent delivery or the existing release. Reactivation resurrects neither
Sessions nor Jobs. No provider or queue calls run in the administrative transaction.

Review found that a cancelled child must not increment a failure counter. The
pipeline receipt now distinguishes cancelled_count. The proof was strengthened
after the first successful run to exercise actual worker entry, the500-row guard,
Session authentication and both parent terminal outcomes; the final two receipts
below belong to unchanged core head d50b59c.

## Fresh verification

- Focused Master/pipeline/support/script tests:61 PASS.
- `python scripts/verify_master_suspension.py --env-file .env.example` twice:
  each8 groups,4 observed PostgreSQL lock races,112 checks,cleanup0.
  Receipts `.omo/evidence/issue-144/master-suspension-verify-7e8b811fe5b1.json`
  (16.109s work/2.750s cleanup) and `master-suspension-verify-5b73499978b4.json`
  (37.875s/2.765s). Tests include atomic rollback, exact replay, publication race,
  post-suspension admission refusal, running work and shared pipeline accounting.
- Inherited Master administration, generation-credit and PostgreSQL/Redis auth
  proofs PASS, cleanup0; no developer/preview project was used.
- `python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 1`:
  ownership348 metadata checks/8 groups/2 deletion races, file-ops310 checks/4 groups
  PASS;260.969s total, cleanup0. This is the frozen one-cycle regression, not a
  fresh two-cycle G4 completion claim (harness complete=false is expected).
- Windows backend1677 PASS,3 existing guarded skips, known Bash-path127 exception
  only; fresh Linux CI remains mandatory. Frontend lint/build, Session60,
  Chromium47 PASS; public-template Compose config and diff hygiene PASS.

## Result and remaining risk

Implemented/Mock Verified suspension and reactivation, not live OAuth/provider
verification. The500-row bound can reject a large backlog safely; a bounded batch
workflow would require a separate design. Dispatched provider work is deliberately
not aborted. Audit immediate counts exclude deferred pipeline cancellation.
G10C read model, G10D console and G10E fixture remain outstanding.
Rollback disables new status commands while retaining Audit evidence; do not
resurrect cancelled work or revoked Sessions. No schema downgrade is needed.

F1 scope12/14 and migration0 APPROVE; F2 transaction/security/races APPROVE;
F3 local proof/regressions APPROVE pending final-head Linux CI;
F4 records complete, protected Ready PR delivery pending.

Delivery: PR145 final head344d2fa passed Linux verify and both Scan/SBOM;
protected squash merge f99fa26 confirmed, Issue144 closed/main synchronized.
F1–F4 APPROVE. Parent137 remains open for G10C/D/E.
