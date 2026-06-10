# Phase 1 Worker Process Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Celery 도입 전에 FastAPI API process와 job worker process를 분리하고, mock mode에서 job lifecycle, asset serving, runner recovery가 깨지지 않는다는 증거를 만든다.

**Architecture:** Postgres는 계속 job source of truth로 유지한다. API process는 job 생성, 상태 조회, asset/file serving만 담당하고, 별도 worker entrypoint가 기존 `InProcessJobRunner().run_forever()`를 FastAPI lifespan 밖에서 실행한다. Redis, Celery, queue routing, outbox, retry/backoff는 Phase 2 이후로 미룬다.

**Tech Stack:** FastAPI, SQLAlchemy async engine, Postgres, `InProcessJobRunner`, Docker Compose, pytest, deterministic `AI_PROVIDER=mock`

---

## Closeout

Status: complete.

Completed in commit: `a88cba9 feat: split api and worker processes`.

The checklist below is preserved as the implementation plan that was executed.
The resulting implementation split FastAPI API serving from job execution,
added a standalone `python -m app.worker` process, updated Compose to run a
`worker` service, and kept Redis/Celery/outbox/queue routing out of Phase 1.

Verification evidence:

- Phase 1 targeted tests: `44 passed`
- Backend full suite: `235 passed`
- Frontend lint/build: passed
- Compose config with `.env.example`: passed
- Compose services: `db`, `backend`, `frontend`, `worker`
- Mock golden-path smoke: passed
- Mock retry smoke: passed
- `python scripts/verify_local.py`: `VERIFY PASSED`

Remaining Phase 2 decisions:

- Introduce Redis strictly as the Celery broker.
- Keep Celery task payloads `job_id`-only.
- Decide whether to add outbox/repair immediately or after minimal enqueue
  tests.
- Keep Postgres as the user-visible job source of truth.

## 기준과 범위

저장소 루트는 현재 checkout의 repository root이다. 필요하면 `git rev-parse --show-toplevel`로 확인한다. 아래 파일 경로는 모두 이 루트 기준의 exact path이다.

이 계획은 `docs/production-worker-queue-plan.md`의 Phase 1을 구현 가능한 작은 작업 단위로 쪼갠 검토용 문서이다. 이 문서를 작성하는 단계에서는 코드 구현을 하지 않는다. 실제 구현 시에도 `.env`, ADC, service-account JSON, API key, private credential 내용을 읽거나 출력하지 않고, 실제 Vertex/Gemini/Imagen/Veo 호출을 하지 않는다.

Phase 1의 핵심 합의:

- Phase 1은 Celery 전 API/worker process 분리 검증이다.
- Phase 1은 짧게 진행하고 gate는 엄격하게 둔다.
- Redis/Celery는 Phase 2로 미룬다.
- mock mode에서도 생성, 미리보기, 파일 서빙, job 상태 흐름이 끝까지 검증되어야 한다.

## 검토용 추천 결정

이 문서는 검토 전 계획이지만, 구현 시작 전에 방향을 더 쉽게 고를 수 있도록 아래 결정을 기본 추천안으로 둔다.

- `JOB_RUNNER_AUTO_START` 기본값은 `false`로 둔다. Phase 1의 목적이 API/worker process 분리이므로, bare `uvicorn app.main:app`에서도 API process가 job runner를 몰래 시작하지 않는 쪽이 더 명확하다.
- `Settings.ai_provider`의 전역 기본값은 Phase 1에서 바꾸지 않는다. 대신 worker entrypoint에서 `AI_PROVIDER`가 명시되지 않은 채 `vertex`로 해석되는 silent fallback을 막는다.
- `docker compose up` 기본 stack에는 `worker` service를 포함한다. local mock 사용자가 별도 명령을 기억하지 않아도 생성 job이 처리되게 하는 것이 혼란을 줄인다.
- Smoke script는 `--compose` 사용 시 `worker` service를 함께 시작하도록 바꾼다. Phase 1 이후 backend-only smoke는 API 생성까지만 되고 job 완료까지 가지 못할 수 있기 때문이다.
- README는 최소 변경으로 두고, 자세한 실행/운영 설명은 `docs/runbooks/local-mock.md`에 둔다.

## Subagent 작업 분할

