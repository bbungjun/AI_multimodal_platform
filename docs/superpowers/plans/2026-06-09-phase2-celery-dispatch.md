# Phase 2 Celery Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redis를 Celery broker로 도입하고, `job_id`-only task dispatch로 generation job을 처리하되 Postgres를 계속 job source of truth로 유지한다.

**Architecture:** Phase 1의 API/worker process separation을 baseline으로 사용한다. API는 job을 Postgres에 commit한 뒤 dispatch adapter를 통해 Celery task를 발행하고, Celery worker는 task payload를 신뢰하지 않고 Postgres에서 최신 job을 다시 조회한다. Redis/Celery는 dispatch layer이며, 사용자-visible 상태 저장소는 아니다.

**Tech Stack:** FastAPI, SQLAlchemy async, Postgres, Redis, Celery, Docker Compose, pytest, deterministic `AI_PROVIDER=mock`

---

## 기준과 범위

저장소 루트는 `C:\multi_modal`이다. 아래 파일 경로는 모두 이 루트 기준이다.

이 문서는 검토용 구현계획이다. 아직 코드를 구현하지 않는다. 실제 구현 시에도 `.env`, ADC, service-account JSON, API key, private credential 내용을 읽거나 출력하지 않고, 실제 Vertex/Gemini/Imagen/Veo 호출을 하지 않는다.

Phase 2는 Phase 1 완료 상태에서 시작한다.

- Phase 1 완료 커밋: `a88cba9 feat: split api and worker processes`
- Phase 1 closeout: `docs/phase1-worker-process-separation-closeout.md`
- 현재 baseline: API process + standalone polling worker process
- Phase 2 목표: Redis/Celery dispatch를 최소 도입하고 mock mode에서 end-to-end를 검증

## 검토용 추천 결정

- `JOB_DISPATCH_MODE=celery`를 Phase 2 mock Compose 기본값으로 둔다.
- 기존 `python -m app.worker` polling worker는 fallback/manual repair path로 보존한다.
- Compose의 `worker` service는 Phase 2에서 Celery worker command로 전환한다.
- Celery task payload는 `job_id` 문자열만 허용한다.
- Celery result backend는 사용자-visible job state로 쓰지 않는다. 기본은 disabled/ignored로 둔다.
- Outbox table은 Phase 2에서 도입하지 않는다. 대신 Phase 2 안에 최소
  `pending AND blocked=false` job 재발행 repair 경계를 둔다.
- Queue routing은 Phase 2에서 단일 `generation` queue로 시작한다. `prompt`, `imagen`, `veo` 분리는 Phase 3로 미룬다.
- Prompt enhancement는 Phase 2에서 Celery로 보내지 않는다. 사용자가 review/edit/accept하는 초안 생성 흐름은 API boundary에 유지한다.

## Subagent 작업 분할

실제 구현은 네 역할로 나눈다.

- 계획 에이전트: 이 문서와 Phase 1 closeout을 기준으로 task 순서, gate, 검증 명령을 재확인한다.
- 구현 에이전트: config, Celery app, enqueue adapter, task wrapper, Compose 변경을 맡는다.
- 테스트 에이전트: dispatch contract, API enqueue points, Celery task idempotency, Compose/smoke tests를 맡는다.
- 리뷰 에이전트: source-of-truth 위반, actual provider call 위험, Redis/Celery 범위 과확장, pipeline child dispatch 누락을 검토한다.

## Phase 2에서 하지 않을 것

- Outbox table 구현
- Dead-letter queue 구현
- Provider별 queue routing 구현
- Celery retry/backoff/rate-limit 정책 고도화
- Prompt enhancement Celery task화
- Celery result backend를 job state source of truth로 사용
- API response contract 확장
- 실제 Vertex/Gemini/Imagen/Veo 호출
- storage helper 또는 `state_machine.transition(...)` 우회

## File Map

- Modify: `backend/pyproject.toml`
  - Celery/Redis broker dependency 추가.
