# Issue #94: Schema Control and Safe Local Reset

## Evidence Status

- Overall: `Planned`
- Specification: `Accepted`
- Implementation: `Not started`
- Runtime verification: `Not run`
- Cloud verification: `Deferred / No-Go`

## Background and Problem

CreativeOps Studio currently lets backend and dispatcher startup execute
`Base.metadata.create_all()` plus handwritten schema repair. This makes several
runtime processes potential DDL owners, provides no revision history, and can
allow a release to start against a schema it did not explicitly verify.

Repository inspection also showed that the default Celery worker assumes the
schema exists, while Docker Compose has no migration-completion dependency.
The current local data is disposable, but deleting it without an exact target
guard would create a separate operational risk.

## Observed Evidence

- `backend/app/db.py` owns `create_all()` and manual retry-column/I2V-index DDL.
- Backend lifespan, the legacy worker, and the outbox dispatcher call the
  mutating initializer.
- The backend image does not contain Alembic configuration or revisions.
- Compose starts database processes after Postgres health, not after a schema
  revision gate.
- There is no `alembic_version` table or downgrade path.

These are code observations only. No database mutation or runtime failure drill
has been executed for Issue #94.

## Accepted Decision

G1 introduces one schema-control module with a small interface for read-only
revision readiness and guarded local reset planning/execution. Alembic becomes
the only schema mutation adapter. Application processes check the revision and
fail closed; they do not run migrations.

Compose will execute one migration container before backend, worker, and
dispatcher. The Celery command will run a schema-check CLI before `exec` rather
than relying on a startup signal exception whose abort behavior is not an
explicit project contract.

The full contract is in
[G1 Schema Control Specification](../initiatives/g1-schema-control-spec.md).

## Planned Verification

- clean isolated Postgres upgrade, schema inventory, downgrade, and re-upgrade;
- metadata/migration drift check;
- missing, outdated, multiple-head, and unreachable readiness failures;
- Compose migration ordering and worker preflight;
- preview-only reset and every independent refusal guard;
- isolated reset happy path with redacted output;
- full mock regression, frontend build, Compose validation, and hygiene checks.

## Expected Outcome

- one reviewable schema history instead of startup DDL;
- deterministic release ordering in local Compose;
- processes that reject an incompatible schema before doing work;
- a reset procedure that is useful for the disposable local database without
  becoming a generic destructive database command;
- a stable migration interface for G2 User and Session persistence.

## Remaining Risks

- GKE is paused and AWS is destroyed, so cloud migration orchestration is not
  part of G1 and remains No-Go before any future rollout.
- The baseline must preserve the existing circular foreign keys and partial
  I2V uniqueness predicate exactly.
- The current database is unversioned and must not be passed to automated
  round-trip tests.
- Every result above remains planned until implementation evidence replaces it.