실제 구현은 사용자의 선호대로 서브에이전트를 나눠 진행한다. 각 작업자는 서로의 변경을 되돌리지 않고, 메인 에이전트가 최종 통합과 검증을 담당한다.

- 계획 에이전트: 이 문서와 `docs/production-worker-queue-plan.md`를 기준으로 task 순서, gate, 검증 명령을 재확인한다.
- 구현 에이전트: `backend/app/config.py`, `backend/app/main.py`, `backend/app/worker.py`, `docker-compose.yml`의 최소 구현을 맡는다.
- 테스트 에이전트: `backend/tests/*`와 smoke script tests를 맡아 Phase 1 gate를 테스트로 고정한다.
- 리뷰 에이전트: Phase 1 범위 이탈, 실제 provider 호출 위험, Redis/Celery 조기 도입, source-of-truth 위반 여부를 검토한다.

## File Map

- Modify: `backend/app/config.py`
  - runner auto-start 제어 설정과 worker env guard에 필요한 설정을 둔다.
- Modify: `backend/app/main.py`
  - FastAPI lifespan에서 runner 자동 시작을 설정으로 gate한다.
- Create: `backend/app/worker.py`
  - FastAPI lifespan 밖에서 worker 단독 bootstrap을 수행한다.
- Modify: `docker-compose.yml`
  - Redis/Celery 없이 `worker` service를 추가하고 backend와 동일한 image/env/volume을 공유한다.
- Create: `backend/tests/test_main_lifespan.py`
  - API process가 runner auto-start disabled 설정에서 runner를 시작하지 않는지 검증한다.
- Create: `backend/tests/test_worker_bootstrap.py`
  - worker bootstrap의 `DATA_DIR` 생성, `init_db_schema`, runner 실행, shutdown, `close_db_connection`을 검증한다.
- Create: `backend/tests/test_worker_environment.py`
  - worker env/mock guard가 missing env에서 vertex silent fallback을 막는지 검증한다.
- Create: `backend/tests/test_compose_worker_service.py`
  - Compose에 `worker` service가 있고 Redis/Celery가 없는지, backend와 env/volume을 맞추는지 검증한다.
- Modify: `backend/tests/test_job_runner.py`
  - 기존 runner startup order, orphan sweep, polling resume regression을 Phase 1 gate로 고정한다.
- Modify candidate: `docs/runbooks/local-mock.md`
  - local mock 실행 방식에서 API와 worker를 함께 띄우는 흐름을 반영한다.
- Modify candidate: `README.md`
  - runbook만으로 부족하면 local mock quick start 요약을 업데이트한다.
- Modify candidate: `scripts/smoke_mock_golden_path.py`
  - `--compose` smoke가 backend 단독 runner를 전제로 하지 않도록 `worker` service 포함 후보를 검토한다.
- Modify candidate: `scripts/smoke_mock_retry_flow.py`
  - retry smoke의 compose start 목록에 `worker` service 포함 후보를 검토한다.

## Task 1: Runner Auto-Start 설정과 API Lifespan Gate

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_main_lifespan.py`

**Test:**
- `backend/tests/test_main_lifespan.py::test_lifespan_skips_runner_when_auto_start_disabled`
- `backend/tests/test_main_lifespan.py::test_lifespan_starts_runner_when_auto_start_enabled`
- `backend/tests/test_main_lifespan.py::test_lifespan_always_closes_db_connection`

- [ ] **Step 1: failing test 작성**

`backend/tests/test_main_lifespan.py`에서 `app.main.lifespan`을 직접 호출한다. `init_db_schema`, `close_db_connection`, `job_runner`를 monkeypatch하고, `main.settings`를 `Settings(ai_provider="mock", data_dir=tmp_path, job_runner_auto_start=False)` 형태로 대체한다.

Minimal assertion shape:

```python
assert calls == ["mkdir", "init_db_schema", "yield", "close_db_connection"]
assert "job_runner" not in calls
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_main_lifespan.py::test_lifespan_skips_runner_when_auto_start_disabled -q
```

Expected: `Settings`에 `job_runner_auto_start`가 없거나 lifespan이 runner를 계속 시작해서 실패한다.

- [ ] **Step 3: 설정 추가**

`backend/app/config.py`에 runner auto-start 설정을 추가한다. Phase 1 초안 기본값은 API/worker 분리 원칙을 우선해 `False`로 둔다.

Minimal shape:

```python
job_runner_auto_start: bool = False
```

- [ ] **Step 4: lifespan gate 구현**

`backend/app/main.py`에서 `settings.job_runner_auto_start`가 true일 때만 `asyncio.create_task(job_runner(), name="job-runner")`를 실행한다. `runner_task`가 없는 경우에도 shutdown에서 `close_db_connection()`은 항상 호출되어야 한다.

Minimal shape:

```python
runner_task = None
if settings.job_runner_auto_start:
    runner_task = asyncio.create_task(job_runner(), name="job-runner")
