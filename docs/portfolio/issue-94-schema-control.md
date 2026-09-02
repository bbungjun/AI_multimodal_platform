# Issue #94: Schema Control and Safe Local Reset

## Evidence Status

- Overall: `Mock Verified`
- Specification: `Accepted`
- Implementation: `Implemented` on branch `codex/issue-94-schema-control`
- Static and unit verification: `Passed`
- Isolated Postgres and mock runtime verification: `Passed`
- Cloud verification: `Deferred / No-Go`
- Delivery: [Draft PR #95](https://github.com/bbungjun/AI_multimodal_platform/pull/95)

This record claims `Mock Verified`, not `Live Verified`. No cloud deployment,
credential, Vertex request, or paid provider path was used.

## Background and Problem

The application previously let backend, legacy worker, and outbox dispatcher
startup execute `Base.metadata.create_all()` plus handwritten retry-column and
partial-index repair. The Celery process had no revision check, and Compose
ordered application startup after Postgres health rather than after migration
completion.

That produced three operational risks:

1. multiple runtime processes could race to mutate schema;
2. ORM metadata, handwritten repair SQL, and the database could drift;
3. a new release could begin work against an incompatible revision.

The current local data is disposable, but a generic reset command would have
introduced a second risk: accidentally targeting a remote or incorrectly named
database.

## Observation and Root-Cause Analysis

Repository inspection found the mutation path in `backend/app/db.py`, three
startup callers, no packaged migration revision, and no one-shot Compose
migration service. The existing test suite also encoded the runtime-DDL helper
as desired behavior, so removing implementation without replacing that test
would have left the obsolete contract in place.

Fresh preflight expanded the expected non-document path map from 20 to 22. The
two omitted paths were the isolated Postgres verifier and deletion of the old
runtime-DDL test. The user approved this G1-only exception; the single-module
and single-migration limits did not change.

## Resolution and Design Rationale

G1 adds one schema-control module at the database bootstrap seam. Its external
interface remains three asynchronous operations:

```python
await require_current_schema()
await plan_local_reset(expected_database)
await execute_local_reset(plan, confirmation=confirmation)
```

The implementation hides Alembic head resolution, read-only database revision
inspection, reset target parsing, live database-name verification, fixed-table
row counts, destructive DDL, upgrade, and final readiness behind that small
interface. Backend, legacy worker, and dispatcher only call
`require_current_schema()`; they do not know Alembic or execute schema DDL.

The baseline revision reproduces only the existing generation schema: four
tables, four native enums, current foreign keys and indexes, and the active-I2V
partial unique predicate. No identity, OAuth, role, plan, credit, usage, or
ownership schema was added.

Compose now runs a finite `migrate` process after database health and gates
backend, worker, and dispatcher on its successful completion. The Celery
command also runs the read-only schema check before `exec celery`, preserving
fail-closed behavior when Compose ordering is bypassed.

Reset defaults to preview and requires all of the following before mutation:

- `APP_ENV` exactly `local` or `test`;
- host exactly `db`, `localhost`, or `127.0.0.1`;
- URL database, expected database, and live `current_database()` all equal;
- explicit execute mode;
- confirmation exactly `RESET:<database>`.

It resets only `public`, upgrades to head, and rechecks readiness. A failed
post-reset upgrade returns `reset_partial_failure` plus the safe recovery
command instead of reporting a rollback or success.

## Verification Evidence

Tested implementation checkpoint: `6aa8a1f` and later documentation-only
changes on the same branch.

| Verification | Result | Evidence boundary |
|---|---|---|
| `python -m alembic heads` | PASS | Exactly `0001_generation_baseline (head)` |
| Alembic offline `upgrade head --sql` | PASS | PostgreSQL transactional DDL compiled through version insert |
| Alembic packaging contracts | PASS | 4 tests |
| Focused schema-control suite | PASS | 33 tests |
| Compose config with `.env.example` | PASS | No provider or credential dependency in `migrate` |
| Backend full pytest | PARTIAL | 385 passed; one pre-existing Windows Bash path-conversion failure |
| Frontend typecheck/lint | PASS | Exit 0 |
| Frontend production build | PASS | 95 modules transformed |
| Runtime image and packaged head | PASS | Backend image built; exactly one packaged head |
| Isolated migration/reset cycle 1 | PASS | `g1-schema-96996ab175ba`; round trip, drift refusal/recovery, preview, reset, cleanup |
| Isolated migration/reset cycle 2 | PASS | `g1-schema-fa2916314600`; same checks repeated on a fresh volume |
| Mock product golden path | PASS | `g1-schema-golden01`; prompt enhancement, generation, PNG/range serving, job cleanup |
| Exact cleanup | PASS | Zero remaining `g1-schema-*` projects and volumes |

The known backend failure is
`test_release_script_guards_plan_scope_and_uses_terraform_rollback`. Windows
passes a drive-letter path to WSL Bash without conversion; the failure predates
G1 and is outside its changed paths. It was not skipped or weakened.

The first runtime attempt exposed two packaging-fidelity defects before final
verification: custom migration constraint names differed from the existing
SQLAlchemy-created schema, and the installed application could not find
`/app/alembic.ini`. The baseline now preserves PostgreSQL's existing unnamed
constraint behavior, index inventory excludes constraint-owned indexes, and
schema control resolves both source-tree and runtime-image config layouts.
Windows Docker output is decoded explicitly as UTF-8 with replacement so the
verifier remains deterministic across host code pages.

## Result and Impact

At the mock-verified evidence level:

- runtime source contains no `create_all`, handwritten `ALTER TABLE`, or
  startup `CREATE INDEX` path;
- missing, empty, outdated, multiple-head, and unreachable states map to stable
  safe error codes;
- three database processes share one readiness interface;
- the code image carries the exact migration configuration and revision;
- reset plans contain no password or full database URL;
- production, remote-host, wrong-database, live-name mismatch, and wrong-
  confirmation tests prove zero mutation;
- backend, worker, and dispatcher each exited nonzero on an intentionally stale
  revision, then passed after head restoration;
- two independent real Postgres 16 volumes completed the full migration and
  guarded reset contract;
- the existing mock generation workflow remained operational end to end;
- G2 can add User and Session persistence as one new revision without changing
  schema-control internals.

## Rollback and Recovery

Before merge, revert the Issue #94 commits in reverse order; do not reset
unrelated work. After a shared deployment, code and schema revisions must be
rolled back together on an explicitly approved target. G1 does not automate a
cloud rollback.

If local reset completes its schema drop but Alembic upgrade fails, run:

```powershell
docker compose run --rm migrate python -m alembic upgrade head
```

Then run the schema check before starting application processes.

## Remaining Risks and Next Steps

1. Keep cloud migration orchestration `Deferred / No-Go` until a separate
   deployment Issue defines rollout and rollback ordering.
2. Fix the pre-existing Windows Bash path conversion test in its own Issue; it
   is unrelated to G1 and was not skipped or weakened here.
3. After G1 merges, start G2 with one User/Session migration and consume only
   the documented schema-control interface.
