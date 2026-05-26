# Phase 7 Imagen T2I Failed Attempt

- 기준 커밋: `9a83dbc fix: make job runner tolerate missing database`
- 기존 작업트리: `/home/user` on `master`
- 새 작업트리: `/tmp/krafton-phase7-imagen-t2i` on `phase7-imagen-t2i`

## 실패 원인

- Phase 7 범위를 한 번에 크게 잡음
- `rg: command not found`
- 잘못된 pytest 경로
- `ImportError: cannot import name 'generations' from 'app.api'`
- `/files/...` 직접 GET 검증 중 StaticFiles / anyio threadpool 경로에서 timeout
- Docker 관련 명령은 이번 문제 해결에 도움 되지 않음

## 재시작 전략

- 새 worktree에서 TDD 방식으로 진행
- 먼저 mock Imagen 기반 pytest 1개 작성
- 실제 Vertex 호출 금지
- `/files/...` 실제 GET은 최소 테스트에서 제외
- asset url 형식, storage bytes, `/files` mount 존재만 검증
