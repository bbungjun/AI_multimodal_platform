# Issue185 — Agent QA History/Usage/Retry/Role Adapter

- [Issue185](https://github.com/bbungjun/AI_multimodal_platform/issues/185)
- Parent: [Issue182](https://github.com/bbungjun/AI_multimodal_platform/issues/182)
- Status: `Mock Verified`

첫 checkpoint는 네 scenario의27 assertion compiler다. 완전한 evidence는 PASS, 제품
불일치는 scenario FAIL, tool/source/cleanup 불완전은 assertion을 만들지 않고 전체
BLOCKED다. 실제 Chrome/DB 실행은 다음 checkpoint에서 연결한다.

두 번째 checkpoint는 owned `workspace_qa_fixture.py`다. mock OAuth user가 생성된 뒤에만
기본 page size20에서 page2를 만들도록 pagination용 failed Job22개를 추가하며 첫 Job은 정상 prompt의 retryable failure다.
`prepare/promote/inspect` 외 operation, foreign DB, non-mock/non-test 환경을 거부한다.
inspect는 retry와 개인 usage 원장의 정제된 수치·boolean만 반환한다. compiler+fixture
focused test는 최종14 PASS다.

## 관측과 원인 분석

첫 통합 실행은 일반 사용자 여정을 완료했지만 Master 사용자 목록이503이었다. Master
read model을 추적한 결과 제품 API 결함이 아니라 fixture가 role만 Master로 바꾸고
account plan은 Free로 남겨 `Master → Max` 불변식을 깨뜨린 것이 원인이었다. fixture를
감사 기록을 남기는 실제 `operator_cli promote` 경계로 교체했고, 재실행에서 overview,
users, audit, ops가 모두200을 반환했다.

실행 전 Docker Desktop은 오래된 Inference/Secrets Engine 런타임 socket 때문에 시작하지
못했다. 이미지·볼륨 초기화 없이 프로세스를 종료하고 두 runtime directory를 timestamp
backup으로 이동해 Engine29.2.1을 복구했다. 백업은 로컬에 남아 있으며 repo evidence에는
개인 PC 경로를 기록하지 않았다.

## 해결과 검증

- History 응답의 offset을 정제해 `[0,0,20,0]`으로 기록하고, 필터 reset, 두 페이지,
  동일 Job 상세 이동, 삭제 취소 후 DELETE0을 교차검증한다.
- Usage 화면의 available/held/charged 문자열을 DB personal usage read model과 대조한다.
  최종 값은 UI `950/0/50`, DB `950000000/0/50000000` microcredits였고 reload 전후가 같다.
- retry는 원본 failed/asset0, 사용자 오류 표시, 새 Job과 원본 link, DB state history
  `pending→running→completed`, asset1, 원본0/retry1 usage record를 검증한다.
- 일반 사용자는 Ops/Master API가 각각403이고 자동 admin polling은0이다. Master는 네
  운영 화면과 API가 모두200이다.

Core `ed296fe`의 owned mock 실행은 Workspace12단계와 Master6단계를131.312초에 완료했고,
external request0, 예상 밖 Console0, browser/runtime cleanup0, source unchanged다. 총27개
assertion 중26개가 PASS했다. 유일한 제품 FAIL은 일반 사용자에게 `운영` 탐색 메뉴가
노출되는 `role.user_admin_navigation_hidden`이다. API 권한 거부는 정상 동작하므로 즉시
권한 상승은 아니지만, 접근 불가능한 기능 노출로 UX와 역할 정책이 불일치한다.

Fresh regression은 backend1898 PASS/3 guarded skips/기존 Windows Bash path1 deselected,
DevTools Node38, frontend lint/build, Registry10 scenario/68 assertion, env-example Compose와
diff check가 PASS했다. delivery는16파일로 bounded slice 기준을 지켰다.

[정제 실행 근거](../evidence/issue-185/workspace-summary.json)는 식별자, prompt 원문,
cookie, OAuth 값, raw response를 포함하지 않는다. 다음 단계는10개 scenario를 하나의
contract-valid Receipt로 집계하고 이 제품 FAIL을 merge 판단에 반영하는 Issue186이다.
