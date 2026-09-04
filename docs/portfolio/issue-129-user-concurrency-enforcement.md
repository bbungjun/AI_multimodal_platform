# Issue #129 — Atomic per-User concurrency enforcement

## 배경과 문제

Prompt Enhancement와 Imagen/Veo 생성은 이미 실행 전에 Credit을 예약했지만,
Plan의 `max_concurrent_requests`는 실제 admission에 적용되지 않았다. 한 사용자의
burst가 worker/provider 진입점을 독점할 수 있었고 Free/Pro/Max의 1/3/5 계약도
운영적으로 강제되지 않았다.

## 기대 동작과 실제 동작

| 구분 | 내용 |
|---|---|
| 기대 동작 | 동일 사용자의 top-level 요청을 Free1/Pro3/Max5로 원자적으로 제한하고 Master도 5를 적용한다. |
| 실제 동작(변경 전) | Credit 잔액만 충분하면 같은 사용자가 Plan 한도를 넘어 held Reservation을 만들 수 있었다. |
| 영향 | 한 사용자의 burst가 제한된 worker/provider 용량을 점유하고 Plan 계약과 실제 동작이 달라질 수 있었다. |

## 관측과 원인 분석

- G5~G7의 공통 admission seam은 `credit_accounting.reserve`였지만 PlanPolicy의
  동시 요청 수는 조회만 되고 enforcement에는 사용되지 않았다.
- Job 상태나 Redis를 별도 counter로 사용하면 Credit Reservation과 서로 다른
  lifecycle이 생겨 crash와 replay에서 drift가 발생한다.
- initial RED는 accounting, prompt mapping/API, generation API 네 경계에서
  동시성 거절이 없거나 503/409로 노출되는 것을 재현했다.
- 첫 inherited accounting proof는 과거 balance-first 기대 때문에 실패했다.
  새 계약의 concurrency-before-allocation 우선순위로 fixture 기대값을 수정했다.
- 첫 ownership proof는 ownership-only admission이 사용자당 다섯 held writer를
  유지하면서 Free fixture를 사용해 실패했다. 공개 plan lifecycle로 해당 actor를
  Max로 설정해 실제 5-slot 한도 안에서 원래 ownership/lineage 검증을 보존했다.
- Redis semaphore, process-local lock, Job counter, 신규 lease table은
  Credit terminal transaction과 원자적으로 맞물리지 않아 No-Go로 결정했다.

## 해결 방법과 판단 근거

- held `CreditReservation` 하나를 top-level slot 하나로 정의했다.
- 기존 User row lock 아래에서 replay를 먼저 판정하고, Plan permission 다음에
  held count를 검사한 뒤 Credit을 할당한다.
- `settle`/`release`가 기존 terminal transaction에서 Reservation을 terminal로
  바꾸므로 별도 slot 반환 API나 cleanup write가 필요 없다.
- Prompt, standalone generation, retry와 pipeline이 같은 accounting Interface를
  사용한다. Pipeline은 parent Reservation 하나만 가져 slot도 하나다.
- 고정 코드 `user_concurrency_limit`를 공개 HTTP429로 변환하고 active count나
  타 사용자 상태는 응답하지 않는다.
- abandoned held Reservation은 자동 해제하지 않고 fail closed로 남겼다. 시간 기반
  복구에는 provider 상태와 운영자 정책이 필요하므로 별도 후속 범위다.
- rollback은 이 변경 커밋을 되돌리는 것으로 가능하며 migration이 없어 schema
  rollback이나 개발 DB 초기화가 필요 없다.

## 검증

### 환경과 전제조건

- Code revision: `4e8132a`
- Schema head: `0006_credit_accounting_persistence` (migration 0)
- Provider mode: `AI_PROVIDER=mock`
- Runtime: 격리 Docker Compose/PostgreSQL과 tracked-only Python 3.11 Linux
- 실제 OAuth, Vertex, cloud, GCP/Kubernetes/Terraform 및 유료 요청: 실행하지 않음

