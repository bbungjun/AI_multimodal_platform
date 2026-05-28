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

2026-05-27 추가 확인 결과, cancel endpoint는 복구 대상에서 제외하는 것이
맞습니다. 초기 구현 계획과 일부 오래된 phase 메모에는
`POST /api/generations/{id}/cancel`이 등장하지만, 후반 제출 정합성 문맥에서는
`cancelled` state만 terminal state로 유지하고 user-facing cancel API/UI는
구현하지 않는 것으로 정리되어 있습니다.

확인 근거:

- `memories/architecture.md`는 현재 구현 route 목록에서 cancel endpoint를
  "Not implemented as standalone endpoints"로 분류합니다.
- `pre_context/krafton_assignment_14.md`에는 "Do not claim there is a
  user-facing cancel button or cancel API"와 "cancelled state exists, but no
  cancel action is implemented" 정리 문구가 있습니다.
- 현재 `README.md` API 표에는 cancel endpoint가 없고, `cancelled`는 state
  machine terminal state와 deletion 대상 상태로만 설명됩니다.
- 현재 코드 검색에서도 `backend/app/api/*`에는 cancel route가 없고,
  frontend는 `cancelled` 표시/삭제 가능 상태만 다룹니다.

결론: `cancelled` state는 유지하되, `POST /api/generations/{id}/cancel`과
cancel button은 이번 복구에서 구현하지 않습니다. 구현하면 원 제출물 복구가
아니라 새 기능 추가에 가까우므로 보류합니다.

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

## Follow-up: generation / pipeline model validation tests restored

2026-05-27 후속 작업에서 `generation/pipeline model validation` 테스트 묶음을
복구했습니다. production code 변경은 필요하지 않았고, 현재 API validation
구현이 README와 최종 요약의 model-family contract를 이미 만족하는 것을
자동 테스트로 고정했습니다.

추가된 계약:

- `/api/generations` T2I request는 Veo model을 거절합니다.
- `/api/generations` T2V request는 Imagen model을 거절합니다.
- `/api/generations` I2V request는 source asset 조회 전에 Imagen model을
  거절합니다.
- `/api/pipelines`는 `video_model`에 Imagen model이 들어오면 거절합니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py -q`
  -> `19 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `90 passed`

다음 비용 없는 P0/P1 후보는 Veo provider failure classification입니다.

## Follow-up: Veo provider failure classification restored

2026-05-27 후속 작업에서 Veo provider failure classification 테스트와 최소
분류 로직을 복구했습니다. 실제 Vertex/Veo 호출은 하지 않았고 fake operation
객체로만 검증했습니다.

복구한 계약:

- `operation.error`에 safety/filter 신호가 있으면
  `vertex_operation_failed`가 아니라 `vertex_safety_blocked`로 분류합니다.
- 완료된 operation이 video bytes를 주지 않더라도 filtered/safety reason이
  있으면 `vertex_output_unavailable`이 아니라 `vertex_safety_blocked`로
  분류합니다.
- T2V handler는 safety blocked provider error를 terminal failed job의
  public error payload로 저장하고 asset file을 만들지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_vertex_veo.py tests/test_job_handlers.py -q`
  -> `16 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `93 passed`

다음 비용 없는 후보는 T2I multi-image gallery / per-image I2V handoff 또는
`/files` range edge case입니다.

## Follow-up: `/files` Range edge cases restored

2026-05-27 후속 작업에서 `/files/{job_uuid}/{filename}` Range handling의
edge case 테스트와 최소 parsing 보강을 복구했습니다. 실제 provider 호출은
없고, 임시 `DATA_DIR`에 저장한 local fixture bytes만 사용했습니다.

복구한 계약:

- explicit single range: `Range: bytes=2-4` -> `206 Partial Content`
- open-ended range: `Range: bytes=3-` -> `206 Partial Content`
- suffix range: `Range: bytes=-2` -> `206 Partial Content`
- unsatisfiable range: `Range: bytes=99-100` -> `416` with
  `Content-Range: bytes */{size}`
- unsupported multiple ranges: `Range: bytes=0-1,3-4` -> `400`
- unsupported range unit: `Range: items=0-1` -> `400`

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_storage.py -q`
  -> `10 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `98 passed`

다음 비용 없는 후보는 T2I multi-image gallery / per-image I2V handoff입니다.

## Follow-up: T2I multi-image gallery / per-image I2V handoff restored

2026-05-27 후속 작업에서 T2I `number_of_images > 1` 결과 표시와 각 image별
I2V handoff 흐름을 복구했습니다. 실제 Vertex/Imagen/Veo 호출은 하지 않았고,
실행 중인 Docker Compose mock 환경의 deterministic image bytes만 사용했습니다.

복구한 계약:

- completed T2I job에 image asset이 여러 개 있으면 Job Detail에서 첫 번째
  asset만 보여주지 않고 gallery/grid로 모두 표시합니다.
- 각 image card에서 `Start I2V`를 누르면 해당 image asset id를
  `/generate?mode=i2v&source_asset_id=...`로 전달합니다.
- `/generate` I2V 진입 화면은 `source_asset_id`의 image asset을 조회해
  cinema 영역에 source image preview를 다시 표시합니다.
