# Architecture — Design Decisions

## Tech Stack (confirmed 2026-05-22)

| Layer | Choice | Why |
|---|---|---|
| Backend lang/framework | Python 3.11 + FastAPI | google-genai SDK 성숙도 1위, Veo LRO 처리 편의, pytest 생태계 |
| Frontend | Vite + React + TypeScript + CSS-first UI | 빠른 빌드, 단순 SPA, BE 분리 명확. Tailwind dependency is present, but the current Phase 11 UI uses `index.css` and shared TSX primitives rather than Tailwind utility classes. |
| DB | PostgreSQL 16 | docker-compose 의 "DB 컨테이너" 명시 충족, JSONB 메타데이터, FOR UPDATE SKIP LOCKED 지원 |
| File storage | 로컬 파일 (`/data/assets`) | 과제 요구사항 명시 ("결과 파일은 로컬에 저장") |
| AI SDK | google-genai 단일 SDK | Imagen + Veo + Gemini 모두 동일 SA 키로 호출, 의존성/설정 단일화 |
| Enhance LLM | Gemini 2.5 Flash via Vertex | 추가 SDK 불필요, JSON schema 강제 응답, 저렴 |
| Job orchestration | FastAPI 내부 asyncio 러너 | Celery/Redis 미도입 (3일 일정, 단일 인스턴스 가정) |

기각된 후보:
- Node + NestJS: 코드 구조화 어필은 강하나 Veo LRO 직접 폴링 코드 필요 + 3일 안 완성 리스크
- SQLite: docker-compose "DB 등" 요구사항 충족 약함, Step 2 큐잉 확장 시 제약
- Anthropic SDK 추가: google-genai 로 Gemini 호출하면 SDK 하나로 통일 가능

## API 표면

Current implemented backend routes are defined by `backend/app/api/*` and
included from `backend/app/main.py`.

```
GET    /api/health                         # HealthResponse + nested vertex readiness
POST   /api/prompts/enhance                # 201 PromptEnhancementResponse
POST   /api/generations                    # 201 JobResponse; mode=t2i|t2v|i2v
GET    /api/generations                    # list[JobResponse], filters: mode/model/state/limit/offset
GET    /api/generations/{job_id}           # JobResponse for FE 2s polling
POST   /api/pipelines                      # 201 PipelineResponse; parent T2I + blocked child I2V
GET    /api/pipelines/{parent_job_id}      # PipelineResponse
GET    /files/{local_path:path}            # StreamingResponse for safe DATA_DIR-relative asset paths
```

3가지 생성 모드는 단일 `POST /api/generations` 로 통합 + `mode` discriminator. Pydantic discriminated union 으로 모드별 유효 필드 검증.

Not implemented as standalone endpoints:

- `POST /api/generations/{id}/cancel`: `cancelled` exists as a state, but no
  cancel API/UI is currently implemented.
- `GET /api/assets/{id}`: asset metadata is embedded in `JobResponse.assets` and
  `PipelineResponse.parent/child.assets`; there is no standalone asset route.
- Upload/remix/global search/settings routes are intentionally absent.
- `auto_enhance=true` on generation create currently returns 501; the supported
  frontend flow is explicit `POST /api/prompts/enhance`, edit/accept, then
  generation with a matching `enhancement_id`.

`GET /api/health` returns:

```json
{
  "ok": true,
  "ready": true,
  "service": "backend",
  "db": "up",
  "vertex": {
    "ready": true,
    "status": "ready",
    "credentials": "available",
    "project": "configured",
    "location": "configured-location"
  }
}
```

The nested `vertex` object is `VertexReadinessResponse`. This is the schema
after `c403718 fix: align health response schema`; public readiness fields use
status labels only and must not expose credential contents.

## Job State Machine

```
                ┌─ (auto_enhance=false) ──────┐
   pending ─────┤                             │
                └─ enhancing ─► (LLM call) ───┤
                                              ▼
                                           queued
                                              │
                                              ▼
                                        generating ──(Imagen sync)──┐
                                              │                      │
                                              │ (Veo)                │
                                              ▼                      │
                                          polling ◄──loop──┐         │
                                              │            │         │
                                              └────────────┘         │
                                              ▼                      │
                                        downloading ◄────────────────┘
                                              │
                                              ▼
                                        completed
              (어디서든 에러 → failed, cancelled 상태는 예약/terminal)
```

