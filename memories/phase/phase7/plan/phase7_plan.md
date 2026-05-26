# Phase 7 Imagen T2I clean worktree 기준 구현 계획

## 기준 상태

- 실제 작업 cwd: `/tmp/krafton-phase7-imagen-t2i`
- 실제 작업 브랜치: `phase7-imagen-t2i`
- 기준 커밋: `9a83dbc`
- 현재 `git status --short`: clean
- 새 worktree 기준 Phase 7 구현은 아직 시작하지 않은 상태다.
- 이전 문서의 dirty 변경분, 구현 상태 OK, `145 passed` 내용은 `/home/user` master의 이전 WIP 관찰 결과였으므로 현재 구현 근거로 사용하지 않는다.
- 이 문서는 clean worktree에서 Phase 7을 작은 단위로 TDD 구현하기 위한 계획이다.

## 진행 원칙

- Phase 7은 작은 작업 단위로 진행한다.
- 한 번에 구현, 테스트, 커밋까지 모두 진행하지 않는다.
- 각 기능 단위는 테스트를 먼저 작성하고, 그 테스트를 통과시키는 최소 구현으로 진행한다.
- 실제 Vertex 호출은 Phase 7 자동 테스트 범위에 포함하지 않는다.
- production code 구현 전에는 해당 기능 단위의 mock 기반 테스트 의도를 먼저 명확히 한다.

## 구현 후 추가 검증 테스트

- Job 상세 조회 404 테스트 1개
- Imagen/Vertex 실패 시 Job이 `failed` 상태와 public error를 기록하는 테스트 1개

## 1. Job 생성 API

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/app/api/generations.py`
  - `backend/app/main.py`
  - `backend/app/schemas.py`
  - `backend/app/models.py`
- 확인해야 할 핵심 동작
  - `POST /api/generations`가 `mode=t2i` 요청을 받는다.
  - 생성된 Job은 `pending` 상태로 저장된다.
  - Imagen 모델만 허용한다.
  - `aspect_ratio`, `number_of_images` 같은 T2I 실행 파라미터를 Job에 보존한다.
  - `auto_enhance` 또는 `enhancement_id` 요청은 Phase 7 범위 밖이므로 명확히 거부한다.
- 최소 구현 방향
  - 먼저 mock DB/session 기반 API 테스트에서 T2I Job 생성 응답을 검증한다.
  - `generations` router를 추가하고 `main.py`에 연결한다.
  - T2V/I2V와 enhance는 이번 Phase에서 구현하지 않고 명시적으로 `501` 또는 validation error로 막는다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests/test_t2i_flow.py`

## 2. Job 상세 조회 API

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/app/api/generations.py`
  - `backend/app/schemas.py`
- 확인해야 할 핵심 동작
  - `GET /api/generations/{id}`가 Job과 연결된 Asset을 함께 반환한다.
  - 없는 Job은 `404`를 반환한다.
  - Asset 응답에는 `/files/{local_path}` 형식의 `url`이 포함된다.
- 최소 구현 방향
  - 먼저 생성된 Job 상세 조회 happy path를 mock T2I flow 테스트에 포함한다.
  - 구현 후 추가 검증 테스트로 상세 조회 404 테스트 1개를 추가한다.
  - Asset 응답 shape은 기존 `AssetResponse`에 computed `url`을 추가하는 방식으로 최소화한다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests/test_t2i_flow.py`

## 3. Job 목록 조회 API 최소 버전

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/app/api/generations.py`
- 확인해야 할 핵심 동작
  - `GET /api/generations`가 최신순 Job 목록을 반환한다.
  - 최소 버전은 `mode`, `model`, `state`, `limit`, `offset` 쿼리 파라미터를 받는다.
  - 목록 응답에도 연결 Asset을 포함할 수 있어야 한다.
- 최소 구현 방향
  - 먼저 기본 목록 조회가 생성된 Job을 반환하는 테스트를 mock T2I flow에 포함한다.
  - 필터/pagination 상세 테스트는 Phase 7 커밋 전 추가 검증 범위에 넣지 않고 후속 QA로 이월한다.
  - 구현은 SQLAlchemy `select(Job)`와 `selectinload(Job.assets)` 기반으로 단순하게 시작한다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests/test_t2i_flow.py`

