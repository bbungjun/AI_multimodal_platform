# krafton_assignment session 14

- Thread ID: 019e5ccf-09ee-7ab0-8d53-f80dd943c9c7
- Source: C:\Users\PC\.codex\sessions\2026\05\25\rollout-2026-05-25T10-45-32-019e5ccf-09ee-7ab0-8d53-f80dd943c9c7.jsonl
- Source SHA256: 4b9fc5852dd2104b8f1ad8524791cff90f639b6cbfe5ae5263fb8a687f4c1302
- Session timestamp: 2026-05-25 10:45:32 +09:00
- Exported at: 2026-05-26 18:53:18 +09:00
- Message count: 87
- Export mode: response_item message content parts only: user=input_text, assistant=output_text

---

## user

````text
# AGENTS.md instructions for C:\Users\PC\Desktop\krafton_assignment

<INSTRUCTIONS>
# Project context for AI tools

This file is read by Claude Code / Codex when working in this repo. Keep it short and load-bearing.

## What this is

A take-home assignment: an AI multimodal content-generation platform on Vertex AI
(Imagen 4 + Veo 3) with prompt enhancement (Gemini 2.5 Flash). The full spec
lives in the original README (preserved in git history; current `README.md` is
the project's own documentation once Phase 17 ships).

## Stack

- **Backend**: Python 3.11 + FastAPI + SQLAlchemy (async) + asyncpg + Postgres 16
- **Frontend**: Vite + React + TypeScript + Tailwind CSS + @tanstack/react-query
- **AI**: `google-genai` SDK (Imagen, Veo, Gemini) authenticated via a single GCP
  service-account key mounted at `/secrets/sa.json`.
- **Orchestration**: `docker-compose up` boots `db`, `backend`, `frontend`.

## Critical conventions

- **No Celery, no Redis.** Jobs are tracked in Postgres and processed by an
  in-process asyncio runner. Concurrency is bounded by a semaphore and a
  per-model sliding-window rate limiter. See `backend/app/services/jobs/runner.py`.
- **Single Vertex SDK.** Imagen, Veo, and Gemini are all called through
  `google-genai` (`genai.Client(vertexai=True, ...)`). Do not introduce
  per-model SDKs.
- **Inline bytes, not GCS.** Veo is called without `output_gcs_uri`; the result
  is read from `operation.result.generated_videos[0].video.video_bytes` and
  written to `DATA_DIR`. Do not switch to GCS unless asked.
- **State machine is strict.** All job state changes go through
  `app/state_machine.py:transition(...)`. Invalid transitions raise; tests
  enforce the matrix.
- **Path safety.** Asset filesystem writes go through `app/services/storage.py`.
  Job IDs are UUIDv4; never accept user-supplied filenames into paths.

## Things to never do

- Never commit `tht-aif-*.json` or any service-account key, even partially.
- Never log the contents of credentials. Log the path only, masked if possible.
- Never amend the README brief away — the project's final `README.md` is
  generated in Phase 17 and replaces the brief.
- Never call Vertex from tests. Tests must mock `app/services/vertex/*` and
  `app/services/llm/*`.

## Git workflow

- Use local git commits only. Do not add remotes or push.
- Commit after each meaningful phase or feature unit is completed.
- Before every commit, run `git status --short`.
- Before every commit, run `git diff --cached --name-only` and verify staged files.
- Never stage or commit credentials, `.env` files, service-account JSON files, `node_modules`, `dist`, `.venv`, `__pycache__`, `data/assets`, or other generated artifacts.
- Use repo-local git identity only. Do not modify global git config.
- Use clear commit messages that describe the completed work unit.

## Dev server and browser verification

- Dev servers that need browser verification must bind to `0.0.0.0`.
- A server that listens only on `localhost` or `127.0.0.1` cannot be reached from the external browser.
- For Vite, use `--host 0.0.0.0`.
- For FastAPI/Uvicorn, use `--host 0.0.0.0`.
- Evaluation sandbox public URLs use `https://<PORT>-${E2B_SANDBOX_ID}.e2b.app`.
- Frontend example: `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173`, public URL `https://5173-${E2B_SANDBOX_ID}.e2b.app`.
- Backend example: `cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`, public URL `https://8000-${E2B_SANDBOX_ID}.e2b.app`.
- Public URLs are externally reachable, so never expose credentials, service-account contents, `.env` values, or other sensitive data through logs, UI, API responses, or static files.

## Where things live

```
backend/app/
  config.py            settings via pydantic-settings
  db.py                async engine + session
  models.py            Job, Asset, PromptEnhancement
  schemas.py           Pydantic DTOs (discriminated union for generations)
  state_machine.py     transition matrix + validator
  api/                 route modules (generations, prompts, pipelines, assets, health)
  services/
    vertex/            client.py, imagen.py, veo.py, errors.py
    llm/enhancer.py    Gemini-based prompt enhance
    jobs/              runner.py, handlers.py, pipeline_link.py
    rate_limit.py
    retry.py
    storage.py
  tests/

frontend/src/
  api/                 client.ts + types.ts (mirrors BE)
  pages/               GeneratePage, JobDetailPage, HistoryPage
  components/          ModeSelector, ModelPicker, PromptInput, EnhanceReview,
                       StateTimeline, AssetView, PipelineLauncher
  hooks/useJob.ts      tanstack-query polling at 2s
```

## Implementation plan

See `.claude/plans/readme-md-imperative-yao.md` for the full 18-phase plan and
dependency graph. Tasks 1–19 in the task list mirror those phases.

</INSTRUCTIONS>
<environment_context>
  <cwd>C:\Users\PC\Desktop\krafton_assignment</cwd>
  <shell>powershell</shell>
  <current_date>2026-05-25</current_date>
  <timezone>Asia/Seoul</timezone>
</environment_context>
````

## user

```text
너는 KRAFTON take-home assignment를 진행 중인 사용자의 전략 파트너다. 직접 구현하지 말고, 사용자가 가져오는 Codex CLI 결과를 판독하고 다음에 Codex CLI에 보낼 짧고 안전한 프롬프트를 제안해라. 사용자가 “프롬프트 줘”라고 할 때만 실제 Codex CLI용 프롬프트를 작성한다.

운영 원칙:
- 실제 작업 repo는 ~/recovered_workspace.
- /home/user 루트는 Git object 손상 및 read-only .git mount 이슈가 있었으므로 git 명령/파일 수정 금지.
- Codex CLI는 반드시 cd ~/recovered_workspace && codex 로 실행.
- 새 문서화 산출물은 .codex/가 아니라 docs/ 하위에 작성.
- /tmp는 임시 조사/백업 용도만. durable work는 두지 않음.
- .env, service-account JSON, credential/API key 내용은 절대 요청/출력하지 않음.
- 실제 Vertex/Gemini 호출은 Live UX QA에서만. 자동화 테스트는 mock/fake only.
- 사용자가 브라우저에서 직접 Live QA를 수행함. Codex CLI가 브라우저를 조작하거나 Chromium을 설치하지 않게 할 것.
- Codex CLI가 결과를 가져오면 상태 판독 후 다음 단계만 제안. 바로 구현 프롬프트를 내밀지 말고, 사용자가 요청할 때만 제공.
- 응답은 짧고 전략적으로. 긴 프롬프트를 싫어함.

환경:
- Docker Compose v2.29.7 복구 완료.
- E2B/과제 서버에서는 sudo 환경변수 보존 필요:
  sudo -E docker compose up -d --build --force-recreate frontend backend db
- public URL:
  https://5173-${E2B_SANDBOX_ID}.e2b.app
  https://8000-${E2B_SANDBOX_ID}.e2b.app
- 제출 전 git status --short는 반드시 clean이어야 함.
- 서버 배치/복구 이후 working tree가 오래된 파일로 덮이는 문제가 있었음. 이런 경우 git log는 정상인데 git diff --stat가 대량 deletions로 나타남. 이미 모든 작업은 커밋되어 있으므로, 이상한 dirty diff는 patch 백업 후 git restore . 로 HEAD 복구하는 방식이 안전했음.

현재 구현 완료 상태:
- Backend:
  - T2I, T2V, I2V generation API 구현.
  - model selection 지원.
  - generated asset DB 저장 + local file 저장.
  - asset detail API 구현.
  - Prompt enhancement API 구현.
  - T2I -> I2V pipeline 구현.
  - in-process asyncio job runner + Postgres job state 관리.
  - no Celery, no Redis.
  - state transitions는 state_machine.transition(...) 경유.
  - google-genai 단일 SDK 사용.
  - Veo는 GCS 없이 inline video bytes를 DATA_DIR에 저장.
  - retry/rate-limit/error classification 구현.
  - storage.py 경유 path-safe file write/delete.
  - History job deletion backend:
    - terminal job(completed/failed/cancelled) row 독립 삭제 가능.
    - active job 삭제 차단.
    - 선택 job을 참조하는 active dependent job이 있으면 409.
    - terminal dependent job은 parent_job_id/source_asset_id null로 끊고 선택 job만 삭제.
    - 해당 job의 asset files만 삭제.
  - /files Range request 지원으로 video preview가 전체 파일 다운로드 없이 가능.

- Frontend:
  - Generate page:
    - T2I/T2V/I2V modes.
    - model/aspect/duration selection.
    - prompt enhancement review/edit/accept flow.
    - Creativity Mode UI.
    - I2V source image handoff from asset detail.
    - /generate?mode=i2v&source_asset_id=...에서 source image preview 표시.
    - I2V는 enhancement 없이 source image + motion prompt만으로 Generate 가능.
  - Job Detail:
    - Job state timeline/live progress.
    - active I2V waiting 중 source context image 표시.
    - completed result는 source context보다 우선.
    - failed/cancelled states 표시.
  - Pipeline:
    - T2I -> I2V pipeline detail.
    - live progress summary band.
    - compact stage timeline.
    - long-running I2V 대기 상황 설명.
  - History:
    - mode/state/model/page size filters.
    - asset type filter: All / Images / Videos.
    - terminal job delete action.
    - video rows show actual muted video preview instead of NO THUMBNAIL.
    - image thumbnail 유지.
    - row navigation and delete action verified.

Prompt Enhancement 구현 핵심:
- API: POST /api/prompts/enhance.
- Request fields: prompt, target_mode, target_model, creativity_preset.
- Backend entry: backend/app/services/llm/enhancer.py.
- Prompt builder is sectioned:
  PERSONA, OBJECTIVE, INSTRUCTIONS, CONSTRAINTS, CONTEXT, OUTPUT FORMAT, RESPONSE FORMAT EXAMPLE, USER PROMPT, RECAP.
- User prompt is delimited to reduce instruction injection risk.
- Mode-specific guidance:
  - T2I: subject, scene, background, style, composition, lighting, camera/lens.
  - T2V: temporal action, camera movement, pacing, continuity.
  - I2V: preserve selected source image, describe motion only, do not add unrelated main subjects.
- Creativity Mode:
  - faithful = 0.2
  - balanced = 0.5
  - imaginative = 0.8
  - default balanced.
- Gemini output expected as JSON with enhanced + components.
- Uses response.parsed first, then response.text JSON extraction/fenced JSON/object selection.
- Pydantic/schema validation.
- malformed JSON now gets exactly one STRICT JSON RETRY.
- Safe diagnostics surfaced in UI/API: reason, field, source.
- Raw provider output, credentials, service-account content are not exposed.
- Prompt enhancement is optional:
  - generation does not automatically enhance.
  - frontend shows original/enhanced/components in review panel.
  - user can edit enhanced draft.
  - only Accept draft copies it into main prompt.
  - generation payload uses visible current prompt as final generation prompt.
  - enhancement_id is optional and linked to job only if accepted/valid.
  - mode/model mismatch for enhancement_id is rejected.

QA / important findings:
- T2I Imagen live success.
- T2V Veo live success.
- I2V live success.
- T2I -> I2V pipeline live success.
- Asset detail API verified.
- T2V failure investigation:
  - one old T2V failed after submit/polling with vertex_unknown_error.
  - submit worked and vertex_operation_name existed.
  - likely provider-side operation failure or empty/filtered output.
  - backend now classifies operation.error and empty/filtered output instead of generic unexpected error.
- Veo children/all-age safety:
  - I2V with children/sledding scene was blocked by Vertex safety filters.
  - adult/person I2V succeeded.
  - likely Veo personGeneration/project allowlist policy, not pipeline bug.
  - decision: do not bypass safety filters; document provider constraint.
- Ambiguous person-action prompt:
  - “상사가 불러서 달려나가는 모습” was rejected.
  - calmer/professional rephrasing succeeded.
  - conclusion: short/ambiguous person-action I2V prompts can trigger provider rejection; rephrase as calm/natural motion.
- Prompt enhancement malformed JSON:
  - I2V short Korean prompt “생동감 있게 보여줘” produced malformed_json once.
  - backend now retries malformed JSON once with strict JSON retry.
  - live QA confirmed /api/prompts/enhance returned 201 and generation request was accepted.
- History:
  - asset type filter works.
  - terminal job deletion works.
  - independent delete policy works.
  - video preview works.
- Recent full-ish test counts:
  - backend full pytest reached 283 passed after prompt enhancement retry.
  - frontend lint/build passed after major changes.
  - Some specific verification runs: prompt enhancement related 75 passed; backend after deletion 279 passed; video preview backend pytest passed.

Current task:
- We are starting final submission documentation.
- Required files:
  - README.md: running instructions and tech stack.
  - AI_COLLABORATION.md: Step 3 answers and prompt enhancement strategy.
- User wants to discuss/write documents strategically, not have Codex blindly write everything.
- User may ask for short natural-language Codex CLI prompts to inspect code or draft sections.

README direction:
- Include:
  - Project overview.
  - Tech stack.
  - Runtime requirements:
    Docker, Docker Compose v2.29.7 or compatible, Vertex service-account mounted at /secrets/sa.json.
  - Docker Compose run:
    docker compose up -d --build
    E2B:
    sudo -E docker compose up -d --build --force-recreate frontend backend db
  - Frontend/backend URLs.
  - Features:
    T2I/T2V/I2V, model selection, prompt enhancement, Creativity Mode, review/edit/accept, T2I -> I2V pipeline, progress/timeline, history filters/delete/video preview.
  - API summary.
  - Testing commands.
  - Reliability/edge cases:
    state machine, retry/rate limit, Veo error classification, safety filter/provider rejection, path-safe storage/delete, mock-only tests.
- Do not include credentials or .env contents.

AI_COLLABORATION direction:
- Must answer:
  - Q1: hardest edge case/failure scenario and solution.
  - Q2: what engineer must verify when applying AI-generated code and why.
  - Q3: concrete case of solving complex issue with AI or overcoming AI limitation.
- Also must describe enhance system design principles and prompt strategy.
- Good Q1 main candidate:
  - Veo operation failure classification: submit succeeded, operation name existed, failure occurred during polling, old backend collapsed provider failure/empty/filtered output into vertex_unknown_error. Fixed by checking operation.error and empty/filtered output; tests and live T2V/I2V QA.
- Good Q1 supporting candidate:
  - Gemini prompt enhancement malformed JSON, fixed with safe diagnostics and one strict JSON retry.
- Good Q2 points:
  - state machine transitions.
  - credential safety.
  - no real Vertex/Gemini in tests.
  - google-genai single SDK.
  - no GCS for Veo unless asked.
  - final prompt source of truth.
  - DB/file consistency for deletion.
  - path traversal/symlink safety.
  - active job/dependency deletion protection.
  - provider errors must be classified, not hidden.
- Good Q3:
  - Creativity Mode and prompt enhancement strategy co-design.
  - User proposed faithful/balanced/imaginative.
  - User corrected AI’s over-strict “ban generic words” into “avoid default/filler overuse unless user asks.”
  - User corrected Balanced interpretation: richer style/composition detail can be intended because temperature is higher than Faithful, not necessarily regression.
  - User emphasized manual review-first: enhanced draft must be compared/edited/accepted before generation.
- Prompt Enhancement Strategy comparison:
  - User wants to compare actual strategy with official Google Vertex AI prompt design strategies:
    https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-design-strategies?hl=ko
  - Relevant official concepts:
    - prompt content and structure both matter.
    - components: objective, instructions, constraints, context, examples/few-shot, response format, recap.
    - use system instructions.
    - add context.
    - include few-shot examples.
    - structure prompts with labels/delimiters.
    - experiment with parameter values.
    - iterate prompt strategy.
  - Map to implementation:
    - sectioned prompt builder.
    - mode-specific objective/context/constraints.
    - JSON output format + schema validation.
    - exemplars for T2I/T2V/I2V.
    - creativity presets as parameter experimentation.
    - delimiter around user prompt.
    - malformed JSON retry and diagnostics as operational hardening.
    - review/edit/accept UX as product-level control beyond pure prompt design.

```

## assistant

```text
`superpowers:using-superpowers` 스킬만 확인하고, 이후엔 구현 없이 전략 판독 모드로 맞출게요.
```

## assistant

```text
확인했어. 나는 여기서 **구현자 말고 판독/전략 파트너**로 움직일게.

지금 최선의 다음 단계는 문서 초안 작성 전에 Codex CLI로 **read-only 문서화 재료 점검**을 한 번 시키는 거야:

- 현재 `README.md` 상태
- `docker-compose.yml`, backend/frontend 실행 포트
- 실제 API 라우트 목록
- 테스트/빌드 스크립트
- 최근 구현과 문서에 반영해야 할 기능 누락 여부

그 결과를 가져오면 내가 “README에 뭐 넣고, AI_COLLABORATION에 뭐 넣을지”를 짧게 판독해줄게.  
네가 **“프롬프트 줘”**라고 하면, 그때 Codex CLI에 보낼 짧고 안전한 프롬프트로 써줄게.
```

## user

```text
이게 READEME.md 야 

# [채용 과제] AI 멀티모달 콘텐츠 생성 플랫폼 구축

## **1. 과제 배경 및 목표**

본 과제는 Google Vertex AI의 멀티모달 생성 AI 모델(Imagen, Veo)을 활용해 에셋을 생성하고 관리하는 통합 플랫폼을 구축하는 작업입니다.
 사용자가 텍스트로 이미지를 생성하고, 이미지나 텍스트로 비디오를 제작하며, 복수의 모델 중 적절한 것을 선택하여 실행할 수 있는 서비스를 구축하는 것이 목표입니다.

과제는 제공된 플랫폼 또는 **본인의 코딩 에이전트 환경**에서 자유롭게 수행할 수 있습니다. 제공된 플랫폼에서는 **Claude Code** 또는 **Codex** 를 활용하여 과제 수행이 가능합니다.
본 과제는 AI 도구 없이 완성하기 어려운 난이도로 설계되어 있으며, **AI를 얼마나 전략적으로 활용하는지** 또한 평가 대상입니다.

- **제한 시간**: 과제 시작 후 3일
- **언어 및 기술 스택**: 자율 선택
- **참고 사항:** 제공되는 Vertex AI 인증 키는 3일 후 자동 만료됩니다.

## **2. API 명세 및 제한 사항**
### **[제공 리소스]**
- **인증 및 GCP 정보**: Vertex AI 인증 키, Project ID (프로젝트 루트에 제공)
- **LLM**: 동일 Vertex AI 인증 키로 Gemini 및 Claude 모델 사용 가능
### **[사용 가능 모델 및 제한]**
| **분류** | **적용 도구** | **모델** | **특성** | **Rate Limit** | **비용** |
|---|---|---|---|---|---|
| Image | Text-to-Image | imagen-4.0-fast-generate-001 | 빠른 생성, 표준 품질 | 75회/분 | $0.02/장 |
| Image | Text-to-Image | imagen-4.0-generate-001 | 고품질, 느린 생성 | 75회/분 | $0.04/장 |
| Image | Text-to-Image | imagen-4.0-ultra-generate-001 | 최고 품질 | 75회/분 | $0.06/장 |
| Video | Text-to-Video / Image-to-Video | veo-3.0-fast-generate-001 | 빠른 생성, 사운드 포함 | 10회/분 | $0.15/초 |
| Video | Text-to-Video / Image-to-Video | veo-3.0-generate-001 | 고품질 | 10회/분 | $0.40/초 |

- 동일 Vertex AI 인증 키로 모든 모델에 접근할 수 있으며, **모델별 Rate Limit은 독립적으로 적용**됩니다.
- API 가이드: [Imagen 4](https://cloud.google.com/vertex-ai/generative-ai/docs/models/imagen/4-0-generate) /
 [Image Generation](https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images) /
  [Veo 3](https://cloud.google.com/vertex-ai/generative-ai/docs/models/veo/3-0-generate) /
   [Text-to-Video](https://cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-text) /
    [Image-to-Video](https://cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-an-image)

## **3. 시스템 기능 명세 (필수 구현)**
> **참고**: 단순히 동작하는 것을 넘어, **에러 상태 처리, 엣지케이스 대응, 코드 구조화** 등 AI 도구만으로는 놓치기 쉬운 엔지니어링 판단이 평가에 반영됩니다.

### **3.1. [BE] 에셋 생성 및 관리**
1. 3가지 생성 모드(Text-to-Image, Text-to-Video, Image-to-Video)를 지원하는 API를 구축합니다. 사용자가 **모델을 선택**하여 생성을 요청할 수 있어야 합니다.
2. 생성된 에셋의 정보를 DB에 저장하고, 결과 파일은 로컬에 저장합니다. 에셋 상세 정보를 조회하는 API를 구현합니다.
3. 제공된 LLM API를 활용하여 **프롬프트 자동 개선(enhance) 시스템**을 구현합니다.

    - 사용자의 원본 프롬프트를 분석하여 **대상 생성 모델에 맞(Imagen/Veo)의 특성게** 최적화합니다.
    - 프롬프트의 구성 요소(피사체, 배경, 스타일, 구도, 조명 등)를 인식하고, 각 요소별로 적절한 수준의 디테일을 보강합니다.
    - 사용자는 개선 전/후 프롬프트를 **비교 확인**하고, 개선된 프롬프트를 **편집**한 뒤 생성을 요청할 수 있어야 합니다.
    - enhance 시스템의 설계 원칙과 프롬프트 전략을 `AI_COLLABORATION.md`에 기술해 주세요.

4. API 호출이 실패할 경우를 대비한 **재시도 전략**을 구현합니다.
5. 생성된 이미지를 Image-to-Video의 입력으로 사용하여 비디오를 생성할 수 있는 **에셋 파이프라인**을 구현합니다. (Text-to-Image → Image-to-Video 연계)
6. 핵심 비즈니스 로직에 대한 **자동화 테스트**를 작성합니다.

### **3.2. [FE] 사용자 인터페이스**

1. 생성 모드 전환, 모델 선택, 프롬프트 입력이 가능한 **생성 인터페이스**를 구현합니다.
2. LLM이 개선한 프롬프트를 사용자가 **확인·편집**할 수 있는 흐름을 구현합니다.
3. 생성 작업이 진행 중일 때, 사용자에게 **유의미한 대기 경험**을 제공합니다. (단순 스피너가 아닌, 현재 상황을 파악할 수 있는 정보를 포함)
4. 완료된 결과물(이미지/비디오)을 표시합니다.
5. **생성 히스토리**를 조회할 수 있습니다.

**※ 안내**: 위 기능이 포함된다면 UI/UX 구성은 자유입니다.

### **3.3. [Infra] 실행 환경**

- 전체 서비스(프론트엔드, 백엔드, DB 등)를 **Docker Compose**로 구성하여 `docker compose up` 한 번으로 실행할 수 있어야 합니다.

## **4. 과제 수행 단계 (3 Step)**

- **Step 1: 핵심 기능 구현 (필수)**: 섹션 3의 모든 요구사항을 완성합니다.

- **Step 2: 부가 기능 (선택 사항)**: 아래는 예시입니다. 본인의 강점을 보여줄 기능을 **자유롭게 선택하거나 직접 정의**하세요.

    - **채팅 에이전트**: 제공된 LLM API와 Tool Use(Function Calling)를 활용하여, 사용자가 **대화만으로** 이미지/비디오를 생성할 수 있는 채팅 인터페이스를 구현합니다.     에이전트가 사용자의 의도를 해석하고, 적절한 생성 모델 API를 도구로 호출하여 결과를 반환합니다.
    - **예산 관리 시스템**: 모델별 비용을 추적하고, 일일 한도를 초과하지 않도록 제어하는 비용 관리 기능.
    - **동시 요청 및 Rate Limit 관리**: 여러 생성 요청이 동시에 들어올 때, 각 모델의 Rate Limit을 초과하지 않도록 처리하는 큐잉 시스템.
    - **모델 비교 모드**: 동일 프롬프트로 여러 모델의 결과를 나란히 비교.

- **Step 3: 심층 질문 (필수)**: AI_COLLABORATION.md 파일에 다음 질문에 대한 답변을 작성해 주세요.

    - Q1. 구현 과정에서 발생한 **가장 까다로운 엣지케이스 또는 장애 시나리오**는 무엇이었으며, 어떻게 해결했는지 설명해 주세요.
    - Q2. AI가 생성한 코드를 실제 프로젝트에 반영할 때, 엔지니어로서 **가장 중요하게 검증해야 하는 항목**은 무엇이며 그 이유는?
    - Q3. 이번 과제에서 AI와 함께 복잡한 문제를 해결했거나, AI의 한계를 본인이 직접 극복한 구체적 사례를 작성해 주세요.

## **5. 산출물**

> 모든 산출물은 제출 시 자동으로 포함됩니다. 응시자는 **README.md** 와 **AI_COLLABORATION.md** 의 내용 작성에 집중하면 됩니다. 자세한 제출 방법은 별도 플랫폼 가이드를 참고하세요.

| 산출물 | 필수 여부 | 비고 |
|---|---|---|
| 소스 코드 | 필수 | 작업 디렉토리 전체 (자동 제출) |
| 프로젝트 컨텍스트 파일 | 필수 | CLAUDE.md / AGENTS.md 등 AI 도구에 제공한 프로젝트 컨텍스트와 사용한 Skill, Plugin 전체. AI가 작성한 plan 파일 등 (자동 제출) |
| README.md | 필수 | 구동 방법 및 기술 스택 명시 |
| AI_COLLABORATION.md | 필수 | Step 3 내용 |
| 세션 히스토리 | 선택 | 본인의 코딩 에이전트 환경에서 수행한 경우 필수. zip 내 `session-history/` 디렉토리에 포함 |

> **본인의 코딩 에이전트 환경에서 직접 수행하는 경우**, 플랫폼 대신 위 산출물 전체를 zip 파일 형태로 별도 제출해야 합니다.

```

## assistant

```text
좋아. 이건 **현재 프로젝트 README가 아니라 과제 원문 브리프**야. 최종 제출용으로는 그대로 두면 위험해. 평가자가 보고 싶은 건 “이 앱을 어떻게 실행하고, 무엇을 구현했고, 어떤 기술 판단을 했는가”라서 README를 프로젝트 문서로 교체해야 해.

추천 방향:

1. `README.md`
   - 프로젝트 개요
   - 기술 스택
   - 실행 요구사항
   - Docker Compose 실행법
   - 주요 URL
   - 구현 기능
   - API 요약
   - 테스트 명령
   - 신뢰성/엣지케이스 대응

2. `AI_COLLABORATION.md`
   - Step 3 Q1/Q2/Q3 답변
   - prompt enhancement 설계 원칙
   - Google Vertex prompt design strategies와의 대응 관계
   - AI가 낸 제안 중 네가 수정/통제한 사례

핵심 판단: README에는 과제 설명을 길게 반복하지 말고, **“우리가 만든 제품 설명서”**로 바꿔야 해. 과제 원문은 git history에 남아 있으면 충분하고, 최종 제출 시 README는 실행 가능성과 구현 범위를 증명하는 문서가 되어야 함.

다음 Codex CLI 작업은 `README.md` 초안 작성이 맞아. 다만 한 번에 AI_COLLABORATION까지 쓰게 하지 말고, README부터 끝내는 게 안전해.
```

## user

```text
AI_COLLABORATION.md 에서  
prompt enhancement 설계 원칙을 지금 작성할거야 

```

## assistant

```text
좋아. 그 섹션은 “프롬프트 잘 씀”보다 **제품/엔지니어링 설계로 통제했다**는 인상을 줘야 해.

구성은 이렇게 가면 좋아:

1. **목표**
   - 사용자의 짧거나 모호한 입력을 Imagen/Veo가 이해하기 좋은 생성 지시로 바꾸되, 사용자의 의도는 보존한다.

2. **모드별 최적화**
   - T2I: subject, scene, style, composition, lighting, camera/lens
   - T2V: temporal action, camera movement, pacing, continuity
   - I2V: source image를 보존하고 motion prompt 중심으로 보강

3. **Creativity Mode**
   - faithful/balanced/imaginative로 보강 강도와 temperature를 조절
   - faithful은 의도 보존, imaginative는 확장, balanced는 기본값

4. **안전한 구조화**
   - PERSONA, OBJECTIVE, INSTRUCTIONS, CONSTRAINTS, CONTEXT, OUTPUT FORMAT 등 섹션화
   - user prompt를 delimiter로 감싸 instruction injection 위험 완화
   - JSON schema로 결과를 검증

5. **사용자 통제**
   - enhancement는 자동 적용하지 않음
   - 원본/개선본/구성요소를 비교
   - 사용자가 편집하고 accept해야 generation prompt가 됨

6. **운영 안정성**
   - malformed JSON은 raw output 노출 없이 safe diagnostics 제공
   - 한 번만 strict JSON retry
   - credentials/provider raw output은 노출하지 않음

톤은 이런 식이 좋아:

> Prompt enhancement는 “사용자를 대신해 프롬프트를 결정하는 기능”이 아니라, 사용자의 의도를 생성 모델에 더 잘 전달하기 위한 controlled drafting layer로 설계했다.

이 문장이 섹션 첫 문장으로 꽤 좋아.  
필요하면 내가 다음에 바로 붙여넣을 수 있는 한국어 초안으로 압축해줄게.
```

## user

```text
공식 문서에서 우리가 직접 연결할 만한 축은 이거야:

Vertex AI prompt strategy	우리 구현과 연결
콘텐츠와 구조가 모두 중요	enhancer system prompt를 PERSONA / OBJECTIVE / INSTRUCTIONS / CONSTRAINTS / CONTEXT / OUTPUT FORMAT / EXAMPLE / USER PROMPT / RECAP로 섹션화
목표, 요청사항, 제약조건, 컨텍스트, 응답 형식	mode별 목표, 금지사항, target model, creativity preset, JSON output format을 명시
시스템 안내 사용	Gemini enhancer에게 “prompt enhancement expert” 역할과 JSON-only 제약 부여
퓨샷 예시	T2I/T2V/I2V별 exemplar로 원하는 output 구조를 보여줌
컨텍스트 정보 추가	target mode/model, creativity preset, I2V source-preservation rules 제공
구조화된 응답 형식	enhanced, components JSON schema + Pydantic validation
프롬프트 반복/파라미터 실험	faithful/balanced/imaginative temperature presets로 사용자 제어권 제공
실패 체크리스트: 명확성, 출력 형식 누락, 과도한 작업	vague I2V prompt와 malformed JSON 문제를 strict retry + diagnostics로 보강
내가 보기에 네 전략에서 강조해야 할 차별점은 이거야:

Prompt enhancement는 자동 대체가 아니라 review-first

공식 전략은 “좋은 prompt를 만드는 방법”에 가깝고, 너는 이것을 제품 UX로 확장했음.
사용자가 original/enhanced/components를 보고 편집/수락해야 final generation prompt가 됨.
모델별 prompt strategy

Imagen은 공간/구도/조명.
T2V는 시간/카메라/움직임/연속성.
I2V는 source image preservation + motion 중심.
이건 과제 요구의 “대상 생성 모델에 맞게 최적화”와 직접 연결됨.
Creativity Mode

공식 문서의 parameter experimentation을 제품 기능으로 만든 것.
faithful=보존, balanced=기본 확장, imaginative=풍부한 시각적 보강.
중요한 건 사용자가 이 정도를 선택한다는 점.
LLM output도 불신하고 검증

JSON schema, parser fallback, malformed JSON 1회 retry.
이게 “AI가 만든 출력도 production input으로 바로 믿지 않는다”는 엔지니어링 판단임.
출처로는 이 공식 문서를 쓰면 돼: Vertex AI Prompt design strategies.
특히 문서의 “프롬프트 구성요소”, “권장사항”, “프롬프트 상태 체크리스트”랑 우리 구현을 비교하면 좋다.

```

## assistant

````text
맞아. 이 정리는 방향이 아주 좋아. 그대로 쓰되, `AI_COLLABORATION.md`에서는 표만 던지기보다 **“공식 prompt strategy를 그대로 복붙한 게 아니라 제품 흐름으로 번역했다”**는 서술을 앞에 두는 게 좋아.

내가 추천하는 섹션 구조:

```md
## Prompt Enhancement Strategy

### Design Goal
Prompt enhancement is designed as a controlled drafting layer, not an automatic replacement for the user's prompt.

### Mapping to Vertex AI Prompt Design Strategies
| Vertex AI strategy | Implementation |
| ... |
```

그 다음에 차별점을 짧게 별도 섹션으로:

```md
### Product-Level Controls Beyond Prompting
```

여기에 네가 말한 네 가지를 넣으면 됨:

- review-first: original/enhanced/components 비교 후 accept해야 적용
- model-specific enhancement: Imagen/T2V/I2V 다른 보강 기준
- Creativity Mode: parameter experimentation을 UX로 노출
- distrust LLM output: JSON schema, validation, retry, safe diagnostics

주의할 점은 하나야. 공식 문서 출처를 쓸 때 URL은 넣되, 너무 “공식 문서에 따르면” 식으로 길게 인용하지 말고, “I used the official Vertex AI prompt design strategies as a checklist” 정도로 두면 자연스럽다.

문장 톤은 이렇게 가면 좋아:

> I treated the Vertex AI prompt design guidance as an engineering checklist, then added product-level controls around it so the model output would remain inspectable, editable, and rejectable by the user.

이게 핵심 메시지야.  
다음에 네가 “프롬프트 줘”라고 하면, Codex CLI가 이 섹션만 `AI_COLLABORATION.md`에 안전하게 작성하도록 짧은 프롬프트 만들어줄게.
````

## user

```text
한글로 보여줘 

```

## assistant

````text
좋아. `AI_COLLABORATION.md`에 넣을 수 있는 한국어 초안은 이렇게 가면 돼.

```md
## Prompt Enhancement Strategy

Prompt enhancement는 사용자의 프롬프트를 자동으로 대체하는 기능이 아니라, 사용자의 의도를 생성 모델에 더 잘 전달하기 위한 controlled drafting layer로 설계했다. 따라서 개선된 프롬프트는 바로 generation에 사용되지 않고, 사용자가 원본/개선본/구성 요소를 비교한 뒤 직접 편집하고 수락해야 최종 generation prompt가 된다.

설계 시에는 Google Vertex AI의 Prompt design strategies 문서를 체크리스트처럼 사용했다. 공식 문서가 강조하는 prompt content와 structure, objective, instructions, constraints, context, examples, response format, iteration 원칙을 enhancer system prompt와 제품 UX에 함께 반영했다.

| Vertex AI prompt strategy | 구현에서의 적용 |
|---|---|
| 콘텐츠와 구조가 모두 중요 | enhancer system prompt를 PERSONA / OBJECTIVE / INSTRUCTIONS / CONSTRAINTS / CONTEXT / OUTPUT FORMAT / EXAMPLE / USER PROMPT / RECAP 섹션으로 나누어 구성했다. |
| 목표, 요청사항, 제약조건, 컨텍스트, 응답 형식 명시 | target mode, target model, creativity preset, mode별 금지사항, JSON output format을 명시했다. |
| 시스템 안내 사용 | Gemini enhancer에게 prompt enhancement expert 역할을 부여하고, JSON-only 응답 제약을 설정했다. |
| 예시 제공 | T2I, T2V, I2V별 exemplar를 제공해 원하는 출력 구조와 보강 방향을 명확히 했다. |
| 컨텍스트 정보 추가 | target mode/model, creativity preset, I2V source image preservation rule을 enhancer context로 제공했다. |
| 구조화된 응답 형식 | enhanced prompt와 components를 JSON schema로 받도록 설계하고, Pydantic validation으로 검증했다. |
| 프롬프트 반복 및 파라미터 실험 | faithful/balanced/imaginative Creativity Mode를 제공하고, 각 preset에 다른 temperature를 적용했다. |
| 실패 체크리스트 활용 | vague I2V prompt나 malformed JSON 같은 실패 사례를 기준으로 strict JSON retry와 safe diagnostics를 추가했다. |

특히 과제 요구사항인 “대상 생성 모델에 맞는 최적화”를 위해 모드별 보강 기준을 다르게 설계했다. T2I에서는 subject, scene, background, style, composition, lighting, camera/lens처럼 정적인 이미지 품질에 중요한 요소를 보강한다. T2V에서는 temporal action, camera movement, pacing, continuity처럼 시간에 따른 움직임과 영상 연속성을 중심으로 보강한다. I2V에서는 새 장면을 마음대로 추가하지 않고, 선택된 source image를 보존한 상태에서 motion prompt를 구체화하도록 제약했다.

Creativity Mode는 공식 문서의 parameter experimentation 원칙을 사용자 기능으로 확장한 것이다. faithful은 원본 의도 보존을 우선하고, balanced는 기본적인 시각적 보강을 제공하며, imaginative는 더 풍부한 스타일과 장면 구성을 제안한다. 중요한 점은 이 강도를 시스템이 임의로 결정하지 않고 사용자가 선택한다는 것이다.

마지막으로, LLM이 생성한 enhancement output도 production input으로 바로 신뢰하지 않았다. 응답은 JSON schema로 검증하고, parser fallback을 두었으며, malformed JSON이 발생하면 raw provider output을 노출하지 않고 한 번만 strict JSON retry를 수행한다. 실패 시에도 credential, service account 내용, provider raw output은 API/UI에 노출하지 않고 reason, field, source 같은 안전한 diagnostics만 반환한다.
```

이 정도면 충분히 “공식 문서를 이해했고, 그대로 구현이 아니라 제품/엔지니어링 판단으로 확장했다”는 인상이 나.
````

## user

```text
READEME 부터 작성해보려고 하는데 

우리 docker 빌드랑 차이가 좀있는 것 같아 확인해봐 

🚀 Vertex Studio - AI Multimodal Content Generation Platform개요: Google Vertex AI의 Imagen 4, Veo 3, Gemini 2.5 Flash를 활용하여 이미지 및 비디오를 생성하고 관리하는 단일 인스턴스 기반 멀티모달 콘텐츠 생성 플랫폼입니다.📌 1. 프로젝트 아키텍처 및 핵심 설계분산 큐(Celery/Redis) 없이, 과제 범위 및 단일 인스턴스 전제를 충족하기 위해 PostgreSQL Job Table과 FastAPI 내부 asyncio runner를 조합하여 구현했습니다.동시성 및 속도 제한: FOR UPDATE SKIP LOCKED 구문으로 pending 상태의 job을 안전하게 가져오며, 전역 세마포어와 모델별 sliding-window rate limiter를 통해 동시 실행 및 분당 호출 수(RPM)를 제어합니다.상태 관리: 모든 Job의 상태 전이는 app/state_machine.py의 transition(...)으로만 수행되며, 잘못된 전이 시 예외를 발생시키고 테스트 코드로 검증합니다.[React SPA]
     │
     ▼
[FastAPI API]
     │
     ├──► [PostgreSQL] (jobs, assets, prompt_enhancements)
     │
     ├──► [In-process Asyncio Job Runner]
     │         │
     │         ├──► [Vertex AI] (Imagen 4 / Veo 3 / Gemini 2.5 via google-genai SDK)
     │         └──► [Local Storage] (/data/assets/{job_uuid}/output.{png|mp4})
     │
     └──► [/files/{job_uuid}/{filename}] (로컬 에셋 스트리밍)
🛠️ 2. 기술 스택 & 사용 모델기술 스택Backend: Python 3.11, FastAPI, SQLAlchemy async, asyncpg, PostgreSQL 16Frontend: Vite, React, TypeScript, @tanstack/react-queryAI SDK: google-genai 단일 SDK 사용 (Vertex AI 연동)Infra: Docker Compose, Postgres named volume, Local asset named volume지원 모델 라인업Imagen (이미지): imagen-4.0-fast-generate-001, imagen-4.0-generate-001, imagen-4.0-ultra-generate-001Veo (비디오): veo-3.0-fast-generate-001, veo-3.0-generate-001Prompt Enhance (프롬프트 개선): gemini-2.5-flash✨ 3. 주요 기능 명세영역구현 내용생성 모드Text-to-Image (T2I), Text-to-Video (T2V), Image-to-Video (I2V)모델 선택Imagen 4 (Fast/Standard/Ultra), Veo 3 (Fast/Standard) 지원프롬프트 개선Gemini 2.5 Flash 기반 enhance, 원본/개선본 비교 및 사용자 편집/수락 UX 제공파이프라인Text-to-Image(부모) 완료 후 Image-to-Video(자식) 작업으로 자동 연결 실행작업 처리Postgres DB에 job 저장 후 FastAPI 프로세스 내부 asyncio runner가 순차 처리상태 UXpending ➔ queued ➔ generating ➔ polling ➔ downloading ➔ completed / failed에셋 관리생성 결과 메타데이터는 DB 저장, 미디어 파일은 로컬 DATA_DIR 저장 및 /files/... 스트리밍히스토리mode / state / model / asset type 필터링, 상세 화면 조회, terminal job(최종 상태) 삭제안정성 정책모델별 sliding-window rate limit, retry/backoff, Veo LRO(Long-Running Operation) resume, orphan job sweep테스트Vertex AI/LLM 실제 호출 없이 Mock 기반으로 백엔드 로직 전반 검증🔌 4. API 엔드포인트 요약MethodPath설명GET/api/healthDB 및 Vertex AI Readiness(준비 상태) 확인POST/api/prompts/enhanceGemini를 이용한 Prompt Enhancement(개선) 결과 생성POST/api/generationsT2I / T2V / I2V 단일 생성 Job 생성GET/api/generationsJob History 조회 및 필터링 (mode, state, model 등)GET/api/generations/{job_id}특정 Job의 상세 상태 및 생성된 Asset 정보 조회DELETE/api/generations/{job_id}완료/실패한 Job 정보 및 로컬 저장소 파일 삭제POST/api/pipelinesT2I(부모) + Blocked I2V(자식) 연계 파이프라인 생성GET/api/pipelines/{parent_job_id}파이프라인 부모/자식 작업 관계 및 진행 상황 조회GET/api/assets/{asset_id}에셋 메타데이터 조회GET/files/{local_path}DATA_DIR 내 상대 경로 검증 후 안전하게 파일 스트리밍🗂️ 5. 주요 API 요청 예시 (JSON)JSON{
  "prompt": "고양이가 집에서 뛰어노는 사진",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced"
}
creativity_preset은 faithful, balanced, imaginative를 지원하며, Gemini 프롬프트 개선 시의 temperature 및 컨텍스트 전략을 조절합니다 (Imagen/Veo 자체의 generation temperature 설정이 아님).JSON{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1,
  "auto_enhance": false
}
JSON{
  "mode": "t2v",
  "prompt": "A slow dolly forward through a rainy neon alley",
  "model": "veo-3.0-fast-generate-001",
  "aspect_ratio": "16:9",
  "duration_sec": 4,
  "auto_enhance": false
}
JSON{
  "mode": "i2v",
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in puddles",
  "model": "veo-3.0-fast-generate-001",
  "source_asset_id": "00000000-0000-4000-8000-000000000000",
  "aspect_ratio": "16:9",
  "duration_sec": 4,
  "auto_enhance": false
}
JSON{
  "image_prompt": "Neon-soaked Seoul alley at night with a cyclist",
  "video_prompt": "Slow dolly forward as the cyclist passes and steam rises",
  "image_model": "imagen-4.0-fast-generate-001",
  "video_model": "veo-3.0-fast-generate-001",
  "image_aspect_ratio": "1:1",
  "video_aspect_ratio": "16:9",
  "duration_sec": 4
}
⚙️ 6. 환경 변수 및 실행 방법.env 설정 파일 양식⚠️ 주의: GCP 서비스 계정 JSON 내용을 직접 텍스트로 복사하지 말고, Host 머신의 절대 경로만 지정하세요.코드 스니펫POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

# docker-compose 환경에서는 Vite 프록시 처리를 위해 비워둡니다.
VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
🐳 Docker Compose로 전체 실행Bash# 전체 서비스 빌드 및 실행
docker compose up --build

# 서비스 정상 구동 확인 (Smoke Test)
curl http://localhost:8000/api/health
Frontend: http://localhost:5173Backend Docs: http://localhost:8000/docs💻 로컬 개발 서버 직접 실행 시Backend:Bashcd backend
python3 -m pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000
Frontend:Bashcd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
🚫 7. 알려진 제한 사항 (Known Limitations)사용자 취소 기능: cancelled 상태는 상태 머신에 구현되어 있으나, 취소 API 및 UI 버튼은 미구현 상태입니다.진행도 세부 UX: 큐 대기 순위(Queue position), 퍼센트 바(Progress percent), 평균 완료 예상 시간 등은 제공되지 않으며 2초 간격 폴링 상태만 노출됩니다.자동 개선: Job 생성 시 auto_enhance=true 옵션은 지원하지 않으며, 명시적으로 /api/prompts/enhance를 거치는 흐름만 지원합니다.파이프라인 제한: 현재 Pipeline 모드 구조상 부모 T2I 단계를 거칠 때 별도의 프롬프트 enhance review 단계를 제공하지 않습니다.스토리지 및 마이그레이션: 클라우드 GCS가 아닌 로컬 Docker named volume을 사용하며, 데이터베이스는 Alembic 같은 마이그레이션 도구 없이 SQLAlchemy create_all 기반으로 기동됩니다.콘텐츠 가드레일: Veo 모델을 통한 특정 인물/아동/전연령 세이프티 정책 위반 시, 별도 우회 없이 vertex_safety_blocked 계열 오류 사유를 사용자에게 그대로 노출합니다.

```

## assistant

```text
README 초안 자체는 방향이 좋아요. 다만 지금은 “멋진 문서”보다 “실제 compose/API와 1:1로 맞는 문서”가 더 중요해서, 몇 군데는 제출 전에 read-only 확인이 필요해 보여요.
```

## assistant

```text
맞아. 이 README 초안은 방향은 좋은데, **실제 구현/compose와 어긋날 가능성이 있는 문장**이 몇 개 보여.

가장 먼저 고쳐야 할 후보는 이거야.

- Docker 실행 명령이 현재 운영 원칙과 다름  
  `docker compose up --build`보다 기본은 `docker compose up -d --build`, E2B는 반드시  
  `sudo -E docker compose up -d --build --force-recreate frontend backend db`  
  를 별도로 적는 게 맞아.

- API 예시에 `auto_enhance`가 들어가 있음  
  우리 구현 방향은 “generation이 자동 enhance하지 않음”이고, `enhancement_id`만 optional linked야. `auto_enhance`가 실제 schema에 없으면 README 예시가 실패 예시가 될 수 있음. 빼는 게 안전해.

- “Veo LRO resume, orphan job sweep”은 위험한 주장  
  실제 구현이 확실히 있으면 넣어도 되지만, 현재 기억상 핵심은 “operation polling, error classification, retry/rate limit”이야. resume/sweep은 Codex CLI로 확인 전엔 삭제하거나 약하게 써야 함.

- “순차 처리” 표현은 부정확할 수 있음  
  runner는 semaphore로 bounded concurrency를 쓰므로 “순차 처리”보다 “제한된 동시 처리”가 맞아.

- `/api/health`가 Vertex readiness까지 확인하는지 확인 필요  
  단순 DB/앱 health라면 “DB 및 서비스 상태 확인” 정도로 낮춰야 함.

- `/files/{local_path}` 경로 표기는 실제 route와 맞춰야 함  
  Range request 지원까지 구현했으니 “Range request를 지원하는 안전한 파일 스트리밍”은 좋지만, path param 이름은 코드 기준으로 맞춰야 해.

- Known Limitations가 약간 방어적으로 길어 보임  
  제출 README에서는 제한사항을 너무 많이 앞세우기보다, “Operational Notes / Provider Constraints”로 정리하는 게 더 좋아. 특히 Veo safety filter는 제한이라기보다 provider constraint로 쓰는 게 자연스러움.

내 판단으로는 README를 바로 쓰기 전에 Codex CLI에 **read-only fact check**를 한 번 시키는 게 안전해. 확인 대상은 `docker-compose.yml`, backend route 목록, schemas, frontend env/proxy, test scripts 정도.  
네가 “프롬프트 줘”라고 하면 그 용도의 짧은 프롬프트로 줄게.
```

## user

```text
우선 docker 실행부터 고쳐보자 , 
실제 docker--compose.yml 파일이야 
# Phase 0 skeleton — full configuration finalized in Phase 15. 


# `version:` key omitted intentionally for docker-compose v1+v2 compatibil
ity.                                 
                                                                          
services:                                                                 
  db:                                
    image: postgres:16-alpine                                             
    environment:                     
      POSTGRES_USER: ${POSTGRES_USER:?Set POSTGRES_USER in .env or pass --
env-file .env.example}               
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .en
v or pass --env-file .env.example}                                        
      POSTGRES_DB: ${POSTGRES_DB:?Set POSTGRES_DB in .env or pass --env-fi
le .env.example}                     
    healthcheck: 
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"
]                                                                         
      interval: 5s                                                        
      timeout: 5s                                                               retries: 10
    volumes:                         
      - pgdata:/var/lib/postgresql/data
                                                                          
  backend:                                                                
    build: ./backend
    depends_on:                                                           
      db:                                                                 
        condition: service_healthy                                        
    environment:                                                          
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:?Set POSTGRES_USE
R in .env or pass --env-file .env.example}:${POSTGRES_PASSWORD:?Set POSTGR
ES_PASSWORD in .env or pass --env-file .env.example}@db:5432/${POSTGRES_DB
:?Set POSTGRES_DB in .env or pass --env-file .env.example}                
      GOOGLE_APPLICATION_CREDENTIALS: ${GOOGLE_APPLICATION_CREDENTIALS:?Se
t GOOGLE_APPLICATION_CREDENTIALS to /secrets/sa.json}                           GCP_PROJECT_ID: ${GCP_PROJECT_ID:-}          
      GCP_LOCATION: ${GCP_LOCATION:?Set GCP_LOCATION in .env or pass --env-file .env.example}                                                       
      ENHANCE_MODEL: ${ENHANCE_MODEL:?Set ENHANCE_MODEL in .env or pass --
env-file .env.example}               
      DATA_DIR: ${DATA_DIR:?Set DATA_DIR in .env or pass --env-file .env.e
xample}                                                                   
      JOB_RUNNER_CONCURRENCY: ${JOB_RUNNER_CONCURRENCY:-10}
    volumes:                                                              
      - ${GOOGLE_APPLICATION_CREDENTIALS_HOST:?Set GOOGLE_APPLICATION_CRED
ENTIALS_HOST to the host service-account JSON path}:/secrets/sa.json:ro   
      - assets:/data/assets          
      - ./backend/app:/app/app                                            
      - ./backend/tests:/app/tests                                        
    ports:                                                                
      - "8000:8000"                  
                  
  frontend:                                                               
    build: ./frontend                                                     
    depends_on:                                                           
      - backend                                                               environment: 
      VITE_API_BASE: ${VITE_API_BASE:-}
      VITE_API_PROXY_TARGET: ${VITE_API_PROXY_TARGET:-http://backend:8000}
      VITE_ALLOWED_HOSTS: ${VITE_ALLOWED_HOSTS:-5173-${E2B_SANDBOX_ID}.e2b
.app}                                                                     
    volumes:                         
      - ./frontend/src:/app/src                                           
      - ./frontend/index.html:/app/index.html                             
      - ./frontend/vite.config.ts:/app/vite.config.ts                     
    ports:                                                                
      - "5173:5173"                               
volumes:                                                                  
  pgdata:                                                                 
  assets:                 


```

## assistant

````text
좋아. 이 compose 기준이면 README의 실행 섹션은 이렇게 고치는 게 맞아.

핵심은 **`.env` 필수**, **서비스 계정 JSON은 host path로 mount**, **컨테이너 내부 경로는 `/secrets/sa.json` 고정**, **E2B에서는 `sudo -E` 필수**야.

```md
## Running with Docker Compose

This project is designed to run the full stack with Docker Compose: PostgreSQL, FastAPI backend, and Vite React frontend.

### 1. Prepare environment variables

Create a `.env` file from `.env.example` and fill in the required values.

Important credential rule:

- Do not paste the service-account JSON content into `.env`.
- Set `GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json`.
- Set `GOOGLE_APPLICATION_CREDENTIALS_HOST` to the absolute host path of the service-account JSON file.
- Docker Compose mounts that host file into the backend container as `/secrets/sa.json:ro`.

Required runtime values include:

```env
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10
VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
```

### 2. Start the stack

For a normal local environment:

```bash
docker compose up -d --build
```

For the E2B assignment environment, preserve environment variables with `sudo -E`:

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```

### 3. Open the app

Local URLs:

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

E2B public URLs:

- Frontend: `https://5173-${E2B_SANDBOX_ID}.e2b.app`
- Backend: `https://8000-${E2B_SANDBOX_ID}.e2b.app`

### 4. Stop the stack

```bash
docker compose down
```

To also remove database and asset volumes:

```bash
docker compose down -v
```

Use `down -v` only when you intentionally want to delete local PostgreSQL data and generated assets.
```

README에는 `docker compose up --build`보다 위처럼 `-d` 붙인 형태가 좋아. 그리고 기존 초안의 “Vite 프록시 처리를 위해 비워둡니다”는 맞긴 한데, `VITE_API_BASE=`가 프론트에서 같은 origin/proxy를 쓰게 한다는 정도로만 설명하면 충분해.
````

## user

```text
한글로 만들어줘 

```

## assistant

`````text
README용 한글 섹션은 이렇게 쓰면 좋아.

````md
## 실행 방법

이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행하도록 구성되어 있습니다.

### 1. 환경 변수 준비

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 채웁니다. `.env.example`이 있는 경우 이를 복사해 사용할 수 있습니다.

서비스 계정 키는 다음 규칙을 따릅니다.

- 서비스 계정 JSON 내용을 `.env`에 직접 붙여넣지 않습니다.
- `GOOGLE_APPLICATION_CREDENTIALS`는 컨테이너 내부 경로인 `/secrets/sa.json`으로 설정합니다.
- `GOOGLE_APPLICATION_CREDENTIALS_HOST`는 호스트 머신에 있는 서비스 계정 JSON 파일의 절대 경로로 설정합니다.
- Docker Compose는 이 파일을 백엔드 컨테이너의 `/secrets/sa.json`에 read-only로 마운트합니다.

예시:

```env
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
```

### 2. 전체 서비스 실행

일반 로컬 환경에서는 다음 명령으로 실행합니다.

```bash
docker compose up -d --build
```

E2B 과제 환경에서는 `sudo` 실행 시 환경 변수를 보존해야 하므로 다음 명령을 사용합니다.

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```

### 3. 접속 URL

로컬 환경:

- Frontend: http://localhost:5173
- Backend API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

E2B 환경:

- Frontend: `https://5173-${E2B_SANDBOX_ID}.e2b.app`
- Backend: `https://8000-${E2B_SANDBOX_ID}.e2b.app`

### 4. 서비스 종료

```bash
docker compose down
```

PostgreSQL 데이터와 생성된 asset volume까지 함께 삭제하려면 다음 명령을 사용합니다.

```bash
docker compose down -v
```

`docker compose down -v`는 로컬 DB 데이터와 생성된 에셋 파일을 삭제하므로, 의도한 경우에만 사용합니다.
````

이 버전이 compose 파일이랑 가장 잘 맞아. 특히 `/secrets/sa.json`과 `GOOGLE_APPLICATION_CREDENTIALS_HOST` 설명은 README에 꼭 있어야 해.
`````

## user

```text
내 판단으로는 README를 바로 쓰기 전에 Codex CLI에 read-only fact check를 한 번 시키는 게 안전해. 확인 대상은 docker-compose.yml, backend route 목록, schemas, frontend env/proxy, test scripts 정도.
네가 “프롬프트 줘”라고 하면 그 용도의 짧은 프롬프트로 줄게. 
이거 진행해보자 

```

## assistant

````text
좋아. 이건 **수정 금지 read-only 조사**로 가면 돼.

Codex CLI에 보낼 프롬프트:

```text
Read-only fact check for final README. Do not edit files, do not run servers, do not install anything, and do not use browser/Chromium.

You are in ~/recovered_workspace. Inspect only the current repo files and report concise facts for documentation:
1. docker-compose.yml services, ports, required env vars, mounted volumes, and exact recommended run commands.
2. backend API routes and whether their paths/methods match the README draft: health, prompts enhance, generations list/create/detail/delete, pipelines create/detail, assets detail, files streaming.
3. generation request schemas: fields for T2I, T2V, I2V, pipeline, and whether auto_enhance exists or not.
4. frontend env/proxy behavior: VITE_API_BASE, VITE_API_PROXY_TARGET, allowed hosts.
5. available test/lint/build commands from backend/frontend config files.
6. any README claims that would be unsafe or unsupported, especially Veo resume/orphan sweep, health readiness, file route path, deletion behavior, and Range request support.

Return only findings and recommended README wording corrections. Do not modify files.
```

실행은 꼭 이렇게:

```bash
cd ~/recovered_workspace && codex
```

결과 가져오면 내가 “README에 넣을 문장 / 빼야 할 문장”으로 바로 정리해줄게.
````

## user

```text
한글로좀 제공해줘 나도 봐야하잖아 

```

## assistant

````text
좋아. Codex CLI에는 아래 한글 프롬프트로 보내면 돼.

```text
최종 README 작성을 위한 read-only fact check를 해줘.

절대 파일을 수정하지 말고, 서버를 실행하지 말고, 패키지를 설치하지 말고, 브라우저/Chromium도 사용하지 마. 현재 repo 파일만 읽어서 문서화에 필요한 사실만 간결하게 보고해줘.

작업 위치는 ~/recovered_workspace 야.

확인할 항목:
1. docker-compose.yml 기준 서비스 구성, 포트, 필수 env 변수, volume mount, README에 적을 정확한 실행 명령.
2. backend API route 목록과 README 초안의 경로/메서드가 맞는지 확인:
   - health
   - prompt enhance
   - generations 생성/목록/상세/삭제
   - pipelines 생성/상세
   - assets 상세
   - files streaming
3. generation request schema 확인:
   - T2I, T2V, I2V, pipeline 요청 필드
   - auto_enhance 필드가 실제로 존재하는지 여부
   - enhancement_id 필드가 어떻게 쓰이는지
4. frontend env/proxy 동작 확인:
   - VITE_API_BASE
   - VITE_API_PROXY_TARGET
   - VITE_ALLOWED_HOSTS
5. backend/frontend 설정 파일 기준 테스트, lint, build 명령어 확인.
6. README에 쓰면 위험하거나 근거가 약한 주장 확인:
   - Veo LRO resume
   - orphan job sweep
   - health endpoint가 Vertex readiness까지 확인하는지
   - file route path 표기
   - deletion behavior
   - Range request 지원 여부

출력은 다음 형식으로만 해줘:
- 확인된 사실
- README에서 고쳐야 할 문장/표현
- README에 그대로 써도 되는 추천 문구

파일 수정은 하지 마.
```

실행은 반드시:

```bash
cd ~/recovered_workspace && codex
```
````

## user

```text
- 확인된 사실                      
      - docker-compose.yml 서비스는 db, backend, frontend 3개입니다. 포트 
        는 backend 8000:8000, frontend 5173:5173; DB는 호스트 포트를 열지
        않습니다.                   
- 필수 compose env는 POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
        GOOGLE_APPLICATION_CREDENTIALS,                                   
        GOOGLE_APPLICATION_CREDENTIALS_HOST, GCP_LOCATION, ENHANCE_MODEL,
        DATA_DIR입니다. GCP_PROJECT_ID, JOB_RUNNER_CONCURRENCY, VITE_*는
        기본값이 있습니다.                                                
      - volume은 pgdata:/var/lib/postgresql/data, assets:/data/assets, 서
        비스 계정 host path -> /secrets/sa.json:ro, 그리고 backend/      
        frontend 소스 bind mount가 있습니다.                       
      - 정확한 전체 실행 명령은 repo root에서 docker compose up --build입 
        니다.                                                             
      - API route는 GET /api/health, POST /api/prompts/enhance, POST/GET /
        api/generations, GET/DELETE /api/generations/{job_id}, POST /api/
        pipelines, GET /api/pipelines/{parent_job_id}, GET /api/assets/
        {asset_id}, GET /files/{local_path:path}입니다.                   
      - generation schema에는 auto_enhance가 실제로 있지만 true면 501로 거
        절됩니다. enhancement_id는 기존 prompt enhancement를 job에 연결하 
        고 enhanced_prompt를 저장합니다.                                 
      - 직접 API 호출 시 enhancement_id만으로 Vertex 호출 prompt가 자동 교
        체되지는 않습니다. runner는 job.prompt를 사용합니다. 프론트엔드는
        enhancement 수락 시 prompt 자체를 개선본으로 바꿔 보냅니다.       
      - pipeline 요청 필드는 image_prompt, video_prompt, image_model,     
        video_model, image_aspect_ratio, video_aspect_ratio, duration_sec 
        입니다. pipeline에는 auto_enhance/enhancement_id가 없습니다.
      - VITE_API_BASE는 frontend fetch base입니다. 비어 있으면 relative /
        api, /files를 사용합니다.                                         
      - VITE_API_PROXY_TARGET은 Vite dev proxy의 /api, /files             
        target입니다. 코드 기본값은 http://localhost:8000, compose        
        기본값은 http://backend:8000입니다.                               
      - VITE_ALLOWED_HOSTS는 comma-separated로 파싱되어 Vite             
        server.allowedHosts에 들어갑니다.                                 
      - backend 테스트 명령은 cd backend, python3 -m pip install -e ".    
        [dev]", python3 -m pytest입니다.                                  
      - frontend 명령은 npm run lint = tsc --noEmit, npm run build = tsc  
        -b && vite build입니다.      
  - README에서 고쳐야 할 문장/표현                                        
      - GET /api/health | DB 및 Vertex readiness 확인은 과합니다. 실제 원
        격 Vertex 호출 검증이 아니라 DB 연결과 Vertex client 구성/      
 credentials readiness 확인입니다.                                
      - /files/{local_path}는 가능하면 /files/{local_path:path} 또는 /    
        files/{job_uuid}/{filename}로 쓰는 편이 정확합니다.              
      - ENHANCE_MODEL은 compose에서 필수지만 backend 설정/LLM 코드에서는
        현재 읽지 않고 gemini-2.5-flash가 hard-coded입니다. “env로 enhance
        model 변경 가능”처럼 쓰면 안 됩니다.                             
      - “terminal job 삭제”는 더 구체화가 필요합니다. terminal job만 삭제
        가능하고, active dependent job이 있으면 409입니다. terminal
        dependent job은 참조가 detach될 수 있습니다.                      
      - “Veo LRO resume”은 맞지만 polling 상태이고 vertex_operation_name이
        있는 job에 한정됩니다.                                            
      - “orphan job sweep”은 맞지만 runner startup 시 오래된 non-terminal
        job을 failed 처리하며, resumable polling job은 제외합니다.     
      - Range request는 지원됩니다. 단, single byte range만 지원하고      
        multiple range는 400, satisfiable하지 않으면 416입니다.           
  - README에 그대로 써도 되는 추천 문구                                   
      - “Docker Compose는 Postgres, FastAPI backend, Vite frontend를 실행
        하며 backend는 8000, frontend는 5173에 노출됩니다.”               
      - “파일은 DB에는 metadata로 저장되고 실제 bytes는 DATA_DIR 아래    
        {job_uuid}/{filename} 형태로 저장되며 /files/{job_uuid}/{filename}
        에서 스트리밍됩니다.”                                             
      - “Prompt enhancement는 /api/prompts/enhance에서 먼저 생성한 뒤, 사 
        용자가 개선 prompt를 수락하면 generation 요청의 prompt와    
        enhancement_id로 연결됩니다.”                                     
      - “auto_enhance=true generation create는 현재 지원하지 않으며 501을 
        반환합니다.”                                                      
      - “Veo job은 operation name을 저장하고, polling 상태의 job은 runner 
        재시작 후 operation name으로 polling을 재개할 수 있습니다.”       
      - “삭제 API는 terminal job만 삭제하며 저장된 asset 파일도 함께 제거
        합니다. active dependent job이 있으면 삭제하지 않습니다.”         
                                                                      

```

## assistant

````text
좋아. Codex CLI 결과 기준으로 보면, Docker/README 쪽은 이렇게 확정하면 돼.

핵심 수정 판단:

- `docker compose up --build`는 맞지만, README 추천 명령은 `docker compose up -d --build`로 써도 문제 없음. `-d`는 실행 방식 차이라서 문서용으로 더 좋음.
- E2B 명령은 반드시 별도 표기:
  `sudo -E docker compose up -d --build --force-recreate frontend backend db`
- `ENHANCE_MODEL`은 compose 필수 env지만 실제 코드에서는 hard-coded라서 “모델 변경 가능”이라고 쓰면 안 됨.
- `auto_enhance`는 schema에는 있지만 `true`면 501이므로 예시 JSON에서는 빼는 게 좋음.
- Prompt enhancement는 `enhancement_id`만으로 prompt가 바뀌지 않음. 프론트가 수락 시 `prompt` 자체를 개선본으로 보내는 구조라고 써야 함.

README 실행 섹션은 이 문구로 가면 안전해:

```md
## 실행 방법

이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행합니다. 백엔드는 `8000`, 프론트엔드는 `5173` 포트로 노출되며, PostgreSQL은 외부 포트를 열지 않습니다.

### 환경 변수

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 설정합니다. 서비스 계정 JSON 내용은 `.env`에 직접 넣지 않고, 호스트 파일 경로만 지정합니다.

```env
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
```

`GOOGLE_APPLICATION_CREDENTIALS_HOST`는 호스트 머신의 서비스 계정 JSON 절대 경로입니다. Docker Compose는 이 파일을 백엔드 컨테이너의 `/secrets/sa.json`에 read-only로 마운트합니다.

### Docker Compose 실행

일반 로컬 환경:

```bash
docker compose up -d --build
```

E2B 과제 환경:

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```

### 접속 URL

로컬 환경:

- Frontend: http://localhost:5173
- Backend API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

E2B 환경:

- Frontend: `https://5173-${E2B_SANDBOX_ID}.e2b.app`
- Backend: `https://8000-${E2B_SANDBOX_ID}.e2b.app`

### 종료

```bash
docker compose down
```

DB 데이터와 생성된 에셋 volume까지 삭제하려면 다음 명령을 사용합니다.

```bash
docker compose down -v
```

`down -v`는 PostgreSQL 데이터와 생성된 에셋 파일을 삭제하므로 의도한 경우에만 사용합니다.
```

다음 README 수정 포인트는 API 예시야. 특히 `auto_enhance`를 예시 payload에서 제거하고, 별도 주석으로 “`auto_enhance=true`는 현재 501”이라고 쓰는 게 안전해.
````

## user

```text
DB는 docekr copose up -d --build 로 실행이 안되는거임 ?

```

## assistant

````text
아니, **DB도 `docker compose up -d --build`로 같이 실행돼.**

compose 파일에 서비스가 이렇게 3개라서:

- `db`
- `backend`
- `frontend`

repo root에서 아래 명령을 치면 세 서비스가 모두 올라와.

```bash
docker compose up -d --build
```

다만 DB는 `ports:` 설정이 없어서 **호스트에서 직접 `localhost:5432`로 접속되지는 않음**. 백엔드 컨테이너가 compose 내부 네트워크에서 `db:5432`로 접근하는 구조야.

즉 정리하면:

- DB 실행됨: 맞음
- DB 데이터 저장됨: `pgdata` named volume에 저장됨
- 외부 포트 노출: 안 함
- 백엔드 연결 주소: `db:5432`
- 사용자가 브라우저로 접속할 URL: frontend `5173`, backend `8000`만 있음

README에는 이렇게 쓰면 깔끔해:

```md
Docker Compose는 PostgreSQL, FastAPI 백엔드, Vite 프론트엔드를 함께 실행합니다. 백엔드는 `8000`, 프론트엔드는 `5173` 포트로 노출되며, PostgreSQL은 compose 내부 네트워크에서만 사용하므로 호스트 포트를 열지 않습니다.
```
````

## user

```text

다음 README 수정 포인트는 API 예시야. 특히 `auto_enhance`를 예시 payload에서 제거하고, 별도 주석으로 “`auto_enhance=true`는 현재 501”이라고 쓰는 게 안전해.

끄냥 auto enhance에 대한 내용 삭제하는건  ?

```

## assistant

````text
그게 더 좋아. **README에서는 `auto_enhance` 내용을 아예 빼는 걸 추천**해.

이유는 간단해:

- 사용자/평가자가 실행 예시를 그대로 따라 할 가능성이 큼
- `auto_enhance=true`는 실제로 501이라 “지원 기능”처럼 보이면 손해
- 과제에서 중요한 건 “프롬프트 개선 UX”이지 “generation 요청에서 자동 enhance”가 아님
- 내부 schema에 남아 있는 미지원 옵션을 README에 드러낼 필요 없음

README에는 이렇게만 쓰면 돼:

```md
Prompt enhancement는 `/api/prompts/enhance`에서 별도로 수행됩니다. 사용자가 개선된 prompt를 확인, 편집, 수락하면 프론트엔드는 해당 개선본을 generation 요청의 `prompt`로 보내고, 선택적으로 `enhancement_id`를 함께 전달해 job과 연결합니다.
```

API 예시에서는 전부 `auto_enhance` 제거:

```json
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1
}
```

즉, 제출 README에서는 **지원하는 흐름만 보여주자**. 미지원 옵션 설명은 오히려 집중도를 흐려.
````

## user

```text
ㅇㅋ auto enhance 뻇어 다음

