# Vertex Studio

Google Vertex AI의 Imagen 4, Veo 3, Gemini 2.5 Flash를 활용해 이미지와 비디오 생성, prompt enhancement, T2I → I2V pipeline, 생성 history 관리를 제공하는 멀티모달 콘텐츠 생성 플랫폼입니다.

## 1. 프로젝트 아키텍처 및 핵심 설계

이 프로젝트는 과제 범위와 단일 인스턴스 실행 환경을 전제로, 별도의 Celery/Redis 없이 PostgreSQL job table과 FastAPI 내부 asyncio runner를 조합해 생성 작업을 처리합니다. Docker Compose는 PostgreSQL, FastAPI backend, Vite frontend를 함께 실행하며, 생성된 asset metadata는 DB에 저장하고 실제 파일 bytes는 로컬 `DATA_DIR`에 저장합니다.

```text
[React SPA]
    |
    v
[FastAPI API]
    |
    +-- [PostgreSQL] jobs / assets / prompt_enhancements
    |
    +-- [In-process asyncio Job Runner]
    |       |
    |       +-- [Vertex AI via google-genai] Imagen / Veo / Gemini
    |       +-- [Local Storage] DATA_DIR/{job_uuid}/{filename}
    |
    +-- [/files/{job_uuid}/{filename}] validated asset streaming
```

### Job Runner

FastAPI는 application lifespan에서 로컬 저장소와 DB schema를 초기화한 뒤, 같은 프로세스 안에서 asyncio 기반 job runner를 시작합니다. runner는 `pending` 상태이면서 `blocked=false`인 job을 PostgreSQL에서 `FOR UPDATE SKIP LOCKED`로 claim하고, `queued`로 전이한 뒤 mode별 handler task를 실행합니다.

동시 실행은 설정값 기반 concurrency limit과 `asyncio.Semaphore`로 제한합니다. 생성 요청은 Vertex 제출 전에 모델별 in-memory sliding-window rate limiter를 통과하며, Imagen 모델은 각 model id별 75 requests/minute, Veo 모델은 각 model id별 10 requests/minute로 제한합니다.
이 rate limiter는 backend 프로세스 내부의 in-memory limiter이므로, 복수 backend 프로세스 간 quota를 공유하거나 동기화하지는 않습니다.


Veo 작업은 polling 단계에서 Vertex operation name을 저장합니다. runner 재시작 시 `polling` 상태이면서 operation name이 있는 job은 저장된 operation name으로 polling을 재개할 수 있습니다. runner 시작 시 오래된 non-terminal job에 대해 1회 recovery sweep을 수행하며, 재개 가능한 polling job은 제외하고 stale job을 `failed`로 처리합니다.


### Vertex AI Integration

AI 호출은 `google-genai` 단일 SDK로 통합했습니다. 백엔드는 `genai.Client(vertexai=True, ...)`를 공유 client로 구성하고, Imagen 이미지 생성, Veo 비디오 생성, Gemini prompt enhancement에 같은 Vertex client 경로를 사용합니다.

Imagen은 `models.generate_images`로 받은 inline image bytes를 로컬 image asset으로 저장합니다. Veo는 `models.generate_videos`로 long-running operation을 생성하고, 완료 후 `generated_videos[0].video.video_bytes`를 읽어 MP4 asset으로 저장합니다. 현재 구현은 `output_gcs_uri`를 사용하지 않으며, GCS 대신 로컬 `DATA_DIR`에 파일을 저장합니다.

초기 Imagen 생성 호출과 초기 Veo submit 호출은 bounded retry helper로 감쌉니다. 기본 정책은 최대 3회 시도와 1초부터 시작하는 exponential backoff입니다. Veo polling 단계에서는 operation error, safety-filtered result, missing output을 `vertex_safety_blocked`, `vertex_output_unavailable` 같은 public error code로 분류합니다.

### State, Storage, and Pipeline

Job lifecycle은 명시적인 state machine으로 관리합니다. 일반적인 생성 흐름은 `pending -> queued -> generating -> polling/downloading -> completed`이며, `completed`, `failed`, `cancelled`는 terminal state입니다. runner와 handler의 상태 변경은 `transition(...)`을 통해 검증되고 `state_history`에 `{state, at, detail}` 형식으로 기록됩니다. 별도 detail이 없는 전이도 frontend timeline payload shape가 안정적이도록 `detail: null`을 유지합니다.

생성 파일은 `DATA_DIR/{job_uuid}/{filename}` 형태로 저장합니다. 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거쳐 UUID job directory, filename, `DATA_DIR` containment를 검증합니다. `/files/{job_uuid}/{filename}` route는 검증된 asset 파일만 스트리밍하며, video preview를 위해 single byte-range request를 지원합니다.

T2I → I2V pipeline은 parent T2I job과 blocked I2V child job을 함께 생성합니다. child job은 parent image asset이 준비되기 전까지 runner 대상에서 제외됩니다. parent T2I가 완료되면 첫 번째 image asset을 child의 `source_asset_id`로 연결하고 `blocked=false`로 바꾸어, 다음 runner tick에서 I2V job으로 처리되도록 합니다.

