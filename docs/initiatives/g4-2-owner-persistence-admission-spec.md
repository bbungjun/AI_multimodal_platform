# G4.2 — Owner persistence, admission and worker invariants

## 0. 상태 / 읽기 범위

- **G4.2A/B Mock Verified — 2026-09-03; B delivery는 실행 기록의 PR 참조.**
- B 실행: [Issue #107](https://github.com/bbungjun/AI_multimodal_platform/issues/107),
  branch `codex/issue-107-worker-ownership-invariants`, A merge `d40a8f7` 기준.
  `.omo/plans/issue-107-g4-2b-worker-ownership-invariants-goal.md`,
  SHA256 `16f6cda60a7306b86bbd909c84241e25394117bb2953ae4445c70c550e271064`.
  구현 `ff808b0`: 실제 독립2cycle, 각 auth12/admission111/smoke3/execution20/pipeline4/
  race3/expiry1 PASS/cleanup0. Linux782 PASS/기존 SKIP3, frontend48+34 PASS.
  B1–B4는 구현 계약이며 [실행·실패 분석 기록](../portfolio/issue-107-worker-ownership-invariants.md)을 함께 본다.
- A 실행: [Issue #105](https://github.com/bbungjun/AI_multimodal_platform/issues/105),
  branch `codex/issue-105-owner-persistence-admission`, main `4dd359a` 동기화 완료.
  frozen Goal은 `.omo/plans/issue-105-g4-2a-owner-persistence-admission-goal.md`이며
  SHA256은 `e7f40b1d993cbdc9e4d3edb116dfcf2ebf6c17b379e0bab170f6550a303d87ab`.
  구현 `e3c98f1`의 schema2/auth1/final admission2, Linux658/기존 SKIP3,
  frontend48+34 PASS. [실행 기록](../portfolio/issue-105-owner-persistence-admission.md)에
  실패 분석·안전한 검증 근거와 PR delivery 상태를 연결한다. 전체 사용자 격리 완료는 아니다.
- 선행: [G4.1 PR104](https://github.com/bbungjun/AI_multimodal_platform/pull/104),
  merge `4dd359ab39285e536e713a452577e19c07b3ec67`.
  설계 시 checkout `670a658`과 merge의 tree가 같음을 확인했다.
- 전체 권한 정책·Master read-only 예외·DB 폐기 정책은
  [initiative](auth-credits-master-console.md#ownership-invariants)와
  [G4 계약 §2–5](g4-ownership-access-control-spec.md)를 따른다. 이 문서는 실행 분할만 구체화한다.
- 기존 단일 G4.2의 20-path 예상표는 실행용 allowlist로 확정하지 않는다.
  아래 A/B 분할은 **사용자 승인 완료**이며 G4.2의 제품 범위를 넓히지 않는다.
- 로컬 Docker PostgreSQL/Redis + AI_PROVIDER=mock만 사용한다.
  실제 OAuth/AI provider/cloud, frontend 수정, Plan/Credit/Usage/Audit는 제외한다.

## 1. 설계 당시 코드에서 확인한 수정 이유

| 관측 | 실행 계획에 미치는 영향 |
|---|---|
| `scripts/mock_auth_support.py`와 `backend/tests/ownership_support.py`가 head0002 고정 | 둘 다 새 head로 맞춰야 G4.1 smoke가 seed 단계에서 중단되지 않는다 |
| `test_identity_models.py`가 generation model의 전체 column 집합을 고정 | owner 추가를 명시적으로 반영하되 identity 불변식과 historical migration 검증은 보존해야 한다 |
| `handlers.py:handle_i2v`가 Asset을 읽은 뒤 바로 storage/provider 사용 | pipeline_link만 바꾸면 직접 I2V 실행과 polling 재개 검증을 놓친다 |
| `pipeline_link`는 완료 연결뿐 아니라 부모 실패 시 child를 변경 | 두 경로 모두 같은 owner 검증이 필요하다 |
| retry는 source Asset을 잠그지 않고 IntegrityError를409로 변환하지 않음 | 인증을 붙이는 것만으로 create/retry 경합 계약이 완성되지 않는다 |
| API fake의 scalars 결과가 미리 정해져 있음 | SQL scope 검증과 실제 Postgres 검증을 별도로 수행해야 한다 |

기존20개에 빠진 harness head/identity test/worker와 그 테스트/runtime matrix 경로를
모두 포함하면20개를 초과한다. 테스트를 삭제하거나 동작을 문서·생성 파일로 숨겨서
경로 수를 맞추지 않는다. schema만 먼저 적용해 익명 writer가 NOT NULL 오류를 내는
중간 PR도 만들지 않는다.

## 2. 승인된 분할과 checkpoint 의미

| 실행 Goal | 한 번에 닫는 산출물 | non-document 예산 | migration |
|---|---|---:|---:|
| G4.2A | owner schema + 모든 신규 writer 인증/owner 부여 + 요청 참조 검증 | 최대20, 아래 후보 정확히20 | 정확히1 |
| G4.2B | worker의 실제 사용 직전 참조 검증 + pipeline 링크/실패 전파 + 실경합 회귀 | 구현11, hard cap20 | 0 |
| 기존 G4.3 | read/list/delete/file/ops 접근 제어, cache, 전체 E2E | 기존20 재확인 | 0 |

A와 B 각각 독립 Issue/branch/frozen Goal/PR/검증을 갖는다. A 병합 후 B 입력은
owner/schema/admission interface와 실제 merge SHA뿐이다. 전체 인터뷰나 A 작업 로그를
B Goal 입력에 복제하지 않는다. 각 Goal에서 21번째 경로가 필요하면 구현 중단·재설계한다.

A 완료는 **Ownership Admission Mock Verified**, B까지 완료는 **G4.2 Mock Verified**다.
어느 단계도 모든 데이터 격리가 아니다. 읽기·파일·삭제·ops가 남아 있으므로 공개 배포 No-Go.

## 3. G4.2A 구현 계약

### A1. 저장소와 migration

- `0003_content_ownership` → `0002_user_session_persistence`, historical0001/0002 수정 금지.
- Job/PromptEnhancement에 `owner_user_id UUID NOT NULL`, users FK RESTRICT,
  `(owner_user_id, created_at, id)` index. Python/server default, nullable 전환 기간,
  sentinel Master와 자동 backfill 없음. owner는 응답에도 새로 노출할 필요가 없다.
- Asset owner 컬럼은 추가하지 않고 Job에서 유도한다. `local_path` UNIQUE 추가.
  기존 SET NULL/CASCADE/active-I2V partial unique index와 enum은 유지한다.
- Upgrade/downgrade 모두 동일 트랜잭션에서 generation4개 테이블을 잠그고
  비어 있는지 DDL보다 먼저 검사한다. 검사와 DDL 사이 concurrent INSERT를 허용하지 않는다.
  하나라도 남으면 고정 refusal code로 실패하고 revision/DDL/row 변경0을 확인한다.
- User/Session만 있는 DB는 upgrade 가능하며 값·개수·FK를 보존한다.
  migration에 DELETE/TRUNCATE/DROP DATABASE/자동 owner 할당을 넣지 않는다.
- 현재 developer/preview DB는 건드리지 않는다. 새 격리 DB에만 migration을 실행한다.
  운영 rollback은 서비스 정지 후 old code/schema 호환성 검토가 필요하다.

### A2. 인증·입력·부수효과 순서

인증을 붙이는 route는 네 개다: generation POST, retry POST, pipeline POST,
prompt enhance POST. 함수별 `Depends(require_user)`를 적용하고 router 전체의
read/delete 정책까지 바꾸지 않는다. G3가 mutation Origin을 검사한다.

- 모든 새 Job과 PromptEnhancement owner는 DB 인증 actor.id다. email/plan/role/payload에서 추론하지 않는다.
- GenerationRequestBase/PromptEnhanceRequest/PipelineCreateRequest에 extra=forbid.
  `owner_user_id`, `user_id`, `role` 위조는422. 기존 frontend payload는 그대로 성공해야 한다.
- 유효 payload: Session/Origin → 참조의 owner 확인 → mode/model/state/kind 검사 → provider/Job/outbox.
  잘못된 body/UUID의 FastAPI422는 허용한다. 이를 위해 validation framework를 교체하지 않는다.
- 유효 UUID의 foreign/missing 참조는 동일404 `content_not_found`.
  자기 enhancement의 target mismatch는 기존400; 자기 retry의 non-failed는 기존409.
- Master도 타인 enhancement/source/retry는404. A에서 Master read/all 기능을 미리 만들지 않는다.
- 요청 거절 시 provider 호출, Job/Prompt/Asset/outbox INSERT, storage 쓰기/삭제 모두0.
  G3의 Session touch 자체는 인증의 정상 부수효과이므로 generation side-effect와 구분한다.
- prompt enhance provider 호출은 인증 이후다. 결과 저장 실패와 provider 비용의 비원자성은
  기존 한계로 남기며 credit/reservation으로 해결하려 하지 않는다.

### A3. Ownership module의 작은 interface

`backend/app/ownership.py`에서 다음만 제공한다(정확한 타입·오류·잠금은 A frozen Goal에 고정).

```python
access = OwnershipAccess(session, actor)
await access.job(job_id, intent="mutate", lock=False)
await access.enhancement(enhancement_id, intent="use")
await access.asset(asset_id, intent="use", lock=False)
assert_same_owner(job, related)
```

module은 commit/rollback/provider/storage를 하지 않는다. HTTP caller가 기존 transaction을
소유한다. scoped SQL 조회와 row owner 재검증을 함께 수행하고 None owner는 거절한다.
Asset은 Job과 join하여 소유권을 판정한다. A는 mutate/use만 구현하고 미지원 intent는
fail closed; G4.3에서 read/scope/file interface를 추가한다. 범용 ACL/repository 엔진은 없다.

Asset 잠금은 join된 users/jobs 전체를 잠그지 말고 `FOR UPDATE OF assets` 등으로
의도한 row만 잠근다. create/retry가 기존 `i2v_guard`의 같은 source lock 규칙을 사용한다.
owner가 맞는 참조들을 모두 확인한 뒤 provenance/model/kind를 검증하므로, foreign source의
active 상태를409로 먼저 노출하지 않는다. Asset과 enhancement 둘 다 제공되면 고정 순서
(enhancement → source)로 접근 권한을 확인하고 그 뒤 의미 검사를 한다.

### A4. Writer별 계약

- T2I/T2V: actor owner로 Job + outbox를 한 transaction에서 commit. 최종 prompt는 payload다.
- I2V: 자신의 image Asset만 사용; owner 확인·source row lock → active 검사 → Job/outbox.
  정확히 기존 active-I2V constraint violation만 rollback 후409로 변환한다.
- Retry: 먼저 자신의 원본 확인 → failed state → 남아 있는 enhancement/parent/source 관계
  owner 재검증 → 새 id·같은 owner·기존 lineage를 저장한다. I2V는 create와 같은 row lock과
  unique409 처리. 이미 null로 정리된 optional link는 기존 의미를 유지하되 신규 I2V source는 필수다.
- Pipeline: parent/blocked child에 같은 actor owner를 넣고 같은 transaction에 저장한다.
  parent outbox만1개, child outbox0개. worker 연결의 강화는 B이며 아직 완료로 주장하지 않는다.
- PromptEnhancement: actor owner를 명시해서 저장하고 기존 응답 필드/초안 검토 흐름 유지.

### A5. 승인된 G4.2A non-document allowlist (20)

```text
backend/app/models.py
backend/migrations/versions/0003_content_ownership.py
backend/app/ownership.py
backend/app/schemas.py
backend/app/api/generations.py
backend/app/api/pipelines.py
backend/app/api/prompts.py
backend/tests/test_generation_api.py
backend/tests/test_pipeline_api.py
backend/tests/test_prompt_api.py
backend/tests/test_identity_models.py
backend/tests/test_alembic_schema.py
backend/tests/test_ownership_persistence.py
backend/tests/ownership_support.py
scripts/mock_auth_support.py
scripts/verify_schema_migrations.py
backend/tests/test_verify_schema_migrations_script.py
scripts/verify_auth_sessions.py
scripts/verify_ownership.py
backend/tests/test_verify_ownership_script.py
```

`test_model_relationships.py`, `test_verify_auth_sessions_script.py`, `test_schema_control.py`는
현재 계약을 검사하며 그대로 실행한다. 새 owner metadata/head parity 검증은 해당 기능의
`test_ownership_persistence.py`에서 수행한다. 위 경로들이 실제로 변경되어야 한다면
예산 초과 여부부터 재검토한다. 0002를 읽는 reset snapshot fixture는 historical 데이터로
의도된 테스트이므로 무조건0003으로 치환하지 않는다.

### A6. 검증·기존 도구 호환

- head를 고정한 schema/auth/harness/seeder를 모두0003에 맞추고 test로 parity를 확인한다.
  schema verifier의 reset raw SQL에는 explicit 유효 User/owner를 넣는다.
- G1/G2 migration 내용과 그 당시 columns 검사 유지. 현재 metadata 검사에 owner만 추가한다.
- route fake는 각 helper에서 actor를 명시해 override 후 finally 원복한다.
  전역 autouse Master나 권한 module override 금지. 이것은 실제 인증 proof와 구분한다.
- `verify_ownership.py --env-file .env.example --cycles 2`는 기존 G4.1 auth12/세 smoke를
  유지하고 A/B/Master 실제 HTTP admission matrix를 추가한다. real cycle에서 auth override 없음.
- DB 확인용 `ownership_support.py` 확장은 owned runtime에서만 수행하며 고정 동작·메모리 비교·
  boolean/count 결과만 허용한다. arbitrary SQL/DB URL/Session secret CLI를 추가하지 않는다.
- 새 isolated Postgres2회에서 upgrade, 각4테이블별 nonempty refusal, rollback,
  FK/NOT NULL/unique/index, User/Session 보존, guarded reset, downgrade/re-upgrade,
  stale revision 거절·복구까지 실행한다. 개발 DB를 비우는 방식으로 통과시키지 않는다.

## 4. G4.2B 구현 계약

- A merge SHA와 owner/schema/admission interface만 입력으로 삼고 새 Goal을 만든다.
- `handlers.py`의 직접 T2I/T2V/I2V 호출과 polling 재개 모두 검사한다. dispatch 함수만
  감싸면 직접 handler를 호출하는 테스트/경로를 놓치므로 실제 사용 직전에 검증한다.
- worker는 저장된 Job owner를 신뢰 시작점으로 삼고 남아 있는 parent/retry/enhancement/
  source Asset의 Job owner 일치를 확인한다. Session 만료를 작업 취소로 해석하지 않는다.
- 신규 I2V submit은 source 필수. polling 재개에서 합법적으로 null인 optional 참조의
  기존 동작은 유지하되 남아 있는 참조가 foreign이면 provider poll보다 먼저 거절한다.
- 불일치는 고정 `ownership_reference_mismatch`로 해당 실행 Job만 transition FAILED 처리.
  타 owner Job/Asset을 수정하거나 owner를 자동 복구하지 않는다. provider/storage 호출0.
- pipeline 완료 연결과 부모 실패 전파 모두 parent/child owner를 확인한다.
  cross-owner child는 source 연결/unblock/outbox/state 변경0, 안전한 reason만 반환한다.
- parent 완료 뒤 link 실패를 parent 생성 실패로 덮어쓰지 않는다. 완료 state를 FAILED로
  되돌리는 우회 없이 PipelineLinkResult에 명시적인 안전 실패를 반환한다.
- 정상 link는 child row lock 아래 blocked→unblocked와 outbox 생성을 같은 transaction에
  수행한다. 반복/동시 호출에도 outbox1개. 기존 state machine/outbox dispatch 정책 유지.
- 실제 Postgres에서 create/create, create/retry, retry/retry를 동시에 실행한다.
  source별 active Job은1개, 나머지409, outbox 중복·500·deadlock0. worker 처리 전/후를
  구분해 active unique index의 의미를 검사하며 임의 sleep으로 동시성을 주장하지 않는다.

### B1. 정확한 실행 준비 allowlist (11, hard cap20)

2026-09-03 A merge `d40a8f704df583c050a6a89c235c311a0d4aef77`에서 재계수했다.
최초10개 후보에 격리 DB proof helper1개를 더한다. 이유는 실제 worker/pipeline/lock-holder
검증을 hash-only identity fixture와 분리하여 각 Todo의 읽기 범위를 제한하기 위해서다.
11개 밖의 non-document 경로가 필요하면20개 미만이어도 먼저 재설계한다.

```text
backend/app/ownership.py
backend/app/services/jobs/handlers.py
backend/app/services/jobs/pipeline_link.py
backend/tests/test_job_handlers.py
backend/tests/test_pipeline_link.py
backend/tests/test_ownership_execution.py
backend/tests/ownership_execution_support.py
backend/tests/ownership_support.py
scripts/verify_ownership.py
backend/tests/test_verify_ownership_script.py
scripts/mock_auth_support.py
```

### B2. Worker Interface와 검증 순서

`ownership.py`에 `OwnershipReferenceMismatch`와
`async validate_execution_references(session: AsyncSession, job: Job) -> Asset | None`를
추가하는 준비안이다. A의 `OwnershipAccess`/`assert_same_owner` 계약은 보존한다.
worker용 가짜 AuthenticatedUser/email/Session을 만들지 않는다. 저장된 실행 Job의 non-null
owner가 기준이며 User 상태·Session 만료·credit 정책은 조회하거나 새로 적용하지 않는다.

- 남아 있는 enhancement → parent → retry-of → source 순서로 확인한다. 유효 UUID가
  있으나 row가 없거나 owner가 다르거나 null이면 고정 mismatch 예외다. SQL owner predicate와
  반환 row 재검사를 함께 사용한다. Asset은 Job join에서 owner를 얻는다.
- `None`인 optional 관계는 허용한다. 단 신규 I2V submit의 source는 필수다. POLLING과
  operation name이 모두 있는 재개는 source가 이미 null이어도 허용하며, 남아 있는 참조는 검사한다.
- terminal Job은 기존 no-op을 유지한다. 직접 T2I/T2V/I2V entry, 각 provider 재시도 attempt,
  poll 진입 및 source storage-read 전에 검증한다. source는 검사 결과의 Asset을 사용한다.
  provider가 실행되는 동안 DB를 잠그거나 악의적인 동시 DB 변경까지 원자적으로 차단한다고
  주장하지 않는다. 오염 proof의 부수효과0는 각 진입 시점에 이미 오염된 경우의 계약이다.
- mismatch는 rate-limit/provider/storage보다 먼저 거절하고 해당 실행 Job만 FAILED로
  transition한다. `ownership_reference_mismatch`, 고정 safe message, retryable=false만
  공개 오류에 사용한다. 이 오류에는 T2I child failure cascade도 실행하지 않는다.
- rollback 전에 Job id 같은 scalar를 저장한다. rollback 후 expired ORM 속성을 읽지 않고
  저장된 id로 다시 조회한다. query 실패를 소유권 불일치로 조작하지 않으며 기존 일반 오류 처리 유지.
  nested provider 오류 변환/retry에서도 mismatch 예외를 그대로 통과시키고 재시도하지 않는다.
- provider가 성공한 뒤 pipeline 연결에 실패한 경우 COMPLETED parent를 실패로 재분류하지 않는다.
  연결 결과를 generation try/except와 분리하고 safe result로 전달한다.

### B3. Pipeline Interface와 transaction

`link_completed_parent`의 기존 `PipelineLinkResult`는 유지한다. foreign/null owner 또는
잘못 반환된 parent/asset 관계에는 `linked=False, reason="ownership_reference_mismatch"`,
식별자 필드None으로 반환하고 source 연결/unblock/outbox/state 변경0을 보장한다.
child query는 stable ordering + `FOR UPDATE OF jobs` + fresh row 재조회로 구성하고,
잠금 후 owner/state/blocked를 다시 검사한다. 이미 unblocked인 child는 fixed
`child_already_unblocked`로 no-op, 추가 outbox0이다. 정상 link는 unblock+outbox를 같은
transaction에서 commit하며 실패 시 rollback하고 `pipeline_link_failed`를 반환한다.
이 실패를 안전하게 보이게 하되 자동 복구/재발행 기능은 추가하지 않는다.

부모 실패 전파의 반환은 `PipelineFailureResult(failed_count, skipped_count, reason)`로
구체화한다. 기존 실제 caller는 handler이며 count 검사는 이 allowlist의 test에 있다.
foreign/null child는 변경하지 않고 skipped_count에 포함하며 safe mismatch reason을 반환한다.
자신의 blocked nonterminal child만 잠금 아래 transition FAILED 처리한다. 혼합 owner
collection도 foreign row를 수정하지 않는다. 외부 API 응답이나 dispatcher 정책은 바꾸지 않는다.

### B4. 실제 격리 검증 설계

기존 canonical `verify_ownership.py --env-file .env.example --cycles 2`를 확장한다.
auth12/admission111/기존 smoke3을 보존하고 별도 execution/pipeline/race count를 추가한다.
`scenarios=3`은 기존 smoke 개수 그대로이며 B 결과를 그 숫자에 숨기지 않는다.

- 실행 helper는 제품에서 import하지 않는다. 현재 owned runtime의 exact labels,
  mock/local, DB host/name, head0003, synthetic fixture inventory를 먼저 확인한다.
  fixed operation/typed records만 stdin으로 받으며 SQL/DB URL/raw Session 인자를 금지한다.
- 오염: 실제 PostgreSQL에 같은 owner/foreign 참조를 준비하고 실제 handler 및 pipeline
  함수를 호출한다. 이미 오염된 남은 참조는 실행 Job만 실패하고 foreign snapshot은 동일해야 한다.
  provider/storage 호출0은 별도 unit spies로 증명하며 DB row count만으로 대신 주장하지 않는다.
- Session 만료: 정상 인증으로 접수한 Job 뒤에 해당 테스트 Session만 DB에서 만료시키고
  `/me`401을 확인한다. 접수 Job은 worker에서 원 owner로 완료돼야 한다. 이후 테스트는 남은
  유효 actor를 쓰며 몰래 reseed/fallback하지 않는다.
- 실제 Celery pipeline은 parent/child 완료, 같은 owner, child source 연결과 child outbox1,
  생성 Asset bytes까지 확인한다. 직접 함수 DB proof와 Celery end-to-end proof를 구분한다.
- 경합3종(create/create, create/retry, retry/retry)은 서로 다른 source fixture로 격리한다.
  owned worker/dispatcher만 정지한 상태에서 host thread Barrier와 DB source row lock을 사용한다.
  두 HTTP 요청의 PostgreSQL lock waiter 수가2임을 확인한 뒤 lock을 해제한다. 단순 sleep이나
  ThreadPool 실행만으로 DB overlap을 주장하지 않는다. 각 pair는201 하나/409 하나,
  active1/outbox1/original 불변/500·deadlock0을 검사한다.
- lock holder는 test-only 고정 line protocol(준비/해제 ACK)을 사용하고20초 자체 timeout,
  host 관측5초와 기존 HTTP10초 timeout을 유지한다. 실패/EOF에도 transaction 해제와
  helper 회수 후 label-checked cleanup을 수행한다. 임의 subprocess/command 실행 Interface는 없다.
- pipeline의 반복/동시 link는 별도 AsyncSession 두 개와 row-lock 관측으로 outbox1을 증명한다.
  모든 fixture 제거는 새 owned DB만 대상으로 한다. developer/preview DB reset은 금지한다.
- 독립 전체2cycle 모두 PASS/cleanup0이어야 한다. 기존360초 work +90초 cleanup/cycle은
  늘리지 않는다. 새로운 count도 type/range 검증 후에만 receipt에 넣고 failure canary를 검사한다.

B는 migration0이므로 A의 destructive schema/reset QA를 반복 실행하지 않는다. 대신
모든 migration bytes/head0003 불변의 정적 회귀와 fresh runtime의 정상 upgrade/readiness를 검증한다.
Linux 전체 pytest와 무변경 frontend lint/build/auth/browser, 최종 head 필수CI3개 및 실제
Ready PR squash MERGED를 실행 종료 조건으로 한다. 실제 PASS와 delivery 증거는 위 실행 기록에 연결한다.

### B5. G4.3에 전달하는 구현 Interface

- `validate_execution_references(session, job)`와 `OwnershipReferenceMismatch`:
  저장된 owner, scoped fresh query, 안전한 non-retryable 실패. HTTP actor/Session을 요구하지 않는다.
- `PipelineLinkResult` 유지, `PipelineFailureResult(failed_count, skipped_count, reason)` 추가.
  child row lock 아래 재검사/원자적 outbox1; generation 완료와 link 실패 분리.
- A의 `OwnershipAccess`와 head0003/migration bytes는 그대로다. B는 migration을 추가하지 않았다.
- canonical runner는 세 기존 smoke와 별도 execution/pipeline/race/expiry 지표를 모두 요구한다.
- G4.3은 조회/list/delete/file/ops/cache 정책만 별도 Goal에서 구현한다. B의 검증은 공개
  다중 사용자 격리 완료나 live provider/OAuth 검증이 아니다. 실패한 link의 자동 복구는 없다.

## 5. 수용 기준 matrix

| ID | Goal | 사례 / 필수 결과 |
|---|---|---|
| P01 | A | 네 writer의 익명/만료/폐기/정지 Session401; Origin 오류403; 생성 부수효과0 |
| P02 | A | 네 writer의 정상 A/B/Master owner=각 actor; pipeline parent/child 동일 |
| P03 | A | 각 요청 model에 owner/user_id/role 추가422; 정상 frontend payload 호환 |
| P04 | A | foreign/missing enhancement/source/retry404 동일; Master도 동일 |
| P05 | A | foreign 참조+target/kind/active 오류404 우선, 자기 대상400/409 유지 |
| P06 | A | retry 새 id/owner/lineage, 원본 불변, Job/outbox commit 실패 rollback |
| P07 | A | 두 owner 컬럼 NOT NULL/FK RESTRICT/default 없음; Asset unique path와 유도 owner |
| P08 | A | User/Session-only upgrade 보존, 각각 nonempty4테이블 upgrade/downgrade 거절·원상태 |
| P09 | A | historical0001/0002 보존, reset fixture owner, head parity, stale refusal/recovery |
| P10 | A | 기존 auth12 + golden/retry/duplicate, 실제 A/B admission, 독립2cycle/cleanup0잔존 |
| P11 | B | 직접 handler와 polling에서 오염된 남은 참조 거절, provider/storage0 |
| P12 | B | 정상 Session 만료 후 접수 Job은 원 owner로 처리; 정지/credit 정책 추가 없음 |
| P13 | B | pipeline 완료/부모 실패 모두 foreign child mutation0; 정상 link 반복·경합 outbox1 |
| P14 | B | 세 종류 create/retry 경합에서 source별 active1, 나머지409, outbox/500/deadlock 오류0 |
| P15 | B | pipeline 실제 완료 + P10 회귀 + 오염 검증, 독립2cycle/cleanup0잔존 |
| P16 | A/B | 민감 receipt0, default/preview 변경0, provider/cloud0, migration 개수/경로 제한 준수 |

## 6. 실행 순서와 종료 조건

A의 Todo1–8 후보: (1) hash/base/경로/baseline, (2) failing owner·migration 계약,
(3) schema/model+도구head 호환, (4) Ownership module, (5) 모든 writer 인증/참조/owner,
(6) real schema/admission2cycle, (7) 전체 회귀, (8) 문서·F gates·Ready PR/CI/squash.
중간 commit은 작게 유지하되 schema만 적용된 checkpoint를 배포/독립 merge하지 않는다.

B의 Todo1–8 후보: (1) A interface/baseline, (2) 오염·경합 계약,
(3) worker reference 검사, (4) pipeline link/실패 전파, (5) real race 검증,
(6) 전체 pipeline2cycle, (7) 전체 회귀, (8) 문서·F gates·Ready PR/CI/squash.

각 Todo는 focused tests → diff/status/staged-path → 명시적 경로만 commit → 안전한 receipt다.
실행용 Goal은 승인 후 각각 하나씩 작성·hash 동결하며 모델 설정을 바꾸었다고 추정하지 않는다.

- F1 Scope: 해당 allowlist/20개 제한, A migration1/B0, backend 제품 owner만 변경.
- F2 Policy: 해당 P matrix 전부 PASS; Master mutation 예외/anonymous fallback 없음.
- F3 Runtime: 실제 독립2cycle + schema/worker 해당 gate, Linux full pytest,
  frontend lint/build/auth/browser 회귀, cleanup 잔여0. 새로운 skip/xfail 금지.
- F4 Evidence/delivery: 문제·관측·해결·실패·수치·남은 위험, current-work/initiative/Issue portfolio,
  최종 head 필수CI3개 성공과 Ready PR squash MERGED 확인. self-review를 독립 reviewer로 포장하지 않는다.

현재 존재하는 검증 명령: backend `AI_PROVIDER=mock python -m pytest -q`, repository root
`python scripts/verify_ownership.py --env-file .env.example --cycles 2`,
`python scripts/verify_schema_migrations.py --env-file .env.example --include-reset`,
`python scripts/verify_auth_sessions.py --env-file .env.example`.
각 command의 실행 횟수/timeout은 frozen Goal에서 확정했다. 최초 설계 단계에는 Docker를
실행하지 않았으며, 승인 후 A 실행 결과는 아래 §8과 Issue105 기록으로 구분한다.

A frozen Goal은 schema verifier2회, auth verifier1회, ownership verifier2cycle로 고정했다.
각각 schema1200s/run, auth900s, ownership900s의 전체 작업 예산과 안전한 owned cleanup을
둔다. 기존 개별 command120/180s 및 ownership360s+cleanup90s 경계를 유지한다.
Todo1–8의 focused command/commit과 F1–F4는 해당 계획이 실행 기준이다.

## 7. 이번 설계의 증거와 남은 결정

- 읽기 전용 코드/호출/fixture/head inventory 및 checkout/merge tree 일치 확인.
- 관련 기존10개 test 파일 **137 PASS**(최종 재실행2.79s), diff/link/예산 문서 검증 PASS.
  후보 경로 A20/B10 모두 중복 없음; 설명되지 않은 missing path0, broken relative link0.
  이는 기존 코드 baseline이며 P01–P16 구현 검증 결과가 아니다.
- 비용 문제 해결: 관리형 Redis 대신 기존 로컬 Redis와 G4.1 test Session 재사용.
- 2026-09-03 사용자 승인: 단일 G4.2 대신 A/B로 분할한다. main 동기화 → A Issue/branch →
  A frozen Goal/hash 준비까지 진행한다. 구현/Goal 실행/DB reset/새 PR은 이번 준비 범위가 아니다.
- read/list/delete/file/ops/cache, 공개 배포·실제 OAuth, 긴급 Session 폐기99는 후속 범위다.

## 8. A 구현 검증과 B 전달 계약

A는 정확히20개 non-document 경로와 신규 migration0003 하나로 구현됐다.
기존0001/0002 bytes는 보존했고 실제 검증은 새 owned local Docker DB에서만 수행했다.
`OwnershipAccess(session, actor)`는 job/enhancement/asset의 owner-scoped SQL과 반환 row
재검증, 동일404, target row lock을 제공한다. `assert_same_owner`는 저장된 두 owner를
비교한다. commit/rollback은 caller 책임이며 Master도 타인 mutation 예외가 없다.
모든 신규 Job/PromptEnhancement는 actor owner를 저장하고 Asset owner는 Job에서 유도한다.

B는 이 interface, head0003, 기존 hash-only authenticated harness를 입력으로 사용한다.
worker handler/polling/pipeline link/race(P11–P15)는 A에서 수정하거나 완료로 주장하지 않았다.
실행 검증 상세·수치·rollback은 [Issue105 기록](../portfolio/issue-105-owner-persistence-admission.md),
안전한 운영 절차는 [local mock](../runbooks/local-mock.md#owner-schema-and-admission-g42a)을 따른다.
