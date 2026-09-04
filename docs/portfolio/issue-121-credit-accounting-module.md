# Issue #121 Atomic credit accounting Module preparation

Status: `Planned / Goal Prepared`, 2026-09-04. Parent
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
- Baseline: merged PR122 squash `68e3df6`, related tests 219 PASS / 1.78s.
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

실행 중 실패한 접근, 실제 counts/time, rollback과 결과는 같은 문서에 추가한다.
준비 단계는 Docker/DB/provider를 실행하지 않았으며 implementation 증거가 아니다.

Frozen Goal: `.omo/plans/issue-121-g5c2-credit-accounting-module-goal.md`
SHA-256: `e3937a938d719a55d83a906f2f796171aaeec40ed9caddd8d6f50952487c6579`
