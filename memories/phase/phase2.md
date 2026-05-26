# Phase 2 — Domain Models and State Machine

## 현재 구조 요약

Phase 2 목표는 Vertex 호출이나 API 라우트 확장이 아니라, 이후 생성 API와 잡 러너가 공유할 백엔드 도메인 기반을 만드는 것이었다.

현재 Phase 2 관련 구조는 다음과 같다.

```text
/home/user/backend/
├── app/
│   ├── models.py
│   ├── schemas.py
│   └── state_machine.py
└── tests/
    └── test_state_machine.py
```

프론트엔드는 수정하지 않았고, Vertex API 초기화나 호출도 추가하지 않았다.

## 생성/수정한 주요 파일

- `backend/app/models.py`
  - SQLAlchemy 모델 `Job`, `Asset`, `PromptEnhancement` 추가.
  - `GenerationMode`, `JobState`, `AssetKind` enum 추가.
  - Postgres UUID, JSONB, enum, timestamp, 관계 설정 추가.
- `backend/app/schemas.py`
  - `T2IRequest`, `T2VRequest`, `I2VRequest` 요청 schema 추가.
  - `GenerationCreate` discriminated union 추가.
  - `JobResponse`/`GenerationResponse`, `AssetResponse`, `PromptEnhancementResponse`, `StateHistoryEntry` 추가.
- `backend/app/state_machine.py`
  - 상태 목록과 허용 전이 매트릭스 추가.
  - `transition()`, `can_transition()`, `normalize_state()` 추가.
  - 잘못된 전이용 `InvalidTransitionError` 추가.
- `backend/tests/test_state_machine.py`
  - 허용 전이/거부 전이 매트릭스 테스트 추가.
  - 상태 이력 기록, timestamp/detail 기록, 기존 이력 보존, 문자열 상태 입력 테스트 추가.

## 구현한 핵심 내용

- 생성 모드는 `t2i`, `t2v`, `i2v`로 정의했다.
- 잡 상태는 `pending`, `enhancing`, `queued`, `generating`, `polling`, `downloading`, `completed`, `failed`, `cancelled`로 정의했다.
- `Job`은 프롬프트, 모델, 상태, enhance 연결, parent/source asset 연결, blocked 플래그, Vertex operation 이름, attempts, `state_history`, error, `vertex_charged`, 생성/수정 시각을 가진다.
- `Asset`은 job 연결, `image`/`video` 종류, 상대 local path, mime, 크기, 이미지/비디오 메타데이터를 가진다.
- `PromptEnhancement`는 원본/개선 프롬프트, components JSON, target mode/model, LLM 모델명, latency/token 메타데이터를 가진다.
- 상태 전이는 `ALLOWED_TRANSITIONS`에 정의된 경로만 허용한다.
- `transition()`은 상태 변경 시 `state_history`에 `{state, at, detail}` 형태로 이력을 append하고 `updated_at`을 갱신한다.
- terminal state는 `completed`, `failed`, `cancelled`이며, 이 상태에서 다른 상태로 나가는 전이는 허용하지 않는다.

## 검증한 명령과 결과

- `python3 -m compileall app`
  - 통과. `models.py`, `schemas.py`, `state_machine.py` 컴파일 성공.
- `.venv/bin/python -m pytest tests/test_state_machine.py`
  - 통과. `85 passed`.
- `DATA_DIR=<temp-data-dir> PYTHONPATH=. .venv/bin/python -c "import app.main; print('backend import ok')"`
  - 통과. FastAPI `app.main:app` import 성공.
- `PYTHONPATH=. .venv/bin/python -c "import app.models; import app.schemas; import app.state_machine; print('domain import ok')"`
  - 통과. 도메인 모듈 import 성공.

## 커밋 해시와 커밋 메시지

- `7e7a0640a8e0d96c86ad9b148294e4e66233d9d0`
  - `feat: add generation domain models and state machine`

## 다음 Phase에서 이어받을 때 주의할 점

- 모든 잡 상태 변경은 `app/state_machine.py`의 `transition()`을 통해 처리해야 한다.
- Phase 2는 모델 정의만 추가했으며, 테이블 생성이나 migration 흐름은 아직 연결하지 않았다.
- `polling`은 Veo 계열 LRO 처리에 사용할 상태로 의도되어 있다. Imagen 흐름에서는 진입하지 않도록 후속 핸들러에서 주의해야 한다.
- `state_history`는 FE 타임라인과 디버깅에 쓰일 데이터이므로 상태 전이 detail을 JSON 직렬화 가능한 값으로 유지해야 한다.
- Vertex 호출, 인증 초기화, 프론트 UI 확장은 이 Phase에 포함하지 않았다.