- Modify: `backend/app/config.py`
  - dispatch mode, broker URL, result backend policy, Celery eager test config 추가.
- Create: `backend/app/celery_app.py`
  - Celery app factory/config boundary.
- Create: `backend/app/services/jobs/enqueue.py`
  - dispatch adapter, `job_id`-only enqueue boundary, enqueue failure policy.
- Create: `backend/app/services/jobs/tasks.py`
  - Celery `process_job(job_id)` task and async job claim/execution wrapper.
- Modify: `backend/app/api/generations.py`
  - create/retry commit 후 dispatch 호출.
- Modify: `backend/app/api/pipelines.py`
  - pipeline parent commit 후 parent dispatch 호출.
- Modify: `backend/app/services/jobs/handlers.py`
  - parent T2I 완료 후 unblocked child id를 dispatch adapter로 전달.
- Modify: `backend/app/services/jobs/pipeline_link.py`
  - completed parent link 처리 결과로 dispatch 대상 child id를 반환.
- Create: `backend/app/services/jobs/repair.py`
  - outbox 없이 pending job을 재발행하는 minimal repair boundary.
- Create: `scripts/reenqueue_pending_jobs.py`
  - 운영자가 수동으로 pending job 재발행을 실행할 수 있는 CLI.
- Modify: `docker-compose.yml`
  - `redis` service 추가, worker command를 Celery worker로 전환.
- Modify: `.env.example`
  - local non-secret Redis/Celery config 추가.
- Modify: `scripts/smoke_mock_golden_path.py`
  - compose start list에 `redis` 포함.
- Modify: `scripts/smoke_mock_retry_flow.py`
  - compose start list에 `redis` 포함.
- Modify: `docs/runbooks/local-mock.md`
  - Phase 2 local stack과 fallback worker 설명.
- Modify: `docs/testing.md`
  - Redis/Celery mock verification 범위 추가.

Test files:

- Create: `backend/tests/test_celery_app.py`
- Create: `backend/tests/test_enqueue.py`
- Create: `backend/tests/test_celery_tasks.py`
- Create: `backend/tests/test_reenqueue_pending.py`
- Modify: `backend/tests/test_generation_api.py`
- Modify: `backend/tests/test_pipeline_api.py`
- Modify: `backend/tests/test_job_handlers.py`
- Modify: `backend/tests/test_compose_worker_service.py`
- Modify: `backend/tests/test_smoke_mock_golden_path_script.py`
- Modify: `backend/tests/test_smoke_mock_retry_script.py`

## Task 1: Config와 Dependency Boundary

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Create: `backend/tests/test_celery_app.py`

**Test:**
- `backend/tests/test_celery_app.py::test_celery_config_uses_broker_without_result_backend`
- `backend/tests/test_celery_app.py::test_dispatch_mode_defaults_are_explicit`

- [ ] **Step 1: failing config test 작성**

`Settings(_env_file=None, ...)`로 secret 파일 없이 설정 객체를 만들고, Phase 2 설정이 명시적으로 존재하는지 검증한다.

Expected config names:

```python
job_dispatch_mode = "celery" | "polling"
celery_broker_url = "redis://redis:6379/0"
celery_result_backend = None
celery_task_always_eager = False
celery_default_queue = "generation"
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py -q
```

Expected: new settings and Celery app do not exist yet.

- [ ] **Step 3: dependency 추가**

`backend/pyproject.toml`에 Celery Redis broker dependency를 추가한다.

Recommended dependency shape:

```toml
"celery[redis]>=5.4,<5.6",
```

No direct provider dependency changes.

- [ ] **Step 4: Settings 추가**

`backend/app/config.py`에 non-secret local defaults를 추가한다.

Recommended minimal shape:

```python
job_dispatch_mode: str = "celery"
celery_broker_url: str = "redis://redis:6379/0"
celery_result_backend: str | None = None
celery_task_always_eager: bool = False
celery_default_queue: str = "generation"
```

