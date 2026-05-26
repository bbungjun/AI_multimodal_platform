# Test coverage gap analysis

작성일: 2026-05-27

이 문서는 현재 복구된 backend/frontend 검증 범위가 과거 최종 제출 시점의
테스트 범위와 어디서 차이 나는지 정리한 메모입니다. 목표는 pytest 개수를
기계적으로 229개에 맞추는 것이 아니라, 최종 제출물의 핵심 계약 중 아직
자동 검증이 얇은 영역을 찾아 다음 복구 순서를 정하는 것입니다.

비용이 발생할 수 있는 Vertex/Gemini/Imagen/Veo live QA는 이 분석 범위에서
제외했습니다. 모든 판단은 현재 코드, README, memories, pre_context 기록,
그리고 mock/fake-only 테스트 경계를 기준으로 합니다.

## 기준 상태

- 기준 commit: `bf98ccf docs: record history delete smoke`
- branch: `main`
- 시작 git 상태: clean, staged 파일 없음
- Compose 상태: mock mode stack 실행 중
- 현재 자동 수집 결과:
  - `cd backend`
  - `$env:AI_PROVIDER='mock'; python -m pytest --collect-only -q`
  - 결과: `67 tests collected`

과거 기록과 비교하면 다음 차이가 있습니다.

- `memories/phase/phase10.md`: 전체 backend regression `206 passed`
- `pre_context/summaries/06-summary.md`: Phase 8 부근 `169 passed`
- 사용자 기억: 최종 제출 시점 pytest 약 `229개`
- 현재 복구본: backend collect 기준 `67개`

따라서 숫자만 보면 약 30% 수준입니다. 다만 현재 67개는 핵심 API skeleton,
state/storage/job runner/provider boundary 위주로 압축 복구된 상태라서,
기능 복구율을 테스트 개수와 동일하게 보면 안 됩니다. 현재 상태는 "핵심
happy path와 주요 안전 경계는 살아 있지만, 과거 제출 직전의 세부 실패
경로와 반복 자동 QA는 많이 빠진 상태"로 보는 것이 맞습니다.

## 현재 테스트 분포

| 파일 | 수집 개수 | 커버하는 범위 |
|---|---:|---|
| `tests/test_asset_api.py` | 2 | asset DTO 조회, missing asset 404 |
| `tests/test_generation_api.py` | 10 | generation 생성/조회/list/delete, enhancement 연결, dependent 보호 |
| `tests/test_health.py` | 2 | DB/Vertex readiness 분리, mock credential 불필요 |
| `tests/test_job_handlers.py` | 8 | T2I/T2V/I2V handler, multi-image 저장, failure cascade, Veo resume/timeout |
| `tests/test_job_runner.py` | 5 | pending claim, handler 실행, failure 처리, polling resume, orphan sweep |
| `tests/test_mock_provider.py` | 5 | mock image/prompt/video/I2V, mock readiness no credential |
| `tests/test_pipeline_api.py` | 5 | pipeline 생성/조회, unsupported image model, 404 |
| `tests/test_pipeline_link.py` | 5 | parent image asset 연결, missing/not-image 실패, terminal child skip |
| `tests/test_prompt_api.py` | 2 | prompt enhancement persist, provider error mapping |
| `tests/test_prompt_enhancer.py` | 4 | schema parse, malformed JSON retry, invalid schema, rate limit mapping |
| `tests/test_state_machine.py` | 5 | transition/history/invalid transition/helper set |
| `tests/test_storage.py` | 5 | save/read/delete, unsafe path, `/files`, single byte range |
| `tests/test_vertex_imagen.py` | 4 | inline/base64 image bytes, missing output, rate limit mapping |
| `tests/test_vertex_veo.py` | 5 | inline/base64 video bytes, missing output, operation error, timeout |

## 현재 강한 영역

- API skeleton과 DTO 흐름은 복구되어 있습니다.
  - `GET /api/health`
  - `POST /api/prompts/enhance`
  - `POST /api/generations`
  - `GET /api/generations`
  - `GET /api/generations/{job_id}`
  - `DELETE /api/generations/{job_id}`
  - `POST /api/pipelines`
  - `GET /api/pipelines/{parent_job_id}`
  - `GET /api/assets/{asset_id}`
  - `GET /files/{job_uuid}/{filename}`
- storage/path safety와 `/files` streaming/range는 기본 계약이 살아 있습니다.
- state machine을 거친 transition/history 기록은 기본 검증이 있습니다.
- mock provider는 실제 Vertex client 생성 없이 image/prompt/video/I2V 흐름을
  검증합니다.
