# Issue #121 Atomic credit accounting Module

Status: `Locally Mock Verified / Delivery Pending`, 2026-09-04. Parent
[#117](https://github.com/bbungjun/AI_multimodal_platform/issues/117); G5 parent
[#114](https://github.com/bbungjun/AI_multimodal_platform/issues/114); predecessor
[#120](https://github.com/bbungjun/AI_multimodal_platform/issues/120) merged by
[PR122](https://github.com/bbungjun/AI_multimodal_platform/pull/122).

## 배경과 문제

G5C1은 reservation/item/allocation/Usage 스키마와 DB guard를 만들었지만 이를
안전하게 쓰는 기능은 없다. caller가 직접 grant 잔액을 계산하거나 ledger/projection을
수정하면 중복 queue 전달, partial 결과, late completion과 renewal 경합에서 overspend나
이중 terminal이 발생할 수 있다. 아직 월 credit 소진 거절이나 실제 차감을 제품 기능으로
주장할 수 없다.

## 관측과 설계 판단

- merged C1과 G5B 구현을 조사한 결과 migration/model 변경 없이 새 accounting Module로
  동작을 닫을 수 있다. 기존 public `ensure_cycle`은 renewal/expiry와 lock prefix를 제공한다.
- 외부 Interface는 `reserve`, `settle`, `release`와 immutable value objects뿐이다.
  allocation priority, grant/ledger shape, replay comparison, lock와 projection reconstruction은
  Implementation에 숨겨 caller의 학습 비용과 오류 가능성을 줄인다.
- reserve replay는 renewal보다 먼저 User lock 아래 확인한다. 동일 요청 재시도가 cycle을
  갱신하거나 credit을 만료시키는 side effect를 만들면 안 되기 때문이다.
- 새 reserve는 public lifecycle Interface를 조합한 후 grant를 UUID 순서로 refresh-lock하고,
  expiring-first priority는 잠금 순서와 분리해 계산한다.
- terminal은 User→Account→latest Cycle→grant UUID→Reservation→item meter→allocation ordinal
  순서를 고정한다. 이를 통해 settle/release와 renewal/expiry가 하나의 직렬화 규칙을 따른다.
- unit fake만으로 PostgreSQL lock/FK/unique semantics를 주장하지 않는다. fixed proof를
  별도 verifier로 두고 두 독립 cycle에서 여덟 race의 실제 blocking을 관측한다.

## 범위와 검증 계획

- Exact code paths: 6; migration: 0.
- Baseline: merged PR122 squash `68e3df6`, fresh related tests 219 PASS / 1.41s.
- Authority: Goal SHA matched; branch/base/three open Issues, local Docker context,
  mock-only execution, zero migration diff and preserved preview resources confirmed.
- Runtime: accounting verifier 2회, schema1, lifecycle1, auth1, ownership/file all2,
  Linux backend, Windows known-exception reproduction, Compose and unchanged frontend.
- Accounting receipt: groups8, races8, checks>=160, current head0006, same committed SHA,
  exact project container/volume/network cleanup0.
- Delivery: Ready PR, final-head verify and both Scan/SBOM, protected squash actual merge;
  then Issues121/117/114 closure with tested-tree evidence.

## 제외와 남은 위험

Job, Prompt Enhancement, Asset, Outbox, worker, state machine, frontend, OAuth,
provider/cloud, Plan/Master/Audit, payment and per-user concurrent-request admission은
변경하지 않는다. G5C2 성공은 accounting Module의 Mock Verified이며 generation billing은
G6/G7 뒤에야 완성된다. abandoned hold reconciliation도 별도 운영 Goal이다.

## 구현과 해결

- 하나의 deep Module이 caller-owned transaction 안에서 nested savepoint를 사용한다.
  caller는 grant/ledger/lock를 알지 않고 세 operation과 immutable receipt만 사용한다.
- reserve는 User lock 아래 committed replay를 renewal보다 먼저 확인하고, public
  `ensure_cycle` 조합 뒤 UUID lock 순서와 expiring-first allocation 우선순위를 분리한다.
  정책 quote, Plan admission, projection-ledger 재구성과 all-or-nothing hold를 한 원자적
  변경으로 묶었다.
- terminal 공통 구현은 settle/release를 한 번만 종료하고 stored rate version으로
  Usage를 계산한다. 실제 units/source는 별도로 저장하며, 만료 grant의 미사용 hold는
  available로 되돌리지 않고 expired projection으로 이동한다.
- replay, cross-owner/missing, overage, projection corruption, signed BIGINT overflow와
  PostgreSQL contention을 고정된 비식별 오류로 닫았다. provider 작업은 lock 안에서
  실행하지 않는다.

## 관측한 실패와 원인

1. unit RED에서 overage 오류가 `ValueError` 호환 catch에 다시 잡혀 account-inconsistent로
   축약됐다. accounting 오류를 먼저 재전파해 `credit_usage_exceeds_reservation`을 보존했다.
2. 수동 F2 검토에서 retry의 `now`가 payload가 아닌데도 renewal 뒤 clock 검사에 막힐 수
   있음을 발견했다. reserve/terminal committed replay를 temporal new-command 검사보다
   앞으로 옮기고 unit/실제 DB proof를 추가했다.
3. 첫 새-SHA C1은 settlement proof에서 실패했다. harness가 END renewal 뒤 새 hold를 과거
   T로 만들어 정상 clock-regression을 유발한 것이 원인이었다. 새 hold 검증을 renewal
   전으로 옮기고, renewal 뒤에는 replay만 검증했다. 실패 project도 cleanup0이었다.
4. 최종 ownership proof는 http-races와 metadata에서 각각 일시적 `harness_failure`가
   발생했다. 둘 다 timeout 전 종료되고 exact cleanup0임을 확인했다. 설정/시간을 완화하지
   않고 전체 all/2를 fresh 실행해981.390s에 complete4를 얻었다. 실패도 성공으로 숨기지 않는다.
5. production 코드가 테스트 fake의 `session.new`를 감지하던 얕은 seam을 F1에서 제거했다.
   생성한 Usage tuple을 같은 구현 경로로 receipt에 전달해 실제 DB와 fake의 분기를 없앴다.

## 최종 검증과 결과

- Final local code: `41b1bf3`; exact6 code paths, migration0, forbidden product/frontend
  경로 변경0. M43, P39, H301 PASS.
- Accounting C1/C2: 각 groups8/races8/checks299, work35.172/14.829s,
  cleanup2.656/2.687s, exact resources0.
- Schema: accounting42/downgrade4, credit90/races3, stale/reset guards;
  work160.922s/cleanup1.875s. Lifecycle groups8/races8/checks320;
  work15.141s/cleanup2.641s. Auth Postgres/Redis/outage recovery와 auth50 p95
  6.906ms PASS.
- Ownership `--suite all --cycles 2`: complete4/981.390s. Ownership cycles each
  metadata348/delete-race2; file-ops cycles each FOVE310/two actors ten stages.
  모든 owned project의 container/volume/network가0이다.
- Linux tracked-only backend1429 PASS/3 guarded skips. Windows1428 PASS/3 skips와
  기존 Bash path native127 한 건만 발생했고 untouched base68e3df6에서 동일 재현했다.
  Compose config, frontend lint/build, Session48, Chromium34 PASS.

F1 scope/architecture, F2 data/security, F3 verification/operations는 APPROVE다.
Ready PR final-head CI와 actual protected squash merge가 F4의 남은 조건이다.

## 영향, rollback과 남은 위험

내부 accounting 사용자는 이제 중복 전달과 동시 경합에서도 잔액 초과 없이 hold를 만들고,
deliverable만 실제 사용량으로 소비하며 no-deliverable은 전액 release할 수 있다. rollback은
현재 product caller가 없으므로 reviewed code revert가 우선이다. 이미 accounting data가 있는
DB는 강제 downgrade/drop하지 않고 forward fix한다.

아직 Job/Outbox/provider와 연결되지 않았고 abandoned hold reconciliation, per-user concurrent
request admission, 개인 Usage UI, Master/Audit도 없다. 따라서 이 결과는 Module의 local Mock
Verified이며 실제 생성 과금 완료가 아니다. 생성 연동은 G6/G7 범위다.

Frozen Goal: `.omo/plans/issue-121-g5c2-credit-accounting-module-goal.md`
SHA-256: `e3937a938d719a55d83a906f2f796171aaeec40ed9caddd8d6f50952487c6579`
