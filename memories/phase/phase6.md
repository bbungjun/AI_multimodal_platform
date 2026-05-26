# Phase 6 Job Runner Memory

## Note

- 이 문서는 git history 기반으로 복원 작성했다.
- 복원 기준은 아래 두 커밋의 `git show --stat`, `git show --name-only`, 필요한 diff 확인 결과다.
- 이 문서는 구현 기록과 다음 Phase 인수인계용 메모이며, 실제 production code 변경 내역은 git commit을 기준으로 확인한다.

## 기준 커밋

- `12be5b6 feat: add in-process job runner skeleton`
- `9a83dbc fix: make job runner tolerate missing database`

## Phase 6 목표

- Celery/Redis 없이 FastAPI 프로세스 내부에서 동작하는 asyncio 기반 job runner 골격을 만든다.
- DB에 저장된 `pending` Job을 주기적으로 선택하고, 동시성 제한 아래 mode별 handler로 dispatch한다.
- 상태 변경은 기존 strict state machine의 `transition(...)`을 경유한다.
- 실제 T2I/T2V/I2V 생성 구현은 Phase 7/8로 남기고, Phase 6에서는 runner와 handler skeleton만 준비한다.
- runner lifecycle을 FastAPI lifespan에 연결해 app startup/shutdown과 함께 시작/정리되도록 한다.

## 주요 변경 파일

### Phase 6 본 구현: `12be5b6`

- `backend/app/config.py`
  - `JOB_RUNNER_CONCURRENCY` 설정을 `job_runner_concurrency`로 추가했다.
- `backend/app/main.py`
  - FastAPI lifespan에서 `job_runner()` background task를 시작하고 shutdown 때 cancel/await하도록 연결했다.
- `backend/app/services/jobs/handlers.py`
  - mode별 dispatch entrypoint인 `handle(job_id)`를 추가했다.
  - `handle_t2i`, `handle_t2v`, `handle_i2v`는 Phase 7/8 구현 예정 skeleton으로 남겼다.
- `backend/app/services/jobs/runner.py`
  - `InProcessJobRunner`와 `job_runner()` entrypoint를 추가했다.
  - pending job pickup, concurrency limit, orphan sweep, handler failure marking, shutdown 로직을 구현했다.
- `backend/tests/test_job_runner.py`
  - runner 동작을 fake session 기반 단위 테스트로 검증했다.

### Phase 6 후속 수정: `9a83dbc`

- `backend/app/main.py`
  - runner task가 shutdown 시 예외를 낼 때 traceback으로 app shutdown을 오염시키지 않도록 logging 후 suppress하는 방향으로 보강했다.
- `backend/app/services/jobs/runner.py`
  - DB 미가용 등 poll/sweep 단계 실패를 runner 전체 crash로 이어지지 않게 보강했다.
  - 반복 poll 실패는 같은 메시지를 계속 남기지 않도록 failure key로 중복 warning을 줄였다.
  - poll recovery 시 info log를 남기도록 했다.
  - shutdown 중 task exception을 warning으로 기록하고 계속 정리하도록 했다.
  - handler 실패 후 `_mark_job_failed(...)` 자체가 실패해도 runner task가 traceback으로 종료되지 않도록 warning 처리했다.
- `backend/tests/test_job_runner.py`
  - DB connection failure를 흉내내는 fake session factory와 관련 회귀 테스트를 추가했다.

## 구현된 동작

- Runner startup
  - `InProcessJobRunner.run_forever()`가 startup 시 orphan sweep을 먼저 시도한다.
  - 이후 `poll_interval`마다 pending job pickup을 반복한다.
- Job pickup
  - `state='pending'`이고 `blocked=false`인 Job만 선택한다.
  - 생성 시각 기준 오래된 Job부터 선택한다.
  - SQL statement는 `FOR UPDATE SKIP LOCKED`를 사용하도록 구성했다.
  - 선택된 Job은 handler 실행 전에 `queued`로 전이하고 state history에 runner detail을 남긴다.
- Concurrency control
  - runner는 active task 수와 configured concurrency를 기준으로 새 pickup 수를 제한한다.
  - 실제 handler 실행은 runner 내부 semaphore 아래에서 수행한다.
- Handler dispatch
  - `handle(job_id)`가 DB에서 Job을 로드한 뒤 `mode`에 따라 `handle_t2i`, `handle_t2v`, `handle_i2v`로 dispatch한다.
  - Phase 6 기준 각 mode handler는 `NotImplementedError` skeleton이다.
- Failure handling
  - handler가 예외를 내면 runner가 Job을 `failed`로 전이한다.
  - error payload에는 exception code, message, retry count, last attempt time을 기록한다.
  - terminal state Job은 failure marking 대상에서 제외한다.