- source image가 연결되고 motion prompt가 있으면 I2V `Generate` 버튼이
  활성화됩니다.
- 단일 image 결과와 video 결과의 기존 preview 흐름은 유지합니다.

검증 결과:

- `cd frontend && npm run lint`
  -> pass
- `cd frontend && npm run build`
  -> pass
- `cd backend && AI_PROVIDER=mock python -m pytest`
  -> `98 passed`
- Docker Compose mock browser smoke:
  - mock T2I job `092d2907-56e2-49f7-9bdb-0b75c9eeb97a`
  - API `asset_count=4`
  - Job Detail에서 `4 Image Results Ready`, Image 1~4, 각 `Start I2V` 확인
  - Image 2 버튼 클릭 후
    `/generate?mode=i2v&source_asset_id=da2b17d8-6cf9-4872-a779-2a92d90c22aa`
    이동 확인
  - Generate 화면에 `Selected I2V source asset da2b17d8-...` image preview
    표시 확인
  - motion prompt 입력 후 I2V `Generate` 버튼 enabled 확인

브라우저 console의 남은 메시지는 개발 모드 React DevTools 안내, React Router v7
future flag 경고, `/favicon.ico` 404이며 pipeline 실패 신호는 아닙니다.

다음 비용 없는 후보는 Prompt Enhancement/History 같은 frontend flow browser
smoke 절차를 문서화하거나, cancel endpoint가 실제 최종 제출 범위였는지 근거를
추가 확인하는 것입니다.

## Follow-up: frontend browser smoke runbook added

2026-05-27 후속 작업에서 Prompt Enhancement, History filter/delete,
T2I multi-image handoff, Pipeline 흐름을 비용 없이 확인하는 수동 browser smoke
절차를 `memories/recovery/frontend-browser-smoke-runbook.md`로 분리했습니다.

이 runbook은 새 frontend test framework를 도입하지 않는 복구 규칙을 유지하면서,
검수자가 `AI_PROVIDER=mock` Compose 환경에서 핵심 사용자 흐름을 재현할 수 있게
합니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 포함하지 않습니다.

같은 세션에서 cancel endpoint도 추가 확인했으며, 최종 제출 범위에서는
user-facing cancel API/UI가 아니라 `cancelled` terminal state만 유지하는 것으로
정리했습니다.

## Follow-up: Vertex auth/permission/quota/transient error mapping restored

2026-05-27 후속 작업에서 Vertex/Gemini provider exception을 public error code로
분류하는 범위를 보강했습니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 하지 않았고,
fake exception 객체만 사용했습니다.

복구한 계약:

- HTTP `401` 또는 Google RPC `UNAUTHENTICATED`/code `16`은
  `vertex_authentication_failed`로 분류합니다.
- HTTP `403` 또는 Google RPC `PERMISSION_DENIED`/code `7`은
  `vertex_permission_denied`로 분류합니다.
- HTTP `429` 또는 Google RPC `RESOURCE_EXHAUSTED`/code `8`은
  retryable `vertex_rate_limited`로 분류합니다.
- HTTP `408/5xx` 또는 Google RPC `DEADLINE_EXCEEDED`, `INTERNAL`,
  `UNAVAILABLE`/code `4/13/14`는 retryable `vertex_transient_error`로
  분류합니다.
- Google RPC `INVALID_ARGUMENT`/code `3` 같은 request invalid 계열은
  `vertex_request_invalid`로 분류합니다.
- raw provider message, credential path, service-account filename은 public
  error message에 노출하지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_vertex_errors.py -q`
  -> `3 passed`
- `AI_PROVIDER=mock python -m pytest tests/test_vertex_errors.py tests/test_vertex_imagen.py tests/test_vertex_veo.py tests/test_prompt_enhancer.py -q`
  -> `18 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `101 passed`

다음 비용 없는 후보는 state machine 전체 transition matrix, delete 중
파일 누락/DB-파일 불일치 처리, job runner semaphore/concurrency, health DB
down/provider down 조합, Prompt Enhancement fenced/긴 응답 명시 테스트입니다.

## Follow-up: state machine transition matrix tests restored

2026-05-27 후속 작업에서 state machine의 전체 transition matrix를 명시적인
자동 테스트로 고정했습니다. production code 변경은 필요하지 않았고, 현재
`app/state_machine.py` 구현이 README와 pre_context에 남아 있는 최종 제출 계약과
일치함을 확인했습니다.

복구한 계약:

- `pending`은 `enhancing`, `queued`, `failed`, `cancelled`로만 이동합니다.
- `enhancing`은 `queued`, `failed`, `cancelled`로만 이동합니다.
- `queued`는 `generating`, `failed`, `cancelled`로만 이동합니다.
- `generating`은 `polling`, `downloading`, `failed`, `cancelled`로만 이동합니다.
- `polling`은 Veo polling heartbeat/resume을 위해 `polling` 자기 전이를
  허용하고, `downloading`, `failed`, `cancelled`로 이동할 수 있습니다.