```

- [ ] **Step 5: enabled 경로 regression test 작성**

`job_runner_auto_start=True`일 때 기존 lifespan behavior처럼 runner가 정확히 한 번 시작되고, shutdown에서 cancel/await 되는지 검증한다.

- [ ] **Step 6: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_main_lifespan.py -q
```

Expected: 새 lifespan tests가 모두 통과한다.

## Task 2: Worker Entrypoint와 Standalone Bootstrap

**Files:**
- Create: `backend/app/worker.py`
- Create: `backend/tests/test_worker_bootstrap.py`

**Test:**
- `backend/tests/test_worker_bootstrap.py::test_worker_bootstrap_initializes_data_dir_schema_runner_and_db_close`
- `backend/tests/test_worker_bootstrap.py::test_worker_bootstrap_closes_db_after_runner_cancel`
- `backend/tests/test_worker_bootstrap.py::test_worker_main_uses_asyncio_run`

- [ ] **Step 1: failing bootstrap test 작성**

`backend/tests/test_worker_bootstrap.py`에서 `init_db_schema`, `close_db_connection`, `InProcessJobRunner`를 fake로 대체한다. fake runner는 `run_forever()`가 호출되면 event를 기록하고 정상 종료 또는 `asyncio.CancelledError`를 발생시킨다.

Minimal assertion shape:

```python
assert calls == ["mkdir", "init_db_schema", "runner.run_forever", "close_db_connection"]
assert tmp_path.exists()
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_worker_bootstrap.py::test_worker_bootstrap_initializes_data_dir_schema_runner_and_db_close -q
```

Expected: `app.worker` module이 아직 없어서 import 실패한다.

- [ ] **Step 3: `backend/app/worker.py` 생성**

`run_worker()`는 FastAPI app을 만들지 않는다. bootstrap 책임은 `DATA_DIR` 생성, env guard, `init_db_schema`, `InProcessJobRunner().run_forever()`, `close_db_connection`으로 제한한다.

Minimal shape:

```python
async def run_worker() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    validate_worker_environment(settings)
    await init_db_schema()
    try:
        await InProcessJobRunner().run_forever()
    finally:
        await close_db_connection()
```

- [ ] **Step 4: shutdown handling 검증**

`run_forever()`가 `asyncio.CancelledError`를 받는 테스트를 추가한다. 기대값은 cancellation이 삼켜지지 않고 전파되며, `close_db_connection()`은 호출되는 것이다.

- [ ] **Step 5: module entrypoint 추가**

`python -m app.worker`로 실행 가능하도록 `main()`과 `if __name__ == "__main__": main()`을 둔다. console script는 Phase 1에서 필수로 추가하지 않는다.

