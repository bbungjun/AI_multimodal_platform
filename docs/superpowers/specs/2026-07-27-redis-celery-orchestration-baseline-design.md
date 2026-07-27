# Redis/Celery 오케스트레이션 기준선 설계

**Issue:** [#83](https://github.com/bbungjun/AI_multimodal_platform/issues/83)

## 목적

현재 GKE의 `Postgres outbox -> dispatcher -> Redis/Celery -> worker` 경로와 이후
`Postgres -> worker` 대안을 동일한 조건에서 비교한다. 목표는 Redis 비용 제거만이
아니라 job 전달 지연과 처리량도 함께 개선되는지 검증하는 것이다.

## 증거 경계

`AI_PROVIDER=mock`은 외부 Vertex 지연, 쿼터, 비용 변동을 제거하므로 오케스트레이션
A/B의 주 측정 모드로 사용한다.

이 측정으로 주장할 수 있는 것은 다음과 같다.

- generation submit API의 p50/p95/p99
- job commit부터 worker claim까지의 지연
- mock job 완료까지의 end-to-end 지연과 처리량
- 실패, timeout, 중복 실행
- outbox backlog, Celery queue depth, workload resource 사용량

이 측정으로 Imagen/Veo의 실제 생성 지연, 품질, Vertex 429 특성, provider 비용은
주장하지 않는다. 실제 Vertex 검증은 구조 변경 후 소량의 compatibility smoke로
분리하고, 사용자의 별도 비용 승인을 받는다.

## Workload

| Phase | Jobs | 제출 동시성 | 집계 포함 |
| --- | ---: | ---: | --- |
| warm-up | 20 | 2 | 아니오 |
| steady | 100 | 2 | 예 |
| burst 1~5 | 각 200 | 50 | 예 |

총 생성 job은 1,120개다. 각 phase의 모든 job이 terminal state에 도달한 뒤 다음
phase를 시작한다. 모든 요청은 T2I mock 1장으로 고정하고 prompt에 run/phase/index를
넣어 실행 단위를 식별한다.

## 지표 정의

- `submit_latency_ms`: client가 `POST /api/generations`를 보낸 시점부터 201 응답까지
- `claim_latency_ms`: `state_history.queued.at - created_at`
- `execution_latency_ms`: `state_history.completed.at - state_history.queued.at`
- `end_to_end_latency_ms`: `state_history.completed.at - created_at`
- `throughput_jobs_sec`: phase job 수 / 첫 생성부터 마지막 완료까지의 server timestamp 구간
- `duplicate_execution`: deterministic mock job에서 `attempts > 1` 또는 queued transition이
  한 번을 초과한 경우

각 latency는 p50/p95/p99/max를 기록한다. warm-up은 환경 예열에만 쓰고 최종 aggregate에서
제외한다.

## Harness 경계

`scripts/benchmark_mock_orchestration.py`는 public HTTP API를 통해 job을 생성하고,
목록 API로 상태를 모아 구조별로 재사용한다. 애플리케이션 DB를 직접 import하거나
state machine, outbox, storage helper를 우회하지 않는다.

GKE 모드에서는 다음 read-only evidence를 함께 수집한다.

- release profile의 account/project/cluster/namespace와 현재 context 일치 여부
- mock health와 dispatch mode
- API/dispatcher/worker image, replica, request/limit
- `kubectl top pod --containers`의 CPU/memory 표본
- worker pod 내부에서 broker URL을 출력하지 않고 조회한 Celery queue `LLEN`
- `/api/ops/health`의 active job과 outbox pending 표본

raw run artifact는 `benchmarks/orchestration/runs/`에 저장하고 Git에서 제외한다.
비밀이나 개인 credential 경로가 없는 검토된 aggregate만 `docs/evidence/`에 남긴다.

## 안전장치

- `--execute`가 없으면 workload를 만들지 않는 preflight/dry-run으로 동작한다.
- release profile의 명시적 personal account/project/cluster guard가 틀리면 중단한다.
- health가 `mock_provider`가 아니거나 dispatch mode가 기대와 다르면 중단한다.
- worker의 Imagen rate limit이 benchmark 최소값보다 작으면 job을 만들기 전에 중단한다.
- Secret payload, broker URL, ADC, API key는 읽거나 출력하지 않는다.
- benchmark가 끝난 뒤 terminal job과 asset은 public DELETE API로 정리한다.
- outbox event는 현재 job FK가 없으므로 자동 삭제되지 않는다. run 전후 증가량을
  증거에 기록하고, 이번 benchmark에서 임의 DB cleanup SQL은 실행하지 않는다.
- 임시 worker rate-limit override는 실행 runbook에서 원래 Deployment spec으로 복구하고
  rollout 및 mock health를 다시 확인한다.

## 결과 해석

Redis/Celery 기준선과 PostgreSQL worker 후보는 같은 harness, workload, worker concurrency,
API replica, GKE node 조건으로 비교한다. 다음 조건을 모두 만족할 때만 대안을 채택한다.

1. Redis instance를 제거할 수 있어 고정 인프라 비용이 감소한다.
2. claim latency와 end-to-end latency의 p95가 기준선보다 악화되지 않고 목표 개선폭을 보인다.
3. 처리량이 기준선보다 악화되지 않는다.
4. 실패, 중복 실행, crash recovery에서 현재의 at-least-once 안전성을 유지한다.

