# Production Worker/Queue Migration Plan

> Current note: 이 문서는 worker/queue migration의 역사와 다음 운영 과제를 함께
> 보존한다. 경로는 현재 checkout의 repository root 기준으로 읽는다. Phase 1
> API/worker separation, Phase 2 Redis/Celery dispatch, Phase 3 transactional
> outbox dispatcher가 완료됐다.

## 목적

CreativeOps Studio는 Phase 1에서 FastAPI API process와 job worker process를
분리했고, 이후 Redis/Celery dispatch와 transactional outbox dispatcher를
도입했다. 이 구조는 mock mode에서 비용 없이 검증되었고, 실제 Vertex 기반
이미지/비디오 생성 서비스를 운영 수준으로 키우기 위한 runtime 경계를 만든 상태다.

이 문서는 API/worker 분리에서 Redis/Celery/outbox 구조로 이동한 결정과 남은
운영 과제를 기록한다. 목표는 Postgres를 job source of truth로 유지하고,
Redis/Celery는 작업 dispatch와 coordination layer로만 사용하는 것이다.

## 현재 상태

- 완료: Phase 1 API/worker process separation
- 완료: Phase 2 Redis/Celery `job_id` dispatch
- 완료: Phase 2 Celery worker ops hardening
- 완료: Phase 2 dispatch/task observability
- 완료: Phase 3 transactional outbox dispatcher
- closeout 문서:
  - `docs/phase1-worker-process-separation-closeout.md`
  - `docs/phase2-celery-dispatch-closeout.md`
  - `docs/phase2-celery-ops-hardening-closeout.md`
  - `docs/phase2-job-observability-closeout.md`
  - `docs/phase3-outbox-dispatcher-closeout.md`
- 현재 runtime: FastAPI API process가 job과 outbox event를 같은 transaction에
  저장하고, `python -m app.services.jobs.outbox_dispatcher`가 Redis/Celery로
  `job_id`를 발행하며, Celery worker가 Postgres에서 최신 job을 claim해 처리한다.
- 현재 Compose: `db`, `redis`, `backend`, `dispatcher`, `frontend`, `worker`
- 아직 미도입: provider별 queue routing, Celery retry/backoff/rate-limit,
  dead-letter 정책, worker metrics/Ops Console

## 현재 결정: Celery 중심 채택 방향

Celery는 현재 기본 worker/queue dispatch layer로 채택되어 있다.

채용/포트폴리오 관점에서는 단순히 "작동하는 비동기 처리"를 넘어서, 프로덕션 레벨의 worker 분리, broker 기반 dispatch, retry/backoff, queue routing, rate limit, 장애 복구, 중복 실행 방어를 고민했다는 점이 중요하다. Celery는 이 주제를 설명하기에 가장 익숙하고 설득력 있는 선택지이며, 실제 운영 사례와 면접 질문으로 연결하기 쉽다.

RQ, Arq, 직접 asyncio worker는 비교 검토한 대안으로 남긴다. RQ는 단순하고 러닝커브가 낮지만 복잡한 routing/retry 운영 설명에는 상대적으로 좁다. Arq는 asyncio 친화적이지만 포트폴리오/면접에서 보편적으로 알려진 선택지는 아니다. 직접 asyncio worker는 현재 코드와 이어지기 쉽지만, 프로덕션 queue system을 학습하고 설계했다는 메시지가 약해질 수 있다. 따라서 기본 실행 방향은 Celery 중심으로 잡고, 대안들은 tradeoff 비교 근거로 문서화한다.

## Phase 0 구조 (Phase 1 이전)

Phase 1 이전 요청 흐름은 다음과 같았다.

```text
React/Vite frontend
  -> FastAPI backend
    -> Postgres job, asset, prompt, pipeline records
    -> internal asyncio job runner
    -> provider/storage boundary
```

당시 핵심 특징은 다음과 같았다.

- Frontend는 `frontend/src/api/*` 클라이언트를 통해 FastAPI API를 호출한다.
- FastAPI backend는 generation 요청을 durable job으로 Postgres에 저장한다.
- Postgres가 job 상태, payload, asset metadata, prompt enhancement, pipeline 관계의 source of truth다.
- `backend/app/main.py`의 `lifespan()`에서 `asyncio.create_task(job_runner(), name="job-runner")`로 internal runner가 시작된다.
- `backend/app/services/jobs/runner.py`의 `InProcessJobRunner`가 `JobState.PENDING`이고 blocked가 아닌 job을 polling한다.
- pending job claim은 `SELECT ... FOR UPDATE SKIP LOCKED` 기반 row lock으로 처리된다.
- claim된 job은 state machine을 통해 `queued`로 전환되고, mode-specific handler가 provider/storage boundary를 호출한다.
- 모든 job 상태 변경은 `backend/app/state_machine.py`의 `transition(...)` 경계를 통해야 한다.
- orphan sweep과 polling resume도 runner startup에서 수행된다.

