# Implementation Plan — 18 Phases


원본 플랜 파일: `/home/user/.claude/plans/readme-md-imperative-yao.md`

## Current Status Update (2026-05-23)

This file began as the original 18-phase implementation plan. The detailed
phase bodies below are retained as historical planning context, but the actual
execution has been rescaled and advanced:

- Backend Phases 1-10 are complete: FastAPI/DB/health, domain models and strict
  state machine, storage/path safety, Vertex client, retry/rate limiting,
  in-process job runner, Imagen T2I, Veo T2V/I2V, Gemini prompt enhancement, and
  T2I -> I2V pipeline APIs/linking.
- Phase 11 completed the required frontend flows unit-by-unit, covering the
  original frontend Phase 11-14 scope: core shell/API client, Generate +
  Enhance review/edit, Job Detail polling/waiting/result/I2V handoff, History,
  and Pipeline launcher/detail UI.
- Phase 12 was explicitly rescoped to Docker Compose / integration readiness and
  is complete: compose env/build hygiene, backend startup schema init and
  `/files` serving, frontend same-origin API/file proxy readiness, compose smoke
  discovery, follow-up health schema fix, and host compose smoke pass.
- README replacement remains deferred until Phase 17. `AI_COLLABORATION.md`
  completion remains deferred until Phase 18.

Key commit anchors:

- `26317fb recovery: import inspected working tree snapshot` restored the
  inspected implementation baseline after git object corruption.
- Phase 8 Veo/T2V/I2V and polling resume: `7af594c` through `80232da`.
- Phase 9 prompt enhance: `b2c95f4`, `2cc0fdb`, `6918a5f`, `7d312c5`,
  `f2aa894`, `5ec75e1`.
- Phase 10 pipeline: `1622326`, `061cc2f`, `98b8c65`, `6aead88`, `7c54abb`.
- Phase 11 frontend required flows: `ef0a5c8`, `23bb054`, `f7916e9`,
  `0095369`, `31a0aba`, `055bd5d`.
- Phase 12 compose readiness and smoke: `e764459`, `3738ad4`, `6133b23`,
  `bd5f4e9`, `339415a`, `3ab45fc`, `c403718`, `c96ba6c`.

## 의존성 그래프

```
Phase 0
  └─► 1 ──► 2 ──┬─► 3 ─ㅎ─┐
                ├─► 4 ──┼─► 5 ─┐
                └─► 6 ◄─────────┘
                       │
                       ├─► 7 ─► 8 ─┬─► 10
                       └─► 9 ──────┘
  └─► 11 ─► 12 ─► 13 ─► 14
                                  ├─► 15 ─► 16 ─► 17 ─► 18
```

각 Phase 는 의존 충족 시 병렬 가능. 예: 7/8/9 는 1~6 완료 후 동시 작업 가능; 11~14 는 BE 와 무관하게 시작 가능.

---

## ✅ Phase 0 — 부트스트랩 (스캐폴딩) — **완료**

**산출됨**:
- `/home/user/.gitignore` (cred 패턴 포함)
- `/home/user/.env.example`
- `/home/user/CLAUDE.md` (AI 컨텍스트)
- `/home/user/AI_COLLABORATION.md` (골격만)
- `/home/user/docker-compose.yml` (v1/v2 호환 스켈레톤)
- `/home/user/backend/Dockerfile` (stub), `pyproject.toml`, `app/__init__.py`, `tests/__init__.py`
- `/home/user/frontend/Dockerfile` (stub), `package.json`
- 디렉토리: `backend/app/{api,services/{vertex,llm,jobs},utils}`, `backend/tests`, `frontend/src/{api,pages,components,hooks}`, `data/assets`, `session-history`

**핵심 결정**:
- 기존 `/home/user/README.md` (과제 명세) 는 Phase 17 에서 교체. Phase 0 에서는 보존.
- GCP project_id 는 .env 에서 선택 사항, startup 시 SA JSON 에서 추출.
- compose 파일은 `version` 키 없이 작성 (v1/v2 호환).

**검증 통과**: `tree -L 3` 으로 구조 확인, `.gitignore` 에 `tht-aif-*.json` 포함 확인.