- `downloading`은 `completed`, `failed`, `cancelled`로만 이동합니다.
- `completed`, `failed`, `cancelled`는 terminal state로 모든 outgoing transition을
  거절하며, 실패한 transition은 job state, `updated_at`, `state_history`를
  변경하지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_state_machine.py -q`
  -> `10 passed`

다음 비용 없는 후보는 delete 중 파일 누락/DB-파일 불일치 처리,
job runner semaphore/concurrency, health DB down/provider down 조합,
Prompt Enhancement fenced/긴 응답 명시 테스트입니다.

## Follow-up: job runner semaphore/concurrency tests restored

2026-05-27 후속 작업에서 FastAPI in-process job runner의 concurrency 계약을
자동 테스트로 고정했습니다. production code 변경은 필요하지 않았고, 실제
Vertex/Gemini/Imagen/Veo 호출 없이 fake handler와 fake session만 사용했습니다.

복구한 계약:

- `poll_once()`는 이미 실행 중인 handler task가 concurrency slot을 모두 점유하고
  있으면 추가 pending job을 조회/claim하지 않습니다.
- concurrency가 1인 상태에서 첫 번째 job handler가 진행 중이면 두 번째 pending
  job은 `pending` 상태로 남습니다.
- `_run_job()`은 직접 여러 task로 호출되어도 `asyncio.Semaphore`를 통해 실제
  handler 동시 실행 수를 설정값 이하로 제한합니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_job_runner.py -q`
  -> `7 passed`

다음 비용 없는 후보는 delete 중 파일 누락/DB-파일 불일치 처리,
health DB down/provider down 조합, Prompt Enhancement fenced/긴 응답 명시
테스트입니다.

## Follow-up: Prompt Enhancement JSON hardening tests restored

2026-05-27 후속 작업에서 Gemini prompt enhancement 응답 parser hardening을
명시적인 자동 테스트로 고정했습니다. production code 변경은 필요하지 않았고,
fake Gemini response 객체만 사용했습니다.

복구한 계약:

- Gemini가 markdown fenced JSON block 형태로 JSON을 반환해도 retry 없이
  파싱합니다.
- Gemini 응답 앞뒤에 설명문이 섞여 있어도 balanced top-level JSON object만
  추출해 schema validation을 통과시킵니다.
- 잘린 JSON처럼 보이는 malformed response는 `malformed_json` /
  `source=text`로 분류하고, diagnostic log에는 `possible_truncated_json=True` 같은
  safe metadata만 남깁니다.
- malformed diagnostic log에는 raw response body를 그대로 남기지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_prompt_enhancer.py -q`
  -> `7 passed`

다음 비용 없는 후보는 health DB down/provider down 조합, delete 중
파일 누락/DB-파일 불일치 처리입니다.

## Follow-up: health DB/provider readiness matrix tests restored

2026-05-27 후속 작업에서 `/api/health`의 DB readiness와 Vertex provider
readiness 분리 계약을 더 넓게 고정했습니다. 실제 DB 장애나 Vertex 호출은 만들지
않고, `check_db_connection`과 `get_vertex_readiness`만 fake로 대체했습니다.

복구한 계약:

- health endpoint 자체는 readiness가 false여도 HTTP `200 OK`로 응답합니다.
- DB가 down이면 provider가 ready여도 `ok=false`, `ready=false`, `db=down`입니다.
- DB와 provider가 모두 down이면 `ok=false`, `ready=false`, `db=down`이고
  provider readiness detail은 그대로 응답에 포함됩니다.
- 전체 `ready`는 `db_up and vertex.ready`이며, `ok`는 DB 연결 상태를 따릅니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_health.py -q`
  -> `4 passed`

다음 비용 없는 후보는 delete 중 파일 누락/DB-파일 불일치 처리입니다.

## Follow-up: delete storage mismatch edge tests restored

2026-05-27 후속 작업에서 `DELETE /api/generations/{job_id}`의 storage/DB 불일치
edge case를 자동 테스트로 고정했습니다. 원래 테스트 파일을 byte-for-byte로 되살린
것은 아니고, pre_context에 남아 있는 원 제출 계약을 현재 `test_generation_api.py`
구조에 맞춰 복구한 것입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `pre_context/krafton_assignment_13.md`에는 deletion 중 missing asset file은
  non-fatal로 처리하되 unsafe stored path는 reject한다는 계획이 남아 있습니다.
- `pre_context/krafton_assignment_13.md`의 당시 변경 요약에는 safe asset file
  deletion과 unsafe path backend coverage가 기록되어 있습니다.
- `pre_context/krafton_assignment_14.md` fact-check에는 deletion이
  `storage.delete_file(asset.local_path, missing_ok=True)`를 호출하고,
  `StoragePathError`가 발생하면 HTTP 409를 반환하며 job을 삭제하지 않는다고
  정리되어 있습니다.

복구한 계약:

- DB에는 asset row가 남아 있지만 실제 asset file/job directory가 없어도 terminal
  job 삭제는 `204 No Content`로 완료되고 job row 삭제가 진행됩니다.
- DB에 저장된 asset `local_path`가 unsafe하면 API는 `409 Conflict`를 반환하고,
  job row 삭제와 commit을 수행하지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_generation_api.py -q`
  -> `15 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `115 passed`

## Follow-up: Prompt Enhancement mode guidance tests restored