이 구조는 `AI_PROVIDER=mock`에서 credential 없이 end-to-end 생성 흐름을 검증하기 좋았다. 다만 API process와 provider 작업 process가 같은 lifecycle을 공유하므로, 장시간 video polling, provider quota 제어, worker 재시작, 다중 replica 운영, queue별 확장에는 한계가 있었다.

## Phase 1 구조

Phase 1에서 완료했던 중간 구조는 다음과 같았다.

```text
React/Vite frontend
  -> FastAPI API process
    -> Postgres job, asset, prompt, pipeline records
    -> /api and /files serving

Worker process
  -> InProcessJobRunner
    -> Postgres pending job polling and row-lock claim
    -> state_machine.transition(...)
    -> provider/storage boundary
```

핵심 특징은 다음과 같았다.

- API process는 job 생성, 상태 조회, asset metadata 조회, `/files` streaming을 담당한다.
- API process는 `JOB_RUNNER_AUTO_START=false` 기본값으로 runner를 자동 시작하지 않는다.
- Worker process는 `python -m app.worker`로 실행되며, 기존 `InProcessJobRunner`를 FastAPI lifespan 밖에서 실행한다.
- Postgres는 계속 job state, payload, prompt enhancement, pipeline relation, asset metadata의 source of truth다.
- Docker Compose mock stack은 `db`, `backend`, `worker`, `frontend`를 함께 실행했다.
- Worker는 `SIGTERM`/`SIGINT`를 task cancellation으로 연결하고, `stop_grace_period: 45s` 안에서 runner shutdown과 DB close를 수행하도록 구성됐다.

## 현재 기본 구조

현재 기본 요청/실행 흐름은 다음과 같다.

```text
React/Vite frontend
  -> FastAPI API server
    -> Postgres jobs, assets, prompt records, and outbox events
    -> /api and /files serving

Outbox dispatcher process
  -> publishes job ids from Postgres outbox to Redis/Celery

Celery worker process
  -> Postgres job lookup/state transition
  -> provider/storage boundary
```

책임 분리는 다음 원칙을 따른다.

- API server는 요청 검증, job/outbox event 생성, prompt enhancement draft 생성 요청, asset/file serving, status 조회를 담당한다.
- Worker process는 job 실행, provider 호출, polling resume, asset 저장, failure marking, retry bookkeeping을 담당한다.
- Postgres는 계속 job source of truth다. Redis/Celery에 들어가는 메시지는 권위 있는 상태가 아니다.
- Redis broker는 dispatch와 coordination layer다. worker가 어떤 job을 처리해야 하는지 알려주는 transport로만 사용한다.
- Celery worker는 task execution framework다. task payload는 큰 generation payload 전체가 아니라 `job_id` 중심으로 유지한다.
- Worker는 task 시작 시 Postgres에서 최신 job record를 다시 읽고, state machine transition 가능 여부와 terminal/idempotency 조건을 확인한다.
- Queue routing은 provider/mode 중심으로 분리할 수 있다. 예: `prompt`, `imagen`, `veo`.

## 기대효과

### API/worker 책임 분리

API server는 HTTP 요청 응답성과 frontend contract에 집중하고, worker는 장시간 실행되는 provider 작업에 집중한다. FastAPI shutdown이나 deploy가 진행될 때 provider 작업과 HTTP serving의 영향을 분리할 수 있다.

이 분리는 특히 Veo polling처럼 오래 걸리는 작업에 중요하다. API process가 재시작되어도 worker가 별도 lifecycle을 가지면 job execution을 더 안정적으로 이어갈 수 있고, API autoscaling 정책과 worker autoscaling 정책을 다르게 둘 수 있다.

### 독립 수평 확장

현재 internal runner는 backend replica 수와 runner 수가 묶인다. Redis/Celery 전환 후에는 API server replica와 worker replica를 독립적으로 조절할 수 있다.

예를 들어 API 트래픽이 많지만 생성 작업량은 낮으면 API만 늘리고, 비디오 생성 backlog가 많으면 worker만 늘릴 수 있다. Postgres row lock과 Celery task idempotency를 함께 유지하면 다중 worker 환경에서도 source of truth는 Postgres에 남는다.

### Provider별 queue 분리

Prompt enhancement, Imagen, Veo는 latency, quota, failure pattern이 다르다. Queue를 `prompt`, `imagen`, `veo`처럼 분리하면 다음 운영 제어가 가능해진다.

- prompt enhancement는 짧고 빈번한 작업으로 낮은 latency를 목표로 둔다.
- Imagen text-to-image는 중간 길이 작업으로 이미지 생성 quota와 concurrency를 제어한다.
- Veo text-to-video/image-to-video는 장시간 작업과 polling을 별도 queue에서 처리한다.
- 특정 provider 장애가 다른 mode의 처리를 막지 않도록 worker pool을 나눌 수 있다.

