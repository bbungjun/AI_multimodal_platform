# pre_context 색인

이 색인은 `pre_context/krafton_assignment_01.md`부터 `15.md`까지의 긴 export를 빠르게 찾아가기 위한 안내서입니다. 원문은 보존하고, 이 파일과 `summaries/`를 복구 작업의 내비게이션으로 사용합니다.

## 현재 색인 범위

- 1차 완료: `krafton_assignment_01.md` ~ `krafton_assignment_03.md`
- 2차 완료: `krafton_assignment_04.md` ~ `krafton_assignment_06.md`
- 3차 완료: `krafton_assignment_07.md` ~ `krafton_assignment_09.md`
- 4차 완료: `krafton_assignment_10.md` ~ `krafton_assignment_12.md`
- 5차 완료: `krafton_assignment_13.md` ~ `krafton_assignment_15.md`
- 전체 완료: `krafton_assignment_01.md` ~ `krafton_assignment_15.md`

## 파일별 요약

| 파일 | 요약 | 복구 사용처 |
|---|---|---|
| `krafton_assignment_01.md` | 초기 과제 이해, 제출 방식, 기술 스택 선택, Phase 0~6 기반, Phase 7 진입 | 전체 설계 의도와 Phase 경계 확인 |
| `krafton_assignment_02.md` | 과제 원문 명세, 전체 아키텍처, prompt enhancement LLM 선택 | 요구사항, Gemini/Claude 판단, enhance 설계 |
| `krafton_assignment_03.md` | Phase 7 Imagen T2I 구현 프롬프트, dirty worktree, `/files` 테스트 hang 대응 | T2I API/handler/service/test 복구 |
| `krafton_assignment_04.md` | Git object corruption 상황에서 Phase 7 WIP 파일을 직접 조사하고 복구 가치를 판단 | 손상된 Git 이력 대신 T2I 구현 흔적과 router 누락 확인 |
| `krafton_assignment_05.md` | Phase 8 Veo T2V/I2V 계획, service adapter, polling, timeout/failure, resume/startup sweep | Veo backend, LRO polling, operation-name resume 복구 |
| `krafton_assignment_06.md` | Phase 8 closeout 후 Phase 9 Prompt Enhance 계획과 Unit 1~4 구현 | Gemini enhancer service, `/api/prompts/enhance`, DB persistence 복구 |
| `krafton_assignment_07.md` | Phase 12 compose readiness, Phase 13 API contract, Phase 14 T2I Live UX QA 진입 | Docker/compose, `/files`, proxy, OpenAPI 타입 정합, T2I 실제 성공 복구 |
| `krafton_assignment_08.md` | Phase 14 `POST /api/generations` lazy-load 500 bugfix와 QA 재개 전략 | `JobResponse.assets` lazy-load/MissingGreenlet fix 확인 |
| `krafton_assignment_09.md` | Phase 14 I2V/T2V/Pipeline Live QA, Prompt Enhance parser/creativity/P3/P4/P5 개선 | 실제 Vertex-backed UX QA와 Prompt Enhancement 품질 개선 복구 |
| `krafton_assignment_10.md` | 전략 파트너 역할 정렬, 기업 서버 + E2B 환경 확인, 원본 과제 README 루브릭 재해석 | 작업 운영 원칙과 최종 산출물/평가 기준 확인 |
| `krafton_assignment_11.md` | Prompt Enhancement P6 안정화, 파일 기준 architecture 확인, frontend UX polish, Veo failure classification | Prompt Enhance 최종 형태, FE polish, T2V failure 분류 복구 |
| `krafton_assignment_12.md` | 최신 상태 handoff, Prompt Enhancement/UX/Veo 상태 압축, 남은 작업 정리 | 다음 복구/마무리 작업의 빠른 현재 상태 확인 |
| `krafton_assignment_13.md` | I2V source/waiting UX, History filter/delete/video preview, Veo provider constraints, Prompt Enhancement diagnostics | 마지막 UX/QA polish와 History/I2V 복구 |
| `krafton_assignment_14.md` | 최종 README 작성을 위한 API/runner/Vertex/state/storage/features fact check와 문구 정리 | README 재작성, architecture 문구, 과장 표현 제거 |
| `krafton_assignment_15.md` | 최종 README/AI_COLLABORATION 작성, Prompt Enhancement Strategy, Q1/Q2/Q3, root sync와 제출 안정화 | 최종 산출물 복구와 제출 직전 기준 확인 |

## 큰 키워드별 찾아가기

### 과제 명세 / 제출 방식

- 관련 파일: `01`, `02`, `10`, `14`, `15`
- 핵심 키워드: 과제 명세, README, AI_COLLABORATION, AGENTS.md, 제출, workspace, E2B, root sync
- 먼저 볼 요약:
  - `summaries/01-summary.md`
  - `summaries/02-summary.md`
  - `summaries/10-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### 기술 스택 / 전체 아키텍처

- 관련 파일: `01`, `02`, `07`, `10`, `14`, `15`
- 핵심 키워드: FastAPI, PostgreSQL, React, Vite, Docker Compose, google-genai, in-process runner
- 먼저 볼 요약:
  - `summaries/01-summary.md`
  - `summaries/02-summary.md`
  - `summaries/07-summary.md`
  - `summaries/10-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Phase 1~6 기반

