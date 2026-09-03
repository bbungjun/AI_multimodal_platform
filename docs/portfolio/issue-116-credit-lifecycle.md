# Issue116 — G5B credit lifecycle design and evidence

Status: Locally Mock Verified / delivery pending, 2026-09-04.
Issue [#116](https://github.com/bbungjun/AI_multimodal_platform/issues/116);
[Ready PR119](https://github.com/bbungjun/AI_multimodal_platform/pull/119);
[spec](../initiatives/g5-credit-lifecycle-spec.md); parent114 remains open.

## Problem

G5A supplies durable balances/ledger and pure policy, but no account initialization,
renewal, Plan change or grants. Writing these directly in authentication/generation
would duplicate transaction and retry rules. A replayed downgrade has no monetary
delta, so the existing ledger alone cannot remember its immutable request/result.

## Observations and alternatives

Inspected merged a003257's credit_models/policy, User roles/status, Alembic/schema
proof, auth/current-head helpers and prior delivery evidence. No unrelated edits
were present; existing .omo was preserved.

- Ledger-only idempotency was rejected: scheduling/cancellation/no-op cannot append
  a valid zero-valued event and cannot identify later replay from current Plan alone.
- A generic repository/event framework was rejected: PostgreSQL is the only store.
- Signup hook and background renewal were deferred: B must be transaction-composable
  without changing authentication or introducing paid/product side effects.
- Head changes affect schema/auth/ownership proofs. Counting that compatibility
  work yields exactly20 code paths, not only the new lifecycle module.

## Proposed solution and trade-offs

codebase-design guided a small three-operation Interface with caller-owned Session
and explicit time: ensure_cycle/change_plan/grant_bonus. Lock User/account/cycle/
grants in one order, refresh locked ORM state, isolate rejected writes in savepoint
and leave final commit/rollback to caller. No provider call within the transaction.

One additive0005 operation table stores immutable typed request/result receipts.
The existing four-table DDL and rate policy remain unchanged. Command replay
precedes renewal/expiry so a retry after a boundary cannot apply twice. Separate
ledger/projection updates remain in the same transaction; no-op Plan requests
write only the receipt.

The spec explicitly resolves pending downgrade replacement/cancellation, current-
cycle-only skipped renewal, immediate allowance difference, Master/suspended
handling, held-credit expiry, strict overflow and original-result replay. The
hash-bearing execution request approved these details. They are implemented and
locally Mock Verified, but remain unwired to product generation.

Rollback preserves all existing data: populated operation downgrade refuses under
bounded locks. Empty-operation downgrade preserves populated0004 rows. There are
no product callers to unwind in this slice. No destructive development/preview QA.

## Preparation performed and verification

- Confirmed PR118 actually MERGED at a003257, Issue115 closed;114/117 open.
- Synchronized main by fast-forward and created codex/issue-116-credit-lifecycle.
- Read and inspected predecessor contracts; added B spec and frozen Goal only.
- Baseline from backend with AI_PROVIDER=mock:

```powershell
python -m pytest tests/test_credit_policy.py tests/test_credit_models.py tests/test_credit_foundation_support.py tests/test_alembic_schema.py tests/test_schema_control.py tests/test_verify_schema_migrations_script.py tests/test_verify_auth_sessions_script.py tests/test_ownership_persistence.py tests/test_mock_auth_support.py tests/test_verify_ownership_script.py -q
```

Result: **446 PASS/3.01s**. This verifies existing code, not proposed lifecycle.
Final fresh rerun: **446 PASS/1.77s**. Exact20 spec/Goal path parity, all24
acceptance IDs,11 PowerShell command blocks,101 relative links, frozen SHA,
static Compose config and diff/status/staged checks PASS. Non-document edits0.
No Docker runtime, OAuth/provider/cloud call, DB reset/migration, frontend change
or application-code edit was performed. All new capability remains Planned.

Frozen local plan: `.omo/plans/issue-116-g5b-credit-lifecycle-goal.md`.
SHA256: `d17f47ac85b21ff11f3c95081794fb81517277368c6b1196427fd53669dcb590`.
Transfer exact file bytes when changing machines; do not stage .omo wholesale.

## Execution checkpoints

### Todo1 — preflight

User approved spec section3 and the frozen SHA. Starting8e2f3fb, origin/main
unchanged a003257; tracked/index clean and existing .omo preserved. Local daemon
desktop-linux/npipe with no DOCKER_HOST override; preview4 running and developer/
preview DB/media volumes present. Backend dotenv guard passed without reading
private configuration. First B0 command above:446 PASS/2.39s. Scope/hygiene checks
pass; implementation is not yet runtime verified. Next: operation schema.

## Planned acceptance and remaining risk

### Todo2 — operation persistence

Added one typed append-only credit_operations table and additive0005 migration.
Nullable request fields have explicit IS NOT NULL shape guards to avoid SQL CHECK
null acceptance. Composite owner FKs and User/key PK prevent cross-owner receipt
references; downgrade locks5s and refuses nonempty operations before DDL. Existing
four-table contracts/migrations preserved. M23 PASS/1.63s; structural tests only,
not real DB proof. Scope4/20; current-head compatibility is intentionally Todo5.
The first staged check found a trailing blank line in the new migration; it was
removed and the owned, unpushed checkpoint amended after fresh staged validation.

### Todo3 — initialization and renewal

Added caller-transaction requirement, savepoint rollback, fresh User/account/cycle/
grant locking, immutable CycleView and current-only signup-anchored renewal.
Held/consumed amounts remain on expired grants; only available moves to expired.
Corrupt anchor/allowance/base/Master state and clock regression fail closed. No
product caller or provider work. Unit fake tests prove Interface decisions, not
PostgreSQL locking. C72 PASS/0.76s, M23 PASS/0.85s; scope6/20, D PASS.

### Todo4 — Plan, bonus and immutable replay

Added all Plan transitions with allowance-difference upgrades, pending replacement/
cancellation/no-op records, strict bonus validation, outstanding BIGINT bound and
replay-before-renewal. Conflicting keys roll back without lazy renewal; identical
replay keeps original IDs/time even after expiry/suspension. Contention maps to a
fixed safe code after savepoint rollback. No product caller. C102 PASS/1.02s and
M23 PASS/0.97s; scope remains6/20. Real SQL/locking proof follows in Todo5/6.

### Todo5 — fixed PostgreSQL proof and compatibility

Implemented the fixed runtime lifecycle proof and its local-only owned-project
runner. Eight groups cover initialization, renewal, Plan, bonus, expiry, replay,
transaction semantics and eight independent lock-observed races. Runtime uses
Python stdin, not pytest or arbitrary SQL/source inputs. Only allowlisted receipts
leave the runner; first failure and cleanup failure remain separate. Work300s and
cleanup90s deadlines are not extended or retried.

All current-head consumers now require0005; historical0003 proof stays pinned.
Schema proof retains credit90/races3 and adds populated0004 round trip, empty new
table downgrade/re-up, populated operation/lock refusal, stale0004 recovery for
all three processes and populated operation reset coverage. Old migrations and
four-table DDL remain unchanged. No provider or product wiring.

Focused H+C+M537 PASS/2.72s; B0452 PASS/2.14s; exact20/20 paths, one new migration
and D PASS. These are host structural/unit results only. Next: commit all code,
capture SHA, then execute S2/R2/A/O/L/W/U on that immutable code.

### Todo6 attempt1 — reset fixture accounting mismatch (not complete)

At faf2e00, schema-verify-4f37775cc70c reached reset and refused because the
verifier predicted one extra credit_operations row from the legacy seed, which
actually inserts only six legacy rows. This was a verifier expectation defect;
reset execute had not started. Work154.657s/cleanup2.000s, failure verification_failed,
credit90 reached; the receipt truthfully marks the full cycle unverified. Exact
container/volume/network label queries independently returned0. No timeout.

Replaced the negative four-table exclusion with the exact six seeded legacy tables;
the regression now explicitly preserves existing operation counts. Also bounded
the first participant of each new lifecycle race to10s, matching the second.
Fresh H+C+M537 PASS/2.91s. Failure receipt retained at
`.omo/evidence/schema/migration-schema-verify-4f37775cc70c.json`. All runtime gates
restart on the corrected committed code; this failed attempt is never counted.

### Todo6 intermediate checks — schema success and runner preflight correction

At243c394, schema-verify-d2c00c2d374b and schema-verify-5273490acda9 passed every
schema/credit/operation/stale/reset gate: work149.469/148.438s, cleanup1.969/1.953s,
credit90/races3 each, old ownership8, independent resources0 after each. No timeout.
These receipts are preserved but superseded for final-code acceptance below.

A read-only new-runner revision probe then reproduced dirty_code_refused with
only docs/.omo changes. The subprocess adapter stripped porcelain's leading status
column, shifting the path. It now removes line endings only; a real-adapter unit
test covers the docs-only status. No Docker target was started by that probe.
Fresh H+C+M538 PASS/2.75s. Commit the corrected runner and restart the complete
runtime sequence so final acceptance never combines different code checkpoints.

### Todo6 intermediate checks — Windows Compose plugin environment

At6ad2a28, schema-d63285db38c4 and schema-d2bf7ee270b0 (both prefixed
schema-verify-) passed all gates, credit90/races3, work149.860/151.156s and
cleanup2.015/2.063s, independent resources0. Full project names are in the safe
schema receipt filenames. These remain intermediate because of the next fix.

The first lifecycle command failed before project creation during Compose config.
Read-only diagnosis found its sanitized process environment omitted Windows
ProgramFiles/ProgramFiles(x86), preventing Docker from locating the Compose plugin
(native exit125). Adding only those system paths made config --quiet pass; a
generated DB/migrate-only config also passed. No DB/volume/network was created.
The new guard test initially assumed case-sensitive environment-key spelling;
Windows normalizes it, so assertions now compare uppercase keys on both platforms.
The test failure is retained here, not relabeled runtime success. No timeout.

All runtime gates restart after the environment compatibility correction; provider
and credential settings remain filtered, no private dotenv is used.

Todo1–8/F1–F4: exact20/new migration1, all24 acceptance IDs, schema2 and lifecycle2
independent projects, auth1, unchanged ownership all/2, authoritative Linux full
backend and existing frontend regression, Ready PR/final-head3 CI/protected squash
actual merge. New proof requires eight completed groups and eight lock-observed
races; partial checks cannot count as complete. Fixed deadlines stop on overrun.

### Todo6 final runtime and regressions

Final code65cdbb4 passed schema2 at151.515/148.312s work and2.032/2.000s
cleanup; each retained credit90/races3, ownership8, populated0004 migration,
stale0004 recovery and guarded reset. Lifecycle2 completed all8 groups,8 observed
lock races and320 checks at16.656/16.828s work and2.938/3.093s cleanup. Every
project independently left containers/volumes/networks0; preview4 stayed running.

Auth passed PostgreSQL/Redis/outage recovery. Ownership all/2 completed four
projects in1027.531s: ownership access348/admission111/delete races2 twice and
file FOVE310/two actors10 stages twice. Linux tracked-only archive:1321 PASS/3
guarded skips. Windows:1320 PASS/3 skips plus the sole documented native127
Bash-path failure, reproduced on untouched a003257. Compose, frontend lint/build,
Session48 and Chromium34 passed. No timeout/provider/OAuth/cloud execution.

### Todo7 sequential self-review

- **F1 APPROVE:** exact20 code paths, one new0005; migrations0001–0004 and
  forbidden production areas unchanged; one lifecycle Module, no product caller.
- **F2 APPROVE:** B01–B23 map to unit plus actual constraints, append-only attempts,
  rollback/fresh locks/replay and eight named races. B24 delivery remains pending;
  no G5C billing claim.
- **F3 APPROVE:** final-code S2/R2/A1/Oall2, Linux/frontend and documented Windows
  exception have direct evidence; every owned project cleaned independently.
- **F4 PENDING:** PR119 is Ready; final-head three CI checks, protected squash and
  Issue states remain and cannot be inferred from local tests.

The20-path cap leaves no spare path. Any21st path, second migration, missing required
Interface or runtime timeout requires redesign before scope expansion. No account/
grant/renewal/charge currently runs for users. G5C reservation/Usage/settlement and
G6/G7 generation wiring remain separate; no overspend/settlement or live claim.
