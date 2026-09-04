# Issue #120 Credit accounting persistence record

Status: `Planned / Goal Prepared`, 2026-09-04. Parent
[#117](https://github.com/bbungjun/AI_multimodal_platform/issues/117); successor
[#121](https://github.com/bbungjun/AI_multimodal_platform/issues/121); aggregate
[spec](../initiatives/g5-credit-accounting-spec.md).

## 배경과 문제

G5A/B로 사용자별 30일 credit grant와 변경 이력은 생겼지만, 생성 요청이 provider를
호출하기 전에 credit을 보류하고 이후 실제 사용량과 결과에 따라 소비 또는 반환할
영속 구조는 없다. 이 상태에서 바로 생성 코드에 차감 로직을 넣으면 중복 worker 전달,
부분 성공, 늦은 완료와 트랜잭션 rollback 때 잔액과 사용량이 서로 달라질 수 있다.

## 기대 동작과 실제 동작

| 구분 | 내용 |
|---|---|
| 기대 동작 | 예약 quote, 원 grant 배분, 원본 Usage, 단 한 번의 terminal 결과를 소유자와 rate version에 묶어 저장한다. |
| 실제 동작 | G5B head에는 account/cycle/grant/lifecycle operation/ledger만 있고 Reservation/Allocation/Usage 테이블과 writer가 없다. |
| 영향 | 월 credit 소진 거절, 중복 차감 방지, 부분 결과 과금과 무결한 사용량 분석을 아직 제품 기능으로 주장할 수 없다. |

## 관측과 원인 분석

- 재현 조건: merged G5B head `ffc4b506`의 model/migration/verifier 경로를 정적으로
  조사했다. 실제 DB 또는 provider는 실행하지 않았다.
- 확인한 state: 새 Alembic head를 도입하면 15개 기존 proof/harness 경로가 현재
  `0005_credit_lifecycle_operations`를 명시적으로 참조한다.
- 확정한 원인: 새 회계 모듈과 runtime proof를 같은 Goal에 합치면 최소 22개 코드
  경로가 필요해 Initiative의 20-path 상한을 넘는다.
- No-Go 판단: 단일 G5C Goal, 기존 verifier 일부를 stale head에 남기는 방법, Job
  linkage를 미리 추가하는 방법은 모두 거절했다.

## 해결 방법과 판단 근거

- 선택한 변경: G5C를 C1 persistence/head compatibility와 C2 accounting Module/race
  proof로 나눴다. C1은 정확히 20개 경로와 migration 1개, C2는 migration 0개다.
- 설계: reservation header/item, original grant allocation, append-only Usage의 네
  테이블과 소유권 FK, terminal transition, downgrade data guard를 먼저 고정한다.
- trade-off: 기능 완성까지 PR이 하나 늘지만 schema rollback과 동시성 로직의 실패
  원인을 분리하고 각 Goal을 sol/medium context에서 검토할 수 있다.
- 안전장치: mock-only, 개발/preview DB 보존, 기존 migration 불변, 새 테이블이 하나라도
  차 있으면 downgrade 거절, 21번째 경로 또는 두 번째 migration이면 즉시 재설계한다.
- rollback: 네 테이블이 모두 비었을 때만 0005로 downgrade한다. 데이터가 있으면
  삭제하지 않고 reviewed forward fix를 사용한다.

## 검증

### 준비 단계 환경과 결과

| 항목 | 결과 | 판정 |
|---|---|---|
| Base | merged G5B `ffc4b506466662f3e57e0f8dca72e16955273749` | 확인 |
| Provider | `AI_PROVIDER=mock` 설계만 수행; 실제 호출 없음 | 확인 |
| Path estimate | 단일 Goal 최소22, C1 exact20 | split 필요 |
| Migration | C1 exactly1 / C2 zero | 고정 |
| 준비 B0 | 관련 backend 538 PASS / 2.79s | 기준선 통과 |
| DB/runtime | 준비 중 실행·초기화 없음 | 미검증을 성공으로 표시하지 않음 |

실행 단계는 frozen Goal의 focused tests, schema/accounting proof 2회, lifecycle/auth,
ownership all2, 전체 backend/frontend와 final-head CI를 통과해야 한다. 결과 수치와
실패 기록은 구현 후 이 문서를 갱신한다.

## 결과와 영향

- 사용자 변화: 아직 없음. 이번 산출물은 구현 전에 회계 의미와 실패 정책을 고정한다.
- 운영 변화: 동일한 usage라도 내부 credit과 원본 단위를 분리해 보존하는 schema 및
  검증 계약이 준비됐다.
- 포트폴리오 가치: 요구사항을 financial invariant, schema migration, concurrency
  boundary와 운영 검증으로 바꾸고, context/path risk를 근거로 delivery slice를 나눈
  FDE/AI Platform 설계 사례다.
- Evidence level: `Planned / Goal Prepared`; `Implemented` 또는 `Mock Verified` 아님.

## Evidence Artifacts

- Aggregate design: `docs/initiatives/g5-credit-accounting-spec.md`
- Execution plan: `.omo/plans/issue-120-g5c1-credit-accounting-persistence-goal.md`
- Frozen SHA-256: `d55cad9eba3013706dfd6554894c78af40ef927ed8c03352fbca062c3463f8cc`
- GitHub: Issue120 and parent117
- Runtime evidence: 실행 전이므로 없음

## 남은 위험과 다음 단계

- C1은 table contract만 구현하며 reserve/settle/release를 제공하지 않는다.
- C2는 C1 실제 merge 후 경로와 Goal을 별도로 동결해야 한다.
- abandoned hold reconciliation, Job/Outbox/terminal-state 결합, pipeline child 방지,
  per-user concurrency, UI/Master/Audit와 실제 provider는 후속 Goal이다.
- Goal 실행 전 계획 SHA와 branch/base가 일치하지 않으면 중단한다.
