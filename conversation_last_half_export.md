KRAFTON assignment conversation export - latter-half context
Date context: 2026-05-24 Asia/Seoul
Purpose: Paste into a new strategy/Codex session so it understands the recent work.

Role setup
- User is building a KRAFTON take-home assignment: AI multimodal content generation platform.
- Assistant is acting as a strategy partner that reviews Codex CLI results and proposes short, safe next prompts.
- Assistant should not directly implement project code unless the user explicitly asks.
- Never request or print .env contents, service-account JSON contents, API keys, or credential secrets.
- Tests must remain mock-only for Vertex/Gemini/Imagen/Veo. Real calls are allowed only during explicit Live UX QA through the frontend/manual flow.

Core project constraints
- Backend: FastAPI + async SQLAlchemy + asyncpg + Postgres.
- Frontend: Vite + React + TypeScript.
- AI SDK: google-genai single SDK for Gemini/Imagen/Veo.
- No Celery/Redis. Jobs are processed by in-process asyncio runner.
- Results are stored as local files, not GCS.
- State changes go through app/state_machine.py transition logic.
- Git is local commits only.

Important completed phases and commits
- Phase 12 Docker Compose / integration readiness completed.
- Phase 13 API contract alignment completed.
- Phase 13 closeout commit: 390039b docs: close out phase 13 api contract alignment.
- Vite E2B public host bug fixed:
  - commit 707bb57 fix: allow configured vite dev hosts.
- POST /api/generations lazy-load 500 bug fixed:
  - commit 1578f1e fix: avoid lazy loading generation assets.

Docker / E2B environment notes
- Project root in the E2B/webserver terminal is /home/user.
- The service-account JSON file exists in /home/user and is gitignored by tht-aif-*.json.
- Do not cat or print the JSON contents.
- Initial Docker state:
  - docker client existed.
  - normal user had no /var/run/docker.sock permission.
  - sudo docker worked.
  - docker compose v2 was initially missing.
  - docker-compose v1 existed but failed with http+docker Python dependency error.
- Compose v2 plugin was manually installed and copied to /usr/local/lib/docker/cli-plugins/docker-compose.
- sudo docker compose version worked afterward.
- sudo docker compose --env-file .env build succeeded for backend and frontend.
- sudo docker compose --env-file .env up -d succeeded.
- db/backend/frontend were confirmed running.

Actual compose smoke results
- sudo docker compose --env-file .env build: success.
- sudo docker compose --env-file .env up -d: success.
- db container healthy.
- backend/frontend containers running.
- GET http://localhost:8000/api/health: 200 OK.
- GET http://localhost:5173/api/health: 200 OK through frontend proxy.
- GET http://localhost:8000/files/smoke-missing-file: 404 JSON, backend asset-serving response.
- GET http://localhost:5173/files/smoke-missing-file: 404 from backend/uvicorn through frontend proxy.
- GET http://localhost:5173/: 200 HTML.

Health schema bug found and fixed
- During compose smoke, /api/health returned 500.
- Backend log root cause:
  - FastAPI ResponseValidationError.
  - response.vertex was expected as bool/string but actual value was nested dict:
    {ready, status, credentials, project, location}.
- Fixed by adding/using proper HealthResponse and VertexReadinessResponse schema.
- Commit: c403718 fix: align health response schema.
- After fix:
  - /api/health direct and frontend proxy both returned 200.

Phase 13 API contract alignment
- Goal: Use FastAPI OpenAPI/Swagger as source of truth, but do not introduce codegen yet.
- Decision:
  - Automatic openapi-typescript/codegen is deferred.
  - Manual type alignment is preferred due to small drift and lower blast radius.
- Unit 1:
  - HealthResponse frontend type alignment.
  - Added VertexReadinessResponse to frontend API types.
  - Added ready and vertex fields to HealthResponse.
  - Commit: 248fe28 fix: align frontend health response type.
- Unit 2:
  - Full FE/BE API contract audit.
  - app.openapi() generated and checked, snapshot not stored.
  - Prompt enhance, generation, job/asset, pipeline, health, error response shapes audited.
  - fix-now drift: none after Unit 1.
  - OpenAPI/docs issues were deferred to later docs/test hardening.
- Unit 3:
  - No code changes because no fix-now drift remained.
  - Drift decision documented.
  - Commit: 53f6cd3 docs: record phase 13 drift decision.
- Unit 4:
  - Compose contract smoke verification.
  - Checked /openapi.json, /docs, /api/health, frontend /api proxy, /files proxy, frontend root.
  - Commit: fb8aa34 docs: record phase 13 contract smoke.
- Closeout:
  - Commit: 390039b docs: close out phase 13 api contract alignment.

Vite public host issue
- When opening frontend public E2B URL, browser showed:
  Blocked request. This host ("5173-...e2b.app") is not allowed.
  Add it to server.allowedHosts in vite.config.js.
