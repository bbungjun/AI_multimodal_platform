# Phase 4 — Vertex Client Configuration

## 현재 구조 요약

Phase 4 목표는 실제 Imagen/Veo/Gemini 생성 호출이 아니라, `google-genai` 클라이언트와 인증 readiness, 예외 매핑 기반을 만드는 것이었다.

현재 Phase 4 관련 구조는 다음과 같다.

```text
/home/user/backend/
├── app/
│   ├── api/
│   │   └── health.py
│   ├── config.py
│   └── services/
│       └── vertex/
│           ├── client.py
│           └── errors.py
└── tests/
    ├── test_health.py
    ├── test_vertex_client.py
    └── test_vertex_errors.py
```

Vertex 실제 생성 API 호출은 추가하지 않았다. 테스트도 서비스 계정 파일이나 Vertex 네트워크 호출 없이 monkeypatch 기반으로 검증했다.

## 생성/수정한 주요 파일

- `backend/app/config.py`
  - `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `GCP_LOCATION`, `ENHANCE_MODEL` 설정 추가.
  - 빈 문자열 env 값을 `None`으로 정규화하는 validator 추가.
- `backend/app/services/vertex/client.py`
  - `get_vertex_client()` 싱글톤 추가.
  - service-account credential 로드, project id 해석, location 검증 추가.
  - `VertexReadiness`와 `get_vertex_readiness()` 추가.
- `backend/app/services/vertex/errors.py`
  - Vertex 설정/인증/권한/요청/safety/rate limit/transient/unknown 예외 클래스 추가.
  - `map_vertex_error()`로 google-genai 예외와 일반 예외를 공개 가능한 내부 예외로 매핑.
- `backend/app/api/health.py`
  - `/api/health` 응답에 `ready`와 `vertex` readiness 필드 추가.
  - 기존 `ok`는 DB/API 연결 상태 의미를 유지하고, 전체 readiness는 `ready`로 분리.
- `backend/tests/test_vertex_client.py`
  - credential file 로딩, project override, missing credential, missing project, public readiness 테스트 추가.
- `backend/tests/test_vertex_errors.py`
  - 429, 401, 503, safety block, unknown error 매핑 테스트 추가.
- `backend/tests/test_health.py`
  - health 응답에 vertex readiness가 포함되는지 검증.

## 구현한 핵심 내용

- Vertex 클라이언트는 `genai.Client(vertexai=True, credentials=..., project=..., location=...)` 형태로 생성한다.
- credential은 `GOOGLE_APPLICATION_CREDENTIALS` 경로의 service-account JSON에서 로드하되, 경로나 파일 내용은 health 응답에 노출하지 않는다.
- `GCP_PROJECT_ID`가 있으면 우선 사용하고, 없으면 credential의 `project_id`를 사용한다.
- readiness 응답은 `ready`, `status`, `credentials`, `project`, `location` 같은 공개 가능한 상태값만 반환한다.
- `/api/health`는 `{ok, ready, service, db, vertex}` 구조로 확장했다.
- Vertex rate limit/transient 예외는 `retryable=True`로 표시해 Phase 5 retry 유틸에서 활용할 수 있게 했다.

## 검증한 명령과 결과

- `python3 -m compileall app`
  - 통과. `config.py`, `api/health.py`, `services/vertex/client.py`, `services/vertex/errors.py` 컴파일 성공.
- `.venv/bin/python -m pytest tests/test_vertex_client.py tests/test_vertex_errors.py tests/test_health.py`
  - 통과. `14 passed`.
- `.venv/bin/python -m pytest`
  - 통과. `116 passed`.
- `DATA_DIR=/tmp/codex-phase4-assets PYTHONPATH=. .venv/bin/python -c "import app.main; print('backend import ok')"`
  - 통과. FastAPI `app.main:app` import 성공.

## 커밋 해시와 커밋 메시지

- `b6b362757460736609e0390991d93d019c551261`
  - `feat: add vertex client configuration`

## 다음 Phase에서 이어받을 때 주의할 점

- Phase 4는 클라이언트 생성과 readiness 기반만 만든 단계다. Imagen/Veo/Gemini 생성 호출은 아직 구현하지 않았다.
- 테스트에서 실제 Vertex 호출이나 서비스 계정 파일 읽기를 하면 안 된다. `app/services/vertex/*`는 mock 또는 monkeypatch로 검증해야 한다.
- health 응답에는 credential path나 파일 내용, project secret, env 값 같은 민감 정보를 추가하지 않는다.
- 후속 Vertex 호출 구현은 `map_vertex_error()` 결과를 사용해 retry 가능 여부와 공개 에러 응답을 분리해야 한다.
- `get_vertex_client()`는 LRU cache를 사용하므로 테스트에서는 `get_vertex_client.cache_clear()`가 필요하다.