### Retry/backoff/rate limit/quota 제어

Celery는 retry, countdown, exponential backoff, task routing, worker concurrency 설정을 제공한다. 이를 provider boundary의 public error mapping과 결합하면 다음 제어가 쉬워진다.

- transient provider error는 제한된 횟수만 backoff retry한다.
- quota/rate limit error는 더 긴 delay나 provider별 queue pause 정책을 적용한다.
- terminal user/payload error는 Celery retry 대신 job을 failed로 확정한다.
- Veo polling은 provider operation name을 Postgres에 유지하면서 일정 delay 후 재확인 task로 분리할 수 있다.

단, retry의 최종 권위는 Celery task 횟수가 아니라 Postgres job state와 attempts/error 기록이어야 한다.

### 배포 안정성

API server와 worker를 따로 배포하면 frontend/API 변경과 worker 실행 변경의 blast radius를 줄일 수 있다. API deploy 중에도 기존 worker가 backlog를 처리하거나, worker deploy 중에도 API가 job 생성과 상태 조회를 계속 제공할 수 있다.

또한 worker를 drain/shutdown하는 절차를 별도로 마련할 수 있다. 장시간 task가 있는 Veo queue는 짧은 prompt queue와 다른 graceful shutdown timeout을 가질 수 있다.

### 장애 복구와 idempotency

Redis/Celery는 일반적으로 at-least-once execution 모델이다. 같은 `job_id` task가 중복 실행될 수 있으므로, worker는 항상 Postgres job state를 보고 실행 가능 여부를 판단해야 한다.

Idempotency 원칙은 다음과 같다.

- terminal job은 다시 실행하지 않는다.
- 이미 `generating`, `polling`, `downloading`인 job은 stale 여부와 ownership 정책을 확인한다.
- asset write는 storage helper를 통해 path containment와 중복 저장 정책을 유지한다.
- provider operation name이 존재하는 Veo polling job은 새 생성 호출 대신 기존 operation resume을 우선한다.
- failure marking과 retry job 생성은 state machine과 DB transaction 경계를 통과한다.

### 관측 가능성/metrics

Queue 구조가 생기면 backlog, queue latency, task runtime, retry count, worker health를 별도 지표로 볼 수 있다. 기존 job state history와 결합하면 Ops Console이나 runbook에서 다음 정보를 보여줄 수 있다.

- mode/provider별 pending/queued/generating/polling/failed/completed job 수
- queue별 대기 시간과 처리 시간
- retry/backoff 발생 횟수
- quota/rate limit error 빈도
- worker heartbeat와 최근 task failure
- orphan sweep/polling resume 결과

## 위험과 tradeoff

### Redis/Celery 운영 복잡도

현재 compose는 `db`, `redis`, `backend`, `dispatcher`, `frontend`, `worker`를 실행한다. Redis/Celery와 dispatcher가 기본 개발 흐름에 들어온 만큼 local dev, deployment, monitoring, restart policy, broker persistence 정책을 계속 관리해야 한다.

Celery 설정도 단순 dependency 추가로 끝나지 않는다. task naming, queue routing, concurrency, retry policy, shutdown behavior, logging/metrics 방식을 명확히 정해야 한다.

### Enqueue 실패와 DB transaction 불일치

API가 Postgres에 job을 생성한 뒤 Redis enqueue에 실패할 수 있다. 반대로 enqueue는 성공했지만 DB transaction이 rollback되면 worker가 없는 job_id를 받을 수 있다.

이 위험을 줄이려면 다음 선택지가 있다.

- 초기에는 DB commit 후 enqueue 실패 시 job을 pending으로 남기고 fallback poller나 repair endpoint가 재enqueue한다.
- 안정화 단계에서 outbox table을 도입해 DB transaction 안에 enqueue intent를 기록하고 별도 dispatcher가 Redis에 발행한다.
- worker는 job_id가 없거나 실행 불가능한 상태면 task를 no-op으로 종료한다.

### At-least-once execution과 중복 처리

Celery task는 네트워크 장애, worker crash, ack timing에 따라 중복 실행될 수 있다. 따라서 task 실행 자체를 job 완료의 권위로 삼으면 안 된다.

중복 처리는 Postgres row lock, state machine transition, terminal state guard, provider operation resume 정책으로 방어해야 한다. 특히 provider 호출 직전과 asset 저장 직후의 중복 가능성을 테스트해야 한다.

### Local dev/CI 복잡도 증가

Redis와 worker가 기본 개발 흐름에 들어오면 `AI_PROVIDER=mock` 테스트와 frontend build 외에도 worker smoke test가 필요하다. CI가 느려지거나 불안정해질 수 있으므로 phase별로 최소 smoke 범위를 정해야 한다.

