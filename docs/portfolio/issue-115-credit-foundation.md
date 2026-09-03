# Issue115 — G5A credit foundation preparation

Status: `In Progress`, 2026-09-04. Frozen Goal execution authorized; preparation
history below remains distinct from implementation/runtime evidence.
[Issue115](https://github.com/bbungjun/AI_multimodal_platform/issues/115),
[parent114](https://github.com/bbungjun/AI_multimodal_platform/issues/114),
[spec](../initiatives/g5-credit-foundation-spec.md).

## Problem and expected outcome

G4 isolated User-owned content, but the product still has no per-User credit
accounting. The accepted G5 spans storage, rates, renewal and concurrent settlement;
implementing all of it in one context would make scope, verification and failure
recovery hard to audit. The user requested a split and executable first Goal.

## Inspection and diagnosis

- Main/G4 delivery verified: PR113 MERGED6537025, parent109 CLOSED.
- Identity exposes User.id and signed_up_at; no credit table or account lifecycle
  exists. Production schema readiness discovers Alembic head automatically.
- Current schema/auth/ownership proof tools pin0003 in several paths. Adding a
  migration without updating those expectations would break existing verification.
- The schema verifier also tests historical0003 downgrade/nonempty behavior.
  Global literal replacement would corrupt that historical proof. The design
  instead runs it at0003 and restores0004 before subsequent proof.
- Runtime image lacks tests/pytest. Real credit proof must be passed into the
  owned migrate container explicitly, using already installed dependencies.
- Existing G4 failed combined-runtime attempt remains in its own record. New
  preparation preserves the split ownership/file suites and their strict budgets.

## Design and trade-offs

- G5A: four empty additive accounting tables, append-only ledger and pure rate/
  elapsed-time policy. B: account/Plan/cycle/grants. C: reserve/settle/release/Usage.
- codebase-design informed the small policy Interface and caller-owned transaction
  Seam for later work; no pass-through repository or generic accounting framework.
- Available credit is derived from grant projections; ledger events reconstruct
  them. This avoids an additional account balance with another synchronization rule.
- Integer microcredits avoid floating-point charge drift. SQL CHECK/FK/unique and
  append-only triggers cover persistence; real concurrency semantics remain B/C.
- New-head proof compatibility is included in exact17 paths, migration exactly1.
  No signup hooks, grants or live deduction exist after A alone. UI stays G9/G10.
- B/C are explicit dependent Issues, not frozen against imaginary source files.
  Their detailed execution plans are created after the preceding real Interface.
- Rollback: guarded empty-credit downgrade only; populated accounting records
  refuse destructive downgrade. Preserve them and use reviewed forward repair.

## Preparation verification

Main fast-forwarded to `6537025535b1006f6ca03366765e8a0f7e6bf978`, then branch
`codex/issue-115-credit-foundation` created. Only documentation changed.
Existing .omo/user changes preserved; no Docker runtime, DB reset, provider/OAuth
call or cloud command was executed for this preparation.

From backend with AI_PROVIDER=mock:

```powershell
python -m pytest tests/test_identity_models.py tests/test_alembic_schema.py tests/test_model_relationships.py tests/test_schema_control.py tests/test_verify_schema_migrations_script.py tests/test_verify_auth_sessions_script.py tests/test_auth_api.py tests/test_auth_service.py tests/test_ownership_persistence.py tests/test_mock_auth_support.py tests/test_verify_ownership_script.py -q
```

Result: **384 PASS,2 existing guarded SKIP,2.20s**; one pre-existing dependency
deprecation warning. This baseline is NOT evidence for new credit functionality.
Exact17 spec/Goal path parity,22 acceptance IDs, Todo1–8/F1–F4, document links,
frozen hash, diff/status/staged path checks are preparation acceptance checks.
Fresh static validation passed all of them:90 relative links resolve; exact17
lists match; A01–A22/Todo1–8/F1–F4 are present; recorded SHA matches. Static
`docker compose --env-file .env.example config --quiet` and `git diff --check`
passed. This Compose command did not start or mutate runtime resources.

Frozen local file `.omo/plans/issue-115-g5a-credit-foundation-goal.md`:
SHA256 `ba64dcd7d57cb4f1b5521e43079d464c0c0ac23fcdbf5696c662a861abf39971`.
Not committed with .omo; transfer exact bytes to another machine before execution.

## Result and remaining work

Execution plan fixes exact17 paths, one migration, Todo1–8 and F1–F4; schema/credit
proof twice, auth once, ownership all/four cycles, full Linux and existing
frontend regression. Final delivery requires Ready PR, final-head verify and
both Scan/SBOM success, protected squash actual MERGED. Parent114 remains open.

No G5A execution, runtime proof, PR, CI pass or merge is claimed by preparation.
Next is explicit hash-bearing G5A Goal execution. B/C must resolve their detailed
renewal/expiry/allocation/over-reservation cases before their own Goal freeze.
No live readiness claim: emergency revocation99, actual OAuth/browser/proxy and
machine-metrics authorization remain separate gates.

## Execution checkpoints

### Todo1 — preflight

Starting checkpoint aeafaba; origin/main unchanged6537025; frozen SHA matched.
Existing tracked/index clean and .omo preserved. Local Docker desktop-linux uses
npipe, no remote override; four login-preview containers running and existing
developer/preview DB/media volumes preserved. No private env read; backend dotenv
guard passed. B0 command above:384 PASS/2 existing guarded skips/2.96s.
Scope/diff/status/staged checks passed. A01–A11/A16–A18 map to ORM/migration and
real S proof; A12–A15 to pure policy P; A19 auth A; A20 ownership O; A21 isolated
repeatability; A22 full regression/CI/delivery. Next: Todo2 pure policy tests.

### Todo2 — pure policy

Added immutable Plan catalog and versioned strict integer rate calculations;
signup-anchored half-open cycle bounds normalize aware instants to UTC and use
timedelta floor division rather than floating-point seconds. No DB/provider/IO.
P first failed at expected `credit_policy_missing` assertion (not collection),
then **55 PASS/0.07s** including all7 rates, BIGINT edges, invalid types, no Master
bypass, leap-year/DST-equivalent instants and exact microsecond cycle boundaries.
Scope2/17; diff/status/staged checks passed. Next: four-table schema/migration.

### Todo3 — persistence

Added CreditAccount/Cycle/Grant/LedgerEvent mappings and additive0004. Named
composite ownership FKs, integer/check constraints, base-cycle uniqueness and
operation uniqueness are explicit. Ledger UPDATE/DELETE/TRUNCATE triggers refuse
mutation; downgrade takes5s bounded locks and checks all four tables before DDL.
No old migration/data writer/identity changes. Grant available is derived, not
another stored total. M+P combined **87 PASS/1.18s**. These are structural tests,
not real PostgreSQL proof. Current-head helper compatibility is Todo4; no runtime
test is run at this transitional checkpoint. Code7/17, one new migration; D PASS.

### Todo4 — fixed proof and compatibility

Implemented credential-free proof through fixed stdin source in a newly owned
migrate container (no pytest/image assumption). Added additive data/schema
preservation, metadata parity, direct PostgreSQL rejection probes, append-only
checks, ledger reconstruction/rollback and three lock-observed uniqueness races.
These probes are implemented, **not yet real-runtime verified** at this checkpoint.
Historical0003 proof stays pinned; new auth/ownership heads0004. Monotonic work300s/
cleanup90s gates preserve first failure and sanitized receipts. Reset validates
all populated tables and row snapshots through preview, then every count zero.
H372 PASS/1.76s; M32/0.84s; P55/0.06s; B0 402/2 existing guarded skips/2.17s.
Exact17 paths/new migration1, old revisions unchanged; D PASS. Next S two fresh
projects on this clean committed code, no source edits while proof runs.

### Todo5 — actual isolated PostgreSQL proof

Both invocations of `python scripts/verify_schema_migrations.py --env-file
.env.example --include-reset` passed at immutable code
`b2900a43a3bbfcbbbcb7f6aee8901269d9d656ba` (join command on one line).

| Cycle/project | Work seconds | Cleanup seconds | Result |
|---|---:|---:|---|
| schema-verify-a8cf88cf7bf3 | 141.406 | 1.859 | PASS, credit90/races3 |
| schema-verify-34b401b48ba1 | 119.000 | 1.875 | PASS, credit90/races3 |

Both actual0004; additive populated legacy data/schema preservation, metadata
parity, all credit constraints, append-only, ledger reconstruction/rollback,
lock-observed uniqueness races, populated downgrade and lock refusals PASS.
Original identity/ownership proof retained8 nonempty refusals and lock refusal;
all3 processes refused both stale sentinel and previous0003 and recovered.
Guarded reset preview preserved populated rows; execution left all tables empty.
Every failure code none. Each exact-project independent container/volume/network
inventory0; preview4 and developer/preview pgdata/assets volumes preserved.
Receipts: `.omo/evidence/schema/migration-<project>.json` with the exact projects
above. Total264.140s, below780s; each below300s work/90s cleanup. No rerun/failure
was required. Read-only Docker inventory formatting was corrected from an
unsupported field; it did not affect runtime validation or resources.
Fresh P/M/H combined459 PASS/1.92s; D PASS. Next auth/ownership/full regression.