- [ ] **Step 6: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_worker_bootstrap.py -q
```

Expected: worker bootstrap tests가 모두 통과한다.

## Task 3: Worker Env/Mock Guard

**Files:**
- Modify: `backend/app/worker.py`
- Create: `backend/tests/test_worker_environment.py`
- Review only candidate: `backend/app/config.py`

**Test:**
- `backend/tests/test_worker_environment.py::test_worker_allows_mock_provider_without_vertex_client`
- `backend/tests/test_worker_environment.py::test_worker_rejects_implicit_vertex_provider`
- `backend/tests/test_worker_environment.py::test_worker_allows_explicit_vertex_provider_without_touching_credentials`

- [ ] **Step 1: failing env guard tests 작성**

Mock mode에서는 worker bootstrap이 credential을 요구하지 않아야 한다. 반대로 `AI_PROVIDER`가 process env에 없는데 resolved provider가 `vertex`인 경우, worker는 기본값을 타고 실제 provider mode로 조용히 넘어가면 안 된다.

Minimal assertion shape:

```python
with pytest.raises(RuntimeError, match="AI_PROVIDER"):
    validate_worker_environment(Settings(ai_provider="vertex"), environ={})
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_worker_environment.py -q
```

Expected: `validate_worker_environment`가 아직 없어서 실패한다.

- [ ] **Step 3: worker-only guard 구현**

`backend/app/worker.py`에 guard를 둔다. guard는 provider client를 만들지 않는다. `mock`은 credential 없이 통과한다. `vertex`는 process env에서 `AI_PROVIDER`가 명시된 경우에만 통과한다. 이 정책은 worker 전용이며, API health/readiness 정책을 바꾸지 않는다.

Minimal shape:

```python
def validate_worker_environment(settings: Settings, environ: Mapping[str, str] = os.environ) -> None:
    if settings.ai_provider == "mock":
        return
    if settings.ai_provider == "vertex" and environ.get("AI_PROVIDER") == "vertex":
        return
    raise RuntimeError("Worker requires explicit AI_PROVIDER before starting.")
```

- [ ] **Step 4: mock provider regression과 함께 검증**

Mock provider tests는 worker guard 이후에도 Vertex client를 만들지 않아야 한다.

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_worker_environment.py tests/test_mock_provider.py -q
```

Expected: env guard와 mock provider tests가 모두 통과한다.

## Task 4: Docker Compose Worker Service

**Files:**
- Modify: `docker-compose.yml`
- Create: `backend/tests/test_compose_worker_service.py`

**Test:**
- `backend/tests/test_compose_worker_service.py::test_compose_defines_worker_without_redis_or_celery`
- `backend/tests/test_compose_worker_service.py::test_worker_uses_backend_image_env_and_asset_volume`

- [ ] **Step 1: failing compose tests 작성**

`backend/tests/test_compose_worker_service.py`는 repository root의 `docker-compose.yml` text를 읽고 다음을 검증한다.

- `worker:` service가 있다.
- `redis:` service가 없다.
- `celery` 문자열이 없다.
- worker command는 `python -m app.worker`이다.
- worker와 backend가 같은 `DATABASE_URL`, `AI_PROVIDER`, `DATA_DIR`, `JOB_RUNNER_CONCURRENCY` env를 가진다.
- worker와 backend가 같은 `assets:/data/assets` volume을 가진다.

Minimal assertion shape:

```python
assert "\n  worker:\n" in compose_text
assert "\n  redis:\n" not in compose_text
assert "celery" not in compose_text.lower()
assert "python -m app.worker" in compose_text
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_compose_worker_service.py -q
```

Expected: `worker` service가 아직 없어서 실패한다.

- [ ] **Step 3: `worker` service 추가**

`docker-compose.yml`에 `worker` service를 추가한다. `backend`와 같은 build context, db health dependency, env, `assets` volume을 사용한다. Redis/Celery service와 dependency는 추가하지 않는다.

Minimal shape:

```yaml
  worker:
    build: ./backend
    depends_on:
      db:
        condition: service_healthy
    command: python -m app.worker
```

- [ ] **Step 4: backend service runner auto-start 명시**

`backend` service env에는 `JOB_RUNNER_AUTO_START: ${JOB_RUNNER_AUTO_START:-false}`를 명시해 Compose API process가 runner를 자동 시작하지 않게 한다. worker service는 `JOB_RUNNER_AUTO_START`에 의존하지 않는다.

- [ ] **Step 5: compose config verification**

Run:

```powershell
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Expected: 두 명령 모두 exit code 0이다.

- [ ] **Step 6: targeted pytest verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_compose_worker_service.py -q
```

Expected: compose worker tests가 모두 통과한다.

## Task 5: Existing Runner Regression Gate

**Files:**
- Modify: `backend/tests/test_job_runner.py`
- Review: `backend/app/services/jobs/runner.py`
- Review: `backend/app/services/jobs/handlers.py`
- Review: `backend/app/state_machine.py`