---

## ✅ Phase 1 — 백엔드 코어 (FastAPI + DB + Health) — **완료**

**의존**: Phase 0 ✅

**산출 예정**:
- `pyproject.toml` 의존성 잠금 (이미 작성됨, 추가 없음)
- `app/config.py`: pydantic-settings, env 로드 (DATABASE_URL, DATA_DIR, GCP_PROJECT_ID(옵션), GCP_LOCATION, ENHANCE_MODEL, JOB_RUNNER_CONCURRENCY). project_id 가 미설정이면 SA JSON 에서 읽어 채움.
- `app/db.py`: `create_async_engine`, `async_sessionmaker`, `class Base(DeclarativeBase)`
- `app/main.py`: `FastAPI(lifespan=...)`. startup: `Base.metadata.create_all` (첫 이터레이션, 나중에 Alembic 옵션). shutdown: engine dispose.
- `app/api/health.py`: `GET /api/health` → `{ok: true, db: "up"|"down"}` (DB ping 으로 확인)
- backend Dockerfile 보강 (Phase 0 stub 그대로 가능)

**검증**: `docker-compose up backend db` → `curl localhost:8000/api/health` → `{"ok": true, "db": "up"}`.

**예상 시간**: 30~45분.

---

## ✅ Phase 2 — 도메인 모델 & DTO + 상태머신 — **완료**

**의존**: Phase 1

**산출 예정**:
- `app/models.py`:
  - `Job`: id (UUID PK), mode, model, state (ENUM), prompt, enhanced_prompt (nullable), enhancement_id (FK nullable), parent_job_id (FK nullable, self-ref), source_asset_id (FK nullable), blocked (bool default false), vertex_operation_name (nullable), attempts (int default 0), state_history (JSONB), error (JSONB nullable), vertex_charged (bool default false), created_at, updated_at
  - `Asset`: id (UUID PK), job_id (FK), kind ('image'|'video'), local_path (text), mime, size_bytes, width (nullable), height (nullable), duration_sec (nullable, float), created_at
  - `PromptEnhancement`: id (UUID PK), original, enhanced, components (JSONB), target_mode, target_model, llm_model, latency_ms, tokens_in, tokens_out, created_at
- `app/schemas.py`:
  - `T2IRequest`, `T2VRequest`, `I2VRequest` (mode discriminator)
  - `GenerationCreate = Annotated[Union[...], Field(discriminator='mode')]`
  - `GenerationResponse`, `EnhanceRequest`, `EnhanceResponse`, `ComponentsSchema`, `PipelineCreate`, `PipelineResponse`, `AssetResponse`
- `app/state_machine.py`:
  - `STATES = Literal[...]`
  - `ALLOWED_TRANSITIONS: dict[State, set[State]]`
  - `transition(session, job, new_state, detail=None) -> Job` — invalid raise `InvalidTransitionError`, state_history 자동 append, updated_at 갱신
- `tests/test_state_machine.py`: 모든 허용/거부 매트릭스 검증

**검증**: `pytest tests/test_state_machine.py` 통과.

**예상 시간**: 60~75분.

---

## ✅ Phase 3 — 스토리지 + 파일 서빙 — **완료**

**의존**: Phase 1

**산출 예정**:
- `app/services/storage.py`:
  - `save_bytes(job_id: UUID, filename: str, data: bytes) -> str` (상대 경로 반환)
  - `read_bytes(local_path: str) -> bytes`
  - `_safe_path(local_path: str) -> Path` — 경로 정규화, DATA_DIR prefix 강제, `..` 제거 검증
- `app/main.py` 에 `app.mount("/files", StaticFiles(directory=DATA_DIR))` 추가
- `tests/test_path_safety.py`: `..`, 절대경로, 심볼릭 링크 우회 시도 모두 차단

**검증**: 트래버설 시도 차단, 정상 저장/읽기 동작.

**예상 시간**: 30~45분.

---

## ✅ Phase 4 — Vertex 클라이언트 + 인증 — **완료**

**의존**: Phase 1

