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

결과는15 PASS다. compiler와 DB probe contract의 구현 증거이며 아직 실제 Chrome/DB
통합 실행 증거는 아니다.

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