2026-05-27 후속 작업에서 Prompt Enhancement의 mode별 guidance와 exemplar
component 계약을 자동 테스트로 고정했습니다. 원래 테스트 파일을 그대로 복구한 것은
아니고, 최종 제출 후반부에 정리된 Prompt Enhancement Strategy를 현재
`test_prompt_enhancer.py` 구조에 맞춰 복구한 것입니다. 실제 Vertex/Gemini 호출은
없고 fake Gemini client만 사용했습니다.

복구 근거:

- `pre_context/summaries/11-summary.md`는 T2I exemplar component keys를
  `subject`, `setting`, `composition`, `lighting`, `style`, `mood` 중심으로
  정리합니다.
- `pre_context/summaries/11-summary.md`는 Video exemplar component keys를
  `subject`, `motion`, `camera_work`, `continuity`, `duration`, `sound_cue`
  중심으로 정리합니다.
- `pre_context/summaries/11-summary.md`와 `12-summary.md`는 creativity preset과
  temperature mapping이 `backend/app/prompt_enhancement.py`에 있고,
  T2I/T2V/I2V guidance split과 sectioned prompt가 `enhancer.py`에 있다고
  확인합니다.
- `pre_context/summaries/15-summary.md`는 I2V가 T2V motion guidance에 source
  image 보존 제약을 추가한다고 정리합니다.

복구한 계약:

- T2I enhancement prompt는 image guidance, T2I exemplar, Balanced strategy,
  `0.5` temperature를 포함하고 I2V source image 보존 문구를 섞지 않습니다.
- I2V enhancement prompt는 video guidance, source image fixed-reference 보존
  제약, Video exemplar, Imaginative strategy, `0.8` temperature를 포함합니다.
- 사용자 prompt는 delimiter 사이의 data로 전달되어 prompt injection 경계를 유지합니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_prompt_enhancer.py -q`
  -> `9 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `117 passed`

## Follow-up: Prompt API validation failure tests restored

2026-05-27 후속 작업에서 `POST /api/prompts/enhance` request validation 실패
계약을 자동 테스트로 고정했습니다. 원래 테스트 파일을 그대로 되살린 것은 아니고,
Phase 9 기록에 남아 있는 `PromptEnhanceRequest` schema validation과 "422,
enhancer not called" 계약을 현재 `test_prompt_api.py` 구조에 맞춰 복구한
것입니다. 실제 Vertex/Gemini 호출은 없습니다.

복구 근거:

- `pre_context/summaries/06-summary.md`는 Unit 1에 `PromptEnhanceRequest`와
  API contract/schema validation 테스트가 추가되었다고 정리합니다.
- `pre_context/krafton_assignment_06.md`는 실패 케이스로 빈 prompt, invalid
  mode/model validation, 실패 시 `PromptEnhancement` row 미생성을 명시합니다.
- 같은 기록은 `/api/prompts/enhance` validation error가 FastAPI/Pydantic
  `422`이며 enhancer를 호출하지 않는다고 정리합니다.
- `README.md`는 prompt enhancement request shape를 `prompt`, `target_mode`,
  `target_model`, `creativity_preset`으로 설명합니다.

복구한 계약:

- 빈 `prompt`는 `422`로 거절되고 enhancer/Gemini 경계로 넘어가지 않습니다.
- invalid `target_mode`는 `422`로 거절되고 enhancer/Gemini 경계로 넘어가지 않습니다.
- 빈 `target_model`은 `422`로 거절되고 enhancer/Gemini 경계로 넘어가지 않습니다.
- invalid `creativity_preset`은 `422`로 거절되고 enhancer/Gemini 경계로 넘어가지 않습니다.
- 모든 validation 실패 케이스는 `PromptEnhancement` row 저장, commit, refresh를
  수행하지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_prompt_api.py -q`
  -> `6 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `121 passed`

## Follow-up: generation list filter/pagination tests restored

2026-05-27 후속 작업에서 `GET /api/generations` History list query contract를
자동 테스트로 보강했습니다. 원래 테스트 파일을 byte-for-byte로 복구한 것은 아니고,
README와 pre_context에 남아 있는 최종 제출 계약을 현재 `test_generation_api.py`
구조에 맞춰 복구한 것입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md:80`은 History가 `mode`, `state`, `model`, page size, asset type
  filter를 제공한다고 설명합니다.
- `README.md:92`는 `GET /api/generations`가 `mode`, `state`, `model`,
  `asset_kind`, pagination 조건으로 job history를 조회한다고 명시합니다.
- `memories/recovery/readme-contract-checklist.md:49`는 같은 query contract를
  검증됨으로 기록합니다.
- `pre_context/krafton_assignment_13.md:2647-2652`는
  `asset_kind=image|video`, no-filter list, invalid `asset_kind` validation을
  당시 복구/구현 항목으로 남깁니다.
- `pre_context/krafton_assignment_14.md:3462-3463`은 frontend가 `mode`,
  `asset_kind`, `state`, `model`, `limit`, `offset`을 보내고 backend
  `list_generations`가 이를 지원한다고 정리합니다.

복구한 계약:

- `mode=t2v`, `asset_kind=video`, `model=veo-3.0-fast-generate-001`,
  `state=failed`, `limit=2`, `offset=1` 조합이 SQLAlchemy select statement에
  모두 반영됩니다.
- list response는 filtered job의 video asset DTO와 `/files/{job_id}/output.mp4`
  URL을 유지합니다.
- invalid `asset_kind=audio`, `limit=0`, `limit=101`, `offset=-1`은
  FastAPI/Pydantic `422`로 거절되며 DB scalar query를 실행하지 않습니다.

검증 결과:

- `AI_PROVIDER=mock python -m pytest tests/test_generation_api.py -q`
  -> `20 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `126 passed`