```

## assistant

````text
좋아. 다음은 **API 엔드포인트 표**를 실제 route 기준으로 정리하면 돼. 지금 초안은 거의 맞는데, health/file/delete 설명을 더 정확하게 다듬는 게 좋아.

추천 표:

```md
## API 요약

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/health` | DB 연결 및 Vertex 클라이언트 설정 상태를 확인합니다. |
| POST | `/api/prompts/enhance` | Gemini 기반 prompt enhancement 결과를 생성합니다. |
| POST | `/api/generations` | T2I, T2V, I2V 단일 생성 job을 생성합니다. |
| GET | `/api/generations` | 생성 job history를 조회하고 mode, state, model 등으로 필터링합니다. |
| GET | `/api/generations/{job_id}` | 특정 job의 상태, 입력값, 생성 asset 정보를 조회합니다. |
| DELETE | `/api/generations/{job_id}` | terminal 상태의 job과 연결 asset file을 삭제합니다. active dependent job이 있으면 삭제하지 않습니다. |
| POST | `/api/pipelines` | T2I parent job과 I2V child job을 연결한 pipeline을 생성합니다. |
| GET | `/api/pipelines/{parent_job_id}` | pipeline의 parent/child job 관계와 진행 상태를 조회합니다. |
| GET | `/api/assets/{asset_id}` | 생성된 asset metadata를 조회합니다. |
| GET | `/files/{job_uuid}/{filename}` | DATA_DIR 아래에 저장된 asset 파일을 안전하게 스트리밍합니다. video preview를 위한 single Range request를 지원합니다. |
```