**산출 예정**:
- `app/services/vertex/client.py`:
  - `get_genai_client() -> genai.Client` 싱글톤 (LRU cache)
  - `genai.Client(vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location)`
  - 자격 증명은 `GOOGLE_APPLICATION_CREDENTIALS` 환경변수로 google-auth 가 자동 픽업
- `app/services/vertex/errors.py`:
  - `class VertexCallError(Exception)`: status (int), message, retryable (bool)
  - `map_google_exception(exc) -> VertexCallError` — `google.api_core.exceptions` → VertexCallError 매핑
- `app/api/health.py` 에 `vertex` 필드 추가: `"ready"` (싱글톤 ok) / `"misconfigured"` (자격 증명 누락/파싱 실패)

**검증**: `/api/health` 응답에 `"vertex": "ready"`.

**예상 시간**: 45~60분.

---

## ✅ Phase 5 — Rate Limiter + Retry — **완료**

**의존**: Phase 1

**산출 예정**:
- `app/services/rate_limit.py`:
  - `class SlidingWindowLimiter` (acquire, current_size, estimate_wait)
  - 모듈 레벨 `LIMITERS: dict[str, SlidingWindowLimiter]` 미리 등록
  - `acquire(model_id: str) -> wait_estimate_sec: float` — 대기한 시간 또는 즉시 통과 시 0.0
- `app/services/retry.py`:
  - `async def with_retry(awaitable_factory, *, max_attempts=3, base=1.0, max_delay=20.0, retryable=(429,500,502,503,504,408))`
  - `awaitable_factory` 는 호출당 새 coroutine 생성하는 callable
- `tests/test_rate_limiter.py`: 100 동시 acquire → capacity 만큼 즉시, 나머지는 윈도우 슬라이드 후 통과. 시간 측정 with `time.monotonic`.
- `tests/test_retry.py`: 429 2회→200 → attempts=3 반환. 4xx 즉시 실패. 5xx 5회 → max_attempts 에서 멈춤. 백오프 시간 상한 검증.

**검증**: 단위 테스트 모두 통과.

**예상 시간**: 60~90분.

---

## ✅ Phase 6 — 잡 러너 (in-process) — **완료**

**의존**: Phase 2, 3, 5

**산출 예정**:
- `app/services/jobs/runner.py`:
  - `async def job_runner()`: 1초 폴링 루프
  - `_pick_pending_jobs(session, limit)`: `SELECT ... WHERE state='pending' AND blocked=false ORDER BY created_at LIMIT N FOR UPDATE SKIP LOCKED`
  - `_global_sem = asyncio.Semaphore(settings.job_runner_concurrency)`
  - 픽업 시 `state → 'enhancing'/'queued'` 로 전이 후 `asyncio.create_task(handle(job))`
  - graceful shutdown: 진행 중 잡은 추적, signal 시 새 픽업 중단, 완료 대기 (timeout 30s)
  - 시작 시 sweep: `_sweep_orphans()` — `updated_at < now() - 5m` AND state IN (비종료) → failed (단 polling + operation_name 있으면 재개)
- `app/services/jobs/handlers.py`:
  - `async def handle(job_id)`: DB 에서 잡 로드 → mode 분기 → `handle_t2i / handle_t2v / handle_i2v` 호출
  - Phase 6 에서는 빈 골격 (`raise NotImplementedError("filled in Phase 7+")`)
- `app/main.py` lifespan 에 `asyncio.create_task(job_runner())` 시작 + shutdown 시 cancel

**검증**: 더미 핸들러 주입 (즉시 completed 전이) → 잡 50개 동시 생성 → 1~2초 내 모두 completed.

**예상 시간**: 90~120분. (가장 까다로운 단계 중 하나)

---

## ✅ Phase 7 — Imagen (T2I) 통합 — **완료**

**의존**: Phase 4, 5, 6

**산출 예정**:
- `app/services/vertex/imagen.py`:
  - `async def generate_image(model_id, prompt, *, number_of_images=1, aspect_ratio="1:1") -> list[bytes]`
  - `client.models.generate_images` 를 `asyncio.to_thread` 로 호출
  - 예외 매핑: `map_google_exception`