- Earlier preview workaround was different:
  - preview mode had preview.allowedHosts issue.
  - compose/dev mode had server.allowedHosts issue.
- vite --help only showed --host, no CLI allowed-host option.
- Bugfix:
  - frontend/vite.config.ts parses VITE_ALLOWED_HOSTS comma-separated list and sets server.allowedHosts only when non-empty.
  - docker-compose.yml passes VITE_ALLOWED_HOSTS to frontend.
  - .env.example includes non-sensitive empty example/explanation.
  - allowedHosts: true was avoided.
- Verification:
  - npm run lint passed.
  - npm run build passed.
  - docker compose --env-file .env config --quiet passed.
  - VITE_ALLOWED_HOSTS=5173-${E2B_SANDBOX_ID}.e2b.app sudo -E docker compose --env-file .env up -d --force-recreate frontend passed.
  - Public URL changed from blocked request to 200 text/html.
- Commit: 707bb57 fix: allow configured vite dev hosts.

Live UX QA started
- User wants to validate real functionality from the frontend, not only API curl.
- Cost is not the primary concern; completeness and product quality matter more.
- Plan: Perform actual user flows manually through the frontend:
  1. Gemini Enhance.
  2. Imagen T2I.
  3. Veo T2V.
  4. I2V using generated image.
  5. Pipeline T2I -> I2V.
  6. History and detail UX.
- Important principle:
  - Automatic tests remain mock-only.
  - Real AI calls happen only in manual Live UX QA flows.

Credential/health preflight
- User ran:
  curl -s http://localhost:8000/api/health
- Response showed:
  ok true, ready true, service backend, db up.
  vertex ready true, status ready, credentials available, project configured, location us-central1.
- This proves credential file exists and config is present, but not necessarily that every model call has IAM/model access until actual calls are made.

First Live UX bug: POST /api/generations 500
- User clicked Text to image Generate in frontend.
- Browser showed:
  POST https://5173-...e2b.app/api/generations 500.
- Request body was normal:
  mode t2i, model imagen-4.0-fast-generate-001, prompt "귀여운 고양이 사진 만들어줘", aspect_ratio 1:1, number_of_images 1, auto_enhance false.
- Backend log root cause:
  FastAPI ResponseValidationError.
  loc: ('response', 'assets').
  MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here.
  Input was <app.models.Job ...>.
- Interpretation:
  - POST /api/generations was returning ORM Job object.
  - FastAPI response_model serialization tried to access job.assets relationship.
  - SQLAlchemy async lazy-load attempted IO outside greenlet/await context.
  - This was response DTO/ORM lazy relationship problem, not Vertex, DB, or frontend request problem.
- Bugfix prompt emphasized:
  - Return explicit DTO with assets=[] for create response.
  - Avoid ORM object lazy relationship in response serialization.
  - Check pipeline create for same risk.
  - Add regression test with mock/runner disabled, no real AI calls.
- Bugfix result:
  - backend/app/schemas.py: job_response_from_job(...) DTO mapper added.
  - backend/app/api/generations.py: POST /api/generations returns DTO with assets=[].
  - backend/app/api/pipelines.py: pipeline create response uses same pattern.
  - backend/tests/test_t2i_flow.py: regression test added where lazy assets access would fail.
  - related pytest: 3 passed.
  - backend full pytest: 215 passed.
  - docker compose --env-file .env config --quiet passed.
  - Commit: 1578f1e fix: avoid lazy loading generation assets.
  - final git status clean.

First successful real Imagen T2I
- After rebuilding/restarting backend, user retried frontend T2I.
- It succeeded.
- User shared screenshot of Job Detail page with generated cat image.
- Confirmed:
  - Real frontend Generate form.
  - POST /api/generations.
  - Backend job runner.
  - Actual Imagen call through Vertex.
  - Local asset storage.
  - /files serving.
  - Frontend job detail polling/result rendering.
  - I2V handoff button displayed.
- Details from screenshot:
  - Prompt: "고양이 사진 만들어줘".
  - Model: imagen-4.0-fast-generate-001.
  - Job id: 1f4a269a-b3a7-427b-b4f2-0e40a102766a.
  - Asset id: 0e5cef25-b5b4-4750-b370-6afc371c14f9.
  - Asset kind: image.
  - MIME: image/png.
  - Size: about 1.4 MB.
  - Job state: completed.
  - Attempts: 1.
  - Vertex charged: yes.
  - Blocked: no.
  - "Use as I2V source" button displayed.

UX follow-up observations from first successful T2I screenshot
- T2I job detail timeline shows Veo-only "Polling" step, which is confusing.
- Stages not traversed are shown as "pending", making the completed flow unclear.
- Image dimensions show "unknown".
- Sidebar brand label still says PHASE 11 CORE.
- These were noted as follow-up candidates, not immediate blockers.