**Test:**
- `backend/tests/test_job_runner.py::test_poll_once_queues_pending_jobs_and_runs_handler`
- `backend/tests/test_job_runner.py::test_run_forever_sweeps_orphans_before_resuming_polling_jobs`
- `backend/tests/test_job_runner.py::test_sweep_orphans_marks_stale_non_terminal_jobs_failed`
- `backend/tests/test_job_runner.py::test_sweep_orphans_preserves_resumable_polling_jobs`
- New candidate: `backend/tests/test_job_runner.py::test_job_runner_wrapper_runs_in_process_runner_once`

- [ ] **Step 1: runner wrapper regression test 작성**

`job_runner()` wrapper가 `InProcessJobRunner().run_forever()`를 정확히 한 번 호출하는지 검증한다. API lifespan에서 runner를 끄더라도 worker entrypoint가 같은 runner boundary를 재사용한다는 증거가 된다.

Minimal assertion shape:

```python
assert calls == ["construct", "run_forever"]
```

- [ ] **Step 2: 기존 startup order test 유지**

`test_run_forever_sweeps_orphans_before_resuming_polling_jobs`는 Phase 1 gate이다. worker process 재시작 시 orphan sweep이 polling resume보다 먼저 실행되어야 한다.

- [ ] **Step 3: pending backlog recovery smoke 후보 확정**

별도 DB integration test가 이미 안정적으로 존재하지 않으면 Phase 1에서는 runner unit tests와 mock HTTP smoke를 결합해 검증한다. 실제 구현 시 `scripts/smoke_mock_golden_path.py --compose`가 `worker` service를 포함하도록 바꾸는 경우, pending job이 API 생성 후 worker에서 완료되는 것이 smoke의 핵심 증거가 된다.

- [ ] **Step 4: targeted verification**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_job_runner.py -q
```

Expected: 기존 runner regression과 새 wrapper regression이 모두 통과한다.

## Task 6: Local Mock Runbook/README Update Candidate

**Files:**
- Modify candidate: `docs/runbooks/local-mock.md`
- Modify candidate: `README.md`
- Modify candidate: `scripts/smoke_mock_golden_path.py`
- Modify candidate: `scripts/smoke_mock_retry_flow.py`
- Test candidate: `backend/tests/test_smoke_mock_golden_path_script.py`
- Test candidate: `backend/tests/test_smoke_mock_retry_script.py`

**Test:**
- `backend/tests/test_smoke_mock_golden_path_script.py::test_start_compose_includes_worker_and_mock_env`
- `backend/tests/test_smoke_mock_retry_script.py::test_start_compose_includes_worker_frontend_and_mock_env`

- [ ] **Step 1: docs scope 결정 후 failing docs/script tests 작성**

Phase 1에서 Compose 기본 실행에 `worker`를 포함한다면, 기존 smoke script 설명과 테스트를 바꾼다. 현재 `scripts/smoke_mock_golden_path.py --compose`는 `db backend`만 시작한다. Phase 1 이후에는 API process가 runner를 실행하지 않으므로 golden-path smoke에는 `worker`가 포함되어야 한다.

Minimal assertion shape:

```python
assert command[-3:] == ["db", "backend", "worker"]
assert env["AI_PROVIDER"] == "mock"
```

- [ ] **Step 2: runbook 문구 업데이트**

`docs/runbooks/local-mock.md`의 expected services에 `worker`를 추가한다. backend 단독 실행 시 job이 처리되지 않을 수 있음을 짧게 설명하고, 기본 개발 흐름은 `docker compose up -d --build`로 API와 worker를 함께 띄우는 것으로 정리한다.

- [ ] **Step 3: README quick start 업데이트 후보 검토**

README의 local mock quick start가 runbook을 충분히 가리키면 README는 최소 변경으로 둔다. 사용자가 첫 실행에서 backend-only 흐름을 따라갈 가능성이 높으면 `worker` service를 expected stack에 추가한다.

- [ ] **Step 4: smoke script 업데이트 후보 검증**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_smoke_mock_golden_path_script.py tests/test_smoke_mock_retry_script.py -q
```

Expected: smoke script command tests가 worker 포함 흐름으로 통과한다.

## Task 7: Phase 1 Full Verification Gate

**Files:**
- Verify: `backend/app/config.py`
- Verify: `backend/app/main.py`
- Verify: `backend/app/worker.py`
- Verify: `docker-compose.yml`
- Verify: `docs/runbooks/local-mock.md`
- Verify: `README.md`
- Verify: `scripts/smoke_mock_golden_path.py`
- Verify: `scripts/smoke_mock_retry_flow.py`

