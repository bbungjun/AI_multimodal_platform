# Project Context — AI Multimodal Content Platform

## What this is

채용 과제 (3일 제한). Google Vertex AI 의 Imagen 4 / Veo 3 를 사용해 텍스트→이미지, 텍스트→비디오, 이미지→비디오를 생성·관리하는 통합 플랫폼. 프롬프트 자동 개선(LLM enhance), 재시도, 모델별 rate limit, T2I→I2V 파이프라인이 핵심 요구사항.

원본 과제 명세: `/home/user/README.md` (Phase 17 에서 프로젝트 README 로 교체 예정).

## Current Status (2026-05-23)

The repository is no longer an initial empty scaffold.

- Backend implementation through Phase 10 is complete:
  - FastAPI app, async SQLAlchemy/Postgres wiring, health API, domain models,
    DTOs, strict state machine, storage/path safety, Vertex client adapters,
    retry/rate limiting, in-process job runner, Imagen T2I, Veo T2V/I2V,
    Gemini prompt enhancement, and T2I -> I2V pipeline APIs/linking.
  - Runtime startup now ensures `DATA_DIR` exists and initializes SQLAlchemy
    metadata before the job runner starts.
  - `/files/{local_path}` is served by the backend through existing storage path
    validation.
- Frontend required flows are complete under Phase 11, covering the original
  frontend Phase 11-14 scope:
  - app shell, typed API client, Generate + Enhance review/edit, Job Detail
    polling/waiting/result/I2V handoff, History filters/pagination, Pipeline
    launcher/detail polling.
- Phase 12 was rescoped to Docker Compose / integration readiness and is
  complete:
  - compose env/build hygiene,
  - backend runtime init and file serving,
  - frontend same-origin `/api` and `/files` proxy readiness,
  - compose smoke discovery and follow-up host revalidation.
- README remains the original assignment brief until Phase 17. Do not replace or
  rewrite it before Phase 17.
- `AI_COLLABORATION.md` remains a Phase 18 deliverable.

Recent status commits:

- `055bd5d docs: update phase 11 closeout`
- `3ab45fc docs: close out phase 12 compose readiness`
- `c403718 fix: align health response schema`
- `c96ba6c docs: update phase 12 compose smoke results`

Compose smoke status:

- A sandbox run confirmed compose config parsing but could not start services due
  to local Docker/Compose constraints.
- A later host run with Docker Compose v2 passed build, `up -d`, service health,
  backend `/api/health`, frontend-origin `/api/health`, backend `/files` 404
  behavior, frontend-origin `/files` proxy behavior, and frontend root load.
- The compose smoke did not call Vertex, Gemini, Imagen, Veo, generation, or
  prompt-enhance endpoints.
- No `.env` values, API keys, credential contents, or service-account JSON
  contents were recorded.

## Current High-Level Layout

```
/home/user/
├── README.md                    # original assignment brief; replace in Phase 17
├── AGENTS.md                    # active AI tool context
├── AI_COLLABORATION.md          # Phase 18 deliverable
├── docker-compose.yml           # db/backend/frontend compose setup
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── api/                 # health, generations, prompts, pipelines, files
│   │   ├── services/            # vertex, llm, jobs, rate limit, retry, storage
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── state_machine.py
│   └── tests/                   # backend unit/integration tests with mocked AI
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── api/                 # typed client + DTO mirrors
│       ├── hooks/               # job and pipeline polling hooks
│       ├── pages/               # Generate, Job Detail, History, Pipeline
│       └── components/          # shared UI primitives and icons
├── data/assets/                 # runtime asset mount; generated, not committed
└── session-history/             # optional submission artifact
```

## Historical Bootstrap Snapshot (2026-05-22; stale)

The snapshot below records the initial scaffold state and is retained only as
history. Do not use it as the current repo map.