초기 phase에서는 Celery 개념 학습과 API/worker lifecycle 분리 준비를 먼저 진행해 복잡도를 낮춘다. Redis를 단순 signal 용도로 크게 구현하는 별도 중간 단계를 만들기보다, Celery app/task의 최소 구조를 빠르게 붙이고 `AI_PROVIDER=mock` 기준으로 no-cost smoke를 검증하는 방향이 현재 결정과 더 잘 맞는다.

### Mock mode/secret hygiene 유지

모든 phase에서 `AI_PROVIDER=mock`은 credential 없이 동작해야 한다. Redis/Celery 도입이 Vertex credential 요구로 이어지면 안 된다.

CI와 local validation은 계속 mock 기준으로 수행한다. `.env`, `backend/.env`, ADC, service-account JSON, API key, private key 내용은 읽거나 출력하지 않고, `.env.example`에는 비밀이 없는 값만 유지한다.

## 학습 포인트

이 migration은 Celery를 단순 dependency로 추가하는 작업이 아니라, CreativeOps Studio의 job lifecycle을 프로덕션 관점에서 설명할 수 있게 만드는 학습 과제다.

- Broker: Redis는 worker에게 `job_id` task를 전달하는 transport다. job 상태와 payload의 권위는 Redis가 아니라 Postgres에 남긴다.
- Task: Celery task는 `process_job(job_id)`처럼 작고 재실행 가능한 단위로 둔다. 큰 generation payload는 task message에 넣지 않고 worker가 DB에서 다시 읽는다.
- Worker: API process와 분리된 실행 process다. provider 호출, polling resume, asset 저장, failure marking을 담당한다.
- Queue: `prompt`, `imagen`, `veo`처럼 provider/mode별로 분리해 latency, quota, concurrency를 다르게 운영할 수 있다.
- Ack: worker가 task를 언제 성공 처리했다고 broker에 알릴지의 문제다. crash와 중복 실행 가능성을 고려해 Postgres state guard와 함께 설계한다.
- Prefetch: worker가 미리 가져오는 task 수다. Veo처럼 긴 작업은 prefetch가 크면 queue fairness가 나빠질 수 있어 provider별 설정을 검토한다.
- Retry/backoff: transient provider error는 제한된 횟수로 지연 재시도하고, terminal user/payload error는 retry하지 않고 failed로 확정한다.
- Visibility timeout/at-least-once: broker/worker 장애 상황에서는 같은 `job_id`가 다시 실행될 수 있다. 따라서 task는 at-least-once를 전제로 idempotent해야 한다.
- Idempotency: terminal job no-op, state machine transition guard, row lock, provider operation resume, storage helper 기반 asset write로 중복 실행을 방어한다.
- Routing: mode/provider에 따라 queue를 선택하고, worker concurrency와 rate limit을 다르게 둔다.
- Result backend: Celery result를 job 상태의 source of truth로 쓰지 않는다. 필요하면 task debugging 보조 정보로만 쓰고, 사용자에게 보이는 상태는 Postgres job record에서 읽는다.

## 면접/포트폴리오 설명 포인트

- API/worker 분리: FastAPI는 요청/조회에 집중하고, Celery worker는 장시간 provider 작업을 처리한다.
- Postgres source of truth: job state, payload, attempts, asset metadata는 Postgres가 권위 있게 보관한다.
- Redis/Celery는 dispatch layer: Redis/Celery message는 "어떤 job을 처리할지" 알려주는 신호이며, 최종 상태 저장소가 아니다.
- job_id 중심 task payload: task message를 작게 유지하고, worker가 DB에서 최신 record를 조회해 stale/terminal 상태를 방어한다.
- provider별 queue/rate limit: prompt, Imagen, Veo의 latency와 quota 특성이 다르므로 queue와 worker concurrency를 분리한다.
- 장애 복구와 중복 실행 방어: at-least-once execution을 전제로 state machine, row lock, idempotency guard, polling resume을 설계한다.
- mock 기반 no-cost CI: `AI_PROVIDER=mock`에서 credential 없이 API, worker, asset serving, job lifecycle을 검증해 비용과 secret 노출을 피한다.

## 단계적 계획

### Phase 0: 현 상태 baseline/검증 유지

목표는 변경 전 현재 동작을 명확한 baseline으로 고정하는 것이다. 이 phase에서는 worker/queue 코드를 추가하지 않는다.

파일 후보:

- 확인: `docs/architecture.md`
- 확인: `docs/job-lifecycle.md`
- 확인: `backend/app/main.py`
- 확인: `backend/app/services/jobs/runner.py`
- 확인: `backend/tests/*`
- 확인: `docker-compose.yml`

테스트 후보:

- runner가 pending job을 row lock으로 claim하고 `queued`로 전환하는 테스트
- orphan sweep이 stale non-terminal job을 failed로 전환하는 테스트
- polling resume이 `POLLING` + `vertex_operation_name` job을 재스케줄하는 테스트
- mock provider 기반 generation API end-to-end 테스트

