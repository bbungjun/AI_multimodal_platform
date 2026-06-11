# I2V Concurrency Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate active image-to-video jobs for the same source image even under repeated clicks, client retries, or near-simultaneous API requests.

**Architecture:** Keep the current API-level duplicate check, but make it concurrency-aware with a source asset row lock. Add a Postgres partial unique index as the database-level final guard, and map any resulting uniqueness violation back to `409 Conflict`.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, Postgres, pytest, Docker Compose mock runtime.

---

## Current Context

The current API already rejects a new `i2v` request when an active `i2v` job exists for the same `source_asset_id`. That is useful for normal repeated clicks, but it is still a check-then-insert flow:

```text
request A: check active i2v -> none
request B: check active i2v -> none
request A: insert pending i2v
request B: insert pending i2v
```

The production-grade target is:

```text
request A: lock source asset row -> check -> insert -> commit
request B: waits on same source asset row -> check -> sees A's job -> 409
```

And if any route bypasses the lock, Postgres still rejects the duplicate through a partial unique index.

## File Structure

- Modify: `backend/app/api/generations.py`
  - Use a locked source asset lookup for `i2v` creation.
  - Re-check active `i2v` jobs while the source asset row lock is held.
  - Convert unique-index `IntegrityError` into the same public `409 Conflict`.
- Create: `backend/app/services/jobs/i2v_guard.py`
  - Own the active-state definition, source asset lock statement, active job lookup statement, and unique-violation detection.
  - Keep SQL construction testable outside the FastAPI handler.
- Modify: `backend/app/models.py`
  - Add a Postgres partial unique index metadata declaration for active `i2v` jobs.
- Modify: `backend/app/db.py`
  - Add an idempotent schema sync helper for existing local/Postgres databases because this repository currently uses `Base.metadata.create_all()` plus small sync helpers instead of Alembic.
- Modify: `backend/tests/test_generation_api.py`
  - Extend the fake session enough to verify lock ordering and `IntegrityError` handling.
- Create: `backend/tests/test_i2v_guard.py`
  - Test generated SQL for row locking, active job lookup, partial index definition, and duplicate scan SQL.
- Modify: `backend/tests/test_model_relationships.py`
  - Assert the partial unique index exists in model metadata.
- Modify: `docs/job-lifecycle.md`
  - Document the transaction lock and DB constraint roles.
- Modify: `docs/current-work.md`
  - Add a short handoff note after implementation.

## Design Decisions

- Active `i2v` states are all non-terminal job states: `pending`, `enhancing`, `queued`, `generating`, `polling`, and `downloading`.
- Terminal `i2v` states are excluded: `completed`, `failed`, and `cancelled`.
- The lock target is the `assets` row, not the parent `jobs` row. The duplicate rule is keyed by `source_asset_id`, so locking the source asset serializes exactly the requests that conflict with each other.
- The API still returns `409 Conflict` with the existing public message:

```text
An active I2V generation already exists for this source asset.
```

- The partial unique index is Postgres-only. Non-Postgres test dialects may compile SQL, but production runtime is Postgres.
- Because the repository does not currently use Alembic, the first implementation should follow the existing `backend/app/db.py` schema sync pattern. A later deployment phase can replace startup DDL with Alembic or a dedicated migration job.

## Task 1: Extract I2V Guard Statements

**Files:**
- Create: `backend/app/services/jobs/i2v_guard.py`
- Create: `backend/tests/test_i2v_guard.py`
- Modify: `backend/app/api/generations.py`

- [ ] **Step 1: Write tests for the SQL statements**

Create `backend/tests/test_i2v_guard.py` with statement-level tests:

