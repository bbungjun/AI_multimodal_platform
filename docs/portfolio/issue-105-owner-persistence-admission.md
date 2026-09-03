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