검증 명령:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
cd frontend
npm run build
cd ..
docker compose --env-file .env.example config --quiet
docker compose config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

검토 포인트:

- 현재 runner test coverage가 worker 분리 전 regression baseline으로 충분한지 확인한다.
- 문서의 현재 구조 설명과 코드가 어긋나는 부분을 먼저 정리한다.

### Phase 1: Celery 전 API/worker 프로세스 분리 검증

목표는 아주 짧게 가되, Celery 도입 전에 API process와 worker process를 분리하면서 새로 생기는 edge case를 강하게 검증하는 것이다. Redis/Celery 없이 Postgres를 계속 job source of truth로 유지하고, 기존 `InProcessJobRunner`를 별도 worker entrypoint/service에서 실행하는 최소 분리만 구현한다. API process는 job 생성, 상태 조회, 파일 서빙을 담당하고, worker process만 job execution lifecycle을 실행한다.

파일 후보:

- 수정 후보: `backend/app/main.py`
- 생성 후보: `backend/app/worker.py` 또는 `backend/app/cli/worker.py`
- 수정 후보: `backend/app/services/jobs/runner.py`
- 수정 후보: `backend/pyproject.toml`
- 수정 후보: `docker-compose.yml`
- 수정 후보: `docs/architecture.md`
- 수정 후보: `docs/job-lifecycle.md`
- 수정 후보: `docs/runbooks/local-mock.md`

구현 방향:

- FastAPI lifespan에서 runner auto-start를 끄고, API process에서는 runner가 시작되지 않게 한다.
- 별도 worker entrypoint가 기존 `InProcessJobRunner().run_forever()`를 실행한다.
- Docker Compose에 `worker` service를 추가할 경우 같은 backend image, 같은 `DATABASE_URL`, 같은 `DATA_DIR`, 같은 `AI_PROVIDER=mock` env를 사용한다.
- API server는 job 생성 후 Postgres에 pending job을 남기며, worker process는 기존 polling/row lock claim으로 실행 가능한 job을 처리한다.
- worker 단독 실행 시 schema 초기화, asset directory 준비, DB session/engine close, shutdown signal 처리를 명확히 한다.
- Phase 2에서 Celery task로 넘어가도 유지해야 하는 state machine, storage helper, provider boundary, orphan sweep, polling resume 동작을 regression gate로 고정한다.

Phase 1에서 하지 않을 것:

- Redis/Celery 도입
- queue routing 설계 구현
- Celery retry/backoff 구현
- outbox table 도입
- broker 장애 대응 구현
- Redis를 단순 signal 용도로 쓰는 임시 consumer 구현

반드시 통과해야 할 Gate:

- API process에서 runner가 자동 시작되지 않고, worker process에서만 정확히 한 번 실행된다.
- worker 단독 실행 시 `init_db_schema`, `DATA_DIR` 생성, DB close가 보장된다.
- API와 worker가 같은 `DATABASE_URL`, `DATA_DIR`, `AI_PROVIDER=mock`을 공유한다.
- worker env 누락으로 `vertex` provider로 빠지는 위험을 막는다.
- worker down 중 생성된 pending job이 worker 재시작 후 처리된다.
- `queued`, `generating`, `downloading` 중 worker crash가 발생한 job은 orphan sweep 정책으로 복구 또는 실패 처리된다.
- `polling` + `vertex_operation_name`이 있는 Veo job은 새 submit 없이 기존 operation을 resume한다.
- shared volume에서 worker가 저장한 asset을 API `/files`가 읽을 수 있고, 삭제 흐름도 유지된다.
- parent 완료 후 blocked I2V child unblock이 유지되고, parent 실패 cascade도 유지된다.

테스트 후보:

- FastAPI test에서 API process가 runner를 auto-start하지 않는지 확인한다.
- worker entrypoint가 runner를 정확히 한 번 생성하고 shutdown signal을 처리하는지 단위 테스트한다.
- worker 단독 실행 시 schema 초기화, `DATA_DIR` 생성, DB close를 검증한다.
- worker env가 누락되거나 잘못될 때 mock 기본 검증이 깨지지 않고 `vertex` provider로 silent fallback하지 않는지 확인한다.
- worker down 중 생성된 pending job이 worker 재시작 후 처리되는지 integration smoke를 둔다.
- 기존 runner/orphan sweep/polling resume/asset serving/I2V cascade tests를 유지해 process 분리로 인한 regression을 잡는다.
- compose config에 `worker` service가 포함되고 API/worker env와 volume이 일치하는지 smoke로 확인한다.

검증 명령:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
docker compose --env-file .env.example config --quiet
docker compose config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

검토 포인트:

- local dev에서 backend만 띄웠을 때 job이 처리되지 않는 혼란을 README/runbook 또는 compose 기본 흐름으로 어떻게 줄일지 정한다.
- Phase 2의 Celery task가 재사용할 수 있도록 worker entrypoint와 runner lifecycle 경계를 너무 넓히지 않았는지 확인한다.

