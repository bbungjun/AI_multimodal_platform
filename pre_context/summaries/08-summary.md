# krafton_assignment_08 요약

## 핵심 주제

Phase 14 Live UX QA 중 발견된 `POST /api/generations` lazy-load 500 버그를 좁혀 bugfix 방향으로 정리하고, 이후 Phase 14 재개/기록 방식을 잡은 짧은 세션입니다. Prompt Enhance 자체 구현은 이 세션에서 하지 않았고, Live QA에서 어떻게 검증할지만 정리했습니다.

## 주요 키워드

- Phase 14 Live UX QA
- `POST /api/generations` 500
- FastAPI `ResponseValidationError`
- `loc: ('response', 'assets')`
- SQLAlchemy async lazy-load, `MissingGreenlet`
- `JobResponse`, `job.assets`, DTO mapper
- `job_response_from_job(...)`
- Gemini Enhance QA planned, no implementation

## 복구에 중요한 내용

- 세션 시작 상태는 Phase 13 API contract alignment 완료, Vite/E2B public host 차단 수정, Phase 14 Live UX QA 진행 중이었습니다.
- T2I Generate가 `POST /api/generations`에서 500으로 실패했고, backend 로그의 핵심은 `ResponseValidationError`, `loc: ('response', 'assets')`, `MissingGreenlet: greenlet_spawn has not been called`였습니다.
- 원인은 FastAPI/Pydantic이 `JobResponse`를 직렬화하면서 ORM relationship인 `job.assets`를 건드렸고, async SQLAlchemy lazy-load가 await 가능한 greenlet 컨텍스트 밖에서 발생한 것입니다.
- bugfix 방향은 API response가 async lazy relationship에 기대지 않도록 명시적 DTO를 만들거나 eager-load하는 것이었습니다. 실제 완료 보고에서는 DTO mapper 방식이 적용되었습니다.
- 복구 시 확인해야 할 변경 요약:
  - `backend/app/schemas.py`: `job_response_from_job(...)` 또는 동등한 DTO mapper가 있는지 확인
  - `backend/app/api/generations.py`: `POST /api/generations`가 ORM `Job` 대신 `assets=[]` 포함 DTO를 반환하는지 확인
  - `backend/app/api/pipelines.py`: pipeline create 응답도 같은 lazy-load 위험을 피하도록 처리되었는지 확인
  - `backend/tests/test_t2i_flow.py`: `assets` lazy 접근 시 실패하는 회귀 테스트가 있는지 확인
- 검증은 관련 endpoint-level pytest, backend 전체 pytest, compose config 검증으로 이루어졌습니다.
- 이 버그를 Phase 14 기록에 반영할 때는 T2I를 바로 `passed`로 표시하지 말고 `fixed, pending live retest` 상태로 남기라고 정리했습니다.
- Phase 14는 자동 테스트가 아니라 실제 브라우저 UI에서 Vertex-backed Gemini/Imagen/Veo 호출까지 포함하는 end-to-end UX QA입니다. 다만 문제 발생 시 QA report와 bugfix를 섞지 않고, 병목 하나씩 최소 수정하는 원칙이 반복됩니다.
- Prompt Enhance에 대해서는 이 세션에서 구현/수정이 없었습니다. 정리된 내용은 Phase 14 Live UX QA에서 Gemini Enhance를 최대 1회 실제 호출로 검증하고, 실패 시 반복 호출하지 않으며, 자동 테스트는 mock-only로 유지한다는 전략입니다.

## 원문에서 찾아볼 위치

- lazy-load bugfix 프롬프트와 root cause: 대략 173~215, 225~274
- 완료 보고와 테스트 결과: 대략 296~308
- Phase 14 재개 프롬프트: 대략 317~369
- Phase 14 의미와 체크리스트: 대략 375~587
- Phase 14 기록 업데이트 프롬프트: 대략 697~770
- Prompt Enhance 관련 세션 요약: 대략 794~821

## 복구 판단 메모

- 현재 `POST /api/generations`가 ORM `Job`을 그대로 반환하고 있다면 원래 fix가 사라졌을 가능성이 큽니다. `job_response_from_job(...)` 또는 동등한 DTO mapper를 확인합니다.
- pipeline create 응답도 같은 lazy-load 위험을 공유했으므로 `generations.py`만 고치고 `pipelines.py`가 빠져 있으면 복구가 불완전할 수 있습니다.
- Prompt Enhance는 이 파일만 보고 "구현 완료"로 판단하면 안 됩니다. 실제 구현/bugfix/Live QA는 `09-summary.md` 쪽이 중요합니다.