- 관련 파일: `01`, `04`, `14`, `15`
- 핵심 키워드: health skeleton, state_machine, storage, Vertex readiness, retry, rate limiter, job runner
- 먼저 볼 요약:
  - `summaries/01-summary.md`
  - `summaries/04-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Git 손상 / 복구 스냅샷 판단

- 관련 파일: `04`, `10`, `12`, `13`
- 핵심 키워드: Git object corruption, dirty working tree, direct file inspection, recovered workspace, dirty diff, restore 판단
- 먼저 볼 요약:
  - `summaries/04-summary.md`
  - `summaries/10-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`

### Phase 7 Imagen T2I

- 관련 파일: `01`, `03`, `04`, `07`, `09`, `15`
- 핵심 키워드: Imagen, T2I, `imagen.py`, `generations.py`, `handle_t2i`, `test_t2i_flow.py`, mock Vertex, actual T2I Live QA, multi-image gallery
- 먼저 볼 요약:
  - `summaries/03-summary.md`
  - `summaries/04-summary.md`
  - `summaries/07-summary.md`
  - `summaries/09-summary.md`
  - `summaries/15-summary.md`

### `/files/...` serving / 테스트 hang / video Range

- 관련 파일: `03`, `04`, `07`, `09`, `13`, `14`
- 핵심 키워드: `/files/...`, ASGITransport, StaticFiles, hang, storage.read_bytes, Asset url, files mount, frontend proxy, byte range, video preview
- 먼저 볼 요약:
  - `summaries/03-summary.md`
  - `summaries/04-summary.md`
  - `summaries/07-summary.md`
  - `summaries/09-summary.md`
  - `summaries/13-summary.md`
  - `summaries/14-summary.md`

### Phase 8 Veo T2V/I2V

- 관련 파일: `05`, `06`, `09`, `11`, `12`, `13`, `14`, `15`
- 핵심 키워드: Veo, T2V, I2V, `veo.py`, `submit_video`, `poll_operation`, failure classification, inline bytes, no GCS, safety filter
- 먼저 볼 요약:
  - `summaries/05-summary.md`
  - `summaries/06-summary.md`
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Veo polling resume / orphan sweep

- 관련 파일: `05`, `06`, `14`, `15`
- 핵심 키워드: `vertex_operation_name`, `poll_operation_by_name`, polling state, resume task, startup sweep
- 먼저 볼 요약:
  - `summaries/05-summary.md`
  - `summaries/06-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Veo Failure Classification / Provider Constraints

- 관련 파일: `11`, `12`, `13`, `14`, `15`
- 핵심 키워드: operation error, empty output, filtered output, `generated_videos`, `video_bytes`, public error, personGeneration, provider rejection
- 먼저 볼 요약:
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Prompt Enhancement / Gemini

- 관련 파일: `02`, `06`, `08`, `09`, `11`, `12`, `13`, `15`
- 핵심 키워드: Gemini via Vertex, PromptEnhancement, `enhancer.py`, `prompts.py`, `/api/prompts/enhance`, original_prompt, enhanced_prompt, final_prompt, safe diagnostics
- 먼저 볼 요약:
  - `summaries/02-summary.md`
  - `summaries/06-summary.md`
  - `summaries/08-summary.md`
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/15-summary.md`

### Phase 9 `enhancement_id` linkage

- 관련 파일: `06`, `09`, `11`, `15`
- 핵심 키워드: existing `enhancement_id`, `Job.enhanced_prompt`, `Job.prompt`, review/edit/apply, source-of-truth, target_mode, target_model
- 먼저 볼 요약:
  - `summaries/06-summary.md`
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/15-summary.md`

### Prompt Enhance Parser Hardening

- 관련 파일: `09`, `11`, `12`, `13`, `15`
- 핵심 키워드: invalid response, malformed JSON, fenced JSON, balanced JSON object, longer `max_output_tokens`, sanitized public error, strict JSON retry
- 먼저 볼 요약:
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/15-summary.md`

### Prompt Enhance Creativity / P3 / P4 / P5 / P6

- 관련 파일: `09`, `11`, `12`, `15`
- 핵심 키워드: Faithful, Balanced, Imaginative, I2V-specific guidance, sectioned prompt template, mode-scoped format exemplar, anti-generic guidance, temperature
- 먼저 볼 요약:
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/15-summary.md`

### Phase 10 Pipeline T2I -> I2V