Suggested next documentation step after first T2I success
- Record Phase 14 Live UX QA T2I success in:
  .codex/memories/phase14/phase14_live_ux_qa_results.md
- Include:
  - prompt, model, job id, asset id.
  - actual Imagen success.
  - frontend/job runner/local storage/files rendering verified.
  - UX follow-up candidates.
- Do not modify code/config/README/AGENTS for documentation-only step.
- Because .codex is gitignored, use exact path:
  git add -f .codex/memories/phase14/phase14_live_ux_qa_results.md
- Suggested commit:
  docs: record live t2i qa success

Current likely next actions
Option A: Documentation checkpoint first
- Ask Codex CLI to record live T2I QA success in Phase 14 memory and commit.

Option B: Continue manual Live UX QA first
- Use the generated image and click "Use as I2V source".
- Validate actual Veo I2V.
- Then validate T2V and Pipeline.
- Keep backend logs running:
  sudo docker compose --env-file .env logs -f backend
- If a failure appears, collect:
  - flow name.
  - visible frontend error.
  - backend traceback/error without secrets.
  - job id if available.

Recommended next prompt if documenting T2I success
"""
Phase 14 Live UX QA 결과 기록만 하세요. 구현 수정은 하지 마세요.

확인된 수동 QA:
- Frontend public URL에서 Text to image flow를 직접 실행
- Prompt: `고양이 사진 만들어줘`
- Model: `imagen-4.0-fast-generate-001`
- Job id: `1f4a269a-b3a7-427b-b4f2-0e40a102766a`
- Asset id: `0e5cef25-b5b4-4750-b370-6afc371c14f9`
- Result: 실제 고양이 PNG 생성 및 Job Detail 화면에서 렌더링 성공
- Asset metadata: kind `image`, MIME `image/png`, size about `1.4 MB`
- Job state: `completed`, attempts `1`, vertex_charged `yes`, blocked `no`
- I2V handoff button displayed: `Use as I2V source`

확인된 end-to-end 범위:
- frontend Generate form
- POST /api/generations
- backend job runner
- actual Imagen call through Vertex
- local asset storage
- /files serving
- frontend job detail polling/result rendering
- image-to-video handoff entry point

관찰된 UX follow-up 후보:
- T2I job detail timeline에 `Polling` 같은 Veo-only 단계가 보여 혼란스러움
- 거치지 않은 단계가 `pending`으로 표시되어 완료 흐름이 덜 명확함
- image dimensions가 `unknown`으로 표시됨
- sidebar brand label이 아직 `PHASE 11 CORE`로 표시됨

작업:
1. `git status --short` 확인
2. `.codex/memories/phase14/phase14_live_ux_qa_results.md`를 작성하거나 업데이트하세요.
3. 위 성공 결과와 follow-up 후보를 기록하세요.
4. 코드/config/README/AGENTS는 수정하지 마세요.
5. 실제 `.env`, credentials, service-account JSON 내용 읽기/출력 금지.
6. `.codex/`는 gitignored이므로 exact path만 `git add -f` 하세요:
   - `git add -f .codex/memories/phase14/phase14_live_ux_qa_results.md`
7. 커밋 전 `git status --short`, `git diff --cached --name-only` 확인

커밋 메시지:
`docs: record live t2i qa success`

완료 후 변경 파일, 커밋 해시, 최종 git status를 요약하세요.
"""

Recommended next prompt if continuing I2V manual QA
"""
구현/커밋하지 말고 Live UX QA 관찰 지원만 하세요.

현재 실제 T2I 성공 job:
- Job id: `1f4a269a-b3a7-427b-b4f2-0e40a102766a`
- Asset id: `0e5cef25-b5b4-4750-b370-6afc371c14f9`
- Prompt: `고양이 사진 만들어줘`
- Model: `imagen-4.0-fast-generate-001`

목표:
사용자가 프론트 화면에서 `Use as I2V source`를 눌러 실제 I2V flow를 검증할 수 있도록 compose/backend 로그 상태만 준비하세요.

작업:
1. `git status --short` 확인
2. `sudo docker compose --env-file .env ps` 확인
3. 필요하면 `sudo docker compose --env-file .env up -d`
4. readiness 확인:
   - `curl -s http://localhost:8000/api/health`
   - `curl -I http://localhost:5173/`
5. backend 로그 관찰 명령을 안내하세요:
   - `sudo docker compose --env-file .env logs -f backend`

제약:
- 파일 수정/stage/commit 금지.
- 실제 `.env`, credentials, service-account JSON 내용 읽기/출력 금지.
- Codex가 직접 I2V 요청을 보내지 마세요. 실제 클릭은 사용자가 프론트에서 합니다.
"""

Do not forget
- If a live flow fails, do not retry blindly.
- First collect backend logs and frontend error.
- Then create a narrow bugfix prompt.
- Keep generated artifacts, .env, credentials, data/assets out of git.
