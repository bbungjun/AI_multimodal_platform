# GKE burst에서 Cloud SQL connection 고갈과 pending job 고립

## 증상

Issue #83 mock 오케스트레이션 benchmark의 첫 200-job burst, submit concurrency 50에서
다음 현상이 동시에 발생했다.

- `POST /api/generations` HTTP 500
- `DELETE /api/generations/{id}` HTTP 500
- Celery task 실패
- Redis queue는 0이지만 Postgres job 20건은 `pending`
- outbox event는 이미 `published`

Pod restart, mock provider failure, Redis 연결 오류는 없었다.

## 첫 구체적 예외

두 API Pod와 worker Pod 모두 같은 예외를 기록했다.

```text
asyncpg.exceptions.TooManyConnectionsError:
remaining connection slots are reserved for roles with privileges of the
"pg_use_reserved_connections" role
```

따라서 public 500, cleanup 실패, pending 고립을 별개 문제로 추측하지 않고 공통 DB
connection 경계를 역추적했다.

## 확인한 상태

read-only DB query:

```text
max_connections=25
superuser_reserved_connections=3
current_connections=20
```

배포는 API 2개, dispatcher 1개, Celery worker concurrency 2를 실행한다.
`backend/app/db.py`는 모든 process에서 다음 기본 engine을 만든다.

```python
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
```

Cloud SQL의 application connection slot은 최대 22개지만, 여러 process의 SQLAlchemy
pool을 합산한 budget, `pool_size`, `max_overflow`, `pool_timeout` 설정이 없다. steady
traffic에서는 pool 재사용으로 드러나지 않았고 burst에서 새 checkout/connect가 동시에
발생하면서 한계를 넘었다.

## pending job이 자동 복구되지 않은 이유

1. API transaction이 성공한 job은 Postgres job과 outbox event를 함께 commit했다.
2. dispatcher가 Celery task를 Redis에 발행하고 outbox를 `published`로 바꿨다.
3. worker가 task를 받았지만 job row claim을 위한 DB connection을 만들지 못했다.
4. `process_job`이 `TooManyConnectionsError`를 raise했다.
5. worker process 자체는 죽지 않았으므로 `task_reject_on_worker_lost=true`가 적용되지
   않았다.
6. 실패한 task는 Redis queue에서 사라졌고, job은 `pending`, outbox는 `published`로
   남았다.

현재 late ack 설정은 worker process loss를 보호하지만 handler 진입 전 transient DB
예외를 자동 재시도하거나 reject하지 않는다.

## 실제 복구

복구 전에는 반드시 ops와 Redis queue를 함께 확인한다. 이 incident에서는 active job
20, pending 20, outbox pending 0, Redis queue 0이었다.

기존 repair service를 dispatcher Pod에서 실행했다. DB credential은 Pod environment에서
opaque하게 사용했고 출력하지 않았다.

```bash
dispatcher_pod="$(kubectl get pod -n creativeops-portfolio \
  -l app=creativeops-dispatcher \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl exec -n creativeops-portfolio "$dispatcher_pod" -- python -c \
  'import asyncio; from app.services.jobs.repair import reenqueue_pending_jobs; r=asyncio.run(reenqueue_pending_jobs(limit=100)); print(f"selected={r.selected} dispatched={r.dispatched} failed={r.failed}")'
```

결과:

```text
selected=20 dispatched=20 failed=0
```

20건이 terminal state에 도달한 뒤 benchmark run-id가 정확히 일치하는 job만 public
DELETE API로 concurrency 2에서 정리했다. 임시 rate-limit override를 제거한 뒤 worker
rollout, rate limit 5, mock health, active 0, queue 0, desired=ready, restart 0을 확인했다.

## 수정 전 검증해야 할 가설

아래는 아직 구현 결과가 아니라 후속 Issue의 검증 항목이다.

1. Cloud SQL `max_connections`에서 reserved/background connection과 모든 application
   process의 pool budget을 빼고 API/dispatcher/worker별 pool을 명시적으로 제한한다.
2. `pool_size`, `max_overflow`, `pool_timeout`을 환경 계약과 Terraform resource
   math로 연결하고 replica/concurrency 변경 시 plan에서 상한을 검증한다.
3. DB checkout timeout/TooManyConnections를 무조건 500으로 노출하지 않고 overload
   signal과 retry policy를 명시한다.
4. Celery task가 job claim 전 transient DB failure를 만나면 bounded retry/reject하고,
   retry exhaustion 시 Postgres에 repair 가능한 상태를 남긴다.
5. `published outbox + pending job + broker task 없음`을 탐지하는 reconciliation과
   alert를 추가한다.
6. 같은 GKE workload에서 stress를 다시 실행해 HTTP failure 0, stranded pending 0,
   cleanup failure 0을 확인한다.

Cloud SQL tier를 올리는 것만으로 통과시키면 process별 connection budget 부재와 task
recovery 결함이 남는다. 반대로 pool만 지나치게 줄이면 API queueing과 worker 처리량이
악화될 수 있으므로 latency, failure, connection peak를 함께 비교해야 한다.
