# Issue184 — Agent QA Video와 Pipeline Adapter

- [Issue184](https://github.com/bbungjun/AI_multimodal_platform/issues/184)
- Parent: [Issue182](https://github.com/bbungjun/AI_multimodal_platform/issues/182)
- Status: `Mock Verified / T2V·I2V Product QA FAIL / Pipeline PASS`

## 첫 체크포인트

`video_pipeline_adapter.py`의 compiler Interface가 정제 evidence를 T2V6, I2V6,
Pipeline8 assertion으로 변환한다. 기술 실행, external0, Console0, cleanup0이 아니면
assertion을 만들지 않고 세 scenario 모두 BLOCKED다.

완전한 fixture는 세 scenario PASS다. Free long-video가201이고 side effect1이면 T2V의
policy refusal/zero-side-effect가 FAIL한다. video가 재생 가능하지도 명시적 placeholder도
아니면 T2V/I2V usable assertion이 FAIL한다. focused4 PASS이며 아직 실제 Chrome/DB
통합 증거는 아니다.

다음은 DevTools로 T2V4초 정상/6초 초과, source image→I2V, parent→child Pipeline과 reload를
실행하고 DB identity/state/reservation 및 video asset probe를 연결하는 것이다.

## T2V 실제 실행

Core `3bbc8e0`에서 T2V4초 정상 요청과 Free6초 초과 요청을 실제 Chrome DevTools로
수행했다. 실행은 external0/Console0/cleanup0으로 끝까지 완료됐다. empty guard는 PASS했다.
Free6초는 HTTP201이고 정상 요청을 제외한 DB delta가 jobs1/outbox1/reservations1이었다.
mock video file은 browser에서 관측되지 않아 MIME/usable이 false였고 빠른 mock 상태는
pending→completed로 관측됐다. 따라서 contract6개 중 policy, side effect, state path,
asset MIME, usable 총5개가 FAIL이었다. 최종 DB history 교차검증 결과는 아래 통합 summary가 대체한다.

## I2V 실제 실행

Core `a3792f2`에서 같은 owned runtime에 자동 T2I source를 만든 후, source Job detail의
실제 `I2V 시작` control을 클릭했다. source ID는 process memory에만 전달하고 receipt에는
저장하지 않았다. source selection과 persisted Job identity, video/mp4 asset은 PASS했다.
no-source DOM disabled는 true였지만 accessibility disabled가 false였고, state는
pending→completed, mock video usable은 false여서 scenario FAIL이다. external0/Console0/
cleanup0이다. 최종 DB history 교차검증 결과는 아래 통합 summary가 대체한다.

## Pipeline 및 최종 판정

Pipeline actual run은 incomplete disabled, POST201, parent/child 완료, source 연결과 reload를
통과했다. DB state_history는 parent pending→running→completed, child blocked→pending→
running→completed였고 same owner/source true, reservation1, held0이다. Pipeline8/8 PASS다.

DB history를 T2V/I2V에도 적용한 최종 compiler 결과는 T2V3 FAIL(policy refusal,
side-effect0, usable), I2V2 FAIL(no-source accessibility disabled, usable), Pipeline PASS다.
모든 run은 external0, 예상 밖 Console0, cleanup0이다.
[최종 정제 summary](../evidence/issue-184/final-video-pipeline-summary.json)에 근거를 모았다.

## 최종 회귀

- backend:1888 PASS,3 guarded SKIP, 기존 Windows/Bash path1 deselected.
- DevTools Node:33 PASS.
- frontend lint/build, env-example Compose, diff check: PASS.
- delivery file19로 child20-file limit 충족.
