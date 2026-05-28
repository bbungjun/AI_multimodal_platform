# AI 도구용 복구 작업 컨텍스트

이 워크스페이스는 KRAFTON take-home assignment의 로컬 복구 작업 공간입니다.
목표는 새 기능 개발이 아니라, 현재 남아 있는 코드/문서/대화 export를 근거로
최종 제출했던 Vertex AI 멀티모달 생성 플랫폼을 최대한 가깝게 복구하는 것입니다.

파일명은 `AGENTS.md`입니다. `AGENT.md`가 따로 없으면 이 파일을 기준으로 작업합니다.

## 현재 Git 상태

- Git repo가 새로 초기화되어 있습니다.
- branch: `main`
- remote: `origin` -> `https://github.com/bbungjun/AI_mult_modal.git`
- `main`은 `origin/main`을 tracking합니다.
- 현재 기준점:
  - `0777f50 chore: baseline recovered workspace`
  - `a081bf9 chore: restore project tool layout`
  - `2501e61 restore backend api imports`
  - `c9347f3 docs: document local mock provider mode`
  - `f368bff test: add local mock ai provider`
  - `d03f100 test: restore state machine contract`
  - `9aca9ae fix: restore pipeline page module`
  - `cd34f5a chore: restore compose env hygiene`
  - `2a4b8c6 docs: record compose smoke status`
  - `d61c99b docs: close phase1 recovery`

작업 전후에는 반드시 다음을 확인합니다.

```bash
git status --short --branch
git diff --cached --name-only
```

복구 단위가 의미 있게 닫히면 작게 커밋합니다. 이미 GitHub remote가 연결되어 있으므로,
사용자가 별도로 막지 않는 한 중요한 복구 체크포인트는 push까지 진행해도 됩니다.
절대 `git reset --hard`, `git checkout -- <path>` 같은 되돌리기 명령으로 사용자 변경을
지우지 않습니다.

## 현재 복구 상태

완료된 것:

- `.gitignore`, `.gitattributes` 추가
- 현재 파일 전체 baseline 커밋 및 push
- 프로젝트 도구 레이아웃 1차 복구
  - `backend/pyproject.toml`
  - `backend/Dockerfile`
  - `frontend/package.json`
  - `frontend/Dockerfile`
  - `frontend/index.html`
  - `frontend/vite.config.ts`
  - `frontend/tsconfig.json`
- backend import/API skeleton 1차 복구
  - `backend/app/api/*.py`
  - `backend/app/services/vertex/errors.py`
  - `backend/app/services/vertex/imagen.py`
  - `backend/app/services/vertex/veo.py`
- local mock provider 1차 복구
  - `AI_PROVIDER=mock`에서 T2I mock PNG 생성
  - `AI_PROVIDER=mock`에서 prompt enhancement mock draft 생성
  - mock provider 테스트는 실제 Vertex client 생성을 금지
  - `/api/health`는 mock provider readiness와 `ok`/`ready` 분리 contract를 테스트
  - storage/files safety는 Windows 로컬 저장, unsafe path 차단, `/files` streaming/range를 테스트
  - `POST /api/generations`는 T2I job 생성, `auto_enhance` 거절, matching `enhancement_id` 연결을 테스트
  - `GET /api/generations/{job_id}`와 `GET /api/generations`는 asset DTO 포함 응답과 404를 테스트
  - `DELETE /api/generations/{job_id}`는 terminal 삭제, non-terminal/active dependent 보호, terminal dependent detach를 테스트
  - `POST /api/pipelines`와 `GET /api/pipelines/{parent_job_id}`는 parent T2I + blocked/unblocked child I2V contract를 테스트
  - `pipeline_link`는 completed parent image asset 연결, asset missing/not-image 실패, parent failure cascade를 테스트
- mock-only backend test suite 복구
  - API, storage, state machine, job runner, job handler, Vertex adapter parsing, prompt enhancer contract 테스트 복구
  - 최근 Phase 1 closeout 기준 `python -m pytest`는 `65 passed`
  - 2026-05-28 follow-up 기준 `AI_PROVIDER=mock python -m pytest`는 `157 passed`
