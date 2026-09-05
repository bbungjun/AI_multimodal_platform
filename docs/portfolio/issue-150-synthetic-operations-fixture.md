# Issue150 — reproducible synthetic operations data

## Problem and implementation

Testing a multi-user management console cannot require120 Google mailboxes or
paid generations. The seed creates120 login-disabled synthetic Users (84Free,
30Pro,6Max) and3000 content-free historical Jobs over90 days from explicit as-of.
Twelve dormant Users have no recent30-day activity; twelve are suspended;96 are
other active Users. Dormancy is a cohort, not a new database status.

User/Job UUID5 and operation keys are stable. Existing complete namespace is a
no-op, partial/mismatched as-of refuses without repair/overwrite. A transaction
advisory lock serializes concurrent seed requests. Dry-run executes the entire
construction and rolls back; apply requires explicit confirmation and a matching
owned local test database. Developer/preview/production targets are refused.

Existing lifecycle/accounting/state_machine Interfaces construct the history.
Seven observed meters,3000 Reservations and9000 Usage records are real local
database accounting, but the generated history is not evidence of actual media
delivery or production Job orchestration. No Assets, Outbox, Sessions or provider
calls are created. Plan/quota/concurrency refusals are observed in a rolled-back
diagnostic savepoint, not fabricated as failed Jobs. CLI output contains counts
only. Invariants retain the existing accounting/quota policy.

## Failure and correction

First dry-run failed; a safe exception-class/code diagnostic identified
monthly_credit_exhausted. Compressed44-day dormant Free history legitimately
exceeded its monthly allowance. Nine dormant Free fixtures now receive an explicit
1000-Credit nonexpiring synthetic bonus through grant_bonus. No quota bypass or
direct balance update. The non-bonus denial probe still proves quota refusal.
Failed receipts preserve36.047s/cleanup2.719s and14.188s/cleanup2.687s, both cleanup0:
`.omo/evidence/issue-150/master-seed-verify-2b6ae219a007.json` and
`master-seed-verify-2c7b4972edd9.json`.

Review also corrected the proof's Outbox table name and matched its stdin process
to the frozen600-second Goal budget; Docker/git auxiliary commands retain180s
ceilings and cleanup60s. No actual time limit was exceeded or raised. A unit test
now verifies command classification rather than relying on a misleading exec name.

## Fresh verification

Goal SHA `ae49954603e8222cb1f35fbdafa40bee64437027a229e33ccf8222ea2f8da6ca`.
Final core243da11,exact8 code paths,migration0,old schema unchanged.

- Focused29 PASS.
- `python scripts/verify_synthetic_seed.py --env-file .env.example` twice:
 each8groups/286checks/1 observed PostgreSQL blocking race,120 Users/3000 Jobs,
 dry-run0writes, complete replay0duplicates, collision rollback, coherent grants/
 ledger/Usage,3 actual denial observations and operational read aggregation.
 `.omo/evidence/issue-150/master-seed-verify-155f9e8d2adb.json`:147.594s/cleanup2.859s.
 `master-seed-verify-53d738934e0b.json`:142.281s/cleanup2.875s. All owned resources0.
- Inherited Master read112checks/3interleavings16.593s/cleanup3.000s and
 Master administration85checks/4races18.312s/cleanup3.047s PASS.
- Windows1753 PASS/3 guarded skips/known native Bash-path127 exception only.
 Frontend lint/build,Session70/Chromium61 PASS,public Compose PASS.
 Final Linux verify and both Scan/SBOM remain a protected delivery gate.

## Result and risk

Implemented/Mock Verified full-size fixture, not provider benchmark or invoice
reconciliation. Default developer DB and real users were untouched. Persistent
demo loading requires separately selecting/guarding a target; the verifier cleans
its generated dataset up. A changed fixture version/as-of or partial namespace
refuses; no destructive reset shortcut. Internal accounting receipt UUIDs remain
opaque, while semantic data and public fixture IDs are deterministic.
F1/F2 and local F3 APPROVE. Final delivery/F4 evidence is recorded on the linked
PR and parent137 closeout after required checks and actual protected merge.