## 4. Imagen service

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/app/services/vertex/imagen.py`
  - `backend/app/services/vertex/errors.py`
- 확인해야 할 핵심 동작
  - `generate_image()`가 `google-genai` 단일 SDK를 사용한다.
  - `client.models.generate_images` 호출은 `asyncio.to_thread`로 감싼다.
  - `types.GenerateImagesConfig`에 `number_of_images`, `aspect_ratio`를 전달한다.
  - 응답의 `generated_images[*].image.image_bytes`를 추출한다.
  - 생성 이미지가 없으면 Vertex public error 계열로 처리한다.
  - Google SDK 예외는 기존 Vertex error mapping을 통해 public error로 변환한다.
- 최소 구현 방향
  - 실제 Vertex 호출 테스트는 작성하지 않는다.
  - handler 테스트에서는 `imagen.generate_image`를 monkeypatch해 bytes를 반환하게 한다.
  - `_extract_image_bytes` 단위 테스트는 후속 QA로 이월한다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests/test_t2i_flow.py backend/tests/test_vertex_errors.py`

## 5. runner `handle_t2i`

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/app/services/jobs/handlers.py`
  - `backend/app/services/jobs/runner.py`
  - `backend/app/state_machine.py`
- 확인해야 할 핵심 동작
  - Phase 6 runner가 `pending` Job을 `queued`로 전이한 뒤 handler를 실행한다.
  - `handle_t2i`는 `queued` 시작 상태를 정상 경로로 처리한다.
  - 직접 handler 호출 테스트가 필요하더라도, 기본 경로는 runner가 `pending -> queued`로 전이한 뒤 `handle_t2i`를 호출하는 구조를 유지한다.
  - handler는 rate limit acquire 후 `generating`으로 전이한다.
  - Imagen 호출은 `with_retry`로 감싼다.
  - 성공 시 `vertex_charged=true`를 설정하고 `downloading`으로 전이한다.
  - 이미지 bytes 저장과 Asset 생성 후 `completed`로 전이한다.
  - 실패 시 Job이 `failed` 상태와 public error를 기록한다.
- 최소 구현 방향
  - 먼저 mock Imagen happy path 테스트를 작성한다.
  - runner pickup부터 handler 완료까지 한 테스트에서 state history, attempts, asset, stored bytes를 확인한다.
  - 구현 후 추가 검증 테스트로 Imagen/Vertex 실패 시 failed/public error 기록을 확인한다.
  - 모든 상태 변경은 계속 `transition(...)`을 경유한다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests/test_t2i_flow.py backend/tests/test_job_runner.py backend/tests/test_retry.py backend/tests/test_state_machine.py`

## 6. storage / Asset 연동

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/app/services/storage.py`
  - `backend/app/services/jobs/handlers.py`
  - `backend/app/models.py`
  - `backend/app/schemas.py`
- 확인해야 할 핵심 동작
  - 생성된 PNG bytes가 `DATA_DIR/{job_uuid}/output.png`에 저장된다.
  - Asset row에는 `kind=image`, `mime=image/png`, `size_bytes`, `local_path`가 기록된다.
  - 응답 `url`은 `/files/{job_uuid}/output.png` 형식이다.
  - 저장 경로는 기존 storage path safety 규칙을 거친다.
- 최소 구현 방향
  - 기존 storage service를 재사용하고, handler에서 사용자 입력 filename을 받지 않는다.
  - `/files/...` 직접 GET 테스트는 이전 timeout 이슈가 있었으므로 Phase 7 테스트에서는 제외한다.
  - mount 존재, `storage.read_bytes()`, Asset 응답 검증으로 대체한다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests/test_storage.py backend/tests/test_t2i_flow.py`

