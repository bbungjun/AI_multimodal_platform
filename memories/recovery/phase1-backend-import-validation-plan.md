# Phase 1 Recovery Plan - Backend Import/API Skeleton

## 목적

현재 복구 작업의 1단계 목표는 기능을 새로 확장하는 것이 아니라, backend가 import 가능한 최소 실행 상태가 되도록 누락된 API router와 Vertex service boundary를 복구하는 것이다.

이 단계가 끝나면 `backend/app/main.py` import가 성공해야 하며, 이후 backend tests 복구와 frontend build 복구로 넘어갈 수 있어야 한다.

## 현재 확인된 상태

- Git 기준점은 `main` branch에 있다.
- `origin/main` tracking이 설정되어 있다.
- baseline commit과 project tool layout 복구 commit이 이미 존재한다.
- `backend/pyproject.toml`, `backend/Dockerfile`, `frontend/package.json`, `frontend/index.html`, `frontend/vite.config.ts`, `frontend/tsconfig.json`은 루트 위치로 복구되었다.
- `backend/app/main.py`는 `app.api.*` router를 import하지만 현재 `backend/app/api/`는 비어 있다.
- `backend/tests/`는 아직 복구되지 않았다.
- `app/services/vertex/errors.py`, `imagen.py`, `veo.py`도 현재 파일 목록에서 보이지 않는다.

## 복구 범위

### 포함

1. Backend import chain 조사
2. API router 파일 복구
3. Vertex service boundary 파일 복구
4. 최소 import/compile 검증
5. 복구 단위 커밋

### 제외

- frontend 수정
- Docker Compose 전체 실행
- 실제 Vertex/Gemini/Imagen/Veo 호출
- README/AI_COLLABORATION 수정
- Redis/Celery/GCS 도입
- 신규 기능 추가
- 대규모 refactor

## 근거 자료 우선순위

1. `pre_context/INDEX.md`
2. `pre_context/summaries/04-summary.md`
3. `pre_context/summaries/05-summary.md`
4. `pre_context/summaries/06-summary.md`
5. `pre_context/summaries/07-summary.md`
6. `pre_context/summaries/08-summary.md`
7. `pre_context/summaries/13-summary.md`
8. `pre_context/summaries/14-summary.md`
9. `memories/architecture.md`
10. 현재 코드:
    - `backend/app/main.py`
    - `backend/app/schemas.py`
    - `backend/app/models.py`
    - `backend/app/services/jobs/handlers.py`
    - `backend/app/services/jobs/runner.py`
    - `backend/app/services/jobs/pipeline_link.py`
    - `backend/app/services/llm/enhancer.py`
    - `backend/app/services/vertex/client.py`
    - `backend/app/services/vertex/storage.py`

긴 원문 export는 summary에서 위치를 좁힌 뒤 필요한 구간만 확인한다.

## 단계별 진행

### Stage 0 - 작업 전 안전 확인

명령:

```bash
git status --short --branch
git log --oneline -3
```

완료 기준:

- working tree가 clean이거나, 사용자가 알고 있는 변경만 존재한다.
- 새 복구 작업은 이전 커밋 위에서 시작한다.

### Stage 1 - Import chain 조사

확인할 것:

- `backend/app/main.py`가 import하는 누락 module
- `backend/app/services/jobs/handlers.py`가 import하는 누락 module
- `backend/app/services/llm/enhancer.py`가 기대하는 schema/model
- `backend/app/services/vertex/client.py`가 기대하는 error type

권장 명령:

```bash
cd backend
python -m compileall app
python -c "import app.main"
```

이 단계에서는 실패가 정상이다. 목적은 첫 번째 구체적인 import error를 확인하는 것이다.

완료 기준:

- 누락 파일 목록을 확정한다.
- 복구 순서를 API router와 Vertex boundary로 나눈다.

### Stage 2 - API router skeleton 복구

복구 대상:

- `backend/app/api/__init__.py`
- `backend/app/api/health.py`
- `backend/app/api/generations.py`
- `backend/app/api/prompts.py`
- `backend/app/api/pipelines.py`
- `backend/app/api/assets.py`
- `backend/app/api/files.py`

API contract 기준:

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

구현 원칙:

- 현재 `schemas.py`, `models.py`, service 함수에 맞춘다.
- 누락된 세부 동작은 새로 과하게 설계하지 않고, import 가능한 최소 구현부터 복구한다.
- `JobResponse.assets` lazy-load 문제가 있었으므로 ORM 객체를 그대로 response로 반환하지 않는지 주의한다.
- delete는 terminal job과 dependent job 보호 정책을 지켜야 한다.
- files route는 storage path safety를 우회하지 않는다.

완료 기준:

- `python -c "import app.main"`이 API router 누락으로 실패하지 않는다.
- endpoint path가 README와 memories의 contract와 어긋나지 않는다.

### Stage 3 - Vertex service boundary 복구

복구 대상:

- `backend/app/services/vertex/errors.py`
- `backend/app/services/vertex/imagen.py`
- `backend/app/services/vertex/veo.py`

구현 원칙:

- `google-genai` 단일 SDK 경로를 유지한다.
- Imagen, Veo, Gemini에 별도 provider SDK를 도입하지 않는다.
- Veo는 `output_gcs_uri`를 사용하지 않고 inline `video_bytes`를 읽는 구조를 유지한다.
- tests에서는 실제 Vertex 호출이 일어나지 않도록 service boundary를 mock 가능하게 둔다.
- Veo polling은 operation error, safety-filtered result, missing output을 구분할 수 있어야 한다.

완료 기준:

- `handlers.py`가 기대하는 함수와 error class가 존재한다.
- import/compile이 Vertex boundary 누락으로 실패하지 않는다.

### Stage 4 - 최소 검증

명령:

```bash
cd backend
python -m compileall app
python -c "import app.main"
```

가능하면 추가:

```bash
python -m pytest
```

단, `backend/tests/`가 아직 복구되지 않은 상태라면 pytest는 "tests 없음" 또는 import failure 확인 용도로만 본다.

완료 기준:

- `compileall app` 통과
- `import app.main` 통과
- 실패 시 첫 번째 구체적인 에러와 다음 복구 단위를 문서화

### Stage 5 - 커밋 및 push

명령:

```bash
git status --short
git diff --cached --name-only
git commit -m "restore backend api imports"
git push
```

커밋 전 확인:

- `.env`
- service-account JSON
- generated cache
- `node_modules`
- `dist`
- `.venv`
- `__pycache__`
- `data/assets`

위 항목이 staged에 들어가면 안 된다.

## 1단계 완료 정의

다음 조건을 만족하면 Phase 1 Recovery를 완료로 본다.

- `backend/app/main.py` import 성공
- API router files 존재
- Vertex service boundary files 존재
- 실제 provider 호출 없이 import/compile 검증 완료
- 복구 변경사항이 Git commit으로 저장되고 remote에 push됨

## 다음 단계 후보

Phase 1 Recovery 이후에는 아래 중 하나로 넘어간다.

1. Backend tests 복구
2. Frontend build/typecheck 복구
3. Docker Compose config/build 검증

우선순위는 Phase 1 결과의 실패 지점에 따라 결정한다.
