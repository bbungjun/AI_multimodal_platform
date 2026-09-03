# Issue #105 — Owner persistence and authenticated admission

- 상태: **In Progress — Todo1**, 2026-09-03. 아래 준비 기록과 실행 기록을 구분한다.
- [Issue #105](https://github.com/bbungjun/AI_multimodal_platform/issues/105),
  branch `codex/issue-105-owner-persistence-admission`.
- Base: synchronized main `4dd359ab39285e536e713a452577e19c07b3ec67`, G4.1 PR104.
- [Accepted spec](../initiatives/g4-2-owner-persistence-admission-spec.md),
  [initiative](../initiatives/auth-credits-master-console.md).
- Runtime verification, PR/merge: **not started**.

## 배경과 문제

로그인·Session 검증 harness는 있지만 콘텐츠 owner 저장과 생성 요청의 참조 검증은 없다.
기존 단일 G4.2 실행 예상표에는 harness schema head, identity column assertion,
직접 worker 경로와 runtime proof의 변경이 빠져20개 경로를 넘길 위험이 있었다.
schema만 분리해서 먼저 적용하면 기존 익명 writer가 NOT NULL 오류를 낼 수도 있다.

## 관측과 원인 분석

기존 설계 기록5개가 이전 G4.1 branch에 dirty 상태로 남아 있었다. 이를 삭제하거나
이미 병합된 PR에 섞지 않고 정확한 경로만 stash하여 main 동기화 후 복원했다.
충돌은 없었고 `.omo`의 기존 계획/evidence는 보존했다. 원격 main은 G4.1 merge4dd359a다.
기존 CI의 실제 job 이름은 verify / Scan and SBOM (backend) / Scan and SBOM (frontend)이며,
향후 실행 종료에서 최종 PR head의 세 결과와 실제 MERGED를 확인하도록 했다.

## 해결 방법과 판단 근거

사용자가 승인한 A/B 분할을 canonical 상태표와 spec에 반영했다. A는 schema와 네 writer,
접수 시 참조 검증을 하나의 delivery slice로 묶고 worker/pipeline/race 강화는 B로 넘긴다.
작은 Ownership Interface가 actor/session을 받아 owner-scoped SQL과404를 책임지며,
commit/rollback은 HTTP caller에 남긴다. 이는 codebase-design의 Interface/Locality 기준을
반영한 설계이며 범용 ACL, RLS, Master backfill은 추가하지 않는다.

- A 정확한 non-document allowlist20개, migration0003 정확히1개.
- Todo1–8, F1–F4, focused tests/작은 commit과 중단 기준을 frozen Goal에 고정.
- 실제 schema2회/auth1회/admission2cycle, Linux 전체 회귀와 무변경 frontend 회귀.
- migration은 generation4개 테이블을 같은 transaction에서 잠근 뒤 비어 있지 않으면
  DDL 전에 거절한다. 개발/preview DB 초기화는 승인되지 않았으며 검증은 새 isolated DB만 쓴다.
- A 완료는 Ownership Admission Mock Verified다. 전체 read/file/delete/ops 격리는 G4.3이며
  공개 배포 가능 또는 실제 OAuth/Vertex 검증으로 표현하지 않는다.

rollback은 향후 데이터 상태와 code/schema 호환성에 따른 운영 절차로 남긴다.
현재는 문서 준비뿐이므로 DB rollback이나 reset할 변경 자체가 없다.

## 검증 — 실행 준비에서 실제 수행한 것

- `git fetch origin`, main fast-forward, exact-path stash/restore, Issue/branch 생성.
- `AI_PROVIDER=mock`, backend에서 계획 B0의 기존11개 test 파일: **212 PASS /2.69s**.
  대상: generation/pipeline/prompt API, identity/Alembic/model relationships/schema control,
  schema/auth/ownership verifier, mock auth support. 새로운 소유권 기능의 PASS가 아니다.
- 정적 검사 PASS: 계획/spec allowlist20 일치, Todo1–8/F1–F4 일치, 설명된 신규 경로3개,
  문서 상대 링크71개/오류0개, 제품 코드 변경0개.
- `git diff --check`, status, cached path 검사 PASS. 준비분은 문서7개만 명시적으로 stage/commit한다.
- local plan SHA256:
  `e7f40b1d993cbdc9e4d3edb116dfcf2ebf6c17b379e0bab170f6550a303d87ab`.
  파일: `.omo/plans/issue-105-g4-2a-owner-persistence-admission-goal.md`.
  계획은 local/untracked이므로 다른 기기에는 exact bytes를 별도로 전달해야 한다.

## 결과와 영향

전체 합의와 이번 A 실행 범위를 구분하고 다음 실행자가 context를 한 Todo씩 읽도록 했다.
Issue105와 작업 branch, frozen Goal/hash까지 준비했으며 제품 코드/migration은 추가하지 않았다.
실제 기능 개선 수치, 보안 PASS, Docker 검증 횟수, CI 또는 PR merge 성과는 아직 없다.
이 기록은 준비 결과이며 Goal Todo 완료 기록으로 사용하지 않는다.

## 남은 위험과 다음 단계

- 명시적 Goal 실행 요청 후 hash/branch/base와 기존 변경부터 재확인한다.
- 21번째 또는 allowlist 외 경로가 필요하면 테스트를 줄이지 말고 중단·재설계한다.
- 실행 시 각 Todo receipt에 실제 실패/원인/수정/수치와 commit을 덧붙인다.
- Ready PR 생성 → 최종 head 필수 CI → squash auto-merge의 실제 병합이 실행 종료 조건이다.
- B worker/pipeline/race와 G4.3 전체 접근 제어, 긴급 폐기99/live 검증은 미완료다.
- 기존 개발/preview DB를 비우거나 managed Redis/실제 provider 비용을 발생시키지 않는다.

## 실행 기록

### Todo1 — baseline

명시적인 실행 요청 후 frozen SHA, branch, main4dd359a ancestry를 확인했다.
관련 tracked/staged 변경0, 기존 .omo 보존. B0 기존11파일 **212 PASS /2.84s**.
Docker Desktop local named-pipe daemon29.2.1을 읽기 전용으로 확인했다.
기존 default/preview DB volume과 preview5개 container는 손대지 않았다.
이 단계는 preflight이며 새 owner 기능이나 runtime gate 통과를 뜻하지 않는다.

### Todo2 — 의도된 RED 계약

schema13개/access25개 새 계약은 각각 누락된 owner/unique/migration/head와
Ownership Interface 때문에 예상 RED였다. 기존 metadata/revision 기대값2개도 RED,
나머지 S 회귀64개 PASS. collection 오류0, skip/xfail 추가0.
SQL owner scope, 반환 row 재검증, Master/None 거절, target row lock,
transaction 부수효과0와 migration DDL 전 거절을 구현 전에 고정했다.

### Todo3 — schema/head compatibility

두 owner NOT NULL/RESTRICT/composite index, Asset path UNIQUE와0003을 추가했다.
upgrade/downgrade는 generation4개 테이블의 ACCESS EXCLUSIVE lock과5초 lock timeout,
DDL 전 nonempty 거절을 사용한다. 기존0001/0002는 수정하지 않았다.
schema/auth/harness/seeder head와 reset owner fixture를 맞췄다.
격리 verifier에 actual constraint/8회 refusal/identity preservation/lock-timeout proof를
추가했지만 실제 runtime 실행은 Todo6으로 남겼다. 내장 proof의 문자열 구문 오류를
단위 검사에서 잡고 수정했으며 재발 방지를 위해 compile 검사도 추가했다.
S 새 schema13 PASS + 기존/확장 회귀68 PASS, H106 PASS. Access25 RED는 Todo4 입력이다.

### Todo4 — Ownership Interface

owner-scoped SQL과 반환 row 재검증, Master 동일 정책, null/missing404,
의도하지 않은 intent 거절과 Asset row만 잠그는 join을 구현했다. commit/rollback은 하지 않는다.
AsyncSession 결과의 first/one_or_none는 동기 메서드이므로 초기 AsyncMock 결과를
동기 Mock으로 정정했다. 제품 코드를 fake에 맞춰 바꾸지 않았다.
Access25 PASS, schema13 PASS, schema 회귀68 PASS. writer 적용 전이며 실제 DB proof는 미실행이다.

### Todo5 — authenticated writers

generation/retry/pipeline/enhance에 함수별 require_user를 연결했다. 모든 신규 Job/Prompt의
owner는 인증 actor이며 request extras는422로 거절한다. foreign/missing 참조는 동일404,
자신의 reference인 경우만 의미 검사를 한다. retry의 source row lock/active409와
Job/outbox rollback을 보강하고, pipeline parent/child에는 같은 owner를 저장한다.
기존 fake는 명시적인 일반 User actor와 실제 FK 관계를 갖도록 바꿨으며 전역 Master
override는 추가하지 않았다. 누락 참조의 이전400/409 기대값은 승인된404 계약으로 바꿨다.
W179 PASS, S68 PASS, H106 PASS. 생성 거절 시 provider/storage/DB 부수효과0는 unit proof이며,
실제 G3 Session과 PostgreSQL 검증은 Todo6에서 별도로 수행한다. Read/delete/worker는 변경하지 않았다.

### Todo6 — 실제 격리 검증

제품 코드 checkpoint133b882, 확장 admission harness2232ba6에서 검증했다.
schema verifier2회: `schema-verify-222735bbc2af`, `schema-verify-e87fa3ef5958` 모두 PASS.
각각 실제 owner 제약,8개 nonempty upgrade/downgrade refusal, identity 보존,
lock timeout, stale revision 거절/복구, guarded reset와 round-trip을 확인했다.
auth verifier `auth-verify-f24475ad43c1` PASS: PostgreSQL/Redis와 outage/recovery,
50개 인증 요청의 테스트 p95=10.499ms; 이는 제품 SLO 측정 결과가 아니다.
ownership2회: `ownership-verify-2da4a26b46bb`77.75s /
`ownership-verify-d53ff045b381`77.81s. 각 auth12/admission111/smoke3 PASS, cleanup=true.
admission111은 HTTP 결과93개와 persisted row 검사18개를 합한 개수다.
검증 runtime의 worker/dispatcher만 잠시 멈춰 접수 상태를 고정하고, actual outbox trigger
실패에서도 Job/outbox 추가0을 확인했다. test rows/trigger 제거 후 consumers를 재시작하여
기존 golden/retry/중복 I2V 시나리오를 그대로 실행했다. G4.2B worker 강화의 증거는 아니다.
민감한 fixture/응답 값은 메모리에서 비교했다. 잘못된 admission metric이 receipt에
들어가기 전에 검증하도록 하고 canary 검사로 확인했다. H113 + W179 =292 PASS, S68 PASS.

### Todo7 — full regression 중 발견한 오류 분류 보강

첫 Linux full652 PASS/기존 integration skip3, Windows651 PASS/skip3/기존 Bash-path fail1.
해당 `test_supply_chain_release` 실패는 수정 전 main4dd359a의 독립 archive에서도
재현했다. 실제 cloud 명령은 실행하지 않고 bash 구문 검사만 수행했다.
frontend lint/build, Session48, Chromium34 PASS; 기존 UI/CSS는 수정하지 않았다.
코드 검토에서 legacy I2V classifier가 SQL exception 문자열 전체를 검색하여 요청 parameter에
index 이름이 있으면 다른 constraint 오류를409로 오인할 수 있음을 재현했다.
허용된 generations 경로에서 PostgreSQL SQLSTATE23505와 driver의 정확한 constraint metadata를
먼저 확인하도록 보강했다. 공용 i2v_guard/worker 파일은 변경하지 않았다.
네 adversarial 회귀를 추가한 W183/H113 PASS. 최종 committed code의 ownership2회와
Linux/Windows 전체 pytest를 다시 실행한 뒤 최종 수치를 기록한다.
