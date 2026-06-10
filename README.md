# CreativeOps Studio

CreativeOps Studio는 이미지, 비디오, 이미지 기반 비디오 파이프라인을 만들고 각 작업의 운영 상태까지 확인할 수 있는 개인용 AI 크리에이티브 워크스페이스입니다. 겉으로는 생성 스튜디오처럼 쓰고, 내부는 상태 기반 job 처리와 Vertex AI 연동을 갖춘 FastAPI 백엔드로 동작합니다.

지원 기능:

- Imagen text-to-image 생성
- Veo text-to-video 생성
- Veo image-to-video 생성
- Gemini 기반 prompt enhancement 초안 생성
- T2I -> I2V 파이프라인 job
- job history, 상세 timeline, 생성 asset preview, provider readiness 확인

## 아키텍처

```text
React/Vite frontend
  -> FastAPI backend
    -> PostgreSQL jobs, assets, prompt records, and outbox events
    -> Local DATA_DIR file streaming
Outbox dispatcher process
  -> publishes job ids from Postgres outbox to Redis/Celery
Celery worker process
  -> claims pending jobs from Postgres
    -> Local DATA_DIR asset storage
    -> Vertex AI through google-genai
```

프론트엔드는 Vertex AI를 직접 호출하지 않습니다. provider 접근은 백엔드 service boundary 안에 격리되어 있습니다. 로컬 개발에서는 deterministic mock provider를 사용할 수 있어 테스트와 smoke check가 실제 AI 비용을 만들지 않습니다.

## 기술 스택

- Backend: Python 3.11, FastAPI, SQLAlchemy async, asyncpg
- Database: PostgreSQL 16
- Frontend: Vite, React, TypeScript, TanStack Query
- AI SDK: `google-genai`
- Runtime: Docker Compose, Redis/Celery dispatch, local Postgres volume, local asset volume

## 빠른 시작: Mock Mode

Mock mode는 로컬 개발의 기본 권장 모드입니다. Google credential이 필요 없고 Gemini, Imagen, Veo를 실제 호출하지 않습니다.

1. 예시 파일로 `.env`를 만듭니다.

```powershell
Copy-Item .env.example .env
```

2. `.env`에서 아래 값을 유지하거나 설정합니다.

```env
AI_PROVIDER=mock
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal
GCP_PROJECT_ID=
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10
JOB_RUNNER_AUTO_START=false
JOB_DISPATCH_MODE=celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_DEFAULT_QUEUE=generation
CELERY_WORKER_CONCURRENCY=10
CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC=5
CELERY_WORKER_SHUTDOWN_GRACE_SEC=60
OUTBOX_DISPATCHER_BATCH_SIZE=50
OUTBOX_DISPATCHER_POLL_INTERVAL_SEC=1.0
OUTBOX_DISPATCHER_MAX_ATTEMPTS=10
VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
VITE_ALLOWED_HOSTS=localhost,127.0.0.1
```

Mock mode에서는 credential 관련 값을 비워둘 수 있습니다.

3. 로컬 환경을 확인합니다. 이 명령은 `.env`가 없으면 `.env.example`에서 만들고,
   기존 `.env`는 덮어쓰지 않습니다.

```powershell
.\scripts\setup_local.ps1
```

4. stack을 실행합니다.

```powershell
docker compose up -d --build
```

5. 앱을 엽니다.

- Frontend: <http://127.0.0.1:5173>
- Backend API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>

## Vertex Mode

Vertex mode는 실제 provider 요청을 보내며 비용이 발생할 수 있습니다. Gemini, Imagen, Veo live check를 의도적으로 실행할 때만 사용합니다.

필수 설정:

```env
AI_PROVIDER=vertex
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
```

Docker에서 ADC 또는 credential 파일을 쓰려면 host credential 경로와 container 경로를 함께 설정합니다.

```env
GOOGLE_APPLICATION_CREDENTIALS=/secrets/google-credentials.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/google-credentials.json
```

Service account 파일을 사용할 때도 같은 패턴을 사용합니다. credential JSON 내용은 `.env`, 문서, 로그, 커밋에 붙여 넣지 않습니다.

Health readiness는 provider 설정 가능 여부를 확인합니다. 모델 품질, quota, billing, live generation 성공을 보장하지는 않습니다.

```powershell
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
```

비용이 발생할 수 있는 generation 요청을 보내기 전에는 [Vertex live QA runbook](docs/runbooks/vertex-live-qa.md)을 먼저 확인합니다.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | DB 및 provider readiness 확인 |
| POST | `/api/prompts/enhance` | 편집 가능한 prompt enhancement 초안 생성 |
| POST | `/api/generations` | T2I, T2V, I2V generation job 생성 |
| GET | `/api/generations` | 필터 기반 job history 조회 |
| GET | `/api/generations/{job_id}` | asset과 state history를 포함한 단일 job 조회 |
| DELETE | `/api/generations/{job_id}` | terminal job 및 local asset 삭제 |
| POST | `/api/pipelines` | T2I parent와 blocked I2V child 생성 |
| GET | `/api/pipelines/{parent_job_id}` | parent/child pipeline 조회 |
| GET | `/api/assets/{asset_id}` | asset metadata 조회 |
| GET | `/files/{job_uuid}/{filename}` | 검증된 local media file streaming |

## 개발 검증

Backend:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Frontend:

```powershell
cd frontend
npm install
npm run build
```

Compose:

```powershell
docker compose config
```

## 문서

- [Architecture](docs/architecture.md)
- [Provider modes](docs/provider-modes.md)
- [Job lifecycle](docs/job-lifecycle.md)
- [Storage and assets](docs/storage-and-assets.md)
- [Testing strategy](docs/testing.md)
- [Local mock runbook](docs/runbooks/local-mock.md)
- [Vertex live QA runbook](docs/runbooks/vertex-live-qa.md)
- [Troubleshooting notes](docs/troubleshooting.md)
- [Architecture decision records](docs/adr)

## 안전 규칙

- `.env`, credential JSON, 생성 media, runtime log를 커밋하지 않습니다.
- 자동화 테스트는 mock 또는 fake provider를 사용합니다.
- Vertex live QA는 명시적이고 수동적이며 비용을 인지한 상태에서만 실행합니다.
- 현재 private repo의 git history에는 archived legacy context가 남아 있습니다. portfolio/public repo로 공개하려면 clean public history를 따로 만드는 것이 안전합니다.

## Mock Golden-Path Smoke

Run the backend HTTP golden path in mock mode only:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
```

If `db`, `redis`, `backend`, `dispatcher`, and `worker` are already running:

```powershell
python scripts/smoke_mock_golden_path.py --base-url http://127.0.0.1:8000
```

The smoke refuses `--env-file .env`, requires `AI_PROVIDER=mock`, starts the
redis, dispatcher, and worker services when `--compose` is used, and verifies health,
prompt enhancement, T2I generation, job state history, PNG asset serving,
byte-range streaming, and cleanup. In mock mode, `vertex_charged: true` only
means the mock provider handler completed; it is not real Vertex billing.
