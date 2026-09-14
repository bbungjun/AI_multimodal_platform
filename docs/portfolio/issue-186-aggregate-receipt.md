# Issue186 — Agent QA 10개 scenario aggregate Receipt gate

- [Issue186](https://github.com/bbungjun/AI_multimodal_platform/issues/186)
- Parent: [Issue182](https://github.com/bbungjun/AI_multimodal_platform/issues/182)
- Status: `In Progress`

네 delivery slice가 각각 실행되더라도 revision과 cleanup이 다른 결과를 사람이 복사해
합치면 Agent의 merge 판단 근거가 재현되지 않는다. aggregate Interface는 full impact
selection, clean immutable HEAD, source digest를 선행조건으로 삼고 각 owned mock runtime의
정제 결과만 입력으로 받는다.

집계기는10개 scenario를 Registry 순서로 정렬하고68개 assertion coverage를 강제한다.
혼합 revision, source 변경, slice 실행 실패, cleanup 누락, scenario 누락은 Receipt를
생성하지 않는다. 생성된 Receipt도 기존 contract validator로 다시 검증한다. 판정은 모든
scenario PASS일 때만 `ALLOW`, 제품 FAIL/BLOCKED는 `REJECT`이며 실제 merge API 호출은
설계 범위 밖이다.

현재 focused aggregate/Adapter/Contract test51개가 PASS했다. 다음 checkpoint에서 같은
core revision으로10개 실제 Chrome DevTools 여정을 모두 실행하고, 실행 시간·결함 수·
cleanup·최종 merge decision을 정제 evidence로 기록한다.