## 7. mock Vertex 기반 테스트 / QA

- 구현 상태: 미구현 / 구현 예정
- 관련 파일
  - `backend/tests/test_t2i_flow.py`
- 확인해야 할 핵심 동작
  - 실제 Vertex 호출 없이 mock Imagen으로 검증한다.
  - API 생성, runner pickup, handler 실행, storage 저장, 상세 조회, 목록 조회가 한 흐름으로 검증된다.
  - 전체 백엔드 회귀 테스트가 통과한다.
- 최소 구현 방향
  - 먼저 `test_t2i_flow.py`를 작성해 실패하는 테스트를 만든다.
  - Fake session/factory는 Phase 6 `test_job_runner.py` 패턴을 참고한다.
  - `handlers.imagen.generate_image`와 rate limiter는 monkeypatch한다.
  - 테스트가 green이 된 뒤에만 다음 기능 단위로 넘어간다.
- 커밋 전 실행할 테스트
  - `backend/.venv/bin/pytest backend/tests`

## 커밋 전 남은 리스크

- 브랜치 리스크
  - 실제 작업 브랜치는 `phase7-imagen-t2i`여야 한다.
  - 커밋 전 `/tmp/krafton-phase7-imagen-t2i`에서 `git branch --show-current`를 다시 확인한다.
- DB schema 리스크
  - T2I 실행 파라미터를 Job에 저장하는 schema 변경이 필요할 수 있다.
  - fresh DB에서는 `create_all` 기반으로 검증할 수 있지만, 기존 로컬 Postgres 볼륨 migration 전략은 후속 QA로 이월한다.
- 테스트 커버리지 리스크
  - 커밋 전 구현 후 추가 검증 테스트는 상세 404와 Vertex 실패 경로 테스트로 제한한다.
  - 목록 필터/pagination 상세 테스트는 후속 QA로 이월한다.
- 실제 Vertex 리스크
  - 실제 Imagen 호출은 자동 테스트에서 제외한다.
  - 실제 1회 수동 QA는 비용과 credential 노출 위험을 고려해 후속 QA로 분리한다.

## 전체 커밋 전 체크리스트

- [ ] `/tmp/krafton-phase7-imagen-t2i`에서 작업 중인지 확인한다.
- [ ] 현재 브랜치가 `phase7-imagen-t2i`인지 확인한다.
- [ ] Phase 7 테스트를 먼저 작성한다.
- [ ] 테스트를 통과시키는 최소 구현만 진행한다.
- [ ] 구현 후 추가 검증 테스트를 추가한다: Job 상세 조회 404 테스트 1개.
- [ ] 구현 후 추가 검증 테스트를 추가한다: Imagen/Vertex 실패 시 Job이 `failed` 상태와 public error를 기록하는 테스트 1개.
- [ ] `backend/.venv/bin/pytest backend/tests`를 실행한다.
- [ ] `git status --short`로 변경 파일을 확인한다.
- [ ] staging 후 `git diff --cached --name-only`로 커밋 대상 파일을 확인한다.
- [ ] credentials, `.env`, generated artifacts, `__pycache__`, data assets가 staged 대상에 없는지 확인한다.
- [ ] Phase 7 범위 밖인 Enhance, T2V, I2V, pipeline, 실제 Vertex 호출 자동화는 이번 커밋에 포함하지 않는다.

## 다음 Phase / 후속 QA로 이월

- Job 목록 조회의 필터/pagination 상세 테스트
- `_extract_image_bytes` 단위 테스트
- 실제 Vertex Imagen 1회 수동 QA
- 기존 로컬 Postgres 볼륨 대상 migration 전략
- Enhance, T2V, I2V, pipeline 확장