- `app/services/jobs/handlers.py:handle_t2i`:
  - state: pending → queued (rate limit acquire) → generating → (vertex call with_retry) → downloading → 파일 저장 + Asset insert → completed
  - 실패 경로: vertex_charged=true 인 경우만 회계
- `app/api/generations.py`:
  - `POST /api/generations` (discriminated union 수용, mode='t2i' 분기)
  - `GET /api/generations/{id}` (잡 + 연결 asset 반환)
  - `GET /api/generations` (목록, 필터: mode/model/state, limit/offset)
- `tests/test_t2i_flow.py`: 모킹 Vertex 로 end-to-end

**검증**: 통합 테스트 + 실제 1회 수동 호출 (`fast` 모델, ~$0.02). 결과 PNG 가 `/data/assets/{uuid}/output.png` 에 존재, `/files/{uuid}/output.png` 가 200.

**예상 시간**: 90~120분.

---

## ✅ Phase 8 — Veo (T2V + I2V) 통합 — **완료**

**의존**: Phase 7

**산출 예정**:
- `app/services/vertex/veo.py`:
  - `async def submit_video(model_id, prompt, *, image_bytes=None, aspect_ratio="16:9", duration_sec=4) -> Operation`
  - `async def poll_operation(op, *, max_interval=30, deadline_sec=600) -> bytes` — 5→10→15→30s 가변, deadline 초과 시 `VeoTimeoutError(op.name)` raise
- `app/services/jobs/handlers.py`:
  - `handle_t2v`: pending → queued → generating (submit) → vertex_operation_name 저장 → polling (loop) → downloading → completed
  - `handle_i2v`: + source_asset_id 에서 바이트 로드 → submit 시 image 인자에 전달
- 시작 시 sweep 보강: polling 상태 잡은 operation_name 있으면 재개 task spawn
- `tests/test_t2v_flow.py`, `tests/test_i2v_flow.py`: 모킹 LRO (3회 폴 후 done)

**검증**: 통합 테스트 + 실제 fast 모델 1회 (~$0.6 for 4s).

**예상 시간**: 120~150분. (LRO 폴링 + 재개 로직 복잡)

---

## ✅ Phase 9 — 프롬프트 Enhance (Gemini) — **완료**

**의존**: Phase 1

**산출 예정**:
- `app/services/llm/enhancer.py`:
  - `class ComponentsSchema(BaseModel)`: subject, environment, style, composition, lighting, camera (video only), motion (video only), mood
  - `ENHANCE_SYSTEM_PROMPT_IMAGE`, `ENHANCE_SYSTEM_PROMPT_VIDEO` — 6대 설계 원칙 반영
  - `async def enhance(prompt, target_mode, target_model) -> EnhanceResponse`
  - `client.models.generate_content(model=ENHANCE_MODEL, contents=[...], config=GenerateContentConfig(response_mime_type="application/json", response_schema=ComponentsSchema, temperature=0.3, max_output_tokens=800))`
  - 실패 시 graceful: 원본 + warning 반환, 잡 진행 가능
  - DB persist: `PromptEnhancement` row 생성
- `app/api/prompts.py`: `POST /api/prompts/enhance`
- `tests/test_enhance.py`: 모킹 LLM, image/video 모드별 system prompt 선택 검증, JSON 파싱 실패 시 graceful, components 결과 차이 (video 에 camera/motion)

**검증**: 통합 테스트 + 수동 "A cat" 으로 두 모드 enhance.

**예상 시간**: 60~90분.

---

## ✅ Phase 10 — T2I → I2V 파이프라인 — **완료**

**의존**: Phase 7, 8

**산출 예정**:
- `app/services/jobs/pipeline_link.py`:
  - `on_job_completed(job)`: parent_job_id 로 child 찾아 blocked=false + source_asset_id=parent.asset.id
  - `on_job_failed(job)`: child 들 cascade fail (`error.cause=parent_failed`)
- `app/services/jobs/runner.py` 의 transition 훅에서 위 두 함수 호출
- `app/api/pipelines.py`:
  - `POST /api/pipelines`: parent + child 동시 생성, parent_id 와 child_id 반환
  - `GET /api/pipelines/{parent_id}`: parent + child 한 번에