## Follow-up: pipeline read child lookup/order tests restored

2026-05-27 후속 작업에서 `GET /api/pipelines/{parent_job_id}` read API가
pipeline child를 조회하는 조건과 stable ordering 계약을 자동 테스트로 고정했습니다.
새 기능 개발이 아니라 Phase 10 pipeline read contract와 현재 구현의 정합성을
테스트로 복구한 것입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md:96`은 `GET /api/pipelines/{parent_job_id}`가 pipeline parent와
  연결된 I2V child job의 진행 상태를 조회한다고 설명합니다.
- `memories/phase/phase10.md:23`은 해당 endpoint가 `{id, parent, child}`를
  반환한다고 정리합니다.
- `memories/phase/phase10.md:60`은 어떤 이유로든 child가 여러 개 있으면
  가장 먼저 생성된 child를 반환하고 fan-out 지원은 Phase 10 범위에서 제외한다고
  명시합니다.
- `pre_context/summaries/09-summary.md:29-31`은 pipeline live QA 중
  `child.parent_job_id`, `source_asset_id`, `/api/pipelines/{parent}` 조회가
  함께 살아 있어야 pipeline 복구가 맞다는 단서를 남깁니다.

복구한 계약:

- pipeline detail read는 먼저 parent job을 UUID로 조회합니다.
- child lookup query는 `parent_job_id`와 `mode=i2v` 조건을 함께 사용합니다.
- child lookup query는 `created_at`, `id` 순서로 정렬해 여러 child row가 있을 때
  stable하게 첫 번째 child를 선택합니다.
- malformed `parent_job_id` path 값은 FastAPI/Pydantic `422`로 거절되며 DB
  parent lookup이나 child scalar query를 실행하지 않습니다.

검증 결과:

- mutation RED: `_get_pipeline_child`의 `ORDER BY jobs.id`를 임시 제거하면
  `test_get_pipeline_queries_i2v_child_by_parent_with_stable_ordering`이 실패함을
  확인한 뒤 원복했습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_pipeline_api.py -q`
  -> `8 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `128 passed`

## Follow-up: asset API video DTO / validation tests restored

2026-05-27 후속 작업에서 `GET /api/assets/{asset_id}`의 asset metadata DTO와
path validation 계약을 조금 더 촘촘하게 고정했습니다. 원래 테스트 파일을
byte-for-byte로 복구한 것은 아니고, README와 pre_context에 남아 있는 asset detail
endpoint / I2V source preview 계약을 현재 `test_asset_api.py` 구조에 맞춰 복구한
것입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md:97`은 `GET /api/assets/{asset_id}`가 asset metadata와 `/files/...`
  URL을 조회한다고 설명합니다.
- `pre_context/summaries/09-summary.md:40`은 Asset detail endpoint가 추가됐고,
  복구 시 job/asset metadata를 안전하게 반환하며 `/files` serving과 일관되는지
  확인해야 한다고 정리합니다.
- `pre_context/summaries/13-summary.md:29`는
  `/generate?mode=i2v&source_asset_id=...` 진입 시 `getAsset(assetId)`로 source
  asset을 조회한다고 기록합니다.
- `memories/recovery/readme-contract-checklist.md:36`과 `:54`는 Generate/JobDetail
  source preview가 `GET /api/assets/{source_asset_id}` / `useAsset` 경로를 사용한다고
  기록합니다.

복구한 계약:

- video asset도 image asset과 동일하게 `id`, `job_id`, `kind`, `local_path`,
  `mime`, `size_bytes`, `width`, `height`, `duration_sec`, `created_at`,
  `/files/{local_path}` URL을 포함한 DTO로 반환됩니다.
- malformed `asset_id` path 값은 FastAPI/Pydantic `422`로 거절되며 DB asset lookup을
  실행하지 않습니다.
- missing UUID 형태의 asset은 기존대로 DB lookup 후 `404 Asset was not found.`를
  반환합니다.

검증 결과:

- mutation RED: `AssetResponse.url`에서 `/files/` prefix를 임시 제거하면
  `test_get_asset_returns_video_metadata_with_file_url`이 실패함을 확인한 뒤
  원복했습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_asset_api.py -q`
  -> `4 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `130 passed`

## Follow-up: generation option validation boundary tests restored

