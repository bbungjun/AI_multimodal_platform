# krafton_assignment session 10

- Thread ID: 019e5887-ee95-7d70-a268-5f2704fc6109
- Source: C:\Users\PC\.codex\sessions\2026\05\24\rollout-2026-05-24T14-49-23-019e5887-ee95-7d70-a268-5f2704fc6109.jsonl
- Source SHA256: f033d4e25a223e53e6f023f5986acdcded3a1050402a457b2670c5219a3100d0
- Session timestamp: 2026-05-24 14:49:23 +09:00
- Exported at: 2026-05-26 18:46:02 +09:00
- Message count: 8
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
  <current_date>2026-05-24</current_date>
  <timezone>Asia/Seoul</timezone>
</environment_context>
````

## user

````text
당신은 KRAFTON take-home assignment를 진행 중인 프로젝트의 전략 파트너입니다. 직접 구현하지 말고, 내가 가져오는 Codex CLI 결과를 보고 다음에 보낼 짧고 안전한 프롬프트/작업 순서를 제안해주세요.

중요 운영 규칙:
- 실제 구현/코드 수정은 내가 Codex CLI에 시킵니다.
- 당신은 결과 판독, 위험 지점 식별, 다음 프롬프트 작성 역할입니다.
- 내가 “프롬프트 줘/제공해줘”라고 할 때만 Codex CLI용 프롬프트를 작성하세요.
- `.env`, service-account JSON, credential/API key 내용은 절대 요청/출력하지 마세요.
- 테스트에서 Vertex/Gemini/Imagen/Veo 실제 호출 금지. 실제 호출은 명시적 Live UX QA에서만.
- 실패하면 같은 실제 호출을 무작정 반복하지 말고 frontend error, backend log, job id/API 응답을 먼저 수집합니다.

현재 실제 작업 repo:
- 반드시 `/home/user/recovered_workspace`
- 기존 `/home/user` 루트는 Git object 손상 및 read-only `.git` mount가 있어 git 작업/파일 수정 금지
- 앞으로 bash/Codex CLI는 `cd ~/recovered_workspace` 후 실행해야 함
- `/tmp`는 임시 복구/조사용만, durable work는 두지 않음

Git 복구 이력:
- `/home/user/.git` object DB가 손상됨
  - missing commit/tree/blob 다수
  - `git diff --binary` segfault
  - `.git` mount가 read-only라 root repo로 수리/승격 불가
- verified workspace를 `/home/user/recovered_workspace`에 재구성
- baseline commit:
  - `7218f8d chore: recover verified assignment workspace`
- recovered workspace 문서화 commit:
  - `f6e2190 docs: document recovered workspace workflow`
- recovered workspace는 backend full pytest, frontend lint/build 통과했음
- `.env`, `tht-aif-f-jungle-fd0b.json`은 recovered workspace에 복사해서 Docker/Live QA에 사용 중. 내용 출력 금지.

Docker/Runtime:
- Docker compose v2 plugin이 사라져서 다시 설치함:
  - `sudo docker compose version` => v2.27.0
- 현재 Docker 작업은 `/home/user/recovered_workspace` 기준
- public frontend host:
  - `https://5173-i1uzm53vxizi1a8kuq8lq.e2b.app`
- Vite allowlist는 필요할 때:
  - `VITE_ALLOWED_HOSTS=5173-i1uzm53vxizi1a8kuq8lq.e2b.app sudo -E docker compose --env-file .env up -d --force-recreate frontend`
- backend logs:
  - `cd /home/user/recovered_workspace && sudo docker compose --env-file .env logs -f --tail=200 backend`