- `tests/test_pipeline.py`: parent completed → child 자동 시작; parent failed → child cascade

**검증**: 통합 테스트.

**예상 시간**: 60~90분.

---

## ✅ Phase 11 — Frontend Required Flows — **완료**

**현재 상태**: Phase 11 absorbed and completed the original frontend Phase
11-14 scope. The implementation is documented in
`.codex/memories/phase11/phase11_frontend_plan.md` and includes:

- Core Vite/React shell, React Router, React Query provider, typed API client.
- Generate T2I/T2V/I2V UI and prompt Enhance review/edit/accept flow.
- Stale enhancement safety checks before submitting `enhancement_id`.
- Job detail polling every 2 seconds for non-terminal jobs, state timeline,
  result asset viewer, and completed image Asset UUID handoff into I2V.
- History filters/pagination on `GET /api/generations`.
- Pipeline launcher and pipeline detail polling on `/api/pipelines`.

The original Phase 11 plan body below is retained as historical planning text.

**의존**: Phase 0

**산출 예정**:
- Vite + React + TS 셋업 (`vite.config.ts`, `tsconfig.json`, `index.html`, `main.tsx`)
- Tailwind PostCSS 설정 (`tailwind.config.js`, `postcss.config.js`, `src/index.css`)
- `react-router-dom`, `@tanstack/react-query` 설치 + provider 셋업
- `src/api/client.ts`: fetch wrapper, 에러 표준화, base URL 은 `import.meta.env.VITE_API_BASE`
- `src/api/types.ts`: BE 스키마 미러 (수동, 작은 분량이라 자동화 불필요)
- 기본 레이아웃: NavBar (Generate / History 링크)
- `App.tsx` + 라우터 셋업
- frontend Dockerfile 마무리 (build → preview 또는 dev 모드)

**검증**: `docker-compose up frontend` → http://localhost:5173 빈 페이지 + 네비.

**예상 시간**: 60~90분.

---

## ✅ Phase 12 — Docker Compose / Integration Readiness — **완료 (rescope)**

**Rescope note**: The original Phase 12 Generate UI + Enhance scope was
completed inside Phase 11. Phase 12 was then rescoped to Docker Compose /
integration readiness. Latest details live in:

- `.codex/memories/phase12/phase12_closeout.md`
- `.codex/memories/phase12/phase12_compose_smoke.md`

Completed Phase 12 units:

- Compose env/build hygiene and `.dockerignore` coverage.
- Backend startup runtime preparation: create `DATA_DIR`, initialize SQLAlchemy
  metadata before job runner startup, and serve `/files/{local_path}` through
  storage path validation.
- Frontend compose API readiness: empty `VITE_API_BASE` falls back to
  same-origin paths; Vite proxies `/api` and `/files` to the backend target.
- Compose smoke discovery was initially blocked by sandbox Docker/Compose v1
  issues, then host revalidation passed with Docker Compose v2 after
  `c403718 fix: align health response schema`.
- Smoke documentation was updated in `c96ba6c docs: update phase 12 compose
  smoke results`.

The original Phase 12 frontend plan body below is retained as historical
planning text.

**의존**: Phase 9, 11

**산출 예정**:
- `pages/GeneratePage.tsx`
- `components/ModeSelector.tsx` (T2I / T2V / I2V 탭)
- `components/ModelPicker.tsx` (모드에 맞는 모델 옵션)
- `components/PromptInput.tsx` (textarea + char count)
- `components/EnhanceReview.tsx` (좌:원본 / 우:개선 + 컴포넌트 칩 + 편집 textarea)
- `components/PipelineLauncher.tsx` (T2I→I2V 한 번에 진입)
- I2V 모드: 히스토리에서 source asset 선택 (단순화)
- Generate 클릭 → POST `/api/generations` → JobDetail 페이지로 이동

**검증**: 수동 — Enhance 동작, 편집 후 Generate, 다음 페이지 이동.

**예상 시간**: 120~180분. (UI 폴리시까지)

---

## ✅ Phase 13 — Job Detail / 대기 UX — **완료 via Phase 11 Unit 3**