**상태값**: `pending, enhancing, queued, generating, polling, downloading, completed, failed, cancelled`

**왜 이렇게**:
- `queued` 는 rate-limit 대기 노출용 (요구사항 3.2-3 "유의미한 대기 경험")
- `polling` 은 Veo 전용 (Imagen 잡은 절대 진입 금지, DB validator 강제)
- `downloading` 분리 → Vertex 비용 발생 후 파일 저장 실패 시 정확한 회계 (`vertex_charged=true` 컬럼)
- `state_machine.transition(job, new_state, detail=None)` 함수가 ALLOWED_TRANSITIONS 매트릭스 강제
- `cancelled` is a terminal state in the model/state machine, but the current
  API surface does not expose a user cancel endpoint.

**부가 컬럼**:
- `state_history JSONB`: `[{state, at, detail}]` — FE 타임라인용
- `error JSONB`: `{code, message, retry_count, last_attempt_at}`
- `vertex_operation_name TEXT`: Veo LRO 식별자 (재시작 후 재개용)
- `attempts INT`, `vertex_charged BOOL`
- `parent_job_id FK`, `blocked BOOL`, `source_asset_id FK` — 파이프라인용

## Per-Model Rate Limiter

```python
class SlidingWindowLimiter:
    """슬라이딩 60초 윈도우. capacity = 분당 호출 수."""
    def __init__(self, capacity: int, window_seconds: float = 60.0): ...
    async def acquire(self) -> float:
        # lock 안에서 만료 timestamp 정리, 여유 있으면 즉시,
        # 없으면 lock 풀고 대기 (deadlock 방지);
        # 반환값은 실제 대기한 초 단위 float
```

**등록**:
```python
LIMITERS = {
    "imagen-4.0-fast-generate-001":  SlidingWindowLimiter(75),
    "imagen-4.0-generate-001":       SlidingWindowLimiter(75),
    "imagen-4.0-ultra-generate-001": SlidingWindowLimiter(75),
    "veo-3.0-fast-generate-001":     SlidingWindowLimiter(10),
    "veo-3.0-generate-001":          SlidingWindowLimiter(10),
    "gemini-2.5-flash":              SlidingWindowLimiter(60),
}
```

**왜 슬라이딩 윈도우**: Google "분당 N회" 정책에 정확. 토큰 버킷의 버스트는 위반 위험.

**Current FE 노출**: handler가 `queued`로 전이한 뒤 rate limiter를 통과하면
`generating` state history detail에 `{rate_limit_wait_sec}`를 기록한다.
`queued_position`은 현재 구현되어 있지 않다.

## Retry / Backoff

```python
async def with_retry(fn, *, max_attempts=3, base=1.0, max_delay=20.0,
                     retryable=(429, 500, 502, 503, 504, 408)):
    # 지수 백오프, max_attempts 소진 시 마지막 예외 raise
```

**원칙**:
- HTTP 4xx (사용자 오류) 는 즉시 실패, 재시도 X
- 429/5xx 또는 `retryable=True` 예외만 재시도, max_attempts=3
- 재시도 소진 → 마지막 예외가 handler로 전파되고 `_public_error()`가
  `error.code`, `retry_count`, `last_attempt_at` 등으로 공개 error payload를
  저장한다.
- Veo LRO 폴링은 별도 정책: **총 10분 deadline + per-call 30s timeout, 폴링 간격 5→10→15→30s 가변**

## In-Process Job Runner (no Celery)

- FastAPI `lifespan` 에서 `DATA_DIR` 생성, SQLAlchemy metadata 초기화, 그
  다음 `asyncio.create_task(job_runner())` 시작
- 1초 폴링: `SELECT ... WHERE state='pending' AND blocked=false ORDER BY created_at LIMIT N FOR UPDATE SKIP LOCKED`
- 픽업 잡마다 `asyncio.create_task(handle(job))`, 전역 `Semaphore(10)` 으로 동시성 제한
- 핸들러는 `mode` 별 dispatch (`handle_t2i`, `handle_t2v`, `handle_i2v`)
- 모든 상태 전이는 `state_machine.transition` 경유 → `state_history` 자동 기록