Core completed work / commits:
- `707bb57 fix: allow configured vite dev hosts`
- `1578f1e fix: avoid lazy loading generation assets`
- `85aef8d fix: pass source image to veo i2v requests`
- `878c481 fix: preserve pipeline parent child linkage`
- `dbce953 docs: record live i2v qa success`
- `1e061fb docs: record live t2v qa success`
- `6dadbd8 docs: record live pipeline qa success`
- `98eb109 docs: record prompt enhance and asset qa`
- `aea4407 feat: add asset detail endpoint`
- `1a95aee docs: record asset detail api qa`
- `fc8fac6 fix: harden prompt enhancement parsing`
- `6e0ef31 fix: accept fenced prompt enhancement json`
- `8c504eb fix: select valid enhancement json object`
- `8015d93 fix: allow longer prompt enhancement responses`
- `df8742c test: cover generation retry flows`
- Latest known pending/just-discussed work: additional retry edge coverage for 429 + multi-image T2I. See “Current immediate task” below.

Phase 14 Live UX QA completed:
1. T2I Imagen success
   - original earlier job: `1f4a269a-b3a7-427b-b4f2-0e40a102766a`
   - asset: `0e5cef25-b5b4-4750-b370-6afc371c14f9`
   - actual Imagen call, local storage, `/files` serving, frontend render succeeded
2. I2V initially failed
   - failed job: `4bdda5a1-da67-48a4-a631-42f1dfbf963e`
   - cause: handler passed `image_bytes=` but `veo.submit_video()` did not support image input
   - fixed by `85aef8d`
3. I2V success after fix
   - job: `2cdd6cd5-b0af-44bb-89bb-5bf9397fb4d8`
   - source asset: `2e32420e-cdb1-49a5-bd11-01c57c2e45b7`
   - video asset: `bd369437-d0ac-4c72-89ca-028b122b7c39`
   - model: `veo-3.0-fast-generate-001`
   - state completed, attempts 1, vertex_charged true
4. T2V success
   - job: `c1360ee4-fa20-4b06-ac8a-5566fda217e0`
   - asset: `fa88e6d4-533f-48af-8715-42fced82e369`
   - model: `veo-3.0-fast-generate-001`
   - duration 8s, video/mp4, vertex_charged true
5. Pipeline T2I -> I2V initial functional success but linkage gap
   - parent T2I: `6e3eb44f-6cf6-4c88-b4cd-c2458849f752`
   - child I2V: `9a312346-a237-441c-a4f8-e918c931d4db`
   - child source_asset_id pointed to parent image asset, but `parent_job_id` was empty and `/api/pipelines/{parent}` returned 404
   - fixed by `878c481`
6. Pipeline linkage retest success
   - parent: `764054f4-465a-4469-bf3c-514b557b9fdc`
   - parent image asset: `c080c6fd-c2fe-4deb-89de-fdd078f81eb8`
   - child: `cec5a245-d623-45ab-90d8-48d6b2cefc76`
   - child parent_job_id == parent
   - child video asset: `90f5a6ea-0416-4962-bade-a2c58eda2d87`
   - `/api/pipelines/{parent}` returned 200 with child
7. Recovered workspace pipeline smoke also succeeded:
   - parent T2I job: `223e7c67-c2f6-4d3b-b26f-bc56cd90cf84`
   - parent image asset: `87f6712f-cb2a-4b50-8a5a-7c2c639ada78`
   - child I2V job: `f3aebd58-c48d-417a-9576-ad23776a22b2`
   - child parent_job_id == parent
   - child source_asset_id == parent image asset
   - child video asset: `bb6ba8e6-3519-423a-aa07-68a883fdb5b1`
   - `/api/pipelines/{parent}` returned 200
8. Prompt Enhancement QA:
   - initially failed with `/api/prompts/enhance` 502 and `Prompt enhancement response was invalid.`
   - several backend parser hardening fixes were applied:
     - response_schema + parsed handling
     - fenced JSON extraction
     - valid top-level JSON selection
     - max_output_tokens 800 -> 1600
     - safe diagnostics without raw response/secret logging
   - after fixes, Korean prompt enhancement succeeded:
     - original: `고양이가 집에서 뛰어노는 사진`
     - enhanced:
       `A high-resolution, realistic photograph of a fluffy, playful domestic cat playfully pouncing in a cozy, sunlit living room. The shot is eye-level, captured with a wide-angle lens and shallow depth of field, emphasizing the cat's dynamic motion. Soft natural light illuminates the scene, creating warm and inviting shadows.`
   - T2I generation using enhanced/final prompt succeeded:
     - job id: `bdd3d735-cfa0-4bd5-b733-64fba5c845ad`
     - enhancement_id: `e1398c8a-1795-409a-af1f-d2d0f4f4fee7`
     - image asset: `98f7b64d-c2aa-417b-807c-18beb91affbc`
     - vertex_charged true, attempts 1
   - Note: There is a subtle distinction:
     - Job Detail `Enhanced prompt` is the initial Gemini enhanced prompt
     - Job Detail `Prompt` is the actual final prompt sent to generation
     - For edited prompt verification, inspect `Prompt`, not `Enhanced prompt`