- [ ] **Step 5: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py -q
```

Expected: config tests pass.

## Task 2: Celery App Boundary

**Files:**
- Create: `backend/app/celery_app.py`
- Modify: `backend/tests/test_celery_app.py`

**Test:**
- `backend/tests/test_celery_app.py::test_celery_app_names_jobs_namespace`
- `backend/tests/test_celery_app.py::test_celery_app_ignores_results_for_user_visible_state`

- [ ] **Step 1: failing Celery app tests 작성**

Tests should import `app.celery_app.celery_app` and assert:

```python
assert celery_app.main == "multimodal.jobs"
assert celery_app.conf.broker_url == settings.celery_broker_url
assert celery_app.conf.task_ignore_result is True
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py -q
```

Expected: module missing.

- [ ] **Step 3: minimal Celery app 구현**

`backend/app/celery_app.py`에서 settings boundary 안에 Celery app을 둔다.

Implementation rules:

- broker URL은 settings에서만 읽는다.
- result backend는 사용자-visible 상태로 사용하지 않는다.
- task module import path는 `app.services.jobs.tasks`로 제한한다.
- task serializer는 JSON으로 제한한다.
- default queue는 Phase 2에서 단일 `generation` queue로 둔다.
- provider client를 만들지 않는다.

- [ ] **Step 4: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py -q
```

Expected: Celery app tests pass.

## Task 3: Enqueue Adapter와 Failure Policy

**Files:**
- Create: `backend/app/services/jobs/enqueue.py`
- Create: `backend/tests/test_enqueue.py`

**Test:**
- `backend/tests/test_enqueue.py::test_enqueue_process_job_sends_job_id_only`
- `backend/tests/test_enqueue.py::test_polling_dispatch_mode_is_noop`
- `backend/tests/test_enqueue.py::test_enqueue_failure_is_reported_without_mutating_job`

- [ ] **Step 1: failing enqueue contract tests 작성**

Fake Celery task object를 사용해 `delay()` 또는 `apply_async()`에 들어가는 payload가 `job_id` 하나뿐인지 확인한다.

Minimal assertion:

```python
assert sent_args == ((str(job_id),),)
assert "prompt" not in sent_repr
assert "parameters" not in sent_repr
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_enqueue.py -q
```

Expected: enqueue module missing.

- [ ] **Step 3: dispatch API 구현**

Recommended public functions:

```python
async def dispatch_job(job_id: UUID, *, reason: str) -> DispatchResult:
    ...

async def dispatch_jobs(job_ids: Iterable[UUID], *, reason: str) -> list[DispatchResult]:
    ...
```

Rules:

- `JOB_DISPATCH_MODE=polling`: no-op success. Existing polling worker can pick pending jobs.
- `JOB_DISPATCH_MODE=celery`: enqueue `process_job(str(job_id))`.
- Enqueue failure raises or returns a structured failure to caller, but never mutates job state.
- The adapter does not read job prompt, parameters, assets, or credentials.

- [ ] **Step 4: enqueue failure policy 고정**

Phase 2 recommended policy:

- API still returns the created job if DB commit succeeded.
- Failed dispatch is logged.
- Job remains `pending`.
- Manual repair/fallback path is documented for Phase 2.
- Outbox automation is Phase 3+.

- [ ] **Step 5: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_enqueue.py -q
```

Expected: enqueue tests pass.

## Task 4: API Dispatch Points

**Files:**
- Modify: `backend/app/api/generations.py`
- Modify: `backend/app/api/pipelines.py`
- Modify: `backend/tests/test_generation_api.py`
- Modify: `backend/tests/test_pipeline_api.py`

**Test:**
- `backend/tests/test_generation_api.py::test_create_generation_dispatches_created_job_after_commit`
- `backend/tests/test_generation_api.py::test_retry_generation_dispatches_retry_job_after_commit`
- `backend/tests/test_generation_api.py::test_create_generation_keeps_pending_job_when_dispatch_fails`
- `backend/tests/test_pipeline_api.py::test_create_pipeline_dispatches_parent_only`

- [ ] **Step 1: failing API dispatch tests 작성**

Monkeypatch `dispatch_job` with a fake async function that records `job_id` and reason.

Expected reasons:

```python
"generation_created"
"generation_retry_created"
"pipeline_parent_created"
```

- [ ] **Step 2: 실패 확인**

Run targeted tests.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py -q
```