2026-05-27 후속 작업에서 `POST /api/generations` request option validation 경계값을
자동 테스트로 고정했습니다. 새 기능 개발이 아니라 README에 남아 있는 generation
option contract와 현재 Pydantic schema의 제출 복구 상태를 테스트로 묶은 것입니다.
실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md:73`은 생성 옵션으로 image aspect ratio, image count, video duration,
  I2V source image 연결을 지원한다고 설명합니다.
- `README.md:124-137`은 T2I 예시에서 `aspect_ratio`, `number_of_images`를,
  T2V 예시에서 `aspect_ratio`, `duration_sec`를 request shape로 보여줍니다.
- `memories/recovery/readme-contract-checklist.md:32`는 생성 옵션이 Pydantic request
  schema, Generate 화면 옵션, pipeline payload, source asset 검증으로 확인됐다고
  기록합니다.
- `memories/recovery/frontend-browser-smoke-runbook.md:162-175`는
  `number_of_images=4` T2I mock smoke와 4개 image card 표시를 복구 절차로 남깁니다.
- 현재 `backend/app/schemas.py`는 generation request option을
  `number_of_images=1..4`, `duration_sec=1..8`, `aspect_ratio` 길이 `3..16`으로
  제한합니다.

복구한 계약:

- T2I `number_of_images=4`는 유효한 상한값이며 job parameters에 보존됩니다.
- T2V `duration_sec=8`은 유효한 상한값이며 job parameters에 보존됩니다.
- T2I `number_of_images=0` 또는 `5`는 `422`로 거절되며 job row를 만들지 않습니다.
- T2V `duration_sec=0` 또는 `9`는 `422`로 거절되며 job row를 만들지 않습니다.
- 너무 짧거나 너무 긴 `aspect_ratio`는 `422`로 거절되며 job row를 만들지 않습니다.

검증 결과:

- mutation RED: `T2IRequest.number_of_images` 상한을 임시로 `3`으로 낮추면
  `test_create_t2i_generation_accepts_max_image_count_boundary`가 실패함을 확인한 뒤
  원복했습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_generation_api.py -q`
  -> `28 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `138 passed`

## Follow-up: pipeline option validation boundary tests restored

2026-05-27 후속 작업에서 `POST /api/pipelines` request option validation
경계값을 자동 테스트로 고정했습니다. 새 기능 개발이 아니라 README의 pipeline
payload 예시와 현재 `PipelineCreateRequest` schema에 남아 있는 제출 계약을
복구한 것입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md:73`은 생성 옵션으로 image aspect ratio, image count,
  video duration, I2V source image 연결을 지원한다고 설명합니다.
- `README.md:162-164`는 `/api/pipelines` 예시 payload에
  `image_aspect_ratio`, `video_aspect_ratio`, `duration_sec`를 포함합니다.
- `memories/recovery/readme-contract-checklist.md:32`는 생성 옵션이
  Pydantic request schema, Generate 화면 옵션, pipeline payload, source asset
  검증으로 확인됐다고 기록합니다.
- 현재 `backend/app/schemas.py`는 pipeline option을
  `duration_sec=1..8`, `image_aspect_ratio`/`video_aspect_ratio` 길이 `3..16`으로
  제한합니다.

복구한 계약:

- Pipeline `duration_sec=8`은 유효한 상한값이며 child I2V job parameters에
  보존됩니다.
- Pipeline `duration_sec=0` 또는 `9`는 `422`로 거절되며 parent/child job을
  만들지 않습니다.
- 너무 짧거나 너무 긴 `image_aspect_ratio`, `video_aspect_ratio`는 `422`로
  거절되며 parent/child job을 만들지 않습니다.

검증 결과:

- mutation RED: `PipelineCreateRequest.duration_sec` 상한을 임시로 `7`로 낮추면
  `test_create_pipeline_accepts_max_duration_boundary`가 `422 != 201`로 실패함을
  확인하고 되돌렸습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_pipeline_api.py -q`
  -> `15 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `145 passed`

## Follow-up: delete source asset dependency guard restored

2026-05-27 후속 작업에서 `DELETE /api/generations/{job_id}`가 target job의
asset을 `source_asset_id`로 참조하는 active dependent job을 보호하는 계약을
자동 테스트로 고정했습니다. 기존 missing file/unsafe path 테스트를 중복한 것이
아니라, ERD에서 `assets.id -> jobs.source_asset_id` 관계를 설명할 때 필요한
active dependency 보호를 더 명시적으로 복구한 것입니다. 실제
Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md:81`과 `README.md:94`는 terminal job deletion을 지원하되 active
  dependent job이 있으면 삭제를 거절한다고 설명합니다.
- `README.md:50`은 parent T2I image asset이 child I2V의 `source_asset_id`로
  연결된다고 설명합니다.
- `pre_context/summaries/13-summary.md:53-54`는 terminal dependent는
  `parent_job_id`/`source_asset_id`를 detach하고, active dependent가 있으면
  삭제를 차단한다고 정리합니다.
- `pre_context/krafton_assignment_14.md:2987-2995`는 deletion이
  `parent_job_id` 참조와 asset ids를 사용하는 `source_asset_id` 참조를 모두
  찾고, non-terminal reference가 있으면 409로 막는다고 fact-check합니다.

복구한 계약:

- target job의 asset을 active I2V job이 `source_asset_id`로 참조하고 있으면,
  target job이 terminal이어도 삭제는 `409 Conflict`로 거절됩니다.
- 이 경우 asset file 삭제, job row 삭제, commit, dependent reference detach를
  수행하지 않습니다.
- `parent_job_id` 없이 `source_asset_id`만 남은 dependent도 보호 대상입니다.

검증 결과:

- mutation RED: `_jobs_referencing_job`에서 `source_asset_id` reference 조회를
  임시 제거하면 `test_delete_generation_rejects_active_source_asset_dependent_job`가
  `204 != 409`로 실패함을 확인하고 되돌렸습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_generation_api.py -q`
  -> `29 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `146 passed`

## Follow-up: PromptEnhancement to Job linkage guard tests restored

2026-05-27 후속 작업에서 `prompt_enhancements.id -> jobs.enhancement_id` 관계의
generation-side 검증 계약을 보강했습니다. 새 기능 개발이 아니라 ERD 설명 노트와
최종 Prompt Enhancement strategy에 남아 있는 "review/edit/accept 후 선택적으로
job에 연결"되는 계약을 현재 `test_generation_api.py` 구조에 맞춰 복구한 것입니다.
실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md`는 prompt enhancement가 generation 요청에 자동 적용되지 않고,
  사용자가 확인/편집/수락한 뒤 generation payload의 `prompt`와 `enhancement_id`로
  전달된다고 설명합니다.
