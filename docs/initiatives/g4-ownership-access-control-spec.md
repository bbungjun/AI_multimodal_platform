# G4 — 사용자별 콘텐츠 소유권과 접근 제어

## 상태와 입력

- **Accepted — G4.1/G4.2A/B and G4.3A Mock Verified; G4.3B Implemented, runtime No-Go; verification redesign approved (2026-09-03).**
  전체 G4 사용자 데이터 격리는 아직 구현·검증 완료가 아니다.
- 기준 revision: `100f5e7ae52d0c4273a7556c8a4e3c1fec2d7e4c`,
  [G3.1 PR #102](https://github.com/bbungjun/AI_multimodal_platform/pull/102) squash 병합 확인.
- 상위 합의: [initiative](auth-credits-master-console.md)의 Ownership Invariants,
  Database Strategy, Identity and Session Decisions. 전체 합의를 복제하지 않는다.
- 선행 interface: `app.api.auth_dependencies.require_user`,
  `app.auth.service.AuthenticatedUser`, G3.1 `useSession`과 same-origin cookie 요청.
- 세 slice 분할, Master의 타인 데이터 읽기만 허용, 운영 endpoint Master 제한을 승인했다.
  비용 범위는 로컬 Docker PostgreSQL/Redis와 AI_PROVIDER=mock이며 유료 관리형 서비스는 제외한다.
- G4.1 Tracker: [Issue #103](https://github.com/bbungjun/AI_multimodal_platform/issues/103).
  Branch: `codex/issue-103-authenticated-mock-harness`. 사용자 Goal 요청으로 구현·격리 검증을 수행했다.
- Frozen Goal: `.omo/plans/issue-103-g4-1-authenticated-mock-harness-goal.md` (local/untracked).
  SHA-256: `ad8b5899d39b23b1f5ec58467658db5d4c20c91d67ee9ed940473607b3fea718`.
  파일은 PC 간 별도 전달해야 한다. G4.1은 13개 allowlist, migration 0개로 실행한다.

## 1. 해결할 문제와 관측 근거

로그인 화면은 작업 UI를 가리지만 backend 접근 권한을 강제하지 않는다.
G4 설계 당시 코드를 직접 확인한 결과(현재 A/B 구현 상태는 상태표와 실행 기록 참조):

| 코드 | 현재 동작 / 누락 |
|---|---|
| `backend/app/models.py` | Job/PromptEnhancement에 owner 없음; Asset은 Job FK만 보유 |
| `backend/app/api/generations.py` | 익명 생성, 전역 목록, UUID 단독 조회·재시도·삭제; enhancement/source 참조에 owner 검사 없음 |
| `backend/app/api/pipelines.py` | parent/child 생성·조회에 인증/소유권 검사 없음 |
| `backend/app/api/prompts.py` | 인증 전에 provider 호출 가능; 결과 owner 없음; 별도 조회/삭제 endpoint는 현재 없음 |
| `backend/app/api/files.py` | DB 조회 없이 storage path로 파일을 열고 Range 응답 |
| `backend/app/api/assets.py` | Asset UUID만으로 metadata 조회 |
| `backend/app/api/ops.py` | 전역 작업 수·실패 Job ID·오류를 익명 반환 |
| `backend/app/api/metrics.py` | 익명 Prometheus scrape; 사용자 인증 도입 시 수집 계약 검토 필요 |
| `backend/tests/test_storage.py` | DB에 등록하지 않은 파일도 HTTP로 다운로드하는 테스트 존재 |
| `scripts/smoke_mock_*.py` | 익명 HTTP; 일부 race 요청은 공통 client를 통하지 않음 |
| schema/auth verification scripts | G2 revision을 head로 고정한 검증 존재 |

성공 기준은 UUID를 숨기는 것이 아니라 요청마다 actor, 대상, 동작을 확인하는 것이다.
최종 생성 prompt payload, outbox/state machine, storage helper는 기존 계약을 유지한다.

## 2. 최종 권한 계약 — 확정

`Content Owner`는 User이며 role/plan/email/browser state에서 소유자를 추정하지 않는다.

| 요청 | 익명/유효하지 않은 Session | 일반 User | Master |
|---|---|---|---|
| 생성·enhance·pipeline 생성 | 거절 | 자신의 owner로 생성 | 자신의 owner로 생성 |
| 기본 작업 목록 | 거절 | 자기 작업 | 자기 작업 |
| `GET /api/generations?scope=all` | 거절 | 403 | 전체 조회 |
| Job/pipeline/Asset/file 단건 읽기 | 거절 | 자신의 대상만 | 운영 목적으로 전체 읽기 |
| retry/delete | 거절 | 자신의 대상만 | 자신의 대상만 |
| enhancement/source Asset 재사용 | 거절 | 자신의 대상만 | 자신의 대상만 |
| `/api/ops/health`, `/api/ops/metrics`, `/metrics` | 거절 | 403 | 조회 가능 |
| `/api/health`, `/api/health/live`, 기존 OAuth endpoints | 기존 계약 유지 | 기존 계약 유지 | 기존 계약 유지 |

- 다른 사용자의 객체와 존재하지 않는 객체는 **같은 404와 같은 detail**.
  조회 가능하다는 이유만으로 Master가 남의 비용을 발생시키거나 데이터를 지우지 않는다.
- 전체 조회는 명시적 `scope=all`에서만 사용한다. `scope` 기본값 `mine`, 나머지 값 422.
  이 query는 목록에만 추가하며 공개 owner 전환·양도·impersonation endpoint는 만들지 않는다.
- 생성 입력의 `owner_user_id`, `user_id`, `role` 등을 신뢰하지 않는다.
  관련 create request model은 `extra='forbid'`로 미정의 필드를 422 거절하는 안을 적용한다.
  기존 frontend payload와 호환되는지 fixture로 확인한다.
- 객체 UUID가 잘못된 형식이면 기존 FastAPI 422 허용. 위 404 계약은 올바른 형식 UUID 대상이다.
- 보안 순서: Session/Origin → scoped 대상 조회 → mode/state/Range 검증 → side effect.
  G3 `require_user`는 mutation의 Origin을 먼저 검사하므로 Origin이 없거나 신뢰되지 않으면
  익명이어도 403이 먼저 나올 수 있다. 이를 임의로 401로 바꾸지 않는다.
- Session 없음/만료/폐기/정지는 G3의 401 계약, 인증 저장소 장애는 기존 503 계약을 유지한다.
  403/404를 frontend 전체 logout 신호로 바꾸지 않는다.
- 성공 및 거절을 포함한 보호된 응답에 `Cache-Control: private, no-store`를 설정한다.
  JSON뿐 아니라 `/files`의 200/206/4xx도 포함한다. Cookie를 cache key로만 쓰는 설계는 제외한다.
- `/metrics`를 Master로 제한하면 기존 무인 scrape는 동작하지 않는다. 이를 숨기지 않는다.
  G4는 cloud/scraper 설정을 변경하지 않으며, 서비스 전용 인증 또는 비공개 수집 경로를
  별도 승인·검증하기 전 운영 관측성 복구/공개 배포를 완료했다고 표시하지 않는다.
- Master 승격 CLI·대시보드·타인 데이터 변경·Audit는 G10이다. 테스트 role 설정은 제품 기능이 아니다.

## 3. 데이터 계약과 migration

G4 전체에서 migration은 **정확히 한 개**, G4.2에서만 추가한다.
후보 revision `0003_content_ownership` → `0002_user_session_persistence`.

| 대상 | 변경 |
|---|---|
| Job | `owner_user_id UUID NOT NULL`, User FK `ON DELETE RESTRICT`, `(owner_user_id, created_at, id)` index |
| PromptEnhancement | 동일 non-null owner FK 및 owner/created_at/id index |
| Asset | owner 복제 없음. `Asset.job_id → Job.owner_user_id`; `local_path` unique 제약 |
| OutboxEvent | 내부 데이터 유지. Session/owner/credential payload 추가 없음 |

- owner의 server/database 기본값 없음. 익명·임시 Master·sentinel User로 채우지 않는다.
- 신규 작업, pipeline의 두 Job, retry는 요청 actor를 owner로 확정한다.
  retry는 먼저 자신의 원본인지 확인하므로 원본 owner와 요청 actor가 일치한다.
- owner는 제품 interface에서 변경 불가. User 삭제 기능은 없고 FK가 실수로 발생하는
  User 삭제를 막는다. 데이터 이관/backfill/ownership transfer는 범위 밖이다.
- migration은 generation 관련 테이블 `jobs/assets/prompt_enhancements/outbox_events`가
  비어 있음을 DDL 전에 검사하고, 하나라도 남으면 안전한 고정 코드로 거절한다.
  User/Session만 존재하는 DB는 해당 FK를 보존하면서 적용할 수 있다.
- migration 자체에 DELETE/TRUNCATE/DROP DATABASE, owner 자동 할당을 넣지 않는다.
  기존 데이터 폐기는 G1의 explicit guarded reset으로만 수행하며 대상 환경을 확인한다.
  이번 설계 요청은 현재 개발 DB나 preview DB reset 실행 승인이 아니다.
- downgrade는 owner 보호가 사라지는 위험 동작이다. generation 데이터가 있으면 거절하고
  빈 격리 DB에서만 downgrade/re-upgrade를 검증한다. 실제 rollback은 서비스 중단과
  이전 코드/schema 조합 점검이 필요하며 보안 검사를 끄는 toggle을 만들지 않는다.
- parent/child/enhancement/source/retry의 동일 owner는 이번에는 application module에서
  검사한다. 모든 교차 참조를 DB composite FK/trigger로 강제했다고 주장하지 않는다.
  직접 DB 조작은 신뢰된 운영 경로이며, 잘못된 링크를 읽거나 worker가 사용할 때도 방어한다.
- 기존 SET NULL/CASCADE 참조 의미, active I2V unique index, state enum은 유지한다.

## 4. Ownership module과 interface

후보 파일: `backend/app/ownership.py`.
actor는 HTTP가 G3에서 인증한 `AuthenticatedUser`; SQLAlchemy session은 호출자가 제공한다.
worker는 브라우저 Session을 전달받지 않고 저장된 Job과 참조의 owner 일치 여부를 검증한다.

작은 public interface의 초안:

```python
access = OwnershipAccess(session, actor)
access.jobs_statement(scope="mine")
await access.job(job_id, intent="read" | "mutate", lock=False)
await access.enhancement(enhancement_id, intent="use")
await access.asset(asset_id, intent="read" | "use", lock=False)
await access.file_asset(local_path)
assert_same_owner(job, related_job_or_enhancement)
```

- 목록은 SQL에서 owner predicate를 적용한 뒤 filter/order/limit/offset 처리한다.
  전체 조회 후 Python으로 필터링하지 않는다. 정렬은 `created_at DESC, id DESC`로 안정화한다.
- 읽기의 Master 예외와 변경/재사용의 자기 owner 조건을 분리한다. intent를 bool `is_admin`
  또는 전역 `bypass`로 표현하지 않는다. 미지원 intent/scope는 fail closed.
- Asset은 Job과 join해 검사한다. child, provenance, retry 관련 링크를 통해 다른 owner의
  객체를 serialize하지 않는다. eager-loaded asset도 그 Job에 속하는지 확인한다.
- module은 commit/rollback, provider 호출, 파일 읽기/삭제를 하지 않는다.
  필요한 row lock을 기존 트랜잭션 안에서 획득하도록 조회를 제공한다.
- 기존 in-memory 테스트용 session과 실제 Postgres를 같은 interface에서 검증한다.
  fake가 SQL predicate를 무시하는 경우 integration test가 반드시 잡아야 한다.
  임의 repository framework나 범용 ACL 엔진/RLS는 추가하지 않는다.

## 5. 요청·worker별 상세 처리

### 생성과 prompt provenance

인증/Origin 검증이 provider 또는 enqueue보다 먼저다. `enhancement_id`가 있으면
자신의 결과를 확인한 다음 target mode/model을 검증한다. 타인/없는 결과 모두 404,
자기 결과지만 mode/model 불일치면 기존 400을 유지한다. 최종 prompt는 사용자 payload다.
새 PromptEnhancement 조회/수정/삭제 endpoint를 추가하지 않는다.

### I2V, pipeline, retry

- source Asset 사용 권한을 잠금 조회로 확인한 후 image-kind·중복 검사를 수행한다.
  타인 source는 404이며 409 중복 여부나 MIME 등 메타데이터를 먼저 노출하지 않는다.
- pipeline parent/child는 같은 트랜잭션에서 같은 owner를 받는다.
- `pipeline_link`는 parent/child/선택 Asset의 Job 일치를 확인한 뒤만 source를 연결하고
  outbox를 생성한다. 불일치는 safe error로 fail closed하며 state 변경은 transition을 사용한다.
- retry는 자신의 failed Job만 허용한다. 참조 source/enhancement/parent가 남아 있으면
  owner 관계를 재검증한다. 정상적인 SET NULL은 기존 동작을 유지한다.
- create와 retry 모두 동일 Asset row lock 및 기존 active-I2V unique 충돌을 409로 처리한다.
  여러 동시 요청에서 500/중복 outbox가 생기지 않는지 Postgres에서 확인한다.
- Session이 만료돼도 이미 접수된 worker Job의 owner는 바뀌지 않는다.
  G10의 정지·취소 lifecycle이나 Credit settlement를 이번 worker 수정에 섞지 않는다.

### 삭제

자기 Job 확인 → terminal/active dependent 정책 확인 → 관련 owner 일치 검증 →
storage 삭제와 기존 DB 정리 순서다. 타인 target은 조회 직후 404이며 storage 호출은 0회.
이상한 cross-owner 참조가 발견되면 수정/삭제 없이 고정 409 오류로 중단한다.
기존 파일 삭제 후 DB commit 실패의 비원자성은 남은 위험으로 기록한다. 범용 파일 복구
시스템을 추가하거나 해결한 것처럼 주장하지 않는다.

### 파일과 cache

`/files/{local_path:path}` 형식과 AssetResponse.url을 유지한다. 경로는 DB의 유일한
`Asset.local_path`와 **정확히 일치**해야 한다. owner 디렉터리 prefix나 UUID만으로 허용하지 않는다.
인증 → Asset/Job owner 검사 → storage.resolve_asset_path → stat/open → Range 순서.
DB 없는 고아 파일은 Master라도 404. traversal/인코딩 변형은 유효 경로로 임의 보정하지 않는다.

정상 사용자 200/206와 기존 400/416 계약을 유지한다. 비권한 사용자의 잘못된 Range도
404이며 파일 크기 `Content-Range`는 반환하지 않는다. 자동 HEAD route는 추가하지 않는다.
현재 등록되지 않은 HEAD는 405일 수 있으나 파일 정보/bytes를 노출하면 안 된다.
각 새 Range 요청에서 Session을 확인한다. 이미 송신을 시작한 stream의 바이트를
로그아웃과 동시에 회수하는 기능은 아니며 사용자 기기에 저장된 파일도 회수할 수 없다.

## 6. Context 크기에 맞춘 실행 분할 — 승인 완료

단일 G4는 production, 기존 endpoint/파일 테스트, migration verifier, mock scripts까지
**20개 이상**의 non-document 경로에 영향을 준다. 파일 수를 숨기거나 인증 테스트를
전역 skip/override로 우회하지 않는다. 최초 세 단계 중 G4.2를 A/B로 나누는
추가 승인과 G4.3A/B 분할을 반영해 **다섯 개의 순차 Goal**로 실행한다.

| Slice | 주된 산출물 | 예상 non-document / migration | 단독 완료의 의미 |
|---|---|---|---|
| G4.1 | 인증된 mock 검증 harness와 smoke 운반 방식 | 13 / 0 | 검증 기반 준비; 제품 소유권 보호 아직 없음 |
| G4.2A | non-null owner·모든 writer 인증·접수 참조 검증 | 20 / 1 | Ownership Admission Mock Verified까지만; worker/전체 격리 미완료 |
| G4.2B | worker/polling 참조·pipeline 연결·실경합 검증 | 구현11, 최대20 / 0 | [Issue107 기록](../portfolio/issue-107-worker-ownership-invariants.md): ff808b0, 실제2cycle/전체 회귀 PASS; delivery는 기록의 PR 참조. 읽기·파일 격리는 G4.3 |
| G4.3 | 모든 읽기·변경·파일·운영 노출 차단 및 E2E | 합집합23 / 0 | 단일20개 예상 폐기; A/B 분할 승인. A16/B16 고정. 최종 gate 통과 시에만 G4 Mock Verified |

**G4.1/2는 비공개 mock 개발 체크포인트**다. 각각 PR/CI를 통과하더라도 사용자별 격리나
공개 배포 완료가 아니다. 공개 노출은 G4.3 및 기존 #99/live 환경 gate 전까지 No-Go.
각 slice 시작 시 이전 PR merge SHA와 실제 경로 수를 재확인한다. 21번째 경로가 필요하면
중단·재설계한다. 이 예상표 자체가 20개 초과 예외 승인은 아니다.
G4.1 전용 frozen Goal은 더 좁은 13개 allowlist를 hard limit으로 사용한다.

### G4.1 경로 예산 (13)

```text
scripts/mock_auth_support.py (new)
scripts/verify_ownership.py (new)
scripts/smoke_mock_golden_path.py
scripts/smoke_mock_retry_flow.py
scripts/smoke_mock_i2v_duplicate_guard.py
backend/tests/ownership_support.py (new)
backend/tests/test_mock_auth_support.py (new)
backend/tests/test_verify_ownership_script.py (new)
backend/tests/test_smoke_mock_golden_path_script.py
backend/tests/test_smoke_mock_retry_script.py
backend/tests/test_smoke_mock_i2v_duplicate_script.py
.github/workflows/smoke-mock-golden-path.yml
backend/tests/test_mock_smoke_workflow.py
```

테스트 전용 User A/B/Master 및 만료/폐기 fixture를 제공한다. 실제 Google 이메일 여러 개가
필요하지 않다. `Synthetic User`를 로그인시키지 않고 fake identity로 만든 test OAuth User를
격리 DB에서만 쓴다. 제품 login route, fixture query parameter, auth bypass env는 금지한다.

runner가 새 무작위 Compose project/DB를 소유하고 mock/local, loopback 주소, resource label,
기존 resource 없음 조건을 검사한다. Session secret은 프로세스 메모리에서 생성하고 hash만
DB에 저장한다. DB 초기화 명령으로 전달할 것은 hash이며 raw secret을 CLI/env/file/stdout에
싣지 않는다. Cookie/Origin은 메모리의 HTTP client에만 주입한다. 예외 repr도 redaction한다.
일반 개발 DB에 임의 User/Session을 seed하는 helper를 제공하지 않는다.

세 smoke의 일반 요청, race 요청, poll, Range, cleanup 모두 동일 인증 운반을 사용한다.
리다이렉트는 자동으로 따라가지 않고, base URL 및 응답 Asset URL은 동일 loopback origin과
허용 경로를 검사한 뒤 요청한다. 인증 cookie를 외부 URL로 보낼 수 없어야 한다.
현 G3의 실제 `require_user`로 `/me`, logout, 만료·폐기를 검증하고 기존 golden을 통과시킨다.
helper test만 통과한 것을 G4 ownership E2E로 기록하지 않는다.

workflow는 해당 guarded runner를 호출하고 실패 시 raw Compose/auth/SQL 로그를 출력하지 않는다.
항상 자신의 project만 정리한다. 폐기된 기존 smoke 명령은 문서에서 새 명령으로 교체하며
보호 활성화 후 익명 fallback을 남기지 않는다. G4.1 frozen Goal에서 canonical CLI를
`python scripts/verify_ownership.py --env-file .env.example --cycles 2`로 고정했다.
G4.1에서 구현·검증을 완료했으며 PR104로 병합됐다.

### G4.2 경로 예산 (20)

아래는 최초 승인 당시 **예상표**이며 실행 allowlist가 아니다. G4.1 병합 후 재조사에서
harness head, identity metadata test, 직접 worker와 runtime 검증 경로 누락을 확인했다.
[G4.2 상세 설계](g4-2-owner-persistence-admission-spec.md)의 A/B 분할을 승인했다.
아래 단일 Goal 예상표는 대체되었으며 실행하지 않는다. A는 상세 spec A5의20개만
허용하고 [Issue #105](https://github.com/bbungjun/AI_multimodal_platform/issues/105)로 준비했다.
제품 권한 계약은 변경하지 않으며 구현은 별도 Goal 요청 후 시작한다.

```text
backend/app/models.py
backend/migrations/versions/0003_content_ownership.py (new)
backend/app/ownership.py (new)
backend/app/schemas.py
backend/app/api/generations.py
backend/app/api/pipelines.py
backend/app/api/prompts.py
backend/app/services/jobs/pipeline_link.py
backend/tests/test_generation_api.py
backend/tests/test_pipeline_api.py
backend/tests/test_prompt_api.py
backend/tests/test_model_relationships.py
backend/tests/test_pipeline_link.py
backend/tests/test_alembic_schema.py
backend/tests/test_ownership_persistence.py (new)
backend/tests/ownership_support.py
scripts/verify_schema_migrations.py
backend/tests/test_verify_schema_migrations_script.py
scripts/verify_auth_sessions.py
backend/tests/test_verify_auth_sessions_script.py
```

기존 historical G1/G2 revision 테스트를 지우지 않고 current-head 검증만 정확히 확장한다.
schema verifier의 raw SQL fixture에도 유효 owner를 넣는다. 두 격리 cycle에서 empty upgrade,
nonempty refusal/rollback, FK/non-null/index, downgrade/re-upgrade, guarded reset과 복구를 검증한다.
create/retry/pipeline/enhance의 authenticated fixture 전환과 owner assertion은 각 기존 test 파일에
명시한다. 전역 autouse Master override는 금지한다. 비동기 worker가 owner를 임의로
보정하거나 로그인 actor 대신 시스템 User를 넣지 않게 검사한다.

### G4.3 이전 경로 예상 (20, 실행 금지)

main `c84394a`에서 재검토한 결과 아래 예상에는 `scripts/mock_auth_support.py`와
`backend/tests/test_mock_auth_support.py`가 빠져 있었다. 기존 client는 query string,
JSON 배열, `/metrics`를 거절하므로 목록·scope·운영 endpoint 실검증에 두 경로가 필요하다.
합집합22개를 단일 Goal로 실행하지 않는다. 이 목록은 과거 추정이며 allowlist가 아니다.

```text
backend/app/ownership.py
backend/app/api/generations.py
backend/app/api/pipelines.py
backend/app/api/assets.py
backend/app/api/files.py
backend/app/api/ops.py
backend/app/api/metrics.py
backend/app/api/auth_dependencies.py
backend/app/main.py
backend/tests/test_generation_api.py
backend/tests/test_pipeline_api.py
backend/tests/test_asset_api.py
backend/tests/test_storage.py
backend/tests/test_ops_api.py
backend/tests/test_ops_runtime.py
backend/tests/test_ownership_access.py (new)
backend/tests/test_ownership_integration.py (new)
backend/tests/ownership_support.py
scripts/verify_ownership.py
backend/tests/test_verify_ownership_script.py
```

전 HTTP 노출면에 정책을 연결한다. main 변경이 필요하면 보호 응답 cache header 적용에만
제한한다. 이 slice는 migration/새 permission model/frontend redesign을 추가하지 않는다.
구현 중 테스트 fake/query 전환이 예산보다 커지면 뒤늦게 파일을 합치지 말고 재분할한다.

### G4.3A/B 분할 — 승인 완료, A 병합/B 실행 준비

[설계 Issue #109](https://github.com/bbungjun/AI_multimodal_platform/issues/109)는 aggregate
설계/종료 추적용이다. 사용자가 A/B 분할과 A 실행 준비를 승인했다.
[A Issue #110](https://github.com/bbungjun/AI_multimodal_platform/issues/110), branch
`codex/issue-110-metadata-ownership-access`, main `c84394a` 기반으로 준비했다.
Goal은 `.omo/plans/issue-110-g4-3a-metadata-ownership-access-goal.md`이며 SHA는 current-work에
기록한다. 사용자의 frozen-SHA 요청으로 A 구현·실제 검증·병합을 완료했다. B는 아래 Issue112에서 확정했다.
제품 권한 정책은 바꾸지 않으며 migration은 두 단계 모두0이다.

| Slice | 책임 | 종료 의미 |
|---|---|---|
| G4.3A | 목록·상세·삭제, JSON cache 경계, harness 호환성 | metadata 접근 제어만 검증; 파일·ops는 아직 미보호, 공개 배포 금지 |
| G4.3B | 파일·Range, Master ops, 최종 전체 보안 검증 | 아래 전체 matrix와 v2 ownership2+file-ops2/CI/merge를 닫은 뒤 G4 Mock Verified |

#### A 실행 경로 (16)

```text
backend/app/ownership.py
backend/app/api/generations.py
backend/app/api/pipelines.py
backend/app/api/assets.py
backend/app/main.py
backend/tests/test_generation_api.py
backend/tests/test_pipeline_api.py
backend/tests/test_asset_api.py
backend/tests/test_ownership_access.py
backend/tests/test_ownership_integration.py
backend/tests/test_ownership_persistence.py
backend/tests/ownership_support.py
scripts/verify_ownership.py
scripts/mock_auth_support.py
backend/tests/test_verify_ownership_script.py
backend/tests/test_mock_auth_support.py
```

#### B 실행 경로 (16, Issue112 고정)

```text
backend/app/ownership.py
backend/app/api/files.py
backend/app/api/ops.py
backend/app/api/metrics.py
backend/app/api/auth_dependencies.py
backend/app/main.py
backend/tests/test_storage.py
backend/tests/test_ops_api.py
backend/tests/test_ops_runtime.py
backend/tests/test_ownership_access.py
backend/tests/test_ownership_integration.py
backend/tests/ownership_support.py
scripts/verify_ownership.py
scripts/mock_auth_support.py
backend/tests/test_verify_ownership_script.py
backend/tests/test_mock_auth_support.py
```

위 B16 경로는 A 병합본에서 모두 존재한다. B에서 새 코드 파일을 추가하지 않는다.
최초 제안은 A15/B16/합집합22였다. A 준비 중 기존 persistence 테스트가 `read`를
미지원 intent로 검사하는 것을 발견했다. `test_ownership_persistence.py`의 해당 테스트만
실제 미지원 intent로 바꿔 보호를 유지하도록 A16으로 확정했다. 합집합23/공통9, 최대20
원칙과 분할 책임은 그대로다. 테스트를 합치거나 생략하지 않는다. A allowlist 밖 코드가
필요하면 최대20 이하여도 먼저 재설계한다. B도 아래 Issue112 계약으로16개를 고정했다.

#### B 실행 준비 — Issue112 (2026-09-03)

- [Issue112](https://github.com/bbungjun/AI_multimodal_platform/issues/112), branch
  `codex/issue-112-file-ops-access`, **In Progress / runtime No-Go**. Todo1–5 구현은
  ebfd530에서 완료했지만 첫 실제 cycle417.17s(cleanup 약54s)에서 work360s 한도에
  도달해 Todo6 중단. 아래 내용은 frozen 설계이며 아직 최종 Mock Verified가 아니다.
- 선행 [PR111](https://github.com/bbungjun/AI_multimodal_platform/pull/111)은 실제 squash
  병합되었다: `cd654e5003e70d78cd7390cc24e98f322a3383fe`. 최종 head5738c0d의 필수
  verify/양쪽 Scan-SBOM SUCCESS. 이 main을 fast-forward한 뒤 B branch를 만들었다.
- [B 준비/실행 기록](../portfolio/issue-112-file-ops-access.md), frozen local Goal
  `.omo/plans/issue-112-g4-3b-file-ops-access-goal.md`와 SHA는 current-work에서 연결한다.
  이후 사용자의 frozen-SHA 실행 요청으로 구현했다. 현재는 시간 한도 중단 조건에 따라
  검증 분할 재설계를 승인받아 아래 v2 계약으로 실행을 준비했다. 아직 v2 구현/실행 전이다.
  [실패/승인 기록](../portfolio/issue-112-file-ops-access.md) 참조.
- B16/migration0, schema0003와 storage helper/worker/metadata writer는 수정하지 않는다.
  최초 후보를 actual merge의 코드/호출자/테스트로 재검토했다. 경로 밖 필요 시 중단한다.

확정할 작은 Interface는 `OwnershipAccess.file_asset(local_path)`와
`require_master(actor=Depends(require_user))`다. 파일 lookup은 정확한 DB path와
Job owner를 SQL에서 확인하고, Master read 외에 mutation 예외를 추가하지 않는다.
`require_master`의 일반 사용자 거절은403 `master_required`;401/503은 require_user 그대로다.

파일 경로는 기존 storage가 생성하는 canonical UUID/filename만 허용한다. raw ASGI path의
percent/encoded slash/dot/중복 separator 변형을 다른 유효 경로로 보정하지 않는다.
DB Asset.job_id와 path의 Job 디렉터리가 불일치하면 Master도404 `content_not_found`.
권한 확정 전 resolve/stat/open/Range parsing0; 권한 확인 후에도 resolved path가 다른
Job/file을 가리키는 기존 in-root symlink alias는 거절한다. storage sandbox를 재사용하며
공격자의 동시 filesystem 교체까지 원자적으로 막았다고 주장하지 않는다.
정상200/206/400/416와 정확한 bytes, 기존 HEAD405를 유지한다. HEAD 기능은 추가하지 않는다.
현재 JSON response-start wrapper를 files/ops/exact metrics로 확장하되 buffering하지 않는다.

최종 실제 proof는 기존 metadata8그룹/348검사와 삭제경합2종 및 이전 proof를 유지하고,
F(files), O(ops), V(revocation), E(A/B end-to-end) 네 그룹을 추가한다. E는 각 사용자마다
enhance/generate/poll/metadata/file/Range/pipeline/retry/delete/cross-user 거절 stage를
별도로 확인한다. V는 기존 logout fixture를 유효할 때 먼저 파일로 검증하고 실제 logout
뒤 동일 client의 새 Range401을 확인한다. Session을 재발급하거나 폐기를 되돌리지 않는다.
기존 A Session 만료 전 A의 모든 권한 필요 stage를 끝낸다.

일반 ScopedClient의 URL guard는 유지한다. 정확한 GET `/metrics`만 좁게 허용하고,
공격 probe/HEAD는 고정 enum과 검증된 fixture ID로만 구성한다. 임의 URL/encoding/header를
허용하는 검증용 탈출구를 만들지 않는다. receipt는 F/O/V/E와 A/B stage가 모두 참일 때만
성공이며 unit fake를 실제 HTTP/DB 증거로 계산하지 않는다.

최초 계획의 검증은 ownership2cycle, 별도 기존 schema verifier2회(`--include-reset`), auth verifier1회,
전체 Linux backend/기존 frontend 회귀다. schema 검증은 새로운 migration이 아니며 모든
reset은 verifier가 만든 새 격리 DB에만 수행한다. 기존360s work+90s cleanup/cycle와 전체900s,
HTTP10s, lock20s/observe5s는 유지한다. A의 약338s 대비 여유가 작으므로 stage 재사용과
최대2개의 독립 actor HTTP 흐름만 병행하고 공유 fixture/worker-stop/expiry는 순차 처리한다.
완전한 proof가 예산에 들어오지 않으면 측정 결과를 보고하고 재설계한다.

#### B 검증 재설계 승인 — v2 (2026-09-03, 실행 전)

최초 한 cycle의 모든 그룹 조건과 전체900s 조건은 다음 분할로 대체한다. 제품 권한과
아래 A1–A24 matrix, schema2/auth1/전체 회귀/CI/merge 조건은 그대로다. 이전 frozen 파일은
변경하지 않으며 `.omo/plans/issue-112-g4-3b-file-ops-access-v2-goal.md`를 새 SHA로 동결한다.

| Suite | 매 fresh cycle 필수 proof | 횟수 |
|---|---|---|
| ownership | auth12/admission111/scenarios3/metadata8·348 이상/delete-race2/execution20/pipeline4/race3/expiry1, 기존 A golden/retry/duplicate 전부 | 2 |
| file-ops | auth12와 F/O/V/E 전부, A/B 각각 enhance/generate/poll/metadata/file/range/pipeline/retry/delete/foreign | 2 |

계획된 CLI는 `--suite all`/`ownership`(기본)/`file-ops`; 기존 `--cycles 2`는 유지한다.
명시적 all에서 ownership2 다음 file-ops2를 순차 실행하고, 네 프로젝트·DB·Redis·identity는
모두 새로 만든다. 하나의 immutable code SHA에서4회 및 cleanup0이 모두 확인되어야
aggregate complete=true다. 개별 suite/1cycle 진단 실행은 전체 완료가 아니다.
현재 코드에는 아직 이 selector/aggregate 계약이 없으므로 새 실행 증거로 해석하지 않는다.
기본 ownership은 기존 수동 smoke CI의20분 한도를 유지하기 위한 호환 선택이다.
그 workflow는 변경/실행하지 않으며, 기본 smoke 성공만으로 B 전체 완료를 주장하지 않는다.

각 cycle work360s+cleanup90s, 각 suite900s를 유지하고4회 전체는 명시적으로1800s다.
HTTP10s, smoke90s, lock20s/observe5s, worker/quota는 그대로다. 기존 suite에 B 추가 E를
겹쳐 넣지 않으며 파일 suite에는 worker-stop/Session expiry를 중복하지 않는다.
계측은 고정 phase와 유한한 elapsed time, 고정 error enum만 남기고 raw exception/로그는
출력하지 않는다. 누락 그룹·잘못된 count·서로 다른 SHA·재사용 project·cleanup 실패는
aggregate 거절이다. timeout 초과는 계속 No-Go이며 측정 근거와 재설계를 보고한다.

새 구현 변경은 기존 verifier/support/guarded fixture/tests5개에 한정한다. 누적16코드
경로/migration0, 기존 제품 구현과 최초 실패 증거를 보존한다. Todo1–8/F1–F4는 v2에서
재개용 순서로 고정하며, 아래 역사적2cycle 표기는 B 종료 시 두 suite 각각2회로 읽는다.

Todo1–8/F1–F4와 정확한 test/CLI는 frozen Goal에 고정한다. Ready PR 최종 head 필수3개 CI
성공과 실제 squash merge 후에만 B 및 aggregate G4 Mock Verified로 종료할 수 있다.
parent109는 그때 전체 matrix 근거와 함께 닫는다. #99/live/proxy/machine-scraper gate는
그대로 열려 있으며 무인 `/metrics`가401로 바뀌는 영향을 숨기지 않는다.

#### A Interface와 실패 계약

- 기존 `OwnershipAccess(session, actor)`를 확장한다. `job`/`asset`의 read와
  owner-only mutate/use를 구분하고 목록용 scoped statement를 제공한다. Master read
  예외가 mutate/use로 전파되지 않게 한다. Ownership Module 내부에서 commit, storage,
  provider 호출을 하지 않는다. worker validator의 계약은 그대로 유지한다.
- 목록은 SQL에서 owner/scope → 기존 filters → `created_at DESC, id DESC` →
  limit/offset을 적용한다. 기본 mine, Master만 all, 일반 all403, 그 외 scope422.
  Python 사후 필터로 pagination을 맞추지 않는다. 기존 최대100 제한을 유지한다.
- read는 기존 serializer 전에 알려진 Job/Asset/parent/retry/source/enhancement
  관계의 owner 정합성을 확인한다. 목록은 일괄 조회로 page 길이에 비례하는 N+1을
  피한다. pipeline은 parent 권한을 먼저 확인한 뒤 same-owner child를 읽는다.
  타인/없는 객체는 동일404 `content_not_found`; Master read도 구조적으로 잘못된
  cross-owner 참조는 노출하지 않는다. 정상 blocked I2V의 null source와 SET NULL
  이력은 허용한다. worker 실행 조건을 read 조건으로 그대로 재사용하지 않는다.
- 임의 JSON 전체나 과거 prompt snapshot을 재귀 탐색하는 범용 sanitizer는 추가하지
  않는다. 알려진 참조와 반환 Asset graph를 검증하는 범위를 A 계획에 명시한다.
- delete는 먼저 own target을 확인한다. cross-owner dependent가 있으면 고정409,
  detach/delete/storage 부수효과0으로 거절한다. 정상 active dependent409는 유지한다.
  lock 순서는 출력 Asset을 id 순으로 잠근 뒤 Job을 잠그고 상태·참조를 fresh
  조회하는 것이다. 기존 create/retry의 Asset → parent FK 순서와 역전되지 않게
  실제 PostgreSQL 동시 요청으로 검증한다. own target → lock/fresh → terminal 확인 →
  모든 incoming reference owner 확인 → active dependent 확인 → storage/detach/delete 순서다.
  cross-owner incoming reference는 `409 ownership_reference_mismatch`로 통일한다.
- 기존 파일 삭제 후 DB commit의 비원자성은 남는 위험으로 기록한다. 새 복구 store,
  saga, DB schema를 이 단계에 추가하지 않는다. foreign target404는 상태 정보보다 앞선다.
- 보호 응답에 `Cache-Control: private, no-store`를 붙인다. JSON 성공/오류와 B의
  streaming/Range/HEAD 거절까지 재사용 가능한 response header 경계를 main에 한정한다.
  unhandled500도 포함하는지 테스트하며, body buffering이나 예외 삼키기를 도입하지 않는다.
  auth/health의 기존 계약, Origin 우선403, Session401/저장소 장애503을 바꾸지 않는다.

#### B Interface와 실패 계약

- 정확한 `Asset.local_path` + Job owner DB 조회가 resolve/stat/open/Range보다 먼저다.
  고아 파일은 Master도404/storage0. 타인 파일과 잘못된 Range의 조합도404이며
  Content-Range/size/bytes가 없어야 한다. 본인200/206/400/416 계약은 유지한다.
- `/api/ops/health`, `/api/ops/metrics`, `/metrics`에 좁은 `require_master` dependency를
  적용한다. collector/render 전에 Master200, User403, 익명/invalid401을 판정한다.
  기존 public health/auth는 그대로다. machine scraper bypass나 cloud 설정 변경은 금지한다.
- HEAD는 새 기능으로 추가하지 않는다. 기존405를 포함한 오류에 파일 metadata가
  없어야 한다. Session 폐기 후 새 Range는401; 이미 보낸 bytes 회수는 주장하지 않는다.

#### Harness와 검증 분담

- query는 raw URL 허용이 아니라 목록 GET의 제한된 key/value를 받는 구조화된
  Interface로 추가한다. 배열 응답은 명시적 타입 검증을 거친다. B에서 정확한 GET
  `/metrics`만 허용한다. same-origin/loopback/no-redirect/secret-in-memory guard 유지.
  traversal 공격 probe가 필요해도 임의 URL/percent 인코딩 전역 허용으로 바꾸지 않는다.
- 현재 B execution proof는 A Session 만료 후 A Job도 B client로 poll한다. A 적용 후
  올바르게404가 되므로 해당 한 Job은 Master의 허용된 read로 관찰하고 B Job은 B로
  유지한다. Session 재발급, anonymous fallback, 인증 dependency override는 금지한다.
- A는 A1–A13/A23/A24의 관련 read/delete 부분 및 JSON A19를 검증한다. 기존 admission,
  worker, pipeline, race, expiry proof를 보존하고 두 fresh project에서 metadata 보안을
  실제 HTTP+Postgres로 확인한다. file/ops는 A의 보안 성공으로 계산하지 않는다.
- B는 전체 A1–A24와 A/B 각각 enhance→generate→poll→metadata→file/Range,
  pipeline/retry/delete/cross-user 거절을 2cycle 검증한다. A21/A22의 기존 schema
  증거와 새 head 회귀를 구별하고 G4.3 migration을 추가하지 않는다.
- 각 cycle 기존 work360s + cleanup90s, 전체900s, HTTP10s, lock holder20s/observe5s를
  유지한다. B 선행 cycle 약275s 대비 추가 proof의 예산을 설계한다. 초과하면 fixture와
  책임을 재검토하고 보고한다. timeout/limit/검증 guard를 몰래 완화하지 않는다.
- FK를 깨는 가짜 실제 fixture나 SQLite로 보안 증거를 대체하지 않는다. 통합 검증은
  실제 Session을 사용하고, unit fake는 명시적 일반 actor를 사용한다. 전역 Master override 금지.

#### A 실행 계획 연결과 B 준비 체크포인트

각 Goal의 Todo 순서는 1 baseline/상태표, 2 Ownership Interface,
3 route 적용, 4 경계·실패 테스트, 5 guarded harness, 6 실제2cycle/전체 회귀,
7 문서·포트폴리오, 8 Ready PR/CI/실제 squash merge로 고정한다. A와 B에서 2–5의
세부 테스트/commit 경로는 각 Issue110/112 frozen Goal에 고정했다. 각 Todo는 focused test,
diff/status/staged 검사 후 작은 commit을 남긴다.

F1 경로/무migration, F2 해당 보안 matrix, F3 실제2cycle/전체 회귀,
F4 문서/최종 head의 verify + 양쪽 Scan/SBOM/실제 MERGED를 모두 APPROVE해야 한다.
A의 APPROVE는 G4 전체 승인이나 공개 배포 허가가 아니다. 검증 우회/관리자 강제 merge 금지.
회귀 명령은 아래7절을 사용하며, 실행 계획 동결 시 실제 CLI/test 존재와 native exit
전파를 확인한다. 초기385 PASS는 기존 코드 baseline이다. A 실제 검증 결과는 아래에 구분한다.

#### A 구현 결과와 B 입력 Interface

Implementation `acb44a9`, [Issue110 실행 기록](../portfolio/issue-110-metadata-ownership-access.md).
16개 코드 경로/migration0, head0003 동일. 실제2cycle337.73/338.12s, 각8개 access group/
348 checks/delete-race2와 기존 proof 유지, cleanup0. Linux928 PASS/3 existing skips,
frontend48+34 PASS. 최종 PR/CI/실제 merge는 실행 기록의 delivery 링크를 확인한다.

- `OwnershipAccess.jobs_statement(scope)` 및 job/asset read, `validate_read_jobs(jobs)`:
  작은 Interface로 목록·상세 권한과 direct reference 검증을 수행한다. Master read와
  owner-only mutate/use는 분리. page1/20/100에서 content SELECT5 실제 측정.
- delete는 Asset id-order lock → fresh Job lock/Asset refresh → terminal → incoming
  owner → active dependent → storage/detach/delete. 실제 delete/create·delete/retry의
  lock 대기를 관측했다. 이전 file-delete/DB-commit 비원자성은 남는다.
- `ContentApplication`/`PrivateContentResponses`는 response-start만 처리하며
  ServerErrorMiddleware 바깥에서 JSON family4개의 no-store를 적용한다. B는 file/ops를
  명시적으로 확장·검증해야 한다. body buffering/예외 삼키기 없음.
- `ScopedClient`는 GET generations의 구조화된 query와 명시적 `expected_type=list`를
  지원한다. `/metrics`는 아직 거절한다. same-origin/no-redirect guard는 유지한다.
- canonical scenario는 `requires_access=True`; access_groups8/access_checks 양수/
  delete_race_checks2와 기존 groups를 검증한다. 고정 access fixture/lock helper만 추가,
  Session fixture9/head0003 유지. 만료A 작업은 Master로 관찰하고 B 작업은 B로 관찰한다.
- 실패한 첫 실행은 Master의 기본 mine을 all로 오해한 probe 문제였다. 해당 요청만
  explicit all로 수정하고 두 cycle을 새로 통과했다. 제품 기본 mine은 변경하지 않았다.

남은 제약: corrupted reference가 포함된 page는 전체404 fail-closed; arbitrary DBA
동시 변경, 파일 원자적 복구, 이미 전송된 bytes 회수는 보장하지 않는다. A만으로 전체
G4/공개 배포를 완료했다고 표시하지 않는다. B16은 실제 A merge 후 Issue112에서 고정했다.

## 7. 필수 검증 matrix

실제 Session+Postgres 검증은 authentication/ownership dependency를 override하지 않는다.
일반 route 회귀용 fake test와 보안 integration test를 명확히 분리한다.

| ID | 사례 | 통과 조건 |
|---|---|---|
| A1 | 익명 GET / 만료·폐기·정지 Session | 보호 route 401; 파일/대상 metadata 없음 |
| A2 | mutation Origin 없음/외부 Origin | 403, provider/enqueue/파일변경 0 |
| A3 | 본인 create/foreign owner payload | owner=actor / 미정의 필드 422 |
| A4 | A/B 목록 교차·filter·pagination | SQL scope 적용; 타인 row 0, page 중복/누락 규칙 검증 |
| A5 | 타인/없는 Job·pipeline·Asset | 동일 404/detail; 연결 객체 정보 없음 |
| A6 | Master 기본 목록 / 전체 목록 / 타인 단건 | mine / all / read 허용; 일반 User scope=all은 403 |
| A7 | Master 타인 retry/delete/source/enhancement | 404, 부수효과 0 |
| A8 | 타인 enhancement와 mode/model 오류 조합 | 404 우선; 자기 결과 mismatch만 400 |
| A9 | 타인 source와 active I2V 조합 | 404 우선; active 상태/파일정보 노출 없음 |
| A10 | 동시 본인 I2V create/retry | 하나만 active; 나머지 409, 중복 outbox/500 없음 |
| A11 | pipeline parent/child 및 worker 연결 | owner 동일, 타 owner 링크 생성/사용 거절 |
| A12 | 자기 failed retry / invalid state | 새 id+같은 owner, 기존 lineage / 409 |
| A13 | 타인 delete / 자기 active dependent | 404·파일 호출 0 / 기존 409 |
| A14 | DB에 없는 고아 파일 | Master 포함 404; 파일 stat/open 0 |
| A15 | 자기 파일·Range·invalid Range | 200/206 및 기존 400/416, 정확한 bytes |
| A16 | 타인 파일 + invalid Range | 항상 404; Content-Range/크기/bytes 없음 |
| A17 | traversal/encoded/중복 경로·DB 참조 혼선 | 접근 거절; storage sandbox 유지; duplicate path DB 거절 |
| A18 | Session 폐기 후 새로운 파일/Range 요청 | 401; 이전 stream 즉시 취소는 주장하지 않음 |
| A19 | 보호된 JSON/file/오류 cache | private,no-store; 계정 간 cache 재사용 경로 없음 |
| A20 | ops health/metrics/Prometheus | Master만 성공; 일반403/익명401; health/auth 계약 유지 |
| A21 | root→head, nonempty upgrade, downgrade→upgrade | 순서/거절/복구 모두 예상대로; owner 기본값/backfill 없음 |
| A22 | NULL/없는 User FK/사용 중 User 삭제 | Postgres가 모두 거절; Asset owner 중복 컬럼 없음 |
| A23 | 위조한 owner/Session/header | DB actor만 신뢰, 다른 User 데이터 노출 0 |
| A24 | failure/cleanup/redirect 증거 안전 | secret/email/prompt/raw response 0; 자기 resource만 정리 |

최종 runtime golden: A와 B 각각 enhance→generate→poll→Asset metadata→file/Range,
cross-user 거절, pipeline 완료, retry, 안전한 삭제까지 실제 DB/Redis/worker로 실행한다.
서로 다른 fresh project에서 **2회** 통과하고 cleanup 잔여 resource 0을 확인한다.
순수 HTTP fixture나 SQLite 검증을 실제 Postgres 결과로 대신하지 않는다.

실행 Goal에서 명령을 고정한다. 지금 존재하는 회귀 명령:

```powershell
# backend에서
$env:AI_PROVIDER = 'mock'
python -m pytest -q
# frontend에서, UI 변경 없이 기존 login 계약 회귀
npm run lint
npm run build
npm run test:auth
npm run test:auth:browser
# repository root에서
docker compose --env-file .env.example config --quiet
git diff --check
git status --short --branch
git diff --cached --name-only
```

`python scripts/verify_ownership.py --env-file .env.example --cycles 2`는 G4.1에서 구현·검증한
명령이다. 기존 smoke CLI는 이를 위임하고 arbitrary base URL/Compose 옵션을 거절한다.
현재 A metadata와 B F/O/V/E 코드는 구현됐지만 B의 합산 runtime은 실패했다. 위 v2 CLI는
계획이며 아직 구현 전이다. [Issue103 기록](../portfolio/issue-103-authenticated-mock-harness.md)에
인증12 × 2, 세 시나리오 × 2, cleanup과 전체 회귀 결과를 구분해 남긴다.

## 8. 종료·중단 조건

각 slice는 focused test → diff/status/staged-path 확인 → 작은 commit 순서로 진행한다.
최종 Goal에는 아래 F1–F4와 ordered Todo를 고정하고 gpt-5.6-sol medium의 새 context에서 실행한다.

- F1 Scope: 각 slice <=20 non-document; G4 총 migration 1; frontend/cloud/Plan/Credit/Audit 변경 0.
- F2 Security: A1–A24 해당 matrix 통과, public route inventory 누락 0,
  allow-all/test bypass 없음, 타인 데이터·파일·부수효과 0.
- F3 Runtime: 최종 전체 pytest/Linux CI, frontend 회귀, real mock runtime 2회,
  migration 거절/복구, golden/cleanup 통과. 기존 Windows Bash 경로 실패는 baseline 근거와
  Linux 전체 성공으로 별도 기록하며 신규 실패를 그 예외에 섞지 않는다.
- F4 Evidence: current-work/initiative/Issue portfolio 최신화, 명령·count·실패 원인·남은 위험 기록,
  민감정보 없는 receipt, Ready PR의 최종 head 필수 CI 3개 성공과 squash auto-merge 확인.
- G4 전체 Mock Verified는 **G4.3까지 모두 닫힌 뒤**만 가능하다. 실제 OAuth/cloud Live Verified 아님.
- 새 제품 권한 정책, 21번째 경로, 추가 migration, 새 store/ACL framework,
  개발 DB 초기화 필요, 외부 provider 호출 필요가 생기면 구현 중단 후 보고한다.

## 9. 실행 준비와 포트폴리오

설계/분할 승인을 반영하고 G4.1 Issue #103과 main `100f5e7` 기반 branch를 만들었다.
G4.1 전용 Todo 1–8, F1–F4, 로컬 격리 검증 2회와 Ready PR/CI/squash auto-merge를 고정한다.
G4.1 구현은 frozen Goal 범위에서 완료했고 test-only harness만 Mock Verified다.
DB reset·새 migration·실제 OAuth/provider/cloud 호출은 수행하지 않았다.

G4.2 입력 interface: `MemoryIdentity`, `ScopedClient`, `OwnedRuntime`과
`verify_ownership.py --cycles 2`; scenario는 `run_smoke(args, client=...)`를 받는다.
서버가 검증한 A/B/Master 및 인증 거절 fixture를 후속 owner/reference 검사에 재사용한다.
G4.2A에서 schema/auth/harness/seeder head를 `0003_content_ownership`로 함께 갱신했다.
신규 owner와 접수 단계 참조 검증은 [Issue105 실행 기록](../portfolio/issue-105-owner-persistence-admission.md)
범위까지 Mock Verified다. B는 `OwnershipAccess(session, actor)`와 `assert_same_owner`,
저장된 owner 및 기존 authenticated harness를 이어받았다. B worker 강화는
[PR108](https://github.com/bbungjun/AI_multimodal_platform/pull/108)에서 실제 병합되었다
(`c84394a`). 상세 B5 handoff와 [Issue107 실행 기록](../portfolio/issue-107-worker-ownership-invariants.md)을
G4.3 입력으로 사용한다. B는11개 경로/migration0, 실제2cycle과 전체 회귀를 검증했다.
G4.3 설계 준비는 [Issue109 기록](../portfolio/issue-109-ownership-access-design.md)에 남긴다.
분할 승인을 반영한 [Issue110 준비 기록](../portfolio/issue-110-metadata-ownership-access.md)과
frozen Goal을 실행해 A metadata 구현·격리 검증을 완료했다. 파일/Range/ops는 B에 남으며 개발/preview DB는 보존했다.

포트폴리오 메시지: “로그인 화면을 붙였다”에서 “타 사용자의 UUID·파일 URL·재시도 입력을
알아도 서버가 동일 정책으로 거절하고, 실제 DB/worker 흐름에서 검증했다”로 발전시키는 작업이다.
후자의 문장은 지금은 목표이며, 검증 이후에만 구현 성과로 사용한다.