Expected: dispatch is not called yet.

- [ ] **Step 3: create/retry/pipeline dispatch 추가**

Rules:

- Dispatch only after `await session.commit()`.
- Do not place generation payload in Celery message.
- Do not change API response schema.
- Dispatch failure should not roll back committed job.
- Pipeline creation dispatches parent only; child is blocked and must not be queued yet.

- [ ] **Step 4: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py -q
```

Expected: API tests pass.

## Task 5: Celery Task Claim과 Idempotency Guard

**Files:**
- Create: `backend/app/services/jobs/tasks.py`
- Create: `backend/tests/test_celery_tasks.py`

**Test:**
- `backend/tests/test_celery_tasks.py::test_process_job_claims_pending_job_before_handler`
- `backend/tests/test_celery_tasks.py::test_process_job_noops_terminal_job`
- `backend/tests/test_celery_tasks.py::test_process_job_noops_blocked_job`
- `backend/tests/test_celery_tasks.py::test_process_job_noops_already_queued_duplicate`
- `backend/tests/test_celery_tasks.py::test_process_job_rejects_invalid_job_id_without_provider_call`

- [ ] **Step 1: failing task tests 작성**

Use fake session/handler or a focused DB fixture to verify:

- pending unblocked job transitions to `queued` with `{"runner": "celery"}` before handler runs
- terminal job no-ops
- blocked job no-ops
- duplicate task seeing `queued/generating/downloading` no-ops in Phase 2
- invalid UUID does not call provider/storage boundary

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_tasks.py -q
```

Expected: tasks module missing.

- [ ] **Step 3: Celery task wrapper 구현**

Recommended shape:

```python
@celery_app.task(name="jobs.process_job", ignore_result=True)
def process_job(job_id: str) -> None:
    asyncio.run(process_job_async(job_id))
```

`process_job_async` should:

- parse UUID
- lock/reload job from Postgres
- no-op if missing, terminal, blocked, or not executable for Phase 2
- transition pending -> queued through `state_machine.transition(...)`
- call existing `handlers.handle(job_id)` after claim

- [ ] **Step 4: handler와 transition 중복 방지 확인**

Existing handlers already accept `queued` jobs and move them to provider execution. If Celery task claims pending -> queued first, handlers should not re-queue with `direct-handler`.

- [ ] **Step 5: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_tasks.py tests/test_job_runner.py -q
```

Expected: Celery task tests and existing runner tests pass.

## Task 6: Pipeline Child Dispatch After Unblock

**Files:**
- Modify: `backend/app/services/jobs/handlers.py`
- Modify: `backend/app/services/jobs/pipeline_link.py`
- Modify: `backend/tests/test_job_handlers.py`
- Modify: `backend/tests/test_pipeline_link.py`

**Test:**
- `backend/tests/test_job_handlers.py::test_completed_parent_dispatches_unblocked_child`
- `backend/tests/test_pipeline_link.py::test_link_completed_parent_returns_child_for_dispatch`

- [ ] **Step 1: failing pipeline child dispatch test 작성**

When a T2I parent completes and `pipeline_link.link_completed_parent(...)` returns a linked child id, the implementation should dispatch the child job.

Expected reason:

```python
"pipeline_child_unblocked"
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_job_handlers.py tests/test_pipeline_link.py -q
```

Expected: child dispatch is not called yet.

- [ ] **Step 3: child dispatch 연결**

Rules:

- Dispatch only after child is unblocked and committed.
- Do not dispatch blocked child at pipeline creation.
- If dispatch fails, child remains pending/unblocked and can be repaired manually or by fallback polling worker.
- Do not create Celery queue routing by mode in Phase 2.

- [ ] **Step 4: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_job_handlers.py tests/test_pipeline_link.py -q
```