주의할 표현:

- `/api/health`를 “Vertex readiness 확인”이라고 강하게 쓰지 말기  
  → “Vertex 클라이언트 설정 상태” 정도가 안전.
- `/files/{local_path}`보다 `/files/{job_uuid}/{filename}`가 README 독자에게 이해 쉬움.
- 삭제는 “완료/실패한 job 삭제”보다 “terminal 상태 job 삭제”가 정확함. `completed/failed/cancelled`를 말하는 느낌.

다음은 **요청 예시 JSON**인데, 거기서는 `enhancement_id`를 optional로 어떻게 보여줄지 정하면 돼. 내 추천은 기본 생성 예시에는 빼고, prompt enhancement 설명 문단에서만 언급하는 거야.
````

## user

```text
cli 에게 api 만  endpoint 기준 전체 내용 보여달라할까 ? 

```

## assistant

````text
응, 좋아. **API 섹션만 read-only로 정확히 뽑게 하는 것** 추천해. README에서 제일 실수 나기 쉬운 부분이라 한 번 더 확인할 가치 있어.

Codex CLI 프롬프트:

```text
README API 섹션 작성을 위해 read-only로 backend API를 정리해줘.

절대 파일 수정하지 말고, 서버 실행하지 말고, 테스트 실행하지 말고, 브라우저도 사용하지 마. 현재 repo 파일만 읽어.

작업 위치는 ~/recovered_workspace 야.

확인할 것:
1. 실제 FastAPI route 전체 목록: method, path, handler 파일.
2. 각 endpoint의 request body schema와 response schema 이름.
3. README에 쓸 수 있는 한 줄 설명.
4. generation 관련 payload 예시:
   - POST /api/prompts/enhance
   - POST /api/generations t2i
   - POST /api/generations t2v
   - POST /api/generations i2v
   - POST /api/pipelines
5. README에 쓰면 안 되는 미지원/오해 소지 필드나 표현.

출력은 README에 바로 옮기기 쉬운 Markdown 표와 JSON 예시 중심으로 해줘.
```

이 결과 가져오면 내가 “길다/짧다/위험한 표현”만 빠르게 다듬어줄게.
````

## user

```text
터미널이라 한글도 깨지고 출력도 다깨지는데 , docs 에 저장하라고 해야할듯 


```

## assistant

````text
맞아. 그러면 **docs 하위에 read-only 리포트 파일만 생성**시키는 게 좋다. 새 문서화 산출물은 `.codex/`가 아니라 `docs/` 하위 원칙에도 맞아.

Codex CLI 프롬프트:

```text
README API 섹션 작성을 위한 조사 결과를 docs/readme-api-factcheck.md 파일로 작성해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-api-factcheck.md 하나만 허용.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. 실제 FastAPI route 전체 목록: method, path, handler file.
2. 각 endpoint의 request body schema와 response schema 이름.
3. README에 쓸 수 있는 한 줄 설명.
4. generation 관련 payload 예시:
   - POST /api/prompts/enhance
   - POST /api/generations t2i
   - POST /api/generations t2v
   - POST /api/generations i2v
   - POST /api/pipelines
5. README에 쓰면 안 되는 미지원/오해 소지 필드나 표현.

출력 파일은 Markdown으로 작성하고, README에 바로 옮기기 쉬운 표와 JSON 예시 중심으로 정리해줘.
```

끝나면 `docs/readme-api-factcheck.md` 내용을 가져와. 내가 README에 넣을 최종 API 섹션으로 줄여줄게.
````

## user

```text
출력 파일도 markdown으로 안하는게 좋을거 같아 

```

## assistant

````text
응, 그럼 **plain text `.txt`**가 제일 안전해. 터미널 깨짐도 줄고, Markdown 표 깨지는 문제도 피할 수 있어.

Codex CLI 프롬프트:

```text
README API 섹션 작성을 위한 조사 결과를 docs/readme-api-factcheck.txt 파일로 작성해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-api-factcheck.txt 하나만 허용.
- Markdown 표를 쓰지 말고 plain text로 작성해.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. 실제 FastAPI route 전체 목록: method, path, handler file.
2. 각 endpoint의 request body schema와 response schema 이름.
3. README에 쓸 수 있는 한 줄 설명.
4. generation 관련 payload 예시:
   - POST /api/prompts/enhance
   - POST /api/generations t2i
   - POST /api/generations t2v
   - POST /api/generations i2v
   - POST /api/pipelines
5. README에 쓰면 안 되는 미지원/오해 소지 필드나 표현.

파일은 다음 구조로 작성해:
- ROUTES
- SCHEMAS
- README_DESCRIPTIONS
- JSON_EXAMPLES
- DO_NOT_CLAIM

README에 바로 옮기기 쉽게 간결하게 정리해줘.
```

이건 문서 조사 산출물이라 `docs/` 하위에 두는 게 딱 맞아. 
완료 후에는 파일 내용을 네가 열어서 가져오면 돼.
````

## user

````text
# README API Fact Check                                                   
                                                                          
This document is a read-only fact check of the backend API surface for the
README API section. It is based on the current repository files only.     
                                                                          
Source files checked:                                                     
                                                                          
- `backend/app/main.py`                                                   
- `backend/app/api/health.py`                                             - `backend/app/api/prompts.py`                                            
- `backend/app/api/generations.py`                                        
- `backend/app/api/pipelines.py`                                          
- `backend/app/api/assets.py`                                             
- `backend/app/api/files.py`                                              
- `backend/app/schemas.py`                                                
- `backend/app/models.py`                                                 
- `backend/app/prompt_enhancement.py` 
                                                                          
FastAPI's automatic documentation routes such as `/docs`, `/redoc`, and   
`/openapi.json` are not listed below.                                     
                                                                          
## Route 목록                                                             
                                                                          
| Method | Path | Handler | Request body schema | Response schema | README
 설명 |                                                                   
|---|---|---|---|---|---|                                                 
| `GET` | `/api/health` | `backend/app/api/health.py::health` | 없음 | `He
althResponse` | DB 연결과 Vertex client 구성 readiness를 확인합니다. |    
| `POST` | `/api/prompts/enhance` | `backend/app/api/prompts.py::enhance_p
rompt` | `PromptEnhanceRequest` | `PromptEnhancementResponse` | Gemini 기 
반 prompt enhancement를 생성하고 저장합니다. |                            
| `POST` | `/api/generations` | `backend/app/api/generations.py::create_ge
neration` | `GenerationCreate` = `T2IRequest \| T2VRequest \| I2VRequest` 
| `GenerationResponse` | T2I, T2V, I2V generation job을 생성합니다. |     
| `GET` | `/api/generations` | `backend/app/api/generations.py::list_gener
ations` | 없음 | `list[GenerationResponse]` | job history를 필터와 paginat
ion으로 조회합니다. |                
| `GET` | `/api/generations/{job_id}` | `backend/app/api/generations.py::g
et_generation` | 없음 | `GenerationResponse` | 단일 generation job의 상태,
 metadata, assets를 조회합니다. |                                         
| `DELETE` | `/api/generations/{job_id}` | `backend/app/api/generations.py
::delete_generation` | 없음 | 없음, `204 No Content` | terminal job과 해당
 asset 파일을 삭제합니다. |                                               
| `POST` | `/api/pipelines` | `backend/app/api/pipelines.py::create_pipeli
ne` | `PipelineCreateRequest` | `PipelineResponse` | T2I parent job과 bloc
ked I2V child job을 함께 생성합니다. |                                    | `GET` | `/api/pipelines/{parent_job_id}` | `backend/app/api/pipelines.py
::get_pipeline` | 없음 | `PipelineResponse` | pipeline parent job과 연결된
 첫 I2V child job을 조회합니다. |                                         
| `GET` | `/api/assets/{asset_id}` | `backend/app/api/assets.py::get_asset
` | 없음 | `AssetResponse` | asset metadata와 `/files/...` URL을 조회합니 
다. |                                                                     
| `GET` | `/files/{local_path:path}` | `backend/app/api/files.py::get_file
` | 없음 | `StreamingResponse` | `DATA_DIR` 아래 asset 파일을 안전하게 스
트리밍합니다. |                                                           
                                                                          
## Query Parameters                                                       
                                                                          
| Endpoint | Query parameters |                                           
|---|---|                                                                 
| `GET /api/generations` | `mode?: t2i\|t2v\|i2v`, `asset_kind?: image\|vi
deo`, `model?: string`, `state?: JobState`, `limit: 1..100 = 20`, `offset:
 >= 0 = 0` |                                                              
| `GET /files/{local_path:path}` | query 없음. `Range` header를 통한 singl
e byte range 요청을 지원합니다. |                                         
                                                                          
## Schema 요약                                                            
                                                                          
### Request Schemas                                                       
                                                                          
| Schema | Fields |                                                       
|---|---|                                                                 
| `PromptEnhanceRequest` | `prompt`, `target_mode`, `target_model`, `creat
ivity_preset = "balanced"` |         
| `T2IRequest` | `mode: "t2i"`, `prompt`, `model`, `aspect_ratio = "1:1"`,
 `number_of_images = 1`, `auto_enhance = false`, `enhancement_id = null` |
| `T2VRequest` | `mode: "t2v"`, `prompt`, `model`, `aspect_ratio = "16:9"`
, `duration_sec = 4`, `auto_enhance = false`, `enhancement_id = null` |   
| `I2VRequest` | `mode: "i2v"`, `prompt`, `model`, `source_asset_id`, `asp
ect_ratio = "16:9"`, `duration_sec = 4`, `auto_enhance = false`, `enhancem
ent_id = null` |                                                          
| `PipelineCreateRequest` | `image_prompt`, `video_prompt`, `image_model`,
 `video_model`, `image_aspect_ratio = "1:1"`, `video_aspect_ratio = "16:9"`, `duration_sec = 4` |                                                   
                                                                          
### Response Schemas                                                      
                                                                          
| Schema | Important fields |                                             
|---|---|                                                                 
| `HealthResponse` | `ok`, `ready`, `service`, `db`, `vertex` |           
| `PromptEnhancementResponse` | `id`, `original`, `enhanced`, `components`
, `target_mode`, `target_model`, `llm_model`, `creativity_preset`, `temper
ature`, `latency_ms`, `tokens_in`, `tokens_out`, `created_at` |           
| `GenerationResponse` / `JobResponse` | `id`, `mode`, `model`, `state`, `
prompt`, `enhanced_prompt`, `enhancement_id`, `parent_job_id`, `source_ass
et_id`, `blocked`, `vertex_operation_name`, `attempts`, `parameters`, `sta
te_history`, `error`, `vertex_charged`, `created_at`, `updated_at`, `asset
s` |                                                                      
| `AssetResponse` | `id`, `job_id`, `kind`, `local_path`, `mime`, `size_by
tes`, `width`, `height`, `duration_sec`, `created_at`, `url` |            
| `PipelineResponse` | `id`, `parent`, `child` |                          
                                                                          
## Enum 값                                                                
                                                                          
| Enum | Values |                                                         
|---|---|                                                                 
| `GenerationMode` | `t2i`, `t2v`, `i2v` |                                
| `JobState` | `pending`, `enhancing`, `queued`, `generating`, `polling`, 
`downloading`, `completed`, `failed`, `cancelled` |                       
| `AssetKind` | `image`, `video` |                                        
| `CreativityPreset` | `faithful`, `balanced`, `imaginative` |

                                                                        
## Request JSON 예시                                                      
                                                                          
### `POST /api/prompts/enhance`                                           
                                                                          
```json                                                                   
{                                                                         
  "prompt": "고양이가 집에서 뛰어노는 사진",                              
  "target_mode": "t2i",                                                     "target_model": "imagen-4.0-fast-generate-001",                         
  "creativity_preset": "balanced"                                         
}                                                                         
```                                                                       
                                                                          
### `POST /api/generations` - T2I                                         
                                                                          
```json                                                                   
{                                                                         
  "mode": "t2i",                                                          
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",         
  "model": "imagen-4.0-fast-generate-001",                                
  "aspect_ratio": "1:1",                                                  
  "number_of_images": 1,                                                  
  "auto_enhance": false,                                                  
  "enhancement_id": null                                                  
}                                                                         
```                                                                       
                                                                          
### `POST /api/generations` - T2V                                         
                                                                          
```json                                                                   
{                                                                         
  "mode": "t2v",                                                          
  "prompt": "A slow dolly forward through a rainy neon alley",            
  "model": "veo-3.0-fast-generate-001",                                   
  "aspect_ratio": "16:9",                                                 
  "duration_sec": 4,                                                      
  "auto_enhance": false,            
 "enhancement_id": null                                                  
}                                                                         
```                                                                       
                                                                          
### `POST /api/generations` - I2V                                         
                                                                          
```json                                                                   
{                                                                           "mode": "i2v",                                                          
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in p
uddles",                                                                  
  "model": "veo-3.0-fast-generate-001",                                   
  "source_asset_id": "00000000-0000-4000-8000-000000000000",              
  "aspect_ratio": "16:9",                                                 
  "duration_sec": 4,                                                      
  "auto_enhance": false,                                                  
  "enhancement_id": null                                                  
}                                                                         
```                                                                       
                                                                          
### `POST /api/pipelines`                                                 
                                                                          
```json                                                                   
{                                                                         
  "image_prompt": "Neon-soaked Seoul alley at night with a cyclist",      
  "video_prompt": "Slow dolly forward as the cyclist passes and steam rise
s",                                                                       
  "image_model": "imagen-4.0-fast-generate-001",                          
  "video_model": "veo-3.0-fast-generate-001",                             
  "image_aspect_ratio": "1:1",                                            
  "video_aspect_ratio": "16:9",                                           
  "duration_sec": 4                                                       
}                                                                         
```                                                                       
                                                                          
## README에 쓰기 좋은 문구                                                
                                                        
                       - `POST /api/prompts/enhance`는 prompt enhancement record를 만들고, 응답의
 `id`를 generation 요청의 `enhancement_id`로 연결할 수 있습니다.          
- `POST /api/generations`는 `mode` discriminator에 따라 T2I, T2V, I2V request를 받습니다.                                                           
- I2V 요청의 `source_asset_id`는 기존 image asset이어야 합니다.           
- Pipeline 생성은 T2I parent job과 blocked I2V child job을 함께 만들며, ch
ild는 parent image asset이 준비된 뒤 연결됩니다.                          
- Asset 응답의 `url`은 `/files/{local_path}` 형식입니다.                  
- 파일 스트리밍 route는 single byte range request를 지원합니다.           
                                                                          
## README에 쓰면 안 되는 표현                                             
                                                                          
- `auto_enhance=true`가 generation 생성에서 동작한다고 쓰면 안 됩니다. 현 
재 `true`이면 `501 Not Implemented`로 거절됩니다.                         
- `enhancement_id`만 넣으면 Vertex 호출 prompt가 자동으로 개선본으로 바뀐 
다고 쓰면 안 됩니다. `enhancement_id`는 job에 연결되고 `enhanced_prompt`를
 저장하지만, generation runner는 request의 `prompt`를 사용합니다.         
- Pipeline request에 `auto_enhance`, `enhancement_id`, `source_asset_id`, 
`number_of_images` 필드가 있다고 쓰면 안 됩니다.                          
- Health endpoint가 실제 Vertex 원격 API 호출까지 검증한다고 쓰면 오해 소 
지가 있습니다. 현재는 DB 연결과 Vertex client 구성 readiness를 반환합니다.
- File route를 `/api/files/...`로 쓰면 안 됩니다. 실제 route는 `/files/{lo
cal_path:path}`입니다.                                                    
- File route가 임의 파일 경로를 받을 수 있다고 쓰면 안 됩니다. 저장소의 sa
fe local path, 즉 `{job_uuid}/{filename}` 형태를 검증합니다.              
- Delete API가 모든 job을 삭제한다고 쓰면 안 됩니다. terminal job만 삭제  
가능하고 active dependent job이 있으면 거절됩니다.                        
- Range request를 완전한 multi-range 지원으로 쓰면 안 됩니다. single byte 
range만 지원하며 multiple ranges는 거절됩니다.                            
- Cancel API나 job update API가 있다고 쓰면 안 됩니다. 현재 route 목록에는
 없습니다.                                                                                                                 

````

## assistant

````text
좋아. 이 결과 기준이면 README API 섹션은 **너무 상세한 schema 표까지 넣지 말고**, 아래 정도로 줄이는 게 좋아. `auto_enhance`는 완전히 빼자.