**Test:**
- Backend pytest full suite
- Compose config
- Targeted smoke script tests
- Hygiene checks

- [ ] **Step 1: backend full suite**

Run:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
```

Expected: all backend tests pass in mock mode.

- [ ] **Step 2: frontend build**

Run:

```powershell
cd frontend
npm run build
cd ..
```

Expected: frontend build passes. Phase 1 should not require frontend code changes.

- [ ] **Step 3: Compose config**

Run:

```powershell
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Expected: both commands pass, `worker` is present, Redis/Celery are absent.

- [ ] **Step 4: mock smoke candidates**

Run if Compose services are available and no real provider mode is requested:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
python scripts/smoke_mock_retry_flow.py --compose --env-file .env.example --timeout-sec 90
```

Expected: both smokes run with `AI_PROVIDER=mock`, include `worker`, and do not require live provider credentials.

- [ ] **Step 5: hygiene**

Run:

```powershell
git diff --check
git status --short --branch
git diff --cached --name-only
```

Expected: no whitespace errors, no unintended staged files, working tree changes are limited to Phase 1 implementation files.

## Phase 1에서 하지 않을 것

- Redis service 추가
- Celery dependency, Celery app, Celery task 추가
- queue routing 구현
- outbox table 추가
- broker 장애 대응 구현
- retry/backoff 정책 구현
- provider별 queue/concurrency/rate-limit 정책 구현
- Celery result backend 결정
- API contract 확장
- storage helper 우회
- state machine 우회
- 실제 Vertex/Gemini/Imagen/Veo 호출

## Exit Criteria

Phase 1은 아래 조건이 모두 충족되어야 완료로 본다.

- API process에서 runner가 자동 시작되지 않는다.
- worker process에서만 `InProcessJobRunner().run_forever()`가 실행된다.
- worker 단독 실행 시 `DATA_DIR` 생성, `init_db_schema`, shutdown handling, `close_db_connection`이 보장된다.
- API와 worker가 같은 `DATABASE_URL`, `DATA_DIR`, `AI_PROVIDER=mock`, asset volume을 공유한다.
- worker env 누락이 `vertex` provider silent fallback으로 이어지지 않는다.
- worker down 중 생성된 pending job이 worker 시작 후 처리된다.
- `queued`, `generating`, `downloading` 상태의 stale job은 orphan sweep 정책으로 복구 또는 실패 처리된다.
- `polling`과 `vertex_operation_name`이 있는 Veo job은 새 submit 없이 기존 operation을 resume한다.
- worker가 저장한 asset을 API `/files`가 읽고 byte-range streaming을 유지한다.
- asset 삭제 흐름은 storage helper 경계를 유지한다.
- parent 완료 후 blocked I2V child unblock이 유지된다.
- parent 실패 cascade가 유지된다.
- `AI_PROVIDER=mock` backend tests가 통과한다.
- `docker compose --env-file .env.example config --quiet`와 `docker compose config --quiet`가 통과한다.
- Redis/Celery 관련 service, dependency, task code가 추가되지 않는다.
- 문서와 smoke script는 backend-only runner 전제를 남기지 않는다.

## Review Questions

1. Runner 기본값: `JOB_RUNNER_AUTO_START`의 Phase 1 기본값을 `false`로 두고 API/worker 분리를 강제할지, bare `uvicorn app.main:app` 호환성을 위해 기본값은 `true`로 두되 Compose backend에서만 `false`를 명시할지 결정해야 한다.
2. Env guard 정책: worker에서 `AI_PROVIDER=vertex`는 process env에 명시된 경우에만 허용하는 정책이 충분한지, 아니면 global `Settings.ai_provider` 기본값 자체를 `mock`으로 바꿀지 결정해야 한다.
3. Compose worker 기본 포함 여부: `docker compose up` 기본 stack에 `worker`를 포함할지, local smoke와 runbook에서만 명시적으로 `worker`를 포함할지 결정해야 한다.
4. Docs 범위: Phase 1에서 `docs/runbooks/local-mock.md`만 업데이트할지, README quick start와 smoke script 설명까지 같은 변경에 포함할지 결정해야 한다.
