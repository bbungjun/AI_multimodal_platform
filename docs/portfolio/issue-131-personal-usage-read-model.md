# Issue #131 — Personal Plan and Usage Read Model

Evidence level: **Mock Verified locally**

Implementation revision: `d103a44`

Schema: `0006_credit_accounting_persistence` (migration 0)

## 배경과 문제

G5–G8은 사용자별 Plan, 정확한 30일 cycle, grant/Reservation, 원본 Usage와
동시 요청 slot을 PostgreSQL에 기록한다. 그러나 인증된 사용자가 자신의 현재
상태를 조회할 Interface가 없었다. frontend가 여러 accounting table을 직접
조합하면 갱신 경계, bonus/hold 계산, meter 단위와 개인정보 정책이 UI caller마다
복제되고 서로 다른 snapshot을 보여줄 위험이 있었다.

목표는 사용자 선택자 없이 현재 actor 한 명의 Plan, cycle, Credit, concurrency,
Usage를 한 번에 반환하는 안정적인 backend seam을 만드는 것이었다. G9B UI와
Master 전체 조회는 이 Issue에 포함하지 않았다.

## 관측과 원인 분석

- 이미 필요한 source row는 존재했지만 일관된 read transaction과 응답 계약이
  없었다.
- cycle 갱신은 단순 SELECT가 아니다. 가입 시각부터 정확히 30일이 지난 경계에서
  기존 lifecycle이 새 cycle과 base grant를 지연 생성할 수 있다.
- available Credit은 base 하나가 아니라 아직 유효한 모든 grant의
  `granted-reserved-consumed-expired` 합이다. held는 grant projection과 held
  Reservation 합이 일치해야 한다.
- 현재 Usage persistence는 모든 record에 정확한 provider model을 보존하지 않는다.
  다른 Job metadata나 operation key에서 추론하면 그럴듯하지만 거짓인 집계를 만들 수
  있다. 신뢰 가능한 dimension은 versioned billing meter였다.
- reserve/settle/release/lifecycle writer는 User row를 먼저 잠근다. read도 같은 순서를
  사용하지 않으면 cycle, hold와 Usage가 서로 다른 시점의 조합이 될 수 있다.

## 검토했지만 선택하지 않은 접근

- **frontend 직접 join:** accounting 규칙과 privacy 정책이 UI에 누출되고 재사용성이
  떨어져 제외했다.
- **정확한 model 추론:** 현재 source of truth가 아니므로 제외하고 일곱 billing meter를
  고정했다.
- **Redis/cache/별도 read table:** schema와 invalidation 문제를 추가하며 현재 규모의
  correctness 문제를 해결하지 않아 제외했다.
- **잠금 없는 여러 SELECT:** 빠르지만 renewal/terminal 경합에서 mixed snapshot을 만들
  수 있어 제외했다.
- **읽기 후 무조건 rollback:** 신규 User나 renewal의 결정적 lifecycle materialization을
  버리므로 caller-owned outer transaction에서 성공 commit을 선택했다.

## 해결 방법과 판단 근거

`read_personal_usage(session, *, user_id, now)` 하나를 외부 Interface로 갖는 deep
Module을 추가했다. caller가 active transaction과 aware timestamp를 제공하고 Module은
engine/clock/commit/provider를 소유하지 않는다. 기존 `ensure_cycle`을 먼저 호출해 User
lock과 exact-30-day policy를 재사용한 뒤 같은 transaction 안에서 grant, held
Reservation과 현재 cycle Usage를 결정적으로 읽는다.

응답은 현재 Plan/pending Plan/rate version, cycle index/start/renewal/allowance/charge,
available/held microcredit, active request/limit, 일곱 meter의 원본 observed units와
charged microcredit만 포함한다. 모든 계산은 integer이며 negative, signed-BIGINT overflow,
unknown meter/version, projection drift와 plan-limit 초과를 `usage_unavailable`로 fail
closed한다. PostgreSQL contention 계열만 `usage_busy`로 구분한다.

HTTP adapter는 `require_user`의 actor ID만 사용하고 query/body/User selector 또는
`scope=all`을 제공하지 않는다. 성공은 lifecycle materialization까지 commit하고 mapped
및 unhandled failure는 outer transaction에서 rollback한다. `/api/usage` 성공, 오류,
redirect와 HEAD 응답은 모두 `Cache-Control: private, no-store`다.

Rollback은 migration 없이 구현 커밋을 되돌리면 된다. accounting row를 자동 수리하거나
개발/preview DB를 초기화하는 rollback 절차는 허용하지 않았다.

## 검증

전제조건은 로컬 Docker, `AI_PROVIDER=mock`, 새 격리 PostgreSQL과 schema head0006이다.
실제 OAuth, Vertex/provider/cloud, GCP/Kubernetes/Terraform 및 유료 호출은 실행하지 않았다.

| 검증 | 결과 |
|---|---|
| personal usage PostgreSQL 2 cycles | 동일 SHA, 각 8 groups / 3 races / 451 checks / cleanup 0 |
| cycle1 work / cleanup | 38.500s / 2.750s |
| cycle2 work / cleanup | 15.984s / 2.859s |
| lifecycle / accounting / concurrency | 320 checks·8 races / 299·8 / 259·6, 모두 cleanup 0 |
| prompt-credit / generation-credit | 35 checks·1 race / 120·2, 모두 cleanup 0 |
| auth PostgreSQL/Redis | signup/session/touch/flow와 outage recovery PASS, cleanup 0 |
| ownership all2 | ownership2 + file-ops2 = 4 cycles, 592.078s, cleanup 0 |
| tracked-only Linux backend | 1558 passed / 3 guarded skipped, test 5.34s |
| native Windows backend | 1557 passed / 3 skipped; 기존 Bash 절대경로 예외 1건 재현 |
| Compose/frontend | config, lint, build, Session48, Chromium34 PASS |

처음 Compose 검증을 frontend working directory에서 실행해 root `.env.example`을 찾지
못했다. 이는 제품 실패가 아니라 검증 명령의 cwd 오류였고, repository root에서 같은
명령을 재실행해 통과했다. 시간 제한이나 수용 기준은 완화하지 않았다.

## 결과와 영향

- G9B는 persistence table이나 갱신 정책을 알지 않고 단일 owner-scoped 응답만 소비할
  수 있다.
- exact 30-day renewal, bonus, hold, terminal과 Usage가 User-first transaction 하나의
  snapshot으로 정렬된다.
- fixed seven-meter zero shape 덕분에 신규 User도 UI missing-row 분기 없이 표시할 수
  있다.
- 다른 User 존재 여부, 내부 ID, account operation, prompt/Job/Asset/session/provider
  payload는 응답과 evidence에 포함하지 않는다.
- 변경은 10개 non-document 경로, migration 0으로 승인된 11-path 경계 안에 머물렀다.

## 남은 위험과 다음 단계

- G9B frontend 표시, responsive/loading/empty/error UX와 browser proof는 아직 미구현이다.
- 정확한 provider model별 Usage는 persistence가 모든 record에서 이를 보존하기 전까지
  제공하지 않는다.
- 실제 Google browser session, Vertex/cloud 처리량, quota와 외부 provider billing은
  검증하지 않았다.
- abandoned held Reservation 복구/sweeper는 별도 운영 범위다. read가 임의로 hold를
  해제하지 않는다.
- [Ready PR132](https://github.com/bbungjun/AI_multimodal_platform/pull/132)의 최종
  verify 및 backend/frontend Scan/SBOM과 실제 squash merge가 delivery 종료 조건으로
  남아 있다.