```md
## API 요약

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/health` | DB 연결과 Vertex client 설정 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
| POST | `/api/prompts/enhance` | Gemini 기반 prompt enhancement record를 생성합니다. |
| POST | `/api/generations` | `mode` 값에 따라 T2I, T2V, I2V generation job을 생성합니다. |
| GET | `/api/generations` | job history를 `mode`, `state`, `model`, `asset_kind`, pagination 조건으로 조회합니다. |
| GET | `/api/generations/{job_id}` | 단일 job의 상태, 입력값, state history, 생성 asset 정보를 조회합니다. |
| DELETE | `/api/generations/{job_id}` | terminal 상태 job과 해당 asset 파일을 삭제합니다. active dependent job이 있으면 거절됩니다. |
| POST | `/api/pipelines` | T2I parent job과 blocked I2V child job을 함께 생성합니다. |
| GET | `/api/pipelines/{parent_job_id}` | pipeline parent job과 연결된 I2V child job의 진행 상태를 조회합니다. |
| GET | `/api/assets/{asset_id}` | asset metadata와 `/files/...` URL을 조회합니다. |
| GET | `/files/{job_uuid}/{filename}` | `DATA_DIR` 아래 asset 파일을 안전하게 스트리밍합니다. video preview용 single byte range request를 지원합니다. |
```

프롬프트 개선 설명은 API 표 밑에 이렇게 넣으면 정확해:

```md
Prompt enhancement는 generation 요청에 자동으로 적용되지 않습니다. 사용자가 `/api/prompts/enhance` 결과를 확인, 편집, 수락하면 프론트엔드는 개선된 prompt를 generation 요청의 `prompt`로 보내고, `enhancement_id`를 함께 전달해 job과 enhancement record를 연결합니다.
```

예시는 이렇게 최소만:

```json
{
  "prompt": "고양이가 집에서 뛰어노는 사진",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced"
}
```

```json
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1
}
```

```json
{
  "mode": "i2v",
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in puddles",
  "model": "veo-3.0-fast-generate-001",
  "source_asset_id": "00000000-0000-4000-8000-000000000000",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

pipeline 예시는 넣어도 되고 안 넣어도 돼. README 길이를 줄이고 싶으면 API 표만 두고, 자세한 payload는 `/docs`에서 확인 가능하다고 쓰는 게 더 깔끔해.
````

## user

```text
ㅇㅋ 내가 노션에서 readme를 수정중이야 
api 와 json , docker 까지 지금 수정을했어 다음 뭐 수정하지 ? 

```

## assistant

````text
다음은 **아키텍처/핵심 설계 섹션**을 다듬는 게 좋아. 지금 초안에서 기술적으로 멋있게 보이는 부분이지만, 과장 표현만 정리하면 점수 잘 받는 영역이야.

수정 포인트:

1. **“단일 인스턴스 기반” 명시 유지**
   - Celery/Redis 없이 Postgres + in-process asyncio runner를 쓴 이유를 설명.
   - 과제 범위에 맞춘 의도적 선택이라는 톤.

2. **“순차 처리” 제거**
   - 실제는 bounded concurrency.
   - 표현:
   ```md
   FastAPI 프로세스 내부의 asyncio runner가 pending job을 가져와 제한된 동시성 안에서 처리합니다.
   ```

3. **`FOR UPDATE SKIP LOCKED` 유지**
   - 좋은 엔지니어링 포인트라 살리기.
   - 단, “분산 큐 대체”보다는 “동일 DB 기반 job claim 안정화”라고 쓰기.

4. **Veo resume/orphan sweep은 짧고 정확하게**
   ```md
   Veo job은 Vertex operation name을 저장하며, polling 상태의 job은 runner 재시작 후 해당 operation name으로 polling을 재개할 수 있습니다. runner startup 시 오래된 non-terminal job은 failed 처리하되, 재개 가능한 polling job은 제외합니다.
   ```

5. **state machine 강조**
   - 이건 README 핵심 강점.
   ```md
   모든 job 상태 변경은 `app/state_machine.py`의 `transition(...)`을 통해서만 수행되며, 허용되지 않은 전이는 예외로 처리하고 테스트로 검증했습니다.
   ```

6. **storage/path safety 강조**
   - 삭제 기능과 연결돼서 좋음.
   ```md
   생성 파일은 `DATA_DIR/{job_uuid}/{filename}` 형태로 저장하고, 파일 쓰기/삭제/스트리밍은 path validation을 거칩니다.
   ```

내가 보기엔 다음 순서는:

**아키텍처/핵심 설계 → 주요 기능 → 테스트/검증 → 알려진 제약/운영 노트**

Known Limitations는 마지막에 너무 방어적으로 쓰지 말고, “운영 노트 및 provider 제약”으로 바꾸는 게 좋아.
````

## user

```text
프로젝트 아키텍쳐 및 핵심 설계도 실제 코드베이스로 fact check 하자 

```

## assistant

````text
좋아. 이건 꼭 fact check 하는 게 맞아. 특히 runner, rate limit, retry, storage, state machine 쪽은 README에서 강점으로 보일 부분이라 정확해야 해.

Codex CLI 프롬프트:

```text
README의 "프로젝트 아키텍처 및 핵심 설계" 섹션 작성을 위해 read-only fact check를 해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-architecture-factcheck.txt 하나만 허용.
- Markdown 표를 쓰지 말고 plain text로 작성해.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. FastAPI app startup 구조와 job runner가 언제/어떻게 시작되는지.
2. job claim 방식:
   - pending/queued/polling/blocked 처리가 어떻게 되는지
   - FOR UPDATE SKIP LOCKED 사용 여부
   - bounded concurrency/semaphore 사용 여부
3. rate limit 구조:
   - 모델별 sliding-window limiter가 있는지
   - Imagen/Veo limit 값이 어디에서 정의되는지
4. retry/backoff 구조:
   - 어떤 오류에 retry하는지
   - max attempts/backoff 정책
5. state machine:
   - 모든 job 상태 전이가 transition(...)을 경유하는지
   - 허용 상태 목록과 주요 흐름
6. Veo long-running operation 처리:
   - operation name 저장 여부
   - polling 재개 가능 여부
   - inline video bytes 저장 여부
   - GCS 사용 여부
7. storage/path safety:
   - DATA_DIR 저장 경로
   - 파일 쓰기/삭제/스트리밍 path validation
   - Range request 지원 범위
8. pipeline linking:
   - T2I parent와 I2V child 연결 방식
   - child blocked 상태 해제 방식
9. orphan/stale job 처리:
   - runner startup 시 어떤 job을 failed 처리하는지
   - polling resume 대상은 제외되는지
10. README에 쓰면 위험하거나 과장인 표현.

파일 구조는 다음처럼 작성해:
- CONFIRMED_ARCHITECTURE_FACTS
- SAFE_README_WORDING
- UNSAFE_OR_OVERSTATED_CLAIMS
- FILE_REFERENCES

README에 바로 옮기기 쉽게 간결하게 정리해줘.
```

결과 파일 가져오면, 내가 아키텍처 섹션을 “제출용으로 세련되지만 과장 없는 문장”으로 다듬어줄게.
````

## user

```text
너무 한번에 많은내용을 체크하게 시키고있음 나눠서 

```

## assistant

````text
맞아, 잘 짚었어. 한 번에 너무 많이 물으면 Codex CLI가 대충 훑거나 긴 출력으로 흐를 수 있어. **아키텍처는 3번으로 쪼개자.**

1차는 runner/job lifecycle만:

```text
README 아키텍처 섹션을 위한 read-only fact check 1차: job runner와 job lifecycle만 확인해줘.

규칙:
- 파일 수정 금지.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새 파일은 docs/readme-runner-factcheck.txt 하나만 허용.
- Markdown 표 없이 plain text로 작성.
- credentials, .env 값, service-account JSON 내용 출력 금지.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. FastAPI app startup에서 job runner가 언제/어떻게 시작되는지.
2. pending/queued/polling/blocked job을 runner가 어떻게 처리하는지.
3. job claim에 FOR UPDATE SKIP LOCKED를 사용하는지.
4. 동시성 제한이 semaphore 등으로 구현되어 있는지.
5. runner 재시작 시 polling job resume 또는 stale job 처리 로직이 있는지.
6. README에 안전하게 쓸 수 있는 문장과 쓰면 안 되는 과장 표현.

출력 파일 구조:
- CONFIRMED_FACTS
- SAFE_README_WORDING
- DO_NOT_CLAIM
- FILE_REFERENCES
```

그 다음 2차:

- rate limit / retry / Vertex 호출

3차:

- state machine / storage / pipeline

이렇게 가면 정확도가 훨씬 좋아. 지금은 1차만 보내면 돼.
````

## user

```text
이것도 api팩트체크와 같이 문서화하자 , 


```

## assistant

````text
좋아. 그러면 `docs/readme-runner-factcheck.txt`처럼 **조사 산출물로 남기는 방식**이 맞아. 나중에 README 작성 근거도 되고, 터미널 깨짐도 피할 수 있어.

이번 1차 프롬프트는 이렇게:

```text
README 아키텍처 섹션을 위한 read-only fact check 1차 결과를 docs/readme-runner-factcheck.txt 파일로 작성해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-runner-factcheck.txt 하나만 허용.
- Markdown 표를 쓰지 말고 plain text로 작성해.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. FastAPI app startup에서 job runner가 언제/어떻게 시작되는지.
2. pending/queued/polling/blocked job을 runner가 어떻게 처리하는지.
3. job claim에 FOR UPDATE SKIP LOCKED를 사용하는지.
4. 동시성 제한이 semaphore 등으로 구현되어 있는지.
5. runner 재시작 시 polling job resume 또는 stale job 처리 로직이 있는지.
6. README에 안전하게 쓸 수 있는 문장과 쓰면 안 되는 과장 표현.

파일 구조:
- CONFIRMED_FACTS
- SAFE_README_WORDING
- DO_NOT_CLAIM
- FILE_REFERENCES
```

이거 실행 후 결과 가져오면, 다음 2차 범위는 **rate limit / retry / Vertex 호출 구조**로 좁혀가면 돼.
````

## user

```text
파일을 작성했습니다. 마지막으로 요청한 파일만 새로 생겼는지와 내용에 민
  감값이 섞이지 않았는지 간단히 확인하겠습니다.

• Ran git status --short
  └ ?? docs/readme-api-factcheck.md
    ?? docs/readme-runner-factcheck.txt

• Explored
  └ Read readme-runner-factcheck.txt

──────────────────────────────────────────────────────────────────────────

• 작성 완료했습니다: readme-runner-factcheck.txt

  규칙대로 구현 파일은 수정하지 않았고, 서버 실행/테스트 실행/패키지 설치/
  브라우저 사용도 하지 않았습니다. 새로 추가한 파일은 요청하신 fact check
  파일 하나입니다.

  참고로 작업트리에는 기존 untracked 파일 docs/readme-api-factcheck.md가
  이미 있었고, 건드리지 않았습니다.

우선 다음 2차프롬프트 제공해서 나중에 한번에 정리하자 

```

## assistant

````text
좋아. 2차는 **rate limit / retry / Vertex 호출 구조**만 보게 하자.

Codex CLI 프롬프트:

```text
README 아키텍처 섹션을 위한 read-only fact check 2차 결과를 docs/readme-vertex-retry-factcheck.txt 파일로 작성해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-vertex-retry-factcheck.txt 하나만 허용.
- Markdown 표를 쓰지 말고 plain text로 작성해.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. Vertex AI 호출이 google-genai 단일 SDK로 구현되어 있는지.
2. Imagen, Veo, Gemini enhancer 호출 파일과 역할.
3. Veo 호출이 GCS 없이 inline video bytes를 저장하는지.
4. 모델별 rate limit 구조:
   - sliding-window limiter 사용 여부
   - Imagen/Veo limit 값
   - 모델별 독립 제한인지
5. retry/backoff 구조:
   - retry 대상 오류
   - retry하지 않는 오류
   - max attempts/backoff 정책
6. Veo operation error, safety block, empty/filtered output을 어떻게 분류하는지.
7. README에 안전하게 쓸 수 있는 문장과 쓰면 안 되는 과장 표현.

파일 구조:
- CONFIRMED_FACTS
- SAFE_README_WORDING
- DO_NOT_CLAIM
- FILE_REFERENCES
```

이 다음 3차는 **state machine / storage / pipeline**으로 가면 딱 좋아.
````

## user

```text
3차도 줘 

```

## assistant

````text
좋아. 3차는 **state machine / storage / pipeline / deletion**만 좁혀서 확인시키면 돼.

```text
README 아키텍처 섹션을 위한 read-only fact check 3차 결과를 docs/readme-state-storage-pipeline-factcheck.txt 파일로 작성해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-state-storage-pipeline-factcheck.txt 하나만 허용.
- Markdown 표를 쓰지 말고 plain text로 작성해.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. state machine:
   - JobState 목록
   - 허용 transition 흐름
   - transition(...) 함수 사용 위치
   - README에 안전하게 쓸 수 있는 상태 관리 설명
2. storage/path safety:
   - DATA_DIR 저장 구조
   - asset write/delete가 어떤 함수들을 경유하는지
   - path traversal 방어 여부
   - /files route의 safe path validation과 Range request 지원 범위
3. pipeline linking:
   - T2I parent와 I2V child 생성/연결 방식
   - child blocked 상태 해제 조건
   - parent asset이 child source_asset_id로 연결되는 방식
4. deletion behavior:
   - 어떤 job을 삭제할 수 있는지
   - active job 삭제 차단 여부
   - dependent job이 있을 때 처리
   - asset file 삭제 범위
5. README에 쓰면 위험하거나 과장인 표현.

파일 구조:
- CONFIRMED_FACTS
- SAFE_README_WORDING
- DO_NOT_CLAIM
- FILE_REFERENCES
```

이 3개 결과 모이면 README 아키텍처 섹션은 꽤 탄탄하게 쓸 수 있어. 
그다음엔 **주요 기능 섹션**은 굳이 fact check 많이 하지 말고, 이미 live QA 기록 기반으로 정리하면 돼.
````

## user

```text
• 문서 작성이 끝났습니다. 지정한 파일 하나만 추가됐는지와 내용 구조를 확인
  하겠습니다.

• Ran git status --short
  └ ?? docs/readme-api-factcheck.md
    ?? docs/readme-runner-factcheck.txt
    ?? docs/readme-state-storage-pipeline-factcheck.txt
    ?? docs/readme-vertex-retry-factcheck.txt

• Explored
  └ Read readme-state-storage-pipeline-factcheck.txt

──────────────────────────────────────────────────────────────────────────

• 작성 완료했습니다: readme-state-storage-pipeline-factcheck.txt

  구현 파일은 수정하지 않았고, 서버/테스트/설치/브라우저도 실행하지 않았습
  니다. 이번 작업에서 새로 만든 파일은 요청하신 docs/readme-state-storage-
  pipeline-factcheck.txt 하나입니다.
깃 상태 관리하고 txt 파일들 내가 보여줄게  

```

## assistant

````text
좋아. 지금 상태는 정상적인 **문서화 조사 산출물 untracked** 상태야.

현재 untracked:

- `docs/readme-api-factcheck.md`
- `docs/readme-runner-factcheck.txt`
- `docs/readme-state-storage-pipeline-factcheck.txt`
- `docs/readme-vertex-retry-factcheck.txt`

다만 네 원칙상 “새 문서화 산출물은 `docs/` 하위”라서 위치는 괜찮아. 그런데 첫 파일이 원래 `.txt`로 하려던 것과 달리 `.md`야. 큰 문제는 아니지만, 최종 제출 전에는 정리하는 게 좋아.

추천:

1. 지금은 그대로 둬도 됨  
   README 작성 근거로 쓰는 중이니까 삭제/이동하지 말기.

2. README/AI_COLLABORATION까지 끝난 뒤 선택  
   - 이 factcheck 파일들을 제출 산출물로 남길지
   - 아니면 README 작성용 임시 문서로 보고 삭제할지

3. 최종 전에는 반드시  
   ```bash
   git status --short
   ```
   clean 확인.

결과 파일들 보여주면 내가 README 아키텍처 섹션으로 압축해줄게. 
특히 runner / vertex-retry / state-storage-pipeline 순서로 보면 좋아.
````

## user

```text
~/recovered_workspace/docs $ cat readme-runner-factcheck.txt              
CONFIRMED_FACTS                                                           
                                                                          
- FastAPI starts the in-process job runner from the application lifespan hook. On startup it creates the data directory, initializes the DB schema, 
then calls asyncio.create_task(job_runner(), name="job-runner"). On shutdo
wn it cancels that task, awaits it, and closes the DB connection.                                                                                   
- job_runner() constructs InProcessJobRunner and calls run_forever().     
                                                                          
- InProcessJobRunner.run_forever() runs two startup recovery steps before 
the normal polling loop: sweep_orphans(), then resume_polling_jobs(). Afte
r that it repeatedly calls poll_once() and sleeps for poll_interval, which
 defaults to 1.0 second.                                                  
                                                                          
- Pending job handling: poll_once() calculates available slots from config
ured concurrency minus active in-memory tasks. It selects jobs where state
 is pending and blocked is false, ordered by created_at, limited to availa
ble slots, and using FOR UPDATE SKIP LOCKED. Each claimed job is transitio
ned to queued in the DB transaction, then an in-memory asyncio task is spa
wned for the job handler.                                                 
                                                                          
- Queued job handling: queued is the state assigned during runner claim. T
he normal DB poller does not select queued jobs. A queued job is expected 
to be handled by the in-memory task that was spawned immediately after cla
im. If a process restarts and leaves queued/generating/downloading jobs be
hind, only the startup orphan sweep handles old enough stale rows.        
                                                                          
- Polling job resume: at runner startup, resume_polling_jobs() selects job
s where state is polling and vertex_operation_name is not null, ordered by
 updated_at, limited by available slots, and using FOR UPDATE SKIP LOCKED.
 Those job IDs are spawned into handler tasks without changing state first
.                                                                                                                                                   
- T2V and I2V handlers have explicit resume paths for state polling plus v
ertex_operation_name. They call veo.poll_operation_name(...), then transit
ion to downloading, save output.mp4, add a video asset, and transition to 
completed.                                                                
                                                                          
- Blocked pipeline child handling: pipeline creation writes a T2I parent j
ob as pending and unblocked, and an I2V child job as pending and blocked. The runner's normal pending claim excludes blocked jobs. When a T2I parent
 completes, pipeline_link finds the first child, finds the parent image as
set, sets child.source_asset_id, sets child.blocked to false, commits, and leaves the child pending so a later runner tick can claim it. If the pare
nt fails, blocked children are transitioned to failed.                    
                                                                          
- Important caveat for blocked jobs: the startup orphan sweep selects non-
terminal jobs older than sweep_after unless they are resumable polling job
s. It does not explicitly exclude blocked jobs, so a stale blocked pending
 child can be failed by the startup sweep.                                
                                                                          
- Startup stale-job handling exists, but it is not a periodic background s
weep in the current implementation. It runs once at runner startup. It fai
ls non-terminal jobs older than sweep_after, except polling jobs with vert
ex_operation_name because those are treated as resumable.                 
                                                                          
- Default job runner concurrency is configured by settings.job_runner_conc
urrency, defaulting to 10. InProcessJobRunner also creates an asyncio.Sema
phore with the resolved concurrency and wraps handler execution in that se
maphore.                                                                  
                                                                          
- The runner also limits spawn count by active task count before creating 
handler tasks. Effective in-process generation concurrency is bounded by b
oth the available-slot calculation and the semaphore.                     
                                                                          
- Generation handlers call rate_limit.acquire(job.model) before moving to 
generating for T2I, T2V, and I2V jobs. The rate limiter is implemented as 
a per-model sliding-window limiter with an asyncio lock.                  
                                                                          
- Prompt enhancement with Gemini is not run by the job runner. The /api/pr
ompts/enhance route calls app.services.llm.enhancer.enhance_prompt directl
y, and that service calls vertex_client.models.generate_content.          
                                                                          
- Imagen and Veo generation paths called by the runner use the shared Vert
ex client wrapper. Imagen calls models.generate_images. Veo calls models.g
enerate_videos and later polls operations for generated video bytes.      
                                                                          
                                                                          
SAFE_README_WORDING                                                       
                                                                          - FastAPI starts an in-process asyncio job runner from the application lif
espan hook after initializing local storage and the database schema.      
                                                                          
- The runner claims unblocked pending jobs from Postgres with FOR UPDATE S
KIP LOCKED, transitions them to queued, and dispatches mode-specific handl
er tasks in the same FastAPI process.                                     
                                                                          
- Handler execution is bounded by a configurable in-process concurrency li
mit and an asyncio semaphore.                                             
                                                                          
- Generation requests also pass through per-model sliding-window rate limi
ters before calling Imagen or Veo.                                        
                                                                          
- Veo jobs store the Vertex operation name when they enter polling. On run
ner startup, polling jobs with an operation name are scheduled so polling 
can resume through the saved operation name.                              
                                                                          
- Pipeline I2V child jobs are created as pending but blocked. They become 
eligible for the normal pending-job runner claim only after the T2I parent
 completes and pipeline_link attaches the parent image asset.             
                                                                          
- The runner has a startup orphan sweep that marks old non-terminal, non-r
esumable jobs as failed. This is startup recovery logic, not a continuousl
y running cleanup loop.                                                   
                                                                          
- Prompt enhancement is handled by the prompts API path directly with Gemi
ni; it should be described separately from runner-dispatched generation jo
bs.                                        
                                                                      
DO_NOT_CLAIM                                                              
                                                                          
- Do not claim this is a distributed queue, durable worker fleet, Celery-l
ike system, or Redis-backed scheduler.                                    
                                                                          
- Do not claim every non-terminal job automatically resumes after restart.
 In the current code, polling jobs with vertex_operation_name are resumable; old non-terminal non-resumable jobs are failed by the startup sweep; ne
wer queued/generating/downloading rows left behind at startup are not sele
cted by the normal pending poller.                                        
                                                                          
- Do not claim the orphan sweep runs periodically. The current runner call
s it once before entering the polling loop.                               
                                                                          
- Do not claim queued jobs are independently polled from the database. Que
ued is assigned when a pending job is claimed, and the corresponding in-me
mory task is expected to process it.                                      
                                                                          
- Do not claim blocked child jobs are picked by the normal runner while bl
ocked. The pending-job query explicitly requires blocked is false.        
                                                                          
- Do not overstate blocked job recovery. The startup orphan sweep does not
 special-case blocked jobs, so stale blocked pending children can be faile
d.                                                                        
                                                                          
- Do not show Gemini as a job-runner step for prompt enhancement. Gemini p
rompt enhancement is currently called by /api/prompts/enhance outside the 
runner.                                                                   
                                                                          
- Do not claim multi-process fairness or exactly-once execution beyond wha
t the SELECT ... FOR UPDATE SKIP LOCKED claim and state transitions provid
e.                                                                        
                                                                          
- Do not claim progress percent, live queue position, poll count, cancella
tion, or average completion time estimates are implemented by the runner.
                                                                         
FILE_REFERENCES                                                           

- backend/app/main.py:24-39 - FastAPI lifespan creates DATA_DIR, initializ
es schema, starts job_runner task, cancels it on shutdown, and closes DB.                                      
- backend/app/services/jobs/runner.py:29-62 - InProcessJobRunner configura
tion, resolved concurrency, semaphore, active task set.                                                                                             
- backend/app/services/jobs/runner.py:64-80 - run_forever startup sequence
and polling loop.                   
                                                                          
- backend/app/services/jobs/runner.py:92-116 - poll_once available-slot ca
lculation, pending-job claim, transition to queued, task spawn.
                                                                          
- backend/app/services/jobs/runner.py:172-200 - per-job asyncio task creation, semaphore-wrapped handler execution, failure marking.                
                                                                          
- backend/app/services/jobs/runner.py:220-241 - scheduling of resumable polling jobs.                                                               
                                                                          
- backend/app/services/jobs/runner.py:244-246 - job_runner entrypoint.    
                                                                          
- backend/app/services/jobs/runner.py:249-264 - pending query with state p
ending, blocked false, order, limit, and with_for_update(skip_locked=True)
.                                                                         
                                                                          
- backend/app/services/jobs/runner.py:267-289 - polling resume query with 
state polling, vertex_operation_name present, and with_for_update(skip_loc
ked=True).                                                                
                                                                          
- backend/app/services/jobs/runner.py:292-338 - orphan sweep query and fai
led transition for old non-terminal non-resumable jobs.                   
                                                                          
- backend/app/services/jobs/handlers.py:31-47 - handler dispatch by genera
tion mode.                                                                

- backend/app/services/jobs/handlers.py:50-112 - T2I handler state progres
sion, rate-limit acquire, image save, completion, and pipeline link call. 

- backend/app/services/jobs/handlers.py:241-356 - T2V handler, including p
olling resume path, rate-limit acquire, operation-name storage, polling, save, and completion.                 
                                                                          
- backend/app/services/jobs/handlers.py:358-483 - I2V handler, including polling resume path, source asset validation/read, rate-limit acquire, oper
ation-name storage, polling, save, and completion. 
- backend/app/services/jobs/pipeline_link.py:26-84 - completed T2I parent 
links first child to first parent image asset and unblocks it. 
                                                                          
- backend/app/services/jobs/pipeline_link.py:87-111 - failed parent marks blocked children failed.                                                  
                                                                          
- backend/app/api/pipelines.py:37-78 - pipeline creation writes parent pending/unblocked and child pending/blocked.                                 
                                                                          
- backend/app/api/generations.py:126-151 - normal generation creation writ
es pending jobs with blocked false.                                       
                                                                          
- backend/app/config.py:7-12 - default job_runner_concurrency setting.    
                                                                          
- backend/app/services/rate_limit.py:28-84 - sliding-window limiter implem
entation.                                                                 
                                                                          
- backend/app/services/rate_limit.py:87-113 - default per-model limits and
 acquire(model_id).                                                       
                                                                          
- backend/app/api/prompts.py:31-77 - prompt enhancement route calls enhanc
er directly and stores PromptEnhancement.                                 
                                                                          
- backend/app/services/llm/enhancer.py:187-303 - Gemini prompt enhancement
 call path via vertex_client.models.generate_content.
                                                                          
- backend/app/services/vertex/client.py:42-53 - shared google-genai Vertex
 client construction.
                                                                          
- backend/app/services/vertex/imagen.py:12-37 - Imagen generation through shared client.                       
                                                                          
- backend/app/services/vertex/veo.py:24-123 - Veo submit, operation polling, and operation-name resume helper.                                                                     

```

## assistant

````text
좋아. 이 runner fact check 기준으로 README 아키텍처 섹션에서 쓸 수 있는 핵심은 확정됐어.

README에는 이렇게 쓰면 안전해:

```md
FastAPI는 application lifespan에서 로컬 저장소와 DB schema를 초기화한 뒤, 같은 프로세스 안에서 asyncio 기반 job runner를 시작합니다. 별도의 Celery나 Redis 없이 PostgreSQL job table을 기준으로 작업 상태를 관리하며, runner는 `pending` 상태이면서 `blocked=false`인 job을 `FOR UPDATE SKIP LOCKED`로 claim한 뒤 `queued`로 전이하고 mode별 handler task를 실행합니다.

동시 실행은 설정값 기반 concurrency limit과 `asyncio.Semaphore`로 제한되며, Imagen/Veo 호출 전에는 모델별 sliding-window rate limiter를 거칩니다. Veo 작업은 polling 단계에서 Vertex operation name을 저장하고, runner 재시작 시 `polling` 상태이면서 operation name이 있는 job은 해당 operation name으로 polling을 재개할 수 있습니다.

T2I → I2V pipeline에서는 I2V child job을 처음에는 `blocked` 상태로 생성합니다. parent T2I job이 완료되면 생성된 image asset을 child의 `source_asset_id`로 연결하고 `blocked=false`로 바꾸어 runner가 처리할 수 있게 합니다. parent가 실패하면 연결된 blocked child job도 실패 상태로 전이합니다.
```

넣지 말아야 할 표현도 명확해:

- “분산 큐”, “Celery-like”, “Redis-backed scheduler”
- “모든 non-terminal job이 재시작 후 자동 복구됨”
- “orphan sweep이 주기적으로 계속 돈다”
- “queued job을 DB에서 다시 polling한다”
- “prompt enhancement도 runner job으로 처리된다”
- “정확한 progress percent / queue position / ETA / cancel API 제공”

특히 좋은 포인트는 이거야: **단일 인스턴스 과제 범위에 맞춰 단순한 구조를 선택했지만, DB claim, state transition, concurrency, rate limit, Veo polling resume까지는 엔지니어링적으로 보강했다**는 메시지.

다음은 `readme-vertex-retry-factcheck.txt` 보여줘.
````

## user

```text
~/recovered_workspace/docs $ cat readme-vertex-retry-factcheck.txt        
CONFIRMED_FACTS                                                           
                                                                          
- The backend declares google-genai as the Vertex SDK dependency. No separ
ate google.cloud Vertex model SDK or provider-specific Imagen/Veo/Gemini S
DK was found in the checked backend app source.                           
                                                                          
- The shared Vertex client is built in backend/app/services/vertex/client.
py with genai.Client(vertexai=True, credentials=..., project=..., location
=...). The credential file contents are not exposed by this check.        
                                                                          
- Imagen calls are implemented in backend/app/services/vertex/imagen.py. g
enerate_image() builds a google.genai.types.GenerateImagesConfig, calls ge
t_vertex_client().models.generate_images, and extracts generated_images[*]
.image.image_bytes.                                                       
                                                                          
- Veo calls are implemented in backend/app/services/vertex/veo.py. submit_
video() builds a google.genai.types.GenerateVideosConfig and calls get_ver
tex_client().models.generate_videos. For text-to-video it passes prompt di
rectly. For image-to-video it passes a GenerateVideosSource containing pro
mpt plus inline image bytes and MIME type.                                
                                                                          
- Gemini prompt enhancement calls are implemented in backend/app/services/
llm/enhancer.py. enhance_prompt() uses the shared Vertex client, builds a 
google.genai.types.GenerateContentConfig with JSON response settings, call
s vertex_client.models.generate_content, and parses/validates the JSON-lik
e response into an enhanced prompt and components.                        
                                                                          
- The prompt enhancement API path calls the enhancer directly. It is not d
ispatched through the in-process job runner.                              
                                                                          
- Veo is implemented without output_gcs_uri. A source search for output_gc
s_uri in backend/app and backend/pyproject.toml returned no matches.      
                                                                          
- Veo output is read from operation.result.generated_videos[0].video.video
_bytes. T2V and I2V handlers save those bytes as output.mp4 through storag
e.save_bytes and record a video asset in the database.

- Imagen output is read as inline image bytes and saved as output.png or o
utput-N.png through storage.save_bytes.

- Rate limiting uses an in-memory SlidingWindowLimiter. Each limiter keeps
 a deque of event timestamps, prunes timestamps outside the window, and us
es an asyncio.Lock around acquire().

- DEFAULT_MODEL_LIMITS defines independent limiter instances per model id 
through the LIMITERS dictionary. The checked generation handlers call rate
_limit.acquire(job.model), so limits are applied by selected model id.

- Imagen limits in DEFAULT_MODEL_LIMITS are 75 requests per 60 seconds for
 each of imagen-4.0-fast-generate-001, imagen-4.0-generate-001, and imagen
-4.0-ultra-generate-001.

- Veo limits in DEFAULT_MODEL_LIMITS are 10 requests per 60 seconds for ea
ch of veo-3.0-fast-generate-001 and veo-3.0-generate-001.

- DEFAULT_MODEL_LIMITS also contains gemini-2.5-flash at 60 requests per 6
0 seconds, but the checked prompt enhancement path does not call rate_limi
t.acquire(). Do not describe Gemini prompt enhancement as actively rate-li
mited by this limiter unless that call path is changed.

- Retry/backoff is implemented in backend/app/services/retry.py. Defaults 
are max_attempts=3, base=1.0 second, max_delay=20.0 seconds, and retryable
 status codes 429, 500, 502, 503, 504, and 408.

- The default retry delay is exponential without jitter: delay = min(max_d
elay, base * 2 ** (attempt - 1)). With the default three attempts, sleeps 
occur after the first and second failed attempts, normally 1 second then 2
 seconds.

- with_retry retries when the exception has retryable=True or when an extr
acted status_code/code/status/response.status_code is in the retryable sta
tus set. Otherwise it raises immediately.

- T2I wraps the Imagen generation attempt in with_retry. T2V wraps the ini
tial Veo submit in with_retry. I2V wraps the initial Veo submit in with_re
try.

- Veo polling is not wrapped in with_retry in the checked handlers. poll_o
peration and poll_operation_name have their own polling loop, operation er
ror mapping, and timeout behavior, but not the generic retry.py backoff wr
apper.

- Gemini prompt enhancement transport/model calls are not wrapped in retry
.py with_retry. There is a separate one-time strict JSON retry only when r
esponse parsing fails with malformed_json from text.
.py with_retry. There is a separate one-time strict JSON retry on[144/232]
esponse parsing fails with malformed_json from text.                      
                                                                          
- Retryable Vertex error classes include VertexRateLimitError and VertexTr
ansientError. map_vertex_error classifies HTTP 429 as rate-limited and 408
/500/502/503/504 or ConnectionError/TimeoutError as transient.            
                                                                          
- map_vertex_operation_error classifies operation error code 8 or resource
_exhausted as VertexRateLimitError. It classifies operation error codes 4,
 10, 13, and 14, or status text deadline_exceeded, aborted, internal, or u
navailable, as VertexTransientError.                                      
                                                                          
- Non-retryable Vertex error categories include configuration/credential e
rrors, authentication failures, permission denied, invalid request, safety
 blocked, output unavailable, and unknown errors unless they carry retryab
le=True or a retryable status code.                                       
                                                                          
- VeoTimeoutError is converted by the job handler into a public error with
 code veo_timeout and retryable true, but the checked code does not automa
tically resubmit or re-poll it through with_retry after the timeout.      
                                                                          
- Veo operation errors are classified by map_vertex_operation_error. Safet
y-like text maps to VertexSafetyError. Unauthenticated maps to VertexAuthe
nticationError. Permission denied maps to VertexPermissionError. Resource 
exhausted maps to VertexRateLimitError. Transient operation states map to 
VertexTransientError. Invalid argument and not found map to VertexRequestE
rror. Otherwise the operation error maps to VertexUnknownError.           
                                                                          
- Veo filtered output is detected from result.rai_media_filtered_reasons o
r a positive result.rai_media_filtered_count and is classified as VertexSa
fetyError with public code vertex_safety_blocked.                         
                                                                          
- Veo empty or missing output is classified as VertexOutputError with publ
ic code vertex_output_unavailable. This covers missing generated_videos an
d missing video.video_bytes.                                              
                                                                          
- Imagen empty output is currently classified as VertexUnknownError when n
o generated image bytes are extracted.                                    
                                                                          
                                                                          
SAFE_README_WORDING                                                       

- Vertex calls are centralized through google-genai: the backend builds a 
shared genai.Client with vertexai=True and uses it for Imagen, Veo, and Ge
mini prompt enhancement.             
                                                                          
- Imagen generation uses models.generate_images and stores returned image 
bytes as local image assets.        

- Veo generation uses models.generate_videos, stores the returned Vertex o
peration name while polling, and saves the completed inline video bytes as
 local MP4 assets.                                                        

- The current Veo implementation does not configure output_gcs_uri; it rea
ds generated_videos[0].video.video_bytes from the completed operation.    
                                     
- Generation calls use per-model in-memory sliding-window rate limiters be
fore submitting to Vertex. The configured limits are 75 requests per minut
e per Imagen model id and 10 requests per minute per Veo model id.

- Initial Imagen and Veo submission calls are wrapped in a bounded retry h
elper for retryable rate-limit and transient failures.                    
                                                                          
- The default retry policy makes up to three attempts with exponential bac
koff starting at 1 second and capped at 20 seconds.                       
                                                                          
- Veo polling maps operation errors, safety-filtered results, and missing 
output into public error codes such as vertex_safety_blocked and vertex_ou
tput_unavailable. 
                                                                          
- Prompt enhancement is a direct Gemini API path, separate from the genera
tion job runner. It validates the model response as JSON and performs one 
strict JSON retry only for malformed text responses.                      

                                                                          
DO_NOT_CLAIM                                                              
                                                                          
- Do not claim the app uses GCS for Veo output. The checked implementation
 does not set output_gcs_uri and saves inline video bytes locally.        
                                                                          
- Do not claim retries cover every Vertex call. The generic with_retry wra
pper covers initial Imagen generation and initial Veo submit calls in the 
checked generation handlers, not Veo polling and not the Gemini enhancer c
all.                                                                      
                                                                          
- Do not claim retries are infinite, unbounded, jittered, or circuit-break
er based. The default helper has three attempts and simple exponential sle
ep without jitter.                                                        
                                                                          
- Do not claim all failures are retryable. Authentication, permission, inv
alid request, safety block, output unavailable, configuration, credential,
 and unknown errors are not retryable unless they explicitly carry retryab
le=True or a retryable status code.                                       
                                                                          
- Do not claim Veo timeout automatically retries the operation. The public
 error is marked retryable, but the checked handler does not automatically
 continue retrying after VeoTimeoutError.                                 
                                                                          
- Do not claim the rate limiter is distributed across processes, persisted
 in Postgres, shared across containers, or synchronized with live Google q
uota data. It is an in-memory limiter per backend process.                
                                                                          
- Do not claim there is one shared Imagen bucket and one shared Veo bucket
 unless you explain it carefully. The code creates one limiter per model i
d, so each listed Imagen model has its own 75/min window and each listed V
eo model has its own 10/min window.                                       
                                                                          
- Do not claim Gemini prompt enhancement is actively protected by rate_lim
it.acquire() in the current call path. A Gemini limit is declared in DEFAU
LT_MODEL_LIMITS, but the enhancer route does not use that limiter in the c
hecked code.                                                              
                                                                          
- Do not claim safety blocks are bypassed or retried into success. Safety 
signals are mapped to vertex_safety_blocked and surfaced as failures.     
                                                                          
- Do not claim operation error classification preserves every provider det
ail. The code maps provider/operation errors into a small public set of ap
plication error categories.                                               
                                                                          
- Do not claim exactly-once Vertex billing or duplicate-charge prevention 
from retry alone. The retry helper may repeat initial submit attempts when
 it classifies failures as retryable.                                     
                                                                          
                                                                          
FILE_REFERENCES                                                           
                                                                          
- backend/pyproject.toml:6-15 - backend dependencies include google-genai.
                                                                          
- backend/app/services/vertex/client.py:7-9 - imports google genai and goo
gle-auth service account helpers.
                                                                          
- backend/app/services/vertex/client.py:42-53 - shared genai.Client(vertex
ai=True, credentials, project, location).
                                                                          
- backend/app/services/vertex/imagen.py:6 - imports google.genai.types.   
                                     
- backend/app/services/vertex/imagen.py:12-37 - Imagen generate_image uses
 GenerateImagesConfig, models.generate_images, and extracted image bytes. 
                                                                          
- backend/app/services/vertex/imagen.py:40-49 - Imagen response byte extra
ction from generated_images[*].image.image_bytes.
                                                                          
- backend/app/services/vertex/veo.py:7 - imports google.genai.types.      
                                     
- backend/app/services/vertex/veo.py:24-59 - Veo submit_video uses Generat
eVideosConfig, optional GenerateVideosSource with inline image bytes, and 
models.generate_videos.                                                   

- backend/app/services/vertex/veo.py:62-83 - Veo polling loop uses operati
ons.get with backoff-like polling interval growth and deadline.           
                                                                          
- backend/app/services/vertex/veo.py:85-102 - Veo operation error mapping,
 filtered-output safety handling, generated_videos check, and video.video_
bytes extraction.                                                         
                                                                          
- backend/app/services/vertex/veo.py:105-123 - poll_operation_name fetches
 an operation by saved operation name and delegates to poll_operation.
                                                                          
- backend/app/services/vertex/veo.py:126-135 - filtered-output detection u
sing rai_media_filtered_reasons and rai_media_filtered_count.             
                                                                          
- backend/app/services/llm/enhancer.py:11 - imports google.genai.types.
                                                                          
- backend/app/services/llm/enhancer.py:187-266 - prompt enhancement entryp
oint uses shared Vertex client and returns parsed enhancement result.     
                                                                          
- backend/app/services/llm/enhancer.py:269-303 - Gemini generate_content c
all and error mapping.                                                    
                                                                          
- backend/app/services/llm/enhancer.py:217-242 and 306-309 - one-time stri
ct JSON retry for malformed text responses.                               
                                                                          
- backend/app/api/prompts.py:31-77 - prompt enhancement API calls enhancer
 directly and stores PromptEnhancement.                                   
                                                                          
- backend/app/services/rate_limit.py:28-84 - SlidingWindowLimiter implemen
tation with deque and asyncio.Lock.                                       
- backend/app/services/rate_limit.py:87-102 - per-model DEFAULT_MODEL_LIMI
TS and LIMITERS dictionary.                                               
                                                                          
- backend/app/services/rate_limit.py:105-113 - get_limiter and acquire cho
ose the limiter by model id.                                              
                                                                          
- backend/app/services/retry.py:9 - default retryable status codes.       
                                     
- backend/app/services/retry.py:19-47 - with_retry defaults, max attempts 
validation, retry loop, and sleep between attempts.                       
                                                                          
- backend/app/services/retry.py:49-50 - exponential delay calculation.    
                                                                          
- backend/app/services/retry.py:53-76 - retryable exception classification
 by retryable attribute or status code.                                   
                                                                          
- backend/app/services/vertex/errors.py:6-28 - base VertexServiceError pub
lic error structure and retryable flag.                                   
                                                                          
- backend/app/services/vertex/errors.py:71-90 - safety, rate-limit, transi
ent, and output error classes.                                            
                                     
- backend/app/services/vertex/errors.py:98-125 - Veo operation error class
ification.                                                                
                                                                          
- backend/app/services/vertex/errors.py:128-150 - regular Vertex exception
 classification.                                                          
                                                                          
- backend/app/services/vertex/errors.py:200-209 - safety signal detection 
terms.                                                                    
                                                                          
- backend/app/services/jobs/handlers.py:59-78 - T2I rate-limit acquire and
 with_retry around Imagen generation.                                     
                                                                          
- backend/app/services/jobs/handlers.py:88-103 - T2I local image byte save
 and completion.                                                          
                                                                          
- backend/app/services/jobs/handlers.py:131-166 - Veo T2V/I2V submit attem
pt helpers increment attempts and call veo.submit_video.                  
                                                                          
- backend/app/services/jobs/handlers.py:169-225 - public job error mapping
, including VeoTimeoutError and VertexServiceError.                       
                                                                          
- backend/app/services/jobs/handlers.py:288-320 - T2V rate-limit acquire, 
with_retry around Veo submit, operation-name storage, and polling call.   
                                                                          
- backend/app/services/jobs/handlers.py:328-349 - T2V local video byte sav
e and completion.                                                         
                                                                          
- backend/app/services/jobs/handlers.py:405-448 - I2V rate-limit acquire, 
source image byte read, with_retry around Veo submit, operation-name stora
ge, and polling call.                                                     
                                                                          
- backend/app/services/jobs/handlers.py:456-477 - I2V local video byte sav
e and completion.                                                                                                             


```

## assistant

````text
좋아. 이걸로 Vertex/retry 섹션은 꽤 정확하게 쓸 수 있어.

README에는 이 정도만 넣는 게 좋아:

```md
AI 호출은 `google-genai` 단일 SDK로 통합했습니다. 백엔드는 `genai.Client(vertexai=True, ...)`를 공유 client로 구성하고, Imagen 이미지 생성, Veo 비디오 생성, Gemini prompt enhancement에 모두 같은 Vertex client 경로를 사용합니다.

Imagen은 `models.generate_images`로 받은 inline image bytes를 로컬 asset으로 저장합니다. Veo는 `models.generate_videos`로 long-running operation을 생성하고, 완료 후 `generated_videos[0].video.video_bytes`를 읽어 MP4 파일로 저장합니다. 현재 구현은 `output_gcs_uri`를 사용하지 않으며, 생성 파일은 로컬 `DATA_DIR` 아래에 저장합니다.

생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과합니다. Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다. 초기 Imagen 생성 호출과 초기 Veo submit 호출은 retry helper로 감싸며, 기본 정책은 최대 3회 시도와 1초부터 시작하는 exponential backoff입니다.

Veo polling 단계에서는 operation error, safety-filtered result, missing output을 별도 public error code로 분류합니다. 예를 들어 safety filter는 `vertex_safety_blocked`, 결과 bytes가 없는 경우는 `vertex_output_unavailable`로 노출합니다. Prompt enhancement는 generation job runner와 별도 API 흐름에서 Gemini를 호출하며, JSON schema validation과 malformed JSON에 대한 1회 strict retry를 적용합니다.
```

주의해서 빼야 할 표현:

- “Gemini도 rate limiter로 보호된다” → 현재 enhancer path는 `rate_limit.acquire()` 안 탐.
- “모든 Vertex 호출에 retry 적용” → Imagen/T2V/I2V 초기 submit 중심.
- “Veo polling도 retry.py로 retry” → 아님.
- “GCS 사용” → 아님.
- “safety block 우회/재시도” → 절대 아님.
- “retry로 중복 과금 방지” → 위험한 주장.

좋은 제출 메시지는 이거야: **단일 SDK, inline bytes, local storage, bounded retry, model별 rate-limit, provider error classification**.

이제 마지막 `state-storage-pipeline` 보여주면 아키텍처 섹션 전체로 합쳐줄 수 있어.
````

## user

```text
~/recovered_workspace/docs $ cat readme-state-storage-pipeline-factcheck.txt                                                                        
CONFIRMED_FACTS                                                           
                                                                          - JobState values are pending, enhancing, queued, generating, polling, dow
nloading, completed, failed, and cancelled.                               
                                                                          
- Terminal states are completed, failed, and cancelled. Non-terminal state
s are all other JobState values.                                          
                                                                          - The allowed transition matrix is explicit. pending can transition to enh
ancing, queued, failed, or cancelled. enhancing can transition to queued, 
failed, or cancelled. queued can transition to generating, failed, or canc
elled. generating can transition to polling, downloading, failed, or cance
lled. polling can transition to polling, downloading, failed, or cancelled
. downloading can transition to completed, failed, or cancelled. completed
, failed, and cancelled have no outgoing transitions.                                                                                               
- transition(...) normalizes the current and target states, rejects transi
tions that are not in ALLOWED_TRANSITIONS by raising InvalidTransitionErro
r, updates job.state and job.updated_at, and appends a state_history entry
 with state, timestamp, and optional detail.                              
                                                                          
- transition(...) is used in the runner, generation handlers, and pipeline
 linking code. It is used for runner claim to queued, handler progress thr
ough generating/polling/downloading/completed, failure paths, orphan sweep
 failure, and pipeline child failure. API create paths construct initial p
ending rows directly rather than calling transition(...).                 
                                                                          
- README can safely describe state handling as an explicit application-lev
el state machine with terminal states and validated transitions. It should
 not imply every assignment to an initial state goes through transition(...), because initial Job objects are constructed with state=JobState.PENDIN
G.                                                                        
                                                                          
- Storage stores files under DATA_DIR using a two-part local path: <job_uu
id>/<filename>. save_bytes writes to DATA_DIR/<job_uuid>/<filename> and re
turns that relative path.                                                                                                                           
- T2I stores image assets with filenames output.png, output-2.png, and so 
on. T2V and I2V store video assets as output.mp4.                         
                                                                          - Asset writes in the generation handlers go through storage.save_bytes. I
2V source image reads go through storage.read_bytes. History deletion file
 removal goes through storage.delete_file.                                
                                                                          
- save_bytes validates the job id as a UUID, validates the filename with a
 conservative regex, creates the job directory under DATA_DIR, verifies th
e resolved job directory and target path stay inside DATA_DIR, and opens t
he directory/file with O_NOFOLLOW when available.                         
                                                                          
- delete_file parses the stored local path, validates the UUID and filenam
e, resolves the job directory under DATA_DIR, opens the directory with O_N
OFOLLOW when available, checks the target with os.stat(..., follow_symlinks=False), requires a regular file, unlinks only that filename via dir_fd, 
and then tries to remove the now-empty job directory.                     
                                                                          
- resolve_asset_path, used by read_bytes and the /files route, requires a 
local path shaped exactly as <job_uuid>/<filename>, rejects absolute paths
, backslashes, empty parts, ".", "..", invalid UUIDs, and unsupported file
name characters, resolves the path, verifies it remains inside DATA_DIR, and requires it to be a file.                                                                                                                        
- Path traversal protections are present for local asset paths. A path lik
e ../..., an absolute path, a path with more than two parts, a non-UUID fi
rst segment, or a filename containing a path separator is rejected before 
serving or deleting.                                                      
                                                                          - Important nuance: resolve_asset_path uses Path.resolve(...), which follo
ws symlinks before checking that the resolved path remains inside DATA_DIR
. save_bytes and delete_file use O_NOFOLLOW/follow_symlinks=False protecti
ons, but the read/serve path should be described as DATA_DIR prefix and lo
cal-path validation rather than as a blanket "no symlink can ever be serve
d" guarantee.                                                             
                                                                          
- The /files/{local_path:path} route calls resolve_asset_path before servi
ng, so the route uses the same local path shape and DATA_DIR containment c
hecks.                                                                                                                                              
- /files returns StreamingResponse with Accept-Ranges: bytes and Content-L
ength for normal full-file responses.                                                                                                               
- /files supports a single byte range in the Range header. It supports exp
licit ranges like bytes=0-99, open-ended ranges like bytes=100-, and suffi
x ranges like bytes=-500.      
- /files rejects non-byte range units, missing intervals, non-numeric boun
ds, and multiple ranges with HTTP 400. It returns HTTP 416 with Content-Ra
nge: bytes */<file_size> for unsatisfiable ranges, including empty files and starts beyond the file size.                                           
                                                                          
- /files does not implement multipart range responses. Multiple byte ranges are explicitly rejected.                                                
                                                                          
- Pipeline creation writes two jobs in one request: a T2I parent job in pe
nding state with blocked=False, and an I2V child job in pending state with
 parent_job_id set to the parent id, source_asset_id=None, and blocked=Tru
e.                                                                        
                                                                          
- The runner's pending-job query only claims jobs where state is pending a
nd blocked is false. Therefore a pipeline child is not eligible for normal
 runner processing while blocked=True.                                    
                                                                          
- When a T2I handler completes, it calls pipeline_link.link_completed_pare
nt(session, job). This linking function only proceeds if the parent mode is T2I and the parent state is completed.                                  
                                                                          
- Pipeline linking finds the first I2V child ordered by created_at and id.
 It only links if the child exists, is not terminal, and is still pending.
                                                                          
- Pipeline linking finds the first asset for the parent ordered by created
_at and id. If no asset exists, the child is transitioned to failed with p
ipeline_source_asset_missing. If the first parent asset is not an image, t
he child is transitioned to failed with pipeline_source_asset_not_image.  
                                                                          
- When linking succeeds, pipeline_link sets child.source_asset_id to the s
elected parent image asset id, sets child.blocked to false, commits, and r
eturns a linked result. The child remains pending, so a later runner poll 
can claim it as an unblocked pending job.                                 
                                                                          - If a T2I parent fails inside the T2I handler, fail_blocked_children_for_
parent marks blocked, non-terminal pipeline children failed with pipeline_
parent_failed.                                                            
                                                                          
- Normal I2V generation requests outside pipeline validate the supplied so
urce_asset_id immediately, require that the source asset exists and is an 
image, set parent_job_id to the source asset's job_id, and create the I2V 
job as pending with blocked=False.                                        
                                                                          
- Deletion is implemented by DELETE /api/generations/{job_id}. Only terminal jobs can be deleted. Non-terminal jobs, including active jobs, are reje
cted with HTTP 409.                                                       
                                                                          
- Before deleting a terminal job, deletion finds jobs that reference it as
 parent_job_id and jobs that use its asset ids as source_asset_id. If any 
referencing job is non-terminal, deletion is rejected with HTTP 409.      
                                                                          
- If all referencing jobs are terminal, deletion proceeds. The code delete
s only files belonging to the target job's own assets, then detaches refer
ences from the terminal referencing jobs by setting parent_job_id to None 
when it pointed at the deleted job and source_asset_id to None when it poi
nted at one of the deleted job's assets.                                                                                                            
- Deletion calls storage.delete_file(asset.local_path, missing_ok=True) fo
r each asset owned by the deleted job. It does not recursively delete arbi
trary files under DATA_DIR; it deletes the validated local paths stored on
 the job's Asset rows and optionally removes the now-empty per-job directo
ry.                                                                       
                                                                          - If storage.delete_file raises StoragePathError during deletion, the API 
returns HTTP 409 and does not delete the job.                             
                                                                          
- The SQLAlchemy Job.assets relationship uses cascade="all, delete-orphan"
, and Asset.job_id has ondelete="CASCADE", so deleting the Job also remove
s its asset rows. Files are deleted explicitly first through storage.delet
e_file.                                                                   
                                                                          
                                                                          
SAFE_README_WORDING                                                       
                                                                          
- Job lifecycle is guarded by an explicit state machine. The normal genera
tion path is pending -> queued -> generating -> polling or downloading -> 
completed, with failed and cancelled modeled as terminal states.          
                                                                          
- State changes during runner and handler execution go through transition(
...), which validates the requested transition and records state_history entries.                                                                   
                                                                          
- Generated assets are written under DATA_DIR using local paths of the form <job_uuid>/<filename>; generation handlers persist asset metadata in Pos
tgres and store bytes through storage.save_bytes.                         
                                                                          
- Storage helpers validate UUID job directories, conservative filenames, D
ATA_DIR containment, and regular-file deletion before writing, serving, or
 deleting asset paths.                                                    
                                                                          
- The /files route streams validated local asset paths and supports single byte-range requests for media playback.                                  
                                                                          
- Pipeline creation stores a pending T2I parent and a blocked pending I2V child. After the parent completes with an image asset, the linker assigns 
that image asset id to child.source_asset_id, clears blocked, and leaves t
he child pending for the runner.                                          
                                                                          
- History deletion is limited to terminal jobs. Active jobs cannot be dele
ted, and terminal jobs with active dependent jobs are protected from delet
ion.                                                                      
                                                                          
- When deleting a terminal job that only has terminal dependents, the API 
deletes the target job's own asset files and clears dependent parent/sourc
e-asset references before deleting the job row.                           
                                                                          
                                                                          DO_NOT_CLAIM                                                              
                                                                          
- Do not claim every Job.state assignment goes through transition(...). In
itial pending state is assigned directly when Job rows are created.       
                                                                          
- Do not claim the app supports arbitrary state transitions, pause/resume 
states, or progress percentage states. The allowed matrix is fixed to the 
listed JobState values and transitions.                                   
                                                                          
- Do not claim cancelled is implemented as a user-facing cancel workflow. 
It exists as a terminal state in the state machine, but the checked deleti
on and generation code does not implement a cancel API flow.              
                                                                          
- Do not claim /files supports multipart ranges. Multiple byte ranges are 
rejected with HTTP 400.                                                   
                                                                          
- Do not claim /files can serve arbitrary DATA_DIR-relative paths. It only
 accepts local paths that parse as <job_uuid>/<filename> with a UUID first
 segment and a validated filename.                                        
                                                                          
- Do not claim path safety is based only on string prefix checks. The code
 parses local paths, validates UUIDs and filenames, resolves paths, checks
 DATA_DIR containment, and uses no-follow or non-symlink checks in write/d
elete paths.                                                              
                                                                          - Do not overstate symlink guarantees for read/serve paths. The read path 
resolves symlinks and enforces that the resolved target remains inside DAT
A_DIR; write/delete paths have stronger no-follow protections.            
                                                                          
- Do not claim pipeline child jobs are immediately runnable when created. 
They are created pending but blocked, and the runner excludes blocked jobs
.                                                                         
                                                                          
- Do not claim pipeline linking creates a new asset copy for the child. It
 sets child.source_asset_id to the existing parent image asset id.        
                                                                          
- Do not claim all parent assets are attached to the child. The linker picks the first parent asset ordered by created_at and id, and requires that 
selected asset to be an image.                                            
                                                                          
- Do not claim failed parents always delete or cancel children. The checke
d logic marks blocked, non-terminal children failed; it does not delete th
em.                                                                       
                                                                          - Do not claim active jobs can be deleted from History. The delete endpoin
t rejects any non-terminal target job.                                    
                                                                          
- Do not claim deleting a completed parent with an active child is allowed
. The delete endpoint blocks deletion when any referencing job is non-term
inal.                                                                     
                                                                          
- Do not claim deletion recursively purges an entire job directory regardl
ess of DB contents. It iterates over the target job's Asset rows, deletes 
those validated local paths, and only attempts to remove the job directory
 if it becomes empty.                                                     
                                                                          
- Do not claim dependent terminal jobs are deleted with the target job. Th
ey are kept, but their parent_job_id and/or source_asset_id references are
 detached when applicable.                                                
                                                                          
                                                                          FILE_REFERENCES                                                           
                                                                          
- backend/app/models.py:21-30 - JobState enum values.                                                                                               
- backend/app/models.py:63-145 - Job columns and relationships, including 
parent_job_id, source_asset_id, blocked, vertex_operation_name, state_hist
ory, and assets relationship cascade.                
                                                                     
- backend/app/models.py:148-179 - Asset columns and relationship to Job.  
                                                                          
- backend/app/state_machine.py:9-15 - STATES, TERMINAL_STATES, and NON_TERMINAL_STATES.                                                             
                                                                          
- backend/app/state_machine.py:17-49 - allowed transition matrix.                                                                                   
- backend/app/state_machine.py:56-67 - state normalization and can_transit
ion.                                                                      
                                                                          
- backend/app/state_machine.py:69-98 - transition(...) validation, state u
pdate, updated_at update, and state_history append.                       
                                                                          
- backend/app/services/jobs/runner.py:92-116 - runner pending-job claim tr
ansitions jobs to queued.                                                 
                                                                          
- backend/app/services/jobs/runner.py:249-259 - pending-job query requires
 state pending and blocked false.                                         
                                                                          - backend/app/services/jobs/runner.py:292-338 - orphan sweep uses transiti
on(..., failed) for old non-terminal non-resumable jobs.                  
                                                                          
- backend/app/services/jobs/runner.py:341-367 - runner failure path uses t
ransition(..., failed).                                                   
                                                                          
- backend/app/services/jobs/handlers.py:50-112 - T2I state transitions, im
age asset save, completion, and pipeline link call.                       
                                                                          
- backend/app/services/jobs/handlers.py:169-177 - handler failure path use
s transition(..., failed).                                                
                                                                          
- backend/app/services/jobs/handlers.py:241-356 - T2V state transitions, v
ideo asset save, and failure handling.                                    
                                                                          
- backend/app/services/jobs/handlers.py:358-483 - I2V state transitions, s
ource asset read, video asset save, and failure handling.                 
                                                                          
- backend/app/services/jobs/pipeline_link.py:26-84 - completed parent link
 conditions, parent asset lookup, source_asset_id assignment, and blocked 
false.                                                                    
                                                                          
- backend/app/services/jobs/pipeline_link.py:87-111 - failed parent handli
ng for blocked children.                                                  
                                                                          - backend/app/services/jobs/pipeline_link.py:119-140 - child and parent as
set lookup ordering.                                                      
                                                                          
- backend/app/services/jobs/pipeline_link.py:143-156 - child failure helpe
r and transition(..., failed).                                            
                                                                          
- backend/app/api/pipelines.py:37-78 - pipeline parent/child job construct
ion with child blocked=True and source_asset_id=None.                     
                                                                          
- backend/app/api/pipelines.py:80-88 - pipeline creation commits both jobs
 and returns parent/child response.                                       
                                                                          - backend/app/api/pipelines.py:91-125 - pipeline lookup by parent id and f
irst I2V child.                                                           
                                                                          
- backend/app/api/generations.py:76-99 - normal I2V create validates sourc
e asset and creates an unblocked I2V job.                                 
                                                                          
- backend/app/api/generations.py:126-151 - normal generation job construction with initial pending state and blocked=False.                         
                                                                          
- backend/app/api/generations.py:197-228 - delete endpoint loads job/asset
s, validates deletability, deletes asset files, detaches references, delet
es job, and commits.                                                      
                                                                          
- backend/app/api/generations.py:230-244 - only terminal jobs are deletabl
e and active dependent jobs block deletion.                               
                                                                          
- backend/app/api/generations.py:247-281 - dependent job discovery through
 parent_job_id and source_asset_id.                                       
                                                                          
- backend/app/api/generations.py:284-290 - reference detachment for termin
al dependent jobs.                                                        
                                                                          
- backend/app/services/storage.py:16-18 - filename regex and no-follow fla
g constants.                                                              
                                                                          
- backend/app/services/storage.py:21-58 - save_bytes DATA_DIR/<job_uuid>/<
filename> write path, validation, containment, no-follow open, and returned local path.                                                             
                                                                          
- backend/app/services/storage.py:61-62 - read_bytes goes through resolve_
asset_path.                                                               
                                                                    
- backend/app/services/storage.py:65-105 - delete_file validation, no-follow directory open, regular-file check, unlink by dir_fd, and optional dire
ctory removal.                                                            
                                                                          
- backend/app/services/storage.py:108-124 - resolve_asset_path and _safe_p
ath containment checks.                                                   
                                                                          
- backend/app/services/storage.py:127-142 - local path parser rejects inva
lid shape, absolute paths, traversal parts, backslashes, non-UUID job ids,
 and invalid filenames.                                                   
                                                                          
- backend/app/services/storage.py:145-148 - DATA_DIR root creation and res
olution.                                                                  
                                                                          
- backend/app/services/storage.py:151-172 - UUID coercion, filename valida
tion, and DATA_DIR containment enforcement.                               
                                                                          
- backend/app/api/files.py:24-72 - /files route safe path resolution, norm
al streaming response, Range handling, and 206/416 responses.             
                                                                          
- backend/app/api/files.py:75-114 - single byte range parser, suffix/open-ended range support, and rejection of invalid or multiple ranges.         
                                                                          
- backend/app/api/files.py:117-137 - full-file and range streaming iterato
rs.                                                                       
  
                  

```

## assistant

````text
좋아. 이제 README 아키텍처/핵심 설계 섹션은 아래처럼 합치면 돼. 너무 구현 디테일을 과하게 늘리지 않고, 평가자가 좋아할 설계 판단만 남긴 버전이야.

```md
## 프로젝트 아키텍처 및 핵심 설계

이 프로젝트는 과제 범위와 단일 인스턴스 실행 환경을 전제로, 별도의 Celery/Redis 없이 PostgreSQL job table과 FastAPI 내부 asyncio runner를 조합해 생성 작업을 처리합니다. Docker Compose는 PostgreSQL, FastAPI backend, Vite frontend를 함께 실행하며, 생성된 asset metadata는 DB에 저장하고 실제 파일 bytes는 로컬 `DATA_DIR`에 저장합니다.

```text
[React SPA]
    |
    v
[FastAPI API]
    |
    +-- [PostgreSQL] jobs / assets / prompt_enhancements
    |
    +-- [In-process asyncio Job Runner]
    |       |
    |       +-- [Vertex AI via google-genai] Imagen / Veo / Gemini
    |       +-- [Local Storage] DATA_DIR/{job_uuid}/{filename}
    |
    +-- [/files/{job_uuid}/{filename}] validated asset streaming
```

### Job Runner

FastAPI는 application lifespan에서 로컬 저장소와 DB schema를 초기화한 뒤, 같은 프로세스 안에서 asyncio 기반 job runner를 시작합니다. runner는 `pending` 상태이면서 `blocked=false`인 job을 PostgreSQL에서 `FOR UPDATE SKIP LOCKED`로 claim하고, `queued`로 전이한 뒤 mode별 handler task를 실행합니다.

동시 실행은 설정값 기반 concurrency limit과 `asyncio.Semaphore`로 제한합니다. 생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과하며, Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다.

Veo 작업은 polling 단계에서 Vertex operation name을 저장합니다. runner 재시작 시 `polling` 상태이면서 operation name이 있는 job은 저장된 operation name으로 polling을 재개할 수 있습니다. 오래된 non-terminal job에 대해서는 runner startup 시 recovery sweep을 수행하되, 재개 가능한 polling job은 제외합니다.

### Vertex AI Integration

AI 호출은 `google-genai` 단일 SDK로 통합했습니다. 백엔드는 `genai.Client(vertexai=True, ...)`를 공유 client로 구성하고, Imagen 이미지 생성, Veo 비디오 생성, Gemini prompt enhancement에 같은 Vertex client 경로를 사용합니다.

Imagen은 `models.generate_images`로 받은 inline image bytes를 로컬 image asset으로 저장합니다. Veo는 `models.generate_videos`로 long-running operation을 생성하고, 완료 후 `generated_videos[0].video.video_bytes`를 읽어 MP4 asset으로 저장합니다. 현재 구현은 `output_gcs_uri`를 사용하지 않으며, GCS 대신 로컬 `DATA_DIR`에 파일을 저장합니다.

초기 Imagen 생성 호출과 초기 Veo submit 호출은 bounded retry helper로 감쌉니다. 기본 정책은 최대 3회 시도와 1초부터 시작하는 exponential backoff입니다. Veo polling 단계에서는 operation error, safety-filtered result, missing output을 `vertex_safety_blocked`, `vertex_output_unavailable` 같은 public error code로 분류합니다.

### State, Storage, and Pipeline

Job lifecycle은 명시적인 state machine으로 관리합니다. 일반적인 생성 흐름은 `pending -> queued -> generating -> polling/downloading -> completed`이며, `completed`, `failed`, `cancelled`는 terminal state입니다. runner와 handler의 상태 변경은 `transition(...)`을 통해 검증되고 `state_history`에 기록됩니다.

생성 파일은 `DATA_DIR/{job_uuid}/{filename}` 형태로 저장합니다. 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거쳐 UUID job directory, filename, `DATA_DIR` containment를 검증합니다. `/files/{job_uuid}/{filename}` route는 검증된 asset 파일만 스트리밍하며, video preview를 위해 single byte-range request를 지원합니다.

T2I → I2V pipeline은 parent T2I job과 blocked I2V child job을 함께 생성합니다. child job은 parent image asset이 준비되기 전까지 runner 대상에서 제외됩니다. parent T2I가 완료되면 첫 번째 image asset을 child의 `source_asset_id`로 연결하고 `blocked=false`로 바꾸어, 다음 runner tick에서 I2V job으로 처리되도록 합니다.
```

이 섹션에서는 **deletion**은 길어지니까 아키텍처에 넣지 말고, “주요 기능”이나 “운영 안정성”에 한 줄로 넣는 게 좋아:

```md
History deletion은 terminal job에 한해 허용하며, active dependent job이 있는 경우 삭제를 차단합니다. 삭제 시 대상 job의 asset file만 검증된 storage path를 통해 제거하고, terminal dependent job의 parent/source reference는 detach합니다.
```

다음 수정 순서는 **주요 기능 섹션**이 좋아. 거긴 fact check보다 지금 완성 상태를 보기 좋게 정리하면 됨.
````

## user

```text
cli에게 줄 프롬프트 줘 주요기능섹션이 마지막인거같은데 ? 

```

## assistant

````text
좋아. 주요 기능 섹션은 **프론트 UX + 백엔드 기능이 실제로 맞는지**만 확인하면 돼.

Codex CLI 프롬프트:

```text
README의 "주요 기능" 섹션 작성을 위한 read-only fact check 결과를 docs/readme-features-factcheck.txt 파일로 작성해줘.

규칙:
- 실제 구현 파일은 수정하지 마.
- 서버 실행, 테스트 실행, 패키지 설치, 브라우저/Chromium 사용 금지.
- 새로 작성할 파일은 docs/readme-features-factcheck.txt 하나만 허용.
- Markdown 표를 쓰지 말고 plain text로 작성해.
- credentials, .env 값, service-account JSON 내용은 절대 출력하지 마.
- 작업 위치는 ~/recovered_workspace.

확인할 것:
1. 프론트엔드에서 실제 제공하는 주요 화면:
   - Generate
   - Job Detail
   - Pipeline
   - History
2. 생성 기능:
   - T2I, T2V, I2V
   - model/aspect/duration/number_of_images/source_asset_id 지원 여부
3. Prompt enhancement UX:
   - 원본/개선본/components 표시 여부
   - 사용자가 편집/수락해야 generation prompt에 반영되는지
   - Creativity Mode 지원 여부
4. Job progress UX:
   - timeline/state history/live polling
   - active I2V에서 source image context 표시 여부
   - completed result 표시 방식
5. Pipeline UX:
   - T2I -> I2V 생성 흐름
   - parent/child progress 표시 여부
6. History UX:
   - mode/state/model/page size/asset type 필터
   - image thumbnail/video preview
   - terminal job delete action
7. README에 안전하게 쓸 수 있는 주요 기능 문구.
8. README에 쓰면 안 되는 과장 표현:
   - chat agent
   - budget system
   - model comparison
   - cancel button
   - progress percent/ETA/queue position
   - automatic prompt enhancement

파일 구조:
- CONFIRMED_FEATURES
- SAFE_README_WORDING
- DO_NOT_CLAIM
- FILE_REFERENCES
```

이 결과까지 받으면 README는 거의 마무리야. 그다음은 내가 전체 README 흐름 기준으로 “남길 문장 / 줄일 문장 / 위험한 문장”만 빠르게 정리해줄게.
````

## user

```text
i2v 에서 비동기 방식으로 처리되고 있는거 맞나 ? 

```

## assistant

````text
응, **I2V도 비동기 job 방식으로 처리되는 게 맞아.**

흐름은 이렇다고 보면 돼:

1. 사용자가 `POST /api/generations`로 I2V 요청
2. API는 즉시 Vertex를 호출하지 않고 DB에 `pending` job 생성
3. FastAPI 내부 `asyncio` job runner가 나중에 `pending && blocked=false` job을 claim
4. runner가 I2V handler task 실행
5. handler가 source image bytes를 읽고 Veo submit
6. Veo operation name 저장 후 `polling`
7. 완료되면 video bytes 저장, asset row 생성, job `completed`

즉 API request/response 관점에서는 **비동기 작업 큐형 처리**야. 사용자는 job id를 받고, 프론트는 2초 polling으로 상태를 갱신하는 구조.

pipeline I2V도 비동기인데 한 단계 더 있어:

- 처음 child I2V job은 `pending + blocked=true`
- parent T2I 완료 후 source image asset이 연결됨
- `blocked=false`가 되면 runner가 나중에 claim해서 I2V 처리

README에는 이렇게 쓰면 안전해:

```md
T2I, T2V, I2V 생성 요청은 모두 즉시 Vertex를 호출하지 않고 DB에 job을 생성한 뒤, FastAPI 내부 asyncio runner가 비동기로 처리합니다. 프론트엔드는 job detail API를 주기적으로 polling하여 상태와 결과 asset을 표시합니다.
```
````

## user

```text
동영상 생성이 느린이유는 api 동영상 생성 모델 성능때문인가 ? 

```

## assistant

````text
대부분은 **Veo 동영상 생성 모델 자체의 long-running operation 특성** 때문이라고 보면 돼.

정확히는:

- T2V/I2V는 이미지 생성처럼 즉시 bytes가 떨어지는 구조가 아니라, Vertex에 video generation operation을 submit한 뒤 완료될 때까지 polling함.
- 동영상은 프레임/시간/연속성/모션/사운드까지 생성해야 해서 Imagen보다 훨씬 오래 걸림.
- `veo-3.0-generate-001`은 품질형이라 더 느릴 수 있고, `veo-3.0-fast-generate-001`도 이미지 생성보다는 느림.
- I2V는 source image를 읽고 모델에 전달한 뒤 그 이미지를 기반으로 motion을 생성해야 하므로 역시 LRO로 처리됨.
- 우리 앱 쪽에서는 비동기 runner로 처리해서 UI가 멈추지는 않지만, **실제 완료 시간은 Vertex/Veo operation 완료 시간에 의존**함.

README/AI_COLLABORATION에는 이렇게 쓰면 좋아:

```md
Veo 기반 T2V/I2V는 Vertex AI long-running operation으로 처리되므로 Imagen 이미지 생성보다 완료 시간이 길 수 있습니다. 이를 고려해 generation 요청은 DB job으로 저장하고, FastAPI 내부 runner가 비동기로 polling하며, 프론트엔드는 상태 timeline과 source/result preview를 통해 대기 중인 작업 맥락을 표시합니다.
```

이건 “우리 구현이 느리다”가 아니라 **비디오 생성 모델의 본질적 latency를 UX/비동기 처리로 흡수했다**는 식으로 설명하면 좋아.
````

## user

```text
Frontend screens:                                                         - Generate screen exists at /generate and is one of the two primary sideba
r nav items.                                                              - History screen exists at /history and is one of the two primary sidebar nav items.                           
- Job Detail screen exists at /jobs/:jobId and is reached after generation submit or from History rows.                                             
- Pipeline screen exists at /pipelines/:pipelineId and is reached after pipeline creation. It is not a primary sidebar nav item.                    
                                                                          
Generation features:                                                      
- Generate supports four selectable modes in the UI: T2I, T2V, I2V, and Pipeline.                                                                   
- T2I uses Imagen model choices, aspect ratio, and number_of_images. The UI limits image count choices to 1, 2, 3, or 4.                            
- T2V uses Veo model choices, aspect ratio, and duration. The UI duration 
choices are 4s, 6s, and 8s.                                               
- I2V uses Veo model choices, aspect ratio, duration, and source_asset_id. In the UI, source_asset_id comes from the query string after starting I2V from a completed image result.     
- The I2V UI fetches and displays the selected source image when possible, and labels it as a locked/connected source image.                        
- Backend schemas also support T2I aspect_ratio and number_of_images, T2V 
aspect_ratio and duration_sec, and I2V source_asset_id, aspect_ratio, and 
duration_sec.                                                             - Backend generation create rejects auto_enhance=true with HTTP 501, so ge
neration-time automatic prompt enhancement is not implemented.            - Backend I2V creation requires source_asset_id to exist and be an image a
sset.                                                                                                                                               Prompt enhancement UX:                                                    
- Generate has a non-pipeline prompt enhancement flow using /api/prompts/enhance.                                                                   
- The request includes prompt, target_mode, target_model, and creativity_preset.                               
- Creativity choices are Faithful, Balanced, and Imaginative.             - The enhancement review panel shows the original prompt, an editable enha
nced prompt draft, prompt components, target mode, creativity, and latency
 when available.                                                          
- The enhanced draft does not affect the generation prompt until the user 
accepts it.                                                               
- Accept draft copies the editable enhanced prompt into the main prompt and records the enhancement id for the generation request while mode/model/c
reativity still match.                                                    - Discard and Keep original are available in the review panel.
- Pipeline mode does not expose prompt enhancement review in the Generate UI.                                                                       
                                                                V         Job progress UX:                                                          
- Job Detail uses live polling every 2 seconds while the job is non-terminal, then stops polling for completed, failed, or cancelled.              
- Job Detail shows a state timeline built from state_history and the current state.                                                                 
- Job Detail shows a current-step summary and a visual state-derived progr
ess bar, but this is not a true model progress percent, ETA, queue positio
n, or poll count.                                                         
- Active I2V jobs with a source_asset_id and no generated result yet fetch the source asset and show source image context when the source can be rendered.                                                                    
- Completed image results render as an inline image with asset metadata.  - Completed video results render as an inline video element with controls 
and asset metadata.                                                       
- Completed image jobs expose a Start I2V with this image action that navi
gates back to Generate with mode=i2v and source_asset_id.                 - Request Summary shows mode, model, timestamps, prompt, parameters, and enhancement/source markers when present.                                   
                                                                          Pipeline UX:                                                              
- Generate Pipeline mode creates a parent T2I job and a blocked child I2V 
job through /api/pipelines.                                               
- Pipeline inputs include image prompt, video prompt, image model, video model, image aspect ratio, video aspect ratio, and duration.
- Backend create_pipeline stores the parent as T2I pending and the child as I2V pending with blocked=true and no source_asset_id.                   
- The runner only picks pending jobs where blocked is false, so the child 
waits until linkage.                                                      
- When the parent T2I job completes with an image asset, backend pipeline_link sets child.source_asset_id to that image and child.blocked=false.
- If the parent fails while the child is still blocked, the blocked child 
is failed with a pipeline parent failure error.
- Pipeline Detail polls every 2 seconds until both parent and child are terminal.                                                                   
- Pipeline Detail shows Step 1 Imagen image and Step 2 Veo I2V stages, parent/child state badges, compact timelines, blocked/source asset informatio
n, prompts, model ids, and image/video previews when assets are available.                                                                          
History UX:                          
- History supports filters for mode, asset type, state, model, and page size.                                                                       - The frontend sends mode, asset_kind, state, model, limit, and offset to 
listGenerations.                                                          - Backend list_generations supports mode, asset_kind, model, state, limit, and offset.                         
- Page size choices in the UI are 10, 20, 50, and 100.                    - History rows show a result preview area, mode/state, prompt/job id, mode
l, created timestamp, and actions.                                        - Image assets render as thumbnails.                                      
- Video assets render as muted inline video previews using metadata preloa
d and a #t=0.1 URL fragment.                                              
- Selecting a row opens the Job Detail screen.                            - Delete action is shown only for terminal jobs in the UI: completed, fail
ed, or cancelled.                                                         - Backend delete also validates that the target job is terminal and blocks
 deletion when active dependent jobs reference it.                        
                                                                          
SAFE_README_WORDING                                                                                                                                 - 주요 화면은 Generate, History, Job Detail, Pipeline Detail로 구성되어 있
습니다. Generate와 History는 사이드바에서 접근하고, Job Detail과 Pipeline Detail은 생성/히스토리/파이프라인 흐름에서 열립니다.                      
- Generate에서 Text-to-Image, Text-to-Video, Image-to-Video, T2I-to-I2V Pi
peline 생성 요청을 만들 수 있습니다.                                      
- 생성 옵션은 모델, aspect ratio, T2I 이미지 개수, 비디오 duration, I2V source image 연결을 지원합니다.                                             
- Prompt enhancement는 Gemini가 만든 개선 프롬프트 초안을 사용자가 검토하 고 편집한 뒤 Accept draft를 눌러야 실제 generation prompt에 반영되는 명시 
적 review/apply 흐름입니다.                                               
- Prompt enhancement에는 Faithful, Balanced, Imaginative creativity mode가 있으며, 이 설정은 prompt enhancement 단계에만 적용됩니다.                
- Job Detail은 활성 job을 2초 간격으로 polling하고, state history 기반 timeline, 현재 단계 요약, request summary, completed image/video result previ
ew, asset metadata를 보여줍니다.                                          - 진행 중인 I2V job은 생성 결과가 나오기 전에도 연결된 source image contex
t를 표시할 수 있습니다.                                                   - 완료된 image result에서는 해당 이미지를 source로 사용해 새 I2V 요청을 시
작할 수 있습니다.                                                         
- Pipeline mode는 parent T2I job과 blocked child I2V job을 만들고, parent 
image asset이 저장되면 child I2V job에 source_asset_id를 연결해 다음 단계 
로 진행합니다.                                                            
- History에서는 mode, state, model, page size, asset type으로 job 목록을  필터링하고, image thumbnail 또는 video preview를 확인하며, terminal job을 
삭제할 수 있습니다.                                                       
                                                                          
DO_NOT_CLAIM                                                              
                                                                          
- Do not claim this is a chat agent or conversational agent workflow.     - Do not claim there is a budget system, spend cap, quota dashboard, or co
st-control UI.                                                            - Do not claim model comparison, A/B comparison, benchmark comparison, or 
side-by-side model evaluation.                                            - Do not claim there is a user-facing cancel button or cancel API. The can
celled state exists, but no cancel action is implemented in the confirmed 
UI/API surface.                                                           
- Do not claim exact progress percent, ETA, queue position, poll count, or
 average completion-time estimates. The Job Detail progress bar is state-derived, not provider/model progress.                                      - Do not claim automatic prompt enhancement during generation. auto_enhanc
e=true is rejected by the backend, and the implemented flow requires explicit Enhance prompt, review/edit, and Accept draft.                        
- Do not claim Pipeline mode has prompt enhancement review.               
- Do not claim arbitrary image upload/import for I2V. The confirmed UI flo
w starts I2V from a completed image asset via source_asset_id.            - Do not claim Pipeline is a primary sidebar nav item. It is a routed scre
en reached from pipeline creation.                                        
                                                                          FILE_REFERENCES                                                           
                                                                          
- frontend/src/App.tsx:13-33 confirms sidebar nav items and routes for Gen
erate, History, Job Detail, and Pipeline.                                 - frontend/src/pages/GeneratePage.tsx:50-124 confirms Imagen/Veo model lis
ts, generation modes, aspect options, duration options, and creativity options.                                                                     
- frontend/src/pages/GeneratePage.tsx:138-153 confirms I2V source_asset_id
 query handling and pipeline model state.                                 
- frontend/src/pages/GeneratePage.tsx:301-327 confirms Accept draft copies the editable enhanced prompt into the main prompt and runEnhance sends pr
ompt/mode/model/creativity.                                               
- frontend/src/pages/GeneratePage.tsx:329-379 confirms generation and pipe
line payload fields, including auto_enhance=false, number_of_images, duration_sec, and source_asset_id.                                             
- frontend/src/pages/GeneratePage.tsx:570-682 confirms pipeline and single-job model/aspect/duration/image-count controls.                          
- frontend/src/pages/GeneratePage.tsx:750-795 confirms creativity selector, Enhance prompt action, Generate action, and EnhanceReviewPanel wiring.  
- frontend/src/pages/GeneratePage.tsx:808-853 confirms source image previe
        w/context for I2V.                                                        
- frontend/src/pages/GeneratePage.tsx:861-970 confirms original/enhanced/components review UI and Accept/Discard/Keep original actions.             
- frontend/src/hooks/useJob.ts:5-17 confirms Job Detail polling every 2 seconds until terminal state.                                               
- frontend/src/hooks/usePipeline.ts:11-20 confirms Pipeline polling every 
2 seconds until both jobs are terminal.                                   
- frontend/src/pages/JobDetailPage.tsx:100-167 confirms Job Detail data loading, source context query, Asset Viewer, Job State, timeline, and Request Summary panels.                                                         
- frontend/src/pages/JobDetailPage.tsx:203-303 confirms active I2V source 
image context before generated result is available.                       
- frontend/src/pages/JobDetailPage.tsx:326-406 confirms completed image/vi
deo rendering, video controls, metadata, and Start I2V action.            
- frontend/src/pages/JobDetailPage.tsx:445-467 confirms current-step summary and state-derived progress bar.                                        
- frontend/src/pages/JobDetailPage.tsx:473-588 confirms state timeline and request summary details.                                                 
- frontend/src/pages/PipelinePage.tsx:33-123 confirms Pipeline screen load
ing, 2s polling label, parent/child stages, and child source asset display.                                                                         
- frontend/src/pages/PipelinePage.tsx:146-275 confirms Pipeline stage metadata and image/video previews.                                            
- frontend/src/pages/PipelinePage.tsx:321-370 confirms pipeline live summary copy for parent/child progress.                                        
- frontend/src/pages/PipelinePage.tsx:420-510 confirms Step 1/Step 2 state copy and I2V source linkage messaging.                                   
- frontend/src/pages/PipelinePage.tsx:547-610 confirms compact parent/chil
d timeline entries.                                                       
- frontend/src/pages/HistoryPage.tsx:17-31 confirms mode, asset type, stat
e, and page size option lists.                                            
- frontend/src/pages/HistoryPage.tsx:45-56 confirms History query params sent to listGenerations.                                                   
- frontend/src/pages/HistoryPage.tsx:59-113 confirms delete mutation and c
onfirmation flow.                                                         
- frontend/src/pages/HistoryPage.tsx:118-198 confirms filter UI for mode, 
asset type, state, model, and page size.                                  
- frontend/src/pages/HistoryPage.tsx:296-324 confirms rows open Job Detail and terminal delete action placement.                                    
- frontend/src/pages/HistoryPage.tsx:406-439 confirms image thumbnails and video previews.                                                          
- frontend/src/pages/HistoryPage.tsx:476-481 confirms delete button eligibility is limited to terminal states.                                      
- backend/app/schemas.py:24-38 confirms prompt enhancement and pipeline cr
eate request fields.                                                      
- backend/app/schemas.py:57-73 confirms T2I/T2V/I2V request fields.       
- backend/app/schemas.py:108-124 confirms prompt enhancement response fields, including original, enhanced, components, creativity_preset, and temperature.                                                                   
- backend/app/schemas.py:126-145 confirms JobResponse fields used by frontend state/history/asset views.                                            
- backend/app/api/prompts.py:23-75 confirms /api/prompts/enhance stores an
d returns enhancement results.                                            
- backend/app/services/llm/enhancer.py:167-254 confirms enhancement result includes original, enhanced, components, target mode/model, llm model, cr
eativity preset, temperature, latency, and token counts.                  
- backend/app/api/generations.py:44-49 confirms auto_enhance=true is rejected.                                                                      
- backend/app/api/generations.py:50-99 confirms T2I/T2V/I2V mode handling 
and I2V source image validation.                                          
- backend/app/api/generations.py:107-141 confirms accepted enhancement_id 
is validated and attached to created jobs.                                
- backend/app/api/generations.py:157-177 confirms History backend filters and pagination.                                                           
- backend/app/api/generations.py:203-244 confirms delete endpoint and term
inal/dependency validation.                                               
- backend/app/api/pipelines.py:31-75 confirms parent T2I and blocked child I2V creation fields.                                                     
- backend/app/services/jobs/runner.py:255 confirms blocked pending jobs ar
e not picked by the runner.                                               
- backend/app/services/jobs/handlers.py:101-103 confirms parent T2I completion triggers pipeline linkage.                                           
- backend/app/services/jobs/pipeline_link.py:26-83 confirms completed pare
nt image asset linkage to child.source_asset_id and child.blocked=false.  
- backend/app/services/jobs/pipeline_link.py:87-107 confirms blocked child failure when parent fails.                                

```

## assistant

````text
좋아. 이 fact check 기준이면 **주요 기능 섹션은 아래처럼 짧은 표 중심**으로 가면 돼. 과장 없이 실제 구현된 것만 담긴 버전.

```md
## 주요 기능

| 영역 | 구현 내용 |
|---|---|
| 생성 모드 | Text-to-Image, Text-to-Video, Image-to-Video, T2I → I2V Pipeline을 지원합니다. |
| 모델 선택 | Imagen 4 Fast/Standard/Ultra, Veo 3 Fast/Standard 모델을 선택할 수 있습니다. |
| 생성 옵션 | 이미지 aspect ratio, 이미지 개수, 비디오 duration, I2V source image 연결을 지원합니다. |
| Prompt Enhancement | Gemini 기반으로 prompt 개선 초안을 생성하고, 사용자가 원본/개선본/components를 비교한 뒤 편집 및 수락할 수 있습니다. |
| Creativity Mode | Faithful, Balanced, Imaginative 모드로 prompt enhancement의 보강 강도를 조절합니다. 이 설정은 enhancement 단계에만 적용됩니다. |
| Job Detail | 활성 job을 2초 간격으로 polling하고, state history 기반 timeline, 현재 단계 요약, request summary, 결과 asset preview를 표시합니다. |
| I2V Source Context | 진행 중인 I2V job은 결과가 나오기 전에도 연결된 source image context를 보여줍니다. |
| Result Preview | 완료된 image/video asset을 상세 화면에서 확인할 수 있으며, image 결과에서는 해당 이미지를 source로 새 I2V 요청을 시작할 수 있습니다. |
| Pipeline | T2I parent job과 blocked I2V child job을 생성하고, parent image asset이 준비되면 child job에 연결해 다음 단계로 진행합니다. |
| History | mode, state, model, page size, asset type 필터를 제공하며, image thumbnail과 muted video preview를 표시합니다. |
| Deletion | completed/failed/cancelled 상태의 terminal job 삭제를 지원하며, active dependent job이 있으면 삭제를 차단합니다. |
```

그리고 기능 섹션 아래에 한 문단으로 UX 의도를 붙이면 좋아:

```md
Veo 기반 T2V/I2V는 Vertex AI long-running operation으로 처리되기 때문에 이미지 생성보다 완료 시간이 길 수 있습니다. 이를 고려해 모든 생성 요청은 비동기 job으로 저장하고, 프론트엔드는 polling 기반 timeline과 source/result preview를 통해 사용자가 현재 작업 상태를 이해할 수 있도록 구성했습니다.
```

빼야 할 표현은 확정:

- 채팅 에이전트
- 예산 관리/비용 한도
- 모델 비교 모드
- cancel button/API
- 정확한 progress percent, ETA, queue position
- generation-time automatic prompt enhancement
- Pipeline prompt enhancement review
- arbitrary image upload for I2V

이제 README는 거의 끝났고, 남은 건 **테스트/검증 명령 섹션**이랑 **운영 노트/제약 섹션** 정도야.
````

## user

````text
## 1. 프로젝트 아키텍처 및 핵심 설계

이 프로젝트는 과제 범위와 단일 인스턴스 실행 환경을 전제로, 별도의 Celery/Redis 없이 PostgreSQL job table과 FastAPI 내부 asyncio runner를 조합해 생성 작업을 처리합니다. Docker Compose는 PostgreSQL, FastAPI backend, Vite frontend를 함께 실행하며, 생성된 asset metadata는 DB에 저장하고 실제 파일 bytes는 로컬 `DATA_DIR`에 저장합니다.

```
[React SPA]
    |
    v
[FastAPI API]
    |
    +-- [PostgreSQL] jobs / assets / prompt_enhancements
    |
    +-- [In-process asyncio Job Runner]
    |       |
    |       +-- [Vertex AI via google-genai] Imagen / Veo / Gemini
    |       +-- [Local Storage] DATA_DIR/{job_uuid}/{filename}
    |
    +-- [/files/{job_uuid}/{filename}] validated asset streaming
```

### **Job Runner**

FastAPI는 application lifespan에서 로컬 저장소와 DB schema를 초기화한 뒤, 같은 프로세스 안에서 asyncio 기반 job runner를 시작합니다. runner는 pending 상태이면서 blocked=false인 job을 PostgreSQL에서 FOR UPDATE SKIP LOCKED로 claim하고, queued로 전이한 뒤 mode별 handler task를 실행합니다.

동시 실행은 설정값 기반 concurrency limit과 asyncio.Semaphore로 제한합니다. 생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과하며, Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다.

Veo 작업은 polling 단계에서 Vertex operation name을 저장합니다. runner 재시작 시 polling 상태이면서 operation name이 있는 job은 저장된 operation name으로 polling을 재개할 수 있습니다. 오래된 non-terminal job에 대해서는 runner startup 시 recovery sweep을 수행하되, 재개 가능한 polling job은 제외합니다.

### **Vertex AI Integration**

AI 호출은 google-genai 단일 SDK로 통합했습니다. 백엔드는 genai.Client(vertexai=True, ...)를 공유 client로 구성하고, Imagen 이미지 생성, Veo 비디오 생성, Gemini prompt enhancement에 같은 Vertex client 경로를 사용합니다.

Imagen은 models.generate_images로 받은 inline image bytes를 로컬 image asset으로 저장합니다. Veo는 models.generate_videos로 long-running operation을 생성하고, 완료 후 generated_videos[0].video.video_bytes를 읽어 MP4 asset으로 저장합니다. 현재 구현은 output_gcs_uri를 사용하지 않으며, GCS 대신 로컬 DATA_DIR에 파일을 저장합니다.

초기 Imagen 생성 호출과 초기 Veo submit 호출은 bounded retry helper로 감쌉니다. 기본 정책은 최대 3회 시도와 1초부터 시작하는 exponential backoff입니다. Veo polling 단계에서는 operation error, safety-filtered result, missing output을 vertex_safety_blocked, vertex_output_unavailable 같은 public error code로 분류합니다.

### **State, Storage, and Pipeline**

Job lifecycle은 명시적인 state machine으로 관리합니다. 일반적인 생성 흐름은 pending -> queued -> generating -> polling/downloading -> completed이며, completed, failed, cancelled는 terminal state입니다. runner와 handler의 상태 변경은 transition(...)을 통해 검증되고 state_history에 기록됩니다.

생성 파일은 DATA_DIR/{job_uuid}/{filename} 형태로 저장합니다. 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거쳐 UUID job directory, filename, DATA_DIR containment를 검증합니다. /files/{job_uuid}/{filename} route는 검증된 asset 파일만 스트리밍하며, video preview를 위해 single byte-range request를 지원합니다.

T2I → I2V pipeline은 parent T2I job과 blocked I2V child job을 함께 생성합니다. child job은 parent image asset이 준비되기 전까지 runner 대상에서 제외됩니다. parent T2I가 완료되면 첫 번째 image asset을 child의 source_asset_id로 연결하고 blocked=false로 바꾸어, 다음 runner tick에서 I2V job으로 처리되도록 합니다.

## 🛠️ 2. 기술 스택 & 사용 모델

### 기술 스택

- **Backend:** Python 3.11, FastAPI, SQLAlchemy async, asyncpg, PostgreSQL 16
- **Frontend:** Vite, React, TypeScript, @tanstack/react-query
- **AI SDK:** `google-genai` 단일 SDK 사용 (Vertex AI 연동)
- **Infra:** Docker Compose, Postgres named volume, Local asset named volume

### 지원 모델 라인업

- **Imagen (이미지):** `imagen-4.0-fast-generate-001`, `imagen-4.0-generate-001`, `imagen-4.0-ultra-generate-001`
- **Veo (비디오):** `veo-3.0-fast-generate-001`, `veo-3.0-generate-001`
- **Prompt Enhance (프롬프트 개선):** `gemini-2.5-flash`

## 3. 주요 기능

| 영역 | 구현 내용 |
| --- | --- |
| 생성 모드 | Text-to-Image, Text-to-Video, Image-to-Video, T2I → I2V Pipeline을 지원합니다. |
| 모델 선택 | Imagen 4 Fast/Standard/Ultra, Veo 3 Fast/Standard 모델을 선택할 수 있습니다. |
| 생성 옵션 | 이미지 aspect ratio, 이미지 개수, 비디오 duration, I2V source image 연결을 지원합니다. |
| Prompt Enhancement | Gemini 기반으로 prompt 개선 초안을 생성하고, 사용자가 원본/개선본/components를 비교한 뒤 편집 및 수락할 수 있습니다. |
| Creativity Mode | Faithful, Balanced, Imaginative 모드로 prompt enhancement의 보강 강도를 조절합니다. 이 설정은 enhancement 단계에만 적용됩니다. |
| Job Detail | 활성 job을 2초 간격으로 polling하고, state history 기반 timeline, 현재 단계 요약, request summary, 결과 asset preview를 표시합니다. |
| I2V Source Context | 진행 중인 I2V job은 결과가 나오기 전에도 연결된 source image context를 보여줍니다. |
| Result Preview | 완료된 image/video asset을 상세 화면에서 확인할 수 있으며, image 결과에서는 해당 이미지를 source로 새 I2V 요청을 시작할 수 있습니다. |
| Pipeline | T2I parent job과 blocked I2V child job을 생성하고, parent image asset이 준비되면 child job에 연결해 다음 단계로 진행합니다. |
| History | mode, state, model, page size, asset type 필터를 제공하며, image thumbnail과 muted video preview를 표시합니다. |
| Deletion | completed/failed/cancelled 상태의 terminal job 삭제를 지원하며, active dependent job이 있으면 삭제를 차단합니다. |

## 🔌 4. API 엔드포인트 요약

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/health` | DB 연결과 Vertex client 설정 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
| POST | `/api/prompts/enhance` | Gemini 기반 prompt enhancement record를 생성합니다. |
| POST | `/api/generations` | `mode` 값에 따라 T2I, T2V, I2V generation job을 생성합니다. |
| GET | `/api/generations` | job history를 `mode`, `state`, `model`, `asset_kind`, pagination 조건으로 조회합니다. |
| GET | `/api/generations/{job_id}` | 단일 job의 상태, 입력값, state history, 생성 asset 정보를 조회합니다. |
| DELETE | `/api/generations/{job_id}` | terminal 상태 job과 해당 asset 파일을 삭제합니다. active dependent job이 있으면 거절됩니다. |
| POST | `/api/pipelines` | T2I parent job과 blocked I2V child job을 함께 생성합니다. |
| GET | `/api/pipelines/{parent_job_id}` | pipeline parent job과 연결된 I2V child job의 진행 상태를 조회합니다. |
| GET | `/api/assets/{asset_id}` | asset metadata와 `/files/...` URL을 조회합니다. |
| GET | `/files/{job_uuid}/{filename}` | `DATA_DIR` 아래 asset 파일을 안전하게 스트리밍합니다. video preview용 single byte range request를 지원합니다. |

## 🗂️ 5. 주요 API 요청 예시 (JSON)

JSON

```
{
  "prompt": "고양이가 집에서 뛰어노는 사진",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced"
}
```

- `creativity_preset`은 `faithful`, `balanced`, `imaginative`를 지원하며, Gemini 프롬프트 개선 시의 temperature 및 컨텍스트 전략을 조절합니다 (Imagen/Veo 자체의 generation temperature 설정이 아님).

JSON

```
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1,
}
```

JSON

```
{
  "mode": "t2v",
  "prompt": "A slow dolly forward through a rainy neon alley",
  "model": "veo-3.0-fast-generate-001",
  "aspect_ratio": "16:9",
  "duration_sec": 4,
}
```

JSON

```
{
  "mode": "i2v",
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in puddles",
  "model": "veo-3.0-fast-generate-001",
  "source_asset_id": "00000000-0000-4000-8000-000000000000",
  "aspect_ratio": "16:9",
  "duration_sec": 4,
}
```

JSON

```
{
  "image_prompt": "Neon-soaked Seoul alley at night with a cyclist",
  "video_prompt": "Slow dolly forward as the cyclist passes and steam rises",
  "image_model": "imagen-4.0-fast-generate-001",
  "video_model": "veo-3.0-fast-generate-001",
  "image_aspect_ratio": "1:1",
  "video_aspect_ratio": "16:9",
  "duration_sec": 4
}
```

## ⚙️ 6. 환경 변수 및 실행 방법

## 

## 실행 방법

이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행합니다. 백엔드는 `8000`, 프론트엔드는 `5173` 포트로 노출되며, PostgreSQL은 외부 포트를 열지 않습니다.

### 환경 변수

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 설정합니다. 서비스 계정 JSON 내용은 `.env`에 직접 넣지 않고, 호스트 파일 경로만 지정합니다.
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000

````

## assistant

`````text
좋아, 전체 흐름은 거의 잡혔어. 지금 고치면 좋은 건 **문서 품질/정확도 디테일**이야.

