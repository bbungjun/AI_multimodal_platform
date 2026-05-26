# Phase 1 — Runnable Health Skeleton

## 현재 구조 요약

Phase 1 목표는 전체 MVP 구현이 아니라 `docker compose up` 기준으로 `db`, `backend`, `frontend`가 뜰 수 있는 최소 실행 뼈대를 만드는 것이었다.

현재 구조는 기존 루트 구조를 유지한다.

```text
/home/user/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   └── api/health.py
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── index.css
│       └── api/client.ts
└── docker-compose.yml
```

Vertex API 초기화나 호출은 아직 넣지 않았다. 인증 키는 compose mount 설정만 기존대로 유지했다.

## 생성/수정한 주요 파일

- `backend/app/config.py`
  - `pydantic-settings` 기반 최소 설정 추가.
  - `DATABASE_URL`, `DATA_DIR`, CORS origin 기본값 제공.
- `backend/app/db.py`
  - SQLAlchemy async engine, session factory, `check_db_connection()` 추가.
  - `/api/health`에서 DB ping을 수행하도록 구성.
- `backend/app/api/health.py`
  - `GET /api/health` 엔드포인트 추가.
  - 응답 예: `{ "ok": true, "service": "backend", "db": "up" }`
- `backend/app/main.py`
  - FastAPI `app` 생성.
  - CORS middleware 추가.
  - startup/lifespan에서 `DATA_DIR` 생성.
  - shutdown에서 DB engine dispose.
- `frontend/index.html`, `frontend/vite.config.ts`, `frontend/tsconfig.json`
  - Vite React 진입 설정 추가.
- `frontend/src/api/client.ts`
  - `VITE_API_BASE` 기준으로 `/api/health` 호출하는 fetch wrapper 추가.
- `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/index.css`
  - Health check 화면 추가.
  - API 연결 상태와 DB 상태를 표시.
  - 5초마다 `/api/health` 재조회.
- `docker-compose.yml`
  - 기존 서비스 구조는 유지.
  - `.env`가 없어도 실행될 수 있도록 Postgres, backend, frontend 환경변수 기본값 보강.

## 검증한 명령과 결과

- `python3 -m compileall backend/app`
  - 통과. Python syntax/import 대상 파일 컴파일 성공.
- `PYTHONPATH=. DATA_DIR=/tmp/assets .venv/bin/python -c "import app.main; print('backend import ok')"`
  - 통과. FastAPI `app.main:app` import 성공.
- `/api/health` 핸들러 직접 호출 테스트
  - DB check 함수를 monkeypatch한 상태에서 `{'ok': True, 'service': 'backend', 'db': 'up'}` 형태 응답 확인.
- `npm install --no-package-lock`
  - 통과. frontend 의존성 설치 완료.
  - `package-lock.json`은 생성하지 않음.
- `npm run build`
  - 통과. TypeScript compile + Vite production build 성공.
- `docker-compose config`
  - 통과. compose 설정이 정상적으로 resolve됨.

## docker-compose up 검증이 막힌 이유

`docker-compose up --build -d`는 코드 문제가 아니라 로컬 Docker 환경 문제로 막혔다.

- 현재 환경의 `docker-compose`는 v1 `1.29.2`.
- 실행 시 Python Docker client 계층에서 `Not supported URL scheme http+docker` 에러 발생.
- `docker compose` v2 plugin은 설치되어 있지 않음.
- `docker version` 확인에서도 Docker daemon socket 접근이 permission denied로 제한됨.

따라서 실제 컨테이너 3개가 동시에 뜨는지까지는 이 환경에서 검증하지 못했다. 대신 compose config, backend import, frontend build까지 확인했다.

## 다음 Phase 2에서 이어받을 때 주의할 점

- Health endpoint는 `/api/health` 하나만 사용한다. `/health` 호환 경로는 남기지 않았다.
- `backend/app/db.py`는 아직 모델 생성이나 migration을 수행하지 않는다. Phase 2에서 `models.py`, `Base.metadata.create_all`, 또는 Alembic 도입 여부를 정해야 한다.
- `check_db_connection()`은 실제 Postgres가 붙는 compose 환경에서 최종 확인이 필요하다.
- Vertex 관련 코드는 아직 없어야 한다. Phase 2에서도 도메인 모델/상태머신 중심으로 진행하고, Vertex 호출은 Phase 4 이후로 유지한다.
- `node_modules`, `frontend/dist`, `backend/.venv`, `__pycache__`는 검증 과정에서 생긴 로컬 산출물이다. `.gitignore` 대상이므로 제출/커밋 대상이 아니다.
- Docker 검증은 가능하면 docker compose v2가 있는 환경이나 daemon 권한이 정상인 환경에서 다시 수행해야 한다.
