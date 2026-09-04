# Issue #120 Credit accounting persistence record

Status: `Mock Verified locally / delivery pending`, 2026-09-04. Parent
[#117](https://github.com/bbungjun/AI_multimodal_platform/issues/117); successor
[#121](https://github.com/bbungjun/AI_multimodal_platform/issues/121); aggregate
[spec](../initiatives/g5-credit-accounting-spec.md).

## 배경과 문제

G5A/B로 사용자별 30일 credit grant와 lifecycle command는 생겼지만, 생성 전에
quote를 보류하고 실제 사용량과 결과를 원 grant에 귀속할 영속 구조가 없었다. 곧바로
Job이나 worker에 차감 로직을 넣으면 중복 전달, 부분 성공, 늦은 완료와 rollback 때
잔액·사용량이 달라질 수 있다. 또한 새 head를 도입하려면 15개 기존 검증 경로가
`0005`에서 이동해야 해 writer까지 한 Goal에 넣을 경우 20-path 상한을 넘었다.

## 관측과 원인 분석

- 단일 G5C 구현은 최소 22개 코드 경로가 필요했다. C1 persistence/head compatibility와
  C2 accounting Module/race proof로 분리하고 C1을 정확히 20개 경로로 고정했다.
- 첫 실제 S1은 Alembic upgrade에서 실패했다. 승인된 revision ID가 34자인데 Alembic
  기본 `version_num`은 `VARCHAR(32)`여서 ID를 기록할 수 없었다.
- 다음 S1은 실제 FK/index가 존재해도 verifier inventory에 새 이름이 없어 실패했다.
- 이후 두 S1은 proof 자체의 결함을 드러냈다. 네 count를 await하지 않은 snapshot과,
  intended owner FK 전에 PK 또는 meter vocabulary가 거절하는 fixture였다.
- 실패 project 다섯 개는 모두 제한 시간 안에 중단됐고 각 exact project의 container,
  volume, network가 0임을 확인했다. 개발/preview DB와 volume은 사용하지 않았다.

## 해결 방법과 판단 근거

- migration `0006_credit_accounting_persistence` 하나로 reservation header/item,
  original grant allocation, append-only Usage 네 테이블을 추가했다.
- composite owner FK, positive BIGINT, finite meter/source/delivery/status, key/version/time
  shape, held-to-terminal 한 방향 전이와 child UPDATE/DELETE/TRUNCATE 거절을 DB에 둔다.
- 네 테이블 중 하나라도 차 있으면 downgrade는
  `credit_accounting_requires_empty_tables`로 거절하며 데이터와 head를 보존한다.
- revision 이름은 승인 계약이므로 줄이지 않았다. upgrade에서 Alembic control column만
  64자로 넓히고 downgrade 때 다시 줄이지 않아 34자 current value가 0005로 안전하게
  전환될 수 있게 했다.
- fixed stdin proof는 valid distinct key/meter를 사용해 정확한 FK를 관측하고, verifier는
  새 FK/index inventory와 stale0005 backend/worker/dispatcher 복구를 함께 검사한다.
- `app.credit_accounting`, reserve/settle/release writer, API, Job/Asset/Outbox/worker,
  frontend와 provider/cloud 변경은 의도적으로 제외했다.

## 검증

최종 local source SHA는 `b4ce32eb7f4dff7c15a9d726b4d2ec77d5e4e3ff`이다.

| Gate | 결과 |
|---|---|
| Scope | exact20 non-document paths; new migration0006 exactly1; migrations0001–0005 unchanged; writer scan clean |
| Focused | M31, P44, H431, B0 551 PASS |
| Schema S1 | `schema-verify-060a7279e7e9`; accounting42/downgrade4, credit90/races3, work164.015s, cleanup1.922s, resources0 |
| Schema S2 | `schema-verify-22cdaa7caec2`; same counts, work168.000s, cleanup1.922s, resources0 |
| G5B lifecycle | 8 groups, 8 races, 320 checks, work15.359s, cleanup2.844s, resources0 |
| Auth | local PostgreSQL/Redis/outage recovery PASS; authentication50, p95 7.547ms; resources0 |
| Ownership all2 | ownership cycles each access348/delete-race2; file cycles each F/O/V/E310, actors2/all10; verified_cycles4, aggregate1010.828s, resources0 |
| Linux backend | 1347 PASS, 3 guarded runtime skips, 4.63s |
| Windows backend | 1346 PASS, 3 skips, known Bash path native127 only, 11.64s; untouched base reproduced same single failure |
| UI/Compose | Compose config, frontend lint/build, Session48 and Chromium34 PASS |

실패 기록은 성공 결과로 덮지 않았다. 순서대로 revision column 길이, verifier inventory,
async snapshot, PK/vocabulary fixture를 수정했고 각 코드 수정 뒤 M/P/H/B0를 재실행한
다음 새 SHA에서 S1부터 다시 시작했다. 실제 Google OAuth, Vertex, cloud 호출은 없었다.

## 결과와 영향

- G5C2가 사용할 데이터 권한과 rollback 경계가 PostgreSQL schema로 고정됐다.
- cross-owner 귀속, terminal mutation, append-only Usage와 populated downgrade를 실제
  격리 PostgreSQL에서 두 번 검증했다.
- 기존 lifecycle/auth/ownership/file 흐름이 새 head0006에서도 유지됨을 입증했다.
- Evidence level은 `Mock Verified locally`이다. persistence가 구현됐다는 뜻이며 실제
  reserve/settle/release, 월 credit 소진 거절, 생성 과금 또는 live provider 검증을
  의미하지 않는다.
- F1 scope/architecture, F2 data/security, F3 verification/operations self-review는
  APPROVE다. F4는 Ready PR 최종 head의 required3 CI와 실제 protected squash merge 뒤
  완료한다.

## Rollback과 남은 위험

- 네 accounting 테이블이 모두 비었을 때만 reviewed downgrade to0005가 가능하다.
  데이터가 있으면 삭제하거나 trigger를 우회하지 않고 forward fix를 사용한다.
- C2는 C1 merge 후 exact paths와 Goal을 새로 동결하며 migration은 추가하지 않는다.
- abandoned hold reconciliation, Job/Outbox/terminal-state 결합, per-user concurrency,
  개인 UI, Master/Audit와 실제 provider 과금은 후속 Goal이다.
- Issue120만 이번 delivery에서 닫는다. Issues121/117/114는 열린 상태를 유지한다.

## Evidence artifacts

- Aggregate design: `docs/initiatives/g5-credit-accounting-spec.md`
- Frozen execution plan: `.omo/plans/issue-120-g5c1-credit-accounting-persistence-goal.md`
- Goal SHA-256: `d55cad9eba3013706dfd6554894c78af40ef927ed8c03352fbca062c3463f8cc`
- Local receipts: `.omo/evidence/` 아래 redacted fixed receipts; `.omo`는 commit하지 않음