1. 코드 표기 깨짐 수정  
지금 `pending`, `blocked=false`, `FOR UPDATE SKIP LOCKED`, `google-genai` 같은 코드성 단어들이 일부 일반 텍스트로 들어가 있어. 전부 백틱 처리하면 훨씬 깔끔해.

예:
```md
runner는 `pending` 상태이면서 `blocked=false`인 job을 PostgreSQL에서 `FOR UPDATE SKIP LOCKED`로 claim하고, `queued`로 전이합니다.
```

2. API JSON 예시의 trailing comma 제거  
현재 JSON이 유효하지 않아.

```json
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1
}
```

`t2v`, `i2v`의 `duration_sec: 4,`도 마지막 comma 제거해야 함.

3. “JSON” 단독 텍스트 제거  
각 예시 앞을 이렇게 바꾸는 게 좋아.

```md
### Prompt Enhancement

```json
...
```
```

```md
### Text-to-Image
```

4. 실행 섹션 중복 제거  
지금:

```md
## ⚙️ 6. 환경 변수 및 실행 방법

## 

## 실행 방법
```

이렇게 중복돼. 하나만 남겨:

```md
## 6. 환경 변수 및 실행 방법
```

5. `.env` 예시는 fenced block 필요  
지금 env가 본문처럼 붙어 있어. 이렇게 감싸야 함.