```
/home/user/
├── README.md                    # 과제 명세 — 보존
├── tht-aif-*.json               # GCP service-account 키 패턴 (gitignored, 절대 노출 금지)
├── .gitignore                   # cred + .env + data + node/python 표준
├── .env.example                 # 키 위치, GCP location, enhance 모델 등 (값 없음)
├── CLAUDE.md                    # AI 도구 컨텍스트 (관례, 금지 사항)
├── AI_COLLABORATION.md          # Phase 18 에서 채울 골격
├── docker-compose.yml           # v1/v2 호환 (version 키 없음), 3 서비스
├── backend/
│   ├── Dockerfile               # Phase 0 stub
│   ├── pyproject.toml           # fastapi, sqlalchemy[asyncio], google-genai 등
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/                 # 비어있음
│   │   ├── services/{vertex,llm,jobs}/  # 비어있음
│   │   └── utils/               # 비어있음
│   └── tests/
│       └── __init__.py
├── frontend/
│   ├── Dockerfile               # Phase 0 stub
│   ├── package.json             # vite, react, tanstack-query, tailwind
│   └── src/{api,pages,components,hooks}/  # 비어있음
├── data/assets/                 # 결과물 저장소 (마운트 포인트)
├── session-history/             # 제출 시 채워질 디렉토리
└── uploads/                     # 빈 디렉토리 (호스트 제공)
```

## Credentials & env (값 비공개)

- **GCP service account JSON**: host filename and JSON contents are
  intentionally not recorded here. Use `.env`/`.env.example` to configure the
  host credential path, and mount it read-only inside the container.
  - 컨테이너 내부 표준 경로는 `/secrets/sa.json`.
  - 환경변수 `GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json` 로 SDK 가 자동 로드.
  - Do not record or commit JSON fields such as `private_key`, `client_email`,
    or other credential contents.
- **Vertex location**: configured by env; do not read or print real `.env`
  values during memory updates.
- **호스트 셸 env (Claude Code 하니스 주입, 과제 코드에서 사용 금지)**:
  `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` 등
- **과제 코드 인증 경로**: a single mounted service-account JSON is used by
  Imagen, Veo, and Gemini through `google-genai`.

## Toolchain (호스트 검증됨)

Current compose verification should prefer Docker Compose v2. The Phase 12
follow-up smoke used `sudo docker compose --env-file .env` successfully after a
Compose v2 plugin was installed. The older table below records the initial host
toolchain snapshot before that follow-up.

| 도구 | 버전 | 상태 |
|---|---|---|
| Python | 3.11.2 | ✅ |
| Node | v22.22.2 | ✅ |
| npm | 10.9.7 | ✅ |
| Docker | 20.10.24 | ✅ |
| docker-compose | v1 1.29.2 | ⚠️ v2 미설치 — compose 파일은 v1/v2 호환으로 작성 |

채점 환경은 v2 `docker compose` 가정. 본 워크스페이스에서는 `docker-compose up` 으로 검증.

## Vertex 모델 카탈로그

| 모드 | 모델 | Rate Limit | 비용 |
|---|---|---|---|
| T2I | imagen-4.0-fast-generate-001 | 75/min | $0.02/장 |
| T2I | imagen-4.0-generate-001 | 75/min | $0.04/장 |
| T2I | imagen-4.0-ultra-generate-001 | 75/min | $0.06/장 |
| T2V/I2V | veo-3.0-fast-generate-001 | 10/min | $0.15/sec |
| T2V/I2V | veo-3.0-generate-001 | 10/min | $0.40/sec |
| Enhance | gemini-2.5-flash | (호출량 적음) | (저렴) |

**예산 주의**: Veo 정품 8초는 ~$3.2. 개발 중 항상 fast 모델 + 4초 또는 모킹 사용.

## 산출물 체크리스트 (README 섹션 5)

- [ ] 소스 코드 전체 (자동 제출)
- [ ] AI 컨텍스트 파일 — `CLAUDE.md` ✅ 작성됨
- [ ] `README.md` — Phase 17 에서 작성 예정
- [ ] `AI_COLLABORATION.md` — Phase 18 에서 작성 예정 (Q1/Q2/Q3 + enhance 설계 원칙)
- [ ] `session-history/` — 본인 환경 수행 시 zip 에 포함

## 보안 원칙 (재강조)

1. `tht-aif-*.json` 은 절대 커밋/로그/외부 전송 금지
2. 로깅 시 자격 증명 경로만, 내용은 마스킹
3. 산출물 zip 제출 전 키 파일 포함 여부 재확인
4. `.gitignore` 패턴: `tht-aif-*.json`, `*.serviceaccount.json`, `.env*`
