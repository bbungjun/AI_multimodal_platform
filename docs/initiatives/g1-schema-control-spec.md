# G1 Schema Control Specification

## Document Status

- Status: `Accepted / Planning Only`
- Last updated: `2026-09-02`
- Parent: [Authentication, Credits, and Master Console Initiative](auth-credits-master-console.md)
- Issue: [#94](https://github.com/bbungjun/AI_multimodal_platform/issues/94)
- Branch: `codex/issue-94-schema-control`
- Goal plan: `.omo/plans/issue-94-g1-schema-control-goal.md`
- Goal plan SHA-256: `a76850315a4ddcd03ec3a7f4e2d01e059024b67884c8ebc0029a568eafd90acb`
- Implementation status: `Planned`
- Provider mode for all verification: `AI_PROVIDER=mock`

This specification is the complete execution input for G1. It intentionally
does not repeat authentication, ownership, credit, or Master-console decisions
that belong to later Goals.

## Goal

Replace runtime-created schema as the operational source of truth with an
Alembic-controlled Postgres schema, provide a fail-closed schema-readiness
interface to every database process, and provide an explicitly guarded local
reset path for the disposable current database.

G1 succeeds when a clean Postgres database can be upgraded, inspected,
downgraded, and upgraded again; Compose runs the migration before application
processes; stale or missing revisions prevent those processes from starting;
and an operator can preview a local reset without exposing credentials or
mutating a production target.

## Why G1 Was Narrowed

The initial initiative outline combined Alembic, safe reset, User, and Session
persistence. Repository inspection showed that schema creation currently spans
`app.db`, backend lifespan, the legacy worker, the outbox dispatcher, Docker
Compose ordering, and the image build. Adding identity persistence in the same
Goal would create a second module and exceed the intended context surface.

G1 therefore owns only the schema-control module. User and Session persistence
moves to G2. Google OAuth moves to G3. This is a scope correction, not an
implementation change.

## Current State and Concrete Problem

Current schema behavior:

- `backend/app/db.py:init_db_schema()` calls `Base.metadata.create_all()`.
- The same function contains manual schema repair for `retry_of_job_id` and the
  active-I2V partial unique index.
- Backend lifespan, the legacy polling worker, and the outbox dispatcher call
  that mutating function during startup.
- The Celery worker assumes the schema exists and has no revision contract.
- Docker Compose has no one-shot migration service or completed-migration
  dependency.
- The backend image copies only the application package, so it cannot execute
  migration artifacts that do not yet exist in the image.
- There is no `alembic_version` record, revision history, or deterministic
  downgrade path.

This creates three operational risks:

1. Every process can attempt DDL during startup.
2. ORM metadata, handwritten startup repair, and the actual database can drift.
3. A new release can accept traffic before its expected schema is present.

## Deep Module and Seam

G1 introduces one schema-control module at the database bootstrap seam.

The external interface is deliberately small:

```python
async def require_current_schema() -> SchemaReadiness:
    """Return the current revision or raise a typed fail-closed error."""

async def plan_local_reset(expected_database: str) -> ResetPlan:
    """Return a redacted, non-mutating description of the exact target."""

async def execute_local_reset(plan: ResetPlan, confirmation: str) -> ResetResult:
    """Reset only the validated local database, then upgrade to Alembic head."""
```

Alembic remains the operator adapter for `upgrade`, `downgrade`, `current`, and
`heads`. Application processes do not call Alembic upgrades and never execute
DDL. They call only `require_current_schema()`.

The interface includes these error modes:

| Error | Condition | Process behavior |
|---|---|---|
| `schema_version_table_missing` | `alembic_version` does not exist | Startup fails before work begins. |
| `schema_revision_missing` | Version table has no revision | Startup fails. |
| `schema_revision_outdated` | Database revision differs from the single code head | Startup fails and reports safe revision IDs. |
| `schema_multiple_heads` | Code or database resolves to more than one head | Startup fails. |
| `schema_unreachable` | Database cannot be queried | Existing health/startup failure behavior remains fail-closed. |
| `reset_target_forbidden` | Environment or target is not explicitly local/test | No mutation. |
| `reset_confirmation_mismatch` | Confirmation does not match the exact database | No mutation. |

No interface result or error may contain a password, full `DATABASE_URL`, OAuth
value, prompt, provider response, or filesystem absolute path.

## Alembic Design

### Layout

```text
backend/
├── alembic.ini
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_generation_baseline.py
└── app/
    ├── db.py
    └── schema_control.py
```

- Add Alembic as a bounded backend runtime dependency.
- `migrations/env.py` imports `Base.metadata` and all mapped models.
- The database URL comes from `Settings.database_url`; it is not committed to
  `alembic.ini` and is never printed.
- Use the existing async SQLAlchemy/asyncpg connection path.
- Require exactly one Alembic head.
- Enable type comparison so model/migration type drift is detectable.
- Revision identifiers are stable and descriptive; G1 begins with
  `0001_generation_baseline`.
- The Docker runtime image copies `alembic.ini` and `migrations/` so the exact
  code image also carries the exact schema revision.

### Baseline Contents

The baseline migration reproduces the current Postgres schema only:

- Tables: `jobs`, `assets`, `prompt_enhancements`, `outbox_events`.
- Native enums: `generation_mode`, `job_state`, `asset_kind`,
  `outbox_event_status`.
- Existing foreign keys and delete behavior, including:
  - Job to Prompt Enhancement;
  - parent and retry Job self-references;
  - Job to source Asset;
  - Asset to Job.
- Existing indexes, including `ix_jobs_retry_of_job_id` and
  `uq_jobs_active_i2v_source_asset` with its exact active-state predicate.
- Existing JSONB, timestamp-with-time-zone, UUID, boolean, and numeric types.

The migration does not create User, Session, Plan, Credit, Usage, Reservation,
Audit, or synthetic-data tables. Those schemas belong to later Goals.

The downgrade removes objects in dependency-safe order and explicitly removes
native Postgres enum types. A downgrade must not leave application tables or
initiative-owned enum types behind in the isolated verification database.

## Runtime Startup Contract

Docker Compose adds a one-shot `migrate` service using the backend image:

```text
db healthy
   ↓
migrate: alembic upgrade head
   ↓ service_completed_successfully
backend ─ worker ─ dispatcher
```

- `migrate` receives only the database settings required for migration.
- It does not receive Google credentials, provider configuration, or asset
  storage mounts.
- Backend, Celery worker, and dispatcher do not start unless migration exits 0.
- Each process independently calls `require_current_schema()` before serving,
  polling, consuming, or dispatching work. Compose ordering is not treated as
  the only correctness mechanism.
- The Celery container uses a fixed startup command that runs the schema-check
  CLI and `exec`s Celery only after success. It does not rely on a Celery signal
  exception to abort startup. The official
  [Celery worker-signal documentation](https://docs.celeryq.dev/en/stable/userguide/signals.html#worker-signals)
  defines lifecycle timing, but G1 keeps process-abort behavior in an explicit,
  directly testable command contract.
- `Base.metadata.create_all()` and handwritten startup DDL are removed.
- The existing manual retry-column and I2V-index repair SQL moves into the
  baseline revision and is deleted from runtime code.
- Readiness checks remain read-only. They do not silently upgrade a database.

GKE workloads are currently paused and AWS is destroyed. G1 does not mutate
cloud infrastructure or resume a deployment. After G1, a future cloud rollout
is No-Go until its release workflow runs the image's migration command before
application rollout. That rollout integration is recorded as a deployment
follow-up rather than hidden inside process startup.

## Safe Local Reset Contract

The current data is disposable, but reset remains a destructive operation and
must be guarded.

Default behavior is preview-only. A reset can execute only when all conditions
are true:

1. `APP_ENV` is exactly `local` or `test`.
2. The connected database reports the same database name supplied by
   `--expected-database`.
3. The target host is `db`, `localhost`, or `127.0.0.1`.
4. `--execute` is present.
5. `--confirm` exactly equals `RESET:<database-name>`.

Preview output contains only:

- environment name;
- dialect;
- allowlisted host alias;
- port;
- database name;
- current safe revision or `unversioned`;
- tables and row counts scheduled for deletion;
- planned target revision.

Execution resets only the selected database's `public` schema, recreates it for
the current database owner, and applies `alembic upgrade head`. It does not drop
the database, delete Docker volumes, remove asset files, touch Redis, or invoke
cloud commands. Failure before upgrade completion returns nonzero and leaves a
clear recovery command; it never reports success from a partial reset.

The reset command is never invoked automatically by application startup,
Compose startup, tests against the developer's normal project, or CI.

## Anticipated Change Map

The executor must confirm the map from the fresh G1 branch before coding.

Production and configuration zones:

- `backend/pyproject.toml`
- `backend/Dockerfile`
- `backend/alembic.ini`
- `backend/migrations/`
- `backend/app/db.py`
- new `backend/app/schema_control.py`
- `backend/app/main.py`
- `backend/app/worker.py`
- `backend/app/services/jobs/outbox_dispatcher.py`
- `backend/app/config.py`
- `.env.example`
- `docker-compose.yml`

Focused test zones:

- new `backend/tests/test_alembic_schema.py`
- new `backend/tests/test_schema_control.py`
- existing startup and Compose contract tests directly invalidated by the
  interface rename or worker command guard

Documentation zones at closeout:

- this specification
- parent initiative status row
- `docs/current-work.md`
- `docs/testing.md`
- `docs/runbooks/local-mock.md`
- one Issue-specific portfolio record after the Issue number exists

If implementation needs a new authentication route, User/Session table,
frontend file, cloud resource, second migration, or more than 20 non-document
changed paths, stop and split before coding.

## TDD Execution Order

### Phase 1: Migration packaging

Write failing tests that require:

- Alembic is installed and configuration resolves through application settings;
- exactly one head exists;
- the backend image contains migration configuration and revision files;
- Compose has one `migrate` service with the required dependency ordering;
- the migration service has no provider credentials or asset volume.

Implement only packaging and static contracts, then run focused tests and
Compose config validation.

### Phase 2: Baseline round trip

Against a uniquely named isolated Compose project and Postgres volume:

1. Start only its database.
2. Run `alembic upgrade head`.
3. Inspect exact tables, columns, foreign keys, indexes, enum values, and head.
4. Run `alembic downgrade base`.
5. Verify application tables and native enums are gone.
6. Run `alembic upgrade head` again and repeat the schema assertions.
7. Tear down only the validated isolated project and volume.

Do not reuse the developer's normal Compose project, database, or volumes for
this automated test.

### Phase 3: Read-only startup readiness

Write failing interface tests for current, missing, outdated, multiple-head,
and unreachable states. Replace runtime DDL with `require_current_schema()` and
update backend, dispatcher, legacy worker, and Celery worker startup tests.

The failure assertion must prove no `CREATE`, `ALTER`, `DROP`, or migration
command was attempted by the application process.

### Phase 4: Guarded reset

Write preview and refusal tests before execution support. Test every guard
independently. Execute the destructive path only against another isolated
database created for the test, then prove it is at head and contains no prior
rows.

### Phase 5: Closeout

Run focused tests, the isolated migration round trip, backend full pytest,
frontend lint/build, both Compose config checks, and repository hygiene. Update
the initiative row and portfolio evidence only with observed results.

## Acceptance Criteria

### Schema correctness

- `alembic heads` returns exactly `0001_generation_baseline`.
- A clean isolated Postgres database passes upgrade, downgrade, and re-upgrade.
- Schema inspection matches every current model table, enum, foreign key, and
  required index.
- Alembic metadata comparison reports no drift after upgrade.
- Runtime code contains no `Base.metadata.create_all()` or handwritten startup
  `ALTER TABLE`/`CREATE INDEX` path.

### Startup safety

- `migrate` completes before backend, worker, and dispatcher start in Compose.
- Missing or stale schema makes each database process exit nonzero before work.
- A current schema allows the normal mock golden path to complete.
- No application startup path performs migration or destructive DDL.

### Reset safety

- Preview is the default and performs zero mutation.
- Production environment, remote host, wrong database, missing execute flag,
  and wrong confirmation each fail independently.
- Output is redacted and contains no database password or full URL.
- The isolated happy path deletes its rows and returns the exact head revision.
- No database volume, asset volume, Redis state, or cloud resource is deleted.

### Regression and documentation

- Backend full pytest passes except a separately evidenced pre-existing failure.
- Frontend lint and build pass even though G1 has no frontend changes.
- `docker compose --env-file .env.example config --quiet` passes.
- `docker compose config --quiet` is run only when the local `.env` is safe and
  intentionally selected; its contents are never printed.
- `git diff --check` passes.
- The portfolio record distinguishes `Implemented`, `Mock Verified`, and the
  deferred cloud rollout migration integration.

## Exact Verification Commands

The final executor may replace only the isolated project suffix with a fresh,
collision-checked value.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_alembic_schema.py tests/test_schema_control.py -q
python -m alembic heads
cd ..

docker compose --env-file .env.example config --quiet
python scripts/verify_local.py
git diff --check
git status --short --branch
git diff --cached --name-only
```

The implementation plan must add `alembic current` and the exact isolated
Postgres round-trip command only after deciding its safe project-name generator
and isolated `DATABASE_URL`. It must not substitute the normal developer
database for that verification.

## Rollback

- Before merge: revert only the G1 branch commits; do not reset unrelated dirty
  work.
- After merge but before any shared deployment: application rollback requires
  rolling code and database revision back together on an isolated or explicitly
  approved target.
- The local database contains disposable data, so the preferred local rollback
  is guarded reset to the prior code revision, not manual table editing.
- Cloud rollback is out of G1. No cloud environment may be resumed with a code
  revision whose expected Alembic head differs from the deployed database.

## Stop Conditions

Stop implementation and revise this specification if any occurs:

- the fresh branch is not based on the documentation revision containing this
  specification;
- the existing database must unexpectedly be preserved;
- more than one migration is required;
- User, Session, Plan, Credit, or ownership columns become necessary for G1;
- a cloud mutation or paid provider call appears necessary;
- Alembic cannot reproduce the existing partial index or circular foreign-key
  behavior without changing product semantics;
- the change map exceeds the initiative's context limit;
- any reset target cannot be proven local and exact.

## Non-Goals

- No Google OAuth client or callback.
- No User, Session, Role, Plan, Credit, Usage, Reservation, or Audit models.
- No ownership filtering.
- No frontend change.
- No synthetic seed data.
- No live GKE/AWS/Vertex execution.
- No preservation, stamping, or backfill of the current database.
- No automatic migration from application startup.

## G2 Handoff Interface

G2 may assume only these G1 guarantees:

- `alembic upgrade head` is the single schema mutation path;
- the database is at one known revision before application code starts;
- every process fails closed on a stale revision;
- a guarded local reset exists for disposable data;
- adding User and Session persistence requires exactly one new Alembic revision
  and does not modify schema-control internals.

G2 must not depend on G1 implementation details beyond this interface.
