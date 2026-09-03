# G4 설계 기록 — 로그인에서 사용자 데이터 격리로

- 상태: **G4 정책과 G4.2A/B 분할 Accepted / A Goal Prepared**, 2026-09-03.
  G4.1은 [PR104](https://github.com/bbungjun/AI_multimodal_platform/pull/104)로 병합됐다.
  아래 최초 설계 당시 기록과 [G4.1 구현 증거](issue-103-authenticated-mock-harness.md)를 구분한다.
- 기준: `100f5e7` (G3.1 PR #102 병합), [설계 초안](../initiatives/g4-ownership-access-control-spec.md).
- 이 문서는 설계 판단 기록이다. runtime 검증이나 이미 구현한 접근 제어의 증거가 아니다.

## 배경과 문제

로그인 frontend를 확인한 뒤, 실제 사용자별 소유권과 접근 제어 설계를 요청받았다.
작업 화면이 잠겨도 backend UUID/파일 URL을 직접 호출하면 타인의 데이터를 읽거나
변경할 수 있으므로 frontend 인증 상태만으로는 멀티유저 제품이 되지 않는다.

## 관측과 원인 분석

Job/PromptEnhancement에 owner가 없고, generation/pipeline/asset은 UUID 또는 전역 SQL로
조회한다. 파일 route는 DB에 등록된 Asset인지 확인하지 않고 storage를 연다.
운영 endpoint도 전역 Job ID와 실패 정보를 반환한다. 기존 smoke와 일부 race 요청은
인증 cookie/Origin 운반이 없으며, schema/auth verifier는 G2 head를 고정하고 있다.

따라서 컬럼 추가만으로 해결되지 않고 요청·참조·worker·파일·검증 도구를 함께 바꿔야 한다.
단일 Goal에서 이를 처리하면 기존 20-path 제한을 넘는다. 파일 수를 줄이려고 기존 테스트를
전역 Master로 실행하거나 검사 자체를 생략하는 접근은 제외했다.

## 해결 방향과 대안

`codebase-design` 원칙을 적용해 actor와 SQL session을 받는 하나의 Ownership module로
조회/재사용/변경 의도를 집중시킨다. `domain-modeling` 원칙으로 Content Owner를
운영 목적으로 조회하는 Master와 구분해 glossary에 기록했다.

제안은 검증 harness → owner 저장/접수 → 전체 접근 강제의 세 Goal이다.
첫 두 단계는 공개 배포 가능한 결과가 아니라 비공개 mock 체크포인트로 명시한다.
일반 User는 자기 데이터만, Master는 타인 읽기만 허용한다. 파일은 DB 소유권 확인 후
storage를 사용하며, 없는 대상과 타인의 대상은 동일한 404로 처리한다.

대안으로 일괄 구현, RLS/범용 ACL 도입, Asset owner 중복 저장, 기존 데이터 Master backfill을
검토했다. 각각 context 범위, 추가 운영 복잡성, 이중 source of truth, 기존 폐기 합의와의
충돌 때문에 선택하지 않았다. 초안 작성 후 사용자가 분할/권한 정책을 승인했고,
로컬 Docker Redis/PostgreSQL만 사용해 관리형 서비스 비용을 발생시키지 않도록 확인했다.

## 검증과 결과

실행한 것은 코드·테스트·스크립트 정적 조사, GitHub 병합 상태 확인, `main` fast-forward,
문서 링크/경로 예산 검사, `git diff --check`, status/staged-path 확인이다.
예상 non-document 예산은 13/20/20이며 G4 총 migration은 1개다.
경로 검사는 선행 slice에서 새로 만드는 파일까지 고려해 13/20/20을 확인했고,
관련 문서의 로컬 링크 18개와 diff hygiene가 통과했다. 최초 단순 파일 존재 검사는
아직 구현하지 않은 선행 helper를 누락으로 판단해, 실제 파일 또는 선행 산출물을
구분하는 검사로 수정했다. 구현 파일을 미리 만드는 방식으로 통과시키지 않았다.
설계에 A1–A24 보안/회귀 matrix와 최종 Postgres/Redis/worker 2회 검증을 정의했다.
구현 결과나 보안 테스트 PASS 수는 아직 없다. 개인 정보·credential·prompt·raw 응답은 읽거나
기록하지 않았다. DB reset, 외부 AI 호출, cloud 변경도 하지 않았다.

## 남은 위험과 다음 단계

- 세 Goal 분할, Master 타인 mutation 금지, 운영 endpoint 접근 계약 승인 완료.
- `/metrics`를 Master로 제한하면 무인 scrape가 중단되므로 별도 배포 gate로 남긴다.
- G4.2의 FK만으로 모든 cross-owner 관계를 DB에서 강제하지는 않는다.
- 기존 파일 삭제/DB commit 비원자성과 이미 전송된 stream 회수 한계를 숨기지 않는다.
- G4.1 구현·검증·병합 완료. G4.2A/B 분할도 승인됐으며 A만 실행 준비했다.
- 구현 이후 이 설계 기록을 해당 Issue 포트폴리오와 연결하고 실제 실패/수정/검증 수치를 추가한다.

## G4.2 상세화 — 2026-09-03

문제: 최초20-path 예상표에 G4.1 신설 harness의 head0002 상수, identity column 집합 검사,
직접 I2V/polling handler와 runtime admission matrix 변경이 빠져 있었다. 구현 단계에서
한도를 넘기거나 검사를 생략할 위험이므로 기존 단일 Goal은 No-Go로 판단했다.

해결 제안: [G4.2 상세 spec](../initiatives/g4-2-owner-persistence-admission-spec.md)에
A(저장·모든 writer·접수20개/migration1), B(worker·pipeline·실경합10개 후보/migration0)를
분리했다. codebase-design의 작은 interface 원칙으로 actor/SQL session을 주입받는
Ownership module은 유지하고, caller transaction과 worker 저장 owner 책임을 구분했다.
nullable owner/자동 Master backfill, schema-only 중간 배포, 테스트 삭제는 선택하지 않았다.

검증: G4.1 merge와 checkout tree 일치, 호출/상수/fixture 정적 검사, 관련10개 test 파일
`python -m pytest ... -q`로137 PASS. 대상은 generation/pipeline/prompt API, model relationships,
identity models, Alembic, schema/auth verifier, pipeline_link, job_handlers 테스트다.
이는 baseline이며 제안 기능의 pass count가 아니다. 새 경로 예산과 문서 링크도 검사한다.

결과: P01–P16, A/B별 Todo1–8 후보와 F1–F4, migration refusal/복구, foreign 참조,
Master 재사용, worker 부수효과0, 동시성/cleanup 검증을 연결했다. 현재는 문서만 변경했다.
분할 승인 후 [A Issue #105 준비 기록](issue-105-owner-persistence-admission.md)에
main 동기화, 작업 branch와 frozen Goal/hash를 연결했다. DB reset/provider/cloud 실행은 하지 않았다.
A의20개 예산에는 여유가 없으므로 추가 필요 시 구현을 멈추고 재설계한다.
G4.3 전까지 read/file/delete/ops 노출은 남는다.