- `pre_context/summaries/06-summary.md`는 Phase 9 Unit 5 후보로 existing
  `enhancement_id` generation linkage를 남기고, `auto_enhance=True` 자동 실행은
  계속 차단해야 한다고 정리합니다.
- `pre_context/summaries/15-summary.md`는 수락된 enhancement가 `enhancement_id`로
  연결되고, generation API가 target mode/model mismatch를 다시 검증한다고
  정리합니다.
- `memories/recovery/erd-explanation-note.md`는 `PromptEnhancement`가 검토 가능한
  초안이며, job에는 optional FK로만 연결된다고 설명합니다.

복구한 계약:

- 존재하지 않는 `enhancement_id`를 generation 요청에 넣으면 `400`으로 거절하고
  job row를 만들지 않습니다.
- `PromptEnhancement.target_mode`가 generation `mode`와 다르면 `400`으로 거절하고
  job row를 만들지 않습니다.
- `PromptEnhancement.target_model`이 generation `model`과 다르면 `400`으로 거절하고
  job row를 만들지 않습니다.
- matching enhancement만 `Job.enhancement_id`와 `Job.enhanced_prompt`에 연결됩니다.

검증 결과:

- mutation RED: `_get_matching_prompt_enhancement`에서 `target_model` 비교를 임시로
  제거하면 `test_create_generation_rejects_prompt_enhancement_target_mismatch_without_job`
  중 model mismatch case가 `201 != 400`으로 실패함을 확인하고 되돌렸습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_generation_api.py -q`
  -> `32 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `149 passed`

## Follow-up: ERD SQLAlchemy relationship contract tests restored

2026-05-27 후속 작업에서 ERD 설명에 필요한 SQLAlchemy model-level FK와
relationship 계약을 자동 테스트로 고정했습니다. 새 기능 개발이 아니라
`README.md`, ERD 설명 노트, 현재 `backend/app/models.py`에 남아 있는 관계를
검증 가능하게 만든 것입니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없습니다.

복구 근거:

- `README.md`는 PostgreSQL tables를 `jobs`, `assets`, `prompt_enhancements`로
  설명하고, asset metadata는 DB에 저장하고 bytes는 local `DATA_DIR`에 둔다고
  설명합니다.
- `memories/recovery/erd-explanation-note.md`는
  `PromptEnhancement -> Job`, `Job -> Asset`, `Job -> Job`,
  `Asset -> Job` 관계를 ERD 설명 핵심으로 정리합니다.
- 현재 `backend/app/models.py`는 optional linkage는 `SET NULL`, job 소유 asset은
  `CASCADE`/`delete-orphan`으로 표현합니다.

복구한 계약:

- `jobs.enhancement_id`, `jobs.parent_job_id`, `jobs.source_asset_id`는 nullable
  optional FK이며 삭제 시 `SET NULL`로 detach됩니다.
- `assets.job_id`는 nullable이 아닌 owned FK이며 job 삭제 시 `CASCADE`됩니다.
- `Job.assets` relationship은 generated asset row를 소유하고
  `delete-orphan` cascade를 유지합니다.
- `Job.enhancement`와 `PromptEnhancement.jobs`는 optional accepted draft linkage의
  양방향 relationship입니다.

검증 결과:

- mutation RED: `jobs.source_asset_id`의 `ondelete`를 임시로 `CASCADE`로 바꾸면
  `test_job_optional_foreign_keys_detach_on_parent_deletion`이 실패함을 확인하고
  되돌렸습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_model_relationships.py -q`
  -> `4 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `153 passed`

## Follow-up: `/files` response header detail tests restored

2026-05-27 후속 작업에서 `/files/{job_uuid}/{filename}` streaming response의
header detail 계약을 조금 더 촘촘하게 고정했습니다. 실제 Vertex/Gemini/Imagen/Veo
호출은 없고, 임시 `DATA_DIR`에 저장한 local fixture bytes만 사용했습니다.

복구 근거:

- `README.md`는 `/files/{job_uuid}/{filename}`가 검증된 asset streaming을 제공하고,
  video preview를 위해 single byte range request를 지원한다고 설명합니다.