**Current note**: Implemented under Phase 11 in `f7916e9 feat: add job detail
polling and asset handoff`. The original phase body below is retained as
historical planning text.

**의존**: Phase 10, 12

**산출 예정**:
- `pages/JobDetailPage.tsx`
- `hooks/useJob.ts`: tanstack-query, `refetchInterval: 2000`, terminal 상태에서 중단
- `components/StateTimeline.tsx`: 단계 체크리스트 + 현재 단계 강조 + 단계별 메타 (queued/polling/failed 디테일)
- `components/AssetView.tsx`: 이미지/비디오 인라인 + 다운로드 + "이 이미지로 비디오 만들기"
- 취소 버튼 (`polling` 상태에서만 활성) → `POST /api/generations/{id}/cancel`
- 파이프라인 잡 표시: parent + child 함께 (별도 컴포넌트 또는 동일 페이지 합본)

**검증**: 수동 — Veo 잡 폴링 화면에서 경과 카운트, 완료 시 비디오 재생.

**예상 시간**: 120~180분.

---

## ✅ Phase 14 — 히스토리 — **완료 via Phase 11 Unit 4**

**Current note**: Implemented under Phase 11 in `0095369 feat: implement
generation history UI` and completed with pipeline UI in `31a0aba feat:
implement pipeline launcher and detail UI`. The original phase body below is
retained as historical planning text.

**의존**: Phase 7, 12

**산출 예정**:
- `pages/HistoryPage.tsx`: 그리드 (썸네일 + 모드/모델/상태/생성일)
- 필터: mode, model, state (URL query 파라미터)
- 페이지네이션 (limit/offset)
- 카드 클릭 → JobDetailPage
- BE: `GET /api/generations` 에 필터 쿼리 처리

**검증**: 수동 — 여러 잡 생성 후 필터 동작.

**예상 시간**: 60~90분.

---

## ⏳ Phase 15 — Docker Compose 마무리

**Current note**: Most compose/integration readiness work originally expected
here was completed early by the rescoped Phase 12. Remaining finalization should
avoid redoing Phase 12 and focus only on any final README/submission polish or
explicitly requested end-to-end generation checks.

**의존**: Phase 14

**산출 예정**:
- `docker-compose.yml` 최종본 (이미 Phase 0 에서 작성된 스켈레톤 보강)
- backend Dockerfile multi-stage (deps 캐시 + 슬림 런타임)
- frontend Dockerfile: `npm ci && npm run build` 후 `vite preview` 또는 `serve dist`
- `.env.example` 갱신 (필요 시)

**검증**: `docker-compose down -v && docker-compose up --build` → http://localhost:5173 → T2I 1회 end-to-end.

**예상 시간**: 60~90분.

---

## ⏳ Phase 16 — 테스트 보강 + 커버리지

**의존**: Phase 2, 12

**산출 예정**:
- 누락된 통합 테스트: `test_rate_limit_visibility.py`, `test_max_retries.py`, `test_cancel.py`
- `pyproject.toml` pytest 설정에 `addopts = "--cov=app --cov-report=term-missing"` 추가
- (선택) GitHub Actions YAML 또는 `Makefile` 추가

**검증**: 핵심 서비스 (rate_limit, retry, state_machine, storage, vertex, handlers) 라인 커버리지 80%+.

**예상 시간**: 60~90분.

---

## ⏳ Phase 17 — README.md 작성

**의존**: Phase 11, 16

**산출 예정**: 기존 과제 명세 README 를 프로젝트 README 로 교체. 포함:
- 한 문단 개요
- 기술 스택 표
- 아키텍처 ASCII 다이어그램
- 빠른 시작 (4줄): cred 파일 확인 → `.env.example → .env` → `docker-compose up --build` → http://localhost:5173
- 환경변수 표
- API 요약 표
- 상태 머신 다이어그램
- 테스트 명령: `docker-compose run --rm backend pytest`
- 알려진 제약: 단일 인스턴스, GCS 미사용, Celery 미도입 근거

**검증**: 새 사람이 README 만 읽고 `docker-compose up --build` 까지 도달 가능.

**예상 시간**: 60~90분.