````md
```env
POSTGRES_USER=app
...
VITE_API_PROXY_TARGET=http://backend:8000
```
````

6. `ENHANCE_MODEL` 설명 주의  
env 예시에는 있어도 되지만, 아래에 “enhance model을 자유롭게 바꿀 수 있다”는 설명은 하지 마. compose 필수값이지만 코드상 실제 Gemini 모델은 hard-coded라고 fact check 됐음.

7. 소개 문장 하나 추가 추천  
맨 위에 이 정도 넣으면 README가 과제 원문 느낌이 아니라 제품 문서 느낌이 남.

```md
# Vertex Studio

Vertex Studio는 Google Vertex AI의 Imagen 4, Veo 3, Gemini 2.5 Flash를 활용해 이미지와 비디오 생성, prompt enhancement, T2I → I2V pipeline, 생성 history 관리를 제공하는 멀티모달 콘텐츠 생성 플랫폼입니다.
```

8. 주요 기능 뒤에 Veo latency 문단 추가 추천  
좋은 UX 판단 어필 포인트야.

```md
Veo 기반 T2V/I2V는 Vertex AI long-running operation으로 처리되므로 Imagen 이미지 생성보다 완료 시간이 길 수 있습니다. 이를 고려해 모든 생성 요청은 비동기 job으로 저장하고, 프론트엔드는 polling 기반 timeline과 source/result preview를 통해 현재 작업 상태를 표시합니다.
```