Phase 1 -> Phase 2 전환 조건은 API process와 worker process의 최소 분리가 mock mode에서 안정적으로 검증되고, 위 Gate가 모두 통과했을 때다. 특히 worker env, shared volume, pending backlog recovery, orphan sweep, Veo polling resume, I2V unblock/cascade가 Celery 없이도 깨지지 않는다는 증거가 있어야 Redis/Celery 도입으로 넘어간다.

### Phase 2: Redis broker + Celery app/task 최소 구현

목표는 Redis를 오직 Celery broker로만 도입하고, 최소 Celery app/task 구조로 `job_id` dispatch를 검증하는 것이다. Celery task payload는 `job_id`만 담고, worker는 task 시작 시 Postgres에서 최신 job을 다시 조회한다. Postgres가 계속 job source of truth이며, Celery result backend는 사용자-visible 상태 저장소로 쓰지 않는다.

기존 "Redis signal만 먼저 도입" 방식은 Celery 중심 결정과 충돌하지 않도록 제거한다. Redis는 독립 임시 consumer를 위한 보조 신호가 아니라 Celery broker로 도입한다. enqueue adapter는 Celery task 발행 경계이며, task payload는 generation payload 전체가 아니라 `job_id`로 제한한다.

파일 후보:

- 생성 후보: `backend/app/services/jobs/enqueue.py`
- 생성 후보: `backend/app/services/jobs/dispatch.py`
- 생성 후보: `backend/app/celery_app.py`
- 생성 후보: `backend/app/services/jobs/tasks.py`
- 수정 후보: `backend/app/api/generations.py`
- 수정 후보: `backend/app/api/prompts.py`
- 수정 후보: `backend/app/config.py`
- 수정 후보: `backend/pyproject.toml`
- 수정 후보: `docker-compose.yml`
- 수정 후보: `.env.example`
- 생성 후보: `backend/tests/services/jobs/test_enqueue.py`
- 생성 후보: `backend/tests/services/jobs/test_celery_tasks.py`

구현 방향:

- Celery app 설정을 backend config 경계 안에 둔다.
- enqueue adapter interface를 만들고 Celery task payload를 `job_id` 중심으로 제한한다.
- Redis dependency와 broker URL 설정을 추가하되 secret이 아닌 local 기본값만 `.env.example`에 둔다.
- DB transaction과 enqueue 순서를 명확히 한다.
- enqueue 실패 시 job은 Postgres에 `pending`으로 남기고, reenqueue repair 또는 polling fallback 정책을 명확히 둔다.
- Redis/Celery enqueue 성공 여부는 dispatch 성공 여부일 뿐, job 존재 여부나 최종 상태의 권위가 아니다.
- Celery task는 시작 시 Postgres에서 최신 job record를 다시 조회하고, terminal/stale 상태면 no-op 처리한다.
- Celery result backend를 사용자에게 보이는 job 상태로 사용하지 않는다. 필요하면 debugging 보조 정보로만 제한한다.
- Redis/Celery 도입 후에도 `AI_PROVIDER=mock` 검증에서 실제 provider client가 생성되지 않아야 한다.
- 초기 task는 mock provider 기준으로 최소 generation flow를 완료하는 것을 목표로 한다.

반드시 통과해야 할 Gate:

- enqueue adapter fake/eager mode에서 `job_id` payload만 발행하는지 검증한다.
- enqueue 실패 시 job은 `pending`으로 유지되고 repair/fallback 대상에서 사라지지 않는다.
- Celery task는 task message의 payload를 신뢰하지 않고 DB에서 최신 job을 다시 조회한다.
- terminal job은 no-op 처리되고, stale/non-executable state guard가 동작한다.
- Redis/Celery 도입 후에도 `AI_PROVIDER=mock`에서는 실제 provider client가 생성되지 않는다.
- docker compose config에서 `redis`와 `worker` service 구조가 검증된다.
- Celery result backend가 사용자-visible job 상태의 source of truth로 쓰이지 않는다.

테스트 후보:

- generation API가 job 생성 후 enqueue adapter를 호출하는지 fake adapter로 검증한다.
- enqueue 실패 시 job이 `pending`으로 남고 repair/fallback 대상이 유지되는지 검증한다.
- Celery eager mode 또는 fake app으로 `job_id` payload만 발행하는지 확인한다.
- task가 job_id를 받아 Postgres에서 최신 job을 다시 조회하는 경계를 테스트한다.
- terminal job task가 no-op 처리되는지 idempotency test를 둔다.
- stale/non-executable state를 가진 job task가 provider/storage boundary를 호출하지 않는지 테스트한다.
- `AI_PROVIDER=mock`에서 Celery task가 실제 Vertex/Gemini/Imagen/Veo client를 만들지 않는지 검증한다.
- docker compose config에 `redis`와 `worker` service가 포함되고 broker/env 구성이 맞는지 smoke로 확인한다.
- 임시 Redis consumer를 새로 만들지 않았는지 확인한다.