---

## ⏳ Phase 18 — AI_COLLABORATION.md 작성

**의존**: Phase 16

**산출 예정**: 네 섹션 모두 작성
1. **Enhance 시스템 설계 원칙과 프롬프트 전략**: 6대 원칙 풀어 쓰기, 모드별 system prompt 발췌, ComponentsSchema 설명, 실패/폴백 정책
2. **Q1 — 가장 까다로운 엣지케이스/장애 시나리오**: 구현 중 마주친 실제 케이스 1~2개 (탐지 → 가설 → 검증 → 해결). 후보: Veo LRO 가 deadline 까지 안 끝나는 경우, 잡 러너 재시작 시 polling 재개, child 잡이 parent 파일 삭제 후 시작 등.
3. **Q2 — AI 생성 코드 검증 시 중요 항목**: (a) 비밀/자격 증명 누수, (b) async/sync 혼용 데드락, (c) DB 트랜잭션 경계 + lock 보유 시간, (d) 입력 검증/트래버설/SQL 인젝션, (e) 에러 분류 (재시도 가능 vs 사용자 오류), (f) "동작하지만 비싼" 호출 (불필요한 모델 호출, 폴링 너무 자주). 각 1~2문장.
4. **Q3 — AI 한계 극복 사례**: 실제 작업 중 AI 가 모르거나 틀린 부분 (예: Veo SDK 시그니처 학습 데이터와 다름 → 공식 docs 확인 + 어댑터 작성). 구체 케이스 1~2개.

**검증**: README 산출물 표 4가지 항목 모두 충족, 분량 적절 (각 섹션 200~400자).

**예상 시간**: 90~120분.

---

## 누적 예상 시간 (historical estimate)

- Phase 0: ✅ 완료 (~30분 소요)
- Phase 1~10 (BE): ✅ 완료 (historically estimated at 약 12~16시간)
- Phase 11 required frontend flows: ✅ 완료 (absorbed original Phase 11~14)
- Phase 12 Docker Compose / integration readiness: ✅ 완료
- Remaining work after the 2026-05-23 status update is Phase 16 test
  hardening/coverage as scoped, Phase 17 README, and Phase 18
  AI_COLLABORATION.
- **총 합산**: 약 24~32시간 (3일 일정 안에 여유 있음)

## 우선순위 결정 가이드 (updated)

The original cut list is mostly historical because frontend History and Pipeline
UI are already complete under Phase 11. Remaining lower-priority candidates if
time is constrained:

1. Phase 16 extra coverage beyond the highest-risk backend paths.
2. Cancel API/UI, which remains deferred.
3. Optional real Vertex/Veo/Gemini manual QA beyond already-recorded mocked
   tests and compose smoke.

절대 잘라내면 안 되는 것 (필수 요구사항):
- T2I/T2V/I2V API (Phase 7, 8) — ✅ complete
- Enhance + 편집 흐름 (Phase 9, Phase 11 frontend) — ✅ complete
- 재시도/rate limit (Phase 5) — ✅ complete
- 파이프라인 (Phase 10 backend, Phase 11 frontend) — ✅ complete
- Docker Compose / integration readiness (rescoped Phase 12) — ✅ complete
- README (Phase 17)
- AI_COLLABORATION Q1/Q2/Q3 (Phase 18)

## 진행 추적

Claude Code task list 의 task #1~#19 originally mapped to phase 0~18. The
mapping changed after frontend consolidation and the Phase 12 rescope.

- Phase 0: ✅ completed.
- Backend Phase 1-10: ✅ completed.
- Frontend required flows: ✅ completed in Phase 11, covering original frontend
  Phase 11-14 scope.
- Phase 12 Docker Compose / integration readiness: ✅ completed.
- Phase 15 Docker Compose 마무리: mostly superseded by Phase 12; keep only final
  submission polish or explicitly requested real-generation compose checks.
- Phase 16 테스트 보강 + 커버리지: ⏳ pending.
- Phase 17 README.md 작성: ⏳ pending; do not replace the original assignment
  brief before this phase.
- Phase 18 AI_COLLABORATION.md 작성: ⏳ pending.
