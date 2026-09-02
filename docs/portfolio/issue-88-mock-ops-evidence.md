# Issue #88 Mock-first Operations Evidence Design

## 상태와 증거 등급

- Issue: [#88](https://github.com/bbungjun/AI_multimodal_platform/issues/88)
- Branch: `codex/issue-88-mock-ops-evidence`
- Design baseline: `d650369` (PR #91 merged `main`)
- Current level: `Planned`
- Target level: source/configuration은 `Implemented`, 로컬 Compose 실행 결과는
  `Mock Verified`
- Historical cloud evidence: 기존 GKE, Managed Prometheus, HPA 결과만 해당 revision의
  `Live Verified (historical)`로 유지
- Deferred: 신규 GKE/HPA/cloud 검증, 실제 Gemini/Imagen/Veo 호출, GPU 운영

이 문서는 구현 전 설계 기록이다. 아래의 dashboard, fault profile, k6 결과와 복구
결과는 아직 실행 증거가 아니며, 검증 전에는 `Implemented`나 `Mock Verified`로
승격하지 않는다.

## 배경과 문제

현재 저장소에는 mock 생성 흐름, `/metrics`, `/api/ops/health`, GCP monitoring Terraform,
k6 live-provider 부하 스크립트와 Celery 복구 설정이 각각 존재한다. 그러나 비용과
credential 없이 한 번에 재현할 수 있는 로컬 관측성 stack, deterministic provider
fault, alert firing/resolved 증거, worker interruption drill은 없다.

포트폴리오 관점의 문제는 기능 부재만이 아니다. 과거 GKE 실증과 현재 로컬 mock
실증을 구분하지 않으면 다음을 정확하게 설명할 수 없다.

- 현재 revision의 metric과 retry/error contract가 반복 검증되는가?
- alert가 어떤 신호와 최소 traffic 조건으로 발생하고 복구되는가?
- worker가 중단됐을 때 어떤 상태는 자동 복구되고 어떤 상태는 운영자 조치가 필요한가?
- 측정값이 실제 provider 품질이나 cloud 운영 증거로 과장되지 않았는가?

## 현재 구현 관측과 gap

| 영역 | 현재 확인된 구현 | Issue #88에서 닫을 gap |
|---|---|---|
| HTTP metric | `/metrics`가 request count, status, duration histogram을 노출 | 로컬 Prometheus scrape와 Grafana p50/p95/p99 dashboard 없음 |
| Provider metric | prompt API만 bounded `code/status/retryable` failure counter 기록 | generation failure와 fault별 metric contract가 일관되지 않음 |
| 운영 상태 | `/api/ops/health`가 DB job/outbox/resumable polling/recent failure를 조회 | 부하 전/중/후 snapshot 수집과 worker 상태 결합 자동화 없음 |
| Mock fault | Imagen에 `[[mock-fail:imagen]]` test sentinel만 존재 | delay, 429, 5xx, timeout, malformed response와 복구 profile 없음 |
| Retry | provider retry/backoff와 public error mapping 구현 | prompt mock fast path가 retry/error boundary를 우회함 |
| Celery | late ack, reject-on-worker-lost, prefetch 1, worker ping 구현 | 모든 비종료 작업의 자동 복구를 보장하지 않음 |
| Load | live Vertex용 `creativeops_gcp_load.js` 존재 | 외부 호출을 구조적으로 막는 mock 전용 profile 없음 |
| Alert | GCP Terraform에 5xx ratio/provider failure rule 존재 | 로컬 Prometheus rule과 Alertmanager firing/resolved drill 없음 |

### Worker recovery에 대한 확정된 제약

Celery task는 Postgres job을 `pending -> queued`로 commit한 뒤 handler를 실행한다.
재전달된 task는 `pending`이 아닌 `queued/generating` job을 `not_pending`으로 종료한다.
예외는 operation name이 저장된 Veo `polling` job이다. 따라서 late ack 설정만으로
T2I/T2V/I2V의 모든 중단 지점이 자동 복구된다고 주장할 수 없다.

Issue #88의 worker drill은 중단 지점별로 다음을 구분해야 한다.

1. publish 전 `pending`: outbox 재시도 또는 pending repair 대상
2. provider 작업 중 `queued/generating`: 현재 자동 복구 gap을 먼저 test로 고정하고,
   lease 또는 명시적 stale-job repair 없이는 성공으로 판정하지 않음
3. operation 저장 후 Veo `polling`: redelivery 또는 polling repair로 재개 가능
4. terminal state: duplicate delivery가 provider를 다시 호출하지 않아야 함

## 목표와 제외 범위

### 목표

- `AI_PROVIDER=mock`을 실행 전후에 검증하고 credential 없이 전체 drill을 수행한다.
- Prometheus, Grafana, Alertmanager를 로컬 컨테이너로만 실행한다.
- normal, delay, 429, 5xx, timeout, malformed response를 deterministic하게 재현한다.
- fault가 기존 retry/backoff, public error, job state, metric 경계를 통과하게 한다.
- baseline, stress, failure, recovery 결과를 동일한 schema의 artifact로 남긴다.
- alert와 worker recovery를 timeline과 DB source of truth로 검증한다.

### 제외 범위

- GCP/AWS/Kubernetes resource 생성, 변경, 재개
- 실제 Vertex/Gemini/Imagen/Veo 요청과 output quality 평가
- 기존 live k6 스크립트의 mock 겸용화
- Grafana 외부 plugin, SaaS exporter, 외부 notification channel
- prompt, request body, raw provider response, env 전체를 metric/log/artifact에 저장

## 제안 아키텍처

```text
k6 mock profiles ───────────────┐
smoke/recovery driver ──────────┼──> backend ──> Postgres
                               │       │
                               │       └──> /metrics <── Prometheus
                               │                         │       │
                               └──> Redis <── worker     │       └──> Alertmanager
                                           │             └──> Grafana
                                           └──> asset volume

/api/ops/health ──> evidence collector ──> redacted JSON/Markdown summary
docker compose ps ─> evidence collector ──> worker/container state
```

기본 application Compose는 유지하고 `docker-compose.observability.yml` override에서만
Prometheus, Grafana, Alertmanager를 추가한다. 외부 egress를 운영체제 수준에서 완전히
차단하는 작업은 이번 범위가 아니므로, 외부 호출 0건의 근거는 다음 세 조건을 함께
기록한다.

- selected env file의 `AI_PROVIDER=mock` 사전 검사
- `/api/health`의 `status=mock_provider`, `credentials=not_required` 확인
- Vertex override 미사용과 cloud command 미실행 기록

## 설계 결정

### 1. Observability Compose는 opt-in override로 분리

제안 파일:

- `docker-compose.observability.yml`
- `infra/local/observability/prometheus.yml`
- `infra/local/observability/rules/creativeops.yml`
- `infra/local/observability/alertmanager.yml`
- `infra/local/observability/grafana/provisioning/`
- `infra/local/observability/grafana/dashboards/creativeops-ops.json`

Prometheus는 Docker network 내부의 `backend:8000/metrics`만 scrape한다. Grafana와
Prometheus UI는 loopback에만 publish하고, named volume은 dashboard provisioning과
분리한다. Alertmanager는 receiver가 없는 로컬 sink로 시작하며, webhook/email/Slack
같은 외부 전송은 추가하지 않는다.

dashboard 최소 panel은 다음과 같다.

- throughput: `sum(rate(creativeops_http_requests_total[1m]))`
- error ratio: 5xx request rate / all request rate
- p50/p95/p99: cumulative duration bucket의 `histogram_quantile`
- provider failures: bounded `code`, `status`, `retryable` 합계
- scrape health: `up{job="creativeops-backend"}`

job/outbox/backlog은 현재 Prometheus series가 아니므로 dashboard에 존재한다고 가장하지
않는다. 첫 구현에서는 `/api/ops/health` snapshot을 정량표에 결합한다. dashboard에
필요하다는 검증 결과가 나오면 DB-backed gauge를 별도 결정으로 추가한다.

### 2. Fault control은 mock adapter 경계의 typed settings로 제한

prompt sentinel 확장은 채택하지 않는다. 사용자 prompt가 제어 채널이 되고 실제 입력과
fault 조건이 섞이기 때문이다. 대신 settings boundary에 다음 typed 값만 허용한다.

```text
MOCK_FAULT_TARGET=none|prompt|imagen|veo
MOCK_FAULT_KIND=normal|delay|rate_limited|transient_5xx|timeout|malformed_response
MOCK_FAULT_DELAY_MS=<bounded integer>
```

안전 규칙:

- 기본값은 `target=none`, `kind=normal`, `delay=0`이다.
- non-normal 값은 `AI_PROVIDER=mock`일 때만 허용하며 Vertex mode에서는 시작을 거부한다.
- `malformed_response`는 response schema가 있는 prompt target에서만 허용한다.
- delay는 상한을 두고, unit test는 injected sleeper로 실제 대기하지 않는다.
- profile은 prompt, job parameter, DB error detail, metric label에 기록하지 않는다.
- 기존 `[[mock-fail:imagen]]`은 regression fixture로만 유지하고 신규 운영 drill의
  제어면으로 사용하지 않는다.

fault injector는 provider service 전체에 퍼뜨리지 않고 mock implementation의 한
경계에 둔다. fault는 기존 typed provider error 또는 기존 response parser로 전달해
production retry/error path를 그대로 지난다.

| Fault | Provider-level 결과 | Retry 기대 | HTTP/public 결과 | Metric 기대 |
|---|---|---|---|---|
| normal | deterministic success | 없음 | 2xx | failure 증가 없음 |
| delay | bounded delayed success | 없음 | 2xx, latency 증가 | duration 증가 |
| rate_limited | `VertexRateLimitedError(429)` | 설정된 횟수까지 | retry 소진 시 503, `vertex_rate_limited` | code/status/retryable 증가 |
| transient_5xx | `VertexTransientError(503)` | 설정된 횟수까지 | retry 소진 시 503, `vertex_transient_error` | code/status/retryable 증가 |
| timeout | retryable transient timeout | 설정된 횟수까지 | retry 소진 시 503 | transient failure와 latency 증가 |
| malformed_response | invalid prompt response fixture | contract repair 경계 적용 | 최종 실패 시 502, `prompt_enhancement_invalid_response` | non-retryable failure 증가 |

generation handler도 prompt API와 동일한 bounded provider-failure recorder를 호출하도록
경계를 정리하되, 중복 count는 test로 막는다.

### 3. Mock load script는 live-provider script와 분리

`scripts/k6/creativeops_mock_ops.js`를 새로 두고 `AI_PROVIDER=mock` health guard가
통과하지 않으면 요청 전에 종료한다. 기존 `creativeops_gcp_load.js`는 Vertex 비용
guard를 가진 historical live script이므로 수정하지 않는다.

| Profile | 목적 | 요청 경로 | 판정 지표 |
|---|---|---|---|
| baseline | 정상 기준선 | health, prompt enhance, generation/read | throughput, p50/p95/p99, failure rate |
| stress | local saturation 신호 | bounded arrival-rate generation/read | dropped iterations, latency, backlog |
| failure | 429/5xx/timeout/malformed | fault target별 단일 profile | public error, retry, counter, alert |
| recovery | fault 해제 후 정상화 | baseline과 동일 | error 감소, alert resolved, backlog 안정 |

threshold 숫자는 첫 baseline 측정 전에 성공 기준으로 고정하지 않는다. machine-dependent
latency를 포트폴리오 SLO처럼 표현하지 않기 위해 첫 clean run을 baseline으로 기록하고,
stress는 resource saturation을 관찰할 만큼만 단계적으로 높인다. 모든 profile은 요청
수와 duration 상한을 갖는다.

### 4. Alert는 최소 traffic과 복구 조건을 포함

GCP rule의 의미를 로컬 Prometheus rule로 옮긴다.

- `CreativeOpsApiHigh5xxRate`: 5분 5xx ratio가 threshold 초과 **그리고** 최소 요청 수
  이상일 때만 firing
- `CreativeOpsProviderFailures`: 5분 provider failure 증가량이 threshold 이상일 때 firing
- 선택적 `CreativeOpsBackendScrapeDown`: backend scrape가 bounded duration 동안 down

unit test나 rule validation에서 zero denominator, low traffic false positive, bounded
labels를 확인한다. drill은 `inactive -> pending -> firing -> resolved`의 timestamp와
관련 metric snapshot을 기록한다.

### 5. Worker recovery는 test로 gap을 잠근 뒤 구현 범위를 결정

첫 failing integration test는 worker가 provider delay 중 강제 종료된 뒤 job이
`queued/generating`에 남고 redelivery가 `not_pending`이 되는 현재 동작을 증명한다.
그 다음 아래 둘 중 하나만 선택한다.

1. lease 기반 자동 회수: worker claim token/heartbeat/expiry를 DB에 저장하고 만료된
   nonterminal job만 원자적으로 재claim
2. 명시적 stale-job repair: age threshold, dry-run, 상태 전이, operator reason을 가진
   안전한 CLI로 복구

단순히 `queued/generating`을 재실행 가능 상태로 넓히는 변경은 중복 provider 호출을
막을 수 없으므로 채택하지 않는다. Issue #88에서는 mock에서 job 유실/중복 여부를
증명할 수 있는 가장 작은 방식을 고르고, Vertex의 exactly-once를 주장하지 않는다.

## 구현 순서와 test gate

1. settings validation과 mock fault unit test를 먼저 작성한다.
2. prompt/Imagen/Veo mock fault adapter와 provider failure metric contract를 구현한다.
3. observability override, Prometheus rule, Grafana provisioning을 static validation한다.
4. mock-only k6와 evidence collector를 구현한다.
5. worker interruption failing scenario를 고정하고 recovery boundary를 구현한다.
6. clean Compose에서 baseline, stress, failure, recovery를 순서대로 실행한다.
7. teardown 후 동일 명령을 한 번 더 실행해 재현성과 cleanup을 확인한다.

## 검증 및 artifact 계약

### 실행 전 guard

```powershell
docker compose --env-file .env.example config --quiet
docker compose -f docker-compose.yml -f docker-compose.observability.yml `
  --env-file .env.example config --quiet
```

driver는 `.env`를 거부하고 `.env.example` 또는 명시적 non-secret env file만 허용한다.
실제 실행 명령은 구현 후 `docs/runbooks/local-mock-operations.md`에 고정한다.

### 보존할 artifact

제안 경로는 `artifacts/issue-88/<run-id>/`이며 raw runtime output은 기본적으로 Git ignore
대상이다. 포트폴리오에는 redacted summary와 필요한 screenshot만 선별 커밋한다.

- `environment.json`: revision, clean/dirty, mock health, Compose service/image 정보
- `metrics-before.json`, `metrics-during.json`, `metrics-after.json`
- `ops-before.json`, `ops-during.json`, `ops-after.json`
- `k6-<profile>-summary.json`
- `alerts-timeline.json`
- `worker-recovery-timeline.json`
- `report.md`

모든 artifact는 prompt, request body, raw error body, credential, env dump, 개인 PC absolute
path, account/project identifier를 금지한다. job ID는 correlation에 필요할 때 run-local
alias로 치환한다.

### 정량 결과 표

구현 후 이 문서에 실제 값을 채운다.

| Metric | Baseline | Stress | Failure | Recovery |
|---|---:|---:|---:|---:|
| Throughput | 미측정 | 미측정 | 미측정 | 미측정 |
| p50 / p95 / p99 | 미측정 | 미측정 | 미측정 | 미측정 |
| HTTP failure rate | 미측정 | 미측정 | 미측정 | 미측정 |
| Dropped iterations | 미측정 | 미측정 | 미측정 | 미측정 |
| Active job / outbox pending | 미측정 | 미측정 | 미측정 | 미측정 |
| Provider failure count | 미측정 | 미측정 | 미측정 | 미측정 |
| 외부 provider/cloud 요청 | 0 목표 | 0 목표 | 0 목표 | 0 목표 |

## Rollback과 cleanup

- fault 비활성화: 모든 `MOCK_FAULT_*`를 기본값으로 되돌리고 backend/worker를 recreate한다.
- observability 비활성화: override 없이 기본 Compose를 실행한다.
- local stack 정리: observability override를 포함해 `docker compose down`을 실행한다.
- volume 삭제는 별도 opt-in 명령으로만 제공하고, 실행 전 대상 volume을 표시한다.
- code rollback은 mock fault adapter와 observability override를 제거해도 기본 mock/live
  provider boundary가 유지되도록 additive하게 구성한다.

## 남은 위험과 다음 단계

- process-local runtime counter는 backend restart 시 초기화된다. alert drill 중 restart를
  포함하면 counter reset을 timeline에 명시해야 한다.
- `/api/ops/health`의 DB snapshot은 Prometheus time series가 아니다. 첫 증거 수집에는
  충분하지만 장기 dashboard 요구가 생기면 exporter/gauge 설계가 필요하다.
- local Docker 성능은 cloud capacity나 HPA 성능을 대변하지 않는다.
- mock timeout과 malformed fixture는 실제 SDK/network failure의 확률 분포를 재현하지
  않는다. retry/error contract 검증만 의미한다.
- worker crash recovery는 duplicate provider charge를 포함한 live exactly-once 보장이
  아니다. 실제 provider operation idempotency는 후속 live-safe 설계가 필요하다.

다음 구현 단계는 fault settings/adapter의 failing tests와 observability Compose static
validation을 먼저 추가하는 것이다. 실제 Compose drill 결과가 생긴 뒤에만 이 문서의
정량표와 evidence level을 갱신한다.
