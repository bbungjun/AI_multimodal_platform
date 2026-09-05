# Issue142 — audited account administration

## Problem and cause

Account operators had no supported promotion, Plan change or bonus-grant entry
point. Direct SQL could create incoherent Master/Free billing state, duplicate
grants on retry, or leave no safe record of who changed what. Existing lifecycle
functions are transaction-composable but intentionally do not authenticate an
operator or provide Audit.

## Solution and trade-offs

One administration Module rechecks the actor under lock, validates a narrow
command, performs the existing lifecycle operation and inserts append-only Audit
inside one savepoint. A global transaction advisory lock serializes rare
administrative changes; ordinary generation does not acquire it. Actor/target
User locks are ordered before credit locks. Lock/statement waits are bounded.

Promotion upgrades the still-normal User's current allowance to Max before
setting role, preserving consumed Credit and clearing a pending downgrade.
Changing role first was rejected during design because lifecycle coherence
checks would then see an invalid Master/Free account.

Stable request UUID plus payload fingerprint yields replay without another grant
or Audit event; conflicting reuse returns409. Authority is rechecked before
replay. Audit insertion failure rolls back all business writes. Reasons and
before/after keys are bounded; no free-text log/PII/prompt/token/raw response.
Database triggers refuse Audit UPDATE/DELETE/TRUNCATE, and populated downgrade
refuses before DDL. This does not protect against a DB owner altering the schema.

HTTP `POST /api/master/users/{target_id}/commands` accepts only Plan/bonus commands;
identity comes from the existing Master dependency and trusted-Origin check.
Success and error responses are private,no-store. Browser role promotion and
actor/source selectors are rejected. The CLI requires exact User UUID, request
UUID, reason and expected local database; default simulation rolls back. Apply
requires `PROMOTE:<UUID>`. Actual allowed environment labels are `local|test`,
with mock provider. Production/remote/live operation is intentionally refused.

Example (operator supplies the actual target; never store identifiers in evidence):

```text
python -m app.master_cli --user-id <UUID> --request-id <UUID> --reason operator_bootstrap --expected-database <database>
```

Add `--execute --confirm PROMOTE:<UUID>` only after verifying preview and target.
CLI bootstrap Audit explicitly uses operator_cli source and target as actor; it
is not a browser-authenticated operator claim. No real User was promoted here.

## Verification and observed results

- Initial RED: missing Audit Module; model/migration/schema contracts then42 PASS.
- Final focused model/Module/HTTP/CLI/harness tests53 PASS.
- Stable implementation `0a350c1`: two independent actual PostgreSQL proofs each
 8 groups/4 observed lock races/85 checks, cleanup0. Work/cleanup35.391/2.781s and
 16.828/2.688s. Proof covers existing consumption preservation, transactional
 preview, Plan scheduling/cancellation, bonus expiry, replay conflict, concurrent
 same/different requests, Audit-trigger rollback, append-only/downgrade guards,
 and authority changed while an administrative request waits on a real DB lock.
- Schema roundtrip140.297s/cleanup1.922s PASS; old constraints and stale revision
 refusals preserved with additive0007 and unchanged0001–0006.
- Inherited lifecycle8 races/320 checks, accounting8 races/299 checks PASS.
- Auth PostgreSQL/Redis and outage/recovery PASS;12 concurrent admissions retain5
 Sessions,20 touches produce1 write; cleanup PASS.
- Windows1657 PASS/3 existing guarded skips/only known Bash path exception127.
- Frontend lint/build, Session60, Chromium47, public Compose PASS.
- Final-head Linux verify and both Scan/SBOM required before merge.

Receipts (local, sanitized):

- `.omo/evidence/issue-142/master-admin-verify-14d0f8c609dd.json`
- `.omo/evidence/issue-142/master-admin-verify-4a7c1c04dd7c.json`
- `.omo/evidence/schema/migration-schema-verify-b4871bb1090c.json`
- `.omo/evidence/issue-116/credit-verify-3082b76dfcf3.json`
- `.omo/evidence/issue-121/accounting-verify-9e4031572f39.json`

F1 scope17/migration1 APPROVE. F2 security/transaction/races APPROVE. F3 local
verification APPROVE pending final Linux CI. F4 records complete, protected
delivery pending. No unexplained failure is converted into a pass.

## Result, rollback and remaining risks

Implemented and locally Mock Verified: promotion CLI and audited Plan/bonus
commands. No suspension, work cancellation, operational read model, console,
synthetic seed or live verification yet. G10B consumes the administration
transaction and Audit format; it must preserve in-flight generation settlement.
Disable new routes/CLI on rollback; populated Audit cannot be downgraded/deleted
silently. Preserve Audit and roll forward rather than deleting operator evidence.
