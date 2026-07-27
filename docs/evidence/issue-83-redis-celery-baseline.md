# Issue #83 Redis/Celery GKE 기준선

**측정 시각:** 2026-07-27 06:24~06:31 UTC
**Harness commit:** `dd6c930cadf1d01af42336d786c59a85b63a7b1c`
**Run ID:** `redis-celery-20260727T0626Z`
**결과:** steady phase 통과, 첫 burst phase에서 Cloud SQL connection 고갈로 중단

## 증거 범위

이 결과는 `AI_PROVIDER=mock`에서 public API, Postgres outbox, dispatcher,
Redis/Celery, worker, storage를 포함한 오케스트레이션 기준선이다. 실제 Imagen/Veo
생성 시간, 품질, Vertex quota/429, provider 비용을 측정하지 않았다. 실제 Vertex
호출은 0건이다.

raw report는 Git에서 제외된
`benchmarks/orchestration/runs/redis-celery-20260727T0626Z.json`에 보존했다.
SHA-256은
`abe5b638359458eea4aeda79247bdf7c2a8bbbfbf2beddbd4aff2bb275d84463`이다.
secret-safe 사후 복원 계산은
`docs/evidence/issue-83-redis-celery-failure-reconstruction.json`에 별도로 고정했다.

증거의 출처를 다음처럼 구분한다.

- **Harness 직접 계측:** warm-up/steady 120개 record, latency/throughput, resource
  sample, 첫 HTTP 500, 최초 cleanup 결과
- **사후 복원:** burst HTTP 201/500 수, pending 고립 수, 수동 복구와 최종 cleanup
- **운영 진단:** API/worker 오류 로그, DB read-only 설정, 최종 ops/deployment
  read-back

burst 수치는 수정 전 harness가 첫 실패 future에서 결과 수집을 중단한 뒤 생성된
raw report만으로 직접 집계한 값이 아니다. 당시 executor는 예약한 200개 요청의 완료를
기다렸지만 raw report에는 warm-up/steady 120개 record와 첫 HTTP 500만 남았다. 따라서
아래 burst 수치는 outbox 전후값, API Pod별 오류 집계, run-id 조회를 교차 검증해
복원한 값이다.

## 환경

| 항목 | 측정 조건 |
| --- | --- |
| GCP | personal project, Seoul `asia-northeast3-a` |
| Provider | `mock_provider`, credentials not required |
| API | 2 replicas, 각 request 100m/512Mi, limit 1 CPU/1Gi |
| Dispatcher | 1 replica, request 100m/256Mi, limit 500m/512Mi |
| Worker | 1 replica, Celery concurrency 2, request 200m/1Gi, limit 1 CPU/2Gi |
| Broker | Redis Basic 1 GiB, queue `generation` |
| Database | Cloud SQL PostgreSQL 16, `db-f1-micro` |
| Dispatch | Celery, late ack, reject on worker lost, prefetch 1 |
| Benchmark rate limit | worker Imagen 5,000/min 임시 override |
| 정상 기본값 | 측정 후 worker Imagen 5/min으로 원복 |

benchmark 전에는 active job 0, outbox pending 0, Redis queue 0이었다. API 2,
dispatcher 1, worker 1은 모두 desired=ready였고 restart 0이었다.

## Harness 직접 계측: Steady 결과

warm-up 20건은 최종 aggregate에서 제외했다. steady phase는 submit concurrency 2로
100건을 생성했고 100건 모두 완료했다.

| 지표 | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| submit API | 28.736 ms | 51.200 ms | 310.481 ms | 1,092.265 ms |
| commit -> worker claim | 28.232 s | 52.148 s | 54.606 s | 55.186 s |
| worker claim -> completed | 0.711 s | 1.388 s | 1.561 s | 1.682 s |
| commit -> completed | 28.901 s | 53.306 s | 55.358 s | 55.591 s |

- 처리량: `1.730095 jobs/s`
- job failure: 0
- duplicate execution: 0
- rate-limit wait: 0

submit latency는 낮았지만 worker 처리량보다 job 생성 속도가 높아 queue가 누적됐다.
따라서 end-to-end p95의 대부분은 provider가 아니라 worker claim 전 대기
`52.148 s`였다.

## 사후 복원: Burst failure

첫 burst는 200건을 submit concurrency 50으로 예약했다. 사후 복원 결과는 다음과
같다.

| 결과 | 건수 | 비율 |
| --- | ---: | ---: |
| HTTP 201 / outbox 생성 | 146 | 73.0% |
| HTTP 500 | 54 | 27.0% |
| accepted 후 pending 고립 | 20 | accepted burst의 13.7% |