```python
from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.models import Asset, GenerationMode, Job, JobState
from app.services.jobs import i2v_guard


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def test_source_asset_lock_statement_uses_for_update():
    asset_id = uuid4()

    statement = i2v_guard.source_asset_for_update_statement(asset_id)
    sql = _sql(statement)

    assert "from assets" in sql
    assert "where assets.id" in sql
    assert "for update" in sql


def test_active_i2v_job_statement_filters_source_asset_and_active_states():
    asset_id = uuid4()

    statement = i2v_guard.active_i2v_job_statement(asset_id)
    sql = _sql(statement)

    assert "from jobs" in sql
    assert "jobs.mode = 'i2v'" in sql
    assert "jobs.source_asset_id" in sql
    assert "jobs.state in" in sql
    assert "'pending'" in sql
    assert "'polling'" in sql
    assert "'completed'" not in sql
    assert "'failed'" not in sql
    assert "'cancelled'" not in sql
    assert "limit 1" in sql


def test_active_i2v_states_match_non_terminal_contract():
    assert i2v_guard.ACTIVE_I2V_STATES == (
        JobState.PENDING,
        JobState.ENHANCING,
        JobState.QUEUED,
        JobState.GENERATING,
        JobState.POLLING,
        JobState.DOWNLOADING,
    )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_i2v_guard.py -q
```

Expected: fail with `ModuleNotFoundError` or `ImportError` because `app.services.jobs.i2v_guard` does not exist yet.

- [ ] **Step 3: Implement the guard module**

Create `backend/app/services/jobs/i2v_guard.py`:

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select

from app.models import Asset, GenerationMode, Job, JobState


ACTIVE_I2V_STATES: tuple[JobState, ...] = (
    JobState.PENDING,
    JobState.ENHANCING,
    JobState.QUEUED,
    JobState.GENERATING,
    JobState.POLLING,
    JobState.DOWNLOADING,
)

ACTIVE_I2V_DUPLICATE_MESSAGE = (
    "An active I2V generation already exists for this source asset."
)


def source_asset_for_update_statement(source_asset_id: UUID) -> Select[tuple[Asset]]:
    return (
        select(Asset)
        .where(Asset.id == source_asset_id)
        .with_for_update()
    )


def active_i2v_job_statement(source_asset_id: UUID) -> Select[tuple[Job]]:
    return (
        select(Job)
        .where(
            Job.mode == GenerationMode.I2V,
            Job.source_asset_id == source_asset_id,
            Job.state.in_(ACTIVE_I2V_STATES),
        )
        .order_by(Job.updated_at.desc())
        .limit(1)
    )
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_i2v_guard.py -q
```

Expected: all tests in `tests/test_i2v_guard.py` pass.

- [ ] **Step 5: Commit the extraction**

Run:

```powershell
git add backend/app/services/jobs/i2v_guard.py backend/tests/test_i2v_guard.py
git commit -m "refactor: extract i2v concurrency guard statements"
```

## Task 2: Apply Source Asset Transaction Lock In The API

**Files:**
- Modify: `backend/app/api/generations.py`
- Modify: `backend/tests/test_generation_api.py`

- [ ] **Step 1: Write a failing API test for lock-before-check order**

Add a fake result helper that can return `Asset` and `Job` rows:

```python
class FakeScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self) -> list[object]:
        return self.rows
