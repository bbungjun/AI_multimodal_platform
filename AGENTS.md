# CreativeOps Studio 작업 지침

이 워크스페이스는 개인 프로덕션 포트폴리오 프로젝트인
`bbungjun/AI_multimodal_platform`의 개발 공간입니다.

목표는 특정 제출물의 흔적을 보존하는 것이 아니라, Vertex AI 기반 멀티모달 생성
서비스를 실제로 운영 가능한 수준까지 키우는 것입니다. 새 기능을 넣을 때도 항상
사용자가 실제로 이미지를 만들고, 프롬프트를 다듬고, 작업 결과를 관리하는 흐름을
더 안정적으로 만드는지부터 판단합니다.

## 제품 방향

- 핵심 서비스는 멀티모달 콘텐츠 생성 스튜디오입니다.
- 지원 범위는 Imagen text-to-image, Veo text-to-video/image-to-video, Gemini 기반
  prompt enhancement입니다.
- RAG, ETL, 챗봇, LLMOps 기능은 제품 가치가 분명할 때만 추가합니다.
- 첫 화면은 실제 작업 공간이어야 하며, 마케팅 랜딩 페이지보다 사용 가능한 생성
  경험을 우선합니다.
- mock mode에서도 생성, 미리보기, 파일 서빙, 작업 상태 흐름이 끝까지 검증되어야
  합니다.

## 저장소와 Git

- 기본 브랜치는 `main`입니다.
- 원격 저장소는 `origin -> https://github.com/bbungjun/AI_multimodal_platform.git`
  입니다.
- 작업 전후에는 반드시 확인합니다.

```bash
git status --short --branch
git diff --cached --name-only
```

- 변경은 작고 의미 있는 단위로 커밋합니다.
- 사용자가 막지 않는 한 중요한 체크포인트는 push까지 진행해도 됩니다.
- `git reset --hard`, `git checkout -- <path>`처럼 사용자 변경을 지울 수 있는
  명령은 명시 요청 없이는 사용하지 않습니다.
- 현재 작업과 무관한 dirty change는 되돌리지 않고 그대로 둡니다.

## 비밀정보 안전

- `.env`, ADC 파일, service-account JSON, API key, private key 내용은 읽지 않고
  출력하지 않고 커밋하지 않습니다.
- credential 파일의 경로는 필요할 때만 환경변수 이름 수준으로 다룹니다.
- `.env.example`에는 로컬 실행에 필요한 비밀이 없는 값만 둡니다.
- 테스트와 기본 compose 검증은 `AI_PROVIDER=mock` 기준으로 수행합니다.
- 실제 Vertex 호출은 비용이 발생할 수 있으므로 사용자가 의도한 상황에서만
  진행합니다.

## Provider 경계

- `AI_PROVIDER=mock`
  - credential 없이 동작해야 합니다.
  - Vertex, Gemini, Imagen, Veo를 실제 호출하면 안 됩니다.
  - deterministic PNG/video placeholder/prompt draft로 앱 흐름을 검증합니다.
- `AI_PROVIDER=vertex`
  - 실제 Vertex AI 경로입니다.
  - SDK는 `google-genai`를 사용하고 `genai.Client(vertexai=True, ...)` 경계를
    유지합니다.
  - ADC 또는 service-account는 opaque credential로 취급합니다.

Provider 선택은 좁은 service boundary 안에서 처리합니다. API, DB model, job runner,
state machine, storage helper, frontend는 가능한 한 provider 종류를 몰라야 합니다.

## 아키텍처 규칙

- Backend는 FastAPI, SQLAlchemy, Postgres를 기준으로 둡니다.
- Frontend는 React, Vite, TypeScript를 기준으로 둡니다.
- Docker Compose는 `db`, `backend`, `frontend`를 실행합니다.
- Job은 Postgres에 저장하고 FastAPI 내부 asyncio runner가 처리합니다.
- Celery, Redis, GCS, 새 DB, 새 frontend framework는 명시적인 설계 결정 없이
  추가하지 않습니다.
- 모든 job 상태 변경은 `backend/app/state_machine.py`의 transition 경계를 거칩니다.
- asset 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거칩니다.
- 사용자 입력 filename을 파일 경로에 직접 사용하지 않습니다.
- Veo 결과는 기본적으로 inline bytes를 `DATA_DIR`에 저장하는 흐름을 유지합니다.
- Prompt Enhancement는 자동 대체가 아니라 review, edit, accept 가능한 초안입니다.
- 최종 generation prompt의 source of truth는 사용자가 확인한 generation payload입니다.

## 문서 기준

제품과 구현 설명은 다음 문서를 우선 기준으로 삼습니다.

- `README.md`
- `docs/architecture.md`
- `docs/provider-modes.md`
- `docs/job-lifecycle.md`
- `docs/storage-and-assets.md`
- `docs/testing.md`
- `docs/runbooks/local-mock.md`
- `docs/runbooks/vertex-live-qa.md`
- `docs/adr/`

문서를 수정할 때는 현재 코드, env, API contract와 맞춰 씁니다. 과거 맥락을 그대로
옮기기보다 지금 제품을 이해하는 데 필요한 정보만 남깁니다.

## 검증 체크리스트

좁은 검증부터 실행합니다.

Backend:

```bash
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Frontend:

```bash
cd frontend
npm run build
```

Docker Compose:

```bash
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Hygiene:

```bash
git diff --check
git status --short --branch
git diff --cached --name-only
```

명령이 실패하면 첫 번째 구체적인 에러부터 진단합니다. 추측으로 대규모 rewrite를
하지 않습니다.

## 개발 우선순위

1. Repo detox와 문서 정합성을 깨끗하게 유지합니다.
2. mock mode에서 전체 생성 흐름을 빠르고 안정적으로 검증합니다.
3. 실제 Vertex mode의 credential, 비용, 실패 처리를 운영 관점에서 단단하게 만듭니다.
4. 생성 스튜디오 UX를 개선합니다.
5. 작업 라이브러리, 상태 추적, asset 관리, 실패 재시도 경험을 제품화합니다.
6. 관측성, 평가, 배포, 보안은 실제 운영에 필요한 범위부터 단계적으로 추가합니다.

## 작업 방식

- 먼저 현재 코드와 문서를 읽고, 기존 패턴에 맞춰 작게 고칩니다.
- 구현 세부사항이 열려 있으면 가장 보수적이고 검증 가능한 선택을 합니다.
- 기능을 추가할 때는 API contract, DB 상태, frontend 흐름, 테스트를 함께 봅니다.
- 사용자가 한국어로 요청하면 결과 정리도 한국어로 합니다.
- 완료라고 말하기 전에 fresh verification을 실행하고 결과를 확인합니다.