- frontend build/typecheck 복구
  - `npm run lint`
  - `npm run build`
- Docker Compose mock smoke 복구
  - `AI_PROVIDER=mock`에서 db, backend, frontend, Vite proxy, job runner, storage, `/files` 흐름 확인
  - 실제 Vertex/Gemini/Imagen/Veo 호출은 수행하지 않음

현재 Phase 1 상태:

- Phase 1 backend import/API/test/frontend/compose mock recovery는 closeout 문서로 닫혔습니다.
- 2026-05-28 follow-up 기준으로 runner startup ordering, orphan sweep resume guard,
  ERD relationship, `/files` response header, prompt enhancement linkage, state_history
  payload detail contract까지 mock/fake-only 테스트로 추가 고정했습니다.
- 실제 provider 접근과 실제 Vertex/Gemini/Veo 품질 QA는 별도 수동 확인 범위입니다.

현재 최종 제출 정합성 리뷰 기준:

- `README.md`, `AGENTS.md`, `memories/recovery/*`, 실제 backend/frontend 코드의 API/env/provider 설명을 맞춥니다.
- mock local mode와 real Vertex mode가 명확히 분리되어 있는지 확인합니다.
- secret, `.env`, service-account JSON, generated runtime asset이 staged/committed 되지 않는지 확인합니다.
- public 전환은 secret/history 문제를 별도로 처리하기 전까지 보류합니다.

## 복구 대상 프로젝트

복구 대상은 Vertex AI 기반 AI 멀티모달 콘텐츠 생성 플랫폼입니다.

- Imagen 4 text-to-image
- Veo 3 text-to-video 및 image-to-video
- Gemini 2.5 Flash prompt enhancement
- FastAPI backend, Postgres job 상태 관리
- React/Vite/TypeScript frontend
- Docker Compose로 `db`, `backend`, `frontend` 실행

## 보존된 컨텍스트

다음 파일과 디렉터리는 복구 근거 자료입니다. 삭제하거나 덮어쓰지 않습니다.

- `original_agents.md`: 과제 구현 당시 Codex CLI가 읽던 원래 작업 지침
- `README_ORIGINAL.md`: 원래 과제 소개/명세 README
- `README.md`: 최종 제출했던 프로젝트 README
- `pre_context/INDEX.md`: 긴 export를 찾기 위한 색인
- `pre_context/summaries/*.md`: export 요약본
- `pre_context/krafton_assignment_01.md` ~ `15.md`: 원문 대화 export
- `conversation_last_half_export.md`: 후반 작업 인수인계 메모
- `memories/`: phase 계획, architecture 메모, troubleshooting 기록

긴 export를 바로 전부 읽지 말고, 먼저 `pre_context/INDEX.md`와 관련 summary를 봅니다.

## 복구 우선순위

1. Backend import가 가능한 상태를 만듭니다.
   - `backend/app/api/*.py`
   - `backend/app/services/vertex/errors.py`
   - `backend/app/services/vertex/imagen.py`
   - `backend/app/services/vertex/veo.py`
2. API contract를 README와 memories 기준으로 맞춥니다.
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
3. Mock-only backend tests를 복구합니다.
4. Frontend build를 복구합니다.
5. Docker Compose config/build 가능 상태를 확인합니다.

## 핵심 구현 규칙

- Celery와 Redis는 사용하지 않습니다. Job은 Postgres에 저장하고 FastAPI 내부
  asyncio runner가 처리합니다.
- Vertex SDK는 `google-genai` 하나만 사용합니다.
  `genai.Client(vertexai=True, ...)` 형태를 유지합니다.
- Veo 결과는 GCS가 아니라 inline video bytes를 `DATA_DIR`에 저장합니다.
- 모든 job 상태 변경은 `app/state_machine.py:transition(...)`을 거칩니다.
- asset 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거칩니다.
- 사용자 입력 filename을 파일 경로에 직접 사용하지 않습니다.
- Prompt Enhancement는 generation 자동 대체가 아니라 review/edit/accept 가능한 초안입니다.
- 최종 generation prompt의 source of truth는 사용자가 확인한 generation payload prompt입니다.