- 관련 파일: `07`, `09`, `12`, `13`, `14`, `15`
- 핵심 키워드: pipeline, parent job, child I2V, `parent_job_id`, `source_asset_id`, blocked child, `/api/pipelines/{parent_job_id}`, model validation
- 먼저 볼 요약:
  - `summaries/07-summary.md`
  - `summaries/09-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### I2V Source / Waiting UX

- 관련 파일: `11`, `12`, `13`, `15`
- 핵심 키워드: source image locked, cinema-screen, Generate enabled, enhancement optional, PipelinePage, JobDetailPage, Source context, motion prompt
- 먼저 볼 요약:
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/15-summary.md`

### Phase 11 Frontend Required Flows / UX Polish

- 관련 파일: `07`, `09`, `11`, `12`, `13`, `15`
- 핵심 키워드: GeneratePage, JobDetailPage, HistoryPage, PipelineLauncher, frontend lint/build, History QA, I2V handoff, developer-facing copy
- 먼저 볼 요약:
  - `summaries/07-summary.md`
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/15-summary.md`

### History / Delete / Video Preview

- 관련 파일: `13`, `15`
- 핵심 키워드: asset_kind filter, image/video filter, terminal delete, dependent job, parent/source detach, active job protection, video preview, Range request
- 먼저 볼 요약:
  - `summaries/13-summary.md`
  - `summaries/15-summary.md`

### T2I Multi-image Gallery

- 관련 파일: `15`
- 핵심 키워드: `number_of_images`, multiple image assets, gallery, first asset only, Start I2V with this image
- 먼저 볼 요약:
  - `summaries/15-summary.md`

### Phase 12 Docker Compose / Integration Readiness

- 관련 파일: `07`, `10`, `12`, `14`, `15`
- 핵심 키워드: `.env.example`, `.dockerignore`, `docker-compose.yml`, `VITE_API_BASE`, `VITE_API_PROXY_TARGET`, `VITE_ALLOWED_HOSTS`, `/api/health`, `/files`, Compose smoke, E2B
- 먼저 볼 요약:
  - `summaries/07-summary.md`
  - `summaries/10-summary.md`
  - `summaries/12-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Phase 13 API Contract Alignment

- 관련 파일: `07`, `14`, `15`
- 핵심 키워드: OpenAPI, Swagger, `/openapi.json`, HealthResponse, VertexReadinessResponse, frontend API types, no codegen, pipeline validation
- 먼저 볼 요약:
  - `summaries/07-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### Phase 14 Live UX QA

- 관련 파일: `07`, `08`, `09`, `11`, `12`, `13`, `15`
- 핵심 키워드: actual Vertex call, manual browser QA, T2I, I2V, T2V, Pipeline, History, docs/memories, provider constraint
- 먼저 볼 요약:
  - `summaries/07-summary.md`
  - `summaries/08-summary.md`
  - `summaries/09-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/15-summary.md`

### `JobResponse.assets` Lazy Load / MissingGreenlet

- 관련 파일: `07`, `08`
- 핵심 키워드: `ResponseValidationError`, `MissingGreenlet`, `job.assets`, `job_response_from_job`, `assets=[]`
- 먼저 볼 요약:
  - `summaries/08-summary.md`
  - 필요하면 `summaries/07-summary.md`

### Docs / Memories 위치 정리

- 관련 파일: `09`, `10`, `11`, `12`, `13`, `14`, `15`
- 핵심 키워드: `.codex/memories`, `docs/memories`, durable docs under `docs/`, README, AI_COLLABORATION, troubleshooting, fact check
- 먼저 볼 요약:
  - `summaries/09-summary.md`
  - `summaries/10-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/13-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### README 최종 작성 / Fact Check

- 관련 파일: `14`, `15`
- 핵심 키워드: README, Quick Start, Docker Compose, API summary, architecture, factcheck, no `auto_enhance` examples, LF normalization
- 먼저 볼 요약:
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### AI_COLLABORATION.md 최종 작성 재료

- 관련 파일: `10`, `11`, `12`, `14`, `15`
- 핵심 키워드: Step 3, edge case, AI 검증 기준, Creativity Mode, manual review-first, Gemini parser, Veo failure classification, Prompt Enhancement Strategy
- 먼저 볼 요약:
  - `summaries/10-summary.md`
  - `summaries/11-summary.md`
  - `summaries/12-summary.md`
  - `summaries/14-summary.md`
  - `summaries/15-summary.md`

### 제출 직전 안정화 / Root Sync

- 관련 파일: `15`
- 핵심 키워드: `/home/user`, `/home/user/recovered_workspace`, README sync, AI_COLLABORATION sync, secret grep, frontend build, Docker Compose ps/logs, final submission
- 먼저 볼 요약:
  - `summaries/15-summary.md`

## 다음 색인 작업 메모

`01~15` 전체 색인은 완료되었습니다. 새 export가 추가되면 같은 방식으로 `summaries/NN-summary.md`를 만들고, 이 색인에는 기능/문서/검증 기준 중심으로만 추가합니다. 일회성 환경 로그, 해시, 원격 작업 메시지는 복구 기준으로 쓰지 않습니다.
