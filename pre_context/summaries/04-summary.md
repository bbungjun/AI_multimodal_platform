# krafton_assignment_04 요약

## 핵심 주제

Git object corruption으로 원래 repo의 Git 기반 확인이 불안정해진 상태에서, Phase 7 Imagen T2I 작업 흔적을 파일 내용 기준으로 읽어 복구 가치를 판단한 세션입니다. 복구 시에는 Git 명령 결과보다 실제 파일 내용과 테스트 의도를 우선해야 한다는 판단 근거로 사용합니다.

## 주요 키워드

- Git object corruption, `git fsck --full`, corrupt/missing loose object
- dirty working tree, recovery snapshot, direct file inspection
- Phase 7 Imagen T2I, `generations.py`, `imagen.py`, `handle_t2i`
- `backend/tests/test_t2i_flow.py`, mock Vertex, no real Vertex call
- `backend/app/main.py` router include 누락
- `/files/...` hang, StaticFiles, ASGITransport
- Phase 4~6 기반 구현 흔적, Vertex client, retry/rate limit, job runner

## 복구에 중요한 내용

- 이 시점의 문제는 앱 코드 자체보다 `/home/user/.git/objects` 손상입니다. `git diff --stat`, 새 worktree checkout, 일부 Git 확인이 신뢰하기 어려운 상태였으므로 파일을 직접 읽어 판단했습니다.
- dirty working tree에는 Phase 7 관련 파일들이 남아 있었습니다. 특히 `backend/app/api/generations.py`, `backend/app/services/vertex/imagen.py`, `backend/tests/test_t2i_flow.py`는 단순 메모가 아니라 실제 T2I 흐름 구현에 가까운 자료로 평가되었습니다.
- `generations.py`는 `POST /api/generations`, 목록, 상세 조회를 구현했고, Phase 7 범위 밖인 `t2v`, `i2v`, `auto_enhance`, `enhancement_id`는 501로 막는 구조였습니다.
- `imagen.py`는 `google-genai` 단일 SDK, `GenerateImagesConfig`, `asyncio.to_thread`, `client.models.generate_images`, bytes 추출, Vertex error mapping을 사용하는 방향이었습니다.
- `test_t2i_flow.py`는 실제 Vertex 호출 없이 `handlers.imagen.generate_image`와 rate limiter를 monkeypatch해 API 생성 -> runner/handler -> storage/asset -> detail/list 흐름을 검증했습니다.
- 중요한 누락은 `backend/app/main.py`에 `generations` router include가 없었다는 점입니다. 복구 시 `/api/generations`가 실제 앱에 연결되는지 반드시 확인해야 합니다.
- `/files/...` 직접 GET 테스트는 hang 위험이 있었고, 테스트에서는 URL 형태와 storage에 저장된 bytes를 직접 검증하는 쪽이 안전하다는 결론이 남았습니다.
- Phase 4~6 기반으로 보이는 구현 흔적도 회수되었습니다. Vertex client 설정, retry/rate limit, in-process runner skeleton, missing DB toleration 등이 이후 복구 판단의 기준입니다.

## 원문에서 찾아볼 위치

- Git object corruption과 읽기 전용 판단: 대략 137~181, 347~450
- Git 명령보다 파일 직접 확인을 우선한 판단: 대략 499~681
- health route `/api/health` prefix 판단: 대략 977~1108
- Phase 7 파일 목록과 조사 기준: 대략 1188~1232, 1374~1429
- `generations.py`, `imagen.py`, `test_t2i_flow.py` 조사 결과: 대략 1440~1476
- Phase 7 복구 판단 요약: 대략 1489~1496
- 회수된 Phase 4~6 계열 구현 메모: 대략 2294~2312

## 복구 판단 메모

- 현재 프로젝트에서 T2I가 깨졌다면 `generations.py`, `imagen.py`, `handle_t2i`, `test_t2i_flow.py`를 가장 먼저 대조합니다.
- Git 이력 대신 `pre_context`의 파일 내용과 현재 로컬 파일을 비교하는 방식이 안전합니다.
- `main.py` router wiring은 작은 차이지만 실제 API 노출 여부를 결정하므로 복구 우선순위가 높습니다.
- T2I 테스트를 보강할 때는 상세 404, Vertex 실패 -> job failed/public error 기록, list filter/pagination을 후속 후보로 봅니다.
