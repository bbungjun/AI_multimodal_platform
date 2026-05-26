# AI 도구용 복구 작업 컨텍스트

이 워크스페이스는 KRAFTON take-home assignment의 로컬 복구 작업 공간입니다.
사용 가능한 Git 히스토리나 원격 저장소는 없습니다. 이 디렉터리에 남아 있는
파일들을 유일한 지속 자료로 보고, 보존된 코드, README, memories, 대화 export를
근거로 최종 제출했던 프로젝트를 최대한 가깝게 복구합니다.

## 현재 목표

복구 대상 프로젝트는 Vertex AI 기반 AI 멀티모달 콘텐츠 생성 플랫폼입니다.

- Imagen 4 text-to-image
- Veo 3 text-to-video 및 image-to-video
- Gemini 2.5 Flash prompt enhancement
- FastAPI 백엔드, Postgres job 상태 관리, React/Vite 프론트엔드

목표는 새 기능 개발이 아니라 복구입니다. 새 설계나 기능 추가보다 최종 제출 당시
동작을 되살리는 것을 우선합니다.

## 보존된 컨텍스트

- `original_agents.md`: 과제 구현 당시 Codex CLI가 읽던 원래 작업 지침입니다.
  보존해야 하며 덮어쓰지 않습니다.
- `README_ORIGINAL.md`: 원래 과제 소개/명세 README입니다. 보존해야 하며
  덮어쓰지 않습니다.
- `README.md`: 최종 제출했던 프로젝트 README입니다. 최종 앱의 의도된 기능과
  실행 방법을 설명하는 우선순위 높은 자료로 취급합니다.
- `pre_context/krafton_assignment_01.md`부터
  `pre_context/krafton_assignment_15.md`: 대화 export 및 복구 근거 자료입니다.
  누락된 코드를 재구성할 때 먼저 검색합니다.
- `conversation_last_half_export.md`: 후반 작업 인수인계 메모입니다.
- `memories/`: phase 계획, 아키텍처 메모, troubleshooting 기록입니다.

## 복구 우선순위

1. 코드 수정 전에 모든 컨텍스트 파일을 보존합니다.
2. 기대되는 프로젝트 레이아웃을 복구합니다.
   - `backend/pyproject.toml`
   - `backend/Dockerfile`
   - `backend/app/...`
   - `backend/tests/...`
   - `frontend/package.json`
   - `frontend/Dockerfile`
   - `frontend/index.html`
   - `frontend/vite.config.ts`
   - `frontend/src/...`
3. `backend/app/main.py`가 참조하는 백엔드 API 모듈을 복구합니다.
   - `app/api/health.py`
   - `app/api/generations.py`
   - `app/api/prompts.py`
   - `app/api/pipelines.py`
   - `app/api/assets.py`
   - `app/api/files.py`
4. 누락된 Vertex 서비스 경계가 있으면 복구합니다.
   - `app/services/vertex/errors.py`
   - `app/services/vertex/imagen.py`
   - `app/services/vertex/veo.py`
5. 프론트엔드 빌드 가능 상태를 복구하고, 비어 있거나 깨진 주요 페이지 파일을
   우선 복구합니다.
6. 앱 import가 정상화된 뒤 mock-only 백엔드 테스트를 복구합니다.
7. 복구 완료를 말하기 전에 로컬 검증 명령을 실행합니다.

## 핵심 구현 규칙

- Celery와 Redis는 사용하지 않습니다. Job은 Postgres에 저장하고 FastAPI 내부
  asyncio runner가 처리합니다.
- Vertex SDK는 `google-genai` 하나만 사용합니다.
  `genai.Client(vertexai=True, ...)` 형태를 유지합니다.
- Veo 결과는 GCS가 아니라 inline video bytes를 `DATA_DIR`에 저장합니다.
- 모든 job 상태 변경은 `app/state_machine.py:transition(...)`을 거칩니다.
- asset 파일 쓰기와 삭제는 storage helper를 거칩니다.
- 사용자 입력 filename을 파일 경로에 직접 사용하지 않습니다.

## 안전 규칙

- `pre_context/`, `memories/`, `original_agents.md`, `README_ORIGINAL.md`,
  `README.md`를 삭제하거나 덮어쓰지 않습니다.
- 큰 파일 이동이나 대규모 rewrite 전에는 백업을 만들거나 기존 파일을 명확한
  복구용 이름으로 보존합니다.
- service-account JSON 내용, `.env` secret, API key, private credential을 출력,
  문서화, 커밋하지 않습니다.
- 자동화 테스트에서 Vertex, Gemini, Imagen, Veo를 실제 호출하지 않습니다.
- 테스트는 `app/services/vertex/*`와 `app/services/llm/*`를 mock 또는 fake로
  대체해야 합니다.
- 복구 중 GCS, Redis, Celery, 새 DB, 새 프론트엔드 프레임워크를 도입하지
  않습니다.
- 대화 export를 그대로 소스 코드로 간주하지 않습니다. 근거로만 사용하고,
  import, 테스트, 빌드로 검증합니다.

## 검증 체크리스트

현재 복구 단계가 맞다는 것을 증명하는 가장 좁은 명령부터 실행합니다.

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

`.env`가 있고 credential이 파일 경로로만 설정된 경우 Docker Compose:

```bash
docker compose config
docker compose up -d --build
```

명령이 실패하면 첫 번째 구체적인 에러부터 진단합니다. 추측성 대규모 rewrite를
피합니다.

## 작업 방식

- 변경은 작게 나누고, 한 번에 하나의 경계만 복구합니다.
- 새로 발명하기보다 현재 남아 있는 코드와 export 근거를 우선합니다.
- 누락 파일을 재구성할 때는 먼저 `pre_context/`와 `memories/`에서 정확한 경로,
  함수명, route, schema 이름을 검색합니다.
- 각 복구 단위가 끝나면 무엇을 복구했고 무엇이 아직 빠져 있는지 요약합니다.