9. Asset storage/detail QA:
   - job detail confirmed asset metadata:
     - asset: `98f7b64d-c2aa-417b-807c-18beb91affbc`
     - job: `bdd3d735-cfa0-4bd5-b733-64fba5c845ad`
     - local_path: `bdd3d735-cfa0-4bd5-b733-64fba5c845ad/output.png`
     - mime: `image/png`
     - size_bytes: `1194569`
     - url: `/files/bdd3d735-cfa0-4bd5-b733-64fba5c845ad/output.png`
   - local file confirmed in backend container:
     - `/data/assets/bdd3d735-cfa0-4bd5-b733-64fba5c845ad/output.png`
     - size 1194569 bytes
   - asset detail endpoint was missing (`GET /api/assets/{id}` returned 404)
   - fixed by `aea4407 feat: add asset detail endpoint`
   - Live retest:
     - `GET /api/assets/98f7b64d-c2aa-417b-807c-18beb91affbc` -> 200 OK with metadata
     - `GET /api/assets/00000000-0000-4000-8000-000000000000` -> 404 `{"detail":"Asset was not found."}`

Current evaluation checklist for 3.1:
- 3 modes T2I/T2V/I2V + model selection: satisfied, live-tested
- DB asset metadata + local file storage + asset detail API: satisfied after `aea4407`, live-tested
- prompt enhancement:
  - implemented and live-tested after parser fixes
  - user review/edit/apply flow exists; important to verify edited final prompt via Job Detail `Prompt`
  - AI_COLLABORATION.md strategy documentation is still intentionally deferred by user until final docs stage
- retry strategy:
  - primitives exist
  - job-level retry integration tests added by `df8742c`
  - still discussing edge coverage for 429 and `number_of_images > 1`
- T2I -> I2V pipeline: satisfied, live-tested
- automated tests: backend currently passed 235 after retry tests, later commits may increase count

Important UX follow-up candidates noted but not immediate blockers:
- T2I Job Detail timeline shows Veo-only `Polling` step, confusing
- skipped stages shown as `pending`, completed flow less clear
- image dimensions show `unknown`
- sidebar brand label still says `PHASE 11 CORE`
- old Enhance review can be accepted after main prompt changes; non-blocking risk
- optional future: enhancement creativity control
  - precise/balanced/creative temperature control
  - not now, likely later feature

Current immediate task:
We were about to ask Codex CLI to add edge coverage after `df8742c test: cover generation retry flows`.
The user noticed two gaps:
1. Job-level retry test lacks 429 `VertexRateLimitError`.
2. T2I `number_of_images > 1` asset persistence is not covered.
3. Mid-retry `vertex_charged` state is hard to inspect and should be deferred.

Recommended prompt already prepared:
```text
현재 repo(`/home/user/recovered_workspace`)에서만 작업하세요. `/home/user` 루트는 건드리지 마세요.

````

## assistant

```text
superpowers:using-superpowers 스킬을 확인해 기본 협업 규칙만 맞춰두겠습니다. 이번 턴은 구현이 아니라 운영 파트너 역할 정렬로만 다룰게요.
```

## assistant

```text
확인했습니다. 저는 여기서 **전략 파트너/리뷰어 역할**로만 움직이고, 직접 구현이나 코드 수정은 하지 않겠습니다.

현재 다음 판단은 이렇습니다:

