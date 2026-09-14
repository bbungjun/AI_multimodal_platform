# Issue186 — Agent QA 10개 scenario aggregate Receipt gate

- [Issue186](https://github.com/bbungjun/AI_multimodal_platform/issues/186)
- Parent: [Issue182](https://github.com/bbungjun/AI_multimodal_platform/issues/182)
- Status: `Mock Verified`

네 delivery slice가 각각 실행되더라도 revision과 cleanup이 다른 결과를 사람이 복사해
합치면 Agent의 merge 판단 근거가 재현되지 않는다. aggregate Interface는 full impact
selection, clean immutable HEAD, source digest를 선행조건으로 삼고 각 owned mock runtime의
정제 결과만 입력으로 받는다.

집계기는10개 scenario를 Registry 순서로 정렬하고68개 assertion coverage를 강제한다.
혼합 revision, source 변경, slice 실행 실패, cleanup 누락, scenario 누락은 Receipt를
생성하지 않는다. 생성된 Receipt도 기존 contract validator로 다시 검증한다. 판정은 모든
scenario PASS일 때만 `ALLOW`, 제품 FAIL/BLOCKED는 `REJECT`이며 실제 merge API 호출은
설계 범위 밖이다.

## 관측과 원인 분석

첫 실제 전체 실행은10 scenario/68 assertion을550.203초에 집계했지만 T2I 정상 작업의
`allowed_job_completed`까지 FAIL로 표시했다. raw identity를 보존하지 않고 정제 상태만
비교한 결과, 브라우저 polling은 빠른 mock 전이의 `running`을 놓쳐
`pending→completed`를 관측했지만 DB state history는 `pending→running→completed`였다.
계약상 해당 assertion의 evidence source가 database/runtime receipt이므로 DB history를
authoritative source로 바꾸고 브라우저는 사용자-visible 결과 판정에만 사용했다.

두 번째 시도는 T2I PNG를 video 전용 MIME validator가 거부해 Image slice 직후
차단됐다. media별 allowlist로 분리했다. 세 번째 시도는 Auth/Image/T2V/I2V/Pipeline을
완료한 뒤 Docker Desktop engine이500으로 내려가 Workspace runtime 시작이 막혔다.
이미지·볼륨 초기화 없이 runtime socket directory를 timestamp backup으로 이동해
Engine29.2.1을 복구했다. 이어 exact revision, source unchanged, process/cleanup0을 모두
만족하는 slice만 재사용하는 `--resume`을 추가했다. 다른 revision이나 불완전한 결과는
재사용하지 않는다.

## 최종 검증과 결과

Core `f6ca646`의 최종 실행은550.656초에10 scenario와68 assertion을 전부 판정했다.
58개 PASS,10개 FAIL, BLOCKED0이며 source unchanged, browser/MCP/Vite/runtime cleanup은
모두0이다. contract validator가 Receipt를 다시 검증했고 aggregate verdict는 `FAIL`,
merge decision은 `REJECT`다.

- PASS: Auth7/7, Prompt Review6/6, Pipeline8/8, History6/6, Usage6/6, Retry6/6
- T2I4 FAIL: Free 2장 요청이 거부되지 않고 Job/Outbox/Reservation side effect가 남음
- T2V3 FAIL: Free 6초 요청과 side effect, mock video가 사용자 재생 결과로 쓸 수 없음
- I2V2 FAIL: source 없는 submit의 accessibility disabled 불일치, mock video unusable
- Role1 FAIL: 일반 사용자에게 접근 불가능한 Ops navigation이 노출됨

[전체 contract-valid Receipt](../evidence/issue-186/aggregate-receipt.json)는 assertion id,
boolean, evidence source, revision과 cleanup만 포함한다. prompt 원문, 사용자 식별자, cookie,
OAuth 값, header/body, 개인 PC 경로는 없다. 이 gate는 현재 제품 결함 때문에 올바르게
merge를 거부했으며, 자동 merge 권한은 의도적으로 연결하지 않았다.

Fresh regression은 backend1903 PASS/3 guarded skips/기존 Windows Bash path1 deselected,
DevTools Node38, frontend lint/build, Registry10 scenario/68 assertion, 저장된 aggregate
Receipt validation, env-example Compose와 diff check가 PASS했다. delivery는13파일이다.