Expected: pipeline tests pass.

## Task 7: Pending Job Reenqueue Repair

**Files:**
- Create: `backend/app/services/jobs/repair.py`
- Create: `scripts/reenqueue_pending_jobs.py`
- Create: `backend/tests/test_reenqueue_pending.py`

**Test:**
- `backend/tests/test_reenqueue_pending.py::test_repair_selects_pending_unblocked_jobs_only`
- `backend/tests/test_reenqueue_pending.py::test_repair_reenqueues_job_ids_without_payload`
- `backend/tests/test_reenqueue_pending.py::test_repair_does_not_mark_jobs_failed_on_enqueue_error`

- [ ] **Step 1: failing repair tests 작성**

Repair 대상은 outbox event가 아니라 현재 Postgres 상태다.

Selection rule:

```text
Job.state == pending
AND Job.blocked == false
```

Do not select:

- blocked pipeline child
- terminal jobs
- queued/generating/downloading jobs
- prompt enhancement records

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_reenqueue_pending.py -q
```

Expected: repair module missing.

- [ ] **Step 3: repair boundary 구현**

Recommended public function:

```python
async def reenqueue_pending_jobs(*, limit: int = 100, reason: str = "repair_pending") -> RepairResult:
    ...
```

Rules:

- Dispatch through the same `dispatch_job(...)` adapter.
- Do not mutate job state.
- Do not increment `attempts`.
- Return counts: selected, dispatched, failed.
- Log dispatch failures but keep jobs pending.
- Do not handle `polling + vertex_operation_name` in Phase 2 unless explicitly approved.

- [ ] **Step 4: repair CLI 구현**

`scripts/reenqueue_pending_jobs.py` should:

- refuse `.env` secret reads
- require operator-provided non-secret env or existing process env
- not call provider clients
- print counts only, not prompts/payloads

- [ ] **Step 5: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_reenqueue_pending.py tests/test_enqueue.py -q
```

Expected: repair and enqueue tests pass.

## Task 8: Compose Redis + Celery Worker

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/tests/test_compose_worker_service.py`

**Test:**
- `backend/tests/test_compose_worker_service.py::test_compose_defines_redis_for_celery_broker`
- `backend/tests/test_compose_worker_service.py::test_worker_uses_celery_command_and_broker_env`
- `backend/tests/test_compose_worker_service.py::test_no_celery_result_backend_source_of_truth`

- [ ] **Step 1: failing compose tests 작성**

Expected compose shape:

```yaml
redis:
  image: redis:7-alpine

worker:
  command: celery -A app.celery_app worker ...