- 즉시 우선순위는 `df8742c` 이후 빠진 테스트 보강입니다.
- 추가할 범위는 안전하게 두 가지:
  - `VertexRateLimitError` / 429 계열 job-level retry 커버
  - T2I `number_of_images > 1`일 때 asset 여러 개가 저장/연결되는지 커버
- `vertex_charged`의 mid-retry 상태 검증은 말씀대로 defer가 맞습니다. 테스트가 brittle해질 가능성이 큽니다.
- Codex CLI 작업은 반드시 `/home/user/recovered_workspace`에서만 하도록 유지해야 합니다.
- 테스트는 mock 기반이어야 하고 Vertex/Gemini/Imagen/Veo 실제 호출은 금지입니다.

그리고 아직 “프롬프트 줘/제공해줘”라고 하시지 않았으니 Codex CLI용 프롬프트는 작성하지 않겠습니다. CLI 결과를 가져오시면 제가 diff/test/log를 보고 다음 순서를 짧게 정리해드릴게요.
```

## user

```text
이곳은 git remote 가 안되어있는 공간이고 나는 , 기업의 서버 +e2b 환경에서 과제중이야 인지했어 ? 

```

## assistant

```text
응, 정확히 인지했어.

현재 전제는 이렇게 잡고 있을게:

- 여기는 **git remote/push가 없는 작업 공간**
- 작업은 **기업 서버 + E2B 평가/브라우저 환경**에서 진행 중
- 실제 durable repo는 **`/home/user/recovered_workspace`**
- `/home/user` 루트 repo는 손상/읽기전용 이슈가 있으니 **수정·git 작업 금지**
- git은 **로컬 커밋만** 사용
- `.env`, service-account JSON, API key/credential 내용은 절대 출력하거나 요청하지 않음
- Live UX QA 외에는 Vertex/Gemini/Imagen/Veo 실제 호출 금지
- 나는 직접 구현하지 않고, 네가 가져오는 Codex CLI 결과를 보고 **판독, 위험 식별, 다음 작업 순서/프롬프트 제안**만 함

그리고 네가 “프롬프트 줘”라고 하기 전까지는 Codex CLI용 프롬프트를 먼저 쓰지 않을게.
```

## user

```text
현재 과제의 README.md 도 읽어봐 
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
응, 읽었어. 이 README는 사실상 **평가 루브릭 원문**으로 보면 돼.

내가 지금 기준으로 중요하게 잡을 포인트는 이거야:

- **3.1 BE 필수 기능**은 거의 충족 상태로 보임: T2I/T2V/I2V, 모델 선택, asset 저장/조회, prompt enhance, retry, T2I→I2V pipeline, 테스트.
- 지금 논의 중인 **429 retry + multi-image T2I asset persistence 테스트 보강**은 README의 “에러 상태 처리, 엣지케이스 대응, 자동화 테스트” 평가 포인트에 직접 연결돼서 좋은 마무리 작업이야.
- **AI_COLLABORATION.md는 필수 산출물**이고, 단순 Step 3 답변뿐 아니라 prompt enhancement의 “설계 원칙과 프롬프트 전략”도 반드시 들어가야 해.
- **README.md 최종본**은 원문 과제 설명이 아니라, 구동 방법, 기술 스택, Docker Compose 실행, 환경변수/credential 배치 방식, 주요 기능, 테스트 방법 중심의 프로젝트 문서여야 해.
- 선택 기능 관점에서는 이미 **동시 요청 및 Rate Limit 관리**가 들어가 있으므로, 굳이 채팅 에이전트/예산/모델 비교까지 욕심내지 않아도 강점 포인트는 만들 수 있어.
- 제출 산출물 관점에서 `session-history/`는 “본인 코딩 에이전트 환경에서 직접 수행하는 경우” 중요할 수 있으니, 최종 패키징 단계에서 한 번 체크해야 해.

지금 전략은 여전히 좋아 보여. 먼저 retry edge 테스트를 닫고, 그 다음 UX 잔여 polish 여부를 판단한 뒤, 마지막에 `README.md`와 `AI_COLLABORATION.md`를 평가 문항에 맞춰 강하게 정리하는 순서가 안전해.
```