**복구**: 시작 시 sweep — `updated_at < now() - 5m` AND 비종료 상태인 잡은 `failed`. 단 `polling` 상태에 `vertex_operation_name` 있으면 재개 시도.

## Vertex SDK 호출 패턴

**Imagen (동기)**:
```python
resp = await asyncio.to_thread(
    client.models.generate_images,
    model=model_id, prompt=prompt,
    config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
)
image_bytes = resp.generated_images[0].image.image_bytes
```

**Veo (LRO)**:
```python
# 제출
op = await asyncio.to_thread(
    client.models.generate_videos,
    model=model_id, prompt=prompt,
    image=types.Image(image_bytes=src, mime_type="image/png") if i2v else None,
    config=types.GenerateVideosConfig(aspect_ratio="16:9"),
)
job.vertex_operation_name = op.name  # DB persist

# 폴링
deadline = time.monotonic() + 600
interval = 5
while not op.done:
    if time.monotonic() > deadline: raise VeoTimeoutError(op.name)
    await asyncio.sleep(interval)
    interval = min(30, interval * 1.5)
    op = await asyncio.to_thread(client.operations.get, op)

video_bytes = op.result.generated_videos[0].video.video_bytes
```

**GCS 미사용**: 인라인 base64 수신 → 로컬 디스크 저장. 과제 요구사항 일치.

## File Storage

**경로 규칙**:
```
/data/assets/{job_uuid}/output.{png|mp4}
/data/assets/{job_uuid}/source.{png}   # I2V 파이프라인 입력 사본
```

DB `assets` 컬럼: `id, job_id, kind(image|video), local_path(상대), mime, size_bytes, width, height, duration_sec, created_at`.

**서빙 (current implementation)**: `StaticFiles` mount가 아니라
`backend/app/api/files.py`의 `GET /files/{local_path:path}` 라우터가
`StreamingResponse`로 파일을 반환한다. 요청 path는
`storage.resolve_asset_path()`를 통과해야 하며, 형식은
`<job_uuid>/<filename>`이다. `storage.save_bytes()`와 `resolve_asset_path()`가
UUID, filename, symlink/path traversal, DATA_DIR prefix를 검증한다. 파일이
없거나 안전하지 않은 path이면 JSON 404 `Asset file was not found.`를
반환한다.

`AssetResponse.url`은 computed field로 `/files/{local_path}`를 반환한다.
별도 `GET /api/assets/{id}` endpoint는 없다.

## T2I → I2V Pipeline

**모델링**: 별도 `pipelines` 테이블 없음. `jobs.parent_job_id` FK + `jobs.blocked` 플래그로 표현.

**플로우**:
1. `POST /api/pipelines` → parent T2I 잡 (pending) + child I2V 잡 (pending, blocked=true) 동시 생성
2. 러너는 `blocked=true` 픽업 안 함
3. parent → `completed` 전이 시 훅: child.blocked=false, child.source_asset_id=parent.asset.id
4. 다음 틱에 child 픽업, I2V 진행
5. parent → `failed` 면 child 도 `failed` (cascade, `error.cause=parent_failed`)

## Prompt Enhance

**엔드포인트**: `POST /api/prompts/enhance { prompt, target_mode, target_model }` → 동기 응답 (3~10s)

**LLM**: Gemini 2.5 Flash via google-genai (`client.models.generate_content` + `response_mime_type="application/json"` + `response_schema=ComponentsSchema`, temperature=0.3)

**6대 설계 원칙** (AI_COLLABORATION.md 에 풀어 쓸 내용):
1. **모드별 최적화** — Imagen: 공간 디테일 (피사체-배경, 조명, 스타일, 카메라 렌즈/구도). Veo: 시간 단서 (카메라 워크 dolly/pan/zoom, 모션 동사, 사운드 큐, 4~8초 행동 단순화).
2. **컴포넌트 분해** — JSON 응답으로 `subject, environment, style, composition, lighting, camera(video), motion(video), mood` 반환. FE 가 칩 단위 편집 제공.
3. **원본 의도 보존** — 사용자 원본 명사/동사는 삭제/대체 금지, 추가만 허용 (system prompt 명시).
4. **결정성** — temperature=0.3, max_tokens=800. 재현성 확보.
5. **편집 가능성** — `enhanced` 통합 문자열 + `components` 칩 둘 다 반환. 사용자 자유 선택.
6. **추적** — `prompt_enhancements` 테이블에 (original, enhanced, components, llm_model, latency_ms, tokens). 잡 생성 시 `enhancement_id` 연결.