```

Extend `FakeGenerationSession` with `scalar_results` already present. Then add:

```python
async def test_create_i2v_generation_locks_source_asset_before_duplicate_check():
    parent = _job_with_asset()
    source_asset = parent.assets[0]
    session = FakeGenerationSession(
        jobs=[parent],
        scalar_results=[[source_asset], []],
    )

    response = await _post_generation(
        {
            "mode": "i2v",
            "prompt": "animate the desk lamp",
            "model": "veo-3.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "duration_sec": 4,
            "source_asset_id": str(source_asset.id),
        },
        session,
    )

    assert response.status_code == 201
    assert len(session.scalar_statements) >= 2
    lock_sql = str(
        session.scalar_statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    active_check_sql = str(
        session.scalar_statements[1].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "from assets" in lock_sql
    assert "for update" in lock_sql
    assert "from jobs" in active_check_sql
    assert "jobs.mode = 'i2v'" in active_check_sql
```

Import the Postgres dialect at the top of `backend/tests/test_generation_api.py`:

```python
from sqlalchemy.dialects import postgresql
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py::test_create_i2v_generation_locks_source_asset_before_duplicate_check -q
```

Expected: fail because the current code uses `session.get(Asset, source_asset_id)` and does not issue a `FOR UPDATE` statement first.

- [ ] **Step 3: Change the I2V branch to lock the source asset row**

In `backend/app/api/generations.py`, import the guard module:

```python
from app.services.jobs import i2v_guard
```

Replace the `i2v` source asset lookup block with:

```python
        source_asset_id = payload.source_asset_id
        source_asset_result = await session.scalars(
            i2v_guard.source_asset_for_update_statement(source_asset_id)
        )
        source_asset = source_asset_result.first()
        if source_asset is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source asset was not found.",
            )
        if source_asset.kind != AssetKind.IMAGE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source asset must be an image.",
            )
        active_result = await session.scalars(
            i2v_guard.active_i2v_job_statement(source_asset_id)
        )
        if active_result.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=i2v_guard.ACTIVE_I2V_DUPLICATE_MESSAGE,
            )
```

Remove the older `_active_i2v_source_asset_job(...)` helper from `generations.py` after all call sites are replaced.

Update the existing duplicate test setup so the first scalar result is the
locked source asset and the second scalar result is the active duplicate:

```python
session = FakeGenerationSession(
    jobs=[parent],
    scalar_results=[[source_asset], [active_i2v]],
)
```

- [ ] **Step 4: Run the API tests**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py -q
```

Expected: all generation API tests pass.

- [ ] **Step 5: Commit the API lock**

Run:

```powershell
git add backend/app/api/generations.py backend/tests/test_generation_api.py
git commit -m "feat: lock i2v source asset during creation"
```

## Task 3: Add Postgres Partial Unique Index Metadata And Schema Sync

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/db.py`
- Modify: `backend/tests/test_model_relationships.py`
- Modify: `backend/tests/test_i2v_guard.py`

- [ ] **Step 1: Write metadata tests for the index**

Add to `backend/tests/test_model_relationships.py`:

```python
from app.services.jobs import i2v_guard