검증 명령:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
docker compose --env-file .env.example config --quiet
docker compose config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

검토 포인트:

- Outbox 없이 Redis enqueue를 바로 도입해도 되는지 판단한다.
- Redis broker 장애 시 pending job repair를 어떻게 운영할지 확인한다.
- Celery result backend를 비활성화할지, debugging 보조 용도로만 제한할지 결정한다.

### Phase 3: Queue routing과 job_id dispatch 안정화

목표는 Phase 2의 최소 Celery task를 안정화하고 mode/provider별 queue routing을 도입하는 것이다. `job_id` 중심 dispatch, idempotency guard, duplicate task 처리, stale job 방어를 명확히 검증한다.

파일 후보:

- 수정 후보: `backend/app/celery_app.py`
- 수정 후보: `backend/app/services/jobs/tasks.py`
- 수정 후보: `backend/app/services/jobs/runner.py`
- 수정 후보: `backend/app/services/jobs/handlers.py`
- 수정 후보: `backend/app/services/jobs/enqueue.py`
- 수정 후보: `backend/app/config.py`
- 수정 후보: `backend/pyproject.toml`
- 수정 후보: `docker-compose.yml`
- 생성 후보: `backend/tests/services/jobs/test_celery_tasks.py`
- 생성 후보: `backend/tests/services/jobs/test_queue_routing.py`

구현 방향:

- Task signature는 `process_job(job_id: str)`처럼 job_id 중심으로 유지한다.
- Worker task는 시작 시 Postgres row lock 또는 transition guard로 job 실행 가능 여부를 확인한다.
- Queue routing은 최소 `prompt`, `imagen`, `veo`부터 검토한다.
- 기존 `InProcessJobRunner`는 fallback 또는 migration bridge로 남길지 제거할지 phase 승인 시 결정한다.
- provider/mode별 worker concurrency, prefetch, rate limit 기본값을 문서화한다.
- duplicate dispatch와 reenqueue repair가 같은 job을 중복 완료하지 않도록 state machine 경계를 확인한다.

테스트 후보:

- job mode별 queue name routing test
- Celery task가 terminal job을 no-op 처리하는 idempotency test
- Celery task가 pending job을 state machine을 통해 queued/generating으로 진행시키는 test
- duplicate task가 같은 job을 중복 완료하지 않는 test
- mock provider 기반 Celery eager mode test

검증 명령:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
docker compose --env-file .env.example config --quiet
docker compose config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

검토 포인트:

- Celery eager mode를 unit test에 사용할지, Redis integration test를 별도로 둘지 정한다.
- `prompt`, `imagen`, `veo` queue를 처음부터 모두 분리할지, `generation` 단일 queue에서 시작할지 정한다.

### Phase 4: Retry/backoff/rate limit/dead-letter/observability

목표는 Celery 도입 자체가 아니라 운영 제어를 제품화하는 것이다.

파일 후보:

- 수정 후보: `backend/app/services/vertex/errors.py`
- 수정 후보: `backend/app/services/vertex/retry.py`
- 수정 후보: `backend/app/services/jobs/tasks.py`
- 수정 후보: `backend/app/state_machine.py`
- 생성 후보: `backend/app/services/jobs/metrics.py`
- 수정 후보: `backend/app/api/health.py`
- 수정 후보: `backend/app/schemas.py`
- 수정 후보: `frontend/src/pages/*`
- 생성 후보: `backend/tests/services/jobs/test_retry_policy.py`
- 생성 후보: `backend/tests/services/jobs/test_worker_metrics.py`

구현 방향:

- Provider error code를 transient, quota/rate limit, terminal error로 분류한다.
- Celery retry/backoff는 Postgres attempts/error 기록과 일치시킨다.
- Dead-letter 정책은 별도 queue, failed state detail, 또는 ops-only repair flow 중 하나로 정한다.
- Rate limit은 provider별 worker concurrency, Celery rate_limit, application-level quota guard 중 어떤 조합을 쓸지 정한다.
- Health endpoint 또는 Ops Console에서 queue backlog와 worker heartbeat를 보여줄 수 있는 최소 지표를 설계한다.

테스트 후보:

- transient error가 backoff retry 대상이 되는지 test
- terminal provider error는 retry 없이 failed state가 되는지 test
- quota error가 긴 delay 또는 rate-limit policy로 처리되는지 test
- duplicate retry가 attempts를 과증가시키지 않는지 test
- metrics endpoint가 secret 없이 mock mode에서 동작하는지 test

검증 명령:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
cd frontend
npm run build
cd ..
docker compose --env-file .env.example config --quiet
docker compose config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

