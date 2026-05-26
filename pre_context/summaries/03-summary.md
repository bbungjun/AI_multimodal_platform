# krafton_assignment_03 요약

## 핵심 주제

Phase 7 Imagen Text-to-Image 구현을 Codex CLI에 어떻게 맡길지 조정하고,
초기 dirty working tree 문제와 `/files/...` 테스트 hang 문제를 다룬 세션입니다.
복구 시에는 T2I API, `imagen.py`, `handle_t2i`, `test_t2i_flow.py`를 복구하는
가장 직접적인 근거로 사용합니다.

## 주요 키워드

- Phase 7, Imagen Text-to-Image, T2I
- `backend/app/services/vertex/imagen.py`
- `backend/app/api/generations.py`
- `backend/app/services/jobs/handlers.py::handle_t2i`
- `backend/tests/test_t2i_flow.py`
- `storage.save_bytes`, Asset row, `/files/{job_id}/output.png`
- mock Vertex, monkeypatch, 실제 Vertex 호출 금지
- `/files/...` GET hang, Starlette StaticFiles, ASGITransport
- git worktree, `phase7-imagen-t2i`, `/tmp/krafton-phase7-imagen-t2i`

## 복구에 중요한 내용

- Phase 7 목표는 Imagen T2I 생성 flow 구현입니다.
- 작업 범위는 `imagen.py`, `generations.py`, runner의 `handle_t2i`, Job 생성/상세/목록
  API 최소 버전, 생성 bytes 저장, Asset row 생성, `/files/...` URL 구조입니다.
- 테스트는 실제 Vertex 호출 없이 `handlers.imagen.generate_image` 또는 동등한 경계를
  fake로 monkeypatch해야 합니다.
- 초기에 `app.api.generations` import 실패가 있었고, 이후 `/files/...` 실제 GET 검증이
  테스트 환경에서 hang을 일으켰습니다.
- 해결 방향은 `/files/...`에 직접 GET하지 않고 다음을 검증하는 것입니다.
  - asset 응답의 `url`이 `/files/{job_id}/output.png` 형태인지 확인
  - storage에 저장된 bytes를 직접 읽어 mock Imagen bytes와 같은지 확인
  - app에 `/files` mount가 존재하는지만 최소 확인
- dirty working tree에서 크게 이어가기보다, 작업 기준점을 새로 잡고 별도 worktree에서
  Phase 7을 작게 다시 시작하는 전략이 선택됩니다.
- Phase 7 핵심 상태 흐름은 T2I 기준 `queued -> generating -> downloading -> completed`이며,
  Imagen은 `polling`에 들어가면 안 됩니다.

## 원문에서 찾아볼 위치

- Phase 7 전제와 구현 범위 초안: 대략 29~146
- 큰 프롬프트가 너무 넓다는 문제 분석: 대략 165~186
- dirty 파일 목록과 첫 실패 보고: 대략 214~300
- `/files/...` GET hang 우회 지시: 대략 328~364
- clean worktree 재시작 판단: 대략 411~449
- 실패하는 테스트부터 시작하는 TDD 지시: 대략 457~474
- dirty checkout 보존 + 새 worktree 전략: 대략 559~618
- worktree 생성 결과: 대략 948~972
- 새 worktree Phase 7 핵심 제약 5개: 대략 1026~1045

## 복구 판단 메모

- 현재 복구에서 T2I flow가 깨졌거나 `generations.py`, `imagen.py`,
  `test_t2i_flow.py`가 빠져 있으면 이 파일을 우선 참조합니다.
- `/files/...` 직접 GET 테스트를 되살리면 다시 hang 위험이 있으므로, storage bytes와
  URL/mount 검증으로 대체하는 방향을 유지하는 것이 안전합니다.
- “실제 Vertex 호출 금지”와 “mock Imagen 경계 유지”는 이 세션의 핵심 안전장치입니다.