**사용자 흐름**: FE 프롬프트 입력 → Enhance 버튼 → 좌:원본/우:개선 + 컴포넌트 칩 표시 → 편집 → Generate.

## FE 대기 UX

**단순 스피너 금지**. 표시 요소:
- **단계 타임라인**: `pending → enhancing → queued → generating → polling → downloading → completed` 체크리스트형. `JobDetailPage` renders each step plus timestamp from `state_history` when present.
- **현재 메타 표시**:
  - state, attempts, `vertex_charged`, blocked.
  - request summary: mode, model, created/updated timestamps, enhancement id,
    source asset id, prompt, enhanced prompt, parameters.
  - completed asset viewer renders backend-provided asset URLs.
  - failed jobs show backend `error.message` or `error.code`.
- **Not implemented**: live queue position, progress percent, elapsed timer,
  average duration estimate, poll count, and cancel action.
- **취소 버튼**: not implemented in the current frontend/API. `cancelled`
  상태는 존재하지만 사용자 cancel flow는 deferred.
- **결과 영역**: 인라인 미리보기 + 다운로드 + "이 이미지로 비디오 만들기" 진입

**구현**: `useQuery` + `refetchInterval: 2000`, terminal 상태에서 폴링 중단.

## Docker Compose

3 서비스 (db / backend / frontend), `version:` 키 없음 (v1/v2 호환),
Postgres healthcheck + `depends_on.condition: service_healthy`, 자격 증명
read-only 마운트, named volumes (pgdata, assets).

Current compose/frontend API routing:

- Backend binds `0.0.0.0:8000`; frontend dev server binds `0.0.0.0:5173`.
- Frontend `VITE_API_BASE` is normalized in `frontend/src/api/client.ts`.
  Empty/undefined means same-origin relative URLs such as `/api/health` and
  `/files/...`.
- Vite dev server proxies `/api` and `/files` to
  `VITE_API_PROXY_TARGET`; compose defaults that target to
  `http://backend:8000`.
- When `VITE_API_BASE` is non-empty, frontend asset URLs returned as
  `/files/{local_path}` are resolved against that API base. When it is empty,
  the same-origin Vite proxy handles both `/api` and `/files`.
- Phase 12 host smoke verified backend `/api/health`, frontend-origin
  `/api/health`, backend `/files` JSON 404 for a missing safe path,
  frontend-origin `/files` proxy behavior, and frontend root load.

## Test Coverage 범위

**Unit** (모킹 Vertex/LLM): rate_limiter, retry, state_machine, path_safety, enhance (system prompt 선택)

**Integration** (TestClient + 실제 Postgres + 모킹 Vertex/LLM):
- T2I flow (생성→러너 픽업→completed→파일 존재→/files 200)
- T2V flow (polling 3회 후 done)
- Pipeline cascade
- Rate limiter/retry/state/storage/health/file-serving behavior is covered by
  focused backend tests.
- Failure paths store public `error` payloads with code, message, retry count,
  and last attempt timestamp.

**FE 컴포넌트 테스트 / Playwright 미구현** — 시간 제약, README 에 명시.

## 위험 & 완화

| 위험 | 완화 |
|---|---|
| Veo 비용 ($0.40/sec) | 기본 fast 모델, 4초 권장, UI 경고, 테스트 항상 모킹 |
| LRO 무한 대기 | 10분 deadline, UI 에 명시 |
| 단일 인스턴스 SPOF | sweep + polling 잡 재개, AI_COLLABORATION.md 한계 명시 |
| 자격 증명 노출 | gitignore + read-only 마운트 + 로그 마스킹 |
| google-genai API 변화 | 마이너 버전 핀 |
| docker-compose v1/v2 차이 | `version` 키 미선언 |
