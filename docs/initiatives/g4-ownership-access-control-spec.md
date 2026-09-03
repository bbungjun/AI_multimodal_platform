# G4 — 사용자별 콘텐츠 소유권과 접근 제어

## 상태와 입력

- **Accepted / Planned — 2026-09-03. 사용자 승인 완료; 구현·검증 완료는 아니다.**
- 기준 revision: `100f5e7ae52d0c4273a7556c8a4e3c1fec2d7e4c`,
  [G3.1 PR #102](https://github.com/bbungjun/AI_multimodal_platform/pull/102) squash 병합 확인.
- 상위 합의: [initiative](auth-credits-master-console.md)의 Ownership Invariants,
  Database Strategy, Identity and Session Decisions. 전체 합의를 복제하지 않는다.
- 선행 interface: `app.api.auth_dependencies.require_user`,
  `app.auth.service.AuthenticatedUser`, G3.1 `useSession`과 same-origin cookie 요청.
- 세 slice 분할, Master의 타인 데이터 읽기만 허용, 운영 endpoint Master 제한을 승인했다.
  비용 범위는 로컬 Docker PostgreSQL/Redis와 AI_PROVIDER=mock이며 유료 관리형 서비스는 제외한다.
- G4.1 Tracker: [Issue #103](https://github.com/bbungjun/AI_multimodal_platform/issues/103).
  Branch: `codex/issue-103-authenticated-mock-harness`. 실행은 별도 Goal 요청 후 시작한다.
- Frozen Goal: `.omo/plans/issue-103-g4-1-authenticated-mock-harness-goal.md` (local/untracked).
  SHA-256: `ad8b5899d39b23b1f5ec58467658db5d4c20c91d67ee9ed940473607b3fea718`.
  파일은 PC 간 별도 전달해야 한다. G4.1은 13개 allowlist, migration 0개로 실행한다.

## 1. 해결할 문제와 관측 근거

로그인 화면은 작업 UI를 가리지만 backend 접근 권한을 강제하지 않는다.
현재 코드를 직접 확인한 결과:

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
전역 skip/override로 우회하지 않고 아래 **세 개의 순차 Goal**로 나눈다.

| Slice | 주된 산출물 | 예상 non-document / migration | 단독 완료의 의미 |
|---|---|---|---|
| G4.1 | 인증된 mock 검증 harness와 smoke 운반 방식 | 13 / 0 | 검증 기반 준비; 제품 소유권 보호 아직 없음 |
| G4.2 | non-null owner·생성/재사용/worker 관계 검증 | 20 / 1 | 저장/접수 규칙 구현; 읽기·파일 격리 아직 미완료 |
| G4.3 | 모든 읽기·변경·파일·운영 노출 차단 및 E2E | 20 / 0 | 아래 최종 gate 통과 시에만 G4 Mock Verified |

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
아직 구현되지 않은 실행 산출물이다.

### G4.2 경로 예산 (20)

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

### G4.3 경로 예산 (20)

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

`python scripts/verify_ownership.py --env-file .env.example`는 **G4.1에서 만들 후보 명령**이다.
현재 실행 가능한 도구로 표현하지 않는다. CI의 backend 전체 pytest는 보안 matrix의
mock 계약을 실행하고, real-runtime 2회 receipt는 별도 필수 delivery gate로 남긴다.

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
계획 준비는 구현 실행이 아니다. DB reset·provider/cloud 호출·새 PR은 수행하지 않는다.

포트폴리오 메시지: “로그인 화면을 붙였다”에서 “타 사용자의 UUID·파일 URL·재시도 입력을
알아도 서버가 동일 정책으로 거절하고, 실제 DB/worker 흐름에서 검증했다”로 발전시키는 작업이다.
후자의 문장은 지금은 목표이며, 검증 이후에만 구현 성과로 사용한다.