accepted 수는 benchmark 전후 outbox `4 -> 270` 증가량 `266`에서 harness가 직접
계측한 warm-up/steady `120`건을 뺀 `146`건이다. 예약한 burst 요청 `200`건에서 이를
빼면 HTTP 500은 `54`건이다. 두 API Pod 오류 집계 `28 + 26 = 54`와도 일치한다.
pending 고립 `20`건은 복구 직전 `active=20`, `pending=20`, `outbox pending=0`,
Redis queue `0` read-back과 repair 결과 `selected=20`을 대조했다.

API와 worker의 첫 구체적 예외는 모두 다음과 같았다.

```text
asyncpg.exceptions.TooManyConnectionsError:
remaining connection slots are reserved for roles with privileges of the
"pg_use_reserved_connections" role
```

read-only DB 진단은 다음을 확인했다.

- `max_connections=25`
- `superuser_reserved_connections=3`
- incident 복구 후 관측한 current connections `20`
- `backend/app/db.py`는 process별 SQLAlchemy 기본 pool을 사용하며 명시적인
  `pool_size`, `max_overflow`, `pool_timeout` 예산이 없다.

API 2개, dispatcher, Celery worker process들이 하나의 22-slot application connection
budget을 공유하지만 배포 설정에는 전체 connection budget이 없다. burst에서 API가
새 connection을 만들지 못해 500을 반환했고, worker task도 claim 전에 같은 오류로
실패했다.

Celery task의 DB connection 예외는 worker process crash가 아니므로
`task_reject_on_worker_lost=true`가 보호하지 못했다. task는 실패 처리된 뒤 Redis queue에서
사라졌고 Postgres job 20건은 `pending`으로 남았다. outbox는 이미 `published`라 dispatcher가
자동 재발행하지 않았다.

## Peak 운영 신호

실패 전까지 14개 표본을 수집했고 sample error는 0이었다.

| 신호 | peak |
| --- | ---: |
| Celery queue depth | 94 |
| active jobs | 131 |
| outbox pending | 73 |
| API CPU 합계 | 73m |
| API memory 합계 | 195 MiB |
| dispatcher CPU | 12m |
| dispatcher memory | 90 MiB |
| worker CPU | 980m |
| worker memory | 206 MiB |

worker CPU는 1 CPU limit에 근접했다. 이는 steady 처리량과 긴 claim backlog의 별도
병목 신호다. 반면 burst HTTP 500과 pending 고립의 직접 원인은 API/worker 로그로
확인한 DB connection 고갈이다.

## 복구와 원복

1. Redis queue가 0인데 Postgres pending이 20인 것을 확인했다.
2. 기존 `reenqueue_pending_jobs` service 경계로 20건을 재발행했다:
   `selected=20 dispatched=20 failed=0`.
3. run-id가 일치하는 잔여 157건이 모두 completed인지 확인했다.
4. public DELETE API를 concurrency 2로 호출해 157건과 asset을 정리했다:
   failure 0.
5. 임시 worker rate limit override를 제거하고 rollout을 완료했다.
6. 최종 read-back:
   - worker rate limit 5/min
   - mock provider
   - active job 0
   - Redis queue 0
   - API 2/2, dispatcher 1/1, worker 1/1
   - workload Pod restart 0
   - 기존 job 3건만 유지

outbox event는 job FK가 없어 삭제되지 않는다. 기준선 run에서 생성된 266개 published
event row가 남아 최종 total은 270이다. Secret, credential, broker URL은 evidence에
기록하지 않았다.

## 결론

현재 결과만으로 “Redis를 제거하면 빨라진다”라고 주장할 수 없다. 확인된 사실은
다음과 같다.

1. steady에서 submit API는 빠르지만 worker backlog 때문에 completion p95가
   `53.306 s`다.
2. burst concurrency 50은 Cloud SQL 25-connection 한계를 초과해 POST의 27%가
   500으로 실패한다.
3. accepted job의 13.7%가 worker DB connection 실패 후 자동 복구되지 않았다.
4. PostgreSQL polling worker로 이동하면 DB 의존도가 더 커지므로 connection budget과
   claim failure recovery를 먼저 고정하지 않으면 Redis 비용을 줄이는 대신 신뢰성을
   악화시킬 수 있다.

다음 A/B는 DB connection budget과 worker transient DB failure 복구를 별도 Issue에서
먼저 해결한 후, 동일한 20 + 100 + 200x5 workload를 다시 실행해야 한다. 개선 후에도
같은 concurrency, replica, worker concurrency, mock media 조건을 유지한다.