```

Expected shared env:

```text
JOB_DISPATCH_MODE=celery
CELERY_BROKER_URL=redis://redis:6379/0
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_compose_worker_service.py -q
```

Expected: redis/celery worker not present.

- [ ] **Step 3: compose/env 구현**

Rules:

- Add `redis` service with healthcheck.
- Backend depends on Redis only when dispatch mode is Celery in local Compose.
- Worker service depends on db and redis.
- Worker service uses Celery command, not `python -m app.worker`.
- Existing `python -m app.worker` polling worker must not run alongside the
  default Celery worker. Keep it as a documented manual fallback/profile only.
- Preserve `stop_grace_period`.
- Do not mount credentials beyond existing vertex override behavior.

- [ ] **Step 4: compose verification**

Run:

```powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --services
```

Expected services include `db`, `redis`, `backend`, `worker`, `frontend`.

## Task 9: Smoke Scripts and Docs

**Files:**
- Modify: `scripts/smoke_mock_golden_path.py`
- Modify: `scripts/smoke_mock_retry_flow.py`
- Modify: `backend/tests/test_smoke_mock_golden_path_script.py`
- Modify: `backend/tests/test_smoke_mock_retry_script.py`
- Modify: `docs/runbooks/local-mock.md`
- Modify: `docs/testing.md`
- Create: `docs/phase2-celery-dispatch-closeout.md` after implementation

**Test:**
- `backend/tests/test_smoke_mock_golden_path_script.py::test_start_compose_includes_redis_worker_and_mock_env`
- `backend/tests/test_smoke_mock_retry_script.py::test_start_compose_includes_redis_worker_frontend_and_mock_env`

- [ ] **Step 1: failing smoke script tests 작성**

Expected start order:

```python
["db", "redis", "backend", "worker"]
["db", "redis", "backend", "worker", "frontend"]
```

- [ ] **Step 2: smoke scripts 업데이트**

Rules:

- Continue refusing `--env-file .env`.
- Continue forcing `AI_PROVIDER=mock`.
- Include Redis when `--compose` is used.
- Keep `--base-url` mode unchanged but document that worker/redis must already be running.

- [ ] **Step 3: docs 업데이트**

Document:

- Phase 2 local stack
- Celery is dispatch only
- Postgres is source of truth
- No real provider calls in mock smoke
- Polling worker fallback remains manual

- [ ] **Step 4: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_smoke_mock_golden_path_script.py tests/test_smoke_mock_retry_script.py -q
```

Expected: smoke script tests pass.

## Task 10: Phase 2 Full Verification Gate

**Files:**
- Verify all files touched in Tasks 1-8.

- [ ] **Step 1: targeted Phase 2 tests**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py tests/test_enqueue.py tests/test_celery_tasks.py tests/test_reenqueue_pending.py tests/test_compose_worker_service.py -q
```

Expected: targeted Celery/dispatch tests pass.

- [ ] **Step 2: backend full suite**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Expected: all backend tests pass.

- [ ] **Step 3: frontend verification**

Run:

```powershell
cd frontend
npm run lint
npm run build
```

Expected: both pass. Phase 2 should not require frontend code changes.

- [ ] **Step 4: compose config**

Run:

```powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --services
```

Expected: services include `db`, `redis`, `backend`, `worker`, `frontend`.

- [ ] **Step 5: mock smoke**

Run sequentially, not in parallel:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
python scripts/smoke_mock_retry_flow.py --compose --env-file .env.example --timeout-sec 90
```

Expected: both pass with `AI_PROVIDER=mock` and no live provider credentials.

- [ ] **Step 6: local quality gate**

Run:

```powershell
python scripts/verify_local.py
```

Expected: `VERIFY PASSED`.

- [ ] **Step 7: hygiene**

Run:

```powershell
git diff --check
git status --short --branch
git diff --cached --name-only
```

Expected: no whitespace errors, no unintended staged files.

## Exit Criteria

Phase 2 is complete only when:

- Redis exists only as Celery broker in local Compose.
- Celery worker processes jobs through `job_id`-only task messages.
- API creates jobs in Postgres first, then dispatches.
- Dispatch failure does not delete or mutate the committed job.
- Terminal, blocked, duplicate, and invalid job tasks no-op safely.
- Pipeline child job dispatch occurs after parent completion/unblock.
- Celery result backend is not used as user-visible job state.
- Existing polling worker remains available as manual fallback.
- Mock golden-path and retry smokes pass without real provider calls.
- Redis/Celery introduction does not change API response contracts.

## Review Questions

1. Should `.env.example` default to `JOB_DISPATCH_MODE=celery` immediately, or should implementation land with `polling` default and enable Celery only in smoke?
2. Is manual polling fallback enough for Phase 2 enqueue failure, or should a minimal `reenqueue_pending_jobs` command be included now?
3. Should `process_job` no-op every non-`pending` job in Phase 2, or should it also resume `polling + vertex_operation_name` jobs?
4. Should task claim use only row lock + state transition, or should we introduce a worker ownership token now?
5. Should Celery eager mode be used in unit tests, or should tests stay on fake task/app objects until compose smoke?
