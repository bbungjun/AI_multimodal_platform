# G4 설계 기록 — 로그인에서 사용자 데이터 격리로

- 상태: **Accepted / Planned**, 2026-09-03. 설계만 완료; 구현은 시작하지 않았다.
  후속 [Issue #103](https://github.com/bbungjun/AI_multimodal_platform/issues/103)의 G4.1 Goal을 준비했다.
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
- G4.1 Issue/branch/고정 Goal 준비 완료. 별도 실행 요청 후 Todo를 시작한다.
- 구현 이후 이 설계 기록을 해당 Issue 포트폴리오와 연결하고 실제 실패/수정/검증 수치를 추가한다.
