# Issue #103 — 인증된 mock 검증 기반

- 상태: **Planned / Goal Prepared**, 구현 시작 전.
- [Issue #103](https://github.com/bbungjun/AI_multimodal_platform/issues/103)
- Branch: `codex/issue-103-authenticated-mock-harness`, base `100f5e7`.
- [Accepted spec](../initiatives/g4-ownership-access-control-spec.md),
  [G4 설계 판단](g4-ownership-design.md).

## 배경과 문제

생성·retry·I2V duplicate smoke가 익명 요청에 의존한다. G4에서 인증과 소유권을
강제하면 기존 검증이 정상 제품 요청을 재현하지 못한다. 실제 Google 계정을 여러 개
만들거나 유료 Redis를 도입하지 않고도 서버가 검증하는 Session으로 테스트해야 한다.

## 관측과 원인

golden의 HttpClient는 cookie/Origin을 전달하지 않고 redirect를 따라간다. duplicate의
동시 요청은 별도 urlopen을 사용한다. 오류에는 body snippet이 포함될 수 있고 manual
workflow는 기본 Compose project의 로그와 down -v를 사용한다. 인증 fixture를 추가하기
전에 요청 운반과 격리·증거 안전을 함께 정리할 필요가 있다.

## 선택과 범위

codebase-design의 작은 interface 원칙을 적용해 test-only harness가 HTTP, fixture,
Docker 수명, receipt를 맡는다. raw Session은 메모리에만 두고 hash만 격리 DB에 저장한다.
실제 G3 인증을 재사용하지만 제품 mock-login route나 소유권 코드는 만들지 않는다.
로컬 Docker PostgreSQL/Redis, mock provider만 사용하며 관리형 클라우드 구축은 제외한다.

## 이번 준비 결과 / 검증

사용자 설계 승인을 canonical initiative에 반영했고 Issue/branch와 Todo 1–8/F1–F4 Goal을
준비했다. 문서-only 작업이며 runtime pass count, 구현 성과, 보안 격리 완료를 주장하지 않는다.
실행 계획은 13개 non-document hard limit, migration 0개, 두 fresh local runtime cycle,
최종 CI 통과 후 Ready PR squash auto-merge를 요구한다. hash와 문서 정합성은 handoff에 남긴다.
준비 검증: SHA-256/Issue 본문 일치, 중복 없는 allowlist 13개, Todo 8개, final gate 4개,
관련 문서 로컬 링크 57개, diff/whitespace 검사 PASS. 제품 테스트는 이번 문서 준비에서
실행하지 않았으며, Git에 문서만 보관하고 frozen Goal은 local/untracked로 유지한다.

## 남은 위험과 다음 단계

실행 요청 후 baseline부터 검증한다. 실패/수정/실제 test count와 cleanup 결과는 이 문서에
추가한다. rollback은 review된 harness/스크립트/workflow revert이며 DB schema는 변경하지 않는다.
G4.1은 검증 기반일 뿐 사용자 데이터 격리는 G4.3 완료까지 미구현이다. 강제 process 종료는
finally cleanup을 막을 수 있어, 정확한 소유 project 복구 절차를 구현 시 기록해야 한다.