### 명령과 결과

| 명령 또는 시나리오 | 실제 결과 | 판정 |
|---|---|---|
| `python scripts/verify_concurrency.py --env-file .env.example` 2회 | 각 8 groups, 6 races, 259 checks, cleanup 0 | PASS |
| 같은 User 50개 admission burst | Free1/Pro3/Max5/Master5, 초과 성공 0 | PASS |
| full-limit replay와 terminal/admission | replay는 새 slot 0, settle/release 후 재입장, 미커밋 terminal은 fail closed | PASS |
| 제품 caller 차단 | Prompt/generation/retry/pipeline HTTP429, provider/enqueue 0 | PASS |
| accounting/lifecycle/prompt-credit/generation-credit/auth | 각 독립 verifier 1회 | PASS |
| `verify_ownership.py --suite all --cycles 2` | ownership 2 + file-ops 2 = 4 cycles, cleanup 0 | PASS |
| tracked-only Linux backend | 1506 passed, 3 guarded skips | PASS |
| native Windows backend | 1505 passed, 3 skips; 기존 Bash 절대경로 예외 1건 재현 | PASS with known platform exception |
| Compose, frontend | config/lint/build, Session48, Chromium34 | PASS |

두 최종 concurrency receipt는 같은 revision `4e8132a`에서 각각 21.109초와
21.891초에 완료됐고 cleanup은 2.703초와 2.765초였다. 긴 원본 로그나 개인 식별자,
prompt/provider payload는 커밋하지 않았다.

### 정량 결과

| Metric | 변경 전 | 변경 후 |
|---|---:|---:|
| Plan별 허용 held slot | 미강제 | Free1 / Pro3 / Max5 / Master5 |
| 동일 User 동시 시도 | 제한 보증 없음 | Plan별 50개 이상, 한도 초과 성공 0 |
| 검증 race | 전용 proof 없음 | cycle당 6 |
| 검증 checks | 전용 proof 없음 | cycle당 259 |
| 격리 자원 잔존 | 해당 없음 | container/volume/network 0 |
| 외부 provider 호출/비용 | 0 | 0 (`mock`) |

p95/p99와 실제 provider throughput은 mock PostgreSQL admission proof로 의미 있게
측정할 수 없어 live 성능 수치로 제시하지 않는다.

## 결과와 영향

- 모든 현재 생성 진입점이 하나의 durable accounting seam에서 사용자별 동시성
  정책을 적용한다.
- replay, Credit, terminal 처리와 동시성 사이에 두 번째 상태 저장소가 생기지 않아
  운영자가 조정해야 할 drift 지점을 줄였다.
- 공개 오류는 안전한 429 코드로 고정되고, 거절 시 provider 호출과 새 영속 row가 0이다.
- Evidence level: **Mock Verified**. 실제 Vertex 처리량, cloud quota 또는 GCP 과금
  검증이 아니다.

## Evidence Artifacts

- 계약: `docs/initiatives/g8-user-concurrency-enforcement-spec.md`
- 구현 seam: `backend/app/credit_accounting.py`
- 격리 proof: `backend/tests/concurrency_support.py`, `scripts/verify_concurrency.py`
- 재현 절차: `docs/testing.md`, `docs/runbooks/local-mock.md`

## 남은 위험과 다음 단계

- 프로세스가 terminal 처리를 영구히 잃으면 held Reservation이 slot을 계속 점유한다.
  자동 sweeper는 expiry/provider reconciliation/operator audit 정책과 함께 별도 설계한다.
- PostgreSQL User row lock은 correctness를 보증하지만 실제 cloud latency와 hot-user
  contention은 측정하지 않았다.
- G9 Plan/Usage UI와 G10 Master/Audit는 아직 구현하지 않았다.
- 실제 Vertex 용량과 quota에 대한 검증은 사용자 승인과 비용 상한이 있는 별도 QA다.