def test_job_has_active_i2v_source_asset_partial_unique_index():
    index = next(
        index
        for index in Job.__table__.indexes
        if index.name == "uq_jobs_active_i2v_source_asset"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["source_asset_id"]
    where = str(
        index.dialect_options["postgresql"]["where"].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "jobs.mode = 'i2v'" in where
    assert "jobs.source_asset_id is not null" in where
    assert "jobs.state in" in where
    assert "'polling'" in where
    assert "'completed'" not in where


def test_job_active_i2v_index_states_match_guard_states():
    assert ACTIVE_I2V_INDEX_STATES == i2v_guard.ACTIVE_I2V_STATES
```

Import the dialect:

```python
from sqlalchemy.dialects import postgresql

from app.models import ACTIVE_I2V_INDEX_STATES
```

- [ ] **Step 2: Run metadata test to verify RED**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_model_relationships.py::test_job_has_active_i2v_source_asset_partial_unique_index -q
```

Expected: fail because the index does not exist yet.

- [ ] **Step 3: Add the model index**

In `backend/app/models.py`, add `and_` to the SQLAlchemy imports:

```python
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, and_
```

After the `Job` class definition and before `Asset`, add:

```python
ACTIVE_I2V_INDEX_STATES: tuple[JobState, ...] = (
    JobState.PENDING,
    JobState.ENHANCING,
    JobState.QUEUED,
    JobState.GENERATING,
    JobState.POLLING,
    JobState.DOWNLOADING,
)

Index(
    "uq_jobs_active_i2v_source_asset",
    Job.source_asset_id,
    unique=True,
    postgresql_where=and_(
        Job.mode == GenerationMode.I2V,
        Job.source_asset_id.is_not(None),
        Job.state.in_(ACTIVE_I2V_INDEX_STATES),
    ),
)
```

- [ ] **Step 4: Add schema sync tests**

Add to `backend/tests/test_i2v_guard.py`:

```python
def test_duplicate_scan_sql_targets_active_i2v_rows_only():
    sql = i2v_guard.ACTIVE_I2V_DUPLICATE_SCAN_SQL.lower()

    assert "from jobs" in sql
    assert "mode = 'i2v'" in sql
    assert "source_asset_id is not null" in sql
    assert "state in" in sql
    assert "group by source_asset_id" in sql
    assert "having count(*) > 1" in sql
    assert "limit 1" in sql


def test_create_index_sql_is_partial_unique_index():
    sql = i2v_guard.ACTIVE_I2V_UNIQUE_INDEX_SQL.lower()

    assert "create unique index" in sql
    assert "uq_jobs_active_i2v_source_asset" in sql
    assert "on jobs (source_asset_id)" in sql
    assert "where mode = 'i2v'" in sql
    assert "state in" in sql
    assert "completed" not in sql
```

- [ ] **Step 5: Add SQL constants to the guard module**

Add to `backend/app/services/jobs/i2v_guard.py`:

```python
ACTIVE_I2V_STATE_SQL = ", ".join(f"'{state.value}'" for state in ACTIVE_I2V_STATES)

ACTIVE_I2V_DUPLICATE_SCAN_SQL = f"""
SELECT source_asset_id, COUNT(*) AS active_count
FROM jobs
WHERE mode = 'i2v'
  AND source_asset_id IS NOT NULL
  AND state IN ({ACTIVE_I2V_STATE_SQL})
GROUP BY source_asset_id
HAVING COUNT(*) > 1
LIMIT 1
"""

ACTIVE_I2V_UNIQUE_INDEX_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_i2v_source_asset
ON jobs (source_asset_id)
WHERE mode = 'i2v'
  AND source_asset_id IS NOT NULL
  AND state IN ({ACTIVE_I2V_STATE_SQL})
"""
```

- [ ] **Step 6: Add schema sync helper**

Call the helper during initialization:

```python
        await conn.run_sync(_sync_jobs_retry_of_schema)
        await conn.run_sync(_sync_jobs_active_i2v_unique_index)
```

Add:

```python
def _sync_jobs_active_i2v_unique_index(conn) -> None:
    from app.services.jobs import i2v_guard

    inspector = inspect(conn)
    table_names = set(inspector.get_table_names())
    if "jobs" not in table_names:
        return

    if conn.dialect.name != "postgresql":
        return

    indexes = {index["name"] for index in inspector.get_indexes("jobs")}
    if "uq_jobs_active_i2v_source_asset" in indexes:
        return

    duplicate = conn.execute(
        text(i2v_guard.ACTIVE_I2V_DUPLICATE_SCAN_SQL)
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot create active I2V uniqueness index while duplicate active "
            "I2V jobs exist."
        )

    conn.execute(text(i2v_guard.ACTIVE_I2V_UNIQUE_INDEX_SQL))
```

- [ ] **Step 7: Run targeted tests**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_i2v_guard.py tests/test_model_relationships.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 8: Commit the DB guard**

Run:

```powershell
git add backend/app/models.py backend/app/db.py backend/app/services/jobs/i2v_guard.py backend/tests/test_i2v_guard.py backend/tests/test_model_relationships.py
git commit -m "feat: add active i2v uniqueness constraint"
```

## Task 4: Convert Unique Index Violations To 409 Conflict

**Files:**
- Modify: `backend/app/api/generations.py`
- Modify: `backend/app/services/jobs/i2v_guard.py`
- Modify: `backend/tests/test_generation_api.py`

- [ ] **Step 1: Write failing test for commit-time uniqueness violation**

Extend `FakeGenerationSession` with optional commit failure:

```python
class FakeGenerationSession:
    def __init__(
        self,
        *,
        prompt_enhancement: PromptEnhancement | None = None,
        jobs: list[Job] | None = None,
        scalar_results: list[list[object]] | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.commit_error = commit_error
```

Update `commit`:

```python
    async def commit(self) -> None:
        self.commit_count += 1
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error
```

Add rollback support:

```python
    async def rollback(self) -> None:
        self.events.append("rollback")
```

Add the test:

```python
async def test_create_i2v_generation_maps_unique_index_error_to_conflict():
    parent = _job_with_asset()
    source_asset = parent.assets[0]
    integrity_error = IntegrityError(
        statement="INSERT INTO jobs ...",
        params={},
        orig=Exception("uq_jobs_active_i2v_source_asset"),
    )
    session = FakeGenerationSession(
        jobs=[parent],
        scalar_results=[[source_asset], []],
        commit_error=integrity_error,
    )

    response = await _post_generation(
        {
            "mode": "i2v",
            "prompt": "animate the desk lamp",
            "model": "veo-3.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "duration_sec": 4,
            "source_asset_id": str(source_asset.id),
        },
        session,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "An active I2V generation already exists for this source asset."
    )
    assert "rollback" in session.events
```

Import `IntegrityError`:

```python
from sqlalchemy.exc import IntegrityError
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py::test_create_i2v_generation_maps_unique_index_error_to_conflict -q
```

Expected: fail with unhandled `IntegrityError`.

- [ ] **Step 3: Add unique-violation detection**

Add to `backend/app/services/jobs/i2v_guard.py`:

```python
ACTIVE_I2V_UNIQUE_INDEX_NAME = "uq_jobs_active_i2v_source_asset"


def is_active_i2v_unique_violation(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    text = str(exc)
    return (
        constraint_name == ACTIVE_I2V_UNIQUE_INDEX_NAME
        or ACTIVE_I2V_UNIQUE_INDEX_NAME in text
        or (orig is not None and ACTIVE_I2V_UNIQUE_INDEX_NAME in str(orig))
    )
```

- [ ] **Step 4: Catch the commit error in create_generation**

In `backend/app/api/generations.py`, import:

```python
from sqlalchemy.exc import IntegrityError
```

Replace the final commit:

```python
    session.add(job)
    add_job_dispatch_event(session, job.id, reason="generation_created")
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if (
            generation_mode == GenerationMode.I2V
            and i2v_guard.is_active_i2v_unique_violation(exc)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=i2v_guard.ACTIVE_I2V_DUPLICATE_MESSAGE,
            ) from exc
        raise
```

- [ ] **Step 5: Run generation API tests**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py -q
```

Expected: all generation API tests pass.

- [ ] **Step 6: Commit error mapping**

Run:

```powershell
git add backend/app/api/generations.py backend/app/services/jobs/i2v_guard.py backend/tests/test_generation_api.py
git commit -m "fix: map active i2v uniqueness races to conflict"
```

## Task 5: Runtime Smoke For Duplicate I2V Requests

**Files:**
- Create: `scripts/smoke_mock_i2v_duplicate_guard.py`
- Modify: `docs/testing.md`

- [ ] **Step 1: Write smoke script**

Create `scripts/smoke_mock_i2v_duplicate_guard.py` that:

1. Starts compose services when `--compose` is passed.
2. Creates a mock T2I generation.
3. Polls until completed.
4. Reads the first image asset id.
5. Sends two I2V create requests for the same asset with `asyncio.gather`.
6. Asserts one request returns `201` and the other returns `409`.
7. Cleans up created jobs.

The key assertion should be:

```python
status_codes = sorted([first.status_code, second.status_code])
if status_codes != [201, 409]:
    raise SmokeError(f"Expected one created I2V and one conflict, got {status_codes}.")
```

- [ ] **Step 2: Run smoke script**

Run:

```powershell
python scripts\smoke_mock_i2v_duplicate_guard.py --compose --env-file .env.example --timeout-sec 90
```

Expected output:

```text
SMOKE PASSED
```

- [ ] **Step 3: Document the smoke**

In `docs/testing.md`, add the command under mock runtime smoke checks:

```powershell
python scripts\smoke_mock_i2v_duplicate_guard.py --compose --env-file .env.example --timeout-sec 90
```

- [ ] **Step 4: Commit smoke coverage**

Run:

```powershell
git add scripts/smoke_mock_i2v_duplicate_guard.py docs/testing.md
git commit -m "test: add i2v duplicate guard smoke"
```

## Task 6: Final Verification And Docs

**Files:**
- Modify: `docs/job-lifecycle.md`
- Modify: `docs/current-work.md`

- [ ] **Step 1: Update lifecycle docs**

In `docs/job-lifecycle.md`, update the I2V duplicate guard paragraph to say:

```markdown
I2V creation uses two layers of protection. The API first locks the source
asset row and checks for an active `i2v` job using that asset, returning
`409 Conflict` before creating another job. Postgres also keeps a partial
unique index on active `i2v` rows by `source_asset_id`, so concurrent or
unexpected write paths cannot create more than one active Veo operation for
the same image.
```

- [ ] **Step 2: Update current handoff**

In `docs/current-work.md`, add a short completed-work bullet:

```markdown
- Hardened I2V duplicate protection with source asset row locking, a Postgres
  partial unique index for active I2V jobs, and conflict mapping for commit-time
  uniqueness races.
```

- [ ] **Step 3: Run full verification**

Run:

```powershell
git diff --check
python scripts\verify_local.py
python scripts\smoke_mock_i2v_duplicate_guard.py --compose --env-file .env.example --timeout-sec 90
git status --short --branch
git diff --cached --name-only
```

Expected:

- `git diff --check` prints no whitespace errors.
- `python scripts\verify_local.py` ends with `VERIFY PASSED`.
- duplicate guard smoke ends with `SMOKE PASSED`.
- `git status --short --branch` only shows intentional files before commit.
- `git diff --cached --name-only` is empty before final staging.

- [ ] **Step 4: Commit docs**

Run:

```powershell
git add docs/job-lifecycle.md docs/current-work.md
git commit -m "docs: document i2v concurrency guard"
```

- [ ] **Step 5: Push**

Run:

```powershell
git push origin main
```

## Review Checklist

- The lock is held while checking active jobs and inserting the new job.
- The DB index filters exactly `mode='i2v'`, non-null `source_asset_id`, and active states.
- The same public `409 Conflict` message is used for both pre-insert duplicate detection and commit-time uniqueness violations.
- Existing terminal jobs do not block new I2V work.
- No Vertex calls are introduced in tests or smoke; all verification uses `AI_PROVIDER=mock`.
- The implementation keeps provider-specific behavior out of the API guard.

## Plan Inspection Result

- Spec coverage: transaction lock, partial unique index, commit-time race handling, tests, smoke, and docs are all mapped to tasks.
- Completion-marker scan: no reserved planning tokens or incomplete task markers remain outside the intentional checkbox steps.
- Type consistency: active state constants use `JobState` in both guard and model metadata, and Task 3 includes a drift test to compare both tuples.
- Import risk found and fixed: `db.py` must import `i2v_guard` inside `_sync_jobs_active_i2v_unique_index(...)`, not at module import time, to avoid `db -> guard -> models -> db` circular import risk.
- Deployment caveat: the plan intentionally follows the repository's current startup schema sync style. Before multi-replica AWS deployment, this should move to Alembic or a one-shot migration job.

## Known Trade-Off

This plan follows the repository's current startup schema sync style instead of introducing Alembic. That keeps the change small and consistent with the existing app, but a later AWS deployment phase should move schema evolution into explicit migrations or a one-shot migration job before running multiple app replicas.
