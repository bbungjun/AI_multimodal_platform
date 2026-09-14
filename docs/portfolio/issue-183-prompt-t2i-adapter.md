# Issue183 — Agent QA prompt review와 T2I Adapter

- Parent: [Issue182](https://github.com/bbungjun/AI_multimodal_platform/issues/182)
- Current: [Issue183](https://github.com/bbungjun/AI_multimodal_platform/issues/183)
- Status: `In Progress`

## 목표

Issue180의 `auth_login` 수직 slice 다음으로 `prompt_review`와 `t2i_generation`을 실제
Chrome DevTools MCP와 owned mock runtime에 연결한다. 두 흐름은 같은 Generate 화면과
사용자 세션을 공유하므로 한 runtime에서 실행하되 scenario result는 독립적으로 판정한다.

## 이번 체크포인트

`qa/executor/prompt_t2i_adapter.py`에 compiler Interface를 먼저 고정했다. 입력은 raw DOM,
request body나 identity가 아니라 정제 boolean/count/status/state path다. 출력은 Registry의
prompt6개와 T2I8개 assertion ID를 정확히 포함하는 scenario result 두 개다.

- DevTools technical complete, external0, Console0, Network cross-check와 runtime Receipt가
  모두 있어야 assertion을 생성한다. 하나라도 없으면 두 scenario는 `BLOCKED`다.
- prompt는 enhancement2회, 원문 보존, discard 복구, edited accept, 제출/persistence
  동일성과 비자동 대체를 검증한다.
- T2I는 empty disabled, Free over-limit403, 거절 후 job/outbox/reservation delta0,
  pending→running→completed, PNG decode와 visible result를 검증한다.
- over-limit201과 side-effect1 입력은 알려진 제품 결함으로 4개 assertion `FAIL`이며
  allow-failure로 바꾸지 않는다.
- closed browser shape에 identity 같은 extra field가 있으면 compiler가 거부한다.

두 번째 체크포인트는 owned backend 내부의 read-only DB probe다. stdin으로 `counts` 또는
`job` operation만 받고 fresh `ownership-verify-*` DB, mock, test mode를 모두 확인한다.
출력은 global job/outbox/reservation count 또는 정상 Job의 state와 asset/PNG/outbox/
reservation count뿐이다. reservation은 Job의 내부 credit metadata ID로 연결해 세며 ID
자체는 출력하지 않는다.

Focused test:

```powershell
python -m pytest backend/tests/test_prompt_t2i_adapter.py backend/tests/test_prompt_t2i_probe_support.py -q
```

결과는 compiler/DB probe15 PASS다.

## 자동 Chrome 체크포인트

기존 agent.mjs image protocol에 `image-controller.mjs`를 추가했다. Controller가 각 화면
변경 후 새 accessibility snapshot에서 control UID를 다시 얻고 fixture 이름으로만 입력한
뒤, enhance/edit/accept/generate/completed/reload/History/revisit 순서를 자동 수행한다.

Core `d071e85` 실제 owned mock 실행 결과:

| Metric | 결과 |
|---|---:|
| DevTools actions | 33 |
| Journey checks | 14/14 |
| 정제 compiler checks | 8/8 |
| Enhancement / generation POST | 1 / 1 |
| PNG | image/png, 556940B, decoded |
| Job / file reads | 4 / 2 |
| External / unexpected Console | 0 / 0 |
| Browser / runtime cleanup | 0 / 0 |
| 실행 시간 | 82.063s |

[정제 summary](../evidence/issue-183/auto-image-journey-summary.json)만 커밋한다. 이 실행은
edited accept와 정상 한 장 생성의 partial Mock Verified 증거다. discard/original choice,
empty disabled, Free over-limit refusal와 DB delta는 아직 검증하지 않았으므로 두 contract
scenario 전체 PASS로 승격하지 않는다.

Core `b38d597`에서는 상태 머신을 empty→discard→keep→edit/accept로 확장했다. 실제 owned
실행은 checkpoint15, enhancement3, generation1, source unchanged와 cleanup0으로 기술적
완료에 도달했다. discard, 원본 유지, edited accept는 모두 성공했고 유일한 제품 실패는
`empty_submission_disabled=false`였다. [경계 summary](../evidence/issue-183/prompt-boundary-summary.json)에
정제 결과를 남겼다. 이 신호는 다음 실행에서 DOM `disabled` property와 accessibility
snapshot을 교차검증하기 전까지 확정 결함으로 과장하지 않는다.

## 남은 구현

1. Chrome DevTools MCP action driver에서 empty/discard/keep/edit/accept/over-limit/allowed
   journey를 실제 control로 수행한다.
2. over-limit 전후 DB job/outbox/reservation delta와 allowed state path를 owned runtime
   내부 allowlist probe로 수집한다.
3. PNG response를 decode하고 browser response와 DevTools Network를 cross-check한다.
4. 동일 clean revision에서 반복 실행, cleanup0, 정제 evidence를 기록한다.
5. 전체 회귀와 일반 PR을 통과한 뒤 merge한다.

제품 코드, 실제 Gemini/Imagen, 전체 Receipt와 자동 merge decision은 이 child의 범위가
아니다.