## 2. 기술 스택 & 사용 모델

### 기술 스택

- **Backend:** Python 3.11, FastAPI, SQLAlchemy async, asyncpg, PostgreSQL 16
- **Frontend:** Vite, React, TypeScript, Tailwind CSS, @tanstack/react-query
- **AI SDK:** `google-genai` 단일 SDK 사용
- **Infra:** Docker Compose, PostgreSQL named volume, local asset named volume

### 지원 모델

- **Imagen:** `imagen-4.0-fast-generate-001`, `imagen-4.0-generate-001`, `imagen-4.0-ultra-generate-001`
- **Veo:** `veo-3.0-fast-generate-001`, `veo-3.0-generate-001`
- **Prompt Enhancement:** `gemini-2.5-flash`

## 3. 주요 기능

| 영역 | 구현 내용 |
|---|---|
| 생성 모드 | Text-to-Image, Text-to-Video, Image-to-Video, T2I → I2V Pipeline을 지원합니다. |
| 모델 선택 | Imagen 4 Fast/Standard/Ultra, Veo 3 Fast/Standard 모델을 선택할 수 있습니다. |
| 생성 옵션 | 이미지 aspect ratio, 이미지 개수, 비디오 duration, I2V source image 연결을 지원합니다. |
| Prompt Enhancement | Gemini 기반으로 prompt 개선 초안을 생성하고, 사용자가 원본/개선본/components를 비교한 뒤 편집 및 수락할 수 있습니다. |
| Creativity Mode | Faithful, Balanced, Imaginative 모드로 prompt enhancement의 보강 강도를 조절합니다. 이 설정은 enhancement 단계에만 적용됩니다. |
| Job Detail | 활성 job을 2초 간격으로 polling하고, state history 기반 timeline, 현재 단계 요약, request summary, 결과 asset preview를 표시합니다. |
| I2V Source Context | 진행 중인 I2V job은 결과가 나오기 전에도 연결된 source image context를 보여줍니다. |
| Result Preview | 완료된 image/video asset을 상세 화면에서 확인할 수 있으며, image 결과에서는 해당 이미지를 source로 새 I2V 요청을 시작할 수 있습니다. |
| Pipeline | T2I parent job과 blocked I2V child job을 생성하고, parent image asset이 준비되면 child job에 연결해 다음 단계로 진행합니다. |
| History | mode, state, model, page size, asset type 필터를 제공하며, image thumbnail과 muted video preview를 표시합니다. |
| Deletion | completed/failed/cancelled 상태의 terminal job 삭제를 지원하며, active dependent job이 있으면 삭제를 차단합니다. |

Veo 기반 T2V/I2V는 Vertex AI long-running operation으로 처리되므로 Imagen 이미지 생성보다 완료 시간이 길 수 있습니다. 이를 고려해 모든 생성 요청은 비동기 job으로 저장하고, 프론트엔드는 polling 기반 timeline과 source/result preview를 통해 현재 작업 상태를 표시합니다.