## 비용 없는 로컬 개발/테스트 방침

Vertex AI, Gemini, Imagen, Veo는 비용이 발생할 수 있으므로 개인 로컬 검증에서는
실제 provider를 호출하지 않는 `AI_PROVIDER=mock` 모드를 둡니다.

- `AI_PROVIDER=vertex`: 최종 제출물의 원래 provider 경로입니다. `google-genai`와
  `genai.Client(vertexai=True, ...)` 경계를 유지합니다.
- `AI_PROVIDER=mock`: 개인 로컬 개발/테스트 전용입니다. credential 없이 실행되어야 하며,
  Vertex/Gemini/Imagen/Veo를 실제 호출하면 안 됩니다.
- mock provider는 실제 AI 품질을 흉내 내는 것이 아니라 앱 흐름을 검증하기 위한
  deterministic media bytes를 생성합니다.
  - T2I mock은 유효한 PNG bytes를 생성하여 storage, asset, `/files/...`, frontend preview
    흐름을 확인할 수 있게 합니다.
  - Prompt enhancement mock은 deterministic enhanced prompt와 components를 반환합니다.
  - Health/readiness는 mock provider에서 Vertex credential을 요구하지 않는 상태를 반환합니다.
  - T2V/I2V mock은 필요 시 별도 fixture 또는 deterministic placeholder로 처리하되,
    원본 Veo 경계를 깨지 않습니다.
- API, DB model, job runner, state machine, storage helper, frontend 흐름은 provider가
  mock인지 vertex인지 몰라야 합니다. provider 선택은 좁은 service boundary 안에서만
  처리합니다.
- `.env` 예시는 credential을 요구하지 않는 local mode와 실제 제출/운영용 Vertex mode를
  분리해서 설명해야 합니다. secret이나 service-account JSON 내용은 절대 출력하거나
  커밋하지 않습니다.
- 자동화 테스트는 기본적으로 `AI_PROVIDER=mock` 또는 monkeypatch/fake provider로 실행하여
  외부 AI 호출과 비용 발생을 막습니다.

## 안전 규칙

- `pre_context/`, `memories/`, `original_agents.md`, `README_ORIGINAL.md`,
  `README.md`를 삭제하거나 덮어쓰지 않습니다.
- service-account JSON 내용, `.env` secret, API key, private credential을 출력,
  문서화, 커밋하지 않습니다.
- 자동화 테스트에서 Vertex, Gemini, Imagen, Veo를 실제 호출하지 않습니다.
- 테스트는 `app/services/vertex/*`와 `app/services/llm/*`를 mock 또는 fake로
  대체해야 합니다.
- 복구 중 GCS, Redis, Celery, 새 DB, 새 frontend framework를 도입하지 않습니다.
- 대화 export를 그대로 소스 코드로 간주하지 않습니다. 근거로만 사용하고,
  import, 테스트, 빌드로 검증합니다.

## 검증 체크리스트

가장 좁은 검증부터 실행합니다.

백엔드:

```bash
cd backend
python -m pip install -e ".[dev]"
python -m pytest
```

프론트엔드:

```bash
cd frontend
npm install
npm run build
```

Docker Compose:

```bash
docker compose config
docker compose up -d --build
```

명령이 실패하면 첫 번째 구체적인 에러부터 진단합니다. 추측성 대규모 rewrite를
피합니다.

## 작업 방식

- 변경은 작게 나누고, 한 번에 하나의 경계만 복구합니다.
- 새로 발명하기보다 현재 남아 있는 코드, README, memories, export 근거를 우선합니다.
- 누락 파일을 재구성할 때는 먼저 `pre_context/INDEX.md`에서 관련 summary를 찾고,
  그 다음 원문 export에서 정확한 경로, 함수명, route, schema 이름을 검색합니다.
- 각 복구 단위가 끝나면 무엇을 복구했고 무엇이 아직 빠져 있는지 요약합니다.
