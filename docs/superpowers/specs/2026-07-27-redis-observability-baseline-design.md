# Redis 오케스트레이션 관측성 보강 설계

**Issue:** [#83](https://github.com/bbungjun/AI_multimodal_platform/issues/83)
**PR:** [#85](https://github.com/bbungjun/AI_multimodal_platform/pull/85)
**상태:** 사용자 승인된 Hybrid 설계

## 문제

첫 Redis/Celery GKE 기준선은 application orchestration 지표와 Celery queue depth를
수집했지만 Memorystore 자체의 CPU, memory, client, command, network, cache 지표를
같은 실행 artifact에 포함하지 않았다. 이 상태에서는 Redis가 병목이 아니었다는
주장을 API/worker/DB 신호로는 설명할 수 있어도, Redis의 실제 부하와 여유 용량을
수치로 증명할 수 없다.

2026-07-27의 원 실행 시간대에는 Cloud Monitoring 이력이 남아 있다. Redis metric
descriptor 192개를 조회했고, 대상 Basic 1 GiB 인스턴스에서 39개 metric에 실제
시계열이 존재했다. 따라서 기존 실행은 사후 복원하고, 이후 실행은 live Redis
표본과 Cloud Monitoring을 함께 수집한다.

## 목표와 비목표

목표:

- Redis `INFO`와 queue depth를 기존 GKE sampler 주기로 함께 수집한다.
- 누적 counter는 실행 구간 delta, gauge는 p50/p95/max로 집계한다.
- command별 calls, total time, weighted usec/call을 기록한다.
- Cloud Monitoring에서 대상 인스턴스에 실제 존재하는 모든 Redis 시계열을 UTC
  구간으로 export하고 원본 hash와 요약을 남긴다.
- 기존 run의 Redis 지표를 idle 비교 구간과 함께 사후 복원한다.
- 다음 PostgreSQL worker A/B가 동일한 Redis 지표 계약을 사용하게 한다.

비목표:

- Redis host, port, broker URL, credential 또는 access token을 artifact에 기록하지 않는다.
- 실제 Vertex provider latency, 품질 또는 비용 지표를 Redis 지표와 혼합하지 않는다.
- 이번 보강 과정에서 새 benchmark traffic이나 cloud resource 변경을 수행하지 않는다.
- 192개 descriptor 중 대상 인스턴스에 시계열이 없는 metric을 0으로 해석하지 않는다.

## 선택한 접근: Hybrid

### 대안 1: Cloud Monitoring만 사용

과거 실행 복원이 가능하고 Google 관리 서비스 관점의 지표를 얻을 수 있다. 그러나
기본 해상도가 60초이고 수집 지연이 있어 짧은 burst와 phase 경계를 정밀하게 나누기
어렵다.

### 대안 2: Redis `INFO`만 사용

기존 2초 sampler에 결합할 수 있어 phase 내 peak와 counter delta가 정확하다. 그러나
과거 실행을 복원할 수 없고 Cloud Monitoring의 관리 서비스 시계열과 교차 검증할 수
없다.

### 선택: 두 소스를 함께 사용

Redis `INFO`는 live 고해상도 evidence, Cloud Monitoring은 지연된 관리 서비스
evidence로 사용한다. 두 값이 완전히 같아야 한다고 가정하지 않고, 각 source와
해상도, 집계 규칙을 report에 명시한다.

## Live Redis 수집

기존 worker Pod 내부 probe가 opaque broker 설정으로 Redis에 연결한다. 연결정보는
출력하지 않고 다음 safe whitelist만 JSON으로 반환한다.

Gauge:

- queue depth
- connected/blocked clients
- used memory, peak used memory, maxmemory
- instantaneous ops/sec
- instantaneous input/output KiB/sec
- key count와 expiration key count
- pub/sub channel과 pattern 수
- role, uptime, RDB/AOF 상태

Cumulative counter:

- total connections received
- total commands processed
- total network input/output bytes
- keyspace hits/misses
- expired/evicted keys
- rejected connections
- Redis parent/main-thread user/sys CPU seconds

Command stats:

- command name
- calls
- total usec
- usec per call
- rejected/failed calls가 provider에서 제공되면 해당 값

probe는 password, URL, host, port, client connection kwargs와 `INFO`의 whitelist 밖
필드를 반환하지 않는다. `commandstats` key도 command name과 숫자 field만 허용한다.
`INFO`와 `LLEN` 자체가 만드는 작은 observer effect는 report에 기록한다.

## Live 집계

기존 sample timestamp를 source of truth로 사용한다.

- Gauge: p50, p95, max와 마지막 값
- Counter: 첫 표본과 마지막 표본의 차이
- Counter reset: 마지막 값이 첫 값보다 작으면 delta를 만들지 않고
  `counter_reset=true`로 표시
- CPU utilization: CPU seconds delta를 sample elapsed seconds로 나눈 비율
- Cache hit ratio: `hit_delta / (hit_delta + miss_delta)`; 분모가 0이면 null
- Command weighted latency: `total_usec_delta / calls_delta`; calls가 0이면 null
- Command 목록: calls delta 내림차순으로 정렬하되 raw report에는 전체를 유지
- 모든 Redis sample 실패는 기존 sampler error와 동일하게 benchmark invalidation 사유

## Cloud Monitoring 사후 export

별도 exporter는 release profile의 account/project/instance guard를 사용한다.
`infra/gcp/release-profile.json`에 non-secret `redis_instance_name`을 추가해
`creativeops-portfolio-redis`를 명시적으로 pin하고, region과 조합한 full instance
resource name만 artifact에 기록한다.

입력:

- release profile
- UTC start/end
- 60초 정렬 구간
- output path

처리:

1. `redis.googleapis.com/` descriptor를 조회한다.
2. 대상 인스턴스와 시간 구간에 실제 시계열이 있는 metric만 수집한다.
3. HTTP 429/5xx는 횟수와 총 대기시간이 제한된 exponential backoff로 재시도한다.
4. DELTA는 60초 bucket별 값과 구간 합계를, GAUGE는 bucket별 값과
   p50/p95/max를 기록한다.
5. metric/resource label은 기록하되 project, region, instance id, node id 외의
   connection 정보는 기록하지 않는다.
6. raw export는 ignored run artifact에 저장하고 SHA-256을 committed evidence에 남긴다.

access token은 process memory와 HTTP Authorization header에서만 사용하며 stdout,
stderr, artifact에 기록하지 않는다. API 오류에는 URL query나 header를 출력하지 않는다.

## 기존 실행 복원 구간

원 harness artifact:

- 시작: `2026-07-27T06:24:56.287198Z`
- 종료: `2026-07-27T06:26:23.626116Z`

Cloud Monitoring은 60초 bucket이므로 다음 구간을 분리한다.

- idle 비교: `[06:21:00Z, 06:24:00Z)`
- benchmark/즉시 실패 처리: `[06:24:00Z, 06:27:00Z)`
- recovery 관찰: `[06:27:00Z, 06:32:00Z)`

`06:24~06:27`은 원 run보다 넓어 첫 4초 이전 background activity와 종료 후 최대
37초의 즉시 cleanup/recovery를 포함한다. 이를 harness 직접 계측이라고 부르지 않고
`Cloud Monitoring post-hoc, 60s-aligned`로 표시한다. idle과의 차이는 참고값이며
완전한 workload attribution으로 주장하지 않는다.

## Artifact

- ignored raw:
  `benchmarks/orchestration/runs/redis-celery-20260727T0626Z-redis-monitoring.json`
- committed summary:
  `docs/evidence/issue-83-redis-monitoring-backfill.json`
- 사람이 읽는 결과:
  `docs/evidence/issue-83-redis-celery-baseline.md`

committed summary는 raw SHA-256, descriptor 수, available metric 수, query error 수,
구간 정의, 주요 aggregate와 source limitation을 포함한다.

## 오류 처리

- Redis probe JSON이 malformed이거나 whitelist type과 다르면 sample error
- worker Pod exec timeout이면 sample error
- counter reset이면 해당 delta만 unavailable
- Monitoring query가 bounded retry 후 실패하면 metric과 public error type을 기록하고
  evidence를 incomplete로 표시
- descriptor 192개 중 시계열이 없는 metric은 `not_observed`, 값 0은 `observed_zero`
- raw hash가 committed summary와 다르면 evidence invalid

## 테스트

테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다.

- Redis probe JSON parser가 safe whitelist만 허용
- secret-like key와 connection field가 report에 들어가지 않음
- gauge percentile/peak/last 집계
- cumulative counter delta와 reset 처리
- CPU utilization과 cache hit ratio 계산
- command calls/total usec/weighted latency 계산
- Monitoring descriptor/time-series normalization
- 39개 available metric과 no-series metric 구분
- 429 bounded retry와 retry exhaustion
- raw artifact hash 검증
- 기존 sampler의 queue/resource/ops 집계 회귀 방지

## 수용 기준

1. local focused test와 전체 backend test가 통과한다.
2. representative Redis `INFO` fixture가 live sample과 summary 계약을 검증하고,
   기존 local mock 3-job orchestration E2E가 회귀 없이 통과한다.
3. GKE dry-run은 실제 worker Redis `INFO` safe snapshot을 검증하되 연결정보를
   출력하지 않는다.
4. 기존 GKE run의 39개 metric을 query error 0으로 복원한다.
5. committed evidence가 raw export hash와 구간/집계 규칙을 명시한다.
6. 새 deployed stress와 실제 Vertex 호출은 0건이다.
7. PR #85의 CI와 독립 재검토가 통과한다.
