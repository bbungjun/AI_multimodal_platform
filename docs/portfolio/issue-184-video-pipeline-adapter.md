# Issue184 — Agent QA Video와 Pipeline Adapter

- [Issue184](https://github.com/bbungjun/AI_multimodal_platform/issues/184)
- Parent: [Issue182](https://github.com/bbungjun/AI_multimodal_platform/issues/182)
- Status: `In Progress`

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
asset MIME, usable 총5개가 FAIL이다. [정제 증거](../evidence/issue-184/t2v-failure-summary.json).