검토 포인트:

- Dead-letter를 제품 UI까지 노출할지, backend runbook으로만 관리할지 정한다.
- Provider quota 제어를 queue concurrency로 충분히 볼지, 별도 budget guard가 필요한지 정한다.

### Phase 5: 운영 검증과 rollout

목표는 mock mode와 제한된 live QA를 통해 배포 위험을 줄이고, 기존 runner에서 worker/queue 구조로 안전하게 전환하는 것이다.

파일 후보:

- 수정 후보: `docs/runbooks/local-mock.md`
- 수정 후보: `docs/runbooks/vertex-live-qa.md`
- 수정 후보: `docs/provider-modes.md`
- 수정 후보: `docs/testing.md`
- 수정 후보: `docs/architecture.md`
- 수정 후보: `docs/job-lifecycle.md`
- 생성 후보: `docs/runbooks/worker-queue-operations.md`
- 수정 후보: `docker-compose.yml`
- 수정 후보: CI workflow 파일이 있다면 해당 workflow

검증 방향:

- `AI_PROVIDER=mock` compose에서 API, frontend, Redis, worker가 end-to-end로 job을 완료하는지 확인한다.
- Queue별 worker를 하나씩 끄고 backlog/recovery가 예상대로 동작하는지 확인한다.
- API 재시작 중에도 worker가 job을 계속 처리하거나 안전하게 no-op 처리하는지 확인한다.
- Worker 재시작 후 polling resume과 orphan sweep 정책이 문서와 일치하는지 확인한다.
- Vertex live QA는 사용자가 명시적으로 승인한 경우에만 비용과 credential 조건을 확인하고 제한적으로 수행한다.

테스트 후보:

- mock compose smoke: text-to-image job 생성 후 completed와 asset serving 확인
- mock compose smoke: image-to-video placeholder flow 확인
- worker restart smoke: pending/queued/polling job recovery 확인
- enqueue failure repair smoke: pending job 재발행 확인
- frontend build와 API contract check

검증 명령:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
cd ..
cd frontend
npm run build
cd ..
docker compose --env-file .env.example config --quiet
docker compose config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

검토 포인트:

- rollout flag를 `JOB_DISPATCH_MODE=internal|worker|celery`처럼 둘지 결정한다.
- 기존 `InProcessJobRunner` 기반 worker fallback을 Celery 안정화 후 언제 제거할지 결정한다.
- Live Vertex QA 범위와 비용 한도를 승인받는다.

## 검토 질문

- Celery는 기본 worker/queue dispatch layer로 채택했다. RQ/Arq/직접 asyncio worker는 비교 대안으로 문서에 남긴다.
- Phase 1 API/worker process 분리, Phase 2 Redis/Celery dispatch, Phase 3 outbox dispatcher는 완료됐다.
- Outbox table은 Phase 3에서 도입했다. 남은 과제는 dispatcher 운영 정책과 실패 관측성을 더 단단히 하는 것이다.
- Celery broker 장애 시 pending job repair를 현재 runbook/dispatcher 정책으로 충분히 볼지, 추가 자동 복구를 둘지?
- Queue routing은 현재 단일 `generation` queue에서 시작한다. 다음 단계에서 `prompt`, `imagen`, `veo`로 분리할지?
- Celery worker별 concurrency, prefetch, rate limit 기본값을 provider/mode별로 어떻게 둘지?
- Veo polling은 같은 task의 retry/countdown으로 다룰지, 별도 polling task로 분리할지?
- Celery retry 횟수와 Postgres `attempts`를 어떻게 매핑할지?
- Celery ack 정책과 worker crash 시 재실행 가능성을 어떤 idempotency guard로 방어할지?
- Celery result backend는 비활성화할지, debugging 보조 정보로만 제한할지?
- Local dev 기본값은 `db`, `redis`, `backend`, `dispatcher`, `frontend`, `worker`를 띄우는 compose로 확정됐다.
- CI smoke 범위는 unit test만 둘지, Redis 포함 compose smoke까지 둘지?
- Worker metrics는 backend health endpoint에 최소 노출할지, 별도 Ops Console 화면까지 포함할지?
- Internal asyncio runner는 Celery 안정화 후 제거할지, mock/local fallback으로 유지할지?

## 승인 전 원칙

- 이 문서는 구현 지시가 아니라 migration 기록과 다음 검토용 계획이다.
- 승인 전에는 provider별 queue routing, retry/backoff/rate-limit, dead-letter, worker metrics, API contract를 변경하지 않는다.
- 모든 구현 phase는 `AI_PROVIDER=mock` 기준 검증을 먼저 통과해야 한다.
- 실제 Vertex/Gemini/Imagen/Veo 호출은 사용자가 명시적으로 승인한 live QA 상황에서만 수행한다.
- 민감 파일과 credential 내용은 읽거나 출력하거나 커밋하지 않는다.
