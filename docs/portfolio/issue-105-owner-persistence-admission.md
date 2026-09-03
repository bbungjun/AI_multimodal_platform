# Issue #105 — Owner persistence and authenticated admission

- 상태: **Ownership Admission Mock Verified — 구현·문서 완료 / delivery는 PR 기준**, 2026-09-03.
  아래 준비 기록과 실행 기록을 구분한다.
- [Issue #105](https://github.com/bbungjun/AI_multimodal_platform/issues/105),
  branch `codex/issue-105-owner-persistence-admission`.
- Base: synchronized main `4dd359ab39285e536e713a452577e19c07b3ec67`, G4.1 PR104.
- [Accepted spec](../initiatives/g4-2-owner-persistence-admission-spec.md),
  [initiative](../initiatives/auth-credits-master-console.md).
- Runtime verification: **PASS**, 최종 구현 `e3c98f1fe5d5a05fb04dee2f1814dcad3ad9b527`.
  Ready PR/최종 CI/merge는 아래 delivery 링크를 기준으로 확인한다.
- Delivery: [Ready PR #106](https://github.com/bbungjun/AI_multimodal_platform/pull/106).
  이 문서는 병합 전 증거 snapshot이며 최종 head CI/실제 squash merge SHA는 PR/Issue가
  source of truth다. 문서 commit의 backend/scripts tree가 검증한 구현 SHA와 같음을 확인했다.

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

준비 단계에는 DB 변경이 없었다. 구현 후 rollback은 아래 Todo8 절과
[운영 절차](../runbooks/local-mock.md#owner-schema-and-admission-g42a)를 따른다.

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

## 준비 단계의 결과와 영향

전체 합의와 이번 A 실행 범위를 구분하고 다음 실행자가 context를 한 Todo씩 읽도록 했다.
Issue105와 작업 branch, frozen Goal/hash까지 준비했으며 제품 코드/migration은 추가하지 않았다.
실제 기능 개선 수치, 보안 PASS, Docker 검증 횟수, CI 또는 PR merge 성과는 아직 없다.
이 기록은 준비 결과이며 Goal Todo 완료 기록으로 사용하지 않는다.

## 준비 단계에서 남긴 위험과 다음 단계

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
네 adversarial 회귀를 추가한 W183/H113 PASS. 첫 보강 checkpoint
`c8ee90a2d1d17774eac17900a936592b46c45090`에서 다시 검증했다.

- Linux 전체 **656 PASS / 기존 SKIP3 /3.32s**; Windows **655 PASS / SKIP3 /
  동일 Bash-path FAIL1 /8.38s**. Windows 예외는 위의 main 독립 재현으로 분류했으며
  skip/xfail을 추가하거나 CI 검증을 우회하지 않았다.
- B0 **288 PASS /4.00s**, S schema13, A25, W183, H113 PASS.
- 최종 ownership: `ownership-verify-06860640f43f` **97.20s**,
  `ownership-verify-e63ce598d6fd` **73.89s**. 각각 auth12/admission111/smoke3 PASS,
  cleanup=true. 두 프로젝트의 정확한 label 기준 container/volume/network는 모두0이다.
- tracked archive만 사용한 Linux test container도 종료/제거됐다. default/preview
  DB와 container는 그대로이며 `.env.example` Compose quiet 검사 PASS.
- 기존 integration skip3은 `test_auth_api.py`, `test_auth_service.py`,
  `test_oauth_flow_store.py`의 guarded PostgreSQL/Redis 전제조건이다. 실제 통합 경계는
  Todo6 auth verifier와 최종 ownership verifier로 검증했다.

해당 보강은 API 오류 분류와 단위 테스트뿐이다. schema/auth/harness 구현은 앞선 실제
검증 revision과 동일하며 이후 문서-only commit은 이 구현 SHA를 검증 근거로 사용한다.

#### 최종 리뷰에서 재발견한 rollback 경계

Todo8 인수 검토에서 retry의 IntegrityError 처리 중 rollback 후 `source.mode` 접근이
만료된 ORM 속성의 재조회로 이어질 수 있음을 발견했다. 일반 fake는 이 만료 동작을
재현하지 않아 이전 테스트에서 보이지 않았다. mode를 rollback 전에 저장하고,
실제 SQLAlchemy Session의 `expire`를 적용한 회귀2개를 추가했다. 새로운 코드 경로는
필요 없었으며 generations/test_generation_api 두 허용 경로 안에서 수정했다.
따라서 Todo7 영향 검증을 최종 commit `e3c98f1`에서 다시 수행했다.
Linux **658 PASS / 기존 SKIP3 /3.55s**, Windows **657 PASS / SKIP3 / 동일 baseline FAIL1 /9.07s**,
B0 **290 PASS /3.72s**, W185+H113 **298 PASS /3.45s**. 프론트와 schema/auth/harness는 변경하지 않았다.
최종 ownership2회는 `ownership-verify-25f997f898ce` **99.73s**와
`ownership-verify-f39362666be5` **76.44s**이며 각각 auth12/admission111/smoke3 PASS,
cleanup=true, exact-label container/volume/network0이었다. schema와 auth proof 코드가
Todo6 이후 동일함을 diff로 확인했고, 읽기/list/delete endpoint4개의 AST 및 제외 경로도
base와 동일했다. 기존 test 함수90개 이름이 모두 보존됐으며 skip/xfail 추가0이다.

### Todo8 — 인수 근거와 운영 한계

결과: 인증된 사용자의 신규 생성·재시도·pipeline·prompt owner가 DB에 저장되며,
타인의 UUID를 알고 있어도 접수 시 동일404로 거절한다. Master도 타인 자료를 재사용해
생성할 수 없다. strict extras가 owner 위조를422로 차단한다. Asset owner 중복 저장 없이
Job join으로 검증하고, schema와 writer를 같은 delivery로 묶었다.

검증 명령은 [testing](../testing.md#owner-persistence-and-admission-g42a)의 R 그룹과
frozen Goal의 B0/S/A/W/H/L/U/D 그대로 실행했다. Windows의 Bash-path 실패는
`tests/test_supply_chain_release.py::test_release_script_guards_plan_scope_and_uses_terraform_rollback`이며
main4dd359a 독립 tracked archive에서도 같은 오류가 났다. Linux/CI는 통과를 별도 요구한다.
최종 프론트 검증은 `npm run lint`, `npm run build`, `npm run test:auth`(48),
`npm run test:auth:browser`(34)이며 frontend 파일은 변경하지 않았다.

#### Acceptance traceability

아래는 단일 실행자의 순차 검토이며 독립 reviewer 검증으로 표현하지 않는다.
pytest node는 `backend/tests/` 기준이고 parameterization을 포함한다.

| 계약 | 실행 가능한 근거 | 관측 결과 |
| --- | --- | --- |
| P01 | `test_generation_api.py::test_admission_p01_real_dependency_rejects_before_generation_effects`; `verify_ownership.py` admission matrix | 네 writer 인증/Origin 거절; actual invalid Session28/Origin8 checks per cycle, unit 부수효과0 |
| P02 | `test_generation_api.py::test_admission_p02_persists_actual_actor`, `test_pipeline_api.py::test_create_pipeline_persists_parent_and_blocked_child`, `test_prompt_api.py::test_enhance_prompt_persists_result_and_returns_response` | A/B/Master 실제 actor owner, 실제 persisted checks18/cycle |
| P03 | 세 API의 `test_admission_p03_*` | owner/user/role 위조422, actual HTTP9/cycle |
| P04/P05 | `test_generation_api.py::test_admission_p04_p05_foreign_missing_same404_before_semantics`; ownership access25 | foreign/missing/Master 동일404, own400/409 유지; actual reference/semantic27/cycle |
| P06 | `test_admission_p06_*`, `test_retry_failed_generation_creates_new_pending_job_without_mutating_original`, `test_admission_untrusted_parameters_cannot_spoof_conflict` | retry lineage/new id/원본 유지, rollback, exact unique409; 실제 outbox commit-failure3/cycle |
| P07 | `test_ownership_persistence.py::test_schema_owner_fk_not_null_no_default_and_composite_index`, `test_schema_asset_unique_path_without_duplicated_owner`; schema verifier | 실제 제약 거절·Asset join PASS; composite 순서는 정적 metadata 검사 |
| P08 | `test_schema_migration_refuses_nonempty_before_ddl`; schema verifier ownership proof | 매 run8개 upgrade/downgrade 거절, rows/schema/revision/identity 보존, lock-timeout rollback |
| P09 | `test_schema_harness_and_verifier_head_parity`, Alembic/schema verifier 회귀와 real schema2 | old migrations 동일, head0003 parity, stale 거절/복구·guarded reset PASS |
| P10 | `verify_ownership.py --env-file .env.example --cycles 2`; H113 | 최종 코드의 각 auth12/admission111/smoke3 PASS, distinct projects/cleanup0 |
| P16 | `test_verify_ownership_script.py` target/collision/receipt canary, mock-auth 안전 회귀와 cumulative diff | non-document20, migration1, 민감 evidence 미기록, default/preview 미변경 |

P11–P15는 B로 **미구현/미검증**이다. optional integration skip3을 해당 계약의 PASS로
대체하지 않는다. 고정 schema proof는 Asset 케이스의 필수 parent fixture 등을 포함하며,
FK가 필요한 경우를 독립 단일-row 검사로 잘못 표현하지 않는다.

Rollback/남은 위험:

- 신규 migration의 upgrade/downgrade는 content가 있으면 원자적으로 거절한다.
  비어 있지 않은 DB를 지우거나 Master에 자동 귀속하지 않는다. 호환 code/schema를 유지하고
  기존 데이터 처리에는 별도 설계·승인을 받는다. 개발/preview migration은 실행하지 않았다.
- FK는 user 존재만 보장한다. worker의 사용 직전 관계 검사와 pipeline/race 강화는 B,
  조회/list/delete/file/ops/cache 경계는 G4.3이다. 공개 multi-user 배포는 금지 상태다.
- Prompt provider 성공 후 DB commit 실패의 비용 비원자성은 남는다. Credit/Reservation을
  임의로 추가하지 않았다. 긴급 Session 폐기99와 live OAuth/proxy/provider 검증도 별도다.
- 실제 고객 KPI/비용 절감이나 cloud 배포 결과를 주장하지 않는다. 여기의 수치는 로컬
  mock 검증 횟수·테스트 통과와 재현 결과다.

최종 self-review: F1 scope, F2 correctness/security, F3 runtime/regression은 위 증거로
APPROVE. F4 문서 검토는 APPROVE이며 **delivery는 최종 PR head의 verify + 양쪽
Scan/SBOM 성공 및 실제 squash MERGED 관측 전까지 PENDING**이다. 최종 merge SHA는
PR/Issue와 종료 보고에 기록하며 사후 상태를 위해 추가 문서 PR을 반복하지 않는다.

인수 문서 검증: Todo8 W/H298 PASS, schema/access/regression106 PASS, 상대 문서 링크91개
오류0, cumulative allowlist20/migration1/historical bytes/hygiene PASS. 실행 중 read-only
AST 보존 검사의 Windows 기본 cp949 decoding 오류는 UTF-8 명시 후 재실행하여90개 기존
test 이름 보존을 확인했다. 제품 실패나 scope 확장으로 처리하지 않았다.