- `pre_context/summaries/13-summary.md`는 History video preview를 복구할 때
  thumbnail 생성보다 `/files` Range support와 frontend `<video>` preview 흐름을
  먼저 확인하라고 정리합니다.
- `pre_context/krafton_assignment_15.md`는 저장된 MP4 asset을 `<video>` preview로
  렌더링하고, `/files`가 byte range를 지원해 전체 다운로드에 의존하지 않도록
  했다고 설명합니다.

복구한 계약:

- MP4 asset에 대한 partial content 응답은 `206`, `Content-Type: video/mp4`,
  `Accept-Ranges: bytes`, 정확한 `Content-Length`, `Content-Range`를 함께 반환합니다.
- unsatisfiable range 응답은 `416`과 `Content-Range: bytes */{size}`를 반환하면서,
  같은 route가 byte range를 지원한다는 `Accept-Ranges: bytes`도 유지합니다.

검증 결과:

- RED: 416 응답에 `Accept-Ranges`가 없어
  `test_files_route_returns_416_for_unsatisfiable_byte_range`가 실패함을 확인했습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_storage.py -q`
  -> `11 passed`

## Follow-up: job runner orphan sweep polling resume guard restored

2026-05-28 후속 작업에서 FastAPI in-process job runner의 startup recovery edge를
보강했습니다. 실제 Vertex/Gemini/Imagen/Veo 호출은 없고 fake session/job 객체만
사용했습니다.

복구 근거:

- `README.md`는 runner 시작 시 오래된 non-terminal job을 `failed`로 정리하되,
  `polling` 상태이면서 `vertex_operation_name`이 있는 Veo job은 저장된 operation
  name으로 polling을 재개할 수 있어 sweep 대상에서 제외한다고 설명합니다.
- `pre_context/summaries/05-summary.md`는 Phase 8 후반 핵심으로 T2V/I2V resume과
  runner startup orphan sweep을 함께 정리하고, `polling + vertex_operation_name`
  job을 resume task로 스케줄하는 흐름을 강조합니다.
- `pre_context/summaries/14-summary.md`도 Veo job은 polling 단계에서 operation
  name을 저장하고 runner 재시작 시 저장된 operation name으로 재개할 수 있다고
  정리합니다.

복구한 계약:

- stale non-terminal job은 orphan sweep에서 `failed`로 정리됩니다.
- 단, `state=polling`이고 `vertex_operation_name`이 있는 job은 resumable Veo job으로
  간주해 sweep 결과에 포함되더라도 `failed`로 바꾸지 않습니다.
- 이 보호는 SQL query 조건뿐 아니라 sweep 실행 루프 내부에서도 한 번 더 적용됩니다.

검증 결과:

- RED: fake session이 resumable polling job을 sweep result로 반환하면 기존 구현은
  `swept_count=1`로 실패 처리했습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_job_runner.py::test_sweep_orphans_preserves_resumable_polling_jobs -q`
  -> `1 passed`

## Follow-up: job runner startup sweep/resume ordering test restored

2026-05-28 후속 작업에서 `InProcessJobRunner.run_forever()`의 startup 순서
계약을 테스트로 고정했습니다. 새 기능 개발이 아니라 README와 recovery 문서에 남아
있는 runner 재시작 복구 설명을 현재 코드에 묶어 둔 것입니다. 실제
Vertex/Gemini/Imagen/Veo 호출은 수행하지 않았고 fake runner subclass만 사용했습니다.

복구 근거:

- `README.md`는 runner 시작 시 오래된 non-terminal job을 1회 recovery sweep으로
  정리하되, `polling` + `vertex_operation_name` job은 재개 가능하므로 제외한다고
  설명합니다.
- `pre_context/summaries/05-summary.md`는 Phase 8 후반 핵심으로 T2V/I2V resume과
  runner startup orphan sweep을 함께 정리하고, resumable polling job을 resume task로
  스케줄하는 흐름을 강조합니다.
- `memories/phase/phase6.md`는 `run_forever()`가 startup 시 orphan sweep을 먼저
  시도한다고 기록합니다.

복구한 계약:

- `run_forever()`는 startup에서 `sweep_orphans()`를 먼저 호출합니다.
- 그 다음 `resume_polling_jobs()`를 호출해 저장된 operation name을 가진 Veo polling
  job을 재개 대상으로 스케줄합니다.
- 이후 일반 pending job poll loop로 들어갑니다.

검증 결과:

- mutation RED: `run_forever()`에서 `resume_polling_jobs()`를 `sweep_orphans()`보다
  먼저 호출하도록 임시로 뒤집으면
  `test_run_forever_sweeps_orphans_before_resuming_polling_jobs`가
  `['resume', 'sweep', 'poll'] != ['sweep', 'resume', 'poll']`로 실패함을 확인하고
  원복했습니다.
- `AI_PROVIDER=mock python -m pytest tests/test_job_runner.py::test_run_forever_sweeps_orphans_before_resuming_polling_jobs -q`
  -> `1 passed`
- `AI_PROVIDER=mock python -m pytest tests/test_job_runner.py -q`
  -> `9 passed`
- `AI_PROVIDER=mock python -m pytest`
  -> `156 passed`