- Prompt Enhancement는 review/edit/accept 흐름의 backend contract와 mock
  browser smoke가 있습니다.
- History filter/delete, I2V source preview, Prompt Enhancement submit은
  최근 browser smoke로 비용 없이 확인했습니다.

## 큰 gap 후보

### P0. Rate limiter / retry 테스트 복구

과거 Phase 5 기록에는 다음 파일이 명시되어 있습니다.

- `backend/tests/test_rate_limiter.py`
- `backend/tests/test_retry.py`

현재 구현 파일은 남아 있습니다.

- `backend/app/services/rate_limit.py`
- `backend/app/services/retry.py`
- 실제 구현은 `backend/app/services/vertex/rate_limit.py`,
  `backend/app/services/vertex/retry.py`로 위임됩니다.

하지만 현재 test suite에는 독립 테스트 파일이 없습니다. README는 모델별
sliding-window rate limiter와 bounded retry를 핵심 architecture로 설명하고
있기 때문에, 이 영역은 다음 복구 우선순위가 높습니다.

복구 후보:

- capacity 이내 acquire 즉시 통과
- capacity 초과 시 injected clock/sleep 기반 window slide 대기
- model registry와 unknown model 에러
- retryable 429/5xx 후 성공
- non-retryable 4xx 즉시 실패
- max attempts 중단
- exponential backoff와 max delay cap
- `retryable=True`, `status_code`, `code`, `status`,
  `response.status_code` 추출 순서
- invalid retry config

이 작업은 실제 Vertex 호출이 필요 없고, backend-only라서 비용/환경 리스크가
낮습니다.

### P0. Veo provider failure classification 보강

현재 `test_vertex_veo.py`는 missing video, operation error, timeout을
검증합니다. README와 최종 요약에는 더 넓은 실패 분류가 등장합니다.

- operation error
- safety-filtered result
- missing output
- `vertex_safety_blocked`
- `vertex_output_unavailable`

현재 코드에는 `VertexSafetyBlockedError` 클래스가 남아 있지만, 자동 테스트가
safety-filtered result를 충분히 재현하는지는 얇습니다. 실제 live QA를 하지
않을 것이므로, fake operation 객체로 provider-side failure shape를 더
넓게 검증하는 것이 좋습니다.

복구 후보:

- Veo operation error payload message/code 보존
- safety-filtered 또는 filtered/no-output 형태를 public code로 매핑
- handler error payload에 `retry_count`, `last_attempt_at`,
  `operation_name`이 필요한 경우 유지되는지 확인
- unexpected provider exception이 credential/secret 없이 sanitize되는지 확인

### P0. Pipeline/generation model validation 세부 테스트

현재 pipeline API에는 unsupported image model 테스트가 있습니다. 최종 요약은
pipeline model validation을 제출 직전 보강 항목으로 기록합니다.

복구 후보:

- `/api/generations`에서 T2I에 Veo model을 넣으면 거절
- `/api/generations`에서 T2V/I2V에 Imagen model을 넣으면 거절
- `/api/pipelines`에서 video_model이 Veo family가 아니면 거절
- I2V request에서 source asset 누락/잘못된 kind가 API 또는 handler 경계에서
  일관된 public error로 나타나는지 확인

이 영역도 실제 provider 호출 없이 API validation과 fake handler로 닫을 수
있습니다.

### P1. T2I multi-image gallery / per-image I2V handoff

현재 backend handler 테스트는 `number_of_images=2`일 때 image asset 두 개를
저장하는 것을 확인합니다. 하지만 frontend `JobDetailPage`는 현재
`job.assets[0]`을 primary asset으로 사용합니다. `pre_context/summaries/15-summary.md`
에는 최종 제출 직전 polish로 "T2I multi-image gallery"와 "각 image별 I2V
시작 흐름"이 언급되어 있습니다.

사용자가 UI의 pixel-perfect 일치는 중요하지 않다고 했으므로, 여기서 중요한
것은 화면 모양이 아니라 기능 계약입니다.

복구 후보:

- completed T2I job에 image asset이 여러 개 있으면 모두 preview 가능
- 각 image asset에서 `Start I2V with this image` 가능
- backend detail/list asset ordering이 deterministic한지 확인
- frontend 자동 테스트 도입은 하지 않고, browser smoke 또는 문서화된 수동
  mock smoke로 검증

### P1. Frontend flow 자동 검증 부재