## 4. API 엔드포인트 요약

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/health` | DB 연결 상태와 서비스 readiness를 확인합니다. 실제 Vertex 원격 호출을 수행하지는 않습니다. |
| POST | `/api/prompts/enhance` | Gemini 기반 prompt enhancement record를 생성합니다. |
| POST | `/api/generations` | `mode` 값에 따라 T2I, T2V, I2V generation job을 생성합니다. |
| GET | `/api/generations` | job history를 `mode`, `state`, `model`, `asset_kind`, pagination 조건으로 조회합니다. |
| GET | `/api/generations/{job_id}` | 단일 job의 상태, 입력값, state history, 생성 asset 정보를 조회합니다. |
| DELETE | `/api/generations/{job_id}` | terminal 상태 job과 해당 asset 파일을 삭제합니다. active dependent job이 있으면 거절됩니다. |
| POST | `/api/pipelines` | T2I parent job과 blocked I2V child job을 함께 생성합니다. |
| GET | `/api/pipelines/{parent_job_id}` | pipeline parent job과 연결된 I2V child job의 진행 상태를 조회합니다. |
| GET | `/api/assets/{asset_id}` | asset metadata와 `/files/...` URL을 조회합니다. |
| GET | `/files/{job_uuid}/{filename}` | `DATA_DIR` 아래 asset 파일을 안전하게 스트리밍합니다. video preview용 single byte range request를 지원합니다. |

Prompt enhancement는 generation 요청에 자동으로 적용되지 않습니다. 사용자가 `/api/prompts/enhance` 결과를 확인, 편집, 수락하면 프론트엔드는 개선된 prompt를 generation 요청의 `prompt`로 보내고, `enhancement_id`를 함께 전달해 job과 enhancement record를 연결합니다.

## 5. 주요 API 요청 예시

### Prompt Enhancement

```json
{
  "prompt": "고양이가 집에서 뛰어노는 사진",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced"
}
```

`creativity_preset`은 `faithful`, `balanced`, `imaginative`를 지원하며, Gemini prompt enhancement 단계의 temperature 및 컨텍스트 전략을 조절합니다. Imagen/Veo generation temperature 설정은 아닙니다.

### Text-to-Image

```json
{
  "mode": "t2i",
  "prompt": "Neon-soaked Seoul alley at night, rain reflections",
  "model": "imagen-4.0-fast-generate-001",
  "aspect_ratio": "1:1",
  "number_of_images": 1
}
```

### Text-to-Video

```json
{
  "mode": "t2v",
  "prompt": "A slow dolly forward through a rainy neon alley",
  "model": "veo-3.0-fast-generate-001",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

### Image-to-Video

```json
{
  "mode": "i2v",
  "prompt": "Slow camera push-in, subtle steam movement, rain ripples in puddles",
  "model": "veo-3.0-fast-generate-001",
  "source_asset_id": "00000000-0000-4000-8000-000000000000",
  "aspect_ratio": "16:9",
  "duration_sec": 4
}
```

### T2I → I2V Pipeline

```json
{
  "image_prompt": "Neon-soaked Seoul alley at night with a cyclist",
  "video_prompt": "Slow dolly forward as the cyclist passes and steam rises",
  "image_model": "imagen-4.0-fast-generate-001",
  "video_model": "veo-3.0-fast-generate-001",
  "image_aspect_ratio": "1:1",
  "video_aspect_ratio": "16:9",
  "duration_sec": 4
}
```

## 6. 환경 변수 및 실행 방법

### 실행 요구사항

- Docker
- Docker Compose v2.29.7 또는 호환되는 Docker Compose v2
- Vertex mode 실행 시 Vertex AI 접근 권한이 있는 GCP service account JSON 파일
- 비용 없는 로컬 개발/테스트만 할 때는 `AI_PROVIDER=mock`
- Backend container는 Python 3.11 기반으로 빌드됩니다. 로컬에 설치된 Python 버전보다 Docker image와 Compose 환경이 기준입니다.

이 프로젝트는 Docker Compose로 PostgreSQL, FastAPI 백엔드, Vite React 프론트엔드를 함께 실행합니다. 백엔드는 `8000`, 프론트엔드는 `5173` 포트로 노출되며, PostgreSQL은 외부 포트를 열지 않습니다.

### 환경 변수

프로젝트 루트에 `.env` 파일을 생성하고 필요한 값을 설정합니다. 서비스 계정 JSON 내용은 `.env`에 직접 넣지 않고, 호스트 파일 경로만 지정합니다.

```env
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal

AI_PROVIDER=vertex
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash

DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10

VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
VITE_ALLOWED_HOSTS=localhost,127.0.0.1
```

`GOOGLE_APPLICATION_CREDENTIALS_HOST`는 호스트 머신의 서비스 계정 JSON 절대 경로입니다. Docker Compose는 이 파일을 백엔드 컨테이너의 `/secrets/sa.json`에 read-only로 마운트합니다.

`AI_PROVIDER=mock`은 개인 로컬 개발/테스트용입니다. 이 모드에서는 Vertex/Gemini/Imagen/Veo를 실제 호출하지 않고 deterministic mock image/prompt 결과로 API, job runner, storage, frontend preview 흐름을 확인합니다. 현재 Compose 파일은 read-only credential mount를 항상 선언하므로 mock mode에서도 `GOOGLE_APPLICATION_CREDENTIALS_HOST`는 repo 밖의 임시 dummy JSON 파일 경로로 채워야 합니다. 이 파일은 실제 서비스 계정이 아니어도 되며 커밋하지 않습니다.

Mock mode 예시:

```env
AI_PROVIDER=mock
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/to/local-dummy-service-account.json
GCP_PROJECT_ID=
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
```

### Docker Compose 실행

일반 로컬 환경:

```bash
docker compose up -d --build
```

E2B 과제 환경:

```bash
sudo -E docker compose up -d --build --force-recreate frontend backend db
```

### 접속 URL

로컬 환경:

- Frontend: http://localhost:5173
- Backend API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

E2B 환경:

- Frontend: `https://5173-${E2B_SANDBOX_ID}.e2b.app`
- Backend: `https://8000-${E2B_SANDBOX_ID}.e2b.app`

### 종료

```bash
docker compose down
```

DB 데이터와 생성된 asset volume까지 삭제하려면 다음 명령을 사용합니다.

```bash
docker compose down -v
```

`down -v`는 PostgreSQL 데이터와 생성된 에셋 파일을 삭제하므로 의도한 경우에만 사용합니다.

## 7. 테스트 및 검증

Backend 테스트는 실제 Vertex AI/Gemini를 호출하지 않고 mock/fake 기반으로 실행됩니다.

```bash
cd backend
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

Frontend 타입 검사와 빌드:

```bash
cd frontend
npm install
npm run lint
npm run build
```
