# krafton_assignment_07 요약

## 핵심 주제

Phase 12 Docker Compose / integration readiness, Phase 13 API contract alignment, Phase 14 Live UX QA 진입까지 이어진 세션입니다. 복구 시 Docker/compose 설정, `/files` serving, frontend API proxy, OpenAPI 기준 타입 정합, 실제 T2I Live QA 성공/실패 흐름을 확인하는 핵심 자료입니다.

## 주요 키워드

- Phase 12 Docker Compose readiness
- `.env.example`, `docker-compose.yml`, backend/frontend `.dockerignore`
- `/files` asset serving, backend runtime init
- `VITE_API_BASE`, `VITE_API_PROXY_TARGET`, same-origin `/api`/`/files` proxy
- Compose smoke, `/api/health`, health response schema
- Phase 13 API contract alignment, OpenAPI, Swagger, `HealthResponse`
- Phase 14 Live UX QA, Vite/E2B allowed host, T2I actual Imagen
- `JobResponse.assets` lazy-load, `MissingGreenlet`

## 복구에 중요한 내용

- 세션 초반 기준으로 Phase 9 Prompt Enhance backend, Phase 10 T2I -> I2V pipeline backend, Phase 11 frontend required flows가 완료된 상태로 보고되었습니다. 마지막 frontend build/lint는 passed, backend full regression은 통과한 상태였습니다.
- Phase 12 Unit 1은 compose env/build hygiene입니다. `.env.example`, `docker-compose.yml`, backend/frontend `.dockerignore`를 정리했고, 빈 env일 때 mandatory value 오류가 의도대로 발생하는지와 `.env.example` 기준 compose config가 통과하는지 확인했습니다.
- `frontend/src/index.css`에 accidental dirty change가 있었고, pipeline CSS 삭제 및 stray text가 섞여 있어 Phase 12 Unit 2 전에 정리 대상으로 판단했습니다. 이는 복구 시 현재 CSS가 이상할 경우 중요한 단서입니다.
- Phase 12 Unit 2는 backend runtime init + `/files` asset serving입니다. `backend/app/api/files.py`가 주요 파일로 등장하며, `/files` path safety와 asset serving 테스트가 복구 확인 대상입니다.
- Phase 12 Unit 3은 frontend compose API readiness입니다. 핵심은 compose/public URL 환경에서 브라우저가 `localhost:8000`에 직접 붙지 않게 하는 것입니다. `VITE_API_BASE`는 기본 빈 값, `VITE_API_PROXY_TARGET=http://backend:8000`가 compose 내부 proxy target으로 정리되었습니다.
- Phase 12 Unit 4 compose smoke는 처음에는 Docker Compose v2/daemon 문제로 blocked로 문서화되었지만, 이후 실제 compose smoke까지 진행되었습니다. 확인 범위는 db healthy, backend/frontend up, backend `/api/health`, frontend proxy `/api/health`, backend `/files`, frontend proxy `/files`였습니다.
- Compose smoke 중 `/api/health` 500이 발견되었고, root cause는 health route 응답 shape와 `HealthResponse` schema 불일치였습니다. 복구 시 `backend/app/api/health.py`, `backend/app/schemas.py`, `backend/tests/test_health.py`를 같이 확인해야 합니다.
- Phase 13은 FastAPI `/docs`와 `/openapi.json`을 source of truth로 삼되, `openapi-typescript` 같은 codegen은 범위가 커서 보류하고 수동 정합으로 진행했습니다.
- Phase 13 Unit 1은 frontend `HealthResponse`/`VertexReadinessResponse` 타입 정합입니다. Unit 2 audit에서는 실제 runtime/API 연동 위험인 `fix now` 후보가 없다고 판단했고, OpenAPI/docs issue들은 후속 문서 보강 후보로 넘겼습니다.
- Phase 13 contract smoke는 `/openapi.json` 200 JSON parse OK 등을 확인했습니다. 복구 시 OpenAPI 접근 가능성과 frontend API type drift를 확인하는 기준입니다.
- Phase 14 Live UX QA 계획은 실제 브라우저 UI에서 Vertex-backed Gemini/Imagen/Veo 호출까지 포함하는 단계로 정리되었습니다. 자동 테스트에서는 계속 실제 Vertex/Gemini/Imagen/Veo 호출 금지입니다.
- Phase 14 초기에 Vite/E2B public host 차단이 있었고, Vite allowed host 설정으로 해결하는 방향이 잡혔습니다. 복구 시 `vite.config.ts`나 frontend dev server host 설정을 확인합니다.
- T2I Generate 클릭 시 `POST /api/generations` 500이 발생했습니다. 원인은 `JobResponse.assets` 직렬화 중 SQLAlchemy async lazy-load가 발생해 `MissingGreenlet`이 난 것으로 판단되었습니다. 이 bugfix 상세는 `08-summary.md`가 더 직접적입니다.
- 이후 실제 Text to image Live QA가 성공했습니다. 사용자는 한국어 고양이 프롬프트로 실제 PNG 생성, Job Detail 렌더링, `/files` asset serving, `Use as I2V source` 버튼 표시까지 확인했습니다.

## 원문에서 찾아볼 위치

- Phase 9~11 완료 상태와 Phase 12 리스크: 대략 144~173
- Phase 12 계획/Unit 1: 대략 215~339
- `frontend/src/index.css` accidental dirty change 판단: 대략 387~856
- Phase 12 Unit 2 `/files` serving: 대략 885~1259
- Phase 12 Unit 3 frontend API proxy: 대략 1264~1386
- Phase 12 Unit 4 compose smoke discovery/blocked: 대략 1389~1839
- 실제 compose smoke, `/api/health` schema bug, `/files` proxy pass: 대략 1900~3386
- Phase 13 OpenAPI/API contract alignment: 대략 4663~6059
- Phase 14 plan, Vite host, lazy-load 500, T2I success: 대략 6102~7602

## 복구 판단 메모

- 현재 복구 프로젝트에서 compose/public URL API가 이상하면 `VITE_API_BASE=`와 `VITE_API_PROXY_TARGET=http://backend:8000` 방향을 먼저 확인합니다.
- `/api/health`는 단순 route 문제가 아니라 response model shape mismatch가 있었던 이력이 있으므로 `schemas.py`와 `health.py`를 같이 봅니다.
- Phase 13은 OpenAPI codegen 도입이 아니라 수동 타입 정합이 원래 방향입니다.
- T2I actual Live QA는 과제의 강한 성공 증거입니다. 다만 당시 job/asset id보다 중요한 것은 frontend -> backend -> actual Imagen -> local asset -> `/files` -> Job Detail 렌더링 흐름이 끝까지 통과했다는 점입니다.