현재 frontend는 `npm run lint`, `npm run build`, 그리고 browser smoke로
확인했습니다. 하지만 old pytest 229개와 비교되는 backend 중심 자동 테스트와
달리 frontend에는 반복 가능한 테스트 파일이 없습니다.

현재 비용 없이 확인된 browser smoke:

- Prompt Enhancement: enhance -> draft edit -> accept -> generation submit
- History: asset type filter, video row preview/fallback, terminal delete
- Job Detail: standalone I2V source image preview

복구 후보:

- 새 frontend test framework를 도입하지 않는 규칙을 유지합니다.
- 대신 smoke 절차를 `memories/recovery/*`에 계속 기록하거나, 기존 도구만으로
  API/client contract compile 범위를 늘립니다.
- 비용이 들지 않는 browser smoke만 유지합니다.

### P1. Cancel flow

초기 구현 계획에는 `POST /api/generations/{id}/cancel`과 `test_cancel.py`가
등장합니다. 현재 README API 요약에는 cancel endpoint가 없고, 현재 복구본에도
명시적 cancel API가 보이지 않습니다.

따라서 지금은 "바로 구현"보다 "최종 제출물에 실제로 남아 있었는지 추가
근거 확인"이 먼저입니다. 증거가 약하면 새 기능으로 간주하고 보류하는 편이
안전합니다.

### P2. 세부 edge case

아래는 중요하지만 P0보다 뒤로 미룰 수 있는 후보입니다.

- `/files` suffix range, invalid range, MIME/header 세부 케이스
- state machine 전체 transition matrix 확장
- delete 중 파일 누락/DB-파일 불일치 처리
- job runner semaphore/concurrency 세부 검증
- health에서 DB down/provider down 조합 추가
- Prompt Enhancement mode별 components 차이, video motion/camera 필드 검증
- Gemini malformed JSON/fenced JSON/긴 응답 edge case 추가
- Vertex auth/permission/quota/transient error mapping breadth

## 다음 복구 순서 추천

추천 1순위는 `test_rate_limiter.py`와 `test_retry.py` 복구입니다.

이유:

- README가 명시한 핵심 architecture입니다.
- 과거 Phase 5에 파일명과 테스트 항목이 구체적으로 남아 있습니다.
- 실제 Vertex/Gemini/Imagen/Veo 호출 없이 검증할 수 있습니다.
- UI 변경이나 새 framework가 필요 없습니다.
- 현재 67개와 과거 206~229개 사이에서 가장 명확하게 빠진 독립 테스트
  묶음입니다.

그 다음 후보는 generation/pipeline model validation과 Veo failure
classification입니다. 둘 다 비용 없는 fake/mock 테스트로 닫을 수 있고,
실제 제출물의 안정성 설명과도 직접 연결됩니다.

## 결론

현재 복구본은 "최소 제출 동작과 주요 no-cost smoke" 기준으로는 꽤 많이
회복되어 있습니다. 하지만 테스트 자동화 관점에서는 과거 최종본 대비 아직
중간 단계입니다.

대략적인 체감 복구율은 다음처럼 보는 것이 현실적입니다.

- 핵심 backend/API/provider boundary: 약 75~85%
- frontend 주요 사용자 흐름: 약 65~75%
- 과거 자동 테스트 커버리지: 약 30~35%
- 최종 제출물 전체 parity: 약 65~75%

다음 세션에서는 테스트 개수를 억지로 맞추기보다, 비용 없는 P0 테스트 묶음을
하나씩 복구해서 confidence를 올리는 방식이 가장 안전합니다.

## Follow-up: rate limiter / retry tests restored

2026-05-27 후속 작업에서 위 P0 후보 중 `rate limiter / retry` 테스트 묶음을
복구했습니다.

추가된 파일:

- `backend/tests/test_rate_limiter.py`
- `backend/tests/test_retry.py`

복구한 계약:

- sliding-window limiter capacity, wait/prune, model registry, unknown model
- Imagen/Veo/Gemini 기본 rate limit 값
- bounded retry 기본 retryable status code
- retryable status 후 성공
- non-retryable 4xx 즉시 실패
- max attempts 중단
- exponential backoff cap
- `retryable=True`, `status_code`, `code`, `status`,
  `response.status_code` 기반 retry 판단
- invalid retry config

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_rate_limiter.py tests/test_retry.py -q`
  -> `19 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `86 passed`

따라서 이 문서의 "P0. Rate limiter / retry 테스트 복구" 항목은 완료된 것으로
보고, 다음 비용 없는 후보는 generation/pipeline model validation 또는 Veo
provider failure classification입니다.