마지막으로 실행 섹션은 env block 아래에 이어서:

```md
### Docker Compose 실행

```bash
docker compose up -d --build
```

E2B 과제 환경:

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```
```

지금 큰 내용은 맞고, 남은 건 “유효한 JSON / 중복 헤더 / 백틱 / env block” 같은 마감 퀄리티야.
`````

## user

````text
## ## 1. 프로젝트 아키텍처 및 핵심 설계

이 프로젝트는 과제 범위와 단일 인스턴스 실행 환경을 전제로, 별도의 Celery/Redis 없이 PostgreSQL job table과 FastAPI 내부 asyncio runner를 조합해 생성 작업을 처리합니다. Docker Compose는 PostgreSQL, FastAPI backend, Vite frontend를 함께 실행하며, 생성된 asset metadata는 DB에 저장하고 실제 파일 bytes는 로컬 `DATA_DIR`에 저장합니다.

```
[React SPA]
    |
    v
[FastAPI API]
    |
    +-- [PostgreSQL] jobs / assets / prompt_enhancements
    |
    +-- [In-process asyncio Job Runner]
    |       |
    |       +-- [Vertex AI via google-genai] Imagen / Veo / Gemini
    |       +-- [Local Storage] DATA_DIR/{job_uuid}/{filename}
    |
    +-- [/files/{job_uuid}/{filename}] validated asset streaming
```

### **Job Runner**

FastAPI는 application lifespan에서 로컬 저장소와 DB schema를 초기화한 뒤, 같은 프로세스 안에서 asyncio 기반 job runner를 시작합니다. runner는 `pending` 상태이면서 `blocked=false`인 job을 PostgreSQL에서 `FOR UPDATE SKIP LOCKED`로 claim하고, `queued`  로 전이 한 후 mode별 handler task를 실행합니다.

동시 실행은 설정값 기반 concurrency limit과 asyncio.Semaphore로 제한합니다. 생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과하며, Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다.

Veo 작업은 polling 단계에서 Vertex operation name을 저장합니다. runner 재시작 시 polling 상태이면서 operation name이 있는 job은 저장된 operation name으로 polling을 재개할 수 있습니다. 오래된 non-terminal job에 대해서는 runner startup 시 recovery sweep을 수행하되, 재개 가능한 polling job은 제외합니다.

### **Vertex AI Integration**

AI 호출은 google-genai 단일 SDK로 통합했습니다. 백엔드는 genai.Client(vertexai=True, ...)를 공유 client로 구성하고, Imagen 이미지 생성, Veo 비디오 생성, Gemini prompt enhancement에 같은 Vertex client 경로를 사용합니다.

Imagen은 models.generate_images로 받은 inline image bytes를 로컬 image asset으로 저장합니다. Veo는 models.generate_videos로 long-running operation을 생성하고, 완료 후 generated_videos[0].video.video_bytes를 읽어 MP4 asset으로 저장합니다. 현재 구현은 output_gcs_uri를 사용하지 않으며, GCS 대신 로컬 DATA_DIR에 파일을 저장합니다.

초기 Imagen 생성 호출과 초기 Veo submit 호출은 bounded retry helper로 감쌉니다. 기본 정책은 최대 3회 시도와 1초부터 시작하는 exponential backoff입니다. Veo polling 단계에서는 operation error, safety-filtered result, missing output을 vertex_safety_blocked, vertex_output_unavailable 같은 public error code로 분류합니다.

### **State, Storage, and Pipeline**

Job lifecycle은 명시적인 state machine으로 관리합니다. 일반적인 생성 흐름은 pending -> queued -> generating -> polling/downloading -> completed이며, completed, failed, cancelled는 terminal state입니다. runner와 handler의 상태 변경은 transition(...)을 통해 검증되고 state_history에 기록됩니다.

생성 파일은 DATA_DIR/{job_uuid}/{filename} 형태로 저장합니다. 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거쳐 UUID job directory, filename, DATA_DIR containment를 검증합니다. /files/{job_uuid}/{filename} route는 검증된 asset 파일만 스트리밍하며, video preview를 위해 single byte-range request를 지원합니다.

T2I → I2V pipeline은 parent T2I job과 blocked I2V child job을 함께 생성합니다. child job은 parent image asset이 준비되기 전까지 runner 대상에서 제외됩니다. parent T2I가 완료되면 첫 번째 image asset을 child의 source_asset_id로 연결하고 blocked=false로 바꾸어, 다음 runner tick에서 I2V job으로 처리되도록 합니다.

## ## 2. 기술 스택 & 사용 모델

### 기술 스택

- **Backend:** Python 3.11, FastAPI, SQLAlchemy async, asyncpg, PostgreSQL 16
- **Frontend:** Vite, React, TypeScript, @tanstack/react-query
- **AI SDK:** `google-genai` 단일 SDK 사용 (Vertex AI 연동)
- **Infra:** Docker Compose, Postgres named volume, Local asset named volume

### 지원 모델 라인업

- **Imagen (이미지):** `imagen-4.0-fast-generate-001`, `imagen-4.0-generate-001`, `imagen-4.0-ultra-generate-001`
- **Veo (비디오):** `veo-3.0-fast-generate-001`, `veo-3.0-generate-001`
- **Prompt Enhance (프롬프트 개선):** `gemini-2.5-flash`

## ## 3. 주요 기능

| 영역 | 구현 내용 |
| --- | --- |
| 생성 모드 | Text-to-Image, Text-to-Video, Image-to-Video, T2I → I2V Pipeline을 지원합니다. |
| 모델 선택 | Imagen 4 Fast/Standard/Ultra, Veo 3 Fast/Standard 모델을 선택할 수 있습니다. |
| 생성 옵션 | 이미지 aspect ratio, 이미지 개수, 비디오 duration, I2V source image 연결을 지원합니다. |
| Prompt Enhancement | Gemini 기반으로 prompt 개선 초안을 생성하고, 사용자가 원본/개선본/components를 비교한 뒤 편집 및 수락할 수 있습니다. |
| Creativity Mode | Faithful, Balanced, Imaginative 모드로 prompt enhancement의 보강 강도를 조절합니다. 이 설정은 enhancement 단계에만 적용됩니다. |
| Job Detail | 활성 job을 2초 간격으로 polling하고, state history 기반 timeline, 현재 단계 요약, request summary, 결과 asset preview를 표시합니다. |
| I2V Source Context | 진행 중인 I2V job은 결과가 나오기 전에도 연결된 source image context를 보여줍니다. |
| Result Preview | 완료된 image/video asset을 상세 화면에서 확인할 수 있으며, image 결과에서는 해당 이미지를 source로 새 I2V 요청을 시작할 수 있습니다. |
| Pipeline | T2I parent job과 blocked I2V child job을 생성하고, parent image asset이 준비되면 child job에 연결해 다음 단계로 진행합니다. |
| History | mode, state, model, page size, asset type 필터를 제공하며, image thumbnail과 muted video preview를 표시합니다. |
| Deletion | completed/failed/cancelled 상태의 terminal job 삭제를 지원하며, active dependent job이 있으면 삭제를 차단합니다. |