- Orphan sweep
  - stale non-terminal Job은 startup sweep에서 `failed`로 전이한다.
  - `polling` 상태이면서 `vertex_operation_name`이 있는 Job은 resumable 후보로 보고 sweep 대상에서 제외한다.
- Shutdown
  - shutdown 시 새 polling을 멈추고 active task를 기다린다.
  - timeout 후 남은 task는 cancel하고 gather로 정리한다.

## Shutdown traceback 수정 내용

- 문제 배경
  - Phase 6 skeleton 직후에는 DB가 아직 준비되지 않았거나 누락된 상태에서 runner startup/poll/sweep이 예외를 내면 shutdown 과정에서 traceback이 드러날 수 있었다.
  - 특히 lifespan에서 runner task를 cancel/await할 때 `CancelledError` 외 예외가 그대로 전파될 가능성이 있었다.
- 후속 수정 방향
  - lifespan shutdown은 runner task의 `CancelledError`는 정상 종료로 보고 무시한다.
  - runner task가 다른 예외로 끝났으면 `app.main` logger에 warning을 남기고 DB close는 계속 수행한다.
  - `run_forever()` 내부 poll loop는 개별 poll 실패를 warning으로 기록하고 다음 tick으로 진행한다.
  - startup orphan sweep 실패는 warning 후 `0`건 처리로 간주한다.
  - shutdown 중 active task exception은 warning으로 기록하고 cleanup을 계속한다.
  - handler 실패 후 Job failed marking이 DB 문제 등으로 실패해도 warning만 남기고 runner task를 보호한다.
- 검증 포인트
  - DB unavailable 상황에서도 runner가 즉시 app import/startup을 깨지 않는다.
  - cancellation은 여전히 `CancelledError`로 정상 전파되어 runner lifecycle이 멈출 수 있다.
  - 반복 poll failure는 동일 warning spam을 줄이고 recovery 시 recovered log를 남긴다.

## 테스트/검증 내용

- `backend/tests/test_job_runner.py`에서 Phase 6 runner를 fake session 기반으로 검증했다.
- Phase 6 본 구현에서 확인한 항목
  - `JOB_RUNNER_CONCURRENCY` 설정 로딩
  - pending/unblocked job만 pickup하는 SQL 조건
  - `FOR UPDATE SKIP LOCKED` 포함 여부
  - runner가 pending Job만 queued로 전이하고 blocked/completed Job은 건드리지 않음
  - concurrency limit 준수
  - dummy handler 성공 시 completed까지 상태 전이 가능
  - dummy handler 실패 시 Job이 failed로 전이되고 error가 기록됨
  - FastAPI lifespan이 runner를 시작하고 shutdown 때 정리함
  - app import 시 runner wiring이 깨지지 않음
- Phase 6 후속 수정에서 추가 확인한 항목
  - orphan sweep이 DB connection failure를 warning 처리하고 `0`을 반환함
  - `run_forever()`가 startup/poll DB unavailable 상황을 기록하면서 cancel 가능 상태를 유지함
  - lifespan shutdown이 runner task 예외를 warning으로 남기고 traceback으로 실패하지 않음

## Phase 7에서 이어받아야 할 주의사항

- Phase 7은 `handle_t2i` skeleton만 채운다. T2V/I2V skeleton은 Phase 8 범위로 남긴다.
- runner가 이미 `pending -> queued`로 전이한 뒤 handler를 호출하므로, `handle_t2i`는 `queued` 시작 상태를 정상 경로로 처리해야 한다.
- 테스트에서 handler를 직접 호출할 경우 `pending` 상태도 허용할 수 있지만, 실제 runner 경로와 중복 전이 충돌이 나지 않게 해야 한다.
- 모든 상태 변경은 계속 `transition(...)`을 경유해야 한다.
- handler 내부 Vertex 호출, storage 저장, Asset 생성 중 예외가 나면 Job을 public error와 함께 `failed`로 정리해야 한다.
- handler에서 예외를 삼키거나 terminal state를 다시 전이하지 않도록 주의한다.
- DB가 없는 환경에서도 app import/startup이 지나갈 수 있도록, runner lifecycle에서 추가되는 예외는 기존 logging/toleration 패턴을 유지한다.
- `polling + vertex_operation_name`은 Phase 8 Veo resume 후보로 남겨둔 예외 조건이므로 Phase 7에서 제거하거나 의미를 바꾸지 않는다.
- Phase 7 테스트는 실제 Vertex 호출 없이 mock service로 runner -> handler -> storage/asset 흐름을 검증한다.