## ## 4. API 엔드포인트 요약

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/health` | DB 연결과 Vertex client 설정 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
| POST | `/api/prompts/enhance` | Gemini 기반 prompt enhancement record를 생성합니다. |
| POST | `/api/generations` | `mode` 값에 따라 T2I, T2V, I2V generation job을 생성합니다. |
| GET | `/api/generations` | job history를 `mode`, `state`, `model`, `asset_kind`, pagination 조건으로 조회합니다. |
| GET | `/api/generations/{job_id}` | 단일 job의 상태, 입력값, state history, 생성 asset 정보를 조회합니다. |
| DELETE | `/api/generations/{job_id}` | terminal 상태 job과 해당 asset 파일을 삭제합니다. active dependent job이 있으면 거절됩니다. |
| POST | `/api/pipelines` | T2I parent job과 blocked I2V child job을 함께 생성합니다. |
| GET | `/api/pipelines/{parent_job_id}` | pipeline parent job과 연결된 I2V child job의 진행 상태를 조회합니다. |
| GET | `/api/assets/{asset_id}` | asset metadata와 `/files/...` URL을 조회합니다. |
| GET | `/files/{job_uuid}/{filename}` | `DATA_DIR` 아래 asset 파일을 안전하게 스트리밍합니다. video preview용 single byte range request를 지원합니다. |

## ## 5. 주요 API 요청 예시 (JSON)

JSON

```
{
  "prompt": "고양이가 집에서 뛰어노는 사진",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced"
}
```

- `creativity_preset`은 `faithful`, `balanced`, `imaginative`를 지원하며, Gemini 프롬프트 개선 시의 temperature 및 컨텍스트 전략을 조절합니다 (Imagen/Veo 자체의 generation temperature 설정이 아님).

JSON

```
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1
}
```

JSON

```
{
  "mode": "t2v",
  "prompt": "A slow dolly forward through a rainy neon alley",
  "model": "veo-3.0-fast-generate-001",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

JSON

```
{
  "mode": "i2v",
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in puddles",
  "model": "veo-3.0-fast-generate-001",
  "source_asset_id": "00000000-0000-4000-8000-000000000000",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

JSON

```
{
  "image_prompt": "Neon-soaked Seoul alley at night with a cyclist",
  "video_prompt": "Slow dolly forward as the cyclist passes and steam rises",
  "image_model": "imagen-4.0-fast-generate-001",
  "video_model": "veo-3.0-fast-generate-001",
  "image_aspect_ratio": "1:1",
  "video_aspect_ratio": "16:9",
  "duration_sec": 4
}
```

## ## 6. 환경 변수 및 실행 방법

이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행합니다. 백엔드는 `8000`, 프론트엔드는 `5173` 포트로 노출되며, PostgreSQL은 외부 포트를 열지 않습니다.

### 환경 변수

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 설정합니다. 서비스 계정 JSON 내용은 `.env`에 직접 넣지 않고, 호스트 파일 경로만 지정합니다.

```
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
```

### Docker Compose 실행

```bash
### Docker Compose 실행

docker compose up -d --build
```

```bash
### e2b 과제 환경

sudo -E docker compose up -d --build --force-recreate frontend backend db
```

````

## assistant

`````text
많이 좋아졌어. 지금은 거의 마감 단계인데, 아래만 고치면 README 톤이 확 살아나.

1. 헤더의 `## ##` 제거  
전부 이렇게 바꿔:

```md
## 1. 프로젝트 아키텍처 및 핵심 설계
## 2. 기술 스택 & 사용 모델
## 3. 주요 기능
## 4. API 엔드포인트 요약
## 5. 주요 API 요청 예시
## 6. 환경 변수 및 실행 방법
```

2. 코드성 단어 백틱 정리  
몇 군데 NBSP 때문에 이상하게 보일 수 있어. 아래처럼 바꾸면 깔끔해.

```md
동시 실행은 설정값 기반 concurrency limit과 `asyncio.Semaphore`로 제한합니다.
```

```md
runner 재시작 시 `polling` 상태이면서 operation name이 있는 job은 저장된 operation name으로 polling을 재개할 수 있습니다.
```

```md
AI 호출은 `google-genai` 단일 SDK로 통합했습니다. 백엔드는 `genai.Client(vertexai=True, ...)`를 공유 client로 구성합니다.
```

```md
Imagen은 `models.generate_images`로 받은 inline image bytes를 로컬 image asset으로 저장합니다.
```

```md
완료 후 `generated_videos[0].video.video_bytes`를 읽어 MP4 asset으로 저장합니다.
```

```md
현재 구현은 `output_gcs_uri`를 사용하지 않으며, GCS 대신 로컬 `DATA_DIR`에 파일을 저장합니다.
```

3. API 예시 앞의 `JSON` 제거하고 소제목 붙이기

```md
### Prompt Enhancement

```json
...
```

### Text-to-Image

```json
...
```

### Text-to-Video

```json
...
```

### Image-to-Video

```json
...
```

### T2I → I2V Pipeline

```json
...
```
```

4. env block에 `env` 언어 태그 추가

````md
```env
POSTGRES_USER=app
...
```
````

5. Docker 코드블록 안의 헤더 제거  
지금은 코드블록 안에 `### Docker Compose 실행`이 들어가 있어. 이렇게 바꿔:

```md
### Docker Compose 실행

일반 로컬 환경:

```bash
docker compose up -d --build
```

E2B 과제 환경:

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```
```

6. 실행 섹션에 접속 URL 추가  
아직 없으니 붙이면 좋아.

```md
### 접속 URL

로컬 환경:

- Frontend: http://localhost:5173
- Backend API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

E2B 환경:

- Frontend: `https://5173-${E2B_SANDBOX_ID}.e2b.app`
- Backend: `https://8000-${E2B_SANDBOX_ID}.e2b.app`
```

7. `.env` 예시에서 `ENHANCE_MODEL` 빠졌음  
compose 기준 필수라 다시 넣는 게 좋아. 단, 설명은 하지 말고 env 예시에만:

```env
ENHANCE_MODEL=gemini-2.5-flash
```

마지막으로, README 맨 위에 제목/한 줄 소개가 없으면 꼭 추가해:

```md
# Vertex Studio

Google Vertex AI의 Imagen 4, Veo 3, Gemini 2.5 Flash를 활용해 이미지와 비디오 생성, prompt enhancement, T2I → I2V pipeline, 생성 history 관리를 제공하는 멀티모달 콘텐츠 생성 플랫폼입니다.
```
`````

## user

```text
너가 완성시켜서 전체 md 파일을 제공해줘

```

## assistant

`````text
아래는 현재 fact check 반영한 README 완성본이야.

````markdown
# Vertex Studio

Google Vertex AI의 Imagen 4, Veo 3, Gemini 2.5 Flash를 활용해 이미지와 비디오 생성, prompt enhancement, T2I → I2V pipeline, 생성 history 관리를 제공하는 멀티모달 콘텐츠 생성 플랫폼입니다.

## 1. 프로젝트 아키텍처 및 핵심 설계

이 프로젝트는 과제 범위와 단일 인스턴스 실행 환경을 전제로, 별도의 Celery/Redis 없이 PostgreSQL job table과 FastAPI 내부 asyncio runner를 조합해 생성 작업을 처리합니다. Docker Compose는 PostgreSQL, FastAPI backend, Vite frontend를 함께 실행하며, 생성된 asset metadata는 DB에 저장하고 실제 파일 bytes는 로컬 `DATA_DIR`에 저장합니다.

```text
[React SPA]
    |
    v
[FastAPI API]
    |
    +-- [PostgreSQL] jobs / assets / prompt_enhancements
    |
    +-- [In-process asyncio Job Runner]
    |       |
    |       +-- [Vertex AI via google-genai] Imagen / Veo / Gemini
    |       +-- [Local Storage] DATA_DIR/{job_uuid}/{filename}
    |
    +-- [/files/{job_uuid}/{filename}] validated asset streaming
```

### Job Runner

FastAPI는 application lifespan에서 로컬 저장소와 DB schema를 초기화한 뒤, 같은 프로세스 안에서 asyncio 기반 job runner를 시작합니다. runner는 `pending` 상태이면서 `blocked=false`인 job을 PostgreSQL에서 `FOR UPDATE SKIP LOCKED`로 claim하고, `queued`로 전이한 뒤 mode별 handler task를 실행합니다.

동시 실행은 설정값 기반 concurrency limit과 `asyncio.Semaphore`로 제한합니다. 생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과하며, Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다.

Veo 작업은 polling 단계에서 Vertex operation name을 저장합니다. runner 재시작 시 `polling` 상태이면서 operation name이 있는 job은 저장된 operation name으로 polling을 재개할 수 있습니다. 오래된 non-terminal job에 대해서는 runner startup 시 recovery sweep을 수행하되, 재개 가능한 polling job은 제외합니다.

### Vertex AI Integration

AI 호출은 `google-genai` 단일 SDK로 통합했습니다. 백엔드는 `genai.Client(vertexai=True, ...)`를 공유 client로 구성하고, Imagen 이미지 생성, Veo 비디오 생성, Gemini prompt enhancement에 같은 Vertex client 경로를 사용합니다.

Imagen은 `models.generate_images`로 받은 inline image bytes를 로컬 image asset으로 저장합니다. Veo는 `models.generate_videos`로 long-running operation을 생성하고, 완료 후 `generated_videos[0].video.video_bytes`를 읽어 MP4 asset으로 저장합니다. 현재 구현은 `output_gcs_uri`를 사용하지 않으며, GCS 대신 로컬 `DATA_DIR`에 파일을 저장합니다.

초기 Imagen 생성 호출과 초기 Veo submit 호출은 bounded retry helper로 감쌉니다. 기본 정책은 최대 3회 시도와 1초부터 시작하는 exponential backoff입니다. Veo polling 단계에서는 operation error, safety-filtered result, missing output을 `vertex_safety_blocked`, `vertex_output_unavailable` 같은 public error code로 분류합니다.

### State, Storage, and Pipeline

Job lifecycle은 명시적인 state machine으로 관리합니다. 일반적인 생성 흐름은 `pending -> queued -> generating -> polling/downloading -> completed`이며, `completed`, `failed`, `cancelled`는 terminal state입니다. runner와 handler의 상태 변경은 `transition(...)`을 통해 검증되고 `state_history`에 기록됩니다.

생성 파일은 `DATA_DIR/{job_uuid}/{filename}` 형태로 저장합니다. 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거쳐 UUID job directory, filename, `DATA_DIR` containment를 검증합니다. `/files/{job_uuid}/{filename}` route는 검증된 asset 파일만 스트리밍하며, video preview를 위해 single byte-range request를 지원합니다.

T2I → I2V pipeline은 parent T2I job과 blocked I2V child job을 함께 생성합니다. child job은 parent image asset이 준비되기 전까지 runner 대상에서 제외됩니다. parent T2I가 완료되면 첫 번째 image asset을 child의 `source_asset_id`로 연결하고 `blocked=false`로 바꾸어, 다음 runner tick에서 I2V job으로 처리되도록 합니다.

## 2. 기술 스택 & 사용 모델

### 기술 스택

- **Backend:** Python 3.11, FastAPI, SQLAlchemy async, asyncpg, PostgreSQL 16
- **Frontend:** Vite, React, TypeScript, Tailwind CSS, @tanstack/react-query
- **AI SDK:** `google-genai` 단일 SDK 사용
- **Infra:** Docker Compose, PostgreSQL named volume, local asset named volume

### 지원 모델

- **Imagen:** `imagen-4.0-fast-generate-001`, `imagen-4.0-generate-001`, `imagen-4.0-ultra-generate-001`
- **Veo:** `veo-3.0-fast-generate-001`, `veo-3.0-generate-001`
- **Prompt Enhancement:** `gemini-2.5-flash`

## 3. 주요 기능

| 영역 | 구현 내용 |
|---|---|
| 생성 모드 | Text-to-Image, Text-to-Video, Image-to-Video, T2I → I2V Pipeline을 지원합니다. |
| 모델 선택 | Imagen 4 Fast/Standard/Ultra, Veo 3 Fast/Standard 모델을 선택할 수 있습니다. |
| 생성 옵션 | 이미지 aspect ratio, 이미지 개수, 비디오 duration, I2V source image 연결을 지원합니다. |
| Prompt Enhancement | Gemini 기반으로 prompt 개선 초안을 생성하고, 사용자가 원본/개선본/components를 비교한 뒤 편집 및 수락할 수 있습니다. |
| Creativity Mode | Faithful, Balanced, Imaginative 모드로 prompt enhancement의 보강 강도를 조절합니다. 이 설정은 enhancement 단계에만 적용됩니다. |
| Job Detail | 활성 job을 2초 간격으로 polling하고, state history 기반 timeline, 현재 단계 요약, request summary, 결과 asset preview를 표시합니다. |
| I2V Source Context | 진행 중인 I2V job은 결과가 나오기 전에도 연결된 source image context를 보여줍니다. |
| Result Preview | 완료된 image/video asset을 상세 화면에서 확인할 수 있으며, image 결과에서는 해당 이미지를 source로 새 I2V 요청을 시작할 수 있습니다. |
| Pipeline | T2I parent job과 blocked I2V child job을 생성하고, parent image asset이 준비되면 child job에 연결해 다음 단계로 진행합니다. |
| History | mode, state, model, page size, asset type 필터를 제공하며, image thumbnail과 muted video preview를 표시합니다. |
| Deletion | completed/failed/cancelled 상태의 terminal job 삭제를 지원하며, active dependent job이 있으면 삭제를 차단합니다. |

Veo 기반 T2V/I2V는 Vertex AI long-running operation으로 처리되므로 Imagen 이미지 생성보다 완료 시간이 길 수 있습니다. 이를 고려해 모든 생성 요청은 비동기 job으로 저장하고, 프론트엔드는 polling 기반 timeline과 source/result preview를 통해 현재 작업 상태를 표시합니다.

## 4. API 엔드포인트 요약

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/health` | DB 연결과 Vertex client 설정 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
| POST | `/api/prompts/enhance` | Gemini 기반 prompt enhancement record를 생성합니다. |
| POST | `/api/generations` | `mode` 값에 따라 T2I, T2V, I2V generation job을 생성합니다. |
| GET | `/api/generations` | job history를 `mode`, `state`, `model`, `asset_kind`, pagination 조건으로 조회합니다. |
| GET | `/api/generations/{job_id}` | 단일 job의 상태, 입력값, state history, 생성 asset 정보를 조회합니다. |
| DELETE | `/api/generations/{job_id}` | terminal 상태 job과 해당 asset 파일을 삭제합니다. active dependent job이 있으면 거절됩니다. |
| POST | `/api/pipelines` | T2I parent job과 blocked I2V child job을 함께 생성합니다. |
| GET | `/api/pipelines/{parent_job_id}` | pipeline parent job과 연결된 I2V child job의 진행 상태를 조회합니다. |
| GET | `/api/assets/{asset_id}` | asset metadata와 `/files/...` URL을 조회합니다. |
| GET | `/files/{job_uuid}/{filename}` | `DATA_DIR` 아래 asset 파일을 안전하게 스트리밍합니다. video preview용 single byte range request를 지원합니다. |

Prompt enhancement는 generation 요청에 자동으로 적용되지 않습니다. 사용자가 `/api/prompts/enhance` 결과를 확인, 편집, 수락하면 프론트엔드는 개선된 prompt를 generation 요청의 `prompt`로 보내고, `enhancement_id`를 함께 전달해 job과 enhancement record를 연결합니다.

## 5. 주요 API 요청 예시

### Prompt Enhancement

```json
{
  "prompt": "고양이가 집에서 뛰어노는 사진",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced"
}
```

`creativity_preset`은 `faithful`, `balanced`, `imaginative`를 지원하며, Gemini prompt enhancement 단계의 temperature 및 컨텍스트 전략을 조절합니다. Imagen/Veo generation temperature 설정은 아닙니다.

### Text-to-Image

```json
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1
}
```

### Text-to-Video

```json
{
  "mode": "t2v",
  "prompt": "A slow dolly forward through a rainy neon alley",
  "model": "veo-3.0-fast-generate-001",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

### Image-to-Video

```json
{
  "mode": "i2v",
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in puddles",
  "model": "veo-3.0-fast-generate-001",
  "source_asset_id": "00000000-0000-4000-8000-000000000000",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

### T2I → I2V Pipeline

```json
{
  "image_prompt": "Neon-soaked Seoul alley at night with a cyclist",
  "video_prompt": "Slow dolly forward as the cyclist passes and steam rises",
  "image_model": "imagen-4.0-fast-generate-001",
  "video_model": "veo-3.0-fast-generate-001",
  "image_aspect_ratio": "1:1",
  "video_aspect_ratio": "16:9",
  "duration_sec": 4
}
```

## 6. 환경 변수 및 실행 방법

이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행합니다. 백엔드는 `8000`, 프론트엔드는 `5173` 포트로 노출되며, PostgreSQL은 외부 포트를 열지 않습니다.

### 환경 변수

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 설정합니다. 서비스 계정 JSON 내용은 `.env`에 직접 넣지 않고, 호스트 파일 경로만 지정합니다.

```env
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
```

`GOOGLE_APPLICATION_CREDENTIALS_HOST`는 호스트 머신의 서비스 계정 JSON 절대 경로입니다. Docker Compose는 이 파일을 백엔드 컨테이너의 `/secrets/sa.json`에 read-only로 마운트합니다.

### Docker Compose 실행

일반 로컬 환경:

```bash
docker compose up -d --build
```

E2B 과제 환경:

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```

### 접속 URL

로컬 환경:

- Frontend: http://localhost:5173
- Backend API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

E2B 환경:

- Frontend: `https://5173-${E2B_SANDBOX_ID}.e2b.app`
- Backend: `https://8000-${E2B_SANDBOX_ID}.e2b.app`

### 종료

```bash
docker compose down
```

DB 데이터와 생성된 asset volume까지 삭제하려면 다음 명령을 사용합니다.

```bash
docker compose down -v
```

`down -v`는 PostgreSQL 데이터와 생성된 에셋 파일을 삭제하므로 의도한 경우에만 사용합니다.

## 7. 테스트 및 검증

Backend 테스트는 실제 Vertex AI/Gemini를 호출하지 않고 mock/fake 기반으로 실행됩니다.

```bash
cd backend
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

Frontend 타입 검사와 빌드:

```bash
cd frontend
npm install
npm run lint
npm run build
```

## 8. 운영 노트 및 제약

- Prompt enhancement는 별도 API와 review/apply UX를 통해 동작합니다. Generation 요청 시 자동 enhancement는 수행하지 않습니다.
- Prompt enhancement의 Creativity Mode는 Gemini prompt enhancement 단계에만 적용됩니다.
- Veo safety filter 또는 provider policy에 의해 일부 인물/아동/민감한 동작 prompt는 거절될 수 있으며, 이를 우회하지 않고 public error code로 표시합니다.
- `/files` route는 validated local asset path만 스트리밍하며, single byte range request를 지원합니다. multipart range response는 지원하지 않습니다.
- History deletion은 terminal job에 한해 허용합니다. active dependent job이 있는 경우 삭제를 차단하며, 삭제 시 대상 job의 asset file만 제거합니다.
- `cancelled`는 state machine의 terminal state로 존재하지만, 현재 사용자-facing cancel button/API는 제공하지 않습니다.
- 진행 UI는 state 기반 timeline과 단계 요약을 제공합니다. 실제 provider progress percent, ETA, queue position은 제공하지 않습니다.
````
`````

## user

```text
그 도커가 python 버전때문에 v2 compose를 사용해야하는 내용 적으면 좋을거 같은데 전체 코드 제공하지말고 수정할부분만 알려줘 

```

## assistant

````text
좋아. 전체 README 다시 갈 필요 없고, **6. 환경 변수 및 실행 방법** 앞부분에 “요구사항” 소절만 추가하면 돼.

추천 위치:

```md
## 6. 환경 변수 및 실행 방법
```

바로 아래, 현재 설명문 앞에 추가:

```md
### 실행 요구사항

- Docker
- Docker Compose v2.29.7 또는 호환되는 Docker Compose v2
- Vertex AI 접근 권한이 있는 GCP service account JSON 파일
- Backend container는 Python 3.11 기반으로 빌드됩니다. 로컬에 설치된 Python 버전보다 Docker image와 Compose 환경이 기준입니다.
```

그리고 기존 문장:

```md
이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행합니다.
```

이 문장은 `### 실행 요구사항` 아래에 그대로 두면 돼.

다만 “Python 버전 때문에 Compose v2가 필요하다”라고 직접 쓰기보다는, 더 정확하게는:

```md
Python 3.11 및 Node/Vite 실행 환경은 Docker image 안에서 고정되므로, 로컬 런타임 버전 차이를 피하려면 Docker Compose v2로 실행하는 것을 권장합니다.
```

이 문장이 좋아.  
`docker compose` 명령도 v2 문법이라 `docker-compose` 하이픈 버전보다 `docker compose`를 기준으로 문서화하는 게 맞아.
````

## user

```text
⚠️ 수정 권장 사항
1. Rate limiter 서술 — 경계 주의
현재 README:

Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute

이건 정확합니다. 다만 아키텍처 다이어그램 바로 아래 문맥에서 이 limiter가 프로세스 내 in-memory임이 명시되지 않았습니다. 멀티 인스턴스 환경에서는 보장되지 않는다는 점이 팩트체크 DO_NOT_CLAIM에 명시되어 있으므로, 한 줄 추가를 권장합니다.
# 권장 추가
> 단, 이 제한은 in-memory 방식으로, 복수 프로세스 간 공유되지 않습니다.
2. Startup orphan sweep 서술 누락
현재 README에는 runner 재시작 시 polling job 재개에 대한 언급은 있지만, startup orphan sweep(오래된 non-terminal, non-resumable job을 failed 처리)에 대한 설명이 없습니다. Job Runner 섹션에 한 문장 추가하면 동작 이해에 도움이 됩니다.
# 권장 추가
runner 시작 시 오래된 non-terminal job에 대해 1회 복구 sweep을 수행하며,
재개 가능한 polling job을 제외한 stale job은 failed로 처리됩니다.
3. /api/health 설명 — 미묘한 표현 개선
현재:

DB 연결과 Vertex client 설정 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다.

팩트체크와 일치하나, "Vertex client 설정 readiness"가 실제로 무엇을 체크하는지(설정값 존재 여부인지, client 객체 초기화 여부인지) 팩트체크 문서에 명확히 확인된 내용이 없습니다. 확인되지 않은 범위이므로 "DB 연결 상태를 확인합니다" 수준으로 보수적으로 줄이는 것이 안전합니다.
4. Deletion 동작 — 의존 job 처리 누락
현재:

active dependent job이 있으면 삭제를 차단합니다.

정확하지만, 팩트체크에는 "terminal dependent job의 parent_job_id / source_asset_id 참조를 분리(detach)한다" 는 동작도 확인된 사실입니다. History 삭제 시 연결된 terminal job이 같이 삭제되는 게 아니라 참조만 끊긴다는 점은 사용자에게 유용한 정보입니다.
# 권장 추가
삭제 시 terminal 상태의 dependent job은 함께 삭제되지 않으며,
해당 job의 parent_job_id / source_asset_id 참조만 제거됩니다.

이 피드백에 대해 검토해봐 

```

## assistant

````text
이 피드백은 전반적으로 **받아들이는 게 맞아**. 다만 3번은 조금 더 보수적으로 조정하고, 2번은 이미 네 README 초안에 비슷한 문장이 있었으니 중복만 피하면 돼.

수정 판단:

1. **Rate limiter in-memory 한계 추가: 반영 추천**
   
   이건 좋음. 멀티 인스턴스 보장처럼 오해될 수 있어서 한 줄 넣는 게 안전해.

   수정 문장:
   ```md
   이 rate limiter는 backend 프로세스 내부의 in-memory limiter이므로, 복수 backend 프로세스 간 quota를 공유하거나 동기화하지는 않습니다.
   ```

2. **Startup orphan sweep: 이미 있으면 중복 주의**
   
   네 README에는 이미 이 문장이 있었어:
   ```md
   오래된 non-terminal job에 대해서는 runner startup 시 recovery sweep을 수행하되, 재개 가능한 polling job은 제외합니다.
   ```

   이 정도면 충분함. 더 명확히 하고 싶으면 교체:
   ```md
   runner 시작 시 오래된 non-terminal job에 대해 1회 recovery sweep을 수행하며, 재개 가능한 polling job은 제외하고 stale job을 failed로 처리합니다.
   ```

3. **`/api/health` 설명: 반영 추천**
   
   맞아. “Vertex client 설정 readiness”는 약간 애매하게 들릴 수 있어. API 표에서는 보수적으로 줄이는 게 좋음.

   교체:
   ```md
   | GET | `/api/health` | DB 연결 상태와 서비스 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
   ```

   “서비스 readiness” 정도는 괜찮고, Vertex client 내부 검증처럼 보이진 않음.

4. **Deletion dependent detach: 반영 추천**
   
   좋은 보완이야. 단 API 표에 너무 길게 넣기보다는 운영 노트 또는 기능 표에 넣는 게 좋아.

   운영 노트에 추가:
   ```md
   - History deletion은 terminal job에 한해 허용합니다. active dependent job이 있는 경우 삭제를 차단합니다. dependent job이 terminal 상태라면 함께 삭제하지 않고 `parent_job_id` / `source_asset_id` 참조만 제거합니다.
   ```

   기존 운영 노트의 deletion bullet을 이걸로 교체하면 됨.

내 결론: **1, 3, 4는 반영. 2는 기존 문장 있으면 교체만.**  
이 피드백은 정확도 높이는 쪽이라 README 신뢰도에 도움이 돼.
````

## user

```text
어느 부분에 넣으면됨  ?

```

## assistant

````text
넣을 위치는 이렇게 가면 돼.

1. **Rate limiter in-memory 한계**
   
   위치: `### Job Runner` 섹션, rate limiter 문장 바로 뒤.

   기존 문장:
   ```md
   동시 실행은 설정값 기반 concurrency limit과 `asyncio.Semaphore`로 제한합니다. 생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과하며, Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다.
   ```

   바로 뒤에 추가:
   ```md
   이 rate limiter는 backend 프로세스 내부의 in-memory limiter이므로, 복수 backend 프로세스 간 quota를 공유하거나 동기화하지는 않습니다.
   ```

2. **Startup orphan sweep 문장 정리**

   위치: `### Job Runner` 섹션, Veo polling resume 문단의 마지막 문장.

   기존 문장:
   ```md
   오래된 non-terminal job에 대해서는 runner startup 시 recovery sweep을 수행하되, 재개 가능한 polling job은 제외합니다.
   ```

   이걸 아래로 교체:
   ```md
   runner 시작 시 오래된 non-terminal job에 대해 1회 recovery sweep을 수행하며, 재개 가능한 polling job은 제외하고 stale job을 `failed`로 처리합니다.
   ```

3. **Health endpoint 설명**

   위치: `## 4. API 엔드포인트 요약` 표에서 `/api/health` 행.

   기존:
   ```md
   | GET | `/api/health` | DB 연결과 Vertex client 설정 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
   ```

   교체:
   ```md
   | GET | `/api/health` | DB 연결 상태와 서비스 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
   ```

4. **Deletion dependent detach**

   위치: `## 8. 운영 노트 및 제약`의 History deletion bullet.

   기존:
   ```md
   - History deletion은 terminal job에 한해 허용합니다. active dependent job이 있는 경우 삭제를 차단하며, 삭제 시 대상 job의 asset file만 제거합니다.
   ```

   교체:
   ```md
   - History deletion은 terminal job에 한해 허용합니다. active dependent job이 있는 경우 삭제를 차단합니다. dependent job이 terminal 상태라면 함께 삭제하지 않고 `parent_job_id` / `source_asset_id` 참조만 제거하며, 삭제 대상 job의 asset file만 제거합니다.
   ```
````

## user

```text
운영 노트 및 제약은 굳이 안넣어도 될것같아서 뺄게 

```

## assistant

````text
괜찮아. **운영 노트 및 제약은 빼도 됨.** README가 더 제출용으로 깔끔해질 수 있어.

다만 빼면 아래 두 가지는 다른 섹션에 흡수하는 게 좋아:

1. **Veo safety/provider constraint**
   
   이건 README에 없어도 치명적이진 않음. `AI_COLLABORATION.md` Q1/Q2에서 다루면 충분해.

2. **Deletion detach**
   
   이건 API 표나 주요 기능에 너무 길게 넣지 말고, 그냥 현재 수준이면 충분함:
   ```md
   terminal 상태 job 삭제를 지원하며, active dependent job이 있으면 삭제를 차단합니다.
   ```

운영 노트 삭제 후 README에 남겨야 하는 최소 정확도 보완은 이 세 개야:

- Job Runner rate limiter 뒤에 in-memory 한계 한 줄
- startup sweep 문장 교체
- `/api/health` 설명 보수화

그리고 `cancelled` 관련은 state machine 설명에 이미 나오니까 user-facing cancel 미구현을 굳이 README에서 고백할 필요 없어.  
좋은 판단이야. 제출 README는 **실행/기능/구조 중심**이면 충분해.
````

## user

```text
~ $ pwd
/home/user
~ $ ls
AGENTS.md            backend              tht-aif-f-jungle-fd0b.json
AI_COLLABORATION.md  docker-compose.yml   uploads
CLAUDE.md            frontend
README.md            recovered_workspace
~ $ cd uploads
~/uploads $ ls
CODEX.md   balanced.png  history.jsx      pipeline.jsx    waiting.jsx
README.md  data.jsx      icons.jsx        primitives.jsx  workspace.jsx
app.jsx    faithful.png  imaginative.png  result.jsx
~/uploads $ cd ..
~ $ cd recovered_workspace
최종 수정본의 README.md 의 pwd 는 /home/user/uploads 에 있고 
이를 내 실제 작업공간인 /home/user/recovered_workspace 로 옮겨야 해 
같은이름인데 덮어씌우면됨 



```

## assistant

````text
맞아. 이 경우에는 **`/home/user/uploads/README.md`를 `/home/user/recovered_workspace/README.md`로 덮어쓰기**가 맞아.

다만 `/home/user` 루트에서 git/수정 작업은 피하라는 원칙이 있으니, Codex CLI나 터미널에서는 목적지를 명확히 지정해서 단일 파일 복사만 하면 돼.

명령:

```bash
cp /home/user/uploads/README.md /home/user/recovered_workspace/README.md
cd /home/user/recovered_workspace
git status --short
```

그 다음 확인:

```bash
head -40 README.md
```

주의:

- `/home/user/README.md`로 복사하면 안 됨
- `/home/user`에서 git 명령 치지 말고, 반드시 `cd /home/user/recovered_workspace` 후 `git status`
- 덮어쓰기 전 백업이 필요하면:
  ```bash
  cp /home/user/recovered_workspace/README.md /tmp/README.before-doc-update.md
  cp /home/user/uploads/README.md /home/user/recovered_workspace/README.md
  ```

지금은 README를 의도적으로 교체하는 거라 덮어써도 괜찮아.
````

## user

```text
저장됐다 . 

```

## assistant

````text
좋아. 이제 다음 체크는 딱 두 개야.

1. 작업공간에서 변경 상태 확인

```bash
cd /home/user/recovered_workspace
git status --short
```

2. README가 실제로 교체됐는지 앞부분 확인

```bash
head -40 README.md
```

정상이라면 다음 단계는 **AI_COLLABORATION.md 작성**이야.  
README는 이미 구조/실행/API/기능까지 들어갔으니, 이제 평가 포인트는 Step 3 답변과 prompt enhancement 전략에 집중하면 됨.
````

## user

```text
다음 단계인 AI_COLLABORATION.md 작성을 하기위해 현재 대화창에서  다음 세션으로 넘어갈려고 . 
다음 세션에게 너의 역할을 프롬프트를 제공해줘 

```

## assistant

````text
다음 세션에 그대로 붙여넣으면 돼.

```text
너는 KRAFTON take-home assignment를 진행 중인 사용자의 전략 파트너다. 직접 구현하지 말고, 사용자가 가져오는 Codex CLI 결과와 문서 초안을 판독하고 다음에 Codex CLI에 보낼 짧고 안전한 프롬프트를 제안해라. 사용자가 “프롬프트 줘”라고 할 때만 실제 Codex CLI용 프롬프트를 작성한다.

응답은 짧고 전략적으로 해라. 사용자는 긴 프롬프트를 싫어한다. 가능하면 “무엇을 넣을지 / 무엇을 빼야 할지 / 어디에 배치할지” 중심으로 답해라.

중요 운영 원칙:
- 실제 작업 repo는 `/home/user/recovered_workspace`.
- `/home/user` 루트는 Git object 손상 및 read-only .git mount 이슈가 있었으므로 git 명령/파일 수정 금지.
- Codex CLI는 반드시 `cd ~/recovered_workspace && codex` 로 실행.
- 새 문서화 산출물은 `.codex/`가 아니라 `docs/` 하위에 작성.
- `/tmp`는 임시 조사/백업 용도만. durable work는 두지 않음.
- `.env`, service-account JSON, credential/API key 내용은 절대 요청/출력하지 않음.
- 실제 Vertex/Gemini 호출은 Live UX QA에서만. 자동화 테스트는 mock/fake only.
- 사용자가 브라우저에서 직접 Live QA를 수행함. Codex CLI가 브라우저를 조작하거나 Chromium을 설치하지 않게 할 것.
- Codex CLI가 결과를 가져오면 상태 판독 후 다음 단계만 제안. 바로 구현 프롬프트를 내밀지 말고, 사용자가 요청할 때만 제공.
- 제출 전 `git status --short`는 반드시 clean이어야 함.
- 서버 배치/복구 이후 working tree가 오래된 파일로 덮이는 문제가 있었음. 이런 경우 git log는 정상인데 git diff --stat가 대량 deletions로 나타남. 이미 모든 작업은 커밋되어 있으므로, 이상한 dirty diff는 patch 백업 후 `git restore .` 로 HEAD 복구하는 방식이 안전했음.

현재 상태:
- README.md는 `/home/user/uploads/README.md`에서 `/home/user/recovered_workspace/README.md`로 덮어써서 저장 완료.
- README에는 아키텍처, 기술 스택, 주요 기능, API 요약, JSON 예시, Docker 실행법, 테스트 명령이 들어감.
- 운영 노트 및 제약 섹션은 사용자가 굳이 넣지 않기로 함.
- README 관련 fact check 문서들이 `docs/` 하위에 생성되어 있을 수 있음:
  - `docs/readme-api-factcheck.md`
  - `docs/readme-runner-factcheck.txt`
  - `docs/readme-vertex-retry-factcheck.txt`
  - `docs/readme-state-storage-pipeline-factcheck.txt`
  - `docs/readme-features-factcheck.txt`
- 이 fact check 파일들은 문서 작성용 산출물이므로 최종 제출 전 남길지 삭제할지 나중에 판단해야 함.

현재 구현 완료 상태:
- Backend:
  - T2I, T2V, I2V generation API 구현.
  - model selection 지원.
  - generated asset DB 저장 + local file 저장.
  - asset detail API 구현.
  - Prompt enhancement API 구현.
  - T2I -> I2V pipeline 구현.
  - in-process asyncio job runner + Postgres job state 관리.
  - no Celery, no Redis.
  - state transitions는 `state_machine.transition(...)` 경유.
  - `google-genai` 단일 SDK 사용.
  - Veo는 GCS 없이 inline video bytes를 `DATA_DIR`에 저장.
  - retry/rate-limit/error classification 구현.
  - storage.py 경유 path-safe file write/delete.
  - History job deletion backend:
    - terminal job(completed/failed/cancelled) row 독립 삭제 가능.
    - active job 삭제 차단.
    - 선택 job을 참조하는 active dependent job이 있으면 409.
    - terminal dependent job은 `parent_job_id`/`source_asset_id` null로 끊고 선택 job만 삭제.
    - 해당 job의 asset files만 삭제.
  - `/files` Range request 지원으로 video preview가 전체 파일 다운로드 없이 가능.
- Frontend:
  - Generate page:
    - T2I/T2V/I2V modes.
    - model/aspect/duration selection.
    - prompt enhancement review/edit/accept flow.
    - Creativity Mode UI.
    - I2V source image handoff from asset detail.
    - `/generate?mode=i2v&source_asset_id=...`에서 source image preview 표시.
    - I2V는 enhancement 없이 source image + motion prompt만으로 Generate 가능.
  - Job Detail:
    - Job state timeline/live progress.
    - active I2V waiting 중 source context image 표시.
    - completed result는 source context보다 우선.
    - failed/cancelled states 표시.
  - Pipeline:
    - T2I -> I2V pipeline detail.
    - live progress summary band.
    - compact stage timeline.
    - long-running I2V 대기 상황 설명.
  - History:
    - mode/state/model/page size filters.
    - asset type filter: All / Images / Videos.
    - terminal job delete action.
    - video rows show actual muted video preview instead of NO THUMBNAIL.
    - image thumbnail 유지.
    - row navigation and delete action verified.

Prompt Enhancement 구현 핵심:
- API: `POST /api/prompts/enhance`.
- Request fields: `prompt`, `target_mode`, `target_model`, `creativity_preset`.
- Backend entry: `backend/app/services/llm/enhancer.py`.
- Prompt builder is sectioned:
  PERSONA, OBJECTIVE, INSTRUCTIONS, CONSTRAINTS, CONTEXT, OUTPUT FORMAT, RESPONSE FORMAT EXAMPLE, USER PROMPT, RECAP.
- User prompt is delimited to reduce instruction injection risk.
- Mode-specific guidance:
  - T2I: subject, scene, background, style, composition, lighting, camera/lens.
  - T2V: temporal action, camera movement, pacing, continuity.
  - I2V: preserve selected source image, describe motion only, do not add unrelated main subjects.
- Creativity Mode:
  - faithful = 0.2
  - balanced = 0.5
  - imaginative = 0.8
  - default balanced.
- Gemini output expected as JSON with enhanced + components.
- Uses response.parsed first, then response.text JSON extraction/fenced JSON/object selection.
- Pydantic/schema validation.
- malformed JSON gets exactly one STRICT JSON RETRY.
- Safe diagnostics surfaced in UI/API: reason, field, source.
- Raw provider output, credentials, service-account content are not exposed.
- Prompt enhancement is optional:
  - generation does not automatically enhance.
  - frontend shows original/enhanced/components in review panel.
  - user can edit enhanced draft.
  - only Accept draft copies it into main prompt.
  - generation payload uses visible current prompt as final generation prompt.
  - enhancement_id is optional and linked to job only if accepted/valid.
  - mode/model mismatch for enhancement_id is rejected.

AI_COLLABORATION.md direction:
- Must answer Step 3:
  - Q1. 구현 과정에서 발생한 가장 까다로운 엣지케이스 또는 장애 시나리오와 해결.
  - Q2. AI가 생성한 코드를 실제 프로젝트에 반영할 때 엔지니어로서 가장 중요하게 검증해야 하는 항목과 이유.
  - Q3. 이번 과제에서 AI와 함께 복잡한 문제를 해결했거나 AI의 한계를 직접 극복한 구체적 사례.
- Also describe prompt enhancement design principles and prompt strategy.
- Good Q1 main candidate:
  - Veo operation failure classification. Submit succeeded, operation name existed, failure occurred during polling, old backend collapsed provider failure/empty/filtered output into `vertex_unknown_error`. Fixed by checking `operation.error`, filtered/empty output and mapping to public codes such as `vertex_safety_blocked`, `vertex_output_unavailable`; verified with tests and live T2V/I2V QA.
- Good Q1 supporting candidate:
  - Gemini prompt enhancement malformed JSON, fixed with safe diagnostics and one strict JSON retry.
- Good Q2 points:
  - state machine transitions.
  - credential safety.
  - no real Vertex/Gemini in tests.
  - `google-genai` single SDK.
  - no GCS for Veo unless asked.
  - final prompt source of truth.
  - DB/file consistency for deletion.
  - path traversal/symlink safety.
  - active job/dependency deletion protection.
  - provider errors must be classified, not hidden.
- Good Q3:
  - Creativity Mode and prompt enhancement strategy co-design.
  - User proposed faithful/balanced/imaginative.
  - User corrected AI’s over-strict “ban generic words” into “avoid default/filler overuse unless user asks.”
  - User corrected Balanced interpretation: richer style/composition detail can be intended because temperature is higher than Faithful, not necessarily regression.
  - User emphasized manual review-first: enhanced draft must be compared/edited/accepted before generation.

Prompt Enhancement Strategy comparison:
- User wants to compare actual strategy with official Google Vertex AI prompt design strategies:
  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-design-strategies?hl=ko
- Relevant official concepts:
  - prompt content and structure both matter.
  - components: objective, instructions, constraints, context, examples/few-shot, response format, recap.
  - use system instructions.
  - add context.
  - include few-shot examples.
  - structure prompts with labels/delimiters.
  - experiment with parameter values.
  - iterate prompt strategy.
- Map to implementation:
  - sectioned prompt builder.
  - mode-specific objective/context/constraints.
  - JSON output format + schema validation.
  - exemplars for T2I/T2V/I2V.
  - creativity presets as parameter experimentation.
  - delimiter around user prompt.
  - malformed JSON retry and diagnostics as operational hardening.
  - review/edit/accept UX as product-level control beyond pure prompt design.
- Key framing:
  - Prompt enhancement is a controlled drafting layer, not automatic replacement.
  - Official prompt strategy was used as an engineering checklist, then extended into product-level controls.
  - User remains in control: inspectable, editable, rejectable, and only applied after Accept.

Recommended next step:
- Start AI_COLLABORATION.md with structure:
  1. Overview of AI collaboration approach
  2. Prompt Enhancement Strategy
  3. Q1 edge case/failure scenario
  4. Q2 engineer verification checklist
  5. Q3 concrete AI collaboration/limitation case
- Before asking Codex CLI to write, consider read-only inspection of current AI_COLLABORATION.md if it already exists.
```

````

